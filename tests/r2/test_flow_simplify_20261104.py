"""2026-11-04 流程精简：三条新链路、在途旧链路按原链走完、学校勾选结项材料、积分认定退回后从原级续审、学校审批职责页签用到的接口。

默认意见只是前端预填：后端仍要求本人提交的请求里带办理说明，退回仍须写原因，本人申请仍被拦。
"""
from datetime import date
from sqlalchemy.orm import Session
from app.models import User, Setting
from app.social_models import SocialResource, SocialProject, SocialClaim
from app import social_training as st
from conftest import auth, post, put
from test_social_training import HASH, setup_social, import_rows, row, action, detail, proof, policy  # noqa: F401
from test_applications import setup as app_setup, apply_course, act, todo_ids

MATERIALS = ['plan', 'filing_form', 'roster', 'attendance', 'hours', 'process', 'assessment', 'outcomes']
CLOSEOUT = {'closed_on': '2026-09-02', 'outcome_report': '合成完整结项报告', 'satisfaction': '96', 'actual_income': '0',
            'finance_reference': '合成零收入核验', 'location': 'onsite'}


def approve(c, ident, basis=''):
    item = c.get('/api/applications/' + ident).json()['item']
    return post(c, '/api/applications/' + ident + '/actions', {'action': 'approve', 'expected_version': item['version'], 'reason': '审核意见：同意', 'basis': basis})


def trainer_setup(app2):
    with app2.state.sessions.begin() as db:
        for ident, name in (('reviewer', '继续教育学院审核人'), ('hruser', '组织人事部办理人')):
            db.add(User(id=ident, username=ident, name=name, org_id='school', role_id='role-school', password_hash=HASH, must_change_password=False, active=True))
        db.add(Setting(key='social_training_duties', value={'coordinator': ['reviewer'], 'trainer_hr': ['hruser']}))


def internal_trainer(c):
    data = {'source': 'internal', 'directions': ['community'], 'qualification_basis': '讲师，十年职业技能培训经验'}
    return post(c, '/api/applications/trainers', {'data': data, 'reason': '提交申请'})


# ---- 丙：三条新链路 ----

def test_new_course_chain_is_college_then_school(app2, client2):
    c = client2
    ids = app_setup(app2)
    auth(c, 'teacher')
    d = apply_course(c, ids['K1']).json()
    ident = d['item']['id']
    assert d['item']['state'] == 'COLLEGE' and d['item']['data']['chain'] == 2
    assert [n['label'] for n in d['progress']['nodes']] == ['提交', '学院审批', '学校审批', '进入培训课程库']
    assert act(c, ident, 'approve').status_code == 403  # 本人申请仍被拦
    auth(c, 'depthead')
    assert ident not in todo_ids(c)  # 教研室不再审培训课程
    assert act(c, ident, 'approve').status_code == 403
    auth(c, 'collegehead')
    assert ident in todo_ids(c)
    r = act(c, ident, 'return', '')
    assert r.status_code == 422  # 退回仍须写原因
    r = act(c, ident, 'return', '请补充课件审查记录')
    assert r.status_code == 200 and r.json()['item']['state'] == 'RETURNED'
    auth(c, 'teacher')
    assert act(c, ident, 'submit', '已补正').json()['item']['state'] == 'COLLEGE'
    auth(c, 'collegehead')
    assert act(c, ident, 'approve').json()['item']['state'] == 'SCHOOL'
    auth(c, 'reviewer')
    d = act(c, ident, 'approve').json()
    assert d['item']['state'] == 'ACTIVE' and [n['state'] for n in d['progress']['nodes']] == ['done'] * 4


def test_dept_registered_course_goes_to_college(app2, client2):
    c = client2
    app_setup(app2)
    auth(c, 'depthead')
    data = {'source': 'manual', 'code': 'SIMP-C1', 'name': '教研室代登记', 'teacher_id': 'teacher', 'hours': '8', 'teaching_mode': 'lecture', 'ideology': 'none'}
    r = post(c, '/api/applications/courses', {'data': data, 'reason': '代老师登记'})
    assert r.status_code == 200 and r.json()['item']['state'] == 'COLLEGE', r.text


def test_new_internal_trainer_chain_is_college_then_hr(app2, client2):
    c = client2
    trainer_setup(app2)
    auth(c, 'teacher')
    d = internal_trainer(c).json()
    ident = d['item']['id']
    assert d['item']['state'] == 'COLLEGE'
    assert [n['label'] for n in d['progress']['nodes']] == ['提交', '学院审批', '组织人事部认定', '进入培训师资']
    auth(c, 'collegehead')
    assert approve(c, ident).json()['item']['state'] == 'HR'
    auth(c, 'reviewer')
    assert ident not in todo_ids(c)  # 学校一级已去掉
    auth(c, 'hruser')
    assert approve(c, ident).status_code == 422  # 认定依据仍必填
    assert approve(c, ident, '湘科人认〔2026〕12号').json()['item']['state'] == 'ACTIVE'


