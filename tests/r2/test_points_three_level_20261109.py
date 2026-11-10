"""社会培训项目积分：结项通过后由老师自己申报，走 教研室 → 学院 → 学校 三级；每一级看得到前面的意见，也能改认定积分（改了要写原因）。
2026-11-10 用户定：不做结项后自动生成申报，和课程认定一样老师自己提起。"""
from datetime import date
from decimal import Decimal
from sqlalchemy import select
from app.models import PointEntry
from app.social_models import SocialClaim
from app import social_training as st
from conftest import auth, post
from test_social_training import HASH, setup_social, import_rows, row, action, detail, policy, close_project  # noqa: F401


def claims_of(app2, pid):
    with app2.state.sessions() as db:
        return db.scalars(select(SocialClaim).where(SocialClaim.project_id == pid)).all()


def self_claim(client, pid, pol):
    """老师在“申报本人积分”里自己申报并提交。"""
    auth(client, 'teacher')
    r = post(client, '/api/social/claims', {'project_id': pid, 'period_id': 'period2026', 'policy_id': pol,
                                            'recognition_form_reference': '学校制式认定表与佐证附件', 'reason': '本人申报'})
    assert r.status_code == 200, r.text
    ident = r.json()['item']['id']
    r = action(client, 'claims', 'social_claim', ident, 'submit')
    assert r.status_code == 200, r.text
    return ident, r.json()['item']['state']


def approve(client, ident, user, **extra):
    auth(client, user)
    return action(client, 'claims', 'social_claim', ident, 'approve', **extra)


def points_of(client, ident):
    return client.get('/api/social/objects/social_claim/' + ident).json()['points']


def setup_closed(setup_social, client2, monkeypatch, **policy_extra):
    monkeypatch.setattr(st, 'today', lambda: date(2026, 9, 3))
    pid = setup_social
    pol = policy(client2, True, **policy_extra)  # 学校已启用积分口径
    assert import_rows(client2, pid, [row()]).status_code == 200
    close_project(client2, pid)
    return pid, pol


def test_closeout_no_longer_creates_claims_teacher_files_them(setup_social, client2, app2, monkeypatch):
    pid, pol = setup_closed(setup_social, client2, monkeypatch)
    assert claims_of(app2, pid) == []  # 结项通过不再自动生成
    ident, state = self_claim(client2, pid, pol)
    assert state == 'DEPT'


def test_three_levels_see_each_other_and_college_can_change_points(setup_social, client2, app2, monkeypatch):
    pid, pol = setup_closed(setup_social, client2, monkeypatch)
    ident, _ = self_claim(client2, pid, pol)
    auth(client2, 'collegehead')
    assert action(client2, 'claims', 'social_claim', ident, 'approve').status_code == 403  # 不能越过教研室
    base = points_of(client2, ident)
    assert base['adjusted'] is False and Decimal(base['teaching']) > 0
    r = approve(client2, ident, 'depthead', reason='教研室核对无误')
    assert r.status_code == 200 and r.json()['item']['state'] == 'COLLEGE', r.text
    # 学院改认定积分：必须写原因
    r = approve(client2, ident, 'collegehead', teaching_points='2.00', auxiliary_points=base['auxiliary'])
    assert r.status_code == 422 and '原因' in r.text
    r = approve(client2, ident, 'collegehead', teaching_points='2000', auxiliary_points='0', adjust_reason='超范围')
    assert r.status_code == 422
    r = approve(client2, ident, 'collegehead', reason='学院审批同意', teaching_points='2.00', auxiliary_points=base['auxiliary'], adjust_reason='本项目承担了额外的实训指导')
    assert r.status_code == 200 and r.json()['item']['state'] == 'SCHOOL', r.text
    # 学校看得到前面两级的意见和积分改动，下一级审批不会因为“依据变化”被拦
    auth(client2, 'reviewer')
    shown = points_of(client2, ident)
    assert shown['adjusted'] is True and shown['teaching'] == '2.00' and len(shown['steps']) == 2
    assert [s['level'] for s in shown['steps']] == ['dept', 'college']
    assert shown['steps'][1]['teaching_before'] == base['teaching'] and shown['steps'][1]['adjust_reason'] == '本项目承担了额外的实训指导'
    assert shown['steps'][0]['reason'] == '教研室核对无误'
    r = approve(client2, ident, 'reviewer', reason='学校认定')
    assert r.status_code == 200 and r.json()['item']['state'] == 'ARCHIVED', r.text
    with app2.state.sessions() as db:
        entries = db.scalars(select(PointEntry).where(PointEntry.kind == 'SOCIAL')).all()
        teaching = next(e for e in entries if e.item_key.startswith('social_teaching_'))
        assert teaching.amount == Decimal('2.00') and '审批中由' in teaching.formula
        assert len(teaching.source_snapshot['review_steps']) == 3
        assert sum(e.amount for e in entries) == Decimal('2.00') + Decimal(base['auxiliary'])
    # 老师看得到最终认定积分和各级意见
    auth(client2, 'teacher')
    mine = points_of(client2, ident)
    assert mine['teaching'] == '2.00' and len(mine['steps']) == 3


