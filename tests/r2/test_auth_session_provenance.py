"""Authentication provenance is server-owned, including migration and revocation."""
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
import pytest
from sqlalchemy import select, text, create_engine
from alembic import command
from alembic.config import Config
from app.models import AuthSession, User, utcnow
from app.installation import require_canonical
from conftest import auth, post
from test_codex_admin_sso_compat import cas_sso, start, callback
from test_api import qual


def current_session(db,client,app):
    token=client.cookies.get(app.state.settings.cookie_name)
    return db.get(AuthSession,sha256(token.encode()).hexdigest())


@pytest.mark.parametrize('marker',['computed','random','absent'])
def test_local_session_cannot_claim_sso_to_skip_password_change(client2,app2,marker):
    auth(client2,'teacher');item=qual(client2)
    with app2.state.sessions.begin() as db:
        db.get(User,'teacher').must_change_password=True
        assert current_session(db,client2,app2).auth_method=='local'
    if marker!='absent':
        token=client2.cookies.get(app2.state.settings.cookie_name)
        client2.cookies.set('nd_sso_session',sha256(('sso:'+token).encode()).hexdigest() if marker=='computed' else 'x'*64)
    assert client2.get('/api/records').status_code==403
    assert post(client2,'/api/qualifications/'+item['id']+'/actions',{'action':'submit','expected_version':item['version'],'reason':'合成来源攻击检查'}).status_code==403
    me=client2.get('/api/auth/me').json()
    assert me['sso_session'] is False and me['user']['must_change_password'] is True


def test_verified_callback_records_sso_without_client_marker(client2,app2,cas_sso):
    with app2.state.sessions.begin() as db:db.get(User,'teacher').must_change_password=True
    assert callback(client2,start(client2)).status_code==303
    assert client2.cookies.get('nd_sso_session') is None
    with app2.state.sessions() as db:
        assert current_session(db,client2,app2).auth_method=='sso'
        assert db.get(User,'teacher').must_change_password is True
    assert client2.get('/api/records').status_code==200
    assert client2.get('/api/auth/me').json()['sso_session'] is True
    assert client2.get('/api/records/rec2').status_code==403


@pytest.mark.parametrize('change',['expired','idle','disabled','revoked','unknown_method'])
def test_trusted_sso_keeps_session_and_account_guards(client2,app2,cas_sso,change):
    with app2.state.sessions.begin() as db:db.get(User,'teacher').must_change_password=True
    assert callback(client2,start(client2)).status_code==303
    with app2.state.sessions.begin() as db:
        session=current_session(db,client2,app2);user=db.get(User,'teacher')
        if change=='expired':session.expires_at=utcnow()-timedelta(minutes=1)
        elif change=='idle':session.last_seen=utcnow()-timedelta(days=1)
        elif change=='disabled':user.active=False
        elif change=='revoked':user.auth_version+=1
        else:session.auth_method='unknown'
    assert client2.get('/api/records').status_code==(403 if change=='unknown_method' else 401)


@pytest.fixture
def migration_url(tmp_path):
    from conftest import _database_url
    url,drop=_database_url(tmp_path)
    yield url
    if drop:drop()


@pytest.mark.parametrize('initial',['base','previous'])
def test_migration_preserves_old_rows_and_defaults_to_local(migration_url,monkeypatch,initial):
    root=Path(__file__).resolve().parents[2];url=migration_url
    monkeypatch.setenv('ND_ENV','test');monkeypatch.setenv('ND_DATABASE_URL',url)
    cfg=Config(str(root/'backend/alembic.ini'))
    command.upgrade(cfg,'20260918_0001' if initial=='base' else '20261009_0003')
    engine=create_engine(url)
    with engine.begin() as db:
        # Foreign keys stay enabled in production; use a genuine minimal account chain.
        db.execute(text("INSERT INTO organizations (id,code,name,kind,active,version,created_at) VALUES ('o','o','合成','school',1,1,'2026-10-12')"))
        db.execute(text("INSERT INTO roles (id,code,name,kind,permissions,active,version,created_at) VALUES ('r','r','合成','school','[]',1,1,'2026-10-12')"))
        db.execute(text("INSERT INTO users (id,username,name,org_id,role_id,password_hash,active,is_admin,must_change_password,auth_version,version,failures,title,created_at) VALUES ('u','u','合成','o','r','synthetic',1,0,1,1,1,0,'','2026-10-12')"))
        db.execute(text("INSERT INTO auth_sessions (token_hash,csrf,user_id,auth_version,expires_at,last_seen) VALUES ('old','csrf','u',1,'2099-01-01','2026-10-12')"))
        db.execute(text("UPDATE users SET staff_no='OLDSTAFF' WHERE id='u'"))
        db.execute(text("INSERT INTO teacher_hr_profiles (id,staff_no,user_id,name,title,org_code,active,source,extra,version,created_at) VALUES ('hr-old','OLDSTAFF','u','合成','','UNKNOWN',1,'合成','{}',1,'2026-10-12')"))
        before=require_canonical(db,allow_baseline=True)
    command.upgrade(cfg,'head');command.upgrade(cfg,'head')
    with engine.begin() as db:
        assert require_canonical(db)['installation_id']==before['installation_id']
        assert db.execute(text("SELECT authorization_pending FROM users WHERE id='u'")).scalar_one()==1
        assert db.execute(text("SELECT auth_version FROM users WHERE id='u'")).scalar_one()==2
        assert db.execute(text("SELECT auth_method FROM auth_sessions WHERE token_hash='old'")).scalar_one()=='local'
        db.execute(text("INSERT INTO auth_sessions (token_hash,csrf,user_id,auth_version,expires_at,last_seen) VALUES ('new','csrf','u',1,'2099-01-01','2026-10-12')"))
        assert db.execute(text("SELECT auth_method FROM auth_sessions WHERE token_hash='new'")).scalar_one()=='local'
    engine.dispose()
