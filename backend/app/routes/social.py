"""Social training within the existing authenticated portal and transaction boundary."""
from decimal import Decimal as D
from types import SimpleNamespace
from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select, func, or_
from ..core import command, read_operation, serial, audit, workflow, check_version, require_open_period, digest
from ..models import Org, User, Role, Setting, Period, PointEntry, Notice, WorkflowEvent
from ..reference_data import TrainingProjectMaster, TrainingCourseMaster, TrainingClassMaster
from ..social_models import SocialProject, SocialUnit, SocialPolicy, SocialClaim, SocialAnnual, SocialResource
from ..social_schemas import ReportInfoIn,PrepIn,ProjectIn, UnitsIn, SocialAction, PolicyIn, PolicyUpdate, RecommendedPolicyIn, PolicyCalendarIn, PolicyData, ClaimIn, AnnualIn, ResourceIn, ResourceUpdate, DutiesIn, CourseIn, CourseBatchIn, CaseNoteIn, CorrectionIn, ReportIn, PointReviewIn
from .. import social_training as st

router=APIRouter(prefix='/api/social',tags=['社会培训项目与制度'])


def college(db,a,ident):
    org=db.get(Org,ident)
    if not org or not org.active or org.kind!='college' or ident not in a.org_ids:raise HTTPException(403,'学院超出授权范围')
    return org


def project_owner(db,ident,org_id):
    user=db.get(User,ident)
    org=db.get(Org,user.org_id) if user else None
    if not user or not user.active or user.authorization_pending or not org or (org.id!=org_id and org.parent_id!=org_id):raise HTTPException(422,'项目负责人须为承办学院的有效人员')


def event(db,a,kind,obj,action,before,reason,basis='',handling=None):
    obj.version+=1;db.flush()
    after=serial(obj)
    if handling:
        from ..approvals import handling_after
        after=handling_after(after,handling)
    workflow(db,a,kind,obj.id,action,before,after,reason,basis)
    return st.detail(db,a,kind,obj)


# 老师可以发起本人负责的培训项目；学院、学校有登记权限的账号可以代登记。
TEACHER_PROJECT_ACTIONS={'submit','close_submit','refile'}


