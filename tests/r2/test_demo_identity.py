import uuid
from datetime import timedelta
import pytest
from sqlalchemy import select
from fastapi.testclient import TestClient
from app.models import User, Role, Audit, AuthSession, utcnow
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
