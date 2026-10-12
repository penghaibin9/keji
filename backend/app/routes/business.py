"""R2 real training/qualification/dispute/portal routes using recovered models."""
from datetime import timedelta
from fastapi import APIRouter,Request,HTTPException
from sqlalchemy import select,func
from ..core import *
from ..schemas import *
from ..services import insert_record,qualification_revision
from ..read_queries import record_query,stats,assessment_query,RECORD_FILTERS,STAT_FILTERS,authorized_org_descendants
from ..settings_catalog import business_dictionary
from ..org_assessment import OrganizationAssessment
from ..reference_data import ensure_reference_from_training_record
router=APIRouter(prefix='/api',tags=['教师业务'])

def owned_object(db,a,model,ident,permission,*,own=False):
    a.require(permission);obj=db.get(model,ident)
    if obj is None:raise HTTPException(404,'业务记录不存在')
    a.check_teacher(db,obj.teacher_id)
    if own and obj.teacher_id!=a.id:raise HTTPException(403,'此操作必须由本人办理')
    return obj

def events(db,kind,ident):
    return db.scalars(select(WorkflowEvent).where(WorkflowEvent.object_type==kind,WorkflowEvent.object_id==ident).order_by(WorkflowEvent.created_at,WorkflowEvent.id)).all()

def safe_attachments(db,obj):
    items=[]
    for ident in obj.attachment_ids or []:
        item=db.get(Attachment,ident)
        if not item or item.object_type!='qualification' or item.object_id!=obj.id or item.teacher_id!=obj.teacher_id:
            raise HTTPException(503,'资质材料关联异常，请联系管理员')
        values=serial(item);values.pop('storage_key',None);items.append(values)
    return items

@router.get('/statistics')
def statistics(request:Request):
    f,_,_=filters_from(request,STAT_FILTERS)
    return read_operation(request,'portal.read',lambda db,a,s:stats(db,a,f))

@router.get('/statistics/comparison')
def statistics_comparison(request:Request):
    """7.4/7.5 period-over-period KPIs from the same stats() source."""
    f,_,_=filters_from(request,STAT_FILTERS)
    from ..read_queries import comparison
    return read_operation(request,'portal.read',lambda db,a,s:comparison(db,a,f))

@router.get('/records')
def records(request:Request):
    f,p,z=filters_from(request,RECORD_FILTERS)
    return read_operation(request,'records.read',lambda db,a,s:page_result(db,record_query(db,a,f).order_by(TrainingRecord.event_date.desc(),TrainingRecord.id),p,z))

@router.get('/records/{ident}')
def record_detail(ident:str,request:Request):
    def load(db,a,s):
        obj=owned_object(db,a,TrainingRecord,ident,'records.read')
        return {'record':obj,'history':db.scalars(select(RecordRevision).where(RecordRevision.record_id==ident).order_by(RecordRevision.version)).all()}
    return read_operation(request,'records.read',load)

@router.post('/records')
def record_create(data:RecordIn,request:Request):
    def apply(db,a,s):
        obj=insert_record(db,a,data)
        ensure_reference_from_training_record(db,obj)
        if data.basis:workflow(db,a,'record',obj.id,'业务录入依据',{},serial(obj),data.reason,data.basis)
        return obj
    return command(request,data.model_dump(),'records.write',apply)

@router.put('/records/{ident}')
def record_update(ident:str,data:RecordUpdate,request:Request):
    def apply(db,a,s):
        obj=owned_object(db,a,TrainingRecord,ident,'records.write');check_version(obj,data.expected_version)
        if obj.external_key!=data.external_key or obj.teacher_id!=data.teacher_id:raise HTTPException(422,'来源编号和教师归属不可直接更换')
        if data.source!=obj.source:raise HTTPException(422,'原始数据来源不可直接更换；更正内容与依据将另外留痕')
        before=serial(obj)
        for k,v in data.model_dump(exclude={'reason','basis','expected_version'}).items():setattr(obj,k,v)
        obj.version+=1;db.flush();ensure_reference_from_training_record(db,obj)
        db.add(RecordRevision(record_id=obj.id,version=obj.version,data=serial(obj),reason=data.reason,actor_id=a.id))
        workflow(db,a,'record',obj.id,'更正培训业务',before,serial(obj),data.reason,data.basis);return obj
    return command(request,data.model_dump(),'records.write',apply)

