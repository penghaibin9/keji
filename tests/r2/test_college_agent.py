"""院长指定学院经办人和教研室负责人：经办人代院长办理学院一级审批，记录写明代办。

隔离夹具：college1 院长 collegehead（主身份）、dept1 教研室负责人 depthead；college2 没有院长。
"""
from datetime import date, timedelta
from sqlalchemy import select
from app.models import Rule, Assessment, User, WorkflowEvent, Setting
from conftest import auth, post
from support import HASH

REASON = '院长指定本院经办人'


def _teacher(app2, ident, staff, org='dept1', name=None):
    with app2.state.sessions.begin() as db:
        db.add(User(id=ident, username=ident, name=name or ('教师' + ident), staff_no=staff, org_id=org, role_id='role-teacher',
                    password_hash=HASH, must_change_password=False, active=True))


def _assessment(app2, ident, teacher, state='COLLEGE'):
    with app2.state.sessions.begin() as db:
        if db.get(Rule, 'ag-rule') is None:
            db.add(Rule(id='ag-rule', kind='assessment', name='经办人测试规则', version_no=1, period_id='period2026',
                config={'components': []}, fingerprint='e' * 64, state='ACTIVE', created_by='schooladmin', reason='测试'))
            db.flush()
        db.add(Assessment(id=ident, teacher_id=teacher, period_id='period2026', rule_id='ag-rule', score=80,
            detail=[], source_snapshot={}, state=state, version=1))


def _act(client, ident, action='confirm'):
    version = client.get('/api/assessments/' + ident).json()['assessment']['version']
    return post(client, f'/api/assessments/{ident}/actions', {'action': action, 'expected_version': version, 'reason': '核对无误'})


def _as_agent(client, username):
    me = auth(client, username)
    agent = [x for x in me['identities'] if x.get('agent')]
    assert agent, me['identities']
    r = post(client, '/api/auth/identity', {'identity_id': agent[0]['id']})
    assert r.status_code == 200, r.text
    me = client.get('/api/auth/me').json(); client.headers['x-csrf-token'] = me['csrf']
    return me


def _events(app2, ident):
    with app2.state.sessions.begin() as db:
        return [(e.actor_id, (e.after or {}).get('handling') or {}) for e in db.scalars(select(WorkflowEvent)
                .where(WorkflowEvent.object_id == ident).order_by(WorkflowEvent.created_at, WorkflowEvent.id))]


def test_dean_appoints_agents_who_act_on_behalf_of_the_dean(app2, client2):
    for n in (1, 2, 3):
        _teacher(app2, 'agent%d' % n, 'J10%d' % n)
    _assessment(app2, 'a-teacher', 'teacher')
    c = client2
    auth(c, 'collegehead')
    staff = c.get('/api/college/staff').json()
    assert [d['user_id'] for d in staff['deans']] == ['collegehead'] and staff['agents'] == [] and staff['max_agents'] == 2
    assert [d['id'] for d in staff['depts']] == ['dept1']
    assert 'agent1' in [x['id'] for x in c.get('/api/college/staff/candidates').json()['items']]
    # 只能选本学院老师；最多两位
    assert post(c, '/api/college/agents', {'user_id': 'otherteacher', 'reason': REASON}).status_code == 422
    until = (date.today() + timedelta(days=200)).isoformat()
    assert post(c, '/api/college/agents', {'user_id': 'agent1', 'reason': REASON, 'valid_until': until}).status_code == 200
    assert post(c, '/api/college/agents', {'user_id': 'agent2', 'reason': REASON}).status_code == 200
    assert post(c, '/api/college/agents', {'user_id': 'agent1', 'reason': REASON}).status_code == 409
    assert post(c, '/api/college/agents', {'user_id': 'agent3', 'reason': REASON}).status_code == 409
    agents = c.get('/api/college/staff').json()['agents']
    assert [(x['user_id'], x['valid_until'], x['delegated_by_name']) for x in agents] == [('agent1', until, '测试学院负责人'), ('agent2', None, '测试学院负责人')]
    # 管理员组织页分开显示院长和经办人
    auth(c, 'schooladmin')
    heads = {o['id']: o for o in c.get('/api/organizations').json()['items']}['college1']['heads']
    assert [(h['user_id'], h['agent']) for h in heads] == [('collegehead', False), ('agent1', True), ('agent2', True)]
    # 教师进度里列出院长和经办人
    me = _as_agent(c, 'agent1')
    assert me['role']['kind'] == 'college' and me['org']['id'] == 'college1'
    assert [x['role_name'] for x in me['identities'] if x.get('agent')] == ['学院经办人']
    # 经办人不能再往下指定
    assert c.get('/api/college/staff').status_code == 403
    assert post(c, '/api/college/agents', {'user_id': 'agent3', 'reason': REASON}).status_code == 403
    assert post(c, '/api/college/dept-heads', {'org_id': 'dept1', 'user_id': 'agent3', 'reason': REASON}).status_code == 403
    # 待办里有本院考核，代院长确认后记录写明代办
    assert any(t['id'] == 'a-teacher' for t in c.get('/api/todos').json()['items'])
    r = _act(c, 'a-teacher'); assert r.status_code == 200, r.text
    assert _events(app2, 'a-teacher') == [('agent1', {'agent_for': '经办人代 测试学院负责人 办理'})]
    # 院长撤销经办人
    auth(c, 'collegehead')
    assert post(c, '/api/college/agents/remove', {'user_id': 'agent2', 'reason': '调整分工'}).status_code == 200
    assert post(c, '/api/college/agents/remove', {'user_id': 'agent2', 'reason': '调整分工'}).status_code == 404
    assert [x['user_id'] for x in c.get('/api/college/staff').json()['agents']] == ['agent1']


