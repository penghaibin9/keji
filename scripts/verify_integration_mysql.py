"""Explicitly isolated local MySQL smoke, not school production acceptance.

Requires a brand-new local database named keji_closeout. No create_all, stamp,
DROP, runtime permission changes or connections to remote school databases.
"""
from pathlib import Path
import argparse
import json
import os
import sys
import tempfile
import uuid
from urllib.parse import urlsplit
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'backend'), str(ROOT/'tests/r2')]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--isolated-local', action='store_true', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    url = os.environ.get('ND_CLOSEOUT_MYSQL_URL', '')
    target = urlsplit(url)
    if target.scheme != 'mysql+pymysql' or target.hostname != '127.0.0.1' or target.path != '/keji_closeout':
        raise SystemExit('Refused: dedicated local test database required')
    from sqlalchemy import create_engine, inspect, text, select
    from sqlalchemy.orm import Session
    engine = create_engine(url)
    if inspect(engine).get_table_names():
        raise SystemExit('Refused: database is not empty')
    with engine.connect() as conn:
        version = conn.execute(text('SELECT VERSION()')).scalar_one()
        assert version.startswith('8.4.'), version
    os.environ.update(ND_ENV='production', ND_DATABASE_URL=url, ND_PUBLIC_ORIGIN='https://synthetic.invalid',
                      ND_SCHOOL_NAME='接口收口独立 MySQL 合成学校')
    from alembic.config import Config
    from alembic import command
    from app.installation import require_canonical
    migration = Config(str(ROOT/'backend/alembic.ini'))
    command.upgrade(migration, 'head')
    with engine.connect() as conn:
        provenance = require_canonical(conn, require_mysql=True)
    from app.config import Settings
    from app.cli import init_empty, check
    from app.models import User, Org
    from app.main import create_app
    password = 'SyntheticOnly_'+uuid.uuid4().hex
    with tempfile.TemporaryDirectory(prefix='keji-mysql-secret-') as temporary:
        secret = Path(temporary)/'admin.txt'
        secret.write_text(password, encoding='utf-8')
        cfg = Settings(env='production', database_url=url, public_origin='https://synthetic.invalid')
        init_empty(cfg, secret)
        check(cfg)
    with Session(engine) as db:
        initial = db.scalar(select(User).where(User.username == 'admin'))
        db.add(Org(id='college1', code='college1', name='合成学院', kind='college', parent_id='school'))
        db.flush()
        db.add(Org(id='dept1', code='dept1', name='合成教研室', kind='dept', parent_id='college1'))
        db.flush()
        db.add(User(id='schooladmin', username='schooladmin', name='合成实施管理员', org_id='school',
            role_id='role-school', is_admin=True, must_change_password=False, password_hash=initial.password_hash))
        db.add(User(id='teacher', username='teacher', name='合成教师', org_id='dept1', staff_no='J001',
            role_id='role-teacher', must_change_password=False, password_hash=initial.password_hash))
        db.commit()
    cfg = Settings(env='test', database_url=url, public_origin='http://testserver', secure_cookie=False,
                   allowed_hosts='testserver', storage_dir=ROOT/'evidence/integration-closeout/mysql-files')
    app = create_app(cfg)
    from test_integration_closeout import test_1001_rows_resume_after_interrupted_second_page
    test_1001_rows_resume_after_interrupted_second_page(app)
    from fastapi.testclient import TestClient
    with TestClient(app) as client:
        client.headers['origin'] = 'http://testserver'
        assert client.post('/api/auth/login', json={'username': 'schooladmin', 'password': password}).status_code == 200
        me = client.get('/api/auth/me').json()
        client.headers['x-csrf-token'] = me['csrf']
        ident = next(x['connection']['id'] for x in client.get('/api/connections/catalog').json()['items'] if x['connection']['code'] == 'sso')
        response = client.put('/api/connections/'+ident+'/draft', headers={'idempotency-key': uuid.uuid4().hex},
            json={'expected_version': 1, 'expected_draft_version': 0, 'config': {}, 'mappings': [], 'reason': '独立MySQL草稿验证'})
        assert response.status_code == 200, response.text
        assert client.get('/api/connections/'+ident+'/draft').json()['draft_version'] == 1
        report = client.get('/api/connections/'+ident+'/implementation').json()
        assert report['statuses']['acceptance'] == '待学校签认'
    command.upgrade(migration, 'head')
    with engine.connect() as conn:
        assert require_canonical(conn, require_mysql=True) == provenance
        count = conn.execute(text('SELECT COUNT(*) FROM training_projects')).scalar_one()
        assert count == 1001
    engine.dispose()
    result = {'status': 'PASS', 'database': 'MySQL', 'version': version,
        'fresh_migration': True, 'repeat_migration_keeps_provenance': True,
        'schema_baseline': '20260918_0001', 'migration_hash_guard_bypassed': False,
        'initialization': True, 'http_login_draft_save_read': True,
        'paged_rows': count, 'interrupted_second_page_resumed': True,
        'synthetic_school_data': True, 'school_system_contacted': False,
        'external_adapter': 'synthetic transport', 'production_acceptance': False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