def project_applicant(db,a,p):
    if a.role.kind=='teacher':
        from ..applications import college_for
        if p.owner_id!=a.id:raise HTTPException(403,'老师只能申报本人负责的项目')
        if p.org_id!=college_for(db,a.user).id:raise HTTPException(422,'承办学院须为本人所在学院')
        return
    a.require('records.write');college(db,a,p.org_id)



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
        resource_query=select(SocialResource).where(SocialResource.kind.in_(['base','achievement','course_resource','ledger','correction','point_review','point_report'])).where(SocialResource.org_id.in_(resource_scope),SocialResource.kind!='ledger')
        if a.role.kind in ('teacher','dept'):
            mine=SocialResource.kind.in_(['correction','point_review'])&SocialResource.data['teacher_id'].as_string().in_([a.id] if a.role.kind=='teacher' else (list(a.teacher_ids) or ['']))
            resource_query=select(SocialResource).where(SocialResource.kind.in_(['base','achievement','course_resource','ledger','correction','point_review','point_report'])).where((SocialResource.org_id.in_(resource_scope)&SocialResource.kind.notin_(['ledger','correction','point_review']))|mine)
            if a.role.kind=='dept':resource_query=resource_query.where(SocialResource.kind.in_(st.DEPT_READABLE_RESOURCES|{'correction','point_review'}))
            if a.role.kind=='teacher':resource_query=resource_query.where((SocialResource.kind!='point_review')|(SocialResource.state!='DRAFT'))
        if a.role.kind=='teacher':resource_query=resource_query.where((SocialResource.kind!='point_report')|SocialResource.state.in_(['PUBLIC','ARCHIVED']))
        if 'points.read' not in a.permissions:resource_query=resource_query.where(SocialResource.kind.notin_(['correction','point_report','point_review']))
        if a.role.kind=='teacher' and 'points.read' in a.permissions:
            parent=db.get(Org,a.org.parent_id)
            if parent:
                visible=resource_query.with_only_columns(SocialResource.id)
                school_reports=(SocialResource.org_id==parent.parent_id)&(SocialResource.kind=='point_report')&SocialResource.state.in_(['PUBLIC','ARCHIVED'])
                resource_query=select(SocialResource).where(SocialResource.kind.in_(['base','achievement','course_resource','ledger','correction','point_review','point_report'])).where(or_(SocialResource.id.in_(visible),school_reports))
        resource_query=resource_query.where(or_(SocialResource.kind!='course_resource',st.course_resource_scope(db,a)))
        if a.role.kind in ('teacher','dept'):
            # 审批中、退回或撤回的基地申请，只有申请人（教研室看本室老师）能在基地清单里看到。
            own=[a.id] if a.role.kind=='teacher' else [a.id,*a.teacher_ids]
            resource_query=resource_query.where(or_(SocialResource.kind!='base',SocialResource.state.notin_(['DEPT','COLLEGE','SCHOOL','RETURNED','WITHDRAWN']),SocialResource.data['teacher_id'].as_string().in_(own)))
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
        course_info={}
        codes=[c.code for c in courses]
        for i in range(0,len(codes),500):
            for r in db.scalars(select(SocialResource).where(SocialResource.kind=='course_apply',SocialResource.state=='ACTIVE',SocialResource.data['course_code'].as_string().in_(codes[i:i+500]))):
                d=r.data;course_info[d['course_code']]={**{k:d.get(k) for k in ('hours','teaching_mode','ideology','teacher_name','courseware','audience','intro','package','one_skill','target_groups')},
                    'application_id':r.id if d.get('application') else None,'source':d.get('source')}
        resource_orgs=dict(db.execute(select(Org.id,Org.name).where(Org.id.in_({r.org_id for r in resources}|{r.org_id for r in annuals}))).all()) if resources or annuals else {}
        display=lambda rows:[{**serial(row),'state_label':st.state_label(row)} for row in rows]
        from ..social_schemas import quality_blockers
        project_items=[{**st.project_read_item(a,p),'state_label':st.state_label(p),'report_issues':quality_blockers(p.data)} for p in projects]
        claim_items=[st.claim_read_item(db,a,c) for c in claims]
        return {'projects':project_items,'claims':claim_items,'annuals':[{**st.annual_read_item(a,row),'org_name':resource_orgs.get(row.org_id,'—')} for row in annuals],'resources':[{**row,'org_name':resource_orgs[row['org_id']]} for row in display(resources)],
                'policies':display(policies),'courses':serial(courses),'course_stats':serial(course_stats),'course_info':serial(course_info),'states':st.STATES,'decisions':st.DECISIONS,
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
        assignments=st.assignments(db)
        people=[]
        for ident in {i for ids in assignments.values() for i in ids}:
            user=db.get(User,ident)
            people.append({'id':ident,'name':user.name if user else '原账号已不存在','username':user.username if user else '',
                           'staff_no':user.staff_no if user else '', 'org_name':db.get(Org,user.org_id).name if user and db.get(Org,user.org_id) else ''})
        return {'assignments':assignments,'version':setting.version if setting else 0,'labels':st.DUTIES,'people':people}
    return read_operation(request,'roles.manage',load)


@router.get('/duty-options')
def duty_options(request:Request,duty:str,q:str=Query('',max_length=100),page:int=Query(1,ge=1)):
    def load(db,a,s):
        a.require_admin()
        if duty not in st.DUTIES:raise HTTPException(422,'审批职责不存在')
        query=select(User).where(User.org_id.in_(a.org_ids))
        if q:query=query.where(or_(User.name.contains(q,autoescape=True),User.username.contains(q,autoescape=True),User.staff_no.contains(q,autoescape=True)))
        total=db.scalar(select(func.count()).select_from(query.subquery()))
        rows=db.scalars(query.order_by(User.name,User.id).offset((page-1)*25).limit(25)).all()
        return {'items':[{'id':u.id,'name':u.name,'username':u.username,'staff_no':u.staff_no,
                          'org_name':db.get(Org,u.org_id).name,'eligible':st.duty_eligible(db,u,a,duty)} for u in rows],
                'total':total,'page':page,'size':25}
    return read_operation(request,'roles.manage',load)


@router.put('/duties')
def set_duties(data:DutiesIn,request:Request):
    def apply(db,a,s):
        a.require_admin();setting=db.get(Setting,'social_training_duties');before=serial(setting)
        if (setting.version if setting else 0)!=data.expected_version:raise HTTPException(409,'职责配置已变化，请刷新')
        for code,ids in data.assignments.items():
            for ident in ids:
                u=db.get(User,ident)
                if not st.duty_eligible(db,u,a,code):raise HTTPException(422,st.DUTIES[code]+'人员须具有有效审核身份及对应组织范围')
        if not setting:setting=Setting(key='social_training_duties',value=data.assignments,version=1);db.add(setting)
        else:setting.value=data.assignments;setting.version+=1
        db.flush();audit(db,a,'social_duties','social_training_duties','配置社会培训职责',before,serial(setting),data.reason)
        return setting
    return command(request,data.model_dump(),'roles.manage',apply)


@router.post('/projects')
def project_create(data:ProjectIn,request:Request):
    def apply(db,a,s):
        p=data.data;project_applicant(db,a,p);project_owner(db,p.owner_id,p.org_id)
        if not p.venue:raise HTTPException(422,'请填写培训场地（校内基地、其他校内场所或校外一事一议）')
        master=db.scalar(select(TrainingProjectMaster).where(TrainingProjectMaster.code==p.code))
        if master and master.name!=p.name:raise HTTPException(409,'项目编码已存在，请使用现有项目名称')
        if not master:
            master=TrainingProjectMaster(code=p.code,name=p.name,start_date=p.start_date,end_date=p.end_date,source='学校项目申报');db.add(master);db.flush()
        obj=SocialProject(master_id=master.id,org_id=p.org_id,owner_id=p.owner_id,cohort=p.cohort,data=serial(p.model_dump()))
        db.add(obj);db.flush();return event(db,a,'social_project',obj,'建立项目申报',{},data.reason)
    return command(request,data.model_dump(),'portal.read',apply)


@router.put('/projects/{ident}')
def project_edit(ident:str,data:ProjectIn,request:Request):
    def apply(db,a,s):
        obj=st.scoped(db,a,'social_project',ident,write=True)
        if obj.state not in {'DRAFT','RETURNED'}:raise HTTPException(409,'核心事项变更须先办理重新备案')
        check_version(obj,data.expected_version);before=serial(obj)
        if not data.data.venue:raise HTTPException(422,'新申报和重新备案须填写培训场地（校内基地、其他校内场所或校外一事一议）')
        if any(getattr(data.data,k)!=obj.data[k] for k in ('code','cohort','org_id')):raise HTTPException(422,'项目编号、期次及承办学院不能直接替换')
        if a.role.kind=='teacher' and data.data.owner_id!=a.id:raise HTTPException(403,'老师不能把项目负责人改成别人')
        project_owner(db,data.data.owner_id,obj.org_id)
        if st.units(db,obj.id) and data.data.mode!=obj.data['mode']:raise HTTPException(409,'已有培训明细，不能更换核算方式')
        outside=[u.external_key for u in st.units(db,obj.id) if not data.data.start_date.isoformat()<=u.data['event_date']<=data.data.end_date.isoformat()]
        if outside:raise HTTPException(409,'已有参训明细超出修改后的培训期间：'+'、'.join(outside[:10])+'；请核对明细后再调整日期')
        values=serial(data.data.model_dump());source=dict(obj.data.get('source',{}))
        if source:
            if data.data.dates_confirmed:source.pop('dates_pending',None);source.pop('date_pending',None)
            if data.data.mode_confirmed:source.pop('mode_pending',None)
            source['policy_pending']=[key for key in source.get('policy_pending',['level','scene'] if source.get('ledger_id') else []) if not values.get(key+'_confirmed')]
            values['source']=source
        values={**values,**{k:obj.data[k] for k in ('returned_level','prep') if k in obj.data}}
        obj.data=values;obj.owner_id=data.data.owner_id
        return event(db,a,'social_project',obj,'修改申报草稿',before,data.reason)
    return command(request,data.model_dump(),'portal.read',apply)


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
        from .. import approvals as ap
        from ..social_schemas import quality_blockers
        obj=st.scoped(db,a,'social_project',ident,write=True);check_version(obj,data.expected_version);before=serial(obj)
        if a.role.kind=='teacher' and data.action not in TEACHER_PROJECT_ACTIONS:raise HTTPException(403,'老师只能提交、结项提交或申请重新备案本人负责的项目')
        if data.action in {'file','return','close'} and obj.state in {'SUBMITTED','CLOSE_REVIEW'}:st.check_project_conflicts(db,a,obj)
        owner=db.get(User,obj.owner_id)
        # 老师、教研室提交的项目先到学院审批；学院、学校账号登记提交的，学院这一级视为登记时已确认。
        via_college=a.role.kind in {'teacher','dept'}
        handling=None
        if data.action=='submit':
            if obj.state not in {'DRAFT','RETURNED'}:raise HTTPException(409,'当前项目不能提交')
            st.require_project_confirmed(obj)
            if not obj.data.get('venue'):raise HTTPException(409,'请先在“修改项目资料”里填写培训场地（新申报和重新备案必填）')
            if via_college and (issues:=quality_blockers(obj.data)):raise HTTPException(409,'“立德树人与质量”等上报信息还没填完：'+'；'.join(issues))
            st.require_evidence(db,'social_project',ident)
            level=obj.data.get('returned_level') if obj.state=='RETURNED' else None
            obj.state='SUBMITTED' if level=='school' or not via_college else 'COLLEGE'
            obj.data={**obj.data,'returned_level':None}
            handling={'flow':'project','decision':'submit','resumed_from':level,'college_by_registrant':None if via_college else '学院、学校登记时已确认'}
        elif data.action in {'approve','college_return'} and obj.state in {'COLLEGE','CLOSE_COLLEGE'}:
            flow='project' if obj.state=='COLLEGE' else 'project_close'
            handling={**ap.check_handler(db,a,owner,'college',obj.org_id),'flow':flow,'decision':'approve' if data.action=='approve' else 'return'}
            if data.action=='approve':
                if ap.same_person(db,'social_project',obj.id,a):handling['same_person']=ap.SAME_PERSON
                if flow=='project':st.require_project_confirmed(obj)
                elif obj.data.get('quality'):
                    # 学院结项核验即核对了主讲教师资格审查表和课件内容审查记录（两项审查都由学院做）。
                    q=obj.data['quality']
                    if not (q.get('teacher_review') or {}).get('checked') or not (q.get('courseware_review') or {}).get('checked'):raise HTTPException(409,'主讲教师资格审查表或课件内容审查记录还没有学院签字')
                    obj.closeout={**obj.closeout,'materials_checked':sorted(set(obj.closeout.get('materials_checked',[]))|{'teacher_review','courseware_review'}),'college_checked_by':a.id}
                obj.state='SUBMITTED' if flow=='project' else 'CLOSE_REVIEW'
            else:
                obj.state='RETURNED' if flow=='project' else 'FILED'
                if flow=='project':obj.data={**obj.data,'returned_level':'college'}
        elif data.action=='file':
            st.duty(db,a,'coordinator',obj.owner_id,obj.org_id)
            if obj.state!='SUBMITTED':raise HTTPException(409,'项目不在审核备案阶段')
            st.require_project_confirmed(obj)
            if obj.data['category']=='subsidy' or obj.data['high_risk']:
                if not data.basis.strip() or not data.prior_review_on:raise HTTPException(422,'高风险项目须记录前置审核日期及依据')
                if data.prior_review_on.isoformat()>obj.data['start_date'] or data.prior_review_on>st.today():raise HTTPException(422,'前置审核须在培训开始前完成，日期不得晚于今天')
            obj.data={**obj.data,'filed_on':st.today().isoformat(),'filed_by':a.id,'prior_review_on':serial(data.prior_review_on),'filing_basis':data.basis}
            obj.state='FILED'
            project_bases(db,obj)
            handling={'flow':'project','decision':'approve','level':'school'}
        elif data.action=='return':
            st.duty(db,a,'coordinator',obj.owner_id,obj.org_id)
            if obj.state not in {'SUBMITTED','CLOSE_REVIEW'}:raise HTTPException(409,'当前项目不能退回')
            handling={'flow':'project_close' if obj.state=='CLOSE_REVIEW' else 'project','decision':'return','level':'school'}
            if obj.state=='SUBMITTED':obj.data={**obj.data,'returned_level':'school'}
            obj.state='FILED' if obj.state=='CLOSE_REVIEW' else 'RETURNED'
        elif data.action=='refile':
            if obj.state!='FILED':raise HTTPException(409,'仅已备案项目可申请重新备案')
            obj.state='RETURNED';obj.data={**obj.data,'returned_level':None}
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
            obj.closeout=serial(c.model_dump());obj.state='CLOSE_COLLEGE' if via_college else 'CLOSE_REVIEW'
            handling={'flow':'project_close','decision':'submit','college_by_registrant':None if via_college else '学院、学校登记时已确认'}
        elif data.action=='close':
            st.duty(db,a,'coordinator',obj.owner_id,obj.org_id)
            if obj.state!='CLOSE_REVIEW':raise HTTPException(409,'项目不在结项核验阶段')
            st.require_project_confirmed(obj)
            if issues:=st.person_day_blockers([u.data for u in st.units(db,ident)]):raise HTTPException(409,'；'.join(issues))
            st.require_closeout_distribution(obj.closeout)
            required={'plan','filing_form','roster','attendance','hours','process','assessment','outcomes'}
            # 有“立德树人与质量”的项目，结项还要核对主讲教师资格审查表和课件内容审查记录。
            if obj.data.get('quality'):required|={'teacher_review','courseware_review'}
            if not required<=set(obj.closeout.get('materials_checked',[])):raise HTTPException(409,'培训方案、备案表、名册、签到、学时、过程、结业考核及成果材料'+('，主讲教师资格审查表、课件内容审查记录' if obj.data.get('quality') else '')+'尚未逐项核验')
            if st.D(obj.closeout['satisfaction'])<85 and not obj.closeout.get('rectification_due'):raise HTTPException(409,'满意度低于85%，须明确整改办理日期')
            from .files import verify_file
            for file in st.attachments(db,'social_project',ident):verify_file(request.app.state.settings.storage_dir,file)
            obj.closeout={**obj.closeout,'reviewed_by':a.id,'review_basis':data.basis,'retention_years':10 if obj.data['category']=='subsidy' else 5};obj.state='CLOSED'
            handling={'flow':'project_close','decision':'approve','level':'school'}
        else:raise HTTPException(422,'项目操作无效')
        result=event(db,a,'social_project',obj,'项目办理：'+st.state_label(obj),before,data.reason,data.basis,handling)
        if obj.state=='CLOSED':satisfaction_achievement(db,a,obj,data.reason)
        if handling and handling.get('decision')=='return':
            from .. import message_push
            message_push.queue(db,[obj.owner_id],'培训项目被退回',obj.data['name']+'：'+data.reason)
        return result
    return command(request,data.model_dump(),'portal.read',apply)


def project_bases(db,project):
    """本项目设立的思政实践教学基地随项目备案一并进入基地清单，不另走基地申请。"""
    for i,b in enumerate(((project.data.get('quality') or {}).get('bases') or []),1):
        code=('PB-'+project.data['code']+'-'+project.cohort+'-'+str(i))[:64]
        if db.scalar(select(SocialResource.id).where(SocialResource.code==code)):continue
        db.add(SocialResource(kind='base',org_id=project.org_id,code=code,name=b['name'],state='DRAFT',
            data={**b,'usages':['ideology'],'recognition':'随培训项目备案设立：'+project.data['name'],'project_id':project.id,'auto':True,'effective_on':st.today().isoformat()}))
    db.flush()


@router.put('/projects/{ident}/prep')
def project_prep(ident:str,data:PrepIn,request:Request):
    """开班前准备清单：负责人、学院、学校勾选，只提醒不拦截。"""
    def apply(db,a,s):
        obj=st.scoped(db,a,'social_project',ident,write=True);check_version(obj,data.expected_version)
        if obj.state in {'CLOSED','CANCELLED'}:raise HTTPException(409,'项目已结束，不再维护开班准备')
        before=serial(obj);prep={**obj.data.get('prep',{}),**data.items}
        obj.data={**obj.data,'prep':prep}
        return event(db,a,'social_project',obj,'更新开班前准备清单',before,data.reason)
    return command(request,data.model_dump(mode='json'),'portal.read',apply)


@router.put('/projects/{ident}/report-info')
def project_report_info(ident:str,data:ReportInfoIn,request:Request):
    """学院给已结项（或已备案）的历史项目补填上报信息：不重新走审批，留修改痕迹。"""
    def apply(db,a,s):
        obj=db.get(SocialProject,ident)
        if obj is None:raise HTTPException(404,'项目不存在')
        if a.role.kind not in {'college','school'} or obj.org_id not in a.org_ids:raise HTTPException(403,'上报信息由承办学院或学校补填')
        a.require('records.write');check_version(obj,data.expected_version)
        if obj.state not in {'FILED','CLOSE_COLLEGE','CLOSE_REVIEW','CLOSED'}:raise HTTPException(409,'还没备案的项目请在申报里填写')
        before=serial(obj)
        values={k:v for k,v in serial(data.model_dump()).items() if k in {'total_hours','audiences','audience_other','quality'}}
        obj.data={**obj.data,**values,'report_info_by':a.id,'report_info_on':st.today().isoformat()}
        result=event(db,a,'social_project',obj,'补填上报信息',before,data.reason,data.basis)
        project_bases(db,obj)
        return result
    return command(request,data.model_dump(mode='json'),'portal.read',apply)


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


@router.put('/policies/{ident}')
def policy_edit(ident:str,data:PolicyUpdate,request:Request):
    def apply(db,a,s):
        obj=st.scoped(db,a,'social_policy',ident,write=True);check_version(obj,data.expected_version)
        if a.role.kind!='school' or obj.state!='DRAFT':raise HTTPException(409,'仅学校可编辑尚未启用的制度草稿')
        require_open_period(db,obj.period_id);require_open_period(db,data.period_id)
        if data.period_id!=obj.period_id and any(db.scalar(select(m.id).where(m.policy_id==ident).limit(1)) for m in (SocialClaim,SocialAnnual)):
            raise HTTPException(409,'草稿已有申报或自评引用，不能更换周期，请复制为新版本')
        before=serial(obj);obj.name=data.name;obj.period_id=data.period_id;obj.data=serial(data.data.model_dump())
        return event(db,a,'social_policy',obj,'补齐学校制度草稿',before,data.reason,data.basis)
    return command(request,data.model_dump(),'rules.manage',apply)


@router.put('/policies/{ident}/calendar')
def policy_calendar(ident:str,data:PolicyCalendarIn,request:Request):
    def apply(db,a,s):
        obj=st.scoped(db,a,'social_policy',ident,write=True);check_version(obj,data.expected_version)
        if a.role.kind!='school':raise HTTPException(403,'校历须由学校维护')
        if obj.state!='DRAFT':raise HTTPException(409,'仅草稿可补充校历，生效口径须新建版本')
        require_open_period(db,obj.period_id);before=serial(obj)
        obj.data={**obj.data,**data.model_dump(mode='json',exclude={'expected_version','reason','basis'})}
        return event(db,a,'social_policy',obj,'补充学校工作日历',before,data.reason,data.basis)
    return command(request,data.model_dump(mode='json'),'rules.manage',apply)


@router.post('/policies/{ident}/actions')
def policy_action(ident:str,data:SocialAction,request:Request):
    def apply(db,a,s):
        obj=st.scoped(db,a,'social_policy',ident,write=data.action!='deactivate');check_version(obj,data.expected_version);before=serial(obj)
        if data.action=='deactivate':
            if obj.state!='ACTIVE':raise HTTPException(409,'仅生效口径可停用')
            st.duty(db,a,'coordinator',obj.created_by)
            if any(db.scalar(select(model.id).where(model.policy_id==ident,model.state!='ARCHIVED').limit(1)) for model in (SocialClaim,SocialAnnual)):
                raise HTTPException(409,'此口径仍有关联的未归档申报或年度考核，请先完成办理或调整草稿口径')
            obj.state='VOID'
            return event(db,a,'social_policy',obj,'停用制度口径（历史记录保留）',before,data.reason,data.basis)
        if data.action=='record_basis':
            require_open_period(db,obj.period_id)
            # 推荐口径草稿：学校书面答复后在草稿上登记依据，再启用（规划第 8 步）
            if obj.state!='DRAFT':raise HTTPException(409,'仅草稿可登记书面依据')
            if a.role.kind!='school':raise HTTPException(403,'规则须由学校维护')
            if len(data.basis.strip())<2:raise HTTPException(422,'请在“依据”里写明学校书面答复的文号或会议纪要')
            obj.data={**obj.data,'interpretation_reference':data.basis.strip()}
            return event(db,a,'social_policy',obj,'登记学校书面解释依据',before,data.reason,data.basis)
        if data.action!='activate' or obj.state!='DRAFT':raise HTTPException(409,'仅草稿可启用，修改时须新建版本')
        require_open_period(db,obj.period_id)
        st.duty(db,a,'coordinator',obj.created_by);st.require_evidence(db,'social_policy',ident)
        reference=(obj.data.get('interpretation_reference') or '').strip()
        if not reference or reference.startswith('系统推荐口径'):raise HTTPException(409,'须记录学校正式书面解释依据；系统推荐说明不能代替学校确认')
        if not all(obj.data.get(k) for k in ('calendar_start','calendar_end','calendar_reference')) or not obj.data['calendar_reference'].strip():
            raise HTTPException(409,'学校工作日历尚未确认，请在草稿详情补充校历开始、结束日期和学校工作日历依据后再启用')
        if db.scalar(select(SocialPolicy.id).where(SocialPolicy.period_id==obj.period_id,SocialPolicy.state=='ACTIVE',SocialPolicy.id!=ident).limit(1)):
            raise HTTPException(409,'本周期已有生效口径，请先完成关联办理并停用原版本，再启用新版本')
        obj.state='ACTIVE';return event(db,a,'social_policy',obj,'确认学校制度执行口径',before,data.reason,data.basis)
    return command(request,data.model_dump(),'rules.manage',apply)


@router.post('/claims')
def claim_create(data:ClaimIn,request:Request):
    def apply(db,a,s):
        if not a.user.staff_no:raise HTTPException(403,'积分必须由有工号的本人申报')
        project=db.get(SocialProject,data.project_id);policy=db.get(SocialPolicy,data.policy_id)
        if not project or not policy or policy.period_id!=data.period_id or policy.state=='VOID':raise HTTPException(422,'项目或规则周期无效，或口径已停用')
        if not any(t['teacher_id']==a.id for u in st.units(db,project.id) for t in u.data['teachers']):raise HTTPException(403,'没有本人参与明细')
        period=require_open_period(db,data.period_id)
        if project.closeout.get('closed_on') and not period.start_date<=date_from(project.closeout['closed_on'])<=period.end_date:
            raise HTTPException(422,'项目结项日期不在所选周期内，请选择包含结项日期的周期')
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
            trial=st.point_trial(db,obj);st.require_unblocked(trial)
            blockers=st.review_staff_blockers(db,SimpleNamespace(org_id=db.get(SocialProject,obj.project_id).org_id,data={'claim_id':obj.id,'teacher_id':obj.teacher_id,'created_by':obj.teacher_id}))
            if blockers:raise HTTPException(409,'审批职责尚未就绪：'+'；'.join(blockers))
            obj.snapshot=st.freeze(trial);obj.state='SUBMITTED'
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
        college(db,a,data.org_id);period=require_open_period(db,data.period_id);policy=db.get(SocialPolicy,data.policy_id)
        if not policy or policy.period_id!=data.period_id or policy.state=='VOID':raise HTTPException(422,'规则周期不匹配或口径已停用')
        values=serial(data.data.model_dump())
        if 'achievements' not in data.data.model_fields_set:values['achievements']=st.annual_achievements(db,data.org_id,period)
        obj=SocialAnnual(org_id=data.org_id,period_id=data.period_id,policy_id=policy.id,owner_id=a.id,data=values)
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


def school_registrar(a):
    if a.role.kind!='school':raise HTTPException(403,'学院、教研室和老师请走“申请培训课程”，由学校审批后入库')


COURSE_INFO_KEYS=('hours','teaching_mode','ideology','courseware','package','one_skill','target_groups')


def course_info(db,a,row,org_id):
    """学校直接登记的课程，五项资料（学时、教学方式、思政属性、主讲教师、课件审查）记在一条课程资料记录里，不改课程主表。"""
    dumped=row.model_dump(mode='json');values={k:dumped[k] for k in COURSE_INFO_KEYS if dumped.get(k) not in (None,'') and not (k in ('package','one_skill') and dumped[k] is False)}
    if not values and not (row.teacher or row.teacher_id):return None
    teacher=st.resolve_teacher(db,org_id,row.teacher,row.teacher_id) if (row.teacher or row.teacher_id) else None
    if row.teacher_id and not teacher:raise HTTPException(422,'主讲教师与学院或姓名不匹配')
    values.update(registered=True,course_code=row.code,project_code=row.project_code,source='registered',
                  teacher_id=teacher.id if teacher else None,teacher_name=teacher.name if teacher else row.teacher)
    obj=SocialResource(kind='course_apply',org_id=org_id,code='CI-'+row.code,name=row.name,state='ACTIVE',data=serial(values))
    db.add(obj);db.flush();workflow(db,a,'social_resource',obj.id,'登记培训课程资料',{},serial(obj),row.reason,'')
    return obj


@router.post('/courses')
def course_create(data:CourseIn,request:Request):
    def apply(db,a,s):
        school_registrar(a)
        projects=db.scalars(select(SocialProject).where(SocialProject.org_id.in_(a.org_ids))).all()
        project=next((p for p in projects if p.data['code']==data.project_code),None)
        if project is None:raise HTTPException(403,'须先建立本组织项目')
        if db.scalar(select(SocialResource.id).where(SocialResource.code=='CI-'+data.code)):raise HTTPException(409,'课程编号已有资料记录')
        obj=TrainingCourseMaster(code=data.code,name=data.name,project_code=data.project_code,source='学校人工登记')
        db.add(obj);db.flush();course_info(db,a,data,project.org_id)
        audit(db,a,'social_courses',obj.id,'登记培训课程',after=serial(obj),reason=data.reason);return obj
    return command(request,data.model_dump(mode='json'),'records.write',apply)


@router.post('/courses/import/{operation}')
def course_import(operation:str,data:CourseBatchIn,request:Request):
    def apply(db,a,s):
        school_registrar(a)
        projects=db.scalars(select(SocialProject).where(SocialProject.org_id.in_(a.org_ids))).all()
        allowed={p.data['code'] for p in projects};seen=set()
        for row in data.rows:
            if row.project_code not in allowed:raise HTTPException(403,'课程所属项目超出授权范围')
            if row.code in seen or db.scalar(select(TrainingCourseMaster.id).where(TrainingCourseMaster.code==row.code)):raise HTTPException(409,'课程编号重复，本批未导入')
            org_id=next(p.org_id for p in projects if p.data['code']==row.project_code)
            if row.teacher_id and not st.resolve_teacher(db,org_id,row.teacher,row.teacher_id):raise HTTPException(422,'课程教师与学院或姓名不匹配')
            seen.add(row.code)
            if db.scalar(select(SocialResource.id).where(SocialResource.code=='CI-'+row.code)):raise HTTPException(409,'课程编号已有资料记录，本批未导入')
        fingerprint=digest(serial([r.model_dump() for r in data.rows]))
        if operation=='preview':return {'count':len(data.rows),'videos':sum(1 for r in data.rows if r.video_minutes is not None),'preview_hash':fingerprint}
        if operation!='confirm' or data.preview_hash!=fingerprint:raise HTTPException(409,'须先预检未修改的课程清单')
        orgs={p.data['code']:p.org_id for p in projects};videos=0
        for row in data.rows:
            db.add(TrainingCourseMaster(code=row.code,name=row.name,project_code=row.project_code,source='超星学习通导出' if row.source=='chaoxing' else '学校批量登记'))
            course_info(db,a,row,orgs[row.project_code])
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
    return command(request,data.model_dump(mode='json'),'records.write',apply)


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
        if obj.project_id!=data.project_id:raise HTTPException(422,'补正不能更换项目')
        period=require_open_period(db,data.period_id);project=db.get(SocialProject,obj.project_id)
        if project.closeout.get('closed_on') and not period.start_date<=date_from(project.closeout['closed_on'])<=period.end_date:
            raise HTTPException(422,'项目结项日期不在所选周期内，请选择正确周期')
        policy=db.get(SocialPolicy,data.policy_id)
        if not policy or policy.period_id!=data.period_id or policy.state=='VOID':raise HTTPException(422,'规则周期不匹配或口径已停用')
        before=serial(obj);obj.period_id=data.period_id;obj.policy_id=data.policy_id;obj.data={**obj.data,'auxiliary':serial([v.model_dump() for v in data.auxiliary]),'recognition_form_reference':data.recognition_form_reference}
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
        if not policy or policy.period_id!=obj.period_id or policy.state=='VOID':raise HTTPException(422,'规则周期不匹配或口径已停用')
        before=serial(obj);values=serial(data.data.model_dump())
        if 'achievements' not in data.data.model_fields_set:values['achievements']=obj.data.get('achievements',[])
        obj.data=values;obj.policy_id=data.policy_id
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
    return command(request,data.model_dump(mode='json'),'records.write',apply)


@router.put('/resources/{ident}')
def resource_update(ident:str,data:ResourceUpdate,request:Request):
    def apply(db,a,s):
        obj=st.scoped(db,a,'social_resource',ident,write=True);check_version(obj,data.expected_version)
        if obj.kind not in {'base','achievement','course_resource'} or obj.data.get('auto') or obj.state=='ARCHIVED':raise HTTPException(409,'此项由原业务生成，请从原业务办理更正')
        if (obj.kind,obj.org_id,obj.code)!=(data.kind,data.org_id,data.code):raise HTTPException(422,'资源类型、所属学院和来源编号不能变更')
        before=serial(obj);values=resource_values(db,a,data)
        obj.name=data.name;obj.data={**obj.data,**values}
        return event(db,a,'social_resource',obj,'补正培训资源资料',before,data.reason,data.basis)
    return command(request,data.model_dump(mode='json'),'records.write',apply)


@router.get('/report-export/check')
def report_check(request:Request,start:str=Query('',max_length=10),end:str=Query('',max_length=10)):
    """导出上报表前的预检：区间内已备案及以后的项目，逐个列出缺的上报信息。"""
    from .. import social_report
    return read_operation(request,'records.read',lambda db,a,s:social_report.check(db,a,start,end))


@router.get('/report-export')
def report_export(request:Request,start:str=Query('',max_length=10),end:str=Query('',max_length=10)):
    from .. import social_report
    def load(db,a,s):
        a.require('records.read')
        sheets,result=social_report.export(db,a,start,end)
        audit(db,a,'social_report_export',result['start']+'~'+result['end'],'导出上报表',after={'scope':result['scope'],'projects':result['count'],'start':result['start'],'end':result['end']},reason='导出 1.2 立德树人与绩效数据')
        return sheets
    content=social_report.xlsx(read_operation(request,'export',load))
    return Response(content,media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':"attachment; filename=social-report.xlsx"})


@router.get('/ledger-summary')
def ledger_summary(request:Request):
    def load(db,a,s):
        return st.ledger_summary(db,a,st.today().year)
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
