"""已入库课程的后续办理；复用项目、本人工作明细和原积分认定，不另算一份分。"""
from datetime import date
from fastapi import HTTPException
from sqlalchemy import select
from . import applications as apps, social_training as st
from .models import Period, User
from .reference_data import TrainingCourseMaster
from .social_models import SocialProject, SocialClaim, SocialPolicy


def can_link_course(actor, application):
    if actor.role.kind == 'teacher':
        return application.data.get('teacher_id') == actor.id
    return actor.role.kind in ('college', 'school') and 'records.write' in actor.permissions and application.org_id in actor.org_ids


def course_points_progress(db, actor, application, project_id=''):
    actor.require('records.read')
    course = db.scalar(select(TrainingCourseMaster).where(TrainingCourseMaster.code == application.data.get('course_code')))
    ready = application.kind == 'course_apply' and application.state == 'ACTIVE' and course is not None and course.active
    can_read_application = True
    try:
        applicant = apps.read_check(db, actor, application)
    except HTTPException as exc:
        if (exc.status_code != 403 or actor.role.kind != 'teacher' or not ready or
                not db.scalar(st.visible_courses(db, actor).where(TrainingCourseMaster.id == course.id))):
            raise
        can_read_application = False
        applicant = actor.user
    if application.kind != 'course_apply' or not applicant:
        raise HTTPException(422, '只有培训课程可以查看积分办理')
    # 共用课程的教师办理本人的积分，原课程申请和附件仍沿原权限保护。
    if actor.role.kind == 'teacher':
        applicant = actor.user
    actor.check_teacher(db, applicant.id)
    own = actor.id == applicant.id and bool(actor.user.staff_no)
    result = {'application_id': application.id, 'can_read_application': can_read_application,
              'course': {'name': course.name if ready else application.name, 'code': course.code if course else ''},
              'applicant': {'id': applicant.id, 'name': applicant.name}, 'project': None, 'claim': None,
              'can_link': bool(ready and not course.project_code and can_link_course(actor, application)),
              'can_create_project': actor.role.kind == 'teacher' or actor.role.kind in ('college', 'school') and 'records.write' in actor.permissions,
              'can_claim': False, 'can_open_claim': False, 'projects': [], 'period_id': '', 'policy_id': ''}
    done = [ready, False, False, False, False]

    def finish(stage, label, message, responsible):
        result.update(stage=stage, label=label, message=message, responsible=responsible,
                      steps=[{'label': label, 'done': value} for label, value in zip(
                          ['课程入库', '关联项目并备案', '登记培训与本人工作', '项目正常结项', '积分审核归档'], done)])
        return result

    if not ready:
        return finish('approval', '待课程入库', '课程审批通过并生效后，继续办理培训项目和积分。', '课程当前审批人')
    if not course.project_code:
        return finish('link', '待关联培训项目', '课程已入库。请选择实际开展培训的项目；尚无项目时可先申报项目，再关联本课程。', '项目负责人或本学院、学校培训管理员')
    candidates = db.scalars(select(SocialProject).where(SocialProject.data['code'].as_string() == course.project_code)
                           .order_by(SocialProject.created_at.desc(), SocialProject.id)).all()
    visible = []
    for project in candidates:
        try:
            st.scoped(db, actor, 'social_project', project.id, allow_participant=True)
        except HTTPException as exc:
            if exc.status_code not in (403, 404):
                raise
            continue
        visible.append(project)
    if not visible:
        return finish('project_access', '待核实项目参与关系', '课程已关联项目，请项目负责人登记本人参与明细，或联系学院核实项目查看范围。', '项目负责人或学院培训管理员')
    if project_id and project_id not in {p.id for p in visible}:
        raise HTTPException(403, '项目不属于本课程或超出查看范围')
    if len(visible) > 1 and not project_id:
        result['projects'] = [{'id': p.id, 'name': p.data['name'], 'cohort': p.cohort} for p in visible]
        return finish('project_choice', '选择实际培训期次', '同一项目有多个期次，请选择本次积分对应的培训期次。', '申报人')
    project = next((p for p in visible if p.id == project_id), visible[0])
    manager = (actor.role.kind == 'teacher' and project.owner_id == actor.id or
               actor.role.kind in ('college', 'school') and 'records.write' in actor.permissions)
    owner = db.get(User, project.owner_id)
    result['project'] = {'id': project.id, 'name': project.data['name'], 'code': project.data['code'],
                         'cohort': project.cohort, 'state': project.state, 'state_label': st.state_label(project),
                         'version': project.version, 'can_manage': manager and project.state not in ('CLOSED', 'VOID')}
    work = [u for u in st.units(db, project.id) if any(t.get('teacher_id') == applicant.id and t.get('staff_type') == 'internal' for t in u.data.get('teachers', []))]
    done[1] = project.state in ('FILED', 'CLOSE_COLLEGE', 'CLOSE_REVIEW', 'CLOSED')
    done[2] = bool(work)
    done[3] = project.state == 'CLOSED'
    claim = db.scalar(select(SocialClaim).where(SocialClaim.project_id == project.id, SocialClaim.teacher_id == applicant.id,
                                               SocialClaim.state != 'VOID').order_by(SocialClaim.created_at.desc(), SocialClaim.id).limit(1))
    if claim:
        result['claim'] = {'id': claim.id, 'state': claim.state, 'state_label': st.state_label(claim)}
        result['can_open_claim'] = True
        done[4] = claim.state == 'ARCHIVED'
        responsible={'DRAFT':'申报人','RETURNED':'申报人','SUBMITTED':'二级学院院长','DEAN':'学校归口复审人员',
                     'COORDINATOR':'分管副校长','APPROVED':'教学秘书','ARCHIVED':'已归档入账，无需继续办理'}
        return finish('claim', '已认定积分' if done[4] else st.state_label(claim),
                      '本项目本人积分已归档入账；其他课程沿用此认定，不再重复申报。' if done[4] else
                      '本项目已有本人积分申请，请继续原申请；其他课程沿用同一份申请。', responsible.get(claim.state,'当前积分审核人'))
    if not done[1]:
        return finish('filing', '待项目备案', '课程已关联。请完善项目材料并沿原流程提交、审批和备案。', owner.name if owner else '项目负责人')
    if not done[2]:
        return finish('work', '待登记本人工作依据', '请登记包含本人工号的实际授课或辅助工作明细及佐证。课程资料中的学时不能代替实际培训记录。', '学院或学校培训管理员')
    if not done[3]:
        return finish('close', '待项目正常结项', '本人工作明细已有记录。完成培训并提交结项材料，核验通过后再申报积分。', owner.name if owner else '项目负责人')
    closed = project.closeout.get('closed_on')
    if not closed:
        return finish('project_data', '待核实结项资料', '项目缺少结项日期，请联系学院核实；不能据此推算申报期限。', '学院培训管理员')
    periods = db.scalars(select(Period).where(Period.state == 'OPEN', Period.start_date <= date.fromisoformat(closed),
                                             Period.end_date >= date.fromisoformat(closed))).all()
    policies = db.scalars(select(SocialPolicy).where(SocialPolicy.state == 'ACTIVE', SocialPolicy.period_id.in_([p.id for p in periods]))).all()
    if not policies:
        return finish('policy', '待开放认定周期或口径', '请学校确认涵盖结项日期的开放周期，并启用该周期的积分制度执行口径。', '学校积分管理员')
    valid, reasons = [], []
    for policy in policies:
        deadline, errors = st.calendar_block(policy.data, date.fromisoformat(closed), 15)
        if errors:
            reasons.append('学校工作日历尚未确认，暂不能确定申报期限。')
        elif deadline and st.today() > deadline:
            reasons.append('已超过结项后15个工作日申报期限，请联系学院核实；本入口不会自动放宽期限。')
        else:
            valid.append(policy)
    if not valid:
        return finish('deadline', '待核实申报期限', '；'.join(dict.fromkeys(reasons)), '学院或学校积分管理员')
    if len(valid) == 1:
        result.update(period_id=valid[0].period_id, policy_id=valid[0].id)
    result['can_claim'] = own
    return finish('ready', '可填写积分申请', '项目已结项，本人工作明细已登记。填写认定材料后提交审核；最终分值和其他条件沿用原规则校验。', applicant.name)