@router.get('/qualifications')
def qualifications(request:Request):
    f,p,z=filters_from(request,{'q','state','teacher_id','org_id'})
    def load(db,a,s):
        q=select(Qualification).where(a.scope(Qualification.teacher_id))
        if f.get('teacher_id'):q=q.where(Qualification.teacher_id==f['teacher_id'])
        if f.get('org_id'):q=q.where(Qualification.teacher_id.in_(select(User.id).where(User.org_id.in_(authorized_org_descendants(db,a,f['org_id'])))))
        if f.get('state'):
            if f['state'] not in {'DRAFT','SUBMITTED','RETURNED','APPROVED'}:raise HTTPException(422,'资质状态无效')
            q=q.where(Qualification.state==f['state'])
        if f.get('q'):q=q.where(Qualification.name.contains(f['q'],autoescape=True)|Qualification.certificate_no.contains(f['q'],autoescape=True))
        return page_result(db,q.order_by(Qualification.created_at.desc(),Qualification.id),p,z)
    return read_operation(request,'qualification.read',load)

@router.get('/qualification-summary')
def qualification_summary(request:Request):
    """5.2 status distribution: 待审/退回/即将到期/有效/已过期/草稿 within the live scope."""
    f,_,_=filters_from(request,{'teacher_id'})
    def load(db,a,s):
        q=select(Qualification.state,Qualification.expires).where(a.scope(Qualification.teacher_id))
        if f.get('teacher_id'):q=q.where(Qualification.teacher_id==f['teacher_id'])
        setting=db.get(Setting,'qualification');days=int((setting.value or {}).get('expiry_days',0)) if setting else 0
        today=school_today();limit=today+timedelta(days=days)
        counts={'SUBMITTED':0,'RETURNED':0,'EXPIRING':0,'VALID':0,'EXPIRED':0,'DRAFT':0}
        for state,expires in db.execute(q):
            if state=='APPROVED':counts['EXPIRED' if expires and expires<today else 'EXPIRING' if expires and expires<=limit else 'VALID']+=1
            elif state in counts:counts[state]+=1
        labels={'SUBMITTED':'待审核','RETURNED':'已退回','EXPIRING':'即将到期','VALID':'有效','EXPIRED':'已过期','DRAFT':'草稿'}
        return {'items':[{'key':k,'label':labels[k],'count':v} for k,v in counts.items()],'total':sum(counts.values()),
                'expiry_days':days,'note':f'即将到期 = 审核通过且 {days} 天内到期；无有效期视为长期有效。'}
    return read_operation(request,'qualification.read',load)

@router.get('/qualifications/{ident}')
def qualification_detail(ident:str,request:Request):
    def load(db,a,s):
        obj=owned_object(db,a,Qualification,ident,'qualification.read')
        return {'qualification':obj,'attachments':safe_attachments(db,obj),
          'revisions':db.scalars(select(QualificationRevision).where(QualificationRevision.qualification_id==ident).order_by(QualificationRevision.version)).all(),
          'events':events(db,'qualification',ident)}
    return read_operation(request,'qualification.read',load)

@router.post('/qualifications')
def qualification_create(data:QualificationIn,request:Request):
    def apply(db,a,s):
        if data.teacher_id!=a.id:raise HTTPException(403,'只能维护本人资质')
        a.check_teacher(db,data.teacher_id,active=True)
        settings=db.get(Setting,'qualification')
        if not settings or data.category not in settings.value.get('categories',[]):raise HTTPException(422,'请选择有效资质类别')
        obj=Qualification(**data.model_dump(exclude={'reason','basis'}));db.add(obj)
        qualification_revision(db,a,obj,data.reason)
        workflow(db,a,'qualification',obj.id,'新建资质',{},serial(obj),data.reason,data.basis);return obj
    return command(request,data.model_dump(),'qualification.write',apply)

