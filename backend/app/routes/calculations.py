"""Teacher and organization assessment routes.

The original teacher Rule/Assessment models and formulas remain compatible.
Department/college/school assessments use separate R3 models, evidence and workflow;
real school calculation policy still requires school sample confirmation.
"""
from fastapi import APIRouter,Request,HTTPException
from fastapi.responses import Response
from urllib.parse import quote
from types import SimpleNamespace
from sqlalchemy import select,func
from decimal import Decimal
from ..core import *
from ..schemas import *
from ..assessment_evidence import assessment_projection, make_archive
from ..org_evidence import verified_org_archive, organization_summary
from ..services import facts,evaluate,evaluate_rule,calculate_points,calculate_assessments,rounded,assessment_source_changes,point_source_changes
from ..calculation_freshness import require_current_sources,relevant_disputes
from ..scoring_methods import clean_teacher_config
from ..read_queries import assessment_query,ASSESSMENT_FILTERS,authorized_org_descendants
from ..social_training import point_entry_read_item
from .business import owned_object,events
from ..identities import stage_handler,VACANCY_LABEL
from ..org_assessment import (OrganizationAssessmentRule,OrganizationRuleTrial,OrganizationAssessment,OrganizationAssessmentMetricEvidence,
    validate_org_rule_config,organization_facts,evaluate_org_rule,archive_payload,ORG_TARGET_KINDS,organization_source_changes,org_rule_warnings)
router=APIRouter(prefix='/api',tags=['积分与教师考核'])

@router.get('/rules')
def rules(request:Request):
    f,_,_=filters_from(request,{'period_id'})
    def load(db,a,s):
        q=select(Rule)
        if f.get('period_id'):q=q.where(Rule.period_id==f['period_id'])
        items=db.scalars(q.order_by(Rule.created_at.desc(),Rule.id)).all()
        # 9.8/10.8: the copy source is recorded in the immutable audit trail (no schema change).
        sources={x.object_id:(x.after or {}).get('source_rule_id') for x in db.scalars(select(Audit).where(Audit.module=='rules',
            Audit.action==RULE_COPY_ACTION,Audit.object_id.in_([r.id for r in items])))} if items else {}
        return {'items':[{**serial(r),'copied_from':sources.get(r.id)} for r in items]}
    return read_operation(request,'rules.manage',load)

@router.post('/rules')
def create_rule(data:RuleIn,request:Request):
    def apply(db,a,s):
        require_open_period(db,data.period_id);config=clean_teacher_config(serial(data.config.model_dump()),data.kind)
        version=(db.scalar(select(func.max(Rule.version_no)).where(Rule.period_id==data.period_id,Rule.kind==data.kind)) or 0)+1
        obj=Rule(kind=data.kind,name=data.name,period_id=data.period_id,version_no=version,config=config,
          fingerprint=digest({'kind':data.kind,'period_id':data.period_id,'config':config}),created_by=a.id,reason=data.reason)
        db.add(obj);db.flush();audit(db,a,'rules',obj.id,'创建新规则版本',after=serial(obj),reason=data.reason);return obj
    return command(request,data.model_dump(),'rules.manage',apply)

RULE_COPY_ACTION='复制为新的教师规则草稿'

@router.post('/rules/{ident}/copy')
def copy_rule(ident:str,data:RuleCopy,request:Request):
    """9.8/10.8: new DRAFT rule from an existing one; source id/version recorded; trial still required."""
    def apply(db,a,s):
        from copy import deepcopy
        source=db.get(Rule,ident)
        if not source:raise HTTPException(404,'规则不存在')
        check_version(source,data.expected_version);require_open_period(db,data.period_id)
        config=clean_teacher_config(serial(data.config.model_dump()),source.kind) if data.config is not None else deepcopy(source.config)
        from pydantic import ValidationError
        try:RuleIn(kind=source.kind,name=data.name,period_id=data.period_id,config=config,reason=data.reason)  # same validation as a new rule
        except ValidationError:raise HTTPException(422,'复制后的规则配置不符合规范（积分规则不能引用本期积分等）') from None
        version=(db.scalar(select(func.max(Rule.version_no)).where(Rule.period_id==data.period_id,Rule.kind==source.kind)) or 0)+1
        obj=Rule(kind=source.kind,name=data.name,period_id=data.period_id,version_no=version,config=config,state='DRAFT',
          fingerprint=digest({'kind':source.kind,'period_id':data.period_id,'config':config}),created_by=a.id,reason=data.reason)
        db.add(obj);db.flush()
        audit(db,a,'rules',obj.id,RULE_COPY_ACTION,after={'source_rule_id':source.id,'source_version_no':source.version_no,'source_period_id':source.period_id,'rule':serial(obj)},reason=data.reason)
        return {**serial(obj),'copied_from':source.id,'trial_required':True}
    return command(request,data.model_dump(),'rules.manage',apply)

@router.post('/rules/{ident}/trial')
def trial(ident:str,data:Trial,request:Request):
    def apply(db,a,s):
        obj=db.get(Rule,ident)
        if not obj:raise HTTPException(404,'规则不存在')
        p=require_open_period(db,obj.period_id);items=[]
        for tid in data.teacher_ids:
            a.check_teacher(db,tid,active=True);raw,snap=facts(db,tid,p);detail=evaluate_rule(obj,raw)
            items.append({'teacher_id':tid,'detail':detail,'total':str(rounded(sum((Decimal(x['score']) for x in detail),Decimal(0))))})
        db.add(RuleTrial(rule_id=obj.id,fingerprint=obj.fingerprint,result=items,actor_id=a.id))
        audit(db,a,'rules',obj.id,'样本试算',after={'teachers':len(items),'fingerprint':obj.fingerprint},reason='规则样本试算，不写积分或考核台账')
        return {'items':items}
    return command(request,data.model_dump(),'rules.manage',apply)