def test_agent_never_handles_the_deans_own_items(app2, client2):
    _teacher(app2, 'agent1', 'J101'); _teacher(app2, 'dean2', 'J201', name='第二院长')
    with app2.state.sessions.begin() as db:
        db.get(User, 'collegehead').staff_no = 'J900'  # 院长本人也有考核
    c = client2
    auth(c, 'schooladmin')
    assert post(c, '/api/organizations/college1/heads', {'user_id': 'dean2', 'reason': '设第二位院长'}).status_code == 200
    auth(c, 'collegehead')
    assert post(c, '/api/college/agents', {'user_id': 'agent1', 'reason': REASON}).status_code == 200
    _assessment(app2, 'a-dean', 'collegehead')
    _as_agent(c, 'agent1')
    assert not any(t['id'] == 'a-dean' for t in c.get('/api/todos').json()['items'])
    r = _act(c, 'a-dean'); assert r.status_code == 403 and '经办人须回避' in r.json()['detail']
    me = auth(c, 'dean2')
    r = post(c, '/api/auth/identity', {'identity_id': me['identities'][1]['id']}); assert r.status_code == 200
    c.headers['x-csrf-token'] = c.get('/api/auth/me').json()['csrf']
    assert _act(c, 'a-dean').status_code == 200


def test_agent_lapses_with_the_dean_and_only_agents_means_vacancy(app2, client2):
    _teacher(app2, 'dean-c2', 'J301', org='dept2'); _teacher(app2, 'agent-c2', 'J302', org='dept2')
    _assessment(app2, 'a-other', 'otherteacher')
    c = client2
    auth(c, 'schooladmin')
    assert post(c, '/api/organizations/college2/heads', {'user_id': 'dean-c2', 'reason': '设院长'}).status_code == 200
    # 管理员也能设经办人，本院只有一位院长时默认代这位院长
    r = post(c, '/api/organizations/college2/heads', {'user_id': 'agent-c2', 'agent': True, 'reason': '管理员兜底设经办人'})
    assert r.status_code == 200, r.text and r.json()['on_behalf_of']['id'] == 'dean-c2'
    assert c.get('/api/assessments/a-other').json()['handler'] == {'kind': 'college', 'acting_for': None}
    # 院长被撤：经办人随之失效，学院按缺位交学校
    assert post(c, '/api/organizations/college2/heads/remove', {'user_id': 'dean-c2', 'reason': '院长调整'}).status_code == 200
    assert c.get('/api/assessments/a-other').json()['handler'] == {'kind': 'school', 'acting_for': '代缺位学院负责人办理'}
    me = auth(c, 'agent-c2')
    assert not [x for x in me['identities'] if x.get('agent')]
    # 经办人到期后同样失效
    auth(c, 'schooladmin')
    assert post(c, '/api/organizations/college2/heads', {'user_id': 'dean-c2', 'reason': '重新设院长'}).status_code == 200
    me = auth(c, 'agent-c2'); assert [x for x in me['identities'] if x.get('agent')]
    with app2.state.sessions.begin() as db:
        row = db.get(Setting, 'account_identities')
        row.value = {'items': [dict(x, valid_until='2020-01-01') if x.get('agent') else x for x in row.value['items']]}
    me = auth(c, 'agent-c2'); assert not [x for x in me['identities'] if x.get('agent')]


