"""培训项目开放老师申报：学院审批 → 学校备案；申报不要求填思政内容，总学时和受众群体必填；学院补填历史项目上报信息。"""
from sqlalchemy import select
from app.models import User, Setting
from app.social_models import SocialResource
from conftest import auth, post, put
from support import HASH
from test_social_training import payload, proof, action, detail

QUALITY = {'ideology_modes': ['course_ideology', 'practice'], 'ideology_hours': '4',
           'bases': [{'name': '湘茶思政实践基地'}],
           'teacher_review': {'percent': 100}, 'courseware_review': {'percent': 80}}


def setup(app2):
    with app2.state.sessions.begin() as db:
        db.add(User(id='reviewer', username='reviewer', name='继续教育学院审核人', org_id='school', role_id='role-school', password_hash=HASH, must_change_password=False, active=True))
        db.add(Setting(key='social_training_duties', value={'coordinator': ['reviewer']}))


def teacher_project(c, **data):
    p = payload()
    p['data'].update(data)
    r = post(c, '/api/social/projects', p)
    assert r.status_code == 200, r.text
    return r.json()['item']


def test_teacher_project_goes_college_then_school_and_application_needs_no_ideology_data(app2, client2):
    c = client2
    setup(app2)
    auth(c, 'teacher')
    assert post(c, '/api/social/projects', {**payload(), 'data': {**payload()['data'], 'owner_id': 'otherteacher'}}).status_code == 403
    p = teacher_project(c)
    proof(c, 'social_project', p['id'], p['version'])
    r = action(c, 'projects', 'social_project', p['id'], 'submit')
    assert r.status_code == 409 and all(x in r.text for x in ('总学时', '受众群体', '服务面向类型', '教学实施方式'))  # 申报只拦这四项
    d = detail(c, 'social_project', p['id'])
    r = put(c, '/api/social/projects/' + p['id'], {**payload(), 'expected_version': d['item']['version'],
            'data': {**payload()['data'], 'total_hours': '16', 'audiences': ['企业职工'], 'service_types': ['national'], 'teaching_methods': ['classroom', 'case'], 'video_minutes': 120, 'base_count': 2}})
    assert r.status_code == 200, r.text
    r = action(c, 'projects', 'social_project', p['id'], 'submit')
    assert r.status_code == 200, r.text
    assert r.json()['item']['state'] == 'COLLEGE' and r.json()['progress']['text'].startswith('学院审批中')
    auth(c, 'reviewer')
    assert action(c, 'projects', 'social_project', p['id'], 'file').status_code == 409  # 学院还没审
    auth(c, 'collegehead')
    todos = c.get('/api/todos', params={'type': 'social_project'}).json()['items']
    assert any(x['id'] == p['id'] and '学院审批' in x['title'] for x in todos)
    r = action(c, 'projects', 'social_project', p['id'], 'college_return')
    assert r.status_code == 200 and r.json()['item']['state'] == 'RETURNED'
    auth(c, 'teacher')
    assert action(c, 'projects', 'social_project', p['id'], 'submit').json()['item']['state'] == 'COLLEGE'
    auth(c, 'collegehead')
    assert action(c, 'projects', 'social_project', p['id'], 'approve').json()['item']['state'] == 'SUBMITTED'
    auth(c, 'reviewer')
    r = action(c, 'projects', 'social_project', p['id'], 'file')
    assert r.status_code == 200, r.text
    nodes = r.json()['progress']['nodes']
    assert [n['state'] for n in nodes] == ['done'] * 4
    auth(c, 'teacher')
    mine = c.get('/api/applications/mine').json()['items']
    assert any(x['id'] == p['id'] and x['progress']['tone'] == 'green' for x in mine)


def test_college_registered_project_skips_college_level_and_can_fill_report_info(app2, client2):
    c = client2
    setup(app2)
    auth(c, 'collegehead')
    p = teacher_project(c)
    proof(c, 'social_project', p['id'], p['version'])
    r = action(c, 'projects', 'social_project', p['id'], 'submit')
    assert r.status_code == 200 and r.json()['item']['state'] == 'SUBMITTED'
    assert r.json()['report_issues']  # 学院登记的不拦，但标出缺项
    assert r.json()['progress']['nodes'][1]['state'] == 'done'
    assert put(c, '/api/social/projects/' + p['id'] + '/report-info', {'expected_version': r.json()['item']['version'], 'service_types': ['regional'], 'reason': '补填'}).status_code == 409
    auth(c, 'reviewer')
    item = action(c, 'projects', 'social_project', p['id'], 'file').json()['item']
    auth(c, 'teacher')
    assert put(c, '/api/social/projects/' + p['id'] + '/report-info', {'expected_version': item['version'], 'service_types': ['regional'], 'reason': '补填'}).status_code == 403
    auth(c, 'collegehead')
    r = put(c, '/api/social/projects/' + p['id'] + '/report-info', {'expected_version': item['version'], 'total_hours': '16', 'audiences': ['社区居民'], 'service_types': ['regional'], 'teaching_methods': ['case'], 'video_minutes': 120, 'base_count': 2, 'reason': '补填历史项目上报信息'})
    assert r.status_code == 200, r.text
    assert r.json()['report_issues'] == [] and r.json()['item']['state'] == 'FILED'
    assert any(e['action'] == '补填上报信息' for e in r.json()['events'])
