"""老师发起的申请走通用审批：社会培训课 教研室→学院→学校，培训基地 学院→学校。

覆盖：逐级办理、退回后从退回那一级接着审、本人回避、缺负责人上交代办、同一人连审、进度显示、我的申请、待办、积分。
"""
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import User, Setting, PointEntry
from app.reference_data import TeacherCourseTerm, TrainingCourseMaster
from conftest import auth, post, put
from test_social_training import HASH

REASON = {'reason': '提交申请'}


def setup(app2, *, coordinator='reviewer'):
    with app2.state.sessions.begin() as db:
        db.add(User(id='reviewer', username='reviewer', name='继续教育学院审核人', org_id='school', role_id='role-school',
                    password_hash=HASH, must_change_password=False, active=True))
        db.add(Setting(key='social_training_duties', value={'coordinator': [coordinator]}))
        for code, name, term, origin, extra in [('K1', '高等数学', '2025-2026-1', 'JW', {}), ('X1', '高数线上版', '2025-2026-1', 'CX', {'jw_course_code': 'K1', 'course_url': 'https://mooc.example/x1'}),
                                                ('X2', '茶艺入门', '2024-2025-2', 'CX', {'chapters': 12}), ('K0', '旧课', '2019-2020-1', 'JW', {})]:
            db.add(TeacherCourseTerm(external_key=origin + '|J001|' + code + '|' + term, origin=origin, staff_no='J001', teacher_name='测试教师一',
                                     course_code=code, course_name=name, term_name=term, credit=2, hours=32, source='测试', extra=extra))
    with Session(app2.state.engine) as db:
        return {r.course_code: r.id for r in db.scalars(select(TeacherCourseTerm))}


def apply_course(c, term_id, **kw):
    data = {'source': 'teaching', 'course_term_id': term_id, 'teaching_mode': 'lecture', 'ideology': 'course_ideology', 'audience': '社区居民、企业职工', **kw}
    return post(c, '/api/applications/courses', {'data': data, **REASON})


def act(c, ident, action, reason='审核意见：同意'):
    item = c.get('/api/applications/' + ident).json()['item']
    return post(c, '/api/applications/' + ident + '/actions', {'action': action, 'expected_version': item['version'], 'reason': reason})


def todo_ids(c):
    r = c.get('/api/todos', params={'type': 'application'})
    assert r.status_code == 200, r.text
    return [x['id'] for x in r.json()['items']]


def test_teaching_course_goes_dept_college_school_and_resumes_at_returned_level(app2, client2):
    c = client2
    ids = setup(app2)
    auth(c, 'teacher')
    years = c.get('/api/applications/teaching-courses').json()['years']
    assert [y['school_year'] for y in years] == ['2025-2026', '2024-2025']
    r = apply_course(c, ids['K1'])
    assert r.status_code == 200, r.text
    d = r.json()
    ident = d['item']['id']
    assert d['item']['state'] == 'DEPT' and d['flow'] == 'teaching_course'
    assert d['progress']['text'] == '教研室审核中 · 第 2 步 / 共 4 步' and '测试教研室负责人' in d['progress']['headline']
    # 同一门课只申报一次：挂了 K1 的超星课算同一门。
    assert apply_course(c, ids['X1']).status_code == 409
    assert apply_course(c, ids['K0']).status_code == 422
    assert act(c, ident, 'approve').status_code == 403
    r = c.get("/api/applications/mine"); assert r.status_code == 200, r.text; mine = r.json()
    assert mine['counts']['pending'] == 1 and mine['items'][0]['label'] == '社会培训课申报'
    auth(c, 'otherteacher')
    assert c.get('/api/applications/' + ident).status_code == 403
    auth(c, 'collegehead')
    assert act(c, ident, 'approve').status_code == 403  # 不能越级
    auth(c, 'depthead')
    assert ident in todo_ids(c)
    assert act(c, ident, 'approve').status_code == 200
    auth(c, 'collegehead')
    r = act(c, ident, 'return', '请补充面向对象和课件审查')
    assert r.status_code == 200, r.text
    assert r.json()['progress']['text'] == '学院退回，待你补正'
    auth(c, 'teacher')
    assert ident in todo_ids(c)
    d = c.get('/api/applications/' + ident).json()
    assert d['permissions']['edit'] and d['permissions']['submit']
    r = put(c, '/api/applications/courses/' + ident, {'data': {'source': 'teaching', 'course_term_id': ids['K1'], 'teaching_mode': 'practice', 'ideology': 'course_ideology',
                                                              'audience': '企业职工', 'courseware': {'checked': True, 'reviewer': '学院课件审查组', 'reviewed_on': '2026-10-01'}},
                                                     'expected_version': d['item']['version'], **REASON})
    assert r.status_code == 200, r.text
    r = act(c, ident, 'submit', '已补正')
    assert r.status_code == 200 and r.json()['item']['state'] == 'COLLEGE'  # 从学院接着审，不回教研室
    auth(c, 'collegehead')
    assert act(c, ident, 'approve').status_code == 200
    auth(c, 'reviewer')
    assert ident in todo_ids(c)
    r = act(c, ident, 'approve')
    assert r.status_code == 200, r.text
    d = r.json()
    assert d['item']['state'] == 'ACTIVE' and d['state_label'] == '已入培训课程库' and d['progress']['tone'] == 'green'
    assert [n['state'] for n in d['progress']['nodes']] == ['done'] * 5
    assert d['item']['data']['points']['state'] == 'pending'
    with Session(app2.state.engine) as db:
        master = db.scalar(select(TrainingCourseMaster).where(TrainingCourseMaster.code == d['item']['code']))
        assert master and master.name == '高等数学' and master.source == '学历课申报为社会培训课'
    auth(c, 'teacher')
    years = c.get('/api/applications/teaching-courses').json()['years']
    k1 = next(i for y in years for i in y['items'] if i['course_code'] == 'K1')
    assert k1['application']['state'] == 'ACTIVE'