@router.put('/qualifications/{ident}')
def qualification_update(ident:str,data:QualificationUpdate,request:Request):
    def apply(db,a,s):
        obj=owned_object(db,a,Qualification,ident,'qualification.write',own=True);check_version(obj,data.expected_version)
        if data.teacher_id!=a.id or obj.state=='SUBMITTED':raise HTTPException(409,'审核中材料不可修改，请先撤回')
        settings=db.get(Setting,'qualification')
        if not settings or data.category not in settings.value.get('categories',[]):raise HTTPException(422,'资质类别无效')
        before=serial(obj)
        for k,v in data.model_dump(exclude={'reason','basis','expected_version'}).items():setattr(obj,k,v)
        obj.state='DRAFT';obj.version+=1
        qualification_revision(db,a,obj,data.reason)
        workflow(db,a,'qualification',obj.id,'修订资质',before,serial(obj),data.reason,data.basis);return obj
    return command(request,data.model_dump(),'qualification.write',apply)

@router.post('/qualifications/{ident}/actions')
def qualification_action(ident:str,data:Action,request:Request):
    permission='qualification.write' if data.action in {'submit','withdraw'} else 'qualification.review'
    def apply(db,a,s):
        obj=owned_object(db,a,Qualification,ident,permission);check_version(obj,data.expected_version)
        own=obj.teacher_id==a.id;before=serial(obj)
        if data.action=='submit':
            if not own:raise HTTPException(403,'资质必须由本人提交')
            if obj.state not in {'DRAFT','RETURNED'}:raise HTTPException(409,'当前资质不能提交')
            if not safe_attachments(db,obj):raise HTTPException(409,'请先上传真实佐证文件')
            # Recheck the actual stored evidence before review, not merely IDs.
            from .files import verify_file
            for attachment in safe_attachments(db,obj):verify_file(request.app.state.settings.storage_dir,db.get(Attachment,attachment['id']))
            obj.state='SUBMITTED'
        elif data.action=='withdraw':
            if not own:raise HTTPException(403,'资质必须由本人撤回')
            if obj.state!='SUBMITTED':raise HTTPException(409,'当前资质不能撤回')
            obj.state='DRAFT'
        elif data.action in {'approve','return'}:
            if own or a.role.kind=='teacher':raise HTTPException(403,'不能审核本人资质')
            if obj.state!='SUBMITTED':raise HTTPException(409,'资质不在待审核环节')
            obj.state='APPROVED' if data.action=='approve' else 'RETURNED'
            if data.action=='return':
                from ..message_push import queue
                queue(db,[obj.teacher_id],'你的资质申报被退回','请登录非学历教育智慧前台，在“个人培训”查看退回原因并补正后重新提交。')
        else:raise HTTPException(422,'资质操作无效')
        obj.version+=1;qualification_revision(db,a,obj,data.reason)
        workflow(db,a,'qualification',obj.id,{'submit':'提交资质','withdraw':'撤回资质','approve':'资质审核通过','return':'资质退回补充'}[data.action],before,serial(obj),data.reason,data.basis)
        return obj
    return command(request,data.model_dump(),permission,apply)

@router.get('/disputes')
def disputes(request:Request):
    f,p,z=filters_from(request,{'state','period_id','teacher_id'})
    def load(db,a,s):
        q=select(Dispute).where(a.scope(Dispute.teacher_id))
        for k in ('state','period_id','teacher_id'):
            if f.get(k):q=q.where(getattr(Dispute,k)==f[k])
        return page_result(db,q.order_by(Dispute.created_at.desc(),Dispute.id),p,z)
    return read_operation(request,'dispute.write',load)

@router.post('/disputes')
def dispute_create(data:DisputeIn,request:Request):
    def apply(db,a,s):
        model,permission={'record':(TrainingRecord,'records.read'),'points':(PointEntry,'points.read'),'assessment':(Assessment,'assessment.read')}[data.object_type]
        source=owned_object(db,a,model,data.object_id,permission,own=True)
        if db.scalar(select(Dispute.id).where(Dispute.teacher_id==a.id,Dispute.object_type==data.object_type,Dispute.object_id==source.id,Dispute.state=='OPEN').limit(1)):
            raise HTTPException(409,'此业务已有未解决核对申请')
        obj=Dispute(teacher_id=a.id,object_type=data.object_type,object_id=source.id,period_id=getattr(source,'period_id',None),reason=data.reason)
        db.add(obj);db.flush();workflow(db,a,'dispute',obj.id,'提出核对申请',{},serial(obj),data.reason,data.basis);return obj
    return command(request,data.model_dump(),'dispute.write',apply)

