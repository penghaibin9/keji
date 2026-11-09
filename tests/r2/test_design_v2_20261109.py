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
    gaps = c.get('/api/social/lifecycle/close-check/' + pid).json()['gaps']
    assert any('签到表' in g and '不计积分' in g for g in gaps)
    assert upload(c, pid).status_code == 200
    gaps = c.get('/api/social/lifecycle/close-check/' + pid).json()['gaps']
    assert not any('签到表' in g for g in gaps)
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
