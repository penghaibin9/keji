"""老师发起的申请：社会培训课申报、培训课程申请、培训基地申请。审批规则见 approvals.py，业务口径见 applications.py。"""
from fastapi import APIRouter, Request, HTTPException
from sqlalchemy import select
from ..core import command, read_operation, serial, workflow, check_version
from ..reference_data import TeacherCourseTerm, TrainingCourseMaster, term_in_scope
from ..social_models import SocialResource, SocialProject
from ..social_schemas import CourseApplyIn, BaseApplyIn, ApplicationAction
from .. import approvals as ap
from .. import applications as apps
from .. import message_push

router = APIRouter(prefix='/api/applications', tags=['老师申请与审批'])


def record(db, a, obj, action, before, reason, handling, basis=''):
    obj.version += 1
    db.flush()
    workflow(db, a, 'social_resource', obj.id, action, before, ap.handling_after(serial(obj), handling), reason, basis)
    return apps.detail(db, a, obj)


def load(db, ident):
    obj = db.get(SocialResource, ident)
    if obj is None or not apps.is_application(obj):
        raise HTTPException(404, '申请不存在')
    return obj


def teaching_values(db, a, applicant, data, current=None):
    row = db.get(TeacherCourseTerm, data.course_term_id)
    if row is None or not row.active or row.staff_no != applicant.staff_no:
        raise HTTPException(422, '只能申报本人在教务或超星系统里的课程')
    if not term_in_scope(row.term_name):
        raise HTTPException(422, '只受理 2020-2021 学年及以后的课程')
    identity = apps.course_identity(db, row)
    code = apps.application_code(applicant.id, identity)
    if current is not None and current.code != code:
        raise HTTPException(422, '退回补正时不能换成另一门课，请撤回后另行申报')
    if current is None and (old := db.scalar(select(SocialResource).where(SocialResource.code == code))) is not None:
        raise HTTPException(409, '这门课已经申报过（' + apps.state_label(old) + '），同一门课只申报一次' +
                            ('；被退回或撤回的请在“我的申请”里补正后重新提交' if old.state in ('RETURNED', 'WITHDRAWN') else ''))
    course = apps.source_course(db, row)
    values = serial(data.model_dump())
    values.update(course=course, identity=identity, code='', name=row.course_name,
                  hours=str(data.hours) if data.hours is not None else (str(course['hours']) if course.get('hours') is not None else None))
    return code, row.course_name, values


def manual_values(db, applicant, data, current=None):
    code = data.code.strip()
    master = db.scalar(select(TrainingCourseMaster).where(TrainingCourseMaster.code == code))
    if master is not None and master.active:
        raise HTTPException(409, '培训课程库里已有编号 ' + code + ' 的课程')
    key = 'CA-' + code
    if current is None and db.scalar(select(SocialResource.id).where(SocialResource.code == key)):
        raise HTTPException(409, '编号 ' + code + ' 已有人申请，请核对')
    if current is not None and current.code != key:
        raise HTTPException(422, '课程编号不能更改')
    values = serial(data.model_dump())
    values['hours'] = str(data.hours)
    return key, data.name.strip(), values


def notify(db, obj, title, desc):
    message_push.queue(db, [obj.data.get('teacher_id'), obj.data.get('created_by')], title, desc)


def create(db, a, kind, flow, code, name, values, applicant, college, reason):
    values.update(application=True, teacher_id=applicant.id, teacher_name=applicant.name, created_by=a.id, returned_level=None)
    obj = SocialResource(kind=kind, org_id=college.id, code=code, name=name, state=ap.first_state(flow), data=values)
    db.add(obj)
    db.flush()
    return record(db, a, obj, '提交' + ap.FLOWS[flow]['label'], {}, reason, {'flow': flow, 'decision': 'submit'})


@router.get('/mine')
def mine(request: Request):
    return read_operation(request, 'portal.read', lambda db, a, s: apps.mine(db, a))


@router.get('/teaching-courses')
def teaching_courses(request: Request):
    """我的课程：本人 2020-2021 学年以后的教务、超星课，每门课带社会培训课申报状态。"""
    return read_operation(request, 'portal.read', lambda db, a, s: {'years': apps.my_teaching_courses(db, a.user)})


@router.get('/{ident}')
def get_one(ident: str, request: Request):
    return read_operation(request, 'portal.read', lambda db, a, s: apps.detail(db, a, load(db, ident)))


@router.post('/courses')
def course_create(data: CourseApplyIn, request: Request):
    def apply(db, a, s):
        applicant = apps.resolve_applicant(db, a, data.data.teacher_id)
        college = apps.college_for(db, applicant)
        if data.data.source == 'teaching':
            code, name, values = teaching_values(db, a, applicant, data.data)
            flow = 'teaching_course'
        else:
            code, name, values = manual_values(db, applicant, data.data)
            flow = 'course'
        return create(db, a, 'course_apply', flow, code, name, values, applicant, college, data.reason)
    return command(request, data.model_dump(mode='json'), 'portal.read', apply)