def test_project_close_goes_college_then_school_and_school_ticks_materials(setup_social, client2, app2, monkeypatch):
    # 2026-11-09 用户定：结项恢复为学院审核 → 学校核验（原 2026-11-04 精简为直接到学校）。
    c = client2
    pid = setup_social
    assert import_rows(c, pid, [row()]).status_code == 200
    auth(c, 'teacher')
    r = action(c, 'projects', 'social_project', pid, 'close_submit', closeout=CLOSEOUT)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d['item']['state'] == 'CLOSE_COLLEGE' and d['item']['data']['close_chain'] == 2
    assert [n['label'] for n in d['progress']['nodes']] == ['提交', '学院审批', '学校审批', '已结项']
    auth(c, 'reviewer')
    assert action(c, 'projects', 'social_project', pid, 'close', materials_checked=MATERIALS).status_code == 409  # 学院没审核前学校不能核验
    auth(c, 'collegehead')
    r = action(c, 'projects', 'social_project', pid, 'approve')
    assert r.status_code == 200 and r.json()['item']['state'] == 'CLOSE_REVIEW', r.text
    auth(c, 'reviewer')
    r = action(c, 'projects', 'social_project', pid, 'close', materials_checked=[])
    assert r.status_code == 409 and '勾选' in r.text  # 明确不勾不能过；不传按点“同意”即核对过
    r = action(c, 'projects', 'social_project', pid, 'close', materials_checked=MATERIALS[:-1])
    assert r.status_code == 409
    r = action(c, 'projects', 'social_project', pid, 'close', materials_checked=MATERIALS)
    assert r.status_code == 200, r.text
    closed = r.json()['item']
    assert closed['state'] == 'CLOSED' and set(closed['closeout']['materials_checked']) == set(MATERIALS)
    assert closed['closeout']['materials_checked_by'] == 'reviewer'


def test_quality_reviews_are_added_automatically_at_school_close(setup_social, client2, app2):
    c = client2
    pid = setup_social
    assert import_rows(c, pid, [row()]).status_code == 200
    with app2.state.sessions.begin() as db:
        p = db.get(SocialProject, pid)
        p.data = {**p.data, 'quality': {'teacher_review': {'percent': 100}, 'courseware_review': {'percent': 90}}}
    auth(c, 'teacher')
    assert action(c, 'projects', 'social_project', pid, 'close_submit', closeout=CLOSEOUT).status_code == 200
    auth(c, 'collegehead')
    assert action(c, 'projects', 'social_project', pid, 'approve').status_code == 200
    auth(c, 'reviewer')
    r = action(c, 'projects', 'social_project', pid, 'close', materials_checked=MATERIALS)
    assert r.status_code == 200, r.text
    assert {'teacher_review', 'courseware_review'} <= set(r.json()['item']['closeout']['materials_checked'])


def test_teacher_close_only_needs_outcome_report_and_school_records_review(setup_social, client2):
    # 2026-11-09 管理办法第十三条：老师结项只交成果报告；满意度（第十四条）和财务（第二十一条）由学校结项核验时登记。
    c = client2
    pid = setup_social
    auth(c, 'teacher')
    r = action(c, 'projects', 'social_project', pid, 'close_submit', closeout={'closed_on': CLOSEOUT['closed_on'], 'outcome_report': '结项报告'})
    assert r.status_code == 200, r.text  # 没有参训明细也能提交
    auth(c, 'collegehead')
    r = action(c, 'projects', 'social_project', pid, 'approve')
    assert r.status_code == 409 and '老师还没上传参训明细表' in r.text  # 老师上传明细后才能通过
    assert import_rows(c, pid, [row()]).status_code == 200
    assert action(c, 'projects', 'social_project', pid, 'approve').status_code == 200
    auth(c, 'reviewer')
    r = action(c, 'projects', 'social_project', pid, 'close', materials_checked=MATERIALS, review={'satisfaction': '80'})
    assert r.status_code == 422 and '整改期限' in r.text
    r = action(c, 'projects', 'social_project', pid, 'close', materials_checked=MATERIALS, review={'satisfaction': '80', 'rectification_due': '2026-12-31'})
    assert r.status_code == 200, r.text
    z = r.json()['item']['closeout']
    assert z['finance_reference'] == '零收入项目，无到账收入' and z['rectification_due'] == '2026-12-31'


# ---- 在途旧链路按原链走完 ----

