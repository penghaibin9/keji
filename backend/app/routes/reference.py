"""Training master data and teacher participation views.

The existing training_records table remains the authoritative teaching/income
ledger.  teacher_participations is deliberately separate so a teacher attending
training is never mistaken for teaching that class or credited the class income.
"""
from types import SimpleNamespace
from fastapi import APIRouter,Request,HTTPException
from sqlalchemy import select,func
from ..core import *
from ..schemas import ParticipationIn,ParticipationUpdate,Reason,CreditReviewIn,CreditLevelIn,CxClaimIn,CxClaimDecisionIn
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
    if f.get('review') not in (None,'pending'):raise HTTPException(422,'review参数无效')
    def load(db,a,s):
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
        return {'items':items,'total':total,'page':p,'size':z,'years':years}
    return read_operation(request,'records.read',load)


from ..identities import stage_handler

CREDIT_DECISIONS={'approve':('APPROVED','认定计分'),'exclude':('EXCLUDED','认定不计分'),'reset':('PENDING','改回待认定')}

@router.post('/reference/teacher-credits/review')
def teacher_credit_review(data:CreditReviewIn,request:Request):
    """学校认定教务、超星同步来的授课：认定后才计学分学时和积分。

    认定人是系统管理员在组织页指定的“授课认定人”（皮老师、教务处等），以及学校层面有考核审核权限的账号；
    教研室、学院不认定。本人的课须回避。认定时记下当时的学分学时，重新拉取后有变化会自动回到待认定。
    """
    def apply(db,a,s):
        state,label=CREDIT_DECISIONS[data.decision]
        if data.decision=='exclude' and len(data.reason)<2:raise HTTPException(422,'不计分请写明原因')
        ids=list(dict.fromkeys(data.ids))
        rows={r.id:r for r in db.scalars(select(TeacherCourseTerm).where(TeacherCourseTerm.id.in_(ids)).with_for_update())}
        missing=[i for i in ids if i not in rows or not rows[i].active]
        if missing:raise HTTPException(409,'有 %d 门课已不在当前授课数据里，请刷新后重试'%len(missing))
        if not can_review_credits(db,a):raise HTTPException(403,'授课由学校指定的授课认定人认定，教研室、学院不办理认定')
        for r in rows.values():
            if a.user.staff_no and r.staff_no==a.user.staff_no:raise HTTPException(403,'须回避本人的课，请由其他授课认定人认定')
            if r.user_id is not None:check_conflicts(db,a,r.user_id)
        # 用和计分同一套口径算出每门课的学分学时（含课程总库补学分、同年重复只算一次）。
        staff={r.staff_no for r in rows.values()}
        peers=db.scalars(select(TeacherCourseTerm).where(TeacherCourseTerm.active.is_(True),TeacherCourseTerm.staff_no.in_(staff)))
        facts={d['id']:d for g in annual_teaching_credits(db,peers) for d in g['details']}
        reviews=credit_reviews(db,ids);at=utcnow().isoformat(timespec='seconds');done=0
        for i in ids:
            r=rows[i];d=facts.get(i)
            if d is None or not d['counted']:raise HTTPException(409,r.course_name+' 是重复课程，已按规则只算一次，不用认定')
            if data.decision=='approve' and d['credit'] is None:raise HTTPException(409,r.course_name+' 缺学分，请先请教务处在课程总库补齐学分再认定；确实不计的可以选“不计分”')
            basis={'staff_no':r.staff_no,'origin':r.origin,'course_code':r.course_code,'term_name':r.term_name,'credit':d['credit'],'hours':d['hours']}
            obj=reviews.get(i);before=serial(obj) if obj else {}
            entry={'decision':state,'by':a.id,'by_name':a.name,'at':at,'reason':data.reason,'basis':basis}
            if obj is None:
                user=db.get(User,r.user_id) if r.user_id else None
                obj=SocialResource(org_id=user.org_id if user else a.org.id,kind=CREDIT_REVIEW_KIND,code=credit_review_code(i),name=r.course_name[:160],state=state,data={})
                db.add(obj)
            elif obj.state==state and obj.data.get('basis')==basis:continue
            else:obj.version+=1
            obj.state=state
            obj.data={'course_term_id':i,'external_key':r.external_key,'staff_no':r.staff_no,'teacher_id':r.user_id,'basis':basis,
                      'reason':data.reason,'by':a.id,'by_name':a.name,'at':at,'history':[*(obj.data or {}).get('history',[]),entry][-50:]}
            db.flush();audit(db,a,'teacher_course',i,'授课认定：'+label,before=before,after=serial(obj),reason=data.reason or label)
            done+=1
        return {'updated':done,'unchanged':len(ids)-done,'decision':data.decision}
    # 授课认定人可能是普通教师身份，权限在 apply 里按“是否授课认定人”判断。
    return command(request,data.model_dump(),None,apply)


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
