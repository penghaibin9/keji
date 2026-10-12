"""Social training within the existing authenticated portal and transaction boundary."""
from decimal import Decimal as D
from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select, func, or_
from ..core import command, read_operation, serial, audit, workflow, check_version, require_open_period, digest
from ..models import Org, User, Role, Setting, Period, PointEntry, Notice, WorkflowEvent
from ..reference_data import TrainingProjectMaster, TrainingCourseMaster, TrainingClassMaster
from ..social_models import SocialProject, SocialUnit, SocialPolicy, SocialClaim, SocialAnnual, SocialResource
from ..social_schemas import ProjectIn, UnitsIn, SocialAction, PolicyIn, RecommendedPolicyIn, PolicyData, ClaimIn, AnnualIn, ResourceIn, ResourceUpdate, DutiesIn, CourseIn, CourseBatchIn, CaseNoteIn, CorrectionIn, ReportIn, PointReviewIn
from .. import social_training as st

router=APIRouter(prefix='/api/social',tags=['社会培训项目与制度'])


def college(db,a,ident):
    org=db.get(Org,ident)
    if not org or not org.active or org.kind!='college' or ident not in a.org_ids:raise HTTPException(403,'学院超出授权范围')
    return org


def project_owner(db,ident,org_id):
    user=db.get(User,ident)
    org=db.get(Org,user.org_id) if user else None
    if not user or not user.active or not org or (org.id!=org_id and org.parent_id!=org_id):raise HTTPException(422,'项目负责人须为承办学院的有效人员')


def event(db,a,kind,obj,action,before,reason,basis=''):
    obj.version+=1;db.flush();workflow(db,a,kind,obj.id,action,before,serial(obj),reason,basis)
    return st.detail(db,a,kind,obj)


def visible_projects(db,a):
    return st.visible_projects(db,a)


@router.get('/project-options')
def project_options(request:Request,q:str=Query('',max_length=100),page:int=Query(1,ge=1),size:int=Query(25,ge=1,le=100),mine:bool=Query(False)):
    def load(db,a,s):
        query=visible_projects(db,a)
        if mine:query=query.where(SocialProject.id.in_(st.participated_project_ids(db,a.id) or {''}),SocialProject.state=='CLOSED')
        if q:query=query.where(or_(*[column.contains(q,autoescape=True) for column in (SocialProject.data['name'].as_string(),SocialProject.data['code'].as_string(),SocialProject.cohort)]))
        total=db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
        projects=db.scalars(query.offset((page-1)*size).limit(size)).all()
        return {'items':[{'id':p.id,'code':p.data['code'],'name':p.data['name'],'cohort':p.cohort,'org_id':p.org_id,'state':p.state,'state_label':st.state_label(p)} for p in projects],'page':page,'size':size,'total':total,'q':q}
    return read_operation(request,'records.read',load)


@router.get('/workspace')
def workspace(request:Request,section:str=Query('projects',pattern='^(projects|courses|bases|outcomes|recognition|annual|policy)$'),page:int=Query(1,ge=1),q:str=Query('',max_length=100),resource_page:int=Query(1,ge=1)):
    def load(db,a,s):
        totals={};size=200
        def listing(query,key,search):
            if key==section and q:query=query.where(or_(*[column.contains(q,autoescape=True) for column in search]))
            totals[key]=db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
            offset=(page-1)*size if key==section else (resource_page-1)*size if key=='resources' else 0
            return db.scalars(query.offset(offset).limit(size)).all()
        projects=listing(visible_projects(db,a),'projects',[SocialProject.data['name'].as_string(),SocialProject.data['code'].as_string(),SocialProject.cohort])
        claim_query=select(SocialClaim).join(User,User.id==SocialClaim.teacher_id).join(SocialProject,SocialProject.id==SocialClaim.project_id).where(a.scope(SocialClaim.teacher_id)).order_by(SocialClaim.created_at.desc(),SocialClaim.id)
        claims=listing(claim_query,'recognition',[SocialClaim.state,User.name,SocialProject.data['name'].as_string()]) if 'points.read' in a.permissions else []
        annual_scope=(SocialAnnual.org_id==a.org.parent_id)&SocialAnnual.state.in_(['PUBLIC','ARCHIVED']) if a.role.kind=='teacher' else SocialAnnual.org_id.in_(a.org_ids)
        annuals=listing(select(SocialAnnual).where(annual_scope).order_by(SocialAnnual.created_at.desc(),SocialAnnual.id),'annual',[SocialAnnual.state]) if 'assessment.read' in a.permissions else []
        resource_scope=[a.org.parent_id] if a.role.kind in ('teacher','dept') else a.org_ids
        resource_query=select(SocialResource).where(SocialResource.org_id.in_(resource_scope),SocialResource.kind!='ledger')
        if a.role.kind in ('teacher','dept'):
            mine=SocialResource.kind.in_(['correction','point_review'])&SocialResource.data['teacher_id'].as_string().in_([a.id] if a.role.kind=='teacher' else (list(a.teacher_ids) or ['']))
            resource_query=select(SocialResource).where((SocialResource.org_id.in_(resource_scope)&SocialResource.kind.notin_(['ledger','correction','point_review']))|mine)
            if a.role.kind=='dept':resource_query=resource_query.where(SocialResource.kind.in_(st.DEPT_READABLE_RESOURCES|{'correction','point_review'}))
            if a.role.kind=='teacher':resource_query=resource_query.where((SocialResource.kind!='point_review')|(SocialResource.state!='DRAFT'))
        if a.role.kind=='teacher':resource_query=resource_query.where((SocialResource.kind!='point_report')|SocialResource.state.in_(['PUBLIC','ARCHIVED']))
        if 'points.read' not in a.permissions:resource_query=resource_query.where(SocialResource.kind.notin_(['correction','point_report','point_review']))
        if a.role.kind=='teacher' and 'points.read' in a.permissions:
            parent=db.get(Org,a.org.parent_id)
            if parent:
                visible=resource_query.with_only_columns(SocialResource.id)
                school_reports=(SocialResource.org_id==parent.parent_id)&(SocialResource.kind=='point_report')&SocialResource.state.in_(['PUBLIC','ARCHIVED'])
                resource_query=select(SocialResource).where(or_(SocialResource.id.in_(visible),school_reports))
        resource_query=resource_query.where(or_(SocialResource.kind!='course_resource',st.course_resource_scope(db,a)))
        if section in {'bases','outcomes'}:resource_query=resource_query.where(SocialResource.kind==('base' if section=='bases' else 'achievement'))
        elif section=='recognition':resource_query=resource_query.where(SocialResource.kind.in_(['correction','point_report','point_review']))
        elif section=='courses':resource_query=resource_query.where(SocialResource.kind=='course_resource')
        resources=listing(resource_query.order_by(SocialResource.code),section if section in {'bases','outcomes'} else 'resources',[SocialResource.code,SocialResource.name])
        policies=listing(select(SocialPolicy).order_by(SocialPolicy.created_at.desc(),SocialPolicy.id),'policy',[SocialPolicy.name])
        course_query=st.visible_courses(db,a)
        courses=listing(course_query.order_by(TrainingCourseMaster.code),'courses',[TrainingCourseMaster.name,TrainingCourseMaster.code,TrainingCourseMaster.project_code])
        course_stats={}
        for r in db.scalars(select(SocialResource).where(st.course_resource_scope(db,a),SocialResource.kind=='course_resource')):
            stats=course_stats.setdefault(r.data['course_code'],{'resources':0,'videos':0,'minutes':st.D(0)});stats['resources']+=1
            if r.data['resource_type']=='video':stats['videos']+=st.resource_video_count(r.data);stats['minutes']+=st.D(r.data['duration_minutes'])
        resource_orgs=dict(db.execute(select(Org.id,Org.name).where(Org.id.in_({r.org_id for r in resources}|{r.org_id for r in annuals}))).all()) if resources or annuals else {}
        display=lambda rows:[{**serial(row),'state_label':st.state_label(row)} for row in rows]
        project_items=[{**st.project_read_item(a,p),'state_label':st.state_label(p)} for p in projects]
        claim_items=[st.claim_read_item(db,a,c) for c in claims]
        return {'projects':project_items,'claims':claim_items,'annuals':[{**st.annual_read_item(a,row),'org_name':resource_orgs.get(row.org_id,'—')} for row in annuals],'resources':[{**row,'org_name':resource_orgs[row['org_id']]} for row in display(resources)],
                'policies':display(policies),'courses':serial(courses),'course_stats':serial(course_stats),'states':st.STATES,'decisions':st.DECISIONS,
                'my_duties':[k for k,v in st.assignments(db).items() if a.id in v],
                'pagination':{'page':page,'size':size,'total':totals.get(section,0),'q':q},'resource_pagination':{'page':resource_page,'size':size,'total':totals.get('resources',0)}}
    return read_operation(request,'records.read',load)