def test_school_can_also_change_points_and_unchanged_levels_keep_trial(setup_social, client2, app2, monkeypatch):
    pid, pol = setup_closed(setup_social, client2, monkeypatch)
    ident, _ = self_claim(client2, pid, pol)
    base = points_of(client2, ident)
    for user in ('depthead', 'collegehead'):
        assert approve(client2, ident, user).status_code == 200
    assert points_of(client2, ident)['adjusted'] is False
    r = approve(client2, ident, 'reviewer', teaching_points='1.00', auxiliary_points=base['auxiliary'], adjust_reason='按学校核定降低')
    assert r.status_code == 200 and r.json()['item']['state'] == 'ARCHIVED', r.text
    with app2.state.sessions() as db:
        assert sum(db.scalars(select(PointEntry.amount).where(PointEntry.kind == 'SOCIAL'))) == Decimal('1.00') + Decimal(base['auxiliary'])


def test_return_keeps_opinion_and_earlier_change_after_resubmit(setup_social, client2, app2, monkeypatch):
    pid, pol = setup_closed(setup_social, client2, monkeypatch, resubmission_mode='original_submission')
    ident, _ = self_claim(client2, pid, pol)
    base = points_of(client2, ident)
    assert approve(client2, ident, 'depthead', teaching_points='1.20', auxiliary_points=base['auxiliary'], adjust_reason='教研室核减').status_code == 200
    auth(client2, 'collegehead')
    r = action(client2, 'claims', 'social_claim', ident, 'return', reason='请补充材料说明')
    assert r.status_code == 200 and r.json()['item']['state'] == 'RETURNED', r.text
    auth(client2, 'teacher')
    r = action(client2, 'claims', 'social_claim', ident, 'submit')
    assert r.status_code == 200 and r.json()['item']['state'] == 'COLLEGE', r.text  # 从被退回的那一级接着审
    shown = points_of(client2, ident)
    assert shown['teaching'] == '1.20' and [s['decision'] for s in shown['steps']] == ['approve', 'return']
    for user in ('collegehead', 'reviewer'):
        assert approve(client2, ident, user).status_code == 200
    with app2.state.sessions() as db:
        teaching = next(e for e in db.scalars(select(PointEntry).where(PointEntry.kind == 'SOCIAL')) if e.item_key.startswith('social_teaching_'))
        assert teaching.amount == Decimal('1.20')


def test_no_active_policy_teacher_cannot_file(setup_social, client2, app2, monkeypatch):
    monkeypatch.setattr(st, 'today', lambda: date(2026, 9, 3))
    pid = setup_social
    assert import_rows(client2, pid, [row()]).status_code == 200
    close_project(client2, pid)
    assert claims_of(app2, pid) == []


def test_vacant_dept_and_vacant_college_goes_straight_to_school(setup_social, client2, app2, monkeypatch):
    """教研室没人批顺延到学院；学院也没人（没设置负责人）就学校批。"""
    from sqlalchemy.orm import Session
    from app.models import User
    pid, pol = setup_closed(setup_social, client2, monkeypatch)
    with Session(app2.state.engine) as db:
        for ident in ('depthead', 'collegehead'):
            db.get(User, ident).role_id = 'role-teacher'
        db.commit()
    ident, state = self_claim(client2, pid, pol)
    assert state == 'SCHOOL'
    r = approve(client2, ident, 'reviewer')
    assert r.status_code == 200 and r.json()['item']['state'] == 'ARCHIVED', r.text


def test_school_one_click_closeout_records_that_materials_were_auto_ticked(setup_social, client2, app2, monkeypatch):
    """学校一键同意结项时，办理记录写明材料是系统自动勾选的，不让记录看起来像逐项核对过。"""
    from sqlalchemy.orm import Session
    from app.models import WorkflowEvent
    pid, pol = setup_closed(setup_social, client2, monkeypatch)
    with Session(app2.state.engine) as db:
        events = [e for e in db.scalars(select(WorkflowEvent).where(WorkflowEvent.object_id == pid).order_by(WorkflowEvent.created_at)) if '已结项' in e.action]
    assert events and '一键同意：结项材料由系统自动勾选为已核对' in events[-1].basis
    item = detail(client2, 'social_project', pid)['item']
    assert item['closeout']['materials_auto'] is True


def test_teacher_can_file_with_unapproved_draft_policy(setup_social, client2, app2, monkeypatch):
    """学校积分量化管理办法暂未批准：只有草稿口径（没有启用的口径），老师结项后也能自己申报，系统标注“试行”；三级审批、改积分、入账照常。"""
    from sqlalchemy.orm import Session
    from app.social_models import SocialPolicy
    pid, pol = setup_closed(setup_social, client2, monkeypatch)
    with Session(app2.state.engine) as db:  # 把口径退回草稿，模拟“办法没批、口径没启用”
        db.get(SocialPolicy, pol).state = 'DRAFT'
        db.commit()
    ident, state = self_claim(client2, pid, pol)
    assert state == 'DEPT'
    auth(client2, 'teacher')
    d = client2.get('/api/social/objects/social_claim/' + ident).json()
    assert d['trial']['trial_mode'] is True and not d['trial']['blockers']
    base = points_of(client2, ident)
    r = approve(client2, ident, 'depthead')
    assert r.status_code == 200
    r = approve(client2, ident, 'collegehead', teaching_points='1.00', auxiliary_points=base['auxiliary'], adjust_reason='试行口径下学院核减')
    assert r.status_code == 200 and r.json()['item']['state'] == 'SCHOOL', r.text
    r = approve(client2, ident, 'reviewer')
    assert r.status_code == 200 and r.json()['item']['state'] == 'ARCHIVED', r.text
    with app2.state.sessions() as db:
        assert sum(db.scalars(select(PointEntry.amount).where(PointEntry.kind == 'SOCIAL'))) == Decimal('1.00') + Decimal(base['auxiliary'])


