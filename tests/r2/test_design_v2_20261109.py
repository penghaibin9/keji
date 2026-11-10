"""2026-11-09 设计图 v2：老师三步列表（6 个状态）、学院学校待我审批、结项查缺、参与老师只能上传材料。"""
import uuid
from io import BytesIO
from PIL import Image
from app.models import User
from support import HASH
from conftest import auth, post
from test_social_training import setup_social, import_rows, row, action  # noqa: F401


def upload(c, pid, name='第1期签到表.png'):
    image = BytesIO(); Image.new('RGB', (2, 2), 'white').save(image, format='PNG')
    version = c.get('/api/social/objects/social_project/' + pid).json()['item']['version']
    return c.post('/api/attachments/social_project/' + pid, headers={'Idempotency-Key': str(uuid.uuid4())},
                  data={'expected_version': str(version), 'reason': '上传运行材料'}, files={'file': (name, image.getvalue(), 'image/png')})


def test_teacher_list_uses_six_statuses_and_stages(setup_social, client2):
    c = client2
    auth(c, 'teacher')
    items = c.get('/api/social/lifecycle/mine/project').json()['items']
    me = next(x for x in items if x['id'] == setup_social)
    assert me['status'] == 'run' and me['status_label'] == '运行中' and me['stage'] == 'run' and me['lead'] is True
    for kind in ('course', 'base', 'trainer'):
        assert c.get('/api/social/lifecycle/mine/' + kind).status_code == 200


def test_close_goes_to_college_queue_then_school_queue_with_gap_check(setup_social, client2):
    c = client2
    pid = setup_social
    assert import_rows(c, pid, [row()]).status_code == 200
    auth(c, 'teacher')
    r = c.get('/api/social/lifecycle/close-check/' + pid).json()  # 2026-11-10 起缺材料只提醒不拦
    assert not any('签到表' in g for g in r['gaps']) and any('签到表' in n for n in r['notes'])
    assert upload(c, pid).status_code == 200
    assert not any('签到表' in n for n in c.get('/api/social/lifecycle/close-check/' + pid).json()['notes'])
    closeout = {'closed_on': '2026-09-02', 'outcome_report': '结项报告', 'satisfaction': '96', 'actual_income': '0',
                'finance_reference': '零收入项目，无到账收入', 'location': 'onsite'}
    assert action(c, 'projects', 'social_project', pid, 'close_submit', closeout=closeout).status_code == 200
    assert next(x for x in c.get('/api/social/lifecycle/mine/project').json()['items'] if x['id'] == pid)['status'] == 'closing'
    auth(c, 'collegehead')
    q = c.get('/api/social/lifecycle/queue/project').json()['items']
    assert any(x['id'] == pid and x['kind'] == 'close' and x['action'] == 'approve' for x in q)
    assert action(c, 'projects', 'social_project', pid, 'approve').status_code == 200
    auth(c, 'reviewer')
    q = c.get('/api/social/lifecycle/queue/project').json()['items']
    item = next(x for x in q if x['id'] == pid)
    assert item['kind'] == 'close' and item['label'] == '结项核验' and item['batch'] is False
    review = c.get('/api/social/lifecycle/close-review/' + pid).json()
    assert review['files'] and review['archive']['name']


def test_participant_teacher_can_upload_but_not_change_or_close(setup_social, client2, app2):
    c = client2
    pid = setup_social
    with app2.state.sessions.begin() as db:
        db.add(User(id='member', username='member', name='参与教师', staff_no='J009', org_id='dept1', role_id='role-teacher', password_hash=HASH, must_change_password=False, active=True))
    member_row = {**row(), 'teachers': [{'teacher_id': 'teacher', 'staff_type': 'internal', 'role': 'lecturer'}, {'teacher_id': 'member', 'staff_type': 'internal', 'role': 'instructor'}]}
    assert import_rows(c, pid, [member_row]).status_code == 200
    auth(c, 'member')
    mine = c.get('/api/social/lifecycle/mine/project').json()['items']
    assert any(x['id'] == pid and x['lead'] is False for x in mine)
    view = c.get('/api/social/lifecycle/project/' + pid).json()
    assert view['can']['upload'] is True and view['can']['change'] is False and view['can']['close'] is False and view['lead'] is False
    assert upload(c, pid, '课堂照片.png').status_code == 200
    r = post(c, '/api/social/lifecycle/project/' + pid + '/changes', {'values': {'expected_participants': 40}, 'reason': '参与老师不能改'})
    assert r.status_code == 403
    assert action(c, 'projects', 'social_project', pid, 'close_submit', closeout={'closed_on': '2026-09-02'}).status_code in (403, 422)