@router.get('/courses/{code}/resources')
def course_resources(code:str,request:Request,page:int=Query(1,ge=1)):
    def load(db,a,s):
        query=select(SocialResource).where(st.course_resource_scope(db,a),SocialResource.kind=='course_resource',SocialResource.data['course_code'].as_string()==code)
        total=db.scalar(select(func.count()).select_from(query.subquery()))
        return {'items':serial(db.scalars(query.order_by(SocialResource.code).offset((page-1)*50).limit(50)).all()),'page':page,'size':50,'total':total}
    return read_operation(request,'records.read',load)


@router.get('/duties')
def duties(request:Request):
    def load(db,a,s):
        a.require_admin();setting=db.get(Setting,'social_training_duties')
        return {'assignments':st.assignments(db),'version':setting.version if setting else 0,'labels':st.DUTIES}
    return read_operation(request,'roles.manage',load)


@router.put('/duties')
def set_duties(data:DutiesIn,request:Request):
    def apply(db,a,s):
        a.require_admin();setting=db.get(Setting,'social_training_duties');before=serial(setting)
        if (setting.version if setting else 0)!=data.expected_version:raise HTTPException(409,'职责配置已变化，请刷新')
        for code,ids in data.assignments.items():
            for ident in ids:
                u=db.get(User,ident);r=db.get(Role,u.role_id) if u else None
                if not u or not u.active or u.org_id not in a.org_ids or not r or not r.active or 'assessment.review' not in r.permissions:raise HTTPException(422,'职责人员须具有有效审核权限')
                if code in {'vice_president','coordinator','committee','finance','academic','discipline'} and r.kind!='school':raise HTTPException(422,'校级职责须授予校级范围账号')
        if not setting:setting=Setting(key='social_training_duties',value=data.assignments,version=1);db.add(setting)
        else:setting.value=data.assignments;setting.version+=1
        db.flush();audit(db,a,'social_duties','social_training_duties','配置社会培训职责',before,serial(setting),data.reason)
        return setting
    return command(request,data.model_dump(),'roles.manage',apply)


@router.post('/projects')
def project_create(data:ProjectIn,request:Request):
    def apply(db,a,s):
        p=data.data;college(db,a,p.org_id);project_owner(db,p.owner_id,p.org_id)
        master=db.scalar(select(TrainingProjectMaster).where(TrainingProjectMaster.code==p.code))
        if master and master.name!=p.name:raise HTTPException(409,'项目编码已存在，请使用现有项目名称')
        if not master:
            master=TrainingProjectMaster(code=p.code,name=p.name,start_date=p.start_date,end_date=p.end_date,source='学校项目申报');db.add(master);db.flush()
        obj=SocialProject(master_id=master.id,org_id=p.org_id,owner_id=p.owner_id,cohort=p.cohort,data=serial(p.model_dump()))
        db.add(obj);db.flush();return event(db,a,'social_project',obj,'建立项目申报',{},data.reason)
    return command(request,data.model_dump(),'records.write',apply)


@router.put('/projects/{ident}')
def project_edit(ident:str,data:ProjectIn,request:Request):
    def apply(db,a,s):
        obj=st.scoped(db,a,'social_project',ident,write=True)
        if obj.state not in {'DRAFT','RETURNED'}:raise HTTPException(409,'核心事项变更须先办理重新备案')
        check_version(obj,data.expected_version);before=serial(obj)
        if any(getattr(data.data,k)!=obj.data[k] for k in ('code','cohort','org_id')):raise HTTPException(422,'项目编号、期次及承办学院不能直接替换')
        project_owner(db,data.data.owner_id,obj.org_id)
        if st.units(db,obj.id) and data.data.mode!=obj.data['mode']:raise HTTPException(409,'已有培训明细，不能更换核算方式')
        values=serial(data.data.model_dump());source=dict(obj.data.get('source',{}))
        if source:
            if data.data.dates_confirmed:source.pop('dates_pending',None);source.pop('date_pending',None)
            if data.data.mode_confirmed:source.pop('mode_pending',None)
            source['policy_pending']=[key for key in source.get('policy_pending',['level','scene'] if source.get('ledger_id') else []) if not values.get(key+'_confirmed')]
            values['source']=source
        obj.data=values;obj.owner_id=data.data.owner_id
        return event(db,a,'social_project',obj,'修改申报草稿',before,data.reason)
    return command(request,data.model_dump(),'records.write',apply)


def validate_units(db,a,project,rows):
    previous=st.units(db,project.id);seen=set();existing={u.external_key for u in previous}
    days={(u.data['class_code'],u.data['event_date']) for u in previous}
    modules={(u.data['class_code'],u.data['course_code'],u.data['module']) for u in previous}
    if issues:=st.person_day_blockers([u.data for u in previous]+[serial(row.model_dump()) for row in rows]):raise HTTPException(409,'；'.join(issues))
    for row in rows:
        if row.external_key in seen or row.external_key in existing:raise HTTPException(409,'来源唯一编号重复，本批未入库')
        seen.add(row.external_key)
        if row.mode!=project.data['mode']:raise HTTPException(422,'同一期项目不能混用核算方式')
        if not project.data['start_date']<=row.event_date.isoformat()<=project.data['end_date']:raise HTTPException(422,'培训日期超出备案期间')
        if row.mode=='person_day':
            key=(row.class_code,row.event_date.isoformat())
            if key in days:raise HTTPException(409,'人天式同一班级同一天必须合并为一个核算单元')
            days.add(key)
        else:
            key=(row.class_code,row.course_code,row.module)
            if key in modules:raise HTTPException(409,'同班同课程模块已有明细，不能换来源编号重复导入')
            modules.add(key)
        course=db.scalar(select(TrainingCourseMaster).where(TrainingCourseMaster.code==row.course_code,TrainingCourseMaster.active==True))
        if not course or course.project_code!=project.data['code']:raise HTTPException(422,'课程须先登记并关联当前项目')
        cl=db.scalar(select(TrainingClassMaster).where(TrainingClassMaster.code==row.class_code))
        if cl and cl.project_code!=project.data['code']:raise HTTPException(422,'班级属于其他项目')
        if cl and cl.course_code and cl.course_code!=row.course_code:raise HTTPException(422,'班级与所选课程不一致')
        for teacher in row.teachers:
            if teacher.staff_type=='internal':a.check_teacher(db,teacher.teacher_id,active=True)
    return {'rows':len(rows),'effective':sum(st.unit_counts(serial(r.model_dump()))['effective'] for r in rows),
            'excluded':sum(st.unit_counts(serial(r.model_dump()))['excluded'] for r in rows),
            'preview_hash':digest({'project_version':project.version,'rows':serial([r.model_dump() for r in rows])})}


@router.post('/projects/{ident}/units/{operation}')
def import_units(ident:str,operation:str,data:UnitsIn,request:Request):
    def apply(db,a,s):
        obj=st.scoped(db,a,'social_project',ident,write=True);check_version(obj,data.expected_version)
        if obj.state!='FILED':raise HTTPException(409,'仅已备案项目可登记培训明细')
        result=validate_units(db,a,obj,data.rows)
        if operation=='preview':return result
        if operation!='confirm':raise HTTPException(422,'导入操作无效')
        if data.preview_hash!=result['preview_hash']:raise HTTPException(409,'请先预检当前明细，预检内容不得更改')
        before=serial(obj)
        for row in data.rows:db.add(SocialUnit(project_id=obj.id,external_key=row.external_key,data=serial(row.model_dump())))
        db.flush();event(db,a,'social_project',obj,'确认培训明细整批入库',before,data.reason)
        return result
    return command(request,data.model_dump(),'records.write',apply)


