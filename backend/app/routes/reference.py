"""Training master data and teacher participation views.

The existing training_records table remains the authoritative teaching/income
ledger.  teacher_participations is deliberately separate so a teacher attending
training is never mistaken for teaching that class or credited the class income.
"""
from types import SimpleNamespace
from fastapi import APIRouter,Request,HTTPException
from sqlalchemy import select,func
from ..core import *
from ..schemas import ParticipationIn,ParticipationUpdate,Reason,CreditReviewIn,CreditLevelIn,CxClaimIn,CxClaimDecisionIn,TeachingPointsIn
from pydantic import Field
from .. import code_tables as codes
from ..reference_data import TrainingProjectMaster,TrainingCourseMaster,TrainingClassMaster,TeacherParticipation,TeacherHrProfile,TeacherCourseTerm,SchoolCourse,annual_teaching_credits,UNKNOWN_YEAR,record_reference_errors,staff_roster,school_year_now,school_year_of,ROSTER_PROBLEMS,HR_PRIVATE_KEYS,credit_summary,source_status,CREDIT_REVIEW_KIND,credit_review_code,credit_reviews,can_review_credits,term_in_scope,year_in_scope,MIN_SCHOOL_YEAR
from ..social_models import SocialResource,SocialProject
from ..social_training import check_conflicts
from ..read_queries import authorized_org_descendants
from ..settings_catalog import business_dictionary,validate_manual_source

router=APIRouter(prefix='/api',tags=['培训主数据与教师参训'])

PART_FILTERS={'q','teacher_id','org_id','start','end','project_code','course_code'}

def _participation_query(db,a,f):
    q=select(TeacherParticipation).where(a.scope(TeacherParticipation.teacher_id),TeacherParticipation.state=='VALID')
    if f.get('teacher_id'):q=q.where(TeacherParticipation.teacher_id==f['teacher_id'])
    if f.get('org_id'):
        ids=authorized_org_descendants(db,a,f['org_id']);q=q.where(TeacherParticipation.teacher_id.in_(select(User.id).where(User.org_id.in_(ids)))
    )
    for key in ('project_code','course_code'):
        if f.get(key):q=q.where(getattr(TeacherParticipation,key)==f[key])
    for key,op in [('start',lambda d:TeacherParticipation.event_date>=d),('end',lambda d:TeacherParticipation.event_date<=d)]:
        if f.get(key):
            try:d=date.fromisoformat(f[key])
            except ValueError:raise HTTPException(422,'日期格式应为 YYYY-MM-DD') from None
            q=q.where(op(d))
    if f.get('q'):
        word=f['q'];q=q.where(TeacherParticipation.project.contains(word,autoescape=True)|TeacherParticipation.course.contains(word,autoescape=True)|TeacherParticipation.external_key.contains(word,autoescape=True)|TeacherParticipation.teacher_id.in_(select(User.id).where(User.name.contains(word,autoescape=True)|User.staff_no.contains(word,autoescape=True))))
    return q

@router.get('/participations')
def participation_list(request:Request):
    f,p,z=filters_from(request,PART_FILTERS)
    return read_operation(request,'records.read',lambda db,a,s:page_result(db,_participation_query(db,a,f).order_by(TeacherParticipation.event_date.desc(),TeacherParticipation.id),p,z))

@router.get('/participations/{ident}')
def participation_detail(ident:str,request:Request):
    def load(db,a,s):
        obj=db.get(TeacherParticipation,ident)
        if not obj or obj.teacher_id not in a.teacher_ids:raise HTTPException(404,'参训记录不存在')
        return {**serial(obj),'events':db.scalars(select(WorkflowEvent).where(WorkflowEvent.object_type=='participation',WorkflowEvent.object_id==ident).order_by(WorkflowEvent.created_at,WorkflowEvent.id)).all()}
    return read_operation(request,'records.read',load)

@router.post('/participations')
def participation_create(data:ParticipationIn,request:Request):
    def apply(db,a,s):
        a.check_teacher(db,data.teacher_id,active=True)
        validate_manual_source(db,data.source)
        if db.scalar(select(TeacherParticipation.id).where(TeacherParticipation.external_key==data.external_key)):raise HTTPException(409,'来源唯一编号重复')
        errors=record_reference_errors(db,data.model_dump())
        if errors:raise HTTPException(409,'；'.join(errors))
        obj=TeacherParticipation(**data.model_dump(exclude={'reason','basis'}));db.add(obj);db.flush()
        workflow(db,a,'participation',obj.id,'新增教师参训记录',{},serial(obj),data.reason,data.basis);return obj
    return command(request,data.model_dump(),'records.write',apply)

