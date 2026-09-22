from pathlib import Path
from sqlalchemy.orm import Session
from sqlalchemy import inspect,select
from app.models import Base,AuthSession,RuntimeState,User,Connection
from app.config import Settings
from app.cli import init_empty,check
from app.maintenance import sanitize_restore
from app.grants import sql
from app.worker import run_once
from app.core import make_engine
from app.passwords import hash_password


def test_runtime_grants_have_no_schema_ddl():
    text=sql()
    runtime=[line for line in text.splitlines() if "TO 'nondegree_app'" in line]
    assert runtime and all('CREATE' not in line and 'ALTER' not in line and 'DROP' not in line for line in runtime)
    assert "TO 'nondegree_migration'" in text and 'ALTER' in text


def test_empty_school_init_requires_empty_database_and_explicit_school_name(tmp_path,monkeypatch):
    db=tmp_path/'fresh.sqlite';cfg=Settings(env='test',database_url='sqlite:///'+str(db),secure_cookie=False,public_origin='http://testserver',allowed_hosts='testserver',storage_dir=tmp_path/'files')
    engine=make_engine(cfg.database_url);Base.metadata.create_all(engine);engine.dispose()
    secret=tmp_path/'admin_password';secret.write_text('StrongTemp_2026!')
    monkeypatch.setenv('ND_SCHOOL_NAME','采购测试学校')
    init_empty(cfg,secret);check(cfg)
    engine=make_engine(cfg.database_url)
    with Session(engine) as s:
        admin=s.scalar(select(User).where(User.username=='admin'))
        assert admin and admin.is_admin and admin.must_change_password and admin.active
        connections={x.code:x for x in s.scalars(select(Connection)).all()}
        assert set(connections)=={'sso','middle','province'}
        assert all(x.state=='NOT_CONNECTED' for x in connections.values())
        assert connections['sso'].config['auth_mode']=='school_sso'
    engine.dispose()
    try:init_empty(cfg,secret)
    except RuntimeError as e:assert 'non-empty' in str(e)
    else:raise AssertionError('second init must fail')


def test_restore_sanitization_revokes_sessions_and_rotates_admin(app2,tmp_path):
    secret=tmp_path/'restore_admin';secret.write_text('RestoreTemp_2026!')
    with Session(app2.state.engine) as db:
        admin=db.get(User,'schooladmin');admin.password_hash=hash_password('OldRestore_2026!');admin.must_change_password=False
        db.add(AuthSession(token_hash='a'*64,csrf='b'*64,user_id='schooladmin',auth_version=admin.auth_version,expires_at=__import__('app.models',fromlist=['utcnow']).utcnow(),last_seen=__import__('app.models',fromlist=['utcnow']).utcnow()));db.commit()
        old_version=admin.auth_version
    sanitize_restore(app2.state.settings,'schooladmin',secret)
    with Session(app2.state.engine) as db:
        admin=db.get(User,'schooladmin');assert admin.auth_version>old_version and admin.must_change_password and admin.active
        assert db.query(AuthSession).count()==0


def test_worker_maintenance_stops_claim_but_keeps_heartbeat(app2,tmp_path):
    maintenance=tmp_path/'maintenance';maintenance.mkdir();(maintenance/'active').write_text('{}')
    app2.state.settings.maintenance_dir=maintenance
    result=run_once(app2.state.settings)
    assert result['status']=='MAINTENANCE' and result['claimed'] is False
    with Session(app2.state.engine) as db:
        hb=db.get(RuntimeState,'worker');assert hb and hb.value['healthy'] is True and hb.value['maintenance'] is True


def test_source_assembly_has_no_nonmigration_missing_files():
    import importlib.util
    root=Path(__file__).resolve().parents[2]
    spec=importlib.util.spec_from_file_location('assembly',root/'scripts/check_assembly.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    result=m.inspect_assembly(root)
    assert result['missing']==[]
    assert result['status']=='PASS' and result['migration_graph_verified'] is True
    assert result['legacy_upgrade_allowed'] is False and result['historical_graph_verified'] is False