@router.post('/projects/{ident}/actions')
def project_action(ident:str,data:SocialAction,request:Request):
    def apply(db,a,s):
        obj=st.scoped(db,a,'social_project',ident,write=True);check_version(obj,data.expected_version);before=serial(obj)
        if data.action in {'file','return','close'}:st.check_project_conflicts(db,a,obj)
        if data.action=='submit':
            if obj.state not in {'DRAFT','RETURNED'}:raise HTTPException(409,'当前项目不能提交')
            st.require_project_confirmed(obj)
            st.require_evidence(db,'social_project',ident);obj.state='SUBMITTED'
        elif data.action=='file':
            st.duty(db,a,'coordinator',obj.owner_id,obj.org_id)
            if obj.state!='SUBMITTED':raise HTTPException(409,'项目不在审核备案阶段')
            st.require_project_confirmed(obj)
            if obj.data['category']=='subsidy' or obj.data['high_risk']:
                if not data.basis.strip() or not data.prior_review_on:raise HTTPException(422,'高风险项目须记录前置审核日期及依据')
                if data.prior_review_on.isoformat()>obj.data['start_date'] or data.prior_review_on>st.today():raise HTTPException(422,'前置审核须在培训开始前完成，日期不得晚于今天')
            obj.data={**obj.data,'filed_on':st.today().isoformat(),'filed_by':a.id,'prior_review_on':serial(data.prior_review_on),'filing_basis':data.basis}
            obj.state='FILED'
        elif data.action=='return':
            st.duty(db,a,'coordinator',obj.owner_id,obj.org_id)
            if obj.state not in {'SUBMITTED','CLOSE_REVIEW'}:raise HTTPException(409,'当前项目不能退回')
            obj.state='FILED' if obj.state=='CLOSE_REVIEW' else 'RETURNED'
        elif data.action=='refile':
            if obj.state!='FILED':raise HTTPException(409,'仅已备案项目可申请重新备案')
            obj.state='RETURNED'
        elif data.action=='close_submit':
            if obj.state!='FILED' or not data.closeout:raise HTTPException(409,'请提交已备案项目的完整结项材料')
            st.require_project_confirmed(obj)
            if issues:=st.person_day_blockers([u.data for u in st.units(db,ident)]):raise HTTPException(409,'；'.join(issues))
            if not st.units(db,ident):raise HTTPException(409,'尚无参训核算明细')
            st.require_evidence(db,'social_project',ident);c=data.closeout
            st.require_closeout_distribution(serial(c.model_dump()))
            if c.closed_on.isoformat()<obj.data['end_date'] or c.closed_on>st.today():raise HTTPException(422,'结项日期应在培训结束后且不晚于今天')
            if obj.data['category']=='subsidy' and not (c.province_receipt.strip() and c.special_evidence.strip()):raise HTTPException(422,'补贴项目须提交报送凭证及专项材料')
            if c.satisfaction<85 and not c.rectification.strip():raise HTTPException(422,'满意度低于85%，须提交整改报告及期限')
            obj.closeout=serial(c.model_dump());obj.state='CLOSE_REVIEW'
        elif data.action=='close':
            st.duty(db,a,'coordinator',obj.owner_id,obj.org_id)
            if obj.state!='CLOSE_REVIEW':raise HTTPException(409,'项目不在结项核验阶段')
            st.require_project_confirmed(obj)
            if issues:=st.person_day_blockers([u.data for u in st.units(db,ident)]):raise HTTPException(409,'；'.join(issues))
            st.require_closeout_distribution(obj.closeout)
            required={'plan','filing_form','roster','attendance','hours','process','assessment','outcomes'}
            if set(obj.closeout.get('materials_checked',[]))!=required:raise HTTPException(409,'培训方案、备案表、名册、签到、学时、过程、结业考核及成果材料尚未逐项核验')
            if st.D(obj.closeout['satisfaction'])<85 and not obj.closeout.get('rectification_due'):raise HTTPException(409,'满意度低于85%，须明确整改办理日期')
            from .files import verify_file
            for file in st.attachments(db,'social_project',ident):verify_file(request.app.state.settings.storage_dir,file)
            obj.closeout={**obj.closeout,'reviewed_by':a.id,'review_basis':data.basis,'retention_years':10 if obj.data['category']=='subsidy' else 5};obj.state='CLOSED'
        else:raise HTTPException(422,'项目操作无效')
        result=event(db,a,'social_project',obj,'项目办理：'+st.state_label(obj),before,data.reason,data.basis)
        if obj.state=='CLOSED':satisfaction_achievement(db,a,obj,data.reason)
        return result
    return command(request,data.model_dump(),'records.write',apply)


def satisfaction_achievement(db,a,project,reason):
    value=st.D(project.closeout['satisfaction'])
    if value<=95:return None
    existing=db.scalars(select(SocialResource).where(SocialResource.kind=='achievement',SocialResource.org_id==project.org_id,SocialResource.data['project_id'].as_string()==project.id)).first()
    if existing or db.scalar(select(SocialResource.id).where(SocialResource.code=='SAT-'+project.id)):return None
    shown=format(value.normalize(),'f');suffix='（满意度 '+shown+'%）'
    name=project.data['name'][:160-len(suffix)]+suffix
    obj=SocialResource(kind='achievement',org_id=project.org_id,code='SAT-'+project.id,name=name,
        data={'kind':'achievement','org_id':project.org_id,'code':'SAT-'+project.id,'name':name,'location':'','onsite':True,
              'recognition':'项目结项满意度'+shown+'%，超过95%，按学校规定自动登记校级（C等）培训成果','level':'school','course_code':'',
              'resource_type':'document','resource_url':None,'duration_minutes':None,'auto':True,'source':'satisfaction',
              'project_id':project.id,'reference':project.data['code']+' · '+project.cohort,'satisfaction':shown,'confirmed_on':project.closeout['closed_on']})
    db.add(obj);db.flush();event(db,a,'social_resource',obj,'满意度超过95%自动登记校级培训成果',{},reason)
    return obj


@router.post('/policies')
def policy_create(data:PolicyIn,request:Request):
    def apply(db,a,s):
        if a.role.kind!='school':raise HTTPException(403,'规则须由学校维护')
        require_open_period(db,data.period_id)
        obj=SocialPolicy(period_id=data.period_id,name=data.name,data=serial(data.data.model_dump()),created_by=a.id)
        db.add(obj);db.flush();return event(db,a,'social_policy',obj,'创建制度口径版本',{},data.reason)
    return command(request,data.model_dump(),'rules.manage',apply)


@router.post('/policies/recommended')
def policy_recommended(data:RecommendedPolicyIn,request:Request):
    def apply(db,a,s):
        if a.role.kind!='school':raise HTTPException(403,'规则须由学校维护')
        require_open_period(db,data.period_id)
        values=PolicyData.model_validate(st.RECOMMENDED_POLICY)
        obj=SocialPolicy(period_id=data.period_id,name='推荐口径（待学校书面确认）',data=serial(values.model_dump()),created_by=a.id)
        db.add(obj);db.flush();return event(db,a,'social_policy',obj,'生成推荐口径草稿',{},data.reason,data.basis)
    return command(request,data.model_dump(),'rules.manage',apply)