def test_in_flight_course_on_old_chain_finishes_dept_college_school(app2, client2):
    c = client2
    ids = app_setup(app2)
    auth(c, 'teacher')
    ident = apply_course(c, ids['K1']).json()['item']['id']
    with app2.state.sessions.begin() as db:  # 模拟精简前提交、停在教研室的申请
        obj = db.get(SocialResource, ident)
        obj.data = {k: v for k, v in obj.data.items() if k != 'chain'}
        obj.state = 'DEPT'
    d = c.get('/api/applications/' + ident).json()
    assert [n['label'] for n in d['progress']['nodes']] == ['提交', '教研室审核', '学院审批', '学校审批', '进入培训课程库']
    for user, after in (('depthead', 'COLLEGE'), ('collegehead', 'SCHOOL'), ('reviewer', 'ACTIVE')):
        auth(c, user)
        r = act(c, ident, 'approve')
        assert r.status_code == 200 and r.json()['item']['state'] == after, r.text


def test_in_flight_trainer_on_old_chain_keeps_school_level(app2, client2):
    c = client2
    trainer_setup(app2)
    auth(c, 'teacher')
    ident = internal_trainer(c).json()['item']['id']
    with app2.state.sessions.begin() as db:
        obj = db.get(SocialResource, ident)
        obj.data = {k: v for k, v in obj.data.items() if k != 'chain'}
    auth(c, 'collegehead')
    assert approve(c, ident).json()['item']['state'] == 'SCHOOL'  # 旧链：学院之后还到学校
    auth(c, 'reviewer')
    assert approve(c, ident).json()['item']['state'] == 'HR'
    auth(c, 'hruser')
    assert approve(c, ident, '认定〔2026〕1号').json()['item']['state'] == 'ACTIVE'


def test_withdrawn_old_course_resubmits_on_new_chain(app2, client2):
    c = client2
    ids = app_setup(app2)
    auth(c, 'teacher')
    ident = apply_course(c, ids['K1']).json()['item']['id']
    with app2.state.sessions.begin() as db:
        obj = db.get(SocialResource, ident)
        obj.data = {k: v for k, v in obj.data.items() if k != 'chain'}
        obj.state = 'DEPT'
    assert act(c, ident, 'withdraw', '撤回修改').json()['item']['state'] == 'WITHDRAWN'
    d = act(c, ident, 'submit', '重新提交').json()
    assert d['item']['state'] == 'COLLEGE' and d['item']['data']['chain'] == 2


def test_in_flight_close_at_college_still_finishes(setup_social, client2, app2):
    c = client2
    pid = setup_social
    assert import_rows(c, pid, [row()]).status_code == 200
    auth(c, 'teacher')
    assert action(c, 'projects', 'social_project', pid, 'close_submit',
                  closeout={**CLOSEOUT, 'materials_checked': MATERIALS}).status_code == 200
    with app2.state.sessions.begin() as db:  # 模拟精简前提交、停在学院结项核验、老师已勾过材料
        p = db.get(SocialProject, pid)
        p.state = 'CLOSE_COLLEGE'
        p.data = {k: v for k, v in p.data.items() if k != 'close_chain'}
    d = detail(c, 'social_project', pid)
    assert [n['label'] for n in d['progress']['nodes']] == ['提交', '学院审批', '学校审批', '已结项']
    auth(c, 'collegehead')
    r = action(c, 'projects', 'social_project', pid, 'approve')
    assert r.status_code == 200 and r.json()['item']['state'] == 'CLOSE_REVIEW', r.text
    auth(c, 'reviewer')
    r = action(c, 'projects', 'social_project', pid, 'close')  # 老师在途勾过的核对项沿用
    assert r.status_code == 200 and r.json()['item']['state'] == 'CLOSED', r.text


# ---- 积分认定：退回后从原级续审 ----

