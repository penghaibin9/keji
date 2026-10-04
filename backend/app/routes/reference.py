"""Training master data and teacher participation views.

The existing training_records table remains the authoritative teaching/income
ledger.  teacher_participations is deliberately separate so a teacher attending
training is never mistaken for teaching that class or credited the class income.
"""
from fastapi import APIRouter,Request,HTTPException
from sqlalchemy import select,func
from ..core import *
from ..schemas import ParticipationIn,ParticipationUpdate
from ..reference_data import TrainingProjectMaster,TrainingCourseMaster,TrainingClassMaster,TeacherParticipation,TeacherHrProfile,record_reference_errors
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
        return obj
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
    f,p,z=filters_from(request,{'q','project_code','active'})
    def load(db,a,s):
        q=select(TrainingCourseMaster)
        if f.get('q'):q=q.where(TrainingCourseMaster.name.contains(f['q'],autoescape=True)|TrainingCourseMaster.code.contains(f['q'],autoescape=True))
        if f.get('project_code'):q=q.where(TrainingCourseMaster.project_code==f['project_code'])
        if f.get('active'):
            if f['active'] not in {'true','false','1','0'}:raise HTTPException(422,'active参数无效')
            q=q.where(TrainingCourseMaster.active.is_(f['active'] in {'true','1'}))
        return page_result(db,q.order_by(TrainingCourseMaster.code),p,z)
    return read_operation(request,'records.read',load)

@router.get('/reference/teacher-hr')
def teacher_hr(request:Request):
    f,p,z=filters_from(request,{'q','org_code','active'})
    def load(db,a,s):
        a.require_admin();q=select(TeacherHrProfile)
        if f.get('q'):q=q.where(TeacherHrProfile.name.contains(f['q'],autoescape=True)|TeacherHrProfile.staff_no.contains(f['q'],autoescape=True))
        if f.get('org_code'):q=q.where(TeacherHrProfile.org_code==f['org_code'])
        if f.get('active'):
            if f['active'] not in {'true','false','1','0'}:raise HTTPException(422,'active参数无效')
            q=q.where(TeacherHrProfile.active.is_(f['active'] in {'true','1'}))
        return page_result(db,q.order_by(TeacherHrProfile.staff_no),p,z)
    return read_operation(request,'users.manage',load)


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