@router.post('/policies/{ident}/actions')
def policy_action(ident:str,data:SocialAction,request:Request):
    def apply(db,a,s):
        obj=st.scoped(db,a,'social_policy',ident,write=True);check_version(obj,data.expected_version);before=serial(obj)
        if data.action=='record_basis':
            # 推荐口径草稿：学校书面答复后在草稿上登记依据，再启用（规划第 8 步）
            if obj.state!='DRAFT':raise HTTPException(409,'仅草稿可登记书面依据')
            if a.role.kind!='school':raise HTTPException(403,'规则须由学校维护')
            if len(data.basis.strip())<2:raise HTTPException(422,'请在“依据”里写明学校书面答复的文号或会议纪要')
            obj.data={**obj.data,'interpretation_reference':data.basis.strip()}
            return event(db,a,'social_policy',obj,'登记学校书面解释依据',before,data.reason,data.basis)
        if data.action!='activate' or obj.state!='DRAFT':raise HTTPException(409,'仅草稿可启用，修改时须新建版本')
        st.duty(db,a,'coordinator',obj.created_by);st.require_evidence(db,'social_policy',ident)
        if not obj.data.get('interpretation_reference'):raise HTTPException(409,'须记录学校书面解释依据；空缺口径继续阻断正式结果')
        obj.state='ACTIVE';return event(db,a,'social_policy',obj,'确认学校制度执行口径',before,data.reason,data.basis)
    return command(request,data.model_dump(),'rules.manage',apply)


@router.post('/claims')
def claim_create(data:ClaimIn,request:Request):
    def apply(db,a,s):
        if not a.user.staff_no:raise HTTPException(403,'积分必须由有工号的本人申报')
        project=db.get(SocialProject,data.project_id);policy=db.get(SocialPolicy,data.policy_id)
        if not project or not policy or policy.period_id!=data.period_id:raise HTTPException(422,'项目或规则周期无效')
        if not any(t['teacher_id']==a.id for u in st.units(db,project.id) for t in u.data['teachers']):raise HTTPException(403,'没有本人参与明细')
        require_open_period(db,data.period_id)
        if st.duplicate_claim(db,project.id,a.id):raise HTTPException(409,'同一项目已有本人审批中或已归档的积分申报，请使用原申报或追加更正；不能换周期重复认定')
        obj=SocialClaim(project_id=project.id,teacher_id=a.id,period_id=data.period_id,policy_id=policy.id,data={'auxiliary':serial([v.model_dump() for v in data.auxiliary]),'recognition_form_reference':data.recognition_form_reference})
        db.add(obj);db.flush();return event(db,a,'social_claim',obj,'建立本人积分申报',{},data.reason)
    return command(request,data.model_dump(),'points.read',apply)


@router.post('/claims/{ident}/actions')
def claim_action(ident:str,data:SocialAction,request:Request):
    def apply(db,a,s):
        obj=st.scoped(db,a,'social_claim',ident,write=True);check_version(obj,data.expected_version);require_open_period(db,obj.period_id);before=serial(obj)
        stages={'SUBMITTED':('dean','DEAN'),'DEAN':('coordinator','COORDINATOR'),'COORDINATOR':('vice_president','APPROVED'),'APPROVED':('secretary','ARCHIVED')}
        if data.action=='submit':
            if a.id!=obj.teacher_id or obj.state not in {'DRAFT','RETURNED'}:raise HTTPException(403,'仅本人可提交待办申报')
            st.require_evidence(db,'social_claim',ident)
            cfg=db.get(SocialPolicy,obj.policy_id).data
            if obj.state=='RETURNED' and cfg.get('resubmission_mode') is None:raise HTTPException(409,'退回补正的期限口径尚待学校确认')
            submitted=st.today().isoformat() if cfg.get('resubmission_mode')=='resubmission_date' else obj.data.get('submitted_on',st.today().isoformat())
            obj.data={**obj.data,'submitted_on':submitted}
            trial=st.point_trial(db,obj);st.require_unblocked(trial);obj.snapshot=st.freeze(trial);obj.state='SUBMITTED'
        elif data.action in {'approve','return'}:
            if obj.state not in stages:raise HTTPException(409,'当前积分申报不在审批阶段')
            code,next_state=stages[obj.state];st.duty(db,a,code,obj.teacher_id,db.get(SocialProject,obj.project_id).org_id)
            st.check_project_conflicts(db,a,db.get(SocialProject,obj.project_id))
            if data.action=='return':
                obj.state='RETURNED'
                from ..message_push import queue
                queue(db,[obj.teacher_id],'你的社会培训积分申报被退回','请登录非学历教育智慧前台，在“个人培训”查看退回原因并补正。')
            else:
                st.require_fresh(db,obj)
                if next_state=='ARCHIVED':
                    from .files import verify_file
                    for file_kind,file_id in [('social_claim',obj.id),('social_project',obj.project_id),('social_policy',obj.policy_id)]:
                        for file in st.attachments(db,file_kind,file_id):verify_file(request.app.state.settings.storage_dir,file)
                    st.book_claim(db,a,obj)
                obj.state=next_state
        else:raise HTTPException(422,'积分申报操作无效')
        return event(db,a,'social_claim',obj,'积分认定：'+st.STATES[obj.state],before,data.reason,data.basis)
    return command(request,data.model_dump(),'points.read',apply)


@router.post('/annuals')
def annual_create(data:AnnualIn,request:Request):
    def apply(db,a,s):
        college(db,a,data.org_id);require_open_period(db,data.period_id);policy=db.get(SocialPolicy,data.policy_id)
        if not policy or policy.period_id!=data.period_id:raise HTTPException(422,'规则周期不匹配')
        obj=SocialAnnual(org_id=data.org_id,period_id=data.period_id,policy_id=policy.id,owner_id=a.id,data=serial(data.data.model_dump()))
        db.add(obj);db.flush();return event(db,a,'social_annual',obj,'建立学院年度自评',{},data.reason)
    return command(request,data.model_dump(),'assessment.review',apply)


@router.post('/annuals/{ident}/actions')
def annual_action(ident:str,data:SocialAction,request:Request):
    def apply(db,a,s):
        obj=st.scoped(db,a,'social_annual',ident,write=data.action!='dispute');check_version(obj,data.expected_version);require_open_period(db,obj.period_id);before=serial(obj)
        if data.action in {'finance','academic','discipline','coordinator','publish','resolve','archive','return'}:st.check_annual_conflicts(db,a,obj)
        if data.action=='submit':
            if obj.state not in {'DRAFT','RETURNED'}:raise HTTPException(409,'当前自评不能提交')
            st.require_evidence(db,'social_annual',ident);trial=st.annual_trial(db,obj);st.require_unblocked(trial)
            obj.snapshot={**st.freeze(trial),'checks':{},'disputes':[]};obj.state='REVIEW'
        elif data.action in {'finance','academic','discipline','coordinator'}:
            if obj.state!='REVIEW':raise HTTPException(409,'当前不在初核阶段')
            st.duty(db,a,data.action,obj.owner_id,obj.org_id);st.require_fresh(db,obj)
            if data.action in obj.snapshot.get('checks',{}):raise HTTPException(409,'该职能部门已完成核验；如需调整，请由归口退回后重新提交')
            obj.snapshot={**obj.snapshot,'checks':{**obj.snapshot['checks'],data.action:{'actor':a.id,'basis':data.basis,'reason':data.reason}}}
            if set(obj.snapshot['checks'])=={'finance','academic','discipline','coordinator'}:obj.state='COMMITTEE'
        elif data.action=='publish':
            st.duty(db,a,'committee',obj.owner_id,obj.org_id)
            if obj.state!='COMMITTEE':raise HTTPException(409,'尚未完成所有职能部门核验')
            st.require_fresh(db,obj);cfg=db.get(SocialPolicy,obj.policy_id).data
            end=st.add_workdays(st.today(),5,cfg);obj.snapshot={**obj.snapshot,'public_start':st.today().isoformat(),'public_end':end.isoformat()};obj.state='PUBLIC'
            db.add(Notice(title=db.get(Org,obj.org_id).name+'社会培训年度考核公示',body='公示截止：'+end.isoformat()+'。总分：'+str(obj.snapshot['trial']['total'])+'，等级：'+str(obj.snapshot['trial']['grade'])+'。请在学院年度考核页面核对并提出异议。',org_id=obj.org_id,author_id=a.id,published=True,category='年度考核公示'))
        elif data.action=='dispute':
            if obj.state!='PUBLIC':raise HTTPException(409,'当前不在公示期间')
            obj.snapshot={**obj.snapshot,'disputes':[*obj.snapshot.get('disputes',[]),{'actor':a.id,'reason':data.reason,'resolved':False}]}
        elif data.action=='resolve':
            st.duty(db,a,'coordinator',obj.owner_id,obj.org_id)
            if obj.state!='PUBLIC' or not data.basis.strip():raise HTTPException(409,'须在公示期记录异议处理依据')
            if any(x['actor']==a.id and not x['resolved'] for x in obj.snapshot.get('disputes',[])):raise HTTPException(403,'不能处理本人提出的异议')
            obj.snapshot={**obj.snapshot,'disputes':[{**x,'resolved':True,'resolution':data.basis,'resolved_by':a.id} for x in obj.snapshot.get('disputes',[])]}
        elif data.action=='archive':
            st.duty(db,a,'secretary',obj.owner_id,obj.org_id)
            if obj.state!='PUBLIC' or st.today()<=date_from(obj.snapshot['public_end']):raise HTTPException(409,'尚未完成5个完整工作日公示')
            if any(not x['resolved'] for x in obj.snapshot.get('disputes',[])):raise HTTPException(409,'公示异议尚未处理')
            st.require_fresh(db,obj)
            from .files import verify_file
            sources=[('social_annual',obj.id),('social_policy',obj.policy_id)]+[('social_project',fact['project']['id']) for fact in obj.snapshot['trial']['basis']['projects']]
            for file_kind,file_id in sources:
                for file in st.attachments(db,file_kind,file_id):verify_file(request.app.state.settings.storage_dir,file)
            obj.state='ARCHIVED'
        elif data.action=='return':
            st.duty(db,a,'coordinator',obj.owner_id,obj.org_id)
            if obj.state not in {'REVIEW','COMMITTEE','PUBLIC'}:raise HTTPException(409,'当前考核不能退回')
            obj.state='RETURNED'
        else:raise HTTPException(422,'年度考核操作无效')
        return event(db,a,'social_annual',obj,'年度考核：'+st.STATES[obj.state],before,data.reason,data.basis)
    return command(request,data.model_dump(),'assessment.read' if data.action=='dispute' else 'assessment.review',apply)