def test_vacant_dept_is_handled_by_college_marked_and_same_person_flagged(app2, client2):
    c = client2
    ids = setup(app2)
    with app2.state.sessions.begin() as db:
        db.get(User, 'depthead').active = False
        db.add(Setting(key='param:social_course_points', value={'name': '每门社会培训课积分', 'type': 'decimal', 'value': '2'}))
    auth(c, 'teacher')
    ident = apply_course(c, ids['X2']).json()['item']['id']
    auth(c, 'collegehead')
    assert ident in todo_ids(c)
    r = act(c, ident, 'approve')
    assert r.status_code == 200, r.text
    r = act(c, ident, 'approve')
    assert r.status_code == 200, r.text
    nodes = r.json()['progress']['nodes']
    assert nodes[1]['acting_for'] and nodes[2]['same_person'] == '同一人连审'
    auth(c, 'reviewer')
    d = act(c, ident, 'approve').json()
    assert d['item']['data']['points']['state'] == 'booked'
    with Session(app2.state.engine) as db:
        entry = db.scalar(select(PointEntry).where(PointEntry.teacher_id == 'teacher', PointEntry.kind == 'SOCIAL'))
        assert entry is not None and str(entry.amount).startswith('2')


def test_school_level_recuses_the_applicant(app2, client2):
    c = client2
    ids = setup(app2, coordinator='teacher')
    auth(c, 'teacher')
    ident = apply_course(c, ids['K1']).json()['item']['id']
    for user in ('depthead', 'collegehead'):
        auth(c, user)
        assert act(c, ident, 'approve').status_code == 200
    auth(c, 'teacher')
    assert ident not in todo_ids(c)
    assert act(c, ident, 'approve').status_code == 403


def test_base_application_college_then_school_and_withdraw(app2, client2):
    c = client2
    setup(app2)
    auth(c, 'teacher')
    data = {'code': 'BASE-T1', 'name': '茶艺实训基地', 'onsite': False, 'partner': '湘茶集团', 'location': '长沙', 'recognition': '共建协议',
            'usages': ['practice', 'ideology'], 'established_on': '2026-09-01'}
    r = post(c, '/api/applications/bases', {'data': data, **REASON})
    assert r.status_code == 200, r.text
    ident = r.json()['item']['id']
    assert r.json()['item']['state'] == 'COLLEGE'
    assert act(c, ident, 'withdraw', '先撤回改资料').json()['item']['state'] == 'WITHDRAWN'
    assert act(c, ident, 'submit', '重新提交').json()['item']['state'] == 'COLLEGE'
    auth(c, 'collegehead')
    assert act(c, ident, 'approve').status_code == 200
    auth(c, 'reviewer')
    d = act(c, ident, 'approve').json()
    assert d['item']['state'] == 'DRAFT' and d['state_label'] == '已生效'
    # 已办结的申请不能再补传附件或修改。
    auth(c, 'teacher')
    assert c.get('/api/social/objects/social_resource/' + ident).status_code == 200
