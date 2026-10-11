"""SQLite verifies control flow only. This file MUST NOT be labelled MySQL acceptance."""
import json,hashlib,os,subprocess,sys,shutil
from pathlib import Path
import pytest
import sqlalchemy as sa
from app.installation import require_canonical,InstallationRejected,migration_preflight,BASELINE_REVISION
from check_assembly import inspect_assembly
from deploy_control import Pipeline,ControlError,validate_installation_receipt
from backup_manifest import create
ROOT=Path(__file__).resolve().parents[2]

def cli(path,*args):
    env={**os.environ,'PYTHONPATH':str(ROOT/'backend'),'ND_ENV':'test','ND_DATABASE_URL':'sqlite:///'+str(path)}
    return subprocess.run([sys.executable,'-m','alembic','-c',str(ROOT/'backend/alembic.ini'),*args],env=env,cwd=ROOT/'backend',capture_output=True,text=True,timeout=15)

@pytest.fixture
def canonical(tmp_path):
    path=tmp_path/'fresh.sqlite';result=cli(path,'upgrade','head');assert result.returncode==0,result.stderr
    return path

def test_fresh_migration_provenance_and_repeat_noop(canonical):
    e=sa.create_engine('sqlite:///'+str(canonical))
    with e.connect() as c:first=require_canonical(c);assert len(sa.inspect(c).get_table_names())==55
    result=cli(canonical,'upgrade','head');assert result.returncode==0,result.stderr
    with e.connect() as c:assert require_canonical(c)==first
    e.dispose()

@pytest.mark.parametrize('kind',['old_revision','stamp_only','business_without_marker','extra_view'])
def test_unverified_databases_rejected_and_existing_data_preserved(tmp_path,kind):
    path=tmp_path/(kind+'.sqlite');e=sa.create_engine('sqlite:///'+str(path))
    with e.begin() as c:
        if kind in {'old_revision','stamp_only'}:
            c.exec_driver_sql('CREATE TABLE alembic_version(version_num VARCHAR(32) NOT NULL PRIMARY KEY)')
            c.execute(sa.text('INSERT INTO alembic_version VALUES (:v)'),{'v':'20260917_0002' if kind=='old_revision' else BASELINE_REVISION})
        else:
            c.exec_driver_sql('CREATE TABLE old_school_records(id INTEGER PRIMARY KEY, note TEXT)');c.exec_driver_sql("INSERT INTO old_school_records VALUES(1,'DO_NOT_CHANGE')")
            if kind=='extra_view':c.exec_driver_sql('CREATE VIEW old_school_view AS SELECT * FROM old_school_records')
        before=c.exec_driver_sql("SELECT name,sql FROM sqlite_master WHERE type IN ('table','view') ORDER BY name").all()
    result=cli(path,'upgrade','head');assert result.returncode!=0
    with e.connect() as c:
        after=c.exec_driver_sql("SELECT name,sql FROM sqlite_master WHERE type IN ('table','view') ORDER BY name").all();assert before==after
        if kind in {'business_without_marker','extra_view'}:assert c.exec_driver_sql('SELECT note FROM old_school_records').scalar()=='DO_NOT_CHANGE'
        assert 'installation_provenance' not in sa.inspect(c).get_table_names()
    e.dispose()

@pytest.mark.parametrize('mutation',['delete_marker','wrong_origin','wrong_uuid','wrong_hash','wrong_revision','extra_table','missing_index','extra_view'])
def test_marker_and_schema_drift_rejected(canonical,mutation):
    e=sa.create_engine('sqlite:///'+str(canonical))
    commands={'delete_marker':'DELETE FROM installation_provenance','wrong_origin':"UPDATE installation_provenance SET source_kind='legacy'",
      'wrong_uuid':"UPDATE installation_provenance SET installation_id='fake'",'wrong_hash':"UPDATE installation_provenance SET contract_sha256='fake'",
      'wrong_revision':"UPDATE alembic_version SET version_num='20260917_0002'",'extra_table':'CREATE TABLE unauthorized_table(id INTEGER)',
      'missing_index':'DROP INDEX ix_connection_checks_connection_id','extra_view':'CREATE VIEW fakeview AS SELECT 1'}
    with e.begin() as c:c.exec_driver_sql(commands[mutation])
    with e.connect() as c:
        with pytest.raises(InstallationRejected):require_canonical(c)
        with pytest.raises(InstallationRejected):migration_preflight(c)
    e.dispose()

@pytest.mark.parametrize('action',[('stamp','head'),('downgrade','base')])
def test_operator_stamp_and_destructive_downgrade_forbidden(canonical,action):
    result=cli(canonical,*action);assert result.returncode!=0
    e=sa.create_engine('sqlite:///'+str(canonical))
    with e.connect() as c:assert require_canonical(c)['baseline_revision']==BASELINE_REVISION
    e.dispose()

def test_runtime_provenance_is_select_only():
    from app.grants import sql
    lines=[x for x in sql().splitlines() if 'installation_provenance' in x and 'nondegree_app' in x]
    assert len(lines)==1 and 'SELECT ON' in lines[0]
    assert all(k not in lines[0] for k in ('INSERT','UPDATE','DELETE','CREATE','ALTER','DROP'))

def test_legacy_migration_bytes_are_preserved_and_excluded():
    p=ROOT/'backend/alembic_legacy_unverified/20260917_0002_org_assessment_and_sync.py'
    assert hashlib.sha256(p.read_bytes()).hexdigest()=='4189c4e40192edf320277a76538df6cc3e86e911af1f8a1d02156e95ccf3f938'
    assert not (ROOT/'backend/alembic/versions'/p.name).exists()
    report=inspect_assembly(ROOT);assert report['legacy_evidence_preserved'] and report['canonical_files_hash_verified']
    assert report['historical_graph_verified'] is False and report['legacy_upgrade_allowed'] is False

def test_legacy_backup_refused_before_docker_or_target_mutation(tmp_path):
    backup=tmp_path/'old_backup';backup.mkdir();(backup/'database.sql.gz').write_bytes(b'old backup evidence');create(backup)
    class NoCommands:
        def run(self,*a,**k):raise AssertionError('legacy restore must be rejected before commands')
    p=Pipeline(ROOT,NoCommands())
    with pytest.raises(ControlError,match='legacy backup'):p.run_restore(backup)

def test_provenance_backup_receipt_is_tied_to_current_contract(canonical):
    e=sa.create_engine('sqlite:///'+str(canonical))
    with e.connect() as c:receipt=require_canonical(c)
    assert validate_installation_receipt(ROOT,receipt)==receipt
    with pytest.raises(ControlError):validate_installation_receipt(ROOT,{**receipt,'contract_sha256':'0'*64})
    e.dispose()

def test_sqlite_mechanics_cannot_satisfy_mysql_requirement(canonical):
    e=sa.create_engine('sqlite:///'+str(canonical))
    with e.connect() as c:
        with pytest.raises(InstallationRejected,match='MYSQL_84_REQUIRED'):require_canonical(c,require_mysql=True)
    e.dispose()