@router.put('/courses/{ident}')
def course_edit(ident: str, data: CourseApplyIn, request: Request):
    def apply(db, a, s):
        obj = load(db, ident)
        if obj.kind != 'course_apply' or not apps.can_edit(a, obj):
            raise HTTPException(409, '只有被退回或已撤回的申请可以由申请人补正')
        check_version(obj, data.expected_version or 0)
        if data.data.source != obj.data.get('source'):
            raise HTTPException(422, '申报类型不能更改')
        applicant = apps.applicant_of(db, obj)
        before = serial(obj)
        if data.data.source == 'teaching':
            _, name, values = teaching_values(db, a, applicant, data.data, obj)
        else:
            _, name, values = manual_values(db, applicant, data.data, obj)
        keep = {k: obj.data.get(k) for k in ('application', 'teacher_id', 'teacher_name', 'created_by', 'returned_level', 'returned_flow')}
        obj.name = name
        obj.data = {**values, **keep}
        return record(db, a, obj, '补正申请资料', before, data.reason, {'flow': apps.flow_of(obj), 'decision': 'edit'})
    return command(request, data.model_dump(mode='json'), 'portal.read', apply)


def base_values(db, applicant, college, data):
    values = serial(data.model_dump())
    if data.project_id:
        p = db.get(SocialProject, data.project_id)
        if p is None or p.org_id != college.id:
            raise HTTPException(422, '来源项目不属于申请人所在学院')
    return values


@router.post('/bases')
def base_create(data: BaseApplyIn, request: Request):
    def apply(db, a, s):
        applicant = apps.resolve_applicant(db, a, data.data.teacher_id)
        college = apps.college_for(db, applicant)
        if db.scalar(select(SocialResource.id).where(SocialResource.code == data.data.code)):
            raise HTTPException(409, '来源编号 ' + data.data.code + ' 已被使用，请核对')
        values = base_values(db, applicant, college, data.data)
        return create(db, a, 'base', 'base', data.data.code, data.data.name, values, applicant, college, data.reason)
    return command(request, data.model_dump(mode='json'), 'portal.read', apply)


@router.put('/bases/{ident}')
def base_edit(ident: str, data: BaseApplyIn, request: Request):
    def apply(db, a, s):
        obj = load(db, ident)
        if obj.kind != 'base' or not apps.can_edit(a, obj):
            raise HTTPException(409, '只有被退回或已撤回的申请可以由申请人补正')
        check_version(obj, data.expected_version or 0)
        if data.data.code != obj.code:
            raise HTTPException(422, '来源编号不能更改')
        applicant = apps.applicant_of(db, obj)
        before = serial(obj)
        values = base_values(db, applicant, apps.college_for(db, applicant), data.data)
        keep = {k: obj.data.get(k) for k in ('application', 'teacher_id', 'teacher_name', 'created_by', 'returned_level')}
        obj.name = data.data.name
        obj.data = {**values, **keep}
        return record(db, a, obj, '补正申请资料', before, data.reason, {'flow': 'base', 'decision': 'edit'})
    return command(request, data.model_dump(mode='json'), 'portal.read', apply)


@router.post('/{ident}/actions')
def action(ident: str, data: ApplicationAction, request: Request):
    def apply(db, a, s):
        obj = load(db, ident)
        check_version(obj, data.expected_version)
        flow = apps.flow_of(obj)
        f = ap.FLOWS[flow]
        applicant = apps.applicant_of(db, obj)
        mine = a.id in {obj.data.get('teacher_id'), obj.data.get('created_by')}
        before = serial(obj)
        if data.action == 'submit':
            if not mine or obj.state not in ('RETURNED', 'WITHDRAWN'):
                raise HTTPException(409, '只有申请人可以重新提交被退回或已撤回的申请')
            level = obj.data.get('returned_level') if obj.state == 'RETURNED' else None
            obj.state = ap.resume_state(flow, level)
            obj.data = {**obj.data, 'returned_level': None}
            return record(db, a, obj, '重新提交' + f['label'], before, data.reason, {'flow': flow, 'decision': 'submit', 'resumed_from': level})
        if data.action == 'withdraw':
            if not mine or obj.state not in apps.PENDING_STATES:
                raise HTTPException(409, '只有申请人可以撤回审批中的申请')
            obj.state = 'WITHDRAWN'
            return record(db, a, obj, '撤回' + f['label'], before, data.reason, {'flow': flow, 'decision': 'withdraw'})
        level = ap.level_of(flow, obj.state)
        if not level:
            raise HTTPException(409, '申请不在审批中')
        handling = ap.check_handler(db, a, applicant, level, obj.org_id)
        handling.update(flow=flow, decision=data.action)
        if data.action == 'return':
            obj.state = 'RETURNED'
            obj.data = {**obj.data, 'returned_level': level}
            result = record(db, a, obj, ap.LEVEL_LABEL[level] + '退回' + f['label'], before, data.reason, handling, data.basis)
            notify(db, obj, f['label'] + '被退回', obj.name + '：' + ap.LEVEL_LABEL[level] + '退回，原因：' + data.reason + '。请在“我的申请”里补正后重新提交。')
            return result
        if ap.same_person(db, 'social_resource', obj.id, a):
            handling['same_person'] = ap.SAME_PERSON
        obj.state = ap.next_state(flow, level)
        if obj.state == f['done']:
            apps.complete(db, a, obj, flow)
        result = record(db, a, obj, ap.LEVEL_LABEL[level] + '通过' + f['label'], before, data.reason, handling, data.basis)
        if obj.state == f['done']:
            notify(db, obj, f['label'] + '已通过', obj.name + '：' + f['final'] + '。')
        return result
    return command(request, data.model_dump(mode='json'), 'portal.read', apply)