@router.post('/rules/{ident}/actions')
def rule_action(ident:str,data:Action,request:Request):
    def apply(db,a,s):
        obj=db.get(Rule,ident)
        if not obj:raise HTTPException(404,'规则不存在')
        check_version(obj,data.expected_version);require_open_period(db,obj.period_id);before=serial(obj)
        # Revalidate persisted JSON rather than trusting a previously saved draft.
        RuleIn(kind=obj.kind,name=obj.name,period_id=obj.period_id,config=obj.config,reason=data.reason)
        if data.action=='activate':
            if obj.kind=='assessment' and sum(Decimal(c['weight']) for c in obj.config['components'])!=Decimal(100):
                raise HTTPException(422,'考核权重总和必须为100')
            if not db.scalar(select(RuleTrial.id).where(RuleTrial.rule_id==ident,RuleTrial.fingerprint==obj.fingerprint).limit(1)):
                raise HTTPException(409,'必须对当前规则版本执行样本试算后再启用')
            for old in db.scalars(select(Rule).where(Rule.kind==obj.kind,Rule.period_id==obj.period_id,Rule.state=='ACTIVE',Rule.id!=ident)):
                old_before=serial(old);old.state='INACTIVE';old.version+=1
                audit(db,a,'rules',old.id,'新规则替代旧规则',old_before,serial(old),data.reason)
            obj.state='ACTIVE'
        elif data.action=='deactivate':obj.state='INACTIVE'
        else:raise HTTPException(422,'规则操作无效')
        obj.version+=1;audit(db,a,'rules',ident,'规则启停',before,serial(obj),data.reason);return obj
    return command(request,data.model_dump(),'rules.manage',apply)

@router.post('/points/calculate')
def point_calculate(data:Calculate,request:Request):
    def apply(db,a,s):
        p=require_open_period(db,data.period_id)
        return calculate_points(db,a,p,data.teacher_ids,data.item_keys,data.reason)
    return command(request,data.model_dump(),'points.calculate',apply)

@router.get('/points/calculation-items')
def point_calculation_items(request:Request):
    f,_,_=filters_from(request,{'period_id'})
    def load(db,a,s):
        if not f.get('period_id'):raise HTTPException(422,'请选择考核周期')
        require_open_period(db,f['period_id'])
        rule=db.scalar(select(Rule).where(Rule.period_id==f['period_id'],Rule.kind=='points',Rule.state=='ACTIVE'))
        if not rule:return {'items':[],'rule_name':None}
        return {'items':[{'key':c['key'],'label':c['label']} for c in rule.config['components']],'rule_name':rule.name}
    return read_operation(request,'points.calculate',load)

@router.post('/assessments/calculate')
def assessment_calculate(data:Calculate,request:Request):
    if data.item_keys:raise HTTPException(422,'教师考核不接收积分项参数')
    def apply(db,a,s):
        period=require_open_period(db,data.period_id)
        # 重算时只提醒新生成或得分变了的老师，避免学校反复试算时同一位老师收到多条消息。
        before={x.teacher_id:x.score for x in db.scalars(select(Assessment).where(Assessment.period_id==period.id,Assessment.teacher_id.in_(data.teacher_ids or [''])))}
        result=calculate_assessments(db,a,period,data.teacher_ids,data.reason)
        from ..message_push import queue
        changed=[x['teacher_id'] for x in result['items'] if x.get('state')=='TEACHER' and (x['teacher_id'] not in before or Decimal(str(before[x['teacher_id']]))!=Decimal(str(x['score'])))]
        queue(db,changed,'年度考核结果已生成，请确认','请登录非学历教育智慧前台，核对本人考核得分后点“本人确认”。')
        return result
    return command(request,data.model_dump(),'assessment.calculate',apply)

def point_scope(db,a,model,f):
    q=select(model).where(a.scope(model.teacher_id))
    for k in ('teacher_id','period_id'):
        if f.get(k):q=q.where(getattr(model,k)==f[k])
    if f.get('org_id'):q=q.where(model.teacher_id.in_(select(User.id).where(User.org_id.in_(authorized_org_descendants(db,a,f['org_id'])))))
    return q

@router.get('/points')
def points(request:Request):
    f,p,z=filters_from(request,{'teacher_id','period_id','org_id'})
    def load(db,a,s):
        q=point_scope(db,a,PointEntry,f);out=page_result(db,q.order_by(PointEntry.created_at.desc(),PointEntry.id),p,z)
        out['items']=[point_entry_read_item(db,a,item) for item in out['items']]
        sub=q.subquery();out['sum']=db.scalar(select(func.coalesce(func.sum(sub.c.amount),0)))
        return out
    return read_operation(request,'points.read',load)

@router.get('/points/{ident}')
def point_detail(ident:str,request:Request):
    def load(db,a,s):
        obj=owned_object(db,a,PointEntry,ident,'points.read')
        rule=db.get(Rule,obj.rule_id) if obj.rule_id else None
        batch=db.get(CalculationBatch,obj.batch_id) if obj.batch_id else None
        return {**point_entry_read_item(db,a,obj),'rule_display_name':(obj.source_snapshot or {}).get('rule',{}).get('name') or (rule.name if rule else '人工复核调整'),
                'batch_created_at':batch.created_at if batch else None}
    return read_operation(request,'points.read',load)

@router.get('/point-balances')
def balances(request:Request):
    f,_,_=filters_from(request,{'teacher_id','period_id','org_id'})
    def load(db,a,s):
        rows=db.scalars(point_scope(db,a,PointBalance,f).order_by(PointBalance.created_at,PointBalance.id)).all()
        period_ids={x.period_id for x in rows};teacher_ids={x.teacher_id for x in rows}
        periods=dict(db.execute(select(Period.id,Period.state).where(Period.id.in_(period_ids))).all())
        archived=set(db.execute(select(Assessment.teacher_id,Assessment.period_id).where(Assessment.teacher_id.in_(teacher_ids),Assessment.period_id.in_(period_ids),Assessment.state=='ARCHIVED')).all())
        items=[]
        for obj in rows:
            reason='考核已归档，该周期积分只读' if (obj.teacher_id,obj.period_id) in archived else '周期已关闭，积分只读' if periods.get(obj.period_id)!='OPEN' else ''
            items.append({**serial(obj),'locked':bool(reason),'lock_reason':reason})
        return {'items':items}
    return read_operation(request,'points.read',load)