@router.put('/participations/{ident}')
def participation_update(ident:str,data:ParticipationUpdate,request:Request):
    def apply(db,a,s):
        obj=db.get(TeacherParticipation,ident)
        if not obj or obj.teacher_id not in a.teacher_ids:raise HTTPException(404,'参训记录不存在')
        check_version(obj,data.expected_version)
        if obj.external_key!=data.external_key or obj.teacher_id!=data.teacher_id:raise HTTPException(422,'来源编号和教师归属不可直接更换')
        if data.source!=obj.source:raise HTTPException(422,'原始数据来源不可直接更换；更正内容与依据将另外留痕')
        a.check_teacher(db,data.teacher_id,active=True)
        errors=record_reference_errors(db,data.model_dump())
        if errors:raise HTTPException(409,'；'.join(errors))
        before=serial(obj)
        for k,v in data.model_dump(exclude={'reason','basis','expected_version'}).items():setattr(obj,k,v)
        obj.version+=1;workflow(db,a,'participation',obj.id,'更正教师参训记录',before,serial(obj),data.reason,data.basis);return obj
    return command(request,data.model_dump(),'records.write',apply)

@router.get('/teacher-activity-summary')
def teacher_activity_summary(request:Request):
    def load(db,a,s):
        teacher_id=a.id if a.role.kind=='teacher' else request.query_params.get('teacher_id')
        if not teacher_id:raise HTTPException(422,'请选择教师')
        a.check_teacher(db,teacher_id)
        teaching=db.execute(select(func.count(TrainingRecord.id),func.coalesce(func.sum(TrainingRecord.hours),0)).where(TrainingRecord.teacher_id==teacher_id,TrainingRecord.state=='VALID')).one()
        learning=db.execute(select(func.count(TeacherParticipation.id),func.coalesce(func.sum(TeacherParticipation.hours),0)).where(TeacherParticipation.teacher_id==teacher_id,TeacherParticipation.state=='VALID')).one()
        recent_teaching=db.scalars(select(TrainingRecord).where(TrainingRecord.teacher_id==teacher_id,TrainingRecord.state=='VALID').order_by(TrainingRecord.event_date.desc(),TrainingRecord.id).limit(5)).all()
        recent_learning=db.scalars(select(TeacherParticipation).where(TeacherParticipation.teacher_id==teacher_id,TeacherParticipation.state=='VALID').order_by(TeacherParticipation.event_date.desc(),TeacherParticipation.id).limit(5)).all()
        return {'teacher_id':teacher_id,'teaching':{'records':teaching[0],'hours':teaching[1],'recent':recent_teaching},'participation':{'records':learning[0],'hours':learning[1],'recent':recent_learning}}
    return read_operation(request,'records.read',load)

@router.get('/reference/projects')
def projects(request:Request):
    f,p,z=filters_from(request,{'q','active'})
    def load(db,a,s):
        q=select(TrainingProjectMaster)
        if f.get('q'):q=q.where(TrainingProjectMaster.name.contains(f['q'],autoescape=True)|TrainingProjectMaster.code.contains(f['q'],autoescape=True))
        if f.get('active'):
            if f['active'] not in {'true','false','1','0'}:raise HTTPException(422,'active参数无效')
            q=q.where(TrainingProjectMaster.active.is_(f['active'] in {'true','1'}))
        return page_result(db,q.order_by(TrainingProjectMaster.code),p,z)
    return read_operation(request,'records.read',load)

@router.get('/reference/courses')
def courses(request:Request):
    f,p,z=filters_from(request,{'q','project_code','active','resource_org_id'})
    def load(db,a,s):
        q=select(TrainingCourseMaster)
        if f.get('resource_org_id'):
            org_id=f['resource_org_id'];authorized_org_descendants(db,a,org_id)
            if db.get(Org,org_id).kind!='college':raise HTTPException(403,'课程资源须选择授权学院')
            q=q.where(TrainingCourseMaster.project_code.in_(select(SocialProject.data['code'].as_string()).where(SocialProject.org_id==org_id)))
        if f.get('q'):q=q.where(TrainingCourseMaster.name.contains(f['q'],autoescape=True)|TrainingCourseMaster.code.contains(f['q'],autoescape=True))
        if f.get('project_code'):q=q.where(TrainingCourseMaster.project_code==f['project_code'])
        if f.get('active'):
            if f['active'] not in {'true','false','1','0'}:raise HTTPException(422,'active参数无效')
            q=q.where(TrainingCourseMaster.active.is_(f['active'] in {'true','1'}))
        return page_result(db,q.order_by(TrainingCourseMaster.code),p,z)
    return read_operation(request,'records.read',load)

