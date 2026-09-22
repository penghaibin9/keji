"""Home workbench contract, using isolated synthetic fixtures only."""
from datetime import date, timedelta
import pytest
from app.models import Qualification, Role
from conftest import auth


def add_qualification(db, ident, teacher='teacher', state='APPROVED', days=None):
    db.add(Qualification(id=ident, teacher_id=teacher, category='职业资格',
        name='合成资质'+ident, certificate_no=ident, issuer='测试机构',
        obtained=date.today()-timedelta(days=365), state=state,
        expires=None if days is None else date.today()+timedelta(days=days)))


def seed(app):
    with app.state.sessions.begin() as db:
        for ident, state, days in [('draft','DRAFT',None),('returned','RETURNED',None),
                ('review','SUBMITTED',None),('expired','APPROVED',-1),
                ('today','APPROVED',0),('soon','APPROVED',7),
                ('boundary','APPROVED',30),('later','APPROVED',31),
                ('permanent','APPROVED',None)]:
            add_qualification(db,ident,state=state,days=days)
        add_qualification(db,'other-review','otherteacher','SUBMITTED')
        add_qualification(db,'other-expired','otherteacher',days=-10)


def test_home_requires_normal_login(client2):
    assert client2.get('/api/portal/workbench').status_code==401


@pytest.mark.parametrize('username,tasks,reminders,scope',[
    ('teacher',2,4,'仅本人'),('depthead',1,4,'测试教研室一'),
    ('collegehead',1,4,'测试学院一'),('schooladmin',2,5,'隔离测试学校')])
def test_home_uses_four_role_scope(client2,app2,username,tasks,reminders,scope):
    seed(app2)
    auth(client2,username)
    response=client2.get('/api/portal/workbench')
    assert response.status_code==200,response.text
    data=response.json()
    assert data['tasks']['total']==tasks
    assert data['reminders']['total']==reminders
    assert data['scope_label']==scope
    assert data['as_of']==date.today().isoformat()
    if username!='schooladmin':
        assert 'other-' not in response.text
    assert 'password' not in response.text and 'attachment_ids' not in response.text
    assert all(x['owner_name'] in {'测试教师一','测试教师二'}
               for x in data['tasks']['items']+data['reminders']['items'])


def test_home_uses_actual_expiry_and_priority_without_fake_deadlines(client2,app2):
    seed(app2);auth(client2,'teacher')
    data=client2.get('/api/portal/workbench').json()
    assert [x['id'] for x in data['tasks']['items']]==['returned','draft']
    assert data['tasks']['returned']==1
    reminders=data['reminders']
    assert reminders['expired']==1
    assert [x['id'] for x in reminders['items']]==['expired','today','soon','boundary']
    assert [x['days_remaining'] for x in reminders['items']]==[-1,0,7,30]
    assert 'deadline' not in str(data)


def test_home_and_unified_todos_share_the_same_source(client2,app2):
    seed(app2);auth(client2,'teacher')
    home=client2.get('/api/portal/workbench').json()
    todos=client2.get('/api/todos?size=100').json()
    assert home['tasks']['total']+home['reminders']['total']==todos['total']
    assert {x['id'] for x in home['tasks']['items']+home['reminders']['items']}=={x['id'] for x in todos['items']}


def test_home_returns_full_counts_but_bounded_previews(client2,app2):
    with app2.state.sessions.begin() as db:
        for i in range(15):
            add_qualification(db,'draft-'+str(i),state='DRAFT')
            add_qualification(db,'expired-'+str(i),days=-i-1)
    auth(client2,'teacher')
    data=client2.get('/api/portal/workbench').json()
    assert data['tasks']['total']==15 and len(data['tasks']['items'])==6
    assert data['reminders']['total']==15 and len(data['reminders']['items'])==4
    assert data['reminders']['items'][0]['id']=='expired-14'


def test_home_does_not_treat_role_name_as_business_permission(client2,app2):
    seed(app2)
    with app2.state.sessions.begin() as db:
        db.get(Role,'role-school').permissions=['portal.read']
    auth(client2,'schooladmin')
    data=client2.get('/api/portal/workbench').json()
    assert data['tasks']['total']==0 and data['reminders']['total']==0


def test_home_rechecks_revoked_permission(client2,app2):
    auth(client2,'teacher')
    with app2.state.sessions.begin() as db:
        db.get(Role,'role-teacher').permissions=[]
    assert client2.get('/api/portal/workbench').status_code==403