@router.post('/point-balances/{ident}/actions')
def balance_action(ident:str,data:Action,request:Request):
    permission='points.read' if data.action=='confirm' else 'points.adjust'
    def apply(db,a,s):
        obj=owned_object(db,a,PointBalance,ident,permission);check_version(obj,data.expected_version)
        require_open_period(db,obj.period_id)
        if archive_exists(db,obj.teacher_id,obj.period_id):raise HTTPException(409,'已归档周期积分不可更改')
        before=serial(obj)
        if data.action=='confirm':
            if obj.teacher_id!=a.id:raise HTTPException(403,'积分必须由本人确认')
            if obj.confirmed:raise HTTPException(409,'积分已经确认')
            point_rows=db.scalars(select(PointEntry).where(PointEntry.teacher_id==obj.teacher_id,PointEntry.period_id==obj.period_id)).all()
            record_ids={r['id'] for p in point_rows for r in (p.source_snapshot or {}).get('facts',{}).get('training_records',[])}
            if db.scalar(relevant_disputes(obj.teacher_id,db.get(Period,obj.period_id),record_ids).limit(1)):
                raise HTTPException(409,'请先处理本周期未解决核对申请')
            require_current_sources(point_source_changes(db,obj.teacher_id,db.get(Period,obj.period_id)))
            obj.confirmed=True
        elif data.action=='reopen':
            if not obj.confirmed or not data.basis:raise HTTPException(409,'解锁需已确认状态且填写依据')
            obj.confirmed=False
        else:raise HTTPException(422,'积分确认操作无效')
        obj.version+=1
        ledger=db.scalars(select(PointEntry).where(PointEntry.teacher_id==obj.teacher_id,PointEntry.period_id==obj.period_id).order_by(PointEntry.id)).all()
        confirmation={'balance':serial(obj),'entries':[{'id':e.id,'amount':str(e.amount)} for e in ledger],
                      'total':str(sum((Decimal(e.amount) for e in ledger),Decimal(0)))}
        workflow(db,a,'point_balance',obj.id,'积分确认' if obj.confirmed else '留痕解锁积分',before,confirmation,data.reason,data.basis)
        return obj
    return command(request,data.model_dump(),permission,apply)

@router.post('/points/adjust')
def point_adjust(data:PointAdjust,request:Request):
    def apply(db,a,s):
        a.check_teacher(db,data.teacher_id,active=True);require_open_period(db,data.period_id)
        if db.scalar(select(PointEntry.id).where(PointEntry.teacher_id==data.teacher_id,PointEntry.period_id==data.period_id,PointEntry.kind=='SOCIAL').limit(1)):raise HTTPException(409,'社会培训积分须从原认定办理更正并逐级审核')
        if not data.basis or data.amount==0:raise HTTPException(422,'人工调整必须填写依据且分值不能为零')
        if archive_exists(db,data.teacher_id,data.period_id):raise HTTPException(409,'归档后的积分不可更改')
        bal=db.scalar(select(PointBalance).where(PointBalance.teacher_id==data.teacher_id,PointBalance.period_id==data.period_id))
        if bal and bal.confirmed:raise HTTPException(409,'请先按授权流程留痕解锁')
        if not bal:bal=PointBalance(teacher_id=data.teacher_id,period_id=data.period_id);db.add(bal);db.flush()
        before_total=db.scalar(select(func.coalesce(func.sum(PointEntry.amount),0)).where(PointEntry.teacher_id==data.teacher_id,PointEntry.period_id==data.period_id))
        obj=PointEntry(teacher_id=data.teacher_id,period_id=data.period_id,item_key=data.item_key,kind='MANUAL',amount=data.amount,raw_value=str(data.amount),
          formula=f'人工调整 {data.amount}',source_snapshot={'before_total':str(before_total),'after_total':str(before_total+data.amount),'basis':data.basis},
          actor_id=a.id,reason=data.reason,basis=data.basis)
        db.add(obj);db.flush();bal.version+=1
        workflow(db,a,'points',obj.id,'追加积分调整',{'total':str(before_total)},{'total':str(before_total+data.amount),'entry':serial(obj)},data.reason,data.basis)
        return obj
    return command(request,data.model_dump(),'points.adjust',apply)

@router.get('/assessment-summary/latest')
def latest_assessment_summary(request:Request):
    f,_,_=filters_from(request,{'period_id'})
    def load(db,a,s):
        if a.role.kind!='teacher' or not a.user.staff_no:
            raise HTTPException(403,'仅教师本人查看最近考核')
        period=None
        if f.get('period_id'):
            period=db.get(Period,f['period_id'])
            if not period:raise HTTPException(404,'考核周期不存在')
            obj=db.scalar(select(Assessment).where(Assessment.teacher_id==a.id,Assessment.period_id==period.id).limit(1))
        else:
            obj=db.scalar(select(Assessment).join(Period,Period.id==Assessment.period_id)
                .where(Assessment.teacher_id==a.id)
                .order_by(Period.end_date.desc(),Period.start_date.desc(),Assessment.created_at.desc(),Assessment.id.desc()).limit(1))
            if obj:period=db.get(Period,obj.period_id)
        return {'assessment':obj,'period':period}
    return read_operation(request,'assessment.read',load)

@router.get('/assessments')
def assessments(request:Request):
    f,p,z=filters_from(request,ASSESSMENT_FILTERS)
    def load(db,a,s):
        q=assessment_query(db,a,f)
        ordered=q.order_by(Assessment.score.desc(),Assessment.teacher_id)
        out=page_result(db,ordered,p,z);sub=q.subquery()
        for i,item in enumerate(out['items']):
            item['scope_rank']=(p-1)*z+i+1
            # 10.7 competition ranking: equal scores share a rank (1,1,3).
            item['rank']=1+db.scalar(select(func.count()).select_from(sub).where(sub.c.score>Decimal(str(item['score']))))
            if item['state']=='ARCHIVED':
                frozen=assessment_projection(db,SimpleNamespace(**item))
                item['teacher_display_name']=frozen['teacher']['name']
                item['period_display_name']=frozen['period']['name']
                item['identity_frozen']=frozen['identity_frozen']
        out['rank_note']='当前授权与筛选范围的得分排序：“名次”同分并列（如 1、1、3），序号仅用于翻页定位；不代表全校名次。'
        return out
    return read_operation(request,'assessment.read',load)

RANKING_PRINT_LIMIT=2000

@router.get('/assessment-ranking/print')
def assessment_ranking_print(request:Request):
    """10.7 printable teacher ranking for the current filter; same scope/filters as the list."""
    f,_,_=filters_from(request,ASSESSMENT_FILTERS)
    def load(db,a,s):
        a.require('assessment.read');q=assessment_query(db,a,f)
        total=db.scalar(select(func.count()).select_from(q.order_by(None).subquery()))
        if total>RANKING_PRINT_LIMIT:raise HTTPException(422,f'打印范围超过 {RANKING_PRINT_LIMIT} 人，请按周期或组织缩小范围')
        sub=q.subquery();ranked=select(sub.c.id,func.rank().over(order_by=sub.c.score.desc()).label('rank')).subquery()
        ranks=dict(db.execute(select(ranked.c.id,ranked.c.rank)).all())
        rows=db.scalars(q.order_by(Assessment.score.desc(),Assessment.teacher_id)).all();items=[]
        for obj in rows:
            if obj.state=='ARCHIVED':
                frozen=assessment_projection(db,obj);name=frozen['teacher']['name'];staff=frozen['teacher'].get('staff_no');period=frozen['period']['name']
            else:
                user=db.get(User,obj.teacher_id);name=user.name if user else '';staff=user.staff_no if user else '';period=(db.get(Period,obj.period_id) or SimpleNamespace(name='')).name
            items.append({'teacher_id':obj.teacher_id,'teacher_name':name,'staff_no':staff,'period_name':period,'score':obj.score,'state':obj.state,'returned':obj.returned,'rank':ranks[obj.id]})
        audit(db,a,'assessment','ranking','打印教师考核排名表',after={'filters':f,'rows':len(items)},reason='授权打印当前筛选范围排名')
        return {'items':items,'total':total,'filters':f,'rank_method':'competition','printed_at':utcnow(),
            'note':'当前授权与筛选范围内排名，同分并列；未归档结果为过程数据，不替代最终确认结果。'}
    return read_operation(request,'export',load)

