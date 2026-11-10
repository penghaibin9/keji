"""2026-11-08 本地全流程走查修复：零收入项目不生成结算跟踪、结算待办只给能办的人；年度确认的年份限制和同年更正。"""
from conftest import auth, post, put
from test_social_training import setup_social, import_rows, row, action  # noqa: F401
from test_applications import act
from test_lifecycle_20261107 import life
from test_flow_simplify_20261104 import MATERIALS

ZERO = {'closed_on': '2026-09-02', 'outcome_report': '结项报告', 'satisfaction': '96', 'actual_income': '0',
        'finance_reference': '零收入项目，无到账收入', 'location': 'onsite'}
PAID = {**ZERO, 'actual_income': '10000', 'funding_source': 'other_training', 'retained': '2000', 'personnel': '6000', 'finance_reference': '财务凭证'}


def settle_titles(c):
    return [x['title'] for x in c.get('/api/todos').json()['items'] if '结算期限' in x.get('title', '')]


def close(c, pid, closeout):
    auth(c, 'schooladmin')
    assert import_rows(c, pid, [row()]).status_code == 200
    auth(c, 'teacher')
    r = action(c, 'projects', 'social_project', pid, 'close_submit', closeout=closeout)
    assert r.status_code == 200, r.text
    auth(c, 'collegehead')
    assert action(c, 'projects', 'social_project', pid, 'approve').status_code == 200
    auth(c, 'reviewer')
    r = action(c, 'projects', 'social_project', pid, 'close', materials_checked=MATERIALS)
    assert r.status_code == 200, r.text


def test_zero_income_project_has_no_settlement_todo(setup_social, client2):
    c = client2
    close(c, setup_social, ZERO)
    for user in ('reviewer', 'teacher', 'collegehead', 'schooladmin'):
        auth(c, user)
        assert settle_titles(c) == [], user


def test_settlement_todo_only_for_finance_or_coordinator(setup_social, client2):
    c = client2
    close(c, setup_social, PAID)
    auth(c, 'reviewer')  # 夹具里 reviewer 同时担任归口复审和财务核验
    assert len(settle_titles(c)) == 1
    for user in ('teacher', 'collegehead', 'schooladmin', 'vice'):
        auth(c, user)
        assert settle_titles(c) == [], user


def base_running(c):
    auth(c, 'teacher')
    data = {'code': 'WALK-B1', 'name': '走查实践基地', 'location': '图书馆', 'onsite': True, 'recognition': '会议纪要',
            'usages': ['practice'], 'established_on': '2026-03-01'}
    r = post(c, '/api/applications/bases', {'data': data, 'reason': '申请基地'})
    assert r.status_code == 200, r.text
    ident = r.json()['item']['id']
    auth(c, 'collegehead')
    assert act(c, ident, 'approve').status_code == 200
    auth(c, 'reviewer')
    assert act(c, ident, 'approve').status_code == 200
    auth(c, 'teacher')
    return ident


def test_annual_confirm_rejects_years_before_base_existed_and_records_correction(setup_social, client2):
    c = client2
    ident = base_running(c)
    view = life(c, 'base', ident)
    assert 2025 not in view['annual_years'] and 2026 in view['annual_years']
    url = '/api/social/lifecycle/base/' + ident + '/annual'
    r = post(c, url, {'year': 2025, 'running': True, 'text': '设立前'})
    assert r.status_code == 422 and '还没有设立或认定' in r.text
    assert post(c, url, {'year': 2026, 'running': True, 'text': '今年在用'}).status_code == 200
    r = post(c, url, {'year': 2026, 'running': False, 'text': '填错了，今年其实没用'})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d['timeline'][0]['what'] == '年度运行确认（更正）：2026年度在运行 → 暂未运行'
    assert d['annual']['2026']['running'] is False
    assert any(k == '最近年度确认' and v == '2026年 · 暂未运行' for k, v in d['stats'])


def test_stopped_base_can_resume(setup_social, client2):
    c = client2
    ident = base_running(c)
    v = life(c, 'base', ident)
    assert post(c, '/api/social/lifecycle/base/' + ident + '/stop', {'reason': '装修', 'expected_version': v['version']}).status_code == 200
    v = life(c, 'base', ident)
    assert v['state'] == 'STOPPED' and v['can']['resume']
    r = post(c, '/api/social/lifecycle/base/' + ident + '/resume', {'reason': '装修完成', 'expected_version': v['version']})
    assert r.status_code == 200, r.text
    assert life(c, 'base', ident)['running']