@router.get('/reference/teacher-hr')
def teacher_hr(request:Request):
    f,p,z=filters_from(request,{'q','org_code','active','unmatched'})
    if f.get('unmatched') not in (None,'true'):raise HTTPException(422,'unmatched参数无效')
    def load(db,a,s):
        a.require_admin();q=select(TeacherHrProfile)
        # 人事表有、本系统没账号: the list an admin works through to create the missing accounts.
        if f.get('unmatched'):q=q.where(TeacherHrProfile.user_id.is_(None))
        if f.get('q'):q=q.where(TeacherHrProfile.name.contains(f['q'],autoescape=True)|TeacherHrProfile.staff_no.contains(f['q'],autoescape=True))
        if f.get('org_code'):q=q.where(TeacherHrProfile.org_code==f['org_code'])
        if f.get('active'):
            if f['active'] not in {'true','false','1','0'}:raise HTTPException(422,'active参数无效')
            q=q.where(TeacherHrProfile.active.is_(f['active'] in {'true','1'}))
        return page_result(db,q.order_by(TeacherHrProfile.staff_no),p,z)
    return read_operation(request,'users.manage',load)


# Managers see gender/education/degree only when the school turns this custom parameter on.
HR_EDU_PARAM='param:hr_managers_see_education'

def _roster_scope(db,a,f):
    q=select(TeacherHrProfile)
    # Staff not yet matched to a local account have no organisation here; only the school sees them.
    q=q.where(a.scope(TeacherHrProfile.user_id)|TeacherHrProfile.user_id.is_(None)) if a.role.kind=='school' else q.where(a.scope(TeacherHrProfile.user_id))
    if f.get('org_id'):
        ids=authorized_org_descendants(db,a,f['org_id']);q=q.where(TeacherHrProfile.user_id.in_(select(User.id).where(User.org_id.in_(ids))))
    if f.get('active'):
        if f['active'] not in {'true','false'}:raise HTTPException(422,'active参数无效')
        q=q.where(TeacherHrProfile.active.is_(f['active']=='true'))
    if f.get('q'):q=q.where(TeacherHrProfile.name.contains(f['q'],autoescape=True)|TeacherHrProfile.staff_no.contains(f['q'],autoescape=True))
    return q.order_by(TeacherHrProfile.staff_no)

def _private_ok(db,a):
    if a.role.kind in {'teacher','school'}:return True  # a teacher only ever gets their own row
    flag=db.get(Setting,HR_EDU_PARAM)
    return bool(flag and isinstance(flag.value,dict) and flag.value.get('value') is True)

def _school_year(f):
    year=f.get('school_year') or school_year_now()
    if school_year_of(year)!=year:raise HTTPException(422,'学年格式应为 2025-2026')
    if not year_in_scope(year):raise HTTPException(422,'只统计 '+MIN_SCHOOL_YEAR+' 学年及以后')
    return year

@router.get('/reference/staff-roster')
def staff_roster_view(request:Request):
    """教职工名册 within the viewer's scope: school fields, account match, this year's credits, problems."""
    f,p,z=filters_from(request,{'q','org_id','active','problem','school_year'})
    if f.get('problem') not in (None,'true','false'):raise HTTPException(422,'problem参数无效')
    def load(db,a,s):
        year=_school_year(f);private=_private_ok(db,a);q=_roster_scope(db,a,f)
        if f.get('problem')=='true':
            rows=[r for r in staff_roster(db,db.scalars(q),school_year=year,private=private) if r['problems']]
            total=len(rows);rows=rows[(p-1)*z:p*z]
        else:
            total=db.scalar(select(func.count()).select_from(q.order_by(None).subquery()))
            rows=staff_roster(db,db.scalars(q.offset((p-1)*z).limit(z)),school_year=year,private=private)
        synced=db.scalar(select(func.max(TeacherHrProfile.created_at)))
        return {'items':rows,'total':total,'page':p,'size':z,'school_year':year,'private_fields':private,
                'problem_labels':ROSTER_PROBLEMS,'ever_synced':synced is not None}
    return read_operation(request,'organization.read',load)

# 超星课程库映射进 extra 的字段（数据中台_适配器配置 字段映射建议.online_course）。
ONLINE_EXTRA_KEYS=('cover_url','course_url','group_name','chapters','course_type','course_source','archived','team_names','team_staff_nos',
    'jw_course_code','nature','course_owner','major','score','period_text','created_at_source','edited_at_source')