def st_reviews(db,teacher_id):
    from ..social_training import open_point_reviews
    return open_point_reviews(db,teacher_id)

def assessment_open_disputes(db,obj):
    return relevant_disputes(obj.teacher_id,db.get(Period,obj.period_id),[r['id'] for r in obj.source_snapshot.get('training_records',[])])

def assessment_details(db,a,ident,permission='assessment.read'):
    obj=owned_object(db,a,Assessment,ident,permission)
    result=assessment_projection(db,obj,events(db,'assessment',ident) if obj.state!='ARCHIVED' else None)
    pending=db.scalars(assessment_open_disputes(db,obj).order_by(Dispute.created_at,Dispute.id)).all() if obj.state!='ARCHIVED' else []
    result['source_changes']=assessment_source_changes(db,obj)
    can_view='dispute.write' in a.permissions
    result['open_point_reviews']=len(st_reviews(db,obj.teacher_id)) if obj.state!='ARCHIVED' else 0
    handler,vacant=stage_handler(db,db.get(User,obj.teacher_id),obj.state)
    result['handler']={'kind':handler,'acting_for':VACANCY_LABEL.get(vacant)}
    result['confirmation_blockers']={'count':len(pending),'can_view':can_view,
        'can_resolve':can_view and 'dispute.resolve' in a.permissions and obj.teacher_id!=a.id,
        'items':[{'id':d.id,'object_type':d.object_type,'reason':d.reason,'created_at':serial(d)['created_at']} for d in pending] if can_view else []}
    return result

@router.get('/assessments/{ident}')
def assessment_detail(ident:str,request:Request):
    return read_operation(request,'assessment.read',lambda db,a,s:assessment_details(db,a,ident))

@router.get('/assessments/{ident}/print')
def assessment_print(ident:str,request:Request):
    def load(db,a,s):
        result=assessment_details(db,a,ident)
        audit(db,a,'assessment',ident,'打印考核结果',after={'version':result['assessment']['version'],'immutable':result['immutable']},reason='授权打印考核结果')
        return result
    return read_operation(request,'export',load)

@router.get('/assessments/{ident}/evidence')
def assessment_evidence_download(ident:str,request:Request):
    with request.app.state.sessions.begin() as db:
        a,s=current_actor(db,request);a.require('export')
        result=assessment_details(db,a,ident)
        if not result['immutable']:raise HTTPException(409,'仅已归档考核可以下载冻结证据')
        payload={'format':'Yueke teacher assessment evidence v2','archive':result['assessment']['archive'],
                 'archive_sha256':result['assessment']['archive_sha256']}
        from ..sensitive import MaskPolicy
        policy=MaskPolicy(db,a);payload=policy.apply(serial(payload))
        if policy.masked:payload['masked_fields']=policy.masked;payload['masking_note']='证书编号/工号已按查看人权限脱敏，本文件不能用于复核归档SHA256'
        data=json.dumps(payload,ensure_ascii=False,indent=2).encode('utf-8')
        audit(db,a,'assessment',ident,'下载教师考核归档证据',after={'archive_sha256':payload['archive_sha256'],'masked_fields':policy.masked},reason='当前权限核验后下载原归档快照')
    return Response(data,media_type='application/json',headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote('教师考核归档证据_'+ident+'.json'),'X-Content-Type-Options':'nosniff'})

@router.get('/assessments/{ident}/attachments/{attachment_id}/download')
def assessment_frozen_attachment(ident:str,attachment_id:str,request:Request):
    from ..assessment_evidence import attachment_index
    from .files import verify_file
    with request.app.state.sessions.begin() as db:
        a,s=current_actor(db,request);a.require('file.read')
        result=assessment_details(db,a,ident)
        if not result['immutable']:raise HTTPException(409,'当前考核尚未归档')
        frozen=result['assessment']['archive']
        item=attachment_index(frozen['source_snapshot'],result['assessment']['teacher_id']).get(attachment_id)
        if item is None:raise HTTPException(404,'该附件不在本次归档依据中')
        stored=db.get(Attachment,attachment_id)
        if not stored or any(getattr(stored,k)!=item.get(k) for k in ('teacher_id','object_type','object_id')):
            raise HTTPException(409,'归档附件业务关联校验失败')
        # Physical key is never exported; digest and size are taken from the archive,
        # so rewriting live attachment metadata cannot bless replacement bytes.
        expected=SimpleNamespace(storage_key=stored.storage_key,sha256=item['sha256'],size=item['size'])
        data=verify_file(request.app.state.settings.storage_dir,expected)
        audit(db,a,'assessment',ident,'下载归档时资质附件',after={'attachment_id':attachment_id,'sha256':item['sha256']},reason='仅下载本次归档引用的原版本附件')
    return Response(data,media_type=item['mime'],headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(item['name']),'X-Content-Type-Options':'nosniff'})