def test_dean_sets_dept_heads_only_inside_own_college(app2, client2):
    _teacher(app2, 'newhead', 'J401')
    c = client2
    auth(c, 'collegehead')
    assert post(c, '/api/college/dept-heads', {'org_id': 'dept2', 'user_id': 'otherteacher', 'reason': '设教研室负责人'}).status_code == 404
    assert post(c, '/api/college/dept-heads', {'org_id': 'dept1', 'user_id': 'otherteacher', 'reason': '设教研室负责人'}).status_code == 422
    assert post(c, '/api/college/dept-heads', {'org_id': 'dept1', 'user_id': 'newhead', 'reason': '设教研室负责人'}).status_code == 200
    heads = c.get('/api/college/staff').json()['depts'][0]['heads']
    assert sorted(h['user_id'] for h in heads) == ['depthead', 'newhead']
    # 主身份负责人要到账号管理调整
    assert post(c, '/api/college/dept-heads/remove', {'org_id': 'dept1', 'user_id': 'depthead', 'reason': '调整'}).status_code == 409
    assert post(c, '/api/college/dept-heads/remove', {'org_id': 'dept1', 'user_id': 'newhead', 'reason': '调整'}).status_code == 200
    # 教研室负责人、普通教师不能用本院人员授权
    auth(c, 'depthead'); assert c.get('/api/college/staff').status_code == 403
    auth(c, 'teacher'); assert c.get('/api/college/staff').status_code == 403


def test_agent_holds_dean_first_review_duty_for_its_dean(app2, client2):
    from app import social_training as st
    from app.identities import identity_actor, extras_for
    _teacher(app2, 'agent1', 'J101')
    auth(client2, 'collegehead')
    assert post(client2, '/api/college/agents', {'user_id': 'agent1', 'reason': REASON}).status_code == 200
    with app2.state.sessions.begin() as db:
        db.add(Setting(key='social_training_duties', value={'dean': ['collegehead']}))
    with app2.state.sessions() as db:
        user = db.get(User, 'agent1')
        ident = extras_for(db, 'agent1')[0]['id']
        agent = identity_actor(db, user, ident)
        assert 'dean' in st.actor_duties(db, agent)
        st.duty(db, agent, 'dean', 'teacher', 'college1')  # 普通教师的初审可以代办
        try:
            st.duty(db, agent, 'dean', 'collegehead', 'college1')
            raise AssertionError('经办人不能代院长初审院长本人的申报')
        except Exception as error:
            assert getattr(error, 'status_code', None) == 403
        assert 'dean' not in st.actor_duties(db, identity_actor(db, user, ''))  # 切回教师身份就没有


def test_agent_approves_course_application_and_progress_shows_it(app2, client2):
    from test_applications import setup, act
    setup(app2)
    _teacher(app2, 'agent1', 'J101')
    c = client2
    auth(c, 'collegehead')
    assert post(c, '/api/college/agents', {'user_id': 'agent1', 'reason': REASON}).status_code == 200
    auth(c, 'teacher')
    created = post(c, '/api/applications/courses', {'data': {'source': 'manual', 'code': 'AG-COURSE', 'name': '经办人审批课程',
        'hours': '8', 'teaching_mode': 'practice', 'ideology': 'course_ideology'}, 'reason': '提交申请'})
    assert created.status_code == 200, created.text
    ident = created.json()['item']['id']
    current = c.get('/api/applications/' + ident).json()['progress']
    auth(c, 'depthead'); assert act(c, ident, 'approve').status_code == 200
    auth(c, 'teacher')
    node = next(n for n in c.get('/api/applications/' + ident).json()['progress']['nodes'] if n['key'] == 'college')
    assert node['state'] == 'current' and node['who'] == '测试学院负责人、教师agent1（经办人）'
    _as_agent(c, 'agent1')
    review = {'checked': True, 'reviewer': '学院课件审查组', 'reviewed_on': '2026-10-18', 'reference': 'KJ-9', 'percent': 0}
    item = c.get('/api/applications/' + ident).json()['item']
    r = post(c, '/api/applications/' + ident + '/actions', {'action': 'approve', 'expected_version': item['version'], 'courseware': review, 'reason': '同意'})
    assert r.status_code == 200, r.text and r.json()['item']['state'] == 'SCHOOL'
    auth(c, 'teacher')
    node = next(n for n in c.get('/api/applications/' + ident).json()['progress']['nodes'] if n['key'] == 'college')
    assert node['state'] == 'done' and node['who'] == '教师agent1' and node['agent_for'] == '经办人代 测试学院负责人 办理'
    assert current['nodes'][1]['key'] == 'dept'