def test_teacher_qualification_needs_only_name(client2):
    """2026-11-09：老师只填证书名称（加上传证书）；类别按名称归类，编号自动生成，取得日期记当天。"""
    from conftest import put
    c = client2
    auth(c, 'teacher')
    cats = c.get('/api/qualification-categories').json()['categories']
    r = post(c, '/api/qualifications', {'teacher_id': 'teacher', 'name': cats[0], 'reason': '申报本人资质证书'})
    assert r.status_code == 200, r.text
    q = r.json()
    assert q['category'] == cats[0] and q['certificate_no'].startswith('AUTO-') and q['obtained'] and q['issuer'] == ''
    r = post(c, '/api/qualifications', {'teacher_id': 'teacher', 'name': '茶艺师（高级）', 'reason': '申报本人资质证书'})
    assert r.status_code == 200 and r.json()['category'] == '其他', r.text
    other = r.json()
    r = put(c, '/api/qualifications/' + q['id'], {'teacher_id': 'teacher', 'name': cats[0] + '（复印件）', 'category': q['category'], 'expected_version': q['version'], 'reason': '改名称'})
    assert r.status_code == 200, r.text
    assert r.json()['certificate_no'] == q['certificate_no'] and r.json()['category'] == q['category']
    assert other['certificate_no'] != q['certificate_no']


def test_base_application_recognition_optional_until_school_approval(client2, app2):
    """2026-11-09：新申报基地时认定依据、设立日期、级别都选填；学校审批认定时必须有认定依据（审批人在“依据”里补）。"""
    from test_applications import act
    from test_social_training import setup_social  # noqa: F401
    from app.models import User, Setting
    with app2.state.sessions.begin() as db:
        if not db.get(User, 'reviewer'):
            db.add(User(id='reviewer', username='reviewer', name='隔离审核人', org_id='school', role_id='role-school', password_hash=HASH, must_change_password=False, active=True))
        if not db.get(Setting, 'social_training_duties'):
            db.add(Setting(key='social_training_duties', value={'coordinator': ['reviewer']}))
    c = client2
    auth(c, 'teacher')
    r = post(c, '/api/applications/bases', {'data': {'code': 'V2-B1', 'name': '简化基地', 'location': '实训楼', 'onsite': True, 'usages': ['practice']}, 'reason': '申请基地'})
    assert r.status_code == 200, r.text
    item = r.json()['item']
    assert item['data']['established_on'] and item['data']['level'] == 'school' and item['data']['recognition'] == ''
    auth(c, 'collegehead')
    assert act(c, item['id'], 'approve').status_code == 200
    auth(c, 'reviewer')
    r = act(c, item['id'], 'approve')
    assert r.status_code == 422 and '认定依据' in r.text, r.text
    version = c.get('/api/applications/' + item['id']).json()['item']['version']
    r = post(c, '/api/applications/' + item['id'] + '/actions', {'action': 'approve', 'expected_version': version, 'reason': '同意', 'basis': '学院会议纪要（2026-11-01）'})
    assert r.status_code == 200, r.text
    assert c.get('/api/applications/' + item['id']).json()['item']['data']['recognition'] == '学院会议纪要（2026-11-01）'


def test_close_check_lists_not_ended_and_report_info(setup_social, client2, app2):
    """结项查缺也列出“培训还没结束”和“还要补上报信息”，不要等到结项表里才报错。"""
    from app.social_models import SocialProject
    with app2.state.sessions.begin() as db:
        p = db.get(SocialProject, setup_social)
        p.data = {**p.data, 'end_date': '2099-12-31', 'report_pending': True, 'audiences': [], 'audience_other': '', 'service_types': []}
    auth(client2, 'teacher')
    gaps = client2.get('/api/social/lifecycle/close-check/' + setup_social).json()['gaps']
    assert any('2099-12-31' in g and '结束后才能结项' in g for g in gaps), gaps
    assert any('上报信息' in g for g in gaps), gaps


def test_teacher_close_check_no_longer_blocks_on_missing_units(setup_social, client2):
    """9e98fb3 起老师结项不被参训明细拦：查缺不再列明细；学院结项审核时队列标出明细数，没明细不进批量。"""
    auth(client2, 'teacher')
    gaps = client2.get('/api/social/lifecycle/close-check/' + setup_social).json()['gaps']
    assert not any('参训明细' in g for g in gaps), gaps