@router.get('/reference/staff-roster/{staff_no}')
def staff_roster_detail(staff_no:str,request:Request):
    """One teacher: roster row, every school year's credits and their 超星 courses."""
    def load(db,a,s):
        profile=db.scalar(_roster_scope(db,a,{}).where(TeacherHrProfile.staff_no==staff_no))
        if profile is None:raise HTTPException(404,'教师不存在或不在授权范围')
        row=staff_roster(db,[profile],school_year=school_year_now(),private=_private_ok(db,a))[0]
        terms=db.scalars(select(TeacherCourseTerm).where(TeacherCourseTerm.staff_no==staff_no,TeacherCourseTerm.active.is_(True))).all()
        years=[{k:g[k] for k in ('school_year','jw_credit','cx_credit','total_credit','courses','missing_credit','pending_credit','pending_courses','excluded_courses')} for g in annual_teaching_credits(db,terms)]
        terms=[t for t in terms if term_in_scope(t.term_name)]
        online=[{'course_code':t.course_code,'course_name':t.course_name,'term_name':t.term_name,'credit':t.credit,'hours':t.hours,
                 **{k:(t.extra or {}).get(k) for k in ONLINE_EXTRA_KEYS},
                 'description':str((t.extra or {}).get('description') or '')[:2000]}
                for t in sorted(terms,key=lambda t:t.term_name,reverse=True) if t.origin=='CX']
        return {'staff':row,'years':years,'online_courses':online}
    return read_operation(request,'organization.read',load)


@router.get('/reference/credit-summary')
def credit_summary_view(request:Request):
    """人均授课学分 within the viewer's scope for one school year, with one row per college."""
    f,_,_=filters_from(request,{'org_id','school_year'})
    def load(db,a,s):
        if a.role.kind=='teacher':raise HTTPException(403,'人均学分仅管理角色查看')
        year=_school_year(f)
        return credit_summary(db,db.scalars(_roster_scope(db,a,f)),school_year=year)
    return read_operation(request,'organization.read',load)

@router.get('/reference/source-status')
def source_status_view(request:Request):
    """对接与同步: rows held per data-hub table and how many need follow-up."""
    f,_,_=filters_from(request,{'school_year'})
    def load(db,a,s):
        if a.role.kind!='school':raise HTTPException(403,'仅学校管理角色查看全校接口数据')
        year=_school_year(f)
        return {'school_year':year,'items':source_status(db,school_year=year)}
    return read_operation(request,'portal.read',load)

def old_terms(db):
    """Term names of active teaching rows before the first counted school year (hidden, not deleted)."""
    return sorted(t for t in db.scalars(select(TeacherCourseTerm.term_name).where(TeacherCourseTerm.active.is_(True)).distinct()) if not term_in_scope(t))

@router.get('/reference/teacher-courses')
def teacher_courses(request:Request):
    """Teacher-course-term rows from the 教务 schedule (JW) and 超星 course library (CX)."""
    f,p,z=filters_from(request,{'q','origin','term_name','staff_no'})
    def load(db,a,s):
        q=select(TeacherCourseTerm).where(TeacherCourseTerm.active.is_(True))
        # Rows whose staff number has no local account yet are visible to the school admin only.
        admin=a.role.kind=='school' and a.user.is_admin
        q=q.where(a.scope(TeacherCourseTerm.user_id)|TeacherCourseTerm.user_id.is_(None)) if admin else q.where(a.scope(TeacherCourseTerm.user_id))
        if f.get('origin'):
            if f['origin'] not in {'JW','CX'}:raise HTTPException(422,'origin参数无效')
            q=q.where(TeacherCourseTerm.origin==f['origin'])
        for key in ('term_name','staff_no'):
            if f.get(key):q=q.where(getattr(TeacherCourseTerm,key)==f[key])
        if f.get('q'):
            word=f['q'];q=q.where(TeacherCourseTerm.course_name.contains(word,autoescape=True)|TeacherCourseTerm.course_code.contains(word,autoescape=True)|TeacherCourseTerm.teacher_name.contains(word,autoescape=True)|TeacherCourseTerm.staff_no.contains(word,autoescape=True))
        q=q.where(TeacherCourseTerm.term_name.not_in(old_terms(db) or ['']))
        return page_result(db,q.order_by(TeacherCourseTerm.term_name.desc(),TeacherCourseTerm.staff_no,TeacherCourseTerm.course_code),p,z)
    return read_operation(request,'records.read',load)