def test_course_withdrawn_at_source_auto_reverses_booked_points(client2, app2):
    """源头撤下已认定入账的课（全量对账或整批撤销停用课程学期）：自动追加反向积分，老师积分确认不再被卡死。"""
    from decimal import Decimal
    from types import SimpleNamespace
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from app.models import PointEntry
    from app.reference_data import TeacherCourseTerm, credit_reviews
    from app.teaching_review import unbook_withdrawn
    from test_teaching_credit_review import ready, course, credits, review, teaching_points, _stale, _confirm
    c = client2
    ready(c, app2)
    for user in ('depthead', 'collegehead', 'jwc'):
        auth(c, user)
        k1 = course(credits(c, 'J001')['2025-2026'], 'K1')
        assert review(c, [k1['id']], 'approve').status_code == 200, user
    assert teaching_points(app2) == Decimal('64')
    actor = SimpleNamespace(id='schooladmin', name='学校测试管理员', org=SimpleNamespace(id='school'), request_id='test-withdrawn')
    with Session(app2.state.engine) as db:
        row = db.get(TeacherCourseTerm, k1['id'])
        row.active = False
        db.flush()
        done = unbook_withdrawn(db, actor, [row])
        assert list(done) == [row.id]
        assert unbook_withdrawn(db, actor, [row]) == {}  # 再跑一次不重复冲销
        obj = credit_reviews(db, [row.id])[row.id]
        assert obj.data['booked'] is None and obj.data['history'][-1]['decision'] == 'withdrawn'
        db.commit()
        amounts = sorted(str(e.amount) for e in db.scalars(select(PointEntry).where(PointEntry.teacher_id == 'teacher', PointEntry.kind == 'TEACHING')))
    assert amounts == ['-64.00', '64.00'] and teaching_points(app2) == Decimal('0')
    assert _stale(app2) == []
    assert _confirm(c).status_code == 200


def test_approved_qualification_void_request_review_and_withdraw(app2, client2):
    """审核通过的资质不能删，只能申请作废：作废审核期间照常有效，同意后变“已作废”，不再算有效；不同意或撤回回到审核通过。"""
    import uuid
    from test_api import qual, png
    from test_teacher_delete import qual_action
    c = client2
    auth(c, 'teacher')
    q = qual(c)
    up = c.post('/api/attachments/qualification/' + q['id'], headers={'Idempotency-Key': str(uuid.uuid4())},
                data={'expected_version': str(q['version']), 'reason': '上传证书'}, files={'file': ('cert.png', png(), 'image/png')})
    assert up.status_code == 200, up.text
    assert qual_action(c, q['id'], 'submit').status_code == 200
    assert qual_action(c, q['id'], 'void_request').status_code == 409  # 还没通过，不能申请作废
    auth(c, 'schooladmin')
    assert qual_action(c, q['id'], 'approve').status_code == 200
    v = c.get('/api/qualifications/' + q['id']).json()['qualification']['version']
    auth(c, 'otherteacher')
    assert qual_action(c, q['id'], 'void_request', v).status_code in (403, 404)
    auth(c, 'teacher')
    d = c.get('/api/qualifications/' + q['id']).json()
    assert d['can_void'] and not d['can_review_void']
    assert qual_action(c, q['id'], 'void_request').status_code == 200
    summary = c.get('/api/qualification-summary').json()
    assert sum(x['count'] for x in summary['items'] if x['key'] in ('VALID', 'EXPIRING', 'EXPIRED')) == 1  # 作废审核期间照常有效
    assert qual_action(c, q['id'], 'void_approve').status_code == 403  # 本人不能审
    assert qual_action(c, q['id'], 'withdraw').status_code == 200
    assert c.get('/api/qualifications/' + q['id']).json()['qualification']['state'] == 'APPROVED'
    assert qual_action(c, q['id'], 'void_request').status_code == 200
    auth(c, 'schooladmin')
    assert any(x['id'] == q['id'] and '作废审核' in x['title'] for x in c.get('/api/todos').json()['items'])
    d = c.get('/api/qualifications/' + q['id']).json()
    assert d['can_review_void']
    assert qual_action(c, q['id'], 'void_reject').status_code == 200
    assert c.get('/api/qualifications/' + q['id']).json()['qualification']['state'] == 'APPROVED'
    auth(c, 'teacher')
    assert qual_action(c, q['id'], 'void_request').status_code == 200
    auth(c, 'schooladmin')
    assert qual_action(c, q['id'], 'void_approve').status_code == 200
    auth(c, 'teacher')
    assert c.get('/api/qualifications/' + q['id']).json()['qualification']['state'] == 'VOID'
    summary = c.get('/api/qualification-summary').json()
    assert summary['voided'] == 1 and sum(x['count'] for x in summary['items'] if x['key'] in ('VALID', 'EXPIRING', 'EXPIRED')) == 0
    assert q['id'] in [x['id'] for x in c.get('/api/qualifications', params={'state': 'VOID'}).json()['items']]
    item = c.get('/api/qualifications/' + q['id']).json()['qualification']
    r = put(c, '/api/qualifications/' + q['id'], {'teacher_id': 'teacher', 'category': '职业资格', 'name': '改名', 'certificate_no': item['certificate_no'],
            'issuer': '合成发证单位', 'obtained': '2026-01-01', 'expires': '2026-12-31', 'expected_version': item['version'], 'reason': '作废后再改'})
    assert r.status_code == 409 and '已作废' in r.text
    assert qual_action(c, q['id'], 'delete').status_code == 409