def date_from(value):
    from datetime import date
    return date.fromisoformat(value)


@router.post('/courses')
def course_create(data:CourseIn,request:Request):
    def apply(db,a,s):
        projects=db.scalars(select(SocialProject).where(SocialProject.org_id.in_(a.org_ids))).all()
        if not any(p.data['code']==data.project_code for p in projects):raise HTTPException(403,'须先建立本组织项目')
        obj=TrainingCourseMaster(code=data.code,name=data.name,project_code=data.project_code,source='学校人工登记')
        db.add(obj);db.flush();audit(db,a,'social_courses',obj.id,'登记培训课程',after=serial(obj),reason=data.reason);return obj
    return command(request,data.model_dump(),'records.write',apply)


@router.post('/courses/import/{operation}')
def course_import(operation:str,data:CourseBatchIn,request:Request):
    def apply(db,a,s):
        projects=db.scalars(select(SocialProject).where(SocialProject.org_id.in_(a.org_ids))).all()
        allowed={p.data['code'] for p in projects};seen=set()
        for row in data.rows:
            if row.project_code not in allowed:raise HTTPException(403,'课程所属项目超出授权范围')
            if row.code in seen or db.scalar(select(TrainingCourseMaster.id).where(TrainingCourseMaster.code==row.code)):raise HTTPException(409,'课程编号重复，本批未导入')
            org_id=next(p.org_id for p in projects if p.data['code']==row.project_code)
            if row.teacher_id and not st.resolve_teacher(db,org_id,row.teacher,row.teacher_id):raise HTTPException(422,'课程教师与学院或姓名不匹配')
            seen.add(row.code)
        fingerprint=digest(serial([r.model_dump() for r in data.rows]))
        if operation=='preview':return {'count':len(data.rows),'videos':sum(1 for r in data.rows if r.video_minutes is not None),'preview_hash':fingerprint}
        if operation!='confirm' or data.preview_hash!=fingerprint:raise HTTPException(409,'须先预检未修改的课程清单')
        orgs={p.data['code']:p.org_id for p in projects};videos=0
        for row in data.rows:
            db.add(TrainingCourseMaster(code=row.code,name=row.name,project_code=row.project_code,source='超星学习通导出' if row.source=='chaoxing' else '学校批量登记'))
            if row.video_minutes is None:continue
            from uuid import uuid4
            code='CXV-'+str(uuid4());name=row.name[:150]+'（超星视频）'
            values={'kind':'course_resource','org_id':orgs[row.project_code],'code':code,'name':name,'location':'超星学习通课程视频汇总','onsite':True,
                    'recognition':'超星学习通导出课程清单'+('；'+data.basis if data.basis else ''),'level':'school','course_code':row.code,'resource_type':'video',
                    'resource_url':None,'duration_minutes':row.video_minutes,'video_count':row.video_count,'teacher':row.teacher,'chapters':row.chapters,'learners':row.learners,'source':row.source}
            teacher=st.resolve_teacher(db,orgs[row.project_code],row.teacher,row.teacher_id)
            values['teacher_id']=teacher.id if teacher else None
            obj=SocialResource(kind='course_resource',org_id=orgs[row.project_code],code=code,name=name,data=serial(values))
            db.add(obj);db.flush();event(db,a,'social_resource',obj,'登记培训资源',{},data.reason);videos+=1
        audit(db,a,'social_courses','batch','批量登记培训课程',after={'codes':sorted(seen),'basis':data.basis,'sources':sorted({r.source for r in data.rows}),'video_resources':videos},reason=data.reason)
        return {'count':len(data.rows),'video_resources':videos}
    return command(request,data.model_dump(),'records.write',apply)


def claim_busy(db,claim_id,*,reviews=True):
    reason=st.claim_busy_reason(db,claim_id,reviews)
    if reason:raise HTTPException(409,reason)


@router.post('/corrections')
def correction_create(data:CorrectionIn,request:Request):
    def apply(db,a,s):
        claim=st.scoped(db,a,'social_claim',data.claim_id)
        if claim.state!='ARCHIVED':raise HTTPException(409,'原认定尚未归档，应退回补正')
        if claim.teacher_id!=a.id:st.duty(db,a,'secretary',claim.teacher_id,db.get(SocialProject,claim.project_id).org_id)
        require_open_period(db,data.period_id);claim_busy(db,claim.id)
        project=db.get(SocialProject,claim.project_id)
        from uuid import uuid4
        obj=SocialResource(org_id=project.org_id,kind='correction',code='COR-'+str(uuid4()),name='社会培训积分更正',
            data={**serial(data.model_dump()),'teacher_id':claim.teacher_id,'created_by':a.id,'original_sha256':claim.snapshot['sha256']})
        db.add(obj);db.flush();return event(db,a,'social_resource',obj,'建立积分更正申请',{},data.reason,data.basis)
    return command(request,data.model_dump(),'points.read',apply)