@router.get('/reference/cx-unmatched.xlsx')
def cx_unmatched_xlsx(request:Request):
    """超星建课人还没对上工号的名单 + 登录名对照核对，学校管理员下载后催老师改超星登录名。"""
    from urllib.parse import quote
    from fastapi.responses import Response
    from ..excel_io import sheets_to_xlsx
    from ..reference_data import cx_unmatched_report
    with request.app.state.sessions.begin() as db:
        a,s=current_actor(db,request);a.require('records.read')
        if a.role.kind!='school' or not a.user.is_admin:raise HTTPException(403,'仅学校管理员下载')
        unmatched,checks=cx_unmatched_report(db)
        data=sheets_to_xlsx([('还没对上工号',['超星登录名','超星里的姓名','课程数','最近学期','课程举例','怎么处理'],unmatched),
            ('登录名对照核对',['超星登录名','对照到的工号','教职工表姓名','超星里的姓名','核对结果'],checks)])
        audit(db,a,'teacher_course','cx-unmatched','下载超星未对应工号名单',after={'unmatched':len(unmatched),'aliases':len(checks)},reason='催办超星登录名改工号')
    name=quote('超星未对应工号名单.xlsx')
    return Response(data,media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':f"attachment; filename*=UTF-8''{name}",'X-Content-Type-Options':'nosniff'})


@router.get('/reference/cx-claims/mine')
def cx_claims_mine(request:Request):
    """本人超星认领：已认领的登录名，和超星姓名与本人一致、还没对上工号的登录名。"""
    from ..cx_claims import my_claims
    return read_operation(request,'records.read',lambda db,a,s:my_claims(db,a))

@router.post('/reference/cx-claims')
def cx_claim_submit(data:CxClaimIn,request:Request):
    from ..cx_claims import submit_claim
    return command(request,data.model_dump(),'records.read',lambda db,a,s:submit_claim(db,a,data.login,data.note))

@router.get('/reference/cx-claims')
def cx_claims_list(request:Request):
    from ..cx_claims import list_claims
    f,_,_=filters_from(request,{'state'})
    if f.get('state') not in (None,'PENDING','APPROVED','REJECTED','REVOKED'):raise HTTPException(422,'state参数无效')
    return read_operation(request,'records.read',lambda db,a,s:list_claims(db,a,f.get('state')))

@router.post('/reference/cx-claims/decide')
def cx_claim_decide(data:CxClaimDecisionIn,request:Request):
    from ..cx_claims import decide_claim
    if data.decision!='approve' and len(data.reason)<2:raise HTTPException(422,'驳回或撤销请写明原因')
    return command(request,data.model_dump(),'records.read',lambda db,a,s:decide_claim(db,a,data.login,data.staff_no,data.decision,data.reason or '管理员确认老师认领'))


@router.get('/reference/school-courses')
def school_courses(request:Request):
    """教务课程总库: official credit and hours per course code."""
    f,p,z=filters_from(request,{'q','code','missing_credit'})
    if f.get('missing_credit') not in (None,'true'):raise HTTPException(422,'missing_credit参数无效')
    def load(db,a,s):
        q=select(SchoolCourse).where(SchoolCourse.active.is_(True))
        if f.get('missing_credit'):q=q.where(SchoolCourse.credit.is_(None))
        if f.get('code'):q=q.where(SchoolCourse.code==f['code'])
        if f.get('q'):q=q.where(SchoolCourse.name.contains(f['q'],autoescape=True)|SchoolCourse.code.contains(f['q'],autoescape=True))
        return page_result(db,q.order_by(SchoolCourse.code,SchoolCourse.course_version.desc()),p,z)
    return read_operation(request,'records.read',load)


@router.get('/reference/teacher-credits')
def teacher_credits(request:Request):
    """Per teacher per school year: 教务 + 超星 course credits of both terms added up."""
    f,p,z=filters_from(request,{'q','school_year','staff_no','problem','detail','org_id','review'})
    for key in ('problem','detail'):
        if f.get(key) not in (None,'true','false'):raise HTTPException(422,key+'参数无效')
    if f.get('review') not in (None,'pending','mine'):raise HTTPException(422,'review参数无效')
    def load(db,a,s):
        if f.get('review')=='mine':return _waiting_mine(db,a,f,p,z)
        q=select(TeacherCourseTerm).where(TeacherCourseTerm.active.is_(True))
        # 授课认定人要认定全校的课（包括工号还没对应账号的），不受本人身份的数据范围限制。
        reviewer=can_review_credits(db,a)
        if not reviewer:
            admin=a.role.kind=='school' and a.user.is_admin
            q=q.where(a.scope(TeacherCourseTerm.user_id)|TeacherCourseTerm.user_id.is_(None)) if admin else q.where(a.scope(TeacherCourseTerm.user_id))
        if f.get('staff_no'):q=q.where(TeacherCourseTerm.staff_no==f['staff_no'])
        if f.get('org_id'):
            # 认定人按全校组织筛选；其他人只能筛本人授权范围内的组织。
            scope_of=SimpleNamespace(org_ids=set(db.scalars(select(Org.id)))) if reviewer else a
            ids=authorized_org_descendants(db,scope_of,f['org_id'])
            q=q.where(TeacherCourseTerm.user_id.in_(select(User.id).where(User.org_id.in_(ids))))
        if f.get('q'):q=q.where(TeacherCourseTerm.teacher_name.contains(f['q'],autoescape=True)|TeacherCourseTerm.staff_no.contains(f['q'],autoescape=True))
        problem=f.get('problem')=='true';detail=f.get('detail')=='true';pending=f.get('review')=='pending'
        def wanted(x):
            # “需核对”和“待认定”两个筛选同时勾选时取交集。
            return (not problem or bool(x['missing_credit'] or not x['user_id'] or not x['in_staff_table'])) and (not pending or x['pending_courses']>0)
        pairs=[(staff,term) for staff,term in db.execute(q.with_only_columns(TeacherCourseTerm.staff_no,TeacherCourseTerm.term_name).distinct()) if term_in_scope(term)]
        groups={(staff,school_year_of(term) or UNKNOWN_YEAR) for staff,term in pairs}
        years=sorted({year for staff,year in groups},key=lambda y:(y!=UNKNOWN_YEAR,y),reverse=True)
        selected={key for key in groups if not f.get('school_year') or key[1]==f['school_year']}
        if problem or pending:
            # shortcut: totals still inspect scoped teachers; batches bound course memory until an indexed summary is justified.
            numbers=sorted({staff for staff,year in selected});items=[]
            terms={term for staff,term in pairs if (school_year_of(term) or UNKNOWN_YEAR)==f['school_year']} if f.get('school_year') else None
            for offset in range(0,len(numbers),64):
                batch=q.where(TeacherCourseTerm.staff_no.in_(numbers[offset:offset+64]))
                if terms is not None:batch=batch.where(TeacherCourseTerm.term_name.in_(terms))
                items.extend(x for x in annual_teaching_credits(db,db.scalars(batch),include_details=False) if wanted(x))
        else:items=[{'staff_no':staff,'school_year':year} for staff,year in selected]
        items.sort(key=lambda x:x['staff_no'])
        items.sort(key=lambda x:(x['school_year']!=UNKNOWN_YEAR,x['school_year']),reverse=True)
        total=len(items);items=items[(p-1)*z:p*z]
        if items and (not (problem or pending) or detail):
            keys={(x['staff_no'],x['school_year']) for x in items}
            terms={term for staff,term in pairs if (staff,school_year_of(term) or UNKNOWN_YEAR) in keys}
            rows=db.scalars(q.where(TeacherCourseTerm.staff_no.in_({staff for staff,year in keys}),TeacherCourseTerm.term_name.in_(terms)))
            items=annual_teaching_credits(db,(r for r in rows if (r.staff_no,school_year_of(r.term_name) or UNKNOWN_YEAR) in keys),include_details=detail)
            if detail:
                from ..teaching_review import annotate
                items=[annotate(db,a,g) for g in items]
        return {'items':items,'total':total,'page':p,'size':z,'years':years}
    return read_operation(request,'records.read',load)


from ..identities import stage_handler

def _waiting_mine(db,a,f,p,z):
    """“待我办理”：本人这一级要办的老师学年（教研室、学院看本组织，学校看到学校这一级）。"""
    from ..reference_data import all_credit_groups
    from ..teaching_review import waiting_for
    groups=waiting_for(db,a,all_credit_groups(db))
    years=sorted({g['school_year'] for g in groups},key=lambda y:(y!=UNKNOWN_YEAR,y),reverse=True)
    if f.get('school_year'):groups=[g for g in groups if g['school_year']==f['school_year']]
    if f.get('staff_no'):groups=[g for g in groups if g['staff_no']==f['staff_no']]
    if f.get('q'):groups=[g for g in groups if f['q'] in (g.get('teacher_name') or '') or f['q'] in g['staff_no']]
    if f.get('org_id'):
        scope_of=SimpleNamespace(org_ids=set(db.scalars(select(Org.id)))) if can_review_credits(db,a) else a
        ids=authorized_org_descendants(db,scope_of,f['org_id'])
        users=set(db.scalars(select(User.id).where(User.org_id.in_(ids))))
        groups=[g for g in groups if g.get('user_id') in users]
    groups=sorted(groups,key=lambda g:g['staff_no'])
    groups.sort(key=lambda g:(g['school_year']!=UNKNOWN_YEAR,g['school_year']),reverse=True)
    return {'items':groups[(p-1)*z:p*z],'total':len(groups),'page':p,'size':z,'years':years}


@router.post('/reference/teacher-credits/review')
def teacher_credit_review(data:CreditReviewIn,request:Request):
    """授课认定三级办理：教研室审核 → 学院审批 → 学校认定，每一级可改积分、写审批意见。

    规则见 app/teaching_review.py：本人的课回避，教研室缺负责人由学院办、学院缺院长由学校办，
    院长指定的经办人能办学院这一级；学校认定后积分入账、课程进入老师的培训课程库。
    """
    from ..teaching_review import apply_review
    # 教研室、学院负责人和授课认定人可能是不同身份，权限在 apply_review 里按课程当前在哪一级判断。
    return command(request,data.model_dump(),None,lambda db,a,s:apply_review(db,a,data))


@router.get('/reference/teacher-credits/course/{course_id}')
def teacher_credit_course(course_id:str,request:Request):
    """一门课的认定详情：课程内容、认定条件、各级办理记录（谁、何时、积分怎么改、审批意见）。"""
    def load(db,a,s):
        from ..teaching_review import annotate
        r=db.get(TeacherCourseTerm,course_id)
        if r is None or not r.active:raise HTTPException(404,'课程不存在或已不在授课数据里')
        if not can_review_credits(db,a) and not (r.user_id and db.scalar(select(User.id).where(User.id==r.user_id,a.scope(User.id)))):
            raise HTTPException(403,'这门课不在你的授权范围')
        year=school_year_of(r.term_name) or UNKNOWN_YEAR
        peers=db.scalars(select(TeacherCourseTerm).where(TeacherCourseTerm.active.is_(True),TeacherCourseTerm.staff_no==r.staff_no))
        group=next((g for g in annual_teaching_credits(db,peers) if g['school_year']==year),None)
        d=next((x for x in (group or {}).get('details',[]) if x['id']==r.id),None)
        if d is None:raise HTTPException(404,'这门课不在计分学年范围内')
        annotate(db,a,{**group,'details':[d]})
        extra=r.extra or {}
        content={'course_code':r.course_code,'course_name':r.course_name,'term_name':r.term_name,'origin':r.origin,'credit':d['credit'],'hours':d['hours']}
        if r.origin=='CX':
            content.update({k:extra.get(k) for k in ONLINE_EXTRA_KEYS},description=str(extra.get('description') or '')[:4000])
        else:
            sc=db.scalar(select(SchoolCourse).where(SchoolCourse.code==r.course_code,SchoolCourse.active.is_(True)).order_by(SchoolCourse.course_version.desc()).limit(1))
            if sc is not None:content.update(dept=sc.dept,weekly_hours=sc.weekly_hours,course_version=sc.course_version,**{k:v for k,v in (sc.extra or {}).items() if k in ('nature','category','attribute','group','teach_mode','exam_mode','manage_dept')})
        has_hr=db.scalar(select(TeacherHrProfile.id).where(TeacherHrProfile.staff_no==r.staff_no,TeacherHrProfile.active.is_(True))) is not None
        mine=bool(a.user.staff_no and r.staff_no==a.user.staff_no) or r.user_id==a.id
        conditions=[{'label':'在学校教职工表里','ok':has_hr,'note':'' if has_hr else '不在教职工表的工号按学校规定不计积分'},
                    {'label':'有本地教师账号','ok':bool(r.user_id),'note':'' if r.user_id else '没有账号，不知道所在教研室，直接由学校认定'},
                    {'label':'有学时','ok':d['hours'] is not None,'note':'' if d['hours'] is not None else '缺学时算不出建议积分，审核时须手工填积分'},
                    {'label':'有学分','ok':d['credit'] is not None,'note':'' if d['credit'] is not None else '课程总库里没有学分（不影响按学时计分）'},
                    {'label':'不是重复课','ok':bool(d['counted']),'note':'' if d['counted'] else '同一学年重复，已按规则只算一次'},
                    {'label':'不是本人的课','ok':not mine,'note':'' if not mine else '须回避，由其他人办理'}]
        review=credit_reviews(db,[r.id]).get(r.id)
        history=list((review.data or {}).get('history') or []) if review else []
        return {'course':d,'school_year':year,'teacher_name':r.teacher_name,'staff_no':r.staff_no,'content':content,'conditions':conditions,'history':history}
    return read_operation(request,'records.read',load)


@router.get('/reference/teacher-credits/points-rule')
def teaching_points_rule(request:Request):
    """授课认定的学时积分口径：每学时折算几分（没设按 1 学时 1 分）。"""
    def load(db,a,s):
        from ..reference_data import teaching_point_rates
        return {k:str(v) for k,v in teaching_point_rates(db).items()}
    return read_operation(request,'records.read',load)


@router.put('/reference/teacher-credits/points-rule')
def teaching_points_rule_save(data:TeachingPointsIn,request:Request):
    """学校系统管理员设置每学时积分；只影响还没认定计分的课（已入账的不变）。"""
    def apply(db,a,s):
        from ..reference_data import TEACHING_POINTS_KEY,teaching_point_rates
        a.require_admin()
        before={k:str(v) for k,v in teaching_point_rates(db).items()}
        value={'JW':str(data.JW),'CX':str(data.CX)}
        row=db.scalar(select(Setting).where(Setting.key==TEACHING_POINTS_KEY).with_for_update())
        if row is None:db.add(Setting(key=TEACHING_POINTS_KEY,value=value,version=1))
        else:row.value=value;row.version+=1
        db.flush();audit(db,a,'teacher_course','points-rule','授课认定：设置每学时积分',before=before,after=value,reason=data.reason or '设置每学时积分')
        return value
    return command(request,data.model_dump(),None,apply)


@router.get('/reference/teacher-credits/library')
def teaching_library(request:Request):
    """本人培训课程库里“授课认定入库”的课（学校已认定计分的教务、超星课）。"""
    def load(db,a,s):
        from ..teaching_review import library
        return {'items':library(db,a.user)}
    return read_operation(request,'portal.read',load)


@router.post('/reference/teacher-credits/level')
def teacher_credit_level(data:CreditLevelIn,request:Request):
    """给课程打国家级、省级、校级标签。标签跟着课程（来源 + 课程号）走，同一门课所有老师一起生效。"""
    def apply(db,a,s):
        from ..reference_data import course_levels,save_course_levels,course_level_key,COURSE_LEVELS
        if not can_review_credits(db,a):raise HTTPException(403,'课程级别由授课认定人设置')
        ids=list(dict.fromkeys(data.ids))
        rows=list(db.scalars(select(TeacherCourseTerm).where(TeacherCourseTerm.id.in_(ids),TeacherCourseTerm.active.is_(True))))
        if len(rows)!=len(ids):raise HTTPException(409,'有课程已不在当前授课数据里，请刷新后重试')
        items=course_levels(db,lock=True);changed=[]
        for key in dict.fromkeys(course_level_key(r.origin,r.course_code) for r in rows):
            old=items.get(key)
            if (old or '')==data.level:continue
            if data.level:items[key]=data.level
            else:items.pop(key,None)
            changed.append({'course':key,'before':COURSE_LEVELS.get(old,''),'after':COURSE_LEVELS.get(data.level,'')})
        if changed:
            save_course_levels(db,items)
            label=COURSE_LEVELS.get(data.level,'清除级别')
            audit(db,a,'teacher_course','course-level','课程级别：'+label,after={'courses':changed[:200]},reason=data.reason or label)
        return {'updated':len(changed),'level':data.level}
    return command(request,data.model_dump(),None,apply)


@router.get('/reference/classes')
def classes(request:Request):
    f,p,z=filters_from(request,{'q','project_code','course_code'})
    def load(db,a,s):
        q=select(TrainingClassMaster).where(TrainingClassMaster.active.is_(True))
        for key in ('project_code','course_code'):
            if f.get(key):q=q.where(getattr(TrainingClassMaster,key)==f[key])
        if f.get('q'):q=q.where(TrainingClassMaster.name.contains(f['q'],autoescape=True)|TrainingClassMaster.code.contains(f['q'],autoescape=True))
        return page_result(db,q.order_by(TrainingClassMaster.code),p,z)
    return read_operation(request,'records.read',load)


class CodeTableIn(Reason):
    text: str = Field(min_length=1,max_length=200000)

@router.get('/reference/code-tables')
def code_tables_view(request:Request):
    """学校码表：页面用它把人事和课程里的代码翻成中文。"""
    def load(db,a,s):
        return {'types':codes.TYPES,'tables':codes.tables(db)}
    return read_operation(request,'portal.read',load)

@router.put('/reference/code-tables/{code_type}')
def code_table_import(code_type:str,data:CodeTableIn,request:Request):
    """Replace one code table with rows pasted from the school's Excel (代码、名称[、是否在职])."""
    def apply(db,a,s):
        a.require_admin()
        rows=codes.parse_rows(code_type,data.text)
        row=db.get(Setting,codes.SETTING_KEY)
        if row is None:row=Setting(key=codes.SETTING_KEY,value={'tables':{}},version=0);db.add(row)
        value=dict(row.value or {});all_tables=dict(value.get('tables') or {})
        before=all_tables.get(code_type)
        all_tables[code_type]=rows;row.value={**value,'tables':all_tables};row.version=(row.version or 0)+1
        audit(db,a,'settings',codes.SETTING_KEY,'导入学校码表：'+codes.TYPES[code_type],{'type':code_type,'rows':len(before or {})},{'type':code_type,'rows':len(rows)},data.reason)
        return {'type':code_type,'rows':len(rows),'version':row.version}
    return command(request,data.model_dump(),'settings.manage',apply)
