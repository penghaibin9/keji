"""Real SQLite controls for digest logic, never MySQL/restore acceptance."""
import copy, hashlib, json, sqlite3
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
import pytest
import sqlalchemy as sa
from test_r5_installation import canonical
from app.database_snapshot import take_snapshot, typed, validate_snapshot, compare_snapshots, payload_bytes
from app.installation import InstallationRejected
from deploy_control import Pipeline, ControlError
from backup_manifest import create
ROOT=Path(__file__).resolve().parents[2]

def engine(path): return sa.create_engine('sqlite:///'+str(path))
def read(path):
    e=engine(path)
    try:return take_snapshot(e,require_mysql=False)
    finally:e.dispose()

def test_deterministic_no_raw_rows_and_validated(canonical):
    first=read(canonical);second=read(canonical)
    assert first==second and len(first['tables'])==47
    assert validate_snapshot(first)==first
    assert compare_snapshots(first,second)['tables']==47
    assert all(set(x)=={'rows','columns','sha256'} for x in first['tables'].values())

def test_real_sqlite_backup_copy_reconciles_then_same_count_tampering_fails(canonical,tmp_path):
    e=engine(canonical)
    with e.begin() as c:
        c.exec_driver_sql("INSERT INTO settings (key,value,version) VALUES ('snapshot-test','{\"secret_note\":\"not_for_receipt\"}',1)")
    e.dispose()
    before=read(canonical);assert 'not_for_receipt' not in json.dumps(before)
    dest=tmp_path/'restored.sqlite'
    with sqlite3.connect(canonical) as a,sqlite3.connect(dest) as b:a.backup(b)
    assert compare_snapshots(before,read(dest))['status']=='MATCH'
    with sqlite3.connect(dest) as c:c.execute("UPDATE settings SET value='{}' WHERE key='snapshot-test'")
    after=read(dest)
    assert before['tables']['settings']['rows']==after['tables']['settings']['rows']
    with pytest.raises(ValueError,match='ROWS_DO_NOT_MATCH'):compare_snapshots(before,after)

def test_snapshot_rejects_missing_provenance(canonical):
    with sqlite3.connect(canonical) as c:c.execute('DELETE FROM installation_provenance')
    with pytest.raises(InstallationRejected):read(canonical)

def test_real_mysql_required_by_default(canonical):
    e=engine(canonical)
    try:
        with pytest.raises(InstallationRejected,match='MYSQL_84_REQUIRED'):take_snapshot(e)
    finally:e.dispose()

@pytest.mark.parametrize('mutation',['count','digest','columns','missing_table','extra_table','missing_key','wrong_baseline','bad_rows_bool','bad_contract'])
def test_invalid_receipts_are_rejected(canonical,mutation):
    value=read(canonical);t=next(iter(value['tables']))
    if mutation=='count':value['tables'][t]['rows']+=1
    elif mutation=='digest':value['snapshot_sha256']='a'*64
    elif mutation=='columns':value['tables'][t]['columns']=['not_a_column']
    elif mutation=='missing_table':value['tables'].pop(t)
    elif mutation=='extra_table':value['tables']['unknown']=value['tables'][t]
    elif mutation=='missing_key':value.pop('installation_id')
    elif mutation=='wrong_baseline':value['baseline_revision']='20260917_0002'
    elif mutation=='bad_rows_bool':value['tables'][t]['rows']=True
    elif mutation=='bad_contract':value['contract_sha256']='bad'
    with pytest.raises(ValueError):validate_snapshot(value)

@pytest.mark.parametrize('value',[float('nan'),float('inf'),Decimal('NaN'),object(),{1:'a'}])
def test_nonportable_values_refused(value):
    with pytest.raises(ValueError):typed(value)

def test_types_are_distinct_and_json_order_deterministic():
    assert typed(Decimal('1.00'))!=typed('1.00')
    assert typed(datetime(2026,9,18,1,2,3))!=typed('2026-09-18T01:02:03.000000')
    assert typed(date(2026,9,18))!=typed('2026-09-18')
    assert typed(b'abc')!=typed('YWJj')
    assert typed(1.0)!=typed(1)
    assert payload_bytes(typed({'b':[2,None],'a':1}))==payload_bytes(typed({'a':1,'b':[2,None]}))

def test_r6_backup_without_row_receipt_fails_before_commands(canonical,tmp_path):
    from app.installation import require_canonical
    e=engine(canonical)
    with e.connect() as c:receipt=require_canonical(c)
    e.dispose()
    backup=tmp_path/'previous';backup.mkdir()
    (backup/'installation-provenance.json').write_text(json.dumps(receipt))
    (backup/'database.sql.gz').write_bytes(b'old controlled fixture, not a SQL restore')
    create(backup)
    class NoCommands:
        def run(self,*a,**kw):raise AssertionError('old backup must fail before any commands')
    with pytest.raises(ControlError,match='reconciliation'):Pipeline(ROOT,NoCommands()).run_restore(backup)

def test_container_uid_and_proxy_limit_match_runtime_configuration():
    docker=(ROOT/'deploy/Dockerfile.frontend').read_text()
    assert 'USER 10001:10001' in docker and 'USER nginx' not in docker
    nginx=(ROOT/'deploy/nginx.conf').read_text()
    assert 'client_max_body_size 101m;' in nginx

def test_restore_row_mismatch_never_opens_services(tmp_path,monkeypatch):
    from test_deployment import IsolatedPipeline,DockerFaultDriver
    from app.installation import BASELINE_REVISION
    import gzip,shutil
    root=tmp_path/'lab';(root/'deploy').mkdir(parents=True)
    (root/'backend').mkdir();shutil.copy(ROOT/'backend/canonical_schema.json',root/'backend/canonical_schema.json')
    (root/'deploy/.env').write_text('ND_API_IMAGE=local/api:r7\nND_FRONTEND_IMAGE=local/front:r7\nND_PUBLIC_ORIGIN=https://school.invalid\n')
    driver=DockerFaultDriver(root);driver.running.clear()
    p=IsolatedPipeline(root,driver)
    p._prepare_private_files=lambda: (root/'runtime/files').mkdir(parents=True,exist_ok=True)
    backup=tmp_path/'backup';backup.mkdir()
    (backup/'installation-provenance.json').write_text(json.dumps(p.installation_receipt()))
    (backup/'database-reconciliation.json').write_text(json.dumps({'snapshot_sha256':'c'*64,'tables':{'fixture':{'rows':1}}}))
    (backup/'files').mkdir()
    with gzip.open(backup/'database.sql.gz','wb') as f:f.write(b'EXPLICIT ORCHESTRATOR DOUBLE, NOT MYSQL')
    create(backup)
    with pytest.raises(ControlError,match='row digests differ'):p.run_restore(backup)
    assert (root/'runtime/maintenance/active').exists()
    assert not driver.running
    assert not any('sanitize-restore' in x['args'] for x in driver.calls)
    assert not any(x['stage']=='starting_new_services' for x in driver.calls)