def test_voided_policy_still_blocks_claims(setup_social, client2, app2, monkeypatch):
    from sqlalchemy.orm import Session
    from app.social_models import SocialPolicy
    pid, pol = setup_closed(setup_social, client2, monkeypatch)
    with Session(app2.state.engine) as db:
        db.get(SocialPolicy, pol).state = 'VOID'
        db.commit()
    auth(client2, 'teacher')
    r = post(client2, '/api/social/claims', {'project_id': pid, 'period_id': 'period2026', 'policy_id': pol,
                                            'recognition_form_reference': '学校制式认定表与佐证附件', 'reason': '本人申报'})
    assert r.status_code == 422


def test_edited_points_flow_into_corrections_booked_display_and_annual_totals(setup_social, client2, app2, monkeypatch):
    """学院改过的认定积分，要同样用于：更正的基数、已记积分显示、学院年度考核的积分合计。不能还按系统原始试算算。"""
    from sqlalchemy.orm import Session
    from app import lifecycle as lc
    pid, pol = setup_closed(setup_social, client2, monkeypatch)
    ident, _ = self_claim(client2, pid, pol)
    base = points_of(client2, ident)
    assert approve(client2, ident, 'depthead').status_code == 200
    r = approve(client2, ident, 'collegehead', teaching_points='1.00', auxiliary_points=base['auxiliary'], adjust_reason='学院核减')
    assert r.status_code == 200
    assert approve(client2, ident, 'reviewer').status_code == 200
    final = Decimal('1.00') + Decimal(base['auxiliary'])
    with Session(app2.state.engine) as db:
        claim = db.get(SocialClaim, ident)
        totals = st.correction_totals(db, claim)
        assert totals['teaching'] == Decimal('1.00') and sum(totals.values()) == final
        project = db.get(__import__('app.social_models', fromlist=['SocialProject']).SocialProject, pid)
        assert lc.points_booked(db, project)['teacher'] == str(final)


def test_member_teacher_and_dept_head_cannot_read_financials_or_peer_points(setup_social, client2, app2, monkeypatch):
    """参与授课的老师、教研室负责人不能通过运行档案接口看到结项财务数据和其他老师的预计积分；负责人和学院学校可以。草稿口径下预计积分照常显示。"""
    from sqlalchemy.orm import Session
    from app.models import User
    from app.social_models import SocialPolicy
    from support import HASH
    monkeypatch.setattr(st, 'today', lambda: date(2026, 9, 3))
    c = client2
    pid = setup_social
    pol = policy(c, True)
    with Session(app2.state.engine) as db:
        db.add(User(id='member', username='member', name='参与教师', staff_no='J009', org_id='dept1', role_id='role-teacher', password_hash=HASH, must_change_password=False, active=True))
        db.get(SocialPolicy, pol).state = 'DRAFT'  # 办法未批准：只有草稿口径
        db.commit()
    member_row = {**row(), 'teachers': [{'teacher_id': 'teacher', 'staff_type': 'internal', 'role': 'lecturer'}, {'teacher_id': 'member', 'staff_type': 'internal', 'role': 'instructor'}]}
    auth(c, 'reviewer')
    assert import_rows(c, pid, [member_row]).status_code == 200
    close_project(c, pid)
    auth(c, 'member')
    mine = c.get('/api/social/lifecycle/project/' + pid).json()['points']
    assert mine['line'] == '' and mine['value'] not in ('口径未启用', '0')
    assert c.get('/api/social/lifecycle/close-review/' + pid).status_code == 403
    assert c.get('/api/social/lifecycle/close-check/' + pid).status_code == 403
    auth(c, 'depthead')
    assert c.get('/api/social/lifecycle/close-review/' + pid).status_code == 403
    assert c.get('/api/social/lifecycle/project/' + pid).json()['points']['line'] == ''
    auth(c, 'teacher')  # 负责人：能看预计积分明细（草稿口径也显示），也能看查缺
    owner = c.get('/api/social/lifecycle/project/' + pid).json()['points']
    assert '参与教师' in owner['line'] and owner['value'] != '口径未启用'
    assert c.get('/api/social/lifecycle/close-check/' + pid).status_code == 200
    auth(c, 'collegehead')
    r = c.get('/api/social/lifecycle/close-review/' + pid)
    assert r.status_code == 200 and 'actual_income' in r.json()['closeout']