@router.get('/disputes/{ident}')
def dispute_detail(ident:str,request:Request):
    def load(db,a,s):
        obj=owned_object(db,a,Dispute,ident,'dispute.write')
        at=db.scalars(select(Attachment).where(Attachment.object_type=='dispute',Attachment.object_id==ident,Attachment.teacher_id==obj.teacher_id)).all()
        return {'dispute':obj,'attachments':[{k:v for k,v in serial(x).items() if k!='storage_key'} for x in at],'events':events(db,'dispute',ident)}
    return read_operation(request,'dispute.write',load)

@router.post('/disputes/{ident}/resolve')
def dispute_resolve(ident:str,data:ResolveDispute,request:Request):
    def apply(db,a,s):
        obj=owned_object(db,a,Dispute,ident,'dispute.resolve');check_version(obj,data.expected_version)
        if obj.teacher_id==a.id:raise HTTPException(403,'申请人与复核人必须分离')
        if obj.state!='OPEN':raise HTTPException(409,'核对申请已经处理')
        before=serial(obj);obj.state='RESOLVED';obj.resolution=data.resolution;obj.resolved_by=a.id;obj.version+=1
        workflow(db,a,'dispute',obj.id,'完成核对复核',before,serial(obj),data.reason,data.basis);return obj
    return command(request,data.model_dump(),'dispute.resolve',apply)

def _todo_items(db,a):
    out=[]
    def add(kind,x,title,state=None,**extra):out.append({'type':kind,'id':x.id,'title':title,'teacher_id':getattr(x,'teacher_id',None),'state':state or x.state,**extra})
    if 'qualification.read' in a.permissions:
        for q in db.scalars(select(Qualification).where(a.scope(Qualification.teacher_id))):
            if q.teacher_id==a.id and q.state in {'DRAFT','RETURNED'}:add('qualification',q,'补充并提交资质：'+q.name)
            elif q.teacher_id!=a.id and 'qualification.review' in a.permissions and q.state=='SUBMITTED':add('qualification',q,'待审核资质：'+q.name)
            elif q.state=='APPROVED' and q.expires:
                setting=db.get(Setting,'qualification')
                days=setting.value['expiry_days'] if setting else 0
                if q.expires<=school_today()+timedelta(days=days):
                    add('qualification',q,'资质有效期核对：'+q.name,'EXPIRING',
                        expires=q.expires,days_remaining=(q.expires-school_today()).days)
    if 'assessment.read' in a.permissions:
        stage={'dept':'DEPARTMENT','college':'COLLEGE','school':'SCHOOL'}.get(a.role.kind)
        for x in db.scalars(select(Assessment).where(a.scope(Assessment.teacher_id))):
            if x.teacher_id==a.id and x.state=='TEACHER' and 'assessment.confirm' in a.permissions:add('assessment',x,'本人考核确认')
            elif x.teacher_id!=a.id and x.state==stage and 'assessment.review' in a.permissions:add('assessment',x,'本级考核确认')
            elif x.state=='READY' and 'assessment.archive' in a.permissions and x.teacher_id!=a.id:add('assessment',x,'考核归档')
    if a.role.kind!='teacher' and 'assessment.read' in a.permissions:
        if a.role.kind in {'dept','college'} and 'assessment.review' in a.permissions:
            for x in db.scalars(select(OrganizationAssessment).where(OrganizationAssessment.target_kind==a.role.kind,
                    OrganizationAssessment.target_id==a.org.id,OrganizationAssessment.state=='GENERATED')):
                if x.generated_by!=a.id:
                    target=db.get(Org,x.target_id);add('organization_assessment',x,'组织考核复核：'+(target.name if target else x.target_id),target_id=x.target_id)
        elif a.role.kind=='school':
            if 'assessment.review' in a.permissions:
                for x in db.scalars(select(OrganizationAssessment).where(OrganizationAssessment.target_kind=='school',
                        OrganizationAssessment.target_id==a.org.id,OrganizationAssessment.state=='GENERATED')):
                    if x.generated_by!=a.id:
                        add('organization_assessment',x,'学校自身考核复核',target_id=x.target_id)
            if 'assessment.archive' in a.permissions:
                for x in db.scalars(select(OrganizationAssessment).where(OrganizationAssessment.state.in_(['REVIEWED','SCHOOL_APPROVED'])).order_by(OrganizationAssessment.created_at)):
                    target=db.get(Org,x.target_id);name=target.name if target else x.target_id
                    if x.state=='REVIEWED' and x.reviewed_by!=a.id:add('organization_assessment',x,'学校审核组织考核：'+name,target_id=x.target_id)
                    elif x.state=='SCHOOL_APPROVED':add('organization_assessment',x,'归档组织考核：'+name,target_id=x.target_id)
    if a.role.kind in {'dept','college'} and 'assessment.review' in a.permissions:
        from types import SimpleNamespace
        from ..reference_data import pending_credit_reviews
        groups=pending_credit_reviews(db,a)
        names=dict(db.execute(select(User.id,User.name).where(User.id.in_(sorted({g['user_id'] for g in groups if g['user_id']})))).all()) if groups else {}
        for g in groups:
            add('credit_review',SimpleNamespace(id=g['staff_no']+'~'+g['school_year'],teacher_id=g['user_id']),
                '授课认定：'+(names.get(g['user_id']) or g['teacher_name'] or g['staff_no'])+' '+g['school_year']+' 学年 '+str(g['pending_courses'])+' 门课待认定','待认定')
    if 'dispute.write' in a.permissions:
        for x in db.scalars(select(Dispute).where(a.scope(Dispute.teacher_id),Dispute.state=='OPEN')):
            if x.teacher_id==a.id or 'dispute.resolve' in a.permissions:add('dispute',x,('我提出的异议：' if x.teacher_id==a.id else '数据核对：')+x.reason[:40])
    if 'audit.read' in a.permissions and a.role.kind=='school' and a.user.is_admin:
        from ..security_alerts import security_summary
        summary=security_summary(db,a)
        if summary['alert']:
            from types import SimpleNamespace
            add('security',SimpleNamespace(id='security-alerts'),'安全提示：'+'；'.join(summary['flags']),'OPEN')
    if 'sync.manage' in a.permissions:
        for x in db.scalars(select(Task).where(Task.kind.in_(['sync','inbound_pull']),Task.state.in_(['FAILED','BLOCKED'])).order_by(Task.created_at.desc(),Task.id)):
            add('sync',x,'数据中台拉取异常' if x.kind=='inbound_pull' else '接口同步异常',task_kind=x.kind)
    from ..social_training import todo_items
    out.extend(todo_items(db,a))
    return out