@router.post('/assessments/{ident}/actions')
def assessment_action(ident:str,data:Action,request:Request):
    def apply(db,a,s):
        obj=owned_object(db,a,Assessment,ident,'assessment.read');check_version(obj,data.expected_version)
        require_open_period(db,obj.period_id)
        if obj.state=='ARCHIVED':raise HTTPException(409,'已归档考核不可修改')
        before=serial(obj);handling={}
        if data.action=='confirm':
            if db.scalar(assessment_open_disputes(db,obj).limit(1)):
                raise HTTPException(409,'存在未解决数据核对，请先处理')
            if st_reviews(db,obj.teacher_id):raise HTTPException(409,'该教师有教研室发起的积分核对（或由此生成的更正）尚未办结，请先办结后再确认')
            if obj.state=='TEACHER':
                a.require('assessment.confirm')
                if obj.teacher_id!=a.id:raise HTTPException(403,'考核必须由本人确认')
                obj.state='DEPARTMENT'
            else:
                a.require('assessment.review')
                expected={'DEPARTMENT':('dept','COLLEGE'),'COLLEGE':('college','SCHOOL'),'SCHOOL':('school','READY')}.get(obj.state)
                handler,vacant=stage_handler(db,db.get(User,obj.teacher_id),obj.state)
                if not expected or handler!=a.role.kind or obj.teacher_id==a.id:raise HTTPException(403,'不能越级审核或审核本人考核')
                handling={'stage':obj.state,'acting_for':VACANCY_LABEL.get(vacant)}
                previous=db.scalar(select(WorkflowEvent).where(WorkflowEvent.object_type=='assessment',WorkflowEvent.object_id==ident,
                    WorkflowEvent.action=='考核确认').order_by(WorkflowEvent.created_at.desc(),WorkflowEvent.id.desc()).limit(1))
                if obj.state in ('COLLEGE','SCHOOL') and previous is not None and previous.actor_id==a.id and (previous.before or {}).get('state')!='TEACHER':
                    handling['same_person']='同一人连审'
                obj.state=expected[1]
            obj.returned=False
        elif data.action=='return':
            a.require('assessment.review')
            expected,vacant=stage_handler(db,db.get(User,obj.teacher_id),obj.state)
            if expected is None or obj.state=='TEACHER' or expected!=a.role.kind or obj.teacher_id==a.id:raise HTTPException(403,'不能越级退回或复核本人考核')
            handling={'stage':obj.state,'acting_for':VACANCY_LABEL.get(vacant)}
            obj.state='TEACHER';obj.returned=True
            from ..message_push import queue
            queue(db,[obj.teacher_id],'年度考核被退回，请重新核对','请登录非学历教育智慧前台，查看退回原因后重新确认本人考核。')
        elif data.action=='archive':
            a.require('assessment.archive')
            if a.role.kind!='school' or obj.state!='READY' or obj.teacher_id==a.id:raise HTTPException(403,'仅学校可归档已审核结果')
            if db.scalar(assessment_open_disputes(db,obj).limit(1)):
                raise HTTPException(409,'仍有未解决核对申请，不能归档')
            if st_reviews(db,obj.teacher_id):raise HTTPException(409,'该教师有教研室发起的积分核对（或由此生成的更正）尚未办结，请先办结后再确认')
            require_current_sources(assessment_source_changes(db,obj))
            obj.archive=make_archive(db,obj,a,events(db,'assessment',ident),data.reason,data.basis,request.app.state.settings.storage_dir)
            obj.state='ARCHIVED'
            obj.archive_sha256=digest(obj.archive)
        else:raise HTTPException(422,'考核操作无效')
        if data.action=='confirm':require_current_sources(assessment_source_changes(db,obj))
        obj.version+=1
        after=serial(obj)
        handling={k:v for k,v in handling.items() if v}
        if len(handling)>1:after['handling']=handling
        workflow(db,a,'assessment',ident,{'confirm':'考核确认','return':'退回教师核对','archive':'考核归档'}[data.action],before,after,data.reason,data.basis)
        return obj
    return command(request,data.model_dump(),'assessment.read',apply)

@router.post('/assessments/{ident}/adjust')
def assessment_adjust(ident:str,data:ScoreAdjust,request:Request):
    def apply(db,a,s):
        obj=owned_object(db,a,Assessment,ident,'assessment.calculate');check_version(obj,data.expected_version)
        require_open_period(db,obj.period_id)
        if obj.state!='TEACHER' or not data.basis or data.delta==0:raise HTTPException(409,'只能在教师核对环节追加有依据的更正项')
        before=serial(obj);new_score=rounded(Decimal(obj.score)+data.delta)
        if not 0<=new_score<=100:raise HTTPException(422,'调整后的考核得分必须在0至100之间')
        obj.detail=[*obj.detail,{'key':'manual_'+uid(),'label':'人工复核更正项','source':'manual','raw':str(data.delta),
          'formula':f'原总分 {obj.score} + 更正 {data.delta} = {new_score}','score':str(data.delta),
          'actor_id':a.id,'at':utcnow().isoformat(),'reason':data.reason,'basis':data.basis}]
        obj.score=new_score;obj.version+=1
        workflow(db,a,'assessment',ident,'追加考核更正项',before,serial(obj),data.reason,data.basis);return obj
    return command(request,data.model_dump(),'assessment.calculate',apply)


# ---- Organization assessment extension: department / college / school ----
def _org_target(db,a,target_id,target_kind,*,for_review=False):
    obj=db.get(Org,target_id)
    if not obj or obj.kind!=target_kind or not obj.active: raise HTTPException(404,'组织考核对象不存在')
    # School calculation can select any valid target. Reviewers are limited to
    # their own organization, never an ancestor or sibling target.
    if for_review:
        if a.role.kind!=target_kind or a.org.id!=obj.id: raise HTTPException(403,'只能复核本人负责的组织考核')
    elif a.role.kind!='school' and obj.id not in a.org_ids:
        raise HTTPException(403,'组织考核对象超出授权范围')
    return obj

@router.get('/organization-assessment-rules')
def organization_rules(request:Request):
    f,_,_=filters_from(request,{'period_id','target_kind'})
    def load(db,a,s):
        q=select(OrganizationAssessmentRule)
        if f.get('period_id'):q=q.where(OrganizationAssessmentRule.period_id==f['period_id'])
        if f.get('target_kind'):
            if f['target_kind'] not in ORG_TARGET_KINDS:raise HTTPException(422,'组织考核对象无效')
            q=q.where(OrganizationAssessmentRule.target_kind==f['target_kind'])
        return {'items':[{**serial(obj),'warnings':org_rule_warnings(obj.config)} for obj in db.scalars(q.order_by(OrganizationAssessmentRule.created_at.desc(),OrganizationAssessmentRule.id))]}
    return read_operation(request,'rules.manage',load)

