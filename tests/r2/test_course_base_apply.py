"""培训课程、培训基地改为申请：学院登记的直接到学校审批；学校直接登记带五项资料；八列导入；基地三项资料与清单可见范围。"""
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import User
from app.social_models import SocialResource
from conftest import auth, post
from test_social_training import setup_social  # noqa: F401  复用：学校建项目 SOC-P1 并备案、登记课程 SOC-C1
from test_social_training import HASH

REVIEW = {'checked': True, 'reviewer': '学院课件审查组', 'reviewed_on': '2026-09-01'}


def act(c, ident, action, reason='审核意见：同意'):
    item = c.get('/api/applications/' + ident).json()['item']
    return post(c, '/api/applications/' + ident + '/actions', {'action': action, 'expected_version': item['version'], 'reason': reason})


def courses(c):
    r = c.get('/api/social/workspace', params={'section': 'courses'})
    assert r.status_code == 200, r.text
    return r.json()


def test_college_course_application_skips_college_level_and_shows_five_fields(setup_social, client2):
    c = client2
    auth(c, 'collegehead')
    # 学院不能再直接往课程库里登记，要走申请。
    assert post(c, '/api/social/courses', {'code': 'SOC-C9', 'name': '学院直登', 'project_code': 'SOC-P1', 'reason': '学院登记'}).status_code == 403
    data = {'source': 'manual', 'code': 'SOC-C3', 'name': '茶艺实训', 'project_code': 'SOC-P1', 'teacher_id': 'teacher', 'hours': '16',
            'teaching_mode': 'practice', 'ideology': 'course_ideology', 'courseware': REVIEW}
    r = post(c, '/api/applications/courses', {'data': data, 'reason': '学院代老师申请'})
    assert r.status_code == 200, r.text
    d = r.json()
    ident = d['item']['id']
    assert d['item']['state'] == 'SCHOOL'
    college = d['progress']['nodes'][1]
    assert college['state'] == 'done' and college['acting_for'] == '学院登记时已确认'
    # 撤回后再交，仍然直接到学校。
    assert act(c, ident, 'withdraw', '先撤回').json()['item']['state'] == 'WITHDRAWN'
    assert act(c, ident, 'submit', '重新提交').json()['item']['state'] == 'SCHOOL'
    auth(c, 'reviewer')
    assert act(c, ident, 'approve').json()['item']['state'] == 'ACTIVE'
    info = courses(c)['course_info']['SOC-C3']
    assert info['hours'] == '16' and info['teaching_mode'] == 'practice' and info['teacher_name'] == '测试教师一'
    assert info['courseware']['checked'] and info['application_id'] == ident


def test_school_registers_and_imports_courses_with_five_fields(setup_social, client2):
    c = client2
    auth(c, 'reviewer')
    r = post(c, '/api/social/courses', {'code': 'SOC-C4', 'name': '直接登记课', 'project_code': 'SOC-P1', 'hours': 8, 'teaching_mode': 'lecture',
                                        'ideology': 'none', 'teacher_id': 'teacher', 'courseware': {'checked': False}, 'reason': '学校登记'})
    assert r.status_code == 200, r.text
    bad = {'code': 'SOC-C5', 'name': '缺审查人', 'project_code': 'SOC-P1', 'courseware': {'checked': True}, 'reason': '学校登记'}
    assert post(c, '/api/social/courses', bad).status_code == 422
    rows = [{'code': 'SOC-C6', 'name': '导入课一', 'project_code': 'SOC-P1', 'hours': '12', 'teaching_mode': 'case', 'ideology': 'ideology_course',
             'teacher': '测试教师一', 'courseware': REVIEW, 'reason': '批量导入'},
            {'code': 'SOC-C7', 'name': '导入课二', 'project_code': 'SOC-P1', 'reason': '批量导入'}]
    data = {'rows': rows, 'reason': '批量导入'}
    preview = post(c, '/api/social/courses/import/preview', data)
    assert preview.status_code == 200, preview.text
    assert post(c, '/api/social/courses/import/confirm', {**data, 'preview_hash': preview.json()['preview_hash']}).status_code == 200
    info = courses(c)['course_info']
    assert info['SOC-C4']['hours'] == '8' and info['SOC-C4']['teacher_name'] == '测试教师一' and info['SOC-C4']['application_id'] is None
    assert info['SOC-C6']['ideology'] == 'ideology_course' and info['SOC-C6']['courseware']['reviewer'] == '学院课件审查组'
    assert 'SOC-C7' not in info and 'SOC-C1' not in info  # 没填五项的不建资料记录
    auth(c, 'collegehead')
    assert post(c, '/api/social/courses/import/preview', data).status_code == 403


def test_base_fields_and_pending_applications_hidden_from_other_teachers(setup_social, client2, app2):
    c = client2
    with app2.state.sessions.begin() as db:
        t = db.get(User, 'teacher')
        db.add(User(id='peer', username='peer', name='同室老师', staff_no='J009', org_id=t.org_id, role_id=t.role_id,
                    password_hash=HASH, must_change_password=False, active=True))
    auth(c, 'reviewer')
    r = post(c, '/api/social/resources', {'kind': 'base', 'org_id': setup_org(app2), 'code': 'BASE-S1', 'name': '学校登记基地', 'recognition': '学校发文',
                                          'onsite': False, 'partner': '湘茶集团', 'usages': ['ideology'], 'established_on': '2026-03-01', 'reason': '学校登记'})
    assert r.status_code == 200, r.text
    assert r.json()['item']['data']['usages'] == ['ideology'] and r.json()['item']['data']['partner'] == '湘茶集团'
    auth(c, 'teacher')
    data = {'code': 'BASE-T9', 'name': '待批基地', 'onsite': True, 'recognition': '学院会议纪要', 'usages': ['practice'], 'established_on': '2026-09-01'}
    assert post(c, '/api/applications/bases', {'data': data, 'reason': '申请基地'}).status_code == 200
    codes = lambda: {x['code'] for x in c.get('/api/social/workspace', params={'section': 'bases'}).json()['resources']}
    assert {'BASE-S1', 'BASE-T9'} <= codes()
    auth(c, 'peer')
    assert 'BASE-T9' not in codes() and 'BASE-S1' in codes()
    auth(c, 'depthead')
    assert 'BASE-T9' in codes()
    auth(c, 'collegehead')
    data = {**data, 'code': 'BASE-C1', 'teacher_id': 'teacher'}
    r = post(c, '/api/applications/bases', {'data': data, 'reason': '学院代登记'})
    assert r.status_code == 200 and r.json()['item']['state'] == 'SCHOOL', r.text


def setup_org(app2):
    with Session(app2.state.engine) as db:
        return db.scalar(select(SocialResource.org_id).limit(1)) or db.get(User, 'collegehead').org_id