@router.get('/todos')
def todos(request:Request):
    f,p,z=filters_from(request,{'q','type','stage'})
    from ..read_queries import clean_filters
    f=clean_filters(f,{'q','type','stage'})
    if f.get('type') and f['type'] not in {'qualification','assessment','organization_assessment','dispute','sync','security','social_project','social_claim','social_annual','social_resource','social_report','credit_review'}:
        raise HTTPException(422,'待办类型无效')
    # 待归档清单只是只读筛选：积分认定、更正待教学秘书归档，教师考核待学校归档；办理仍走原单条接口。
    if f.get('stage') and f['stage']!='archive':raise HTTPException(422,'待办环节无效')
    def load(db,a,s):
        items=_todo_items(db,a)
        counts={}
        for x in items:counts[x['type']]=counts.get(x['type'],0)+1
        if f.get('type'):items=[x for x in items if x['type']==f['type']]
        if f.get('stage')=='archive':items=[x for x in items if (x['type'] in {'social_claim','social_resource'} and x['state']=='待教学秘书归档') or (x['type']=='assessment' and x['state']=='READY')]
        if f.get('q'):items=[x for x in items if f['q'].casefold() in x['title'].casefold()]
        total=len(items)
        return {'items':items[(p-1)*z:p*z],'total':total,'page':p,'size':z,'counts':counts}
    return read_operation(request,'portal.read',load)