@router.post('/organization-assessment-rules')
def create_organization_rule(data:OrgAssessmentRuleIn,request:Request):
    def apply(db,a,s):
        a.require_admin();require_open_period(db,data.period_id)
        config=validate_org_rule_config(data.target_kind,serial(data.config.model_dump()))
        version=(db.scalar(select(func.max(OrganizationAssessmentRule.version_no)).where(
            OrganizationAssessmentRule.period_id==data.period_id,OrganizationAssessmentRule.target_kind==data.target_kind)) or 0)+1
        obj=OrganizationAssessmentRule(target_kind=data.target_kind,name=data.name,version_no=version,period_id=data.period_id,config=config,
          fingerprint=digest({'target_kind':data.target_kind,'period_id':data.period_id,'config':config}),created_by=a.id,reason=data.reason)
        db.add(obj);db.flush();audit(db,a,'organization_rules',obj.id,'创建组织考核规则版本',after=serial(obj),reason=data.reason);return obj
    return command(request,data.model_dump(),'rules.manage',apply)

@router.post('/organization-assessment-rules/{ident}/copy')
def copy_organization_rule(ident:str,data:OrgRuleCopy,request:Request):
    def apply(db,a,s):
        from copy import deepcopy
        # 9.8/10.8: any holder of rules.manage (checked by command) may copy into a new draft.
        source=db.get(OrganizationAssessmentRule,ident)
        if not source:raise HTTPException(404,'组织考核规则不存在')
        check_version(source,data.expected_version);require_open_period(db,data.period_id)
        config=validate_org_rule_config(source.target_kind,serial(data.config.model_dump()) if data.config is not None else deepcopy(source.config))
        version=(db.scalar(select(func.max(OrganizationAssessmentRule.version_no)).where(
            OrganizationAssessmentRule.period_id==data.period_id,OrganizationAssessmentRule.target_kind==source.target_kind)) or 0)+1
        obj=OrganizationAssessmentRule(target_kind=source.target_kind,name=data.name,period_id=data.period_id,
            version_no=version,config=config,state='DRAFT',created_by=a.id,reason=data.reason,
            fingerprint=digest({'target_kind':source.target_kind,'period_id':data.period_id,'config':config}))
        db.add(obj);db.flush()
        audit(db,a,'organization_rules',obj.id,'复制为新的组织规则草稿',after={'source_rule_id':source.id,'source_version':source.version_no,'rule':serial(obj)},reason=data.reason)
        return {**serial(obj),'copied_from':source.id,'trial_required':True}
    return command(request,data.model_dump(),'rules.manage',apply)

@router.post('/organization-assessment-rules/{ident}/trial')
def trial_organization_rule(ident:str,data:OrgRuleTrial,request:Request):
    def apply(db,a,s):
        a.require_admin();rule=db.get(OrganizationAssessmentRule,ident)
        if not rule:raise HTTPException(404,'组织考核规则不存在')
        period=require_open_period(db,rule.period_id);items=[]
        for oid in data.target_ids:
            target=_org_target(db,a,oid,rule.target_kind)
            raw,snapshot=organization_facts(db,target,period)
            if any(c['source']=='points' for c in rule.config['components']):
                for tid in snapshot['teacher_ids']:require_current_sources(point_source_changes(db,tid,period))
            detail=evaluate_org_rule(rule,raw)
            items.append({'target_kind':rule.target_kind,'target_id':oid,'target_name':target.name,'detail':detail,
                          'total':str(rounded(sum((Decimal(x['score']) for x in detail),Decimal(0))))})
        db.add(OrganizationRuleTrial(rule_id=rule.id,fingerprint=rule.fingerprint,target_ids=list(data.target_ids),result=items,actor_id=a.id))
        audit(db,a,'organization_rules',rule.id,'组织考核样本试算',after={'targets':len(items),'fingerprint':rule.fingerprint},reason='规则样本试算，不写正式考核')
        return {'items':items,'warnings':org_rule_warnings(rule.config)}
    return command(request,data.model_dump(),'rules.manage',apply)

@router.post('/organization-assessment-rules/{ident}/actions')
def organization_rule_action(ident:str,data:Action,request:Request):
    def apply(db,a,s):
        a.require_admin();obj=db.get(OrganizationAssessmentRule,ident)
        if not obj:raise HTTPException(404,'组织考核规则不存在')
        check_version(obj,data.expected_version);require_open_period(db,obj.period_id);validate_org_rule_config(obj.target_kind,obj.config);before=serial(obj)
        if data.action=='activate':
            if not db.scalar(select(OrganizationRuleTrial.id).where(OrganizationRuleTrial.rule_id==ident,OrganizationRuleTrial.fingerprint==obj.fingerprint).limit(1)):
                raise HTTPException(409,'必须先对当前组织规则执行样本试算')
            for old in db.scalars(select(OrganizationAssessmentRule).where(OrganizationAssessmentRule.target_kind==obj.target_kind,
                    OrganizationAssessmentRule.period_id==obj.period_id,OrganizationAssessmentRule.state=='ACTIVE',OrganizationAssessmentRule.id!=ident)):
                old_before=serial(old);old.state='INACTIVE';old.version+=1
                audit(db,a,'organization_rules',old.id,'新组织规则替代旧规则',old_before,serial(old),data.reason)
            obj.state='ACTIVE'
        elif data.action=='deactivate':obj.state='INACTIVE'
        else:raise HTTPException(422,'组织规则操作无效')
        obj.version+=1;audit(db,a,'organization_rules',ident,'组织规则启停',before,serial(obj),data.reason);return {**serial(obj),'warnings':org_rule_warnings(obj.config)}
    return command(request,data.model_dump(),'rules.manage',apply)

