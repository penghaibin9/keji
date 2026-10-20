from datetime import date

from app.models import Qualification, User
from conftest import auth
from test_demo_identity import demo, switch


def add_qualifications(app):
    with app.state.sessions.begin() as db:
        for ident, teacher, state in [('draft', 'teacher', 'DRAFT'), ('submitted', 'teacher', 'SUBMITTED'), ('outside', 'otherteacher', 'SUBMITTED')]:
            db.add(Qualification(id='role-summary-' + ident, teacher_id=teacher,
                                 category='职业资格', name='隔离资质-' + ident,
                                 certificate_no='TEST-' + ident, issuer='测试机构',
                                 obtained=date(2026, 1, 1), state=state))


def test_demo_summary_counts_authorized_roles_without_exposing_tasks(demo):
    app, client = demo
    add_qualifications(app)
    response = client.get('/api/auth/role-summary')
    assert response.status_code == 200
    data = response.json()
    counts = {x['username']: x['todo_count'] for x in data['demo_switch']['options']}
    assert counts['show_teacher'] == 1
    assert counts['show_dept'] == 1
    assert counts['show_college'] == 1
    assert counts['admin'] == 2
    assert 'certificate_no' not in response.text and '隔离资质' not in response.text
    switch(client, 'show_teacher')
    data = client.get('/api/auth/role-summary').json()
    assert data['current_todo_count'] == 1
    assert data['demo_switch']['current'] == 'show_teacher'
    with app.state.sessions.begin() as db:
        db.get(User, 'depthead').active = False
    data = client.get('/api/auth/role-summary').json()
    dept = next(x for x in data['demo_switch']['options'] if x['username'] == 'show_dept')
    assert dept['todo_count'] is None and dept['unavailable'] is True


def test_ordinary_teacher_summary_does_not_grant_demo_access(app2, client2):
    add_qualifications(app2)
    assert client2.get('/api/auth/role-summary').status_code == 401
    auth(client2, 'teacher')
    response = client2.get('/api/auth/role-summary?username=schooladmin')
    assert response.status_code == 200
    assert response.json() == {'demo_switch': None, 'identities': [], 'current_todo_count': 1}


def test_role_summary_keeps_real_extra_identity_scope(app2, client2):
    from test_multi_identity import _add_extra
    add_qualifications(app2)
    auth(client2, 'schooladmin')
    assert _add_extra(client2, 'teacher', [{'role_id': 'role-dept', 'org_id': 'dept1'}]).status_code == 200
    auth(client2, 'teacher')
    data = client2.get('/api/auth/role-summary').json()
    assert data['demo_switch'] is None
    assert data['current_todo_count'] == 1
    assert [(x['role_kind'], x['todo_count']) for x in data['identities']] == [('teacher', 1), ('dept', 1)]
    assert all(x['org_id'] == 'dept1' for x in data['identities'])
