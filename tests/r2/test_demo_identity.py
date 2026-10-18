import uuid
from datetime import timedelta
import pytest
from sqlalchemy import select
from fastapi.testclient import TestClient
from app.models import User, Role, Audit, AuthSession, utcnow
from app.config import Settings
from app.demo_identity import profile_identities
from conftest import auth, post


@pytest.fixture
def demo(app2, client2):
    app2.state.settings.demo_identity_switch_enabled=True
    with app2.state.sessions.begin() as db:
        for uid, username in [('schooladmin','admin'),('teacher','show_teacher'),
                              ('depthead','show_dept'),('collegehead','show_college')]:
            db.get(User,uid).username=username
    auth(client2,'admin')
    return app2,client2


def switch(client, username):
    response=post(client,'/api/auth/demo-switch',{'username':username})
    assert response.status_code==200,response.text
    me=client.get('/api/auth/me')
    assert me.status_code==200,me.text
    client.headers['x-csrf-token']=me.json()['csrf']
    return me.json()


def test_four_identities_use_real_scope_and_return(demo):
    app,client=demo
    before=client.get('/api/auth/me').json()
    assert len(before['demo_switch']['options'])==4
    for username,role in [('show_teacher','teacher'),('show_dept','dept'),('show_college','college'),('admin','school')]:
        me=switch(client,username)
        assert me['user']['username']==username
        assert me['role']['kind']==role
        assert me['csrf']!=before['csrf']
        if role=='teacher':
            assert client.get('/api/users').status_code==403
            records=client.get('/api/records').json()
            assert all(row['teacher_id']=='teacher' for row in records['items'])
        before=me
    assert client.get('/api/users').status_code==200
    with app.state.sessions() as db:
        logs=db.scalars(select(Audit).where(Audit.action=='切换演示身份')).all()
        assert len(logs)==4
        assert all(log.actor_id=='schooladmin' for log in logs)


def test_normal_teacher_cannot_switch_or_see_options(demo):
    app,client=demo
    auth(client,'show_teacher')
    assert client.get('/api/auth/me').json()['demo_switch'] is None
    assert post(client,'/api/auth/demo-switch',{'username':'admin'}).status_code==403


def test_disabled_by_default_and_unlisted_targets(demo):
    app,client=demo
    assert post(client,'/api/auth/demo-switch',{'username':'otherteacher'}).status_code==403
    app.state.settings.demo_identity_switch_enabled=False
    assert client.get('/api/auth/me').json()['demo_switch'] is None
    assert post(client,'/api/auth/demo-switch',{'username':'show_teacher'}).status_code==403


def test_csrf_and_replayed_old_writes_rejected(demo):
    app,client=demo
    stale_csrf=client.headers['x-csrf-token']
    assert post(client,'/api/auth/demo-switch',{'username':'show_teacher'},headers={'x-csrf-token':'wrong'}).status_code==403
    switch(client,'show_teacher')
    assert post(client,'/api/auth/demo-switch',{'username':'admin'},headers={'x-csrf-token':stale_csrf}).status_code==403
    assert post(client,'/api/auth/demo-switch',{'username':'admin'},headers={'origin':'https://evil.example'}).status_code==403
    assert client.get('/api/auth/me').json()['user']['username']=='show_teacher'


@pytest.mark.parametrize('change',['controller_password','controller_disabled','controller_expired','target_password','target_disabled','feature_disabled'])
def test_revocation_takes_effect_for_delegated_session(demo,change):
    app,client=demo
    switch(client,'show_teacher')
    with app.state.sessions.begin() as db:
        if change=='controller_password':db.get(User,'schooladmin').auth_version+=1
        elif change=='controller_disabled':db.get(User,'schooladmin').active=False
        elif change=='controller_expired':
            for session in db.scalars(select(AuthSession)):session.expires_at=utcnow()-timedelta(seconds=1)
        elif change=='target_password':db.get(User,'teacher').auth_version+=1
        elif change=='target_disabled':db.get(User,'teacher').active=False
        else:app.state.settings.demo_identity_switch_enabled=False
    assert client.get('/api/records').status_code in (401,403)


def test_selection_cannot_transfer_to_different_session(demo):
    app,client=demo
    switch(client,'show_teacher')
    name=app.state.settings.demo_cookie_name
    selection=client.cookies.get(name)
    with TestClient(app) as other:
        other.headers['origin']='http://testserver'
        auth(other,'admin')
        other.cookies.set(name,selection)
        assert other.get('/api/auth/me').status_code==401


def test_logout_revokes_controller_and_password_write_denied(demo):
    app,client=demo
    switch(client,'show_teacher')
    assert post(client,'/api/auth/password',{'old_password':'FixtureOnly_2026_Local','new_password':'AnotherPassword123'}).status_code==403
    assert post(client,'/api/auth/logout').status_code==200
    assert client.get('/api/auth/me').status_code==401
    auth(client,'show_teacher')
    assert client.get('/api/auth/me').json()['demo_switch'] is None


@pytest.fixture
def daily_demo(app2, client2):
    app2.state.settings.demo_identity_switch_enabled=True
    app2.state.settings.demo_identity_profile='daily-test'
    app2.state.settings.public_origin='http://localhost'
    client2.headers['origin']='http://localhost'
    with app2.state.sessions.begin() as db:
        admin=db.get(User,'schooladmin')
        for username in ('reviewer','vice'):
            db.add(User(id=username,username=username,name=username,role_id=admin.role_id,
                        org_id=admin.org_id,password_hash=admin.password_hash,is_admin=False,
                        must_change_password=False))
    auth(client2,'schooladmin')
    return app2,client2