@router.post('/organization-assessments/calculate')
def calculate_organization_assessments(data:OrgAssessmentCalculate,request:Request):
    def apply(db,a,s):
        a.require('assessment.calculate')
        if a.role.kind!='school':raise HTTPException(403,'组织考核由学校统一发起计算')
        period=require_open_period(db,data.period_id)
        rule=db.scalar(select(OrganizationAssessmentRule).where(OrganizationAssessmentRule.target_kind==data.target_kind,
            OrganizationAssessmentRule.period_id==data.period_id,OrganizationAssessmentRule.state=='ACTIVE'))
        if not rule:raise HTTPException(409,'本周期尚未启用该层级组织考核规则')
        out=[]
        for oid in data.target_ids:
            target=_org_target(db,a,oid,data.target_kind)
            obj=db.scalar(select(OrganizationAssessment).where(OrganizationAssessment.target_kind==data.target_kind,
                    OrganizationAssessment.target_id==oid,OrganizationAssessment.period_id==data.period_id).with_for_update())
            if obj and obj.state!='GENERATED':raise HTTPException(409,'已进入复核或已归档的组织考核不能被重算覆盖')
            raw,snapshot=organization_facts(db,target,period)
            if any(c['source']=='points' for c in rule.config['components']):
                for tid in snapshot['teacher_ids']:require_current_sources(point_source_changes(db,tid,period))
            detail=evaluate_org_rule(rule,raw)
            score=rounded(sum((Decimal(x['score']) for x in detail),Decimal(0)))
            before=serial(obj) if obj else {}
            if obj:
                db.query(OrganizationAssessmentMetricEvidence).filter(OrganizationAssessmentMetricEvidence.assessment_id==obj.id).delete(synchronize_session=False)
                obj.rule_id=rule.id;obj.score=score;obj.detail=detail;obj.source_snapshot=snapshot;obj.generated_by=a.id;obj.reviewed_by=None;obj.school_audited_by=None;obj.version+=1
            else:
                obj=OrganizationAssessment(target_kind=data.target_kind,target_id=oid,period_id=data.period_id,rule_id=rule.id,score=score,
                        detail=detail,source_snapshot=snapshot,generated_by=a.id)
                db.add(obj);db.flush()
            for d in detail:
                db.add(OrganizationAssessmentMetricEvidence(assessment_id=obj.id,metric_code=d['key'],metric_name=d['label'],raw_value=d['raw'],
                    data_source=d['source'],scope_snapshot={'target':snapshot['target'],'org_ids':snapshot['org_ids'],'teacher_ids':snapshot['teacher_ids']},
                    formula=d['formula'],target_value=d['target'],weight=Decimal(d['weight']),rule_version=rule.version_no,calculated_score=Decimal(d['score'])))
            workflow(db,a,'organization_assessment',obj.id,'生成组织考核',before,serial(obj),data.reason,data.basis);out.append(serial(obj))
        return {'items':out,'count':len(out),'warnings':org_rule_warnings(rule.config)}
    return command(request,data.model_dump(),'assessment.calculate',apply)

@router.get('/organization-assessments')
def list_organization_assessments(request:Request):
    f,p,z=filters_from(request,{'period_id','target_kind','target_id','state','progress'})
    def load(db,a,s):
        if a.role.kind=='teacher':raise HTTPException(403,'普通教师不访问组织考核')
        q=select(OrganizationAssessment)
        if a.role.kind!='school':q=q.where(OrganizationAssessment.target_id==a.org.id,OrganizationAssessment.target_kind==a.role.kind)
        for key in ('period_id','target_kind','target_id','state'):
            if f.get(key):q=q.where(getattr(OrganizationAssessment,key)==f[key])
        generated=db.scalars(q.where(OrganizationAssessment.state=='GENERATED').with_only_columns(OrganizationAssessment.id)).all()
        returned=org_returned_ids(db,generated)
        if f.get('progress'):q=q.where(org_progress_clause(a,f['progress'],returned))
        total=db.scalar(select(func.count()).select_from(q.order_by(None).subquery()))
        rows=db.scalars(q.order_by(OrganizationAssessment.created_at.desc(),OrganizationAssessment.id).offset((p-1)*z).limit(z)).all()
        return {'items':[{**organization_summary(db,obj),'returned':obj.id in returned} for obj in rows],'total':total,'page':p,'size':z}
    return read_operation(request,'assessment.read',load)

ORG_RETURN_ACTION='退回组织考核复核'

def org_returned_ids(db,ids):
    """A return stays pending through evidence uploads; regeneration or review handles it."""
    if not ids:return set()
    latest={}
    for oid,action in db.execute(select(WorkflowEvent.object_id,WorkflowEvent.action).where(WorkflowEvent.object_type=='organization_assessment',
            WorkflowEvent.object_id.in_(list(ids)),WorkflowEvent.action.in_(['生成组织考核',ORG_RETURN_ACTION])).order_by(WorkflowEvent.created_at,WorkflowEvent.id)):latest[oid]=action
    return {i for i,action in latest.items() if action==ORG_RETURN_ACTION}

def org_progress_clause(a,progress,returned):
    O=OrganizationAssessment
    if progress=='returned':return O.id.in_(list(returned) or [''])
    if a.role.kind=='school':
        if progress=='pending':return O.state.in_(['REVIEWED','SCHOOL_APPROVED'])|((O.target_kind=='school')&(O.state=='GENERATED'))
        if progress=='done':return O.state=='ARCHIVED'
    else:
        if progress=='pending':return O.state=='GENERATED'
        if progress=='done':return O.state.in_(['REVIEWED','SCHOOL_APPROVED','ARCHIVED'])
    raise HTTPException(422,'进度筛选只允许 pending / done / returned')

@router.get('/organization-assessments/ranking')
def organization_assessment_ranking(request:Request):
    f,p,z=filters_from(request,{'period_id','target_kind','rule_id','state'})
    return read_operation(request,'assessment.read',lambda db,a,s:_org_ranking(db,a,f,p,z))

@router.get('/organization-assessment-ranking/print')
def organization_assessment_ranking_print(request:Request):
    """10.7 printable organization ranking for the same comparable scope."""
    f,_,_=filters_from(request,{'period_id','target_kind','rule_id','state'})
    def load(db,a,s):
        a.require('assessment.read');out=_org_ranking(db,a,f,1,RANKING_PRINT_LIMIT)
        if out['total']>RANKING_PRINT_LIMIT:raise HTTPException(422,'打印范围过大，请缩小范围')
        audit(db,a,'organization_assessment','ranking','打印组织考核排名表',after={'filters':f,'rows':len(out['items'])},reason='授权打印组织考核排名')
        return {**out,'printed_at':utcnow()}
    return read_operation(request,'export',load)