@router.post('/corrections/{ident}/actions')
def correction_action(ident:str,data:SocialAction,request:Request):
    def apply(db,a,s):
        obj=st.scoped(db,a,'social_resource',ident,write=True);check_version(obj,data.expected_version)
        if obj.kind!='correction':raise HTTPException(422,'不是积分更正申请')
        before=serial(obj);stages={'SUBMITTED':('dean','DEAN'),'DEAN':('coordinator','COORDINATOR'),'COORDINATOR':('vice_president','APPROVED'),'APPROVED':('secretary','ARCHIVED')}
        if data.action=='submit':
            if obj.data['created_by']!=a.id or obj.state not in {'DRAFT','RETURNED'}:raise HTTPException(403,'仅申请人可补正后提交')
            if not (obj.data.get('review_id') and st.evidence(db,'social_resource',obj.data['review_id'])):st.require_evidence(db,'social_resource',ident)
            obj.state='SUBMITTED'
        elif data.action=='void':
            if obj.data['created_by']!=a.id:raise HTTPException(403,'仅发起人可作废尚未入账的更正')
            obj.state='VOID';obj.data={**obj.data,'void_reason':data.reason}
        elif data.action in {'approve','return'}:
            if obj.state not in stages:raise HTTPException(409,'当前更正不在审核阶段')
            duty,next_state=stages[obj.state];st.duty(db,a,duty,obj.data['teacher_id'],obj.org_id)
            claim=db.get(SocialClaim,obj.data['claim_id']);st.check_project_conflicts(db,a,db.get(SocialProject,claim.project_id))
            if a.id==obj.data['created_by']:raise HTTPException(403,'不能审核本人发起的更正')
            if data.action=='return':obj.state='RETURNED'
            else:
                if next_state=='ARCHIVED':
                    from .files import verify_file
                    files=list(st.attachments(db,'social_resource',ident))
                    if obj.data.get('review_id'):
                        st.require_evidence(db,'social_resource',obj.data['review_id'])
                        files+=list(st.attachments(db,'social_resource',obj.data['review_id']))
                    if not files:raise HTTPException(409,'请先补齐更正认定的正式佐证附件')
                    for file in files:verify_file(request.app.state.settings.storage_dir,file)
                    st.book_correction(db,a,obj)
                obj.state=next_state
        else:raise HTTPException(422,'更正办理操作无效')
        return event(db,a,'social_resource',obj,'积分更正：'+st.STATES[obj.state],before,data.reason,data.basis)
    return command(request,data.model_dump(),'points.read',apply)


@router.put('/corrections/{ident}')
def correction_edit(ident:str,data:CorrectionIn,request:Request):
    def apply(db,a,s):
        obj=st.scoped(db,a,'social_resource',ident,write=True);check_version(obj,data.expected_version)
        if obj.kind!='correction' or obj.state not in {'DRAFT','RETURNED'} or obj.data['created_by']!=a.id:raise HTTPException(403,'仅申请人可补正更正草稿')
        if data.claim_id!=obj.data['claim_id']:raise HTTPException(422,'不得更换原认定记录')
        if obj.data.get('review_id') and (D(str(data.teaching))!=D(str(obj.data['teaching'])) or D(str(data.auxiliary))!=D(str(obj.data['auxiliary']))):
            raise HTTPException(409,'由积分核对生成的更正，分值已经教师同意或学院裁定，不能修改；如分值有误，请作废未入账更正后重新发起核对')
        require_open_period(db,data.period_id);before=serial(obj);obj.data={**obj.data,**serial(data.model_dump())}
        return event(db,a,'social_resource',obj,'补正积分更正申请',before,data.reason,data.basis)
    return command(request,data.model_dump(),'points.read',apply)


@router.post('/point-reviews')
def point_review_create(data:PointReviewIn,request:Request):
    """教研室（或学院）发现本单位教师已归档的社会培训积分有误：先建核对单、上传材料，再发给教师回应。"""
    def apply(db,a,s):
        if a.role.kind not in ('dept','college'):raise HTTPException(403,'积分核对由教研室或学院负责人发起；教师本人请用“有异议”')
        claim=st.scoped(db,a,'social_claim',data.claim_id)
        if claim.teacher_id==a.id:raise HTTPException(403,'本人积分请用“有异议”提出核对')
        if claim.state!='ARCHIVED':raise HTTPException(409,'这条积分还在审批中，请由审批人直接退回补正')
        require_open_period(db,data.period_id)
        claim_busy(db,claim.id)
        project=db.get(SocialProject,claim.project_id)
        from uuid import uuid4
        obj=SocialResource(org_id=project.org_id,kind='point_review',code='REV-'+str(uuid4()),name='积分核对：'+project.data['name'],state='DRAFT',
            data={**serial(data.model_dump()),'teacher_id':claim.teacher_id,'created_by':a.id})
        db.add(obj);db.flush();return event(db,a,'social_resource',obj,'发起积分核对',{},data.reason,data.basis)
    return command(request,data.model_dump(),'points.read',apply)


def correction_from_review(db,a,review,how,state='SUBMITTED'):
    claim=db.get(SocialClaim,review.data['claim_id']);d=review.data;claim_busy(db,claim.id,reviews=False)
    from uuid import uuid4
    fix=SocialResource(org_id=review.org_id,kind='correction',code='COR-'+str(uuid4()),name='社会培训积分更正',state=state,
        data={'reason':d['reason'],'basis':d.get('basis',''),'claim_id':d['claim_id'],'period_id':d['period_id'],'teaching':d['teaching'],'auxiliary':d['auxiliary'],
              'decision_reference':'积分核对单 '+review.code+'（'+how+'）','expected_version':None,'teacher_id':d['teacher_id'],'created_by':d['created_by'],
              'original_sha256':claim.snapshot['sha256'],'review_id':review.id})
    db.add(fix);db.flush();workflow(db,a,'social_resource',fix.id,'由积分核对生成更正（'+how+'）',{},serial(fix),d['reason'],review.code)
    return fix


@router.post('/point-reviews/{ident}/actions')
def point_review_action(ident:str,data:SocialAction,request:Request):
    def apply(db,a,s):
        obj=st.scoped(db,a,'social_resource',ident);check_version(obj,data.expected_version)
        if obj.kind!='point_review':raise HTTPException(422,'不是积分核对单')
        d=obj.data;before=serial(obj);label=None
        if data.action=='send':
            if a.id!=d['created_by'] or obj.state!='DRAFT':raise HTTPException(403,'仅发起人可在草稿时发送')
            blockers=st.review_staff_blockers(db,obj)
            if blockers:raise HTTPException(409,'；'.join(blockers))
            st.require_evidence(db,'social_resource',ident);obj.state='TEACHER';label='发给教师回应'
            from ..message_push import queue
            queue(db,[d['teacher_id']],'教研室请你核对一条社会培训积分','请登录非学历教育智慧前台，在“个人培训”查看核对材料，回应同意或不同意。')
        elif data.action=='withdraw':
            if a.id!=d['created_by'] or obj.state not in {'DRAFT','TEACHER'}:raise HTTPException(403,'仅发起人可在教师回应前撤回')
            obj.state='CLOSED';obj.data={**d,'outcome':'withdrawn'};label='发起人撤回核对'
        elif data.action in {'agree','explain'}:
            if a.id!=d['teacher_id'] or obj.state!='TEACHER':raise HTTPException(403,'仅被核对教师本人可回应')
            if data.action=='agree':
                fix=correction_from_review(db,a,obj,'教师同意');obj.state='CLOSED';obj.data={**d,'outcome':'corrected','correction_id':fix.id,'teacher_reply':data.reason};label='教师同意更正，已生成更正单'
            else:obj.state='COLLEGE';obj.data={**d,'teacher_reply':data.reason};label='教师说明情况，提交学院裁定'
        elif data.action in {'uphold','dismiss'}:
            if obj.state!='COLLEGE':raise HTTPException(409,'当前不在学院裁定环节')
            st.duty(db,a,'dean',d['teacher_id'],obj.org_id)
            if a.id==d['created_by']:raise HTTPException(403,'发起人不能裁定本人发起的核对')
            if data.action=='uphold':
                fix=correction_from_review(db,a,obj,'学院院长已裁定，免院长初审','DEAN');obj.state='CLOSED';obj.data={**d,'outcome':'corrected','correction_id':fix.id,'ruling':data.reason};label='学院裁定更正，已生成更正单'
            else:obj.state='CLOSED';obj.data={**d,'outcome':'kept','ruling':data.reason};label='学院裁定维持原认定'
        else:raise HTTPException(422,'核对办理操作无效')
        return event(db,a,'social_resource',obj,label,before,data.reason,data.basis)
    return command(request,data.model_dump(),'points.read',apply)