def test_me_tells_dean_and_agent_apart(app2, client2):
    _teacher(app2, 'agent1', 'J101')
    me = auth(client2, 'collegehead')
    assert me['college_dean'] is True and me['college_agent'] is None
    assert post(client2, '/api/college/agents', {'user_id': 'agent1', 'reason': REASON}).status_code == 200
    me = _as_agent(client2, 'agent1')
    assert me['college_dean'] is False and me['college_agent'] == {'on_behalf_of': '测试学院负责人'}
    me = auth(client2, 'depthead'); assert me['college_dean'] is False


def _extras(app2, items):
    with app2.state.sessions.begin() as db:
        row = db.get(Setting, 'account_identities')
        if row is None:
            db.add(Setting(key='account_identities', value={'items': items}))
        else:
            row.value = {'items': items}


def test_school_level_account_with_teacher_identity_here_can_be_chosen(app2, client2):
    # 主身份在学校级（学校管理员只能作主身份），兼任本院教研室负责人或教师：院长能搜到并设为经办人；
    # 别院的兼任、已到期的兼任、别人的经办人兼任都不算。
    with app2.state.sessions.begin() as db:
        db.add(User(id='schoolstaff', username='schoolstaff', name='学校级老师', staff_no='J777', org_id='school', role_id='role-school',
                    password_hash=HASH, must_change_password=False, active=True))
    c = client2
    auth(c, 'collegehead')

    def found():
        return [x['id'] for x in c.get('/api/college/staff/candidates?q=学校级').json()['items']]
    assert found() == []
    assert post(c, '/api/college/agents', {'user_id': 'schoolstaff', 'reason': REASON}).status_code == 422
    for extra in [{'role_id': 'role-dept', 'org_id': 'dept2'}, {'role_id': 'role-teacher', 'org_id': 'dept1', 'valid_until': '2020-01-01'},
                  {'role_id': 'role-college', 'org_id': 'college1', 'agent': True, 'delegated_by': 'collegehead'}]:
        _extras(app2, [{'id': 'x1', 'user_id': 'schoolstaff', 'granted_by': 'schooladmin', 'granted_at': '2026-11-02T00:00:00', 'reason': '兼任', **extra}])
        assert found() == [], extra
        assert post(c, '/api/college/agents', {'user_id': 'schoolstaff', 'reason': REASON}).status_code in (409, 422)
    for role in ('role-teacher', 'role-dept'):
        _extras(app2, [{'id': 'x1', 'user_id': 'schoolstaff', 'role_id': role, 'org_id': 'dept1', 'granted_by': 'schooladmin',
                        'granted_at': '2026-11-02T00:00:00', 'reason': '兼任本院'}])
        assert found() == ['schoolstaff'], role
    assert [x['id'] for x in c.get('/api/college/staff/candidates?q=J777').json()['items']] == ['schoolstaff']
    assert post(c, '/api/college/agents', {'user_id': 'schoolstaff', 'reason': REASON}).status_code == 200
    assert [x['user_id'] for x in c.get('/api/college/staff').json()['agents']] == ['schoolstaff']
    # 别院院长看不到
    auth(c, 'schooladmin')
    assert 'schoolstaff' not in [x['id'] for x in c.get('/api/organizations/college2/head-candidates?q=J777').json()['items']]
    assert 'schoolstaff' in [x['id'] for x in c.get('/api/organizations/dept1/head-candidates?q=J777').json()['items']]