def test_daily_four_roles_keep_real_scope_and_account_permissions(daily_demo):
    app,client=daily_demo
    def authorization_snapshot():
        with app.state.sessions() as db:
            users=sorted((u.id,u.username,u.role_id,u.org_id,u.is_admin,u.auth_version,u.password_hash,u.version)
                         for u in db.scalars(select(User)))
            roles=sorted((r.id,r.version,r.active,tuple(r.permissions)) for r in db.scalars(select(Role)))
            return users,roles
    before=authorization_snapshot()
    initial=client.get('/api/auth/me').json()
    assert initial['demo_switch']['label']=='快速切换角色'
    assert [o['username'] for o in initial['demo_switch']['options']]==['teacher','depthead','collegehead','schooladmin','reviewer','vice']
    for username,kind,org,teachers in [
        ('teacher','teacher','dept1',{'teacher'}),
        ('depthead','dept','dept1',{'teacher'}),
        ('collegehead','college','college1',{'teacher'}),
        ('reviewer','school','school',{'teacher','otherteacher'}),
        ('vice','school','school',{'teacher','otherteacher'}),
        ('schooladmin','school','school',{'teacher','otherteacher'}),
    ]:
        me=switch(client,username)
        assert me['user']['username']==username
        assert me['role']['kind']==kind and me['org']['id']==org
        assert me['demo_switch']['current']==username
        assert {r['teacher_id'] for r in client.get('/api/records').json()['items']}==teachers
        if kind!='school':
            assert me['user']['is_admin'] is False
            assert client.get('/api/users').status_code==403
    assert client.get('/api/users').status_code==200
    assert authorization_snapshot()==before
    with app.state.sessions() as db:
        assert {s.user_id for s in db.scalars(select(AuthSession))}=={'schooladmin'}
        logs=db.scalars(select(Audit).where(Audit.action=='切换演示身份')).all()
        assert len(logs)==6 and all(log.actor_id=='schooladmin' for log in logs)


def test_daily_fixed_list_normal_login_and_old_page_writes(daily_demo):
    app,client=daily_demo
    old_csrf=client.headers['x-csrf-token']
    assert post(client,'/api/auth/demo-switch',{'username':'otherteacher'}).status_code==403
    assert post(client,'/api/auth/demo-switch',{'username':'show_teacher'}).status_code==403
    switch(client,'teacher')
    assert post(client,'/api/auth/demo-switch',{'username':'schooladmin'},headers={'x-csrf-token':old_csrf}).status_code==403
    assert post(client,'/api/auth/demo-switch',{'username':'schooladmin'},headers={'origin':'https://evil.example'}).status_code==403
    auth(client,'teacher')
    assert client.get('/api/auth/me').json()['demo_switch'] is None
    assert post(client,'/api/auth/demo-switch',{'username':'schooladmin'}).status_code==403


@pytest.mark.parametrize('change',['production','remote_origin','feature_disabled','target_pending','target_role_disabled'])
def test_daily_revocation_is_checked_on_every_request(daily_demo,change):
    app,client=daily_demo
    switch(client,'teacher')
    with app.state.sessions.begin() as db:
        if change=='production':app.state.settings.env='production'
        elif change=='remote_origin':app.state.settings.public_origin='http://example.com'
        elif change=='feature_disabled':app.state.settings.demo_identity_switch_enabled=False
        elif change=='target_pending':db.get(User,'teacher').authorization_pending=True
        else:db.get(Role,'role-teacher').active=False
    if change in {'production','remote_origin'}:
        assert profile_identities(app.state.settings)=={}
    assert client.get('/api/auth/me').status_code==(503 if change=='production' else 403)


def test_daily_logout_and_selection_cannot_transfer(daily_demo):
    app,client=daily_demo
    switch(client,'teacher')
    selection=client.cookies.get(app.state.settings.demo_cookie_name)
    with TestClient(app) as other:
        other.headers['origin']='http://localhost'
        auth(other,'schooladmin')
        other.cookies.set(app.state.settings.demo_cookie_name,selection)
        assert other.get('/api/auth/me').status_code==401
    assert post(client,'/api/auth/logout').status_code==200
    assert client.get('/api/auth/me').status_code==401


@pytest.mark.parametrize('env,origin',[('production','https://localhost'),('test','https://example.com')])
def test_daily_profile_rejects_nonlocal_or_production_configuration(env,origin):
    with pytest.raises(ValueError,match='日常测试角色切换仅允许本机测试环境'):
        Settings(env=env,database_url='mysql+pymysql://test:test@localhost/test',
                 public_origin=origin,allowed_hosts='localhost',demo_identity_profile='daily-test')


def test_daily_profile_requires_explicit_enable(app2,client2):
    app2.state.settings.demo_identity_profile='daily-test'
    app2.state.settings.public_origin='http://localhost'
    client2.headers['origin']='http://localhost'
    auth(client2,'schooladmin')
    assert client2.get('/api/auth/me').json()['demo_switch'] is None
    assert post(client2,'/api/auth/demo-switch',{'username':'teacher'}).status_code==403