def _closed_events(app2, pid):
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from app.models import WorkflowEvent
    with Session(app2.state.engine) as db:
        return [(e.action, e.reason) for e in db.scalars(select(WorkflowEvent).where(WorkflowEvent.object_id == pid).order_by(WorkflowEvent.created_at))]


def test_closeout_without_policy_or_open_period_says_why_no_claim(setup_social, client2, app2, monkeypatch):
    """线上现状：没有启用的积分口径、没有开放周期。结项通过后不再静默跳过，项目办理记录里写明原因。"""
    from datetime import date
    from sqlalchemy.orm import Session
    from app import social_training as st
    from app.models import Period
    from test_social_training import close_project
    monkeypatch.setattr(st, 'today', lambda: date(2026, 9, 3))
    c = client2
    pid = setup_social
    assert import_rows(c, pid, [row()]).status_code == 200
    close_project(c, pid)  # 周期开放，但没有启用口径
    notes = [r for a_, r in _closed_events(app2, pid) if a_ == '结项通过，未生成积分申报']
    assert len(notes) == 1 and '还没有已启用的积分认定口径' in notes[0]


def test_closeout_with_closed_period_says_no_open_period(setup_social, client2, app2, monkeypatch):
    from datetime import date
    from sqlalchemy.orm import Session
    from app import social_training as st
    from app.models import Period
    from test_social_training import close_project
    monkeypatch.setattr(st, 'today', lambda: date(2026, 9, 3))
    c = client2
    pid = setup_social
    assert import_rows(c, pid, [row()]).status_code == 200
    with Session(app2.state.engine) as db:
        db.get(Period, 'period2026').state = 'CLOSED'
        db.commit()
    close_project(c, pid)
    notes = [r for a_, r in _closed_events(app2, pid) if a_ == '结项通过，未生成积分申报']
    assert len(notes) == 1 and '没有包含结项日期' in notes[0] and '开放考核周期' in notes[0]


def test_live_like_config_vacant_dept_and_single_school_approver_still_walks_through(setup_social, client2, app2, monkeypatch):
    """照线上现状：教研室没有负责人（占位），学校级职责都在同一个账号上。结项通过后自动生成的申报直接到学院，再到学校，能入账。"""
    from datetime import date
    from decimal import Decimal
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from app import social_training as st
    from app.models import PointEntry, User
    from app.social_models import SocialClaim
    from test_social_training import policy, close_project
    monkeypatch.setattr(st, 'today', lambda: date(2026, 9, 3))
    c = client2
    pid = setup_social
    with Session(app2.state.engine) as db:  # 教研室负责人退成普通教师：dept1 没有负责人
        db.get(User, 'depthead').role_id = 'role-teacher'
        db.commit()
    policy(c, True)
    assert import_rows(c, pid, [row()]).status_code == 200
    close_project(c, pid)
    assert [r for a_, r in _closed_events(app2, pid) if a_ == '结项通过，未生成积分申报'] == []
    with Session(app2.state.engine) as db:
        claims = db.scalars(select(SocialClaim).where(SocialClaim.project_id == pid)).all()
    assert len(claims) == 1 and claims[0].state == 'COLLEGE'  # 教研室缺位，直接到学院
    ident = claims[0].id
    for user, after in (('collegehead', 'SCHOOL'), ('reviewer', 'ARCHIVED')):
        auth(c, user)
        r = action(c, 'claims', 'social_claim', ident, 'approve')
        assert r.status_code == 200 and r.json()['item']['state'] == after, r.text
    with Session(app2.state.engine) as db:
        assert sum(db.scalars(select(PointEntry.amount).where(PointEntry.kind == 'SOCIAL'))) == Decimal('1.56')


def test_teaching_credit_books_into_open_period_when_closed_one_overlaps(setup_social, app2):
    """线上有个已关闭的试验周期“1111”（2026-01-01～10-31）。新建同样日期的正式周期后，授课认定积分要记入开放的那个。"""
    from datetime import date
    from sqlalchemy.orm import Session
    from app.models import Period
    from app.teaching_review import _period_for
    with Session(app2.state.engine) as db:
        db.add(Period(id='period-closed-test', name='1111', start_date=date(2026, 1, 1), end_date=date(2026, 10, 31), state='CLOSED'))
        db.commit()
        for _ in range(3):  # 日期相同时不能靠编号碰运气
            assert _period_for(db, date(2026, 3, 1)).id == 'period2026'
        assert _period_for(db, date(2026, 3, 1)).state == 'OPEN'