@router.get('/portal/workbench')
def portal_workbench(request:Request):
    """Task-first home summary. Reuse live permissions; never infer deadlines."""
    def load(db,a,s):
        items=[x for x in _todo_items(db,a)
               if not x.get('target_id') or x['target_id'] in a.org_ids]
        names=dict(db.execute(select(User.id,User.name).where(a.scope(User.id))).all())
        for item in items:
            if item.get('teacher_id'):
                item['owner_name']=names.get(item['teacher_id'],'授权教师')
            elif item.get('target_id'):
                target=db.get(Org,item['target_id'])
                item['owner_name']=target.name if target else '授权组织'
            else:
                item['owner_name']='安全审计' if item['type']=='security' else '学校系统对接'
        reminders=sorted((x for x in items if x['state']=='EXPIRING'),
                         key=lambda x:(x['expires'],x['id']))
        tasks=sorted((x for x in items if x['state']!='EXPIRING'),
                     key=lambda x:(0 if x['state']=='RETURNED' else 1 if x['type']=='dispute' else 2,x['type'],x['id']))
        return {'scope_label':'仅本人' if a.role.kind=='teacher' else a.org.name,
                'as_of':school_today(),
                'tasks':{'total':len(tasks),'items':tasks[:6],
                         'returned':sum(x['state']=='RETURNED' for x in tasks)},
                'reminders':{'total':len(reminders),'items':reminders[:4],
                             'expired':sum(x['days_remaining']<0 for x in reminders)},
                'scope_note':'待办理与资质提醒包含全部周期，不受下方统计筛选影响。'}
    return read_operation(request,'portal.read',load)


@router.get('/portal/search')
def portal_search(request:Request):
    """Search only business types and rows the live actor can read."""
    from ..read_queries import clean_filters
    from .admin import notice_scope
    f,_,_=filters_from(request,{'q'})
    word=clean_filters(f,{'q'}).get('q','').strip()
    if not word:raise HTTPException(422,'请输入搜索关键词')
    def load(db,a,s):
        groups=[]
        def collect(kind,title,stmt,project):
            rows=db.scalars(stmt.limit(11)).all()
            groups.append({'type':kind,'title':title,'has_more':len(rows)>10,'items':[project(x) for x in rows[:10]]})
        if 'records.read' in a.permissions:
            collect('record','培训数据',record_query(db,a,{'q':word}).order_by(TrainingRecord.event_date.desc(),TrainingRecord.id),
                    lambda x:{'id':x.id,'title':x.project+' · '+x.course,'description':str(x.event_date)+' · '+x.external_key})
        if 'qualification.read' in a.permissions:
            stmt=select(Qualification).where(a.scope(Qualification.teacher_id),Qualification.name.contains(word,autoescape=True)|Qualification.certificate_no.contains(word,autoescape=True)).order_by(Qualification.created_at.desc(),Qualification.id)
            collect('qualification','教师资质',stmt,lambda x:{'id':x.id,'title':x.name,'description':x.category,'state':x.state})
        if 'notice.read' in a.permissions:
            stmt=select(Notice).where(Notice.org_id.in_(notice_scope(db,a)),Notice.published.is_(True),Notice.title.contains(word,autoescape=True)|Notice.body.contains(word,autoescape=True)).order_by(Notice.created_at.desc(),Notice.id)
            collect('notice','政策通知',stmt,lambda x:{'id':x.id,'title':x.title,'description':x.category})
        return {'groups':groups}
    return read_operation(request,'portal.read',load)

@router.get('/organization-workbench')
def organization_workbench(request:Request):
    f,_,_=filters_from(request,STAT_FILTERS)
    def load(db,a,s):
        if a.role.kind not in {'dept','college','school'}:
            raise HTTPException(403,'仅教研室、学院或学校管理角色访问分级管理工作台')
        target_id=f.get('org_id') or a.org.id
        org_ids=authorized_org_descendants(db,a,target_id)
        target=db.get(Org,target_id)
        if not target:raise HTTPException(404,'组织不存在')
        scoped={**f,'org_id':target_id}
        summary=stats(db,a,scoped)
        teacher_ids=set(db.scalars(select(User.id).where(User.org_id.in_(org_ids),User.staff_no.is_not(None),User.authorization_pending.is_(False))))
        # The unified source already applies action permissions and separation of duties.
        # Keep organization-owned assessment tasks inside this exact authorized subtree;
        # do not admit every non-teacher object just because teacher_id is absent.
        items=[]
        for x in _todo_items(db,a):
            if x.get('teacher_id') in teacher_ids:
                items.append(x)
            elif x.get('type')=='organization_assessment' and x.get('target_id') in org_ids:
                items.append(x)
            elif target.kind=='school' and a.role.kind=='school' and x.get('type')=='sync':
                items.append(x)
        return {'organization':target,'statistics':summary,'todos':{'items':items,'total':len(items)},
                'assessment_states':summary.get('assessment_states',{}),
                'scope':{'org_id':target_id,'org_ids':org_ids,'teacher_count':len(teacher_ids)}}
    return read_operation(request,'organization.read',load)