def _org_ranking(db,a,f,p,z):
    if True:
        if a.role.kind=='teacher':raise HTTPException(403,'普通教师不访问组织考核排名')
        if not all(f.get(k) for k in ('period_id','target_kind','rule_id')):raise HTTPException(422,'排名须指定同一周期、组织层级和规则版本')
        if f['target_kind'] not in ORG_TARGET_KINDS:raise HTTPException(422,'组织考核对象无效')
        if a.role.kind!='school' and a.role.kind!=f['target_kind']:raise HTTPException(403,'不能跨组织层级获取排名')
        rule=db.get(OrganizationAssessmentRule,f['rule_id'])
        if not rule or rule.period_id!=f['period_id'] or rule.target_kind!=f['target_kind']:raise HTTPException(422,'规则版本与排名周期或层级不一致')
        clauses=[OrganizationAssessment.period_id==f['period_id'],OrganizationAssessment.target_kind==f['target_kind'],OrganizationAssessment.rule_id==rule.id]
        if a.role.kind!='school':clauses.append(OrganizationAssessment.target_id==a.org.id)
        if f.get('state'):
            if f['state'] not in {'GENERATED','REVIEWED','SCHOOL_APPROVED','ARCHIVED'}:raise HTTPException(422,'组织考核状态无效')
            clauses.append(OrganizationAssessment.state==f['state'])
        total=db.scalar(select(func.count()).select_from(OrganizationAssessment).where(*clauses))
        # An off-page corrupt archived score would still change every rank. Validate the
        # entire authorized cohort before the window query, not only this page.
        for archived in db.scalars(select(OrganizationAssessment).where(*clauses,OrganizationAssessment.state=='ARCHIVED').execution_options(yield_per=100)):
            verified_org_archive(archived)
        # Window rank before pagination, equal scores share competition rank: 1,1,3.
        q=select(OrganizationAssessment,func.rank().over(order_by=OrganizationAssessment.score.desc()).label('rank')).where(*clauses)
        rows=db.execute(q.order_by(OrganizationAssessment.score.desc(),OrganizationAssessment.target_id).offset((p-1)*z).limit(z)).all()
        items=[{'id':obj.id,'target_id':obj.target_id,'target_name':organization_summary(db,obj)['target_display_name'],
            'score':obj.score,'state':obj.state,'rank':rank,'rule_id':obj.rule_id} for obj,rank in rows]
        return {'items':items,'total':total,'page':p,'size':z,'scope':'school' if a.role.kind=='school' else 'own_organization_only',
            'rank_method':'competition','filters':f,'note':'仅在当前授权范围、周期、层级及规则版本内排名；同分并列，不等于跨版本排名',
            'rule_name':rule.name,'rule_version':rule.version_no}

def _organization_details(db,a,ident):
    if a.role.kind=='teacher':raise HTTPException(403,'普通教师不访问组织考核')
    obj=db.get(OrganizationAssessment,ident)
    if not obj:raise HTTPException(404,'组织考核不存在')
    if a.role.kind!='school' and (obj.target_id!=a.org.id or obj.target_kind!=a.role.kind):raise HTTPException(403,'组织考核超出授权范围')
    if obj.state=='ARCHIVED':
        frozen=verified_org_archive(obj)
        return {'assessment':{**frozen['assessment'],'archive':frozen,'archive_sha256':obj.archive_sha256},
            'rule':frozen.get('rule',{}),'target':frozen.get('target') or frozen['assessment']['source_snapshot']['target'],
            'period':frozen.get('period') or frozen['assessment']['source_snapshot']['period'],
            'evidence':frozen['evidence'],'events':frozen.get('events',[]),'immutable':True,'returned':False,
            'events_frozen':frozen.get('schema_version')==2,
            'history_note':'' if frozen.get('schema_version')==2 else '旧归档未冻结办理轨迹，不以当前日志补写历史。'}
    return {'assessment':obj,'rule':db.get(OrganizationAssessmentRule,obj.rule_id),'target':db.get(Org,obj.target_id),
        'period':db.get(Period,obj.period_id),'evidence':db.scalars(select(OrganizationAssessmentMetricEvidence).where(
            OrganizationAssessmentMetricEvidence.assessment_id==ident).order_by(OrganizationAssessmentMetricEvidence.metric_code)).all(),
        'events':events(db,'organization_assessment',ident),'immutable':False,'returned':obj.state=='GENERATED' and ident in org_returned_ids(db,[ident]),'source_changes':organization_source_changes(db,obj)}

@router.get('/organization-assessments/{ident}')
def organization_assessment_detail(ident:str,request:Request):
    return read_operation(request,'assessment.read',lambda db,a,s:_organization_details(db,a,ident))

@router.get('/organization-assessments/{ident}/print')
def organization_assessment_print(ident:str,request:Request):
    def load(db,a,s):
        a.require('assessment.read');result=_organization_details(db,a,ident)
        audit(db,a,'organization_assessment',ident,'打印组织考核结果',after={'immutable':result['immutable']},reason='授权打印组织考核；未归档结果标记为过程稿')
        return {**result,'document_status':'ARCHIVED' if result['immutable'] else 'DRAFT_NOT_FINAL'}
    return read_operation(request,'export',load)

@router.post('/organization-assessments/{ident}/actions')
def organization_assessment_action(ident:str,data:Action,request:Request):
    def apply(db,a,s):
        obj=db.get(OrganizationAssessment,ident)
        if not obj:raise HTTPException(404,'组织考核不存在')
        check_version(obj,data.expected_version);require_open_period(db,obj.period_id);before=serial(obj)
        if data.action=='review':
            a.require('assessment.review');_org_target(db,a,obj.target_id,obj.target_kind,for_review=True)
            if obj.state!='GENERATED':raise HTTPException(409,'组织考核当前不能复核')
            if obj.generated_by==a.id:raise HTTPException(403,'生成者不能复核同一组织考核')
            obj.state='REVIEWED';obj.reviewed_by=a.id
        elif data.action=='school_audit':
            a.require('assessment.archive')
            if a.role.kind!='school' or obj.state!='REVIEWED':raise HTTPException(403,'仅学校可审核已复核组织考核')
            if obj.reviewed_by==a.id:raise HTTPException(403,'组织复核人与学校审核人必须分离')
            obj.state='SCHOOL_APPROVED';obj.school_audited_by=a.id
        elif data.action=='return':
            if a.role.kind!='school' or 'assessment.archive' not in a.permissions:raise HTTPException(403,'仅学校可退回组织考核')
            if obj.state not in {'REVIEWED','SCHOOL_APPROVED'}:raise HTTPException(409,'当前组织考核不能退回')
            obj.state='GENERATED';obj.reviewed_by=None;obj.school_audited_by=None
        elif data.action=='archive':
            a.require('assessment.archive')
            if a.role.kind!='school' or obj.state!='SCHOOL_APPROVED':raise HTTPException(403,'仅学校可归档已审核组织考核')
            require_current_sources(organization_source_changes(db,obj))
            payload,sha=archive_payload(db,obj,actor=a,reason=data.reason,basis=data.basis);obj.state='ARCHIVED';obj.archive=payload;obj.archive_sha256=sha
        else:raise HTTPException(422,'组织考核操作无效')
        if data.action in {'review','school_audit'}:require_current_sources(organization_source_changes(db,obj))
        obj.version+=1
        workflow(db,a,'organization_assessment',ident,{'review':'组织考核复核','school_audit':'学校审核组织考核','return':'退回组织考核复核','archive':'组织考核归档'}[data.action],before,serial(obj),data.reason,data.basis)
        return obj
    return command(request,data.model_dump(),'assessment.read',apply)