def test_claim_return_resumes_at_returned_level(setup_social, client2, app2, monkeypatch):
    monkeypatch.setattr(st, 'today', lambda: date(2026, 9, 3))
    c = client2
    pid = setup_social
    assert import_rows(c, pid, [row()]).status_code == 200
    auth(c, 'schooladmin')
    r = action(c, 'projects', 'social_project', pid, 'close_submit', closeout={**CLOSEOUT, 'materials_checked': MATERIALS})
    assert r.status_code == 200, r.text
    auth(c, 'reviewer')
    assert action(c, 'projects', 'social_project', pid, 'close').status_code == 200
    pol = policy(c, True, resubmission_mode='original_submission')
    auth(c, 'teacher')
    r = post(c, '/api/social/claims', {'project_id': pid, 'period_id': 'period2026', 'policy_id': pol, 'recognition_form_reference': '认定表', 'reason': '本人申报'})
    assert r.status_code == 200, r.text
    claim = r.json()['item']
    proof(c, 'social_claim', claim['id'], claim['version'])
    assert action(c, 'claims', 'social_claim', claim['id'], 'submit').status_code == 200
    # 2026-11-09 三级：教研室 → 学院 → 学校
    for user in ('depthead', 'collegehead'):
        auth(c, user)
        r = action(c, 'claims', 'social_claim', claim['id'], 'approve')
        assert r.status_code == 200, r.text
    auth(c, 'reviewer')
    item = detail(c, 'social_claim', claim['id'])['item']
    assert item['state'] == 'SCHOOL'
    r = post(c, '/api/social/claims/' + claim['id'] + '/actions', {'action': 'return', 'expected_version': item['version'], 'reason': ''})
    assert r.status_code == 422  # 退回仍须写原因
    r = action(c, 'claims', 'social_claim', claim['id'], 'return')
    assert r.status_code == 200 and r.json()['item']['state'] == 'RETURNED'
    auth(c, 'teacher')
    r = action(c, 'claims', 'social_claim', claim['id'], 'submit')
    assert r.status_code == 200, r.text
    assert r.json()['item']['state'] == 'SCHOOL'  # 从学校这一级接着审，不回教研室
    for user, after in (('reviewer', 'ARCHIVED'),):
        auth(c, user)
        r = action(c, 'claims', 'social_claim', claim['id'], 'approve')
        assert r.status_code == 200 and r.json()['item']['state'] == after, r.text


def test_reason_is_still_required_from_the_person_who_acts(setup_social, client2):
    c = client2
    pid = setup_social
    assert import_rows(c, pid, [row()]).status_code == 200
    auth(c, 'teacher')
    item = detail(c, 'social_project', pid)['item']
    r = post(c, '/api/social/projects/' + pid + '/actions', {'action': 'close_submit', 'expected_version': item['version'], 'closeout': CLOSEOUT})
    assert r.status_code == 422  # 没有办理说明不办理：默认意见只是前端预填，须本人点确认提交


# ---- 乙：学校审批职责页签用到的接口 ----

def test_duties_tab_reads_people_usable_and_options_account(app2, client2):
    c = client2
    with app2.state.sessions.begin() as db:
        db.add(User(id='reviewer', username='reviewer', name='学校审核人', org_id='school', role_id='role-school', password_hash=HASH, must_change_password=False, active=True))
        db.add(User(id='gone', username='gone', name='停用审核人', org_id='school', role_id='role-school', password_hash=HASH, must_change_password=False, active=False))
        db.add(Setting(key='social_training_duties', value={'coordinator': ['reviewer', 'gone'], 'dean': ['collegehead']}))
    auth(c, 'schooladmin')
    d = c.get('/api/social/duties').json()
    assert set(d['labels']) >= {'dean', 'coordinator', 'trainer_hr'} and 'dean' not in d['school_duties']
    people = {p['id']: p for p in d['people']}
    assert people['reviewer']['usable'] is True and people['gone']['usable'] is False
    opts = c.get('/api/social/duty-options', params={'duty': 'coordinator', 'q': '测试教师一'}).json()['items']
    teacher = next(x for x in opts if x['id'] == 'teacher')
    assert teacher['eligible'] is False and teacher['account']['role_id'] and 'extra_identities' in teacher['account']
    # 页签“添加”：按最新版本只改这一个职责
    r = c.put('/api/social/duties', json={'expected_version': d['version'], 'assignments': {**d['assignments'], 'trainer_hr': ['reviewer']}, 'reason': '指定组织人事部认定人'},
              headers={'Idempotency-Key': 'simplify-duty-0001'})
    assert r.status_code == 200, r.text
    d2 = c.get('/api/social/duties').json()
    assert d2['assignments']['trainer_hr'] == ['reviewer'] and d2['assignments']['coordinator'] == ['reviewer', 'gone']
    # 旧版本号保存被拒，避免覆盖
    r = c.put('/api/social/duties', json={'expected_version': d['version'], 'assignments': {}, 'reason': '过期页面'}, headers={'Idempotency-Key': 'simplify-duty-0002'})
    assert r.status_code == 409
    # 没有学校审核身份的人不能直接加入学校职责
    r = c.put('/api/social/duties', json={'expected_version': d2['version'], 'assignments': {**d2['assignments'], 'coordinator': ['reviewer', 'teacher']}, 'reason': '加人'},
              headers={'Idempotency-Key': 'simplify-duty-0003'})
    assert r.status_code == 422
    # 移除
    r = c.put('/api/social/duties', json={'expected_version': d2['version'], 'assignments': {**d2['assignments'], 'coordinator': ['reviewer']}, 'reason': '移除停用账号'},
              headers={'Idempotency-Key': 'simplify-duty-0004'})
    assert r.status_code == 200, r.text
    assert c.get('/api/social/duties').json()['assignments']['coordinator'] == ['reviewer']
