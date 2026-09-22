from types import SimpleNamespace
import json
import pytest
from sqlalchemy import text
from app import models as m
from app.readiness import collect_readiness
from app.maintenance_guard import maintenance_state


def test_readiness_reports_all_sections(engine,cfg):
    r=collect_readiness(engine,cfg,'isolated-test')
    assert r['status']=='ok' and r['accepting_requests'] is True
    assert all(r[k]['status']=='ok' for k in ('database','migration','initialization'))

@pytest.mark.parametrize('what',['guard','branding','metrics','qualification','business_dictionary','import_policy','root','teacher_role','dept_role','college_role','school_role'])
def test_missing_initialization_not_ready(engine,cfg,what):
    with engine.begin() as conn:
        if what=='guard':conn.execute(text('DELETE FROM mutation_guards'))
        elif what in {'branding','metrics','qualification','business_dictionary','import_policy'}:conn.execute(text('DELETE FROM settings WHERE `key`=:key'),{'key':what})
        elif what=='root':conn.execute(text("UPDATE organizations SET active=0 WHERE id='school'"))
        else:conn.execute(text('UPDATE roles SET active=0 WHERE kind=:kind'),{'kind':what.removesuffix('_role')})
    r=collect_readiness(engine,cfg,'isolated-test')
    assert r['status']=='not_ready' and r['initialization']['status']=='incomplete'

@pytest.mark.parametrize('value',[{}, {'expiry_days':True,'categories':['x']},{'expiry_days':0,'categories':['x']},{'expiry_days':30,'categories':[]}])
def test_malformed_required_setting_not_ready(db,engine,cfg,value):
    db.get(m.Setting,'qualification').value=value;db.commit()
    assert collect_readiness(engine,cfg,'isolated-test')['initialization']['status']=='incomplete'

@pytest.mark.parametrize('head',['wrong','empty','extra'])
def test_migration_mismatch(engine,cfg,head):
    with engine.begin() as conn:
        if head=='empty':conn.execute(text('DELETE FROM alembic_version'))
        elif head=='extra':conn.execute(text("INSERT INTO alembic_version VALUES ('unrelated_branch')"))
        else:conn.execute(text("UPDATE alembic_version SET version_num='wrong'"))
    assert collect_readiness(engine,cfg,'test')['migration']['status']=='mismatch'


def test_missing_migration_table_safe_response(engine,cfg):
    with engine.begin() as conn:conn.execute(text('DROP TABLE alembic_version'))
    r=collect_readiness(engine,cfg,'test')
    assert r['status']=='not_ready' and r['migration']['status']=='unavailable'
    assert 'SELECT' not in json.dumps(r)


def test_database_failure_never_echoes_secrets(cfg):
    from sqlalchemy.exc import OperationalError
    class BrokenEngine:
        def connect(self):raise OperationalError('SECRET_SQL',{'password':'VERY_SECRET'},RuntimeError('secret://connection'))
    r=collect_readiness(BrokenEngine(),cfg,'test')
    assert r['database']['status']=='unavailable'
    assert 'SECRET' not in json.dumps(r) and 'connection' not in json.dumps(r)


def test_production_sqlite_cannot_pass(engine,tmp_path):
    r=collect_readiness(engine,SimpleNamespace(env='production',maintenance_dir=tmp_path),'test')
    assert r['status']=='not_ready' and r['database']['status']=='unsupported'

@pytest.mark.parametrize('key',['ND_SEED_ENABLED','ND_AUTO_CREATE_TABLES','ND_AUTO_CREATE_SCHEMA'])
def test_production_seed_and_schema_creation_blocked(engine,tmp_path,monkeypatch,key):
    monkeypatch.setenv(key,'true')
    r=collect_readiness(engine,SimpleNamespace(env='production',maintenance_dir=tmp_path),'test')
    assert r['initialization']=={'status':'invalid','reason':'PRODUCTION_POLICY'}


def test_active_latch_keeps_probe_inspectable_but_blocks_business(engine,cfg,tmp_path):
    cfg.maintenance_dir=tmp_path;(tmp_path/'active').write_text('maintenance')
    r=collect_readiness(engine,cfg,'test')
    assert r['status']=='ok' and r['maintenance']=='ACTIVE' and r['accepting_requests'] is False


def test_guard_fails_closed_on_missing_directory_and_links(tmp_path):
    assert maintenance_state(tmp_path/'missing',required=True)['blocked']
    (tmp_path/'link').symlink_to(tmp_path,target_is_directory=True)
    assert maintenance_state(tmp_path/'link',required=True)['blocked']
    assert maintenance_state(None,required=True)['blocked']