@router.post('/reports')
def report_create(data:ReportIn,request:Request):
    def apply(db,a,s):
        st.duty(db,a,'secretary',org=data.org_id);rows=st.report_rows(db,a,data.org_id,data.year,data.start_month,data.end_month)
        st.check_report_conflicts(db,a,rows)
        policy=db.get(SocialPolicy,data.policy_id)
        if not policy or policy.state!='ACTIVE':raise HTTPException(409,'请选择已确认的制度与学校工作日历')
        if data.start_month==1 and data.end_month==12 and db.get(Org,data.org_id).kind!='school':raise HTTPException(422,'年度公示须汇总全校')
        from uuid import uuid4
        obj=SocialResource(kind='point_report',org_id=data.org_id,code='REP-'+str(uuid4()),name=f'{data.year}年{data.start_month}—{data.end_month}月积分汇总',
            data={**serial(data.model_dump()),'created_by':a.id,'rows':rows,'sha256':digest(rows),'disputes':[]})
        db.add(obj);db.flush();return event(db,a,'social_resource',obj,'生成已认定积分汇总',{},data.reason,data.basis)
    return command(request,data.model_dump(),'points.read',apply)


@router.post('/reports/{ident}/actions')
def report_action(ident:str,data:SocialAction,request:Request):
    def apply(db,a,s):
        obj=st.scoped(db,a,'social_resource',ident);check_version(obj,data.expected_version);before=serial(obj);d=obj.data
        if obj.kind!='point_report' or obj.state in {'ARCHIVED','VOID'}:raise HTTPException(409,'汇总已归档、已被新公示替代或类型不符')
        if digest(d['rows'])!=d['sha256']:raise HTTPException(409,'汇总快照校验失败')
        if data.action=='submit':
            if a.id!=d['created_by'] or obj.state!='DRAFT':raise HTTPException(403,'仅汇总人可提交草稿')
            obj.state='SUBMITTED'
        elif data.action=='approve':
            st.duty(db,a,'coordinator',d['created_by'],obj.org_id);st.check_report_conflicts(db,a,d['rows'])
            if obj.state!='SUBMITTED':raise HTTPException(409,'汇总尚未提交复核')
            from calendar import monthrange
            from datetime import date
            if st.today()<=date(d['year'],d['end_month'],monthrange(d['year'],d['end_month'])[1]):raise HTTPException(409,'汇总期间尚未结束，可保留草稿，期满后再复核报送')
            current=st.report_rows(db,a,obj.org_id,d['year'],d['start_month'],d['end_month'])
            if digest(current)!=d['sha256']:raise HTTPException(409,'已认定积分发生变化，请重新生成汇总')
            if (d['start_month'],d['end_month'])==(1,12):
                policy=db.get(SocialPolicy,d['policy_id']);end=st.add_workdays(st.today(),5,policy.data)
                obj.data={**d,'public_start':st.today().isoformat(),'public_end':end.isoformat()};obj.state='PUBLIC'
                body='公示截止：'+end.isoformat()+'（完成5个工作日）。请在社会培训积分认定中的汇总公示提出异议。\n'+'\n'.join(r['teacher_name']+' · '+r['project']+'：授课 '+r['teaching']+'，辅助 '+r['auxiliary'] for r in d['rows'])
                notice=Notice(title=obj.name+'公示',body=body,category='社会培训积分公示',org_id=obj.org_id,author_id=a.id,published=True)
                db.add(notice);db.flush();obj.data={**obj.data,'notice_id':notice.id}
                replaced=[]
                for previous in db.scalars(select(SocialResource).where(SocialResource.kind=='point_report',SocialResource.org_id==obj.org_id,SocialResource.state=='PUBLIC',SocialResource.id!=obj.id)):
                    old=previous.data
                    if any(old[k]!=d[k] for k in ('year','start_month','end_month')) or old['sha256']==d['sha256']:continue
                    if any(not x['resolved'] for x in old['disputes']):raise HTTPException(409,'旧公示仍有异议未处理，请先记录处理依据，再重新公示')
                    st.check_report_conflicts(db,a,old['rows']);old_before=serial(previous)
                    old_notice=db.get(Notice,old['notice_id']) if old.get('notice_id') else None
                    if not old_notice:
                        publication=db.scalar(select(WorkflowEvent).where(WorkflowEvent.object_type=='social_resource',WorkflowEvent.object_id==previous.id,WorkflowEvent.before['state'].as_string()=='SUBMITTED',WorkflowEvent.after['state'].as_string()=='PUBLIC').order_by(WorkflowEvent.created_at.desc()).limit(1))
                        candidates=db.scalars(select(Notice).where(Notice.org_id==previous.org_id,Notice.author_id==publication.actor_id,Notice.title==previous.name+'公示',Notice.body.contains('公示截止：'+old['public_end'],autoescape=True),Notice.created_at>=previous.created_at,Notice.created_at<=publication.created_at)).all() if publication else []
                        if len(candidates)!=1:raise HTTPException(409,'旧公示通知关联不明确，请先核实历史公示通知关联，再重新公示')
                        old_notice=candidates[0]
                    if old_notice.org_id!=previous.org_id:raise HTTPException(409,'旧公示通知范围不一致，请先核实关联')
                    previous.state='VOID';previous.data={**old,'notice_id':old_notice.id,'superseded_by':obj.id,'superseded_on':st.today().isoformat()}
                    old_notice.published=False
                    previous.version+=1;workflow(db,a,'social_resource',previous.id,'来源变化，已由新公示替代',old_before,serial(previous),data.reason,data.basis)
                    replaced.append(previous.id)
                if replaced:obj.data={**obj.data,'replaces':replaced}
            else:obj.state='ARCHIVED'
        elif data.action=='dispute':
            if obj.state!='PUBLIC':raise HTTPException(409,'当前不在公示期间')
            obj.data={**d,'disputes':[*d['disputes'],{'actor':a.id,'reason':data.reason,'resolved':False}]}
        elif data.action=='resolve':
            st.duty(db,a,'coordinator',d['created_by'],obj.org_id);st.check_report_conflicts(db,a,d['rows'])
            if obj.state!='PUBLIC' or not data.basis:raise HTTPException(409,'须记录异议核实依据')
            if any(x['actor']==a.id and not x['resolved'] for x in d['disputes']):raise HTTPException(403,'不能处理本人提出的异议')
            obj.data={**d,'disputes':[{**x,'resolved':True,'resolution':data.basis,'resolved_by':a.id} for x in d['disputes']]}
        elif data.action=='archive':
            st.duty(db,a,'secretary',org=obj.org_id);st.check_report_conflicts(db,a,d['rows'])
            if obj.state!='PUBLIC' or st.today()<=date_from(d['public_end']):raise HTTPException(409,'尚未完成5个完整工作日公示')
            if any(not x['resolved'] for x in d['disputes']):raise HTTPException(409,'尚有公示异议未处理')
            current=st.report_rows(db,a,obj.org_id,d['year'],d['start_month'],d['end_month'])
            if digest(current)!=d['sha256']:raise HTTPException(409,'公示期间已认定积分发生变化，请重新生成并公示汇总')
            obj.state='ARCHIVED'
        else:raise HTTPException(422,'汇总办理操作无效')
        return event(db,a,'social_resource',obj,'积分汇总：'+st.state_label(obj),before,data.reason,data.basis)
    return command(request,data.model_dump(),'points.read',apply)


@router.put('/claims/{ident}')
def claim_edit(ident:str,data:ClaimIn,request:Request):
    def apply(db,a,s):
        obj=st.scoped(db,a,'social_claim',ident,write=True)
        check_version(obj,data.expected_version);require_open_period(db,obj.period_id)
        if obj.teacher_id!=a.id or obj.state not in {'DRAFT','RETURNED'}:raise HTTPException(403,'仅本人可补正待办积分')
        if (obj.project_id,obj.period_id)!=(data.project_id,data.period_id):raise HTTPException(422,'补正不能更换项目及周期')
        policy=db.get(SocialPolicy,data.policy_id)
        if not policy or policy.period_id!=obj.period_id:raise HTTPException(422,'规则周期不匹配')
        before=serial(obj);obj.policy_id=data.policy_id;obj.data={**obj.data,'auxiliary':serial([v.model_dump() for v in data.auxiliary]),'recognition_form_reference':data.recognition_form_reference}
        return event(db,a,'social_claim',obj,'补正本人积分申报',before,data.reason)
    return command(request,data.model_dump(),'points.read',apply)


@router.put('/annuals/{ident}')
def annual_edit(ident:str,data:AnnualIn,request:Request):
    def apply(db,a,s):
        obj=st.scoped(db,a,'social_annual',ident,write=True)
        check_version(obj,data.expected_version);require_open_period(db,obj.period_id)
        if obj.state not in {'DRAFT','RETURNED'}:raise HTTPException(409,'请先退回年度考核后补正')
        if (obj.org_id,obj.period_id)!=(data.org_id,data.period_id):raise HTTPException(422,'补正不能更换学院及周期')
        policy=db.get(SocialPolicy,data.policy_id)
        if not policy or policy.period_id!=obj.period_id:raise HTTPException(422,'规则周期不匹配')
        before=serial(obj);obj.data=serial(data.data.model_dump());obj.policy_id=data.policy_id
        return event(db,a,'social_annual',obj,'补正学院自评',before,data.reason)
    return command(request,data.model_dump(),'assessment.review',apply)


@router.post('/projects/{ident}/notes')
def case_note(ident:str,data:CaseNoteIn,request:Request):
    def apply(db,a,s):
        obj=st.scoped(db,a,'social_project',ident);check_version(obj,data.expected_version)
        previous=next((x for x in st.project_followups(db,ident) if x['case_reference']==data.case_reference),None)
        financial=data.kind=='settlement' and (data.settlement_result or (previous or {}).get('settlement_result') or a.id in st.assignments(db).get('finance',[]))
        st.duty(db,a,'finance' if financial else 'discipline' if data.kind=='violation' else 'coordinator',obj.owner_id,obj.org_id)
        st.check_project_conflicts(db,a,obj)
        policy=db.get(SocialPolicy,data.policy_id)
        if not policy or policy.state!='ACTIVE':raise HTTPException(409,'请先选择已确认工作日历')
        if previous and previous['kind']!=data.kind:raise HTTPException(409,'事项编号已有记录，不得换成其他类型覆盖')
        deadlines={}
        if data.kind=='complaint':
            deadlines['调查启动期限']=st.add_workdays(data.received_on,2,policy.data).isoformat()
            if not data.major:deadlines['一般投诉办结期限']=st.add_workdays(data.received_on,10,policy.data).isoformat()
            if data.completed_on and not data.reply.strip():raise HTTPException(422,'办结投诉须记录书面回复')
            if data.major and not data.basis.strip():raise HTTPException(422,'重大投诉须记录提交委员会的依据')
        if data.due_on:deadlines['办理期限']=data.due_on.isoformat()
        before={'version':obj.version};obj.version+=1
        workflow(db,a,'social_project',ident,'投诉与项目跟踪',before,{**serial(data.model_dump()),'deadlines':deadlines},data.reason,data.basis)
        return {'deadlines':deadlines,'version':obj.version}
    return command(request,data.model_dump(),'assessment.review',apply)


def resource_values(db,a,data):
    college(db,a,data.org_id)
    if data.kind=='course_resource':
        course=db.scalar(select(TrainingCourseMaster).where(TrainingCourseMaster.code==data.course_code))
        allowed=db.scalars(select(SocialProject).where(SocialProject.org_id==data.org_id)).all()
        if not course or not any(p.data['code']==course.project_code for p in allowed):raise HTTPException(422,'课程不属于所选学院项目')
    values=data.model_dump(exclude={'reason','basis','resource_url','expected_version'});values['resource_url']=str(data.resource_url) if data.resource_url else None
    if data.kind=='course_resource':
        teacher=st.resolve_teacher(db,data.org_id,data.teacher,data.teacher_id)
        if data.teacher_id and not teacher:raise HTTPException(422,'课程教师与学院或姓名不匹配')
        values['teacher_id']=teacher.id if teacher else None
    return serial(values)


@router.post('/resources')
def resource_create(data:ResourceIn,request:Request):
    def apply(db,a,s):
        values=resource_values(db,a,data)
        obj=SocialResource(kind=data.kind,org_id=data.org_id,code=data.code,name=data.name,data=values)
        db.add(obj);db.flush();return event(db,a,'social_resource',obj,'登记培训资源',{},data.reason)
    return command(request,data.model_dump(),'records.write',apply)


@router.put('/resources/{ident}')
def resource_update(ident:str,data:ResourceUpdate,request:Request):
    def apply(db,a,s):
        obj=st.scoped(db,a,'social_resource',ident,write=True);check_version(obj,data.expected_version)
        if obj.kind not in {'base','achievement','course_resource'} or obj.data.get('auto') or obj.state=='ARCHIVED':raise HTTPException(409,'此项由原业务生成，请从原业务办理更正')
        if (obj.kind,obj.org_id,obj.code)!=(data.kind,data.org_id,data.code):raise HTTPException(422,'资源类型、所属学院和来源编号不能变更')
        before=serial(obj);values=resource_values(db,a,data)
        obj.name=data.name;obj.data={**obj.data,**values}
        return event(db,a,'social_resource',obj,'补正培训资源资料',before,data.reason,data.basis)
    return command(request,data.model_dump(),'records.write',apply)


@router.get('/ledger-summary')
def ledger_summary(request:Request):
    def load(db,a,s):
        rows=db.scalars(select(SocialClaim).where(a.scope(SocialClaim.teacher_id),SocialClaim.state=='ARCHIVED')).all()
        teachers={};year=st.today().year
        for claim in rows:
            trial=claim.snapshot['trial'];closed=trial['basis']['facts']['project']['closeout']['closed_on'];claim_year=int(closed[:4])
            record=teachers.setdefault(claim.teacher_id,{'teacher_id':claim.teacher_id,'teaching':st.D(0),'auxiliary':st.D(0),'five_year_total':st.D(0),'years':{}})
            totals=st.correction_totals(db,claim);total=sum(totals.values())
            record['teaching']+=totals['teaching'];record['auxiliary']+=totals['auxiliary']
            if year-4<=claim_year<=year:record['five_year_total']+=total
            y=record['years'].setdefault(str(claim_year),{'teaching':st.D(0),'auxiliary':st.D(0),'title_score':st.D(0),'title_pending':False})
            y['teaching']+=totals['teaching'];y['auxiliary']+=totals['auxiliary']
            cfg=trial['basis']['policy']['data'];scope=cfg.get('title_scope');title_config=(cfg.get('title_precision'),cfg.get('title_rounding'))
            if '_title_config' in y and y['_title_config']!=title_config:y['title_pending']=True
            y['_title_config']=title_config
            if scope is None or None in title_config:y['title_pending']=True
            else:y['title_score']+=(total if scope=='all' else totals['teaching'])/100
        for teacher in teachers.values():
            for y in teacher['years'].values():
                precision,_=y.pop('_title_config')
                y['title_score']=None if y['title_pending'] else str(y['title_score'].quantize(st.D(1).scaleb(-precision),rounding=st.ROUND_HALF_UP))
        return {'items':serial(list(teachers.values())),'promotion_gate_enabled':False,'note':'仅汇总本模块已归档认定积分；历史汇总记录须补齐依据后另行核定。近五年340分条件尚不用于拦截职称申报。'}
    return read_operation(request,'points.read',load)


@router.get('/objects/{kind}/{ident}')
def object_detail(kind:str,ident:str,request:Request):
    return read_operation(request,'records.read',lambda db,a,s:st.detail(db,a,kind,st.scoped(db,a,kind,ident,allow_participant=True)))


@router.get('/objects/{kind}/{ident}/export')
def object_export(kind:str,ident:str,request:Request):
    def load(db,a,s):
        a.require('records.read')
        result=st.detail(db,a,kind,st.scoped(db,a,kind,ident,allow_participant=True));audit(db,a,kind,ident,'导出业务证据',after={'version':result['item']['version']},reason='授权导出')
        return result
    payload=read_operation(request,'export',load)
    from ..social_export import workbook
    return Response(workbook(payload),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':"attachment; filename=social-training.xlsx"})
