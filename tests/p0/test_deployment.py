"""Real filesystem/locks plus explicit Docker fault injection, NOT a Docker drill."""
from pathlib import Path
import gzip,json,os,subprocess,sys
import pytest
from atomic_env import update_images
from backup_manifest import create,verify
from deploy_control import Pipeline,Maintenance,MaintenanceBusy,ControlError
from check_assembly import inspect_assembly
ROOT=Path(__file__).resolve().parents[2]

@pytest.mark.parametrize('initial',[
 'ND_API_IMAGE=old/api:x\nKEEP_ME=yes\n',
 'KEEP_ME=yes\n',
 'export ND_API_IMAGE="old/api:x"\r\nND_FRONTEND_IMAGE=old/front:x\r\nKEEP_ME=yes\r\n',
])
def test_atomic_images_add_replace_preserve_permissions(tmp_path,initial):
    p=tmp_path/'.env';p.write_bytes(initial.encode());p.chmod(0o640);before=p.stat()
    update_images(p,'new/api:release','new/front:release')
    after=p.stat();raw=p.read_bytes()
    assert b'ND_API_IMAGE=new/api:release' in raw and b'ND_FRONTEND_IMAGE=new/front:release' in raw and b'KEEP_ME=yes' in raw
    assert (after.st_mode&0o777)==0o640
    assert (after.st_uid,after.st_gid)==(before.st_uid,before.st_gid)
    assert after.st_ino!=before.st_ino
    if '\r\n' in initial:assert b'\r\n' in raw

@pytest.mark.parametrize('reference',['bad\nND_ENV=test','$(bad)','bad image','../bad:tag',''])
def test_bad_image_refs_do_not_touch_config(tmp_path,reference):
    p=tmp_path/'.env';p.write_text('KEEP=yes\n');old=p.read_bytes()
    with pytest.raises(ValueError):update_images(p,reference,'new/front:x')
    assert p.read_bytes()==old


def test_duplicate_image_keys_rejected(tmp_path):
    p=tmp_path/'.env';p.write_text('ND_API_IMAGE=a\nND_API_IMAGE=b\n');old=p.read_bytes()
    with pytest.raises(ValueError):update_images(p,'a:new','b:new')
    assert p.read_bytes()==old


def test_atomic_replace_failure_preserves_old_and_cleans_temp(tmp_path,monkeypatch):
    import atomic_env
    p=tmp_path/'.env';p.write_text('KEEP=yes\n');old=p.read_bytes()
    def fail(*args):raise OSError('injected interruption')
    monkeypatch.setattr(atomic_env.os,'replace',fail)
    with pytest.raises(OSError):update_images(p,'new/api:x','new/front:x')
    assert p.read_bytes()==old and not list(tmp_path.glob('.images-*'))


def test_symlink_environment_not_followed(tmp_path):
    real=tmp_path/'real';real.write_text('KEEP=yes\n');link=tmp_path/'.env';link.symlink_to(real)
    with pytest.raises(OSError):update_images(link,'new/api:x','new/front:x')
    assert real.read_text()=='KEEP=yes\n'

@pytest.fixture
def backup_dir(tmp_path):
    root=tmp_path/'backup';root.mkdir();(root/'files').mkdir()
    (root/'files/certificate.bin').write_bytes(b'isolated-test-bytes')
    with gzip.open(root/'database.sql.gz','wb') as f:f.write(b'-- isolated dump, not an actual DB acceptance\n')
    return root


def test_manifest_roundtrip(backup_dir):
    result=create(backup_dir)
    assert result==verify(backup_dir) and result['files']==2

@pytest.mark.parametrize('kind',['modify','remove','extra','symlink','traversal'])
def test_manifest_rejects_tampering(backup_dir,kind):
    create(backup_dir);target=backup_dir/'files/certificate.bin'
    if kind=='modify':target.write_bytes(b'tampered')
    if kind=='remove':target.unlink()
    if kind=='extra':(backup_dir/'unlisted').write_text('unexpected')
    if kind=='symlink':target.unlink();target.symlink_to('/etc/hosts')
    if kind=='traversal':
        m=json.loads((backup_dir/'manifest.json').read_text());m['files']['../outside']={'sha256':'x'*64,'bytes':1};(backup_dir/'manifest.json').write_text(json.dumps(m))
    with pytest.raises(ValueError):verify(backup_dir)

class DockerFaultDriver:
    """Test-only command double. It never starts containers or returns real DB evidence."""
    def __init__(self,root,fail=None):
        self.root=root;self.running={'api','worker','frontend'};self.calls=[];self.fail=fail;self.failed=False;self.mismatch=False
    def image(self,reference):return 'sha256:'+('f'*64 if 'front' in reference else 'a'*64)
    def run(self,command,**kwargs):
        active=self.root/'runtime/maintenance/active'
        stage=json.loads(active.read_text())['stage'] if active.exists() else None
        args=command[6:] if command[:2]==['docker','compose'] else command
        self.calls.append({'args':args,'stage':stage,'latch':active.exists()})
        if self.fail and not self.failed and self.fail(args,stage):
            self.failed=True;raise ControlError('explicit Docker fault injection')
        if command[:3]==['docker','image','inspect']:
            return json.dumps([{'Id':self.image(command[3])}]).encode()
        if command[:2]==['docker','inspect']:
            return json.dumps([{'Image':'sha256:'+('z'*64 if self.mismatch else 'f'*64 if ident=='c-frontend' else 'a'*64),
                               'State':{'Running':True,'Health':{'Status':'healthy'}}} for ident in command[2:]]).encode()
        if args[:4]==['ps','--status','running','--services']:
            return ('\n'.join(s for s in ('api','worker','frontend') if s in self.running)).encode()
        if args[:2]==['ps','-q']:return ('c-'+args[2]).encode() if args[2] in self.running else b''
        if args==['ps','-aq']:return b'c-api' if self.running else b''
        if args and args[0]=='stop':self.running.clear();return b''
        if args and args[0]=='up':self.running.update(a for a in args if a in ('api','worker','frontend'));return b''
        if 'mysqldump' in args:
            kwargs['output'].write(b'-- SYNTHETIC SQL FOR ORCHESTRATOR TEST ONLY\nCREATE TABLE checkpoint_fixture(id INTEGER);\n');return b''
        if 'mysql' in args and '-N' in args:return b'0\n'
        return b''

class IsolatedPipeline(Pipeline):
    def database_snapshot(self):
        # Orchestrator fault double, deliberately not valid MySQL evidence.
        return {'snapshot_sha256':'a'*64,'tables':{'fixture':{'rows':1,'sha256':'b'*64}}}
    def preflight(self,operation):
        # Fixture assembly is intentionally not passed off as the real project.
        from atomic_env import read_env
        self.config=read_env(self.root/'deploy/.env')
    def installation_receipt(self):
        # Explicit orchestrator-only test double, never real database evidence.
        import hashlib
        return {'installation_id':'00000000-0000-0000-0000-000000000005','baseline_revision':'20260918_0001',
            'source_kind':'canonical_empty_school','contract_sha256':hashlib.sha256((ROOT/'backend/canonical_schema.json').read_bytes()).hexdigest(),
            'installed_at':'2026-09-18T00:00:00'}
    def smoke(self):
        assert (self.root/'runtime/maintenance/active').is_file()
        return {'status':'PASS','scope':'TEST_DOUBLE_ONLY','business_e2e':False}

@pytest.fixture
def pipeline(tmp_path):
    (tmp_path/'deploy').mkdir();(tmp_path/'deploy/.env').write_text('ND_API_IMAGE=old/api:x\nND_PUBLIC_ORIGIN=https://school.invalid\nKEEP_ME=yes\n')
    (tmp_path/'deploy/.env').chmod(0o640)
    (tmp_path/'runtime/files').mkdir(parents=True);(tmp_path/'runtime/files/proof.bin').write_bytes(b'synthetic attachment')
    runner=DockerFaultDriver(tmp_path)
    return IsolatedPipeline(tmp_path,runner)


def test_upgrade_has_one_lock_no_backup_resume_and_verified_images(pipeline):
    result=pipeline.run_upgrade('new/api:release','new/front:release')
    assert result['status']=='UPGRADE_SMOKE_VERIFIED'
    assert verify(result['backup'])['files']>=3
    assert not (pipeline.root/'runtime/maintenance/active').exists()
    assert all(c['latch'] for c in pipeline.runner.calls if c['args'] and c['args'][0]=='up')
    assert all(c['stage']=='starting_new_services' for c in pipeline.runner.calls if c['args'] and c['args'][0]=='up')
    assert 'ND_FRONTEND_IMAGE=new/front:release' in (pipeline.root/'deploy/.env').read_text()
    assert (pipeline.root/'deploy/.env').stat().st_mode&0o777==0o640

@pytest.mark.parametrize('stage',[
 'stopping_writers','database_and_file_backup','release_check','schema_migration',
 'database_grants','data_consistency_check','starting_new_services','verify_running_images',
])
def test_each_command_failure_keeps_latch_and_stops_writers(pipeline,stage):
    pipeline.runner.fail=lambda args,current:current==stage
    with pytest.raises(ControlError):pipeline.run_upgrade('new/api:x','new/front:x')
    assert not pipeline.runner.running
    marker=json.loads((pipeline.root/'runtime/maintenance/active').read_text())
    assert marker['stage'].startswith('FAILED_AT_')
    with pytest.raises(MaintenanceBusy):
        with Maintenance(pipeline,'retry'):pass


def test_smoke_failure_keeps_services_closed(pipeline):
    def fail():raise ControlError('explicit smoke failure')
    pipeline.smoke=fail
    with pytest.raises(ControlError):pipeline.run_upgrade('new/api:x','new/front:x')
    assert not pipeline.runner.running and (pipeline.root/'runtime/maintenance/active').exists()


def test_wrong_running_image_is_not_success(pipeline):
    pipeline.runner.mismatch=True
    with pytest.raises(ControlError):pipeline.run_upgrade('new/api:x','new/front:x')
    assert not pipeline.runner.running


def test_standalone_backup_restores_only_originally_running_set(pipeline):
    pipeline.runner.running={'api','frontend'}
    r=pipeline.run_backup()
    assert pipeline.runner.running=={'api','frontend'} and r['restore_tested'] is False
    assert not (pipeline.root/'runtime/maintenance/active').exists()


def test_inherited_owner_backup_never_resumes(pipeline):
    pipeline.runner.running.clear()
    with Maintenance(pipeline,'upgrade') as owner:
        pipeline.create_backup(owner)
        assert (pipeline.root/'runtime/maintenance/active').exists()
        assert not any(c['args'][0]=='up' for c in pipeline.runner.calls)
        owner.success()


def test_real_flock_excludes_another_process(pipeline):
    lock=pipeline.root/'runtime/maintenance.lock'
    code="import fcntl,sys;f=open(sys.argv[1],'a');\ntry:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)\nexcept BlockingIOError:sys.exit(7)\n"
    with Maintenance(pipeline,'backup') as owner:
        p=subprocess.run([sys.executable,'-c',code,str(lock)],timeout=5)
        assert p.returncode==7
        owner.success()
    p=subprocess.run([sys.executable,'-c',code,str(lock)],timeout=5)
    assert p.returncode==0


def test_empty_restore_never_overwrites_files(pipeline):
    with pytest.raises(ControlError,match='not empty'):pipeline.empty_school()
    assert (pipeline.root/'runtime/files/proof.bin').read_bytes()==b'synthetic attachment'


def test_actual_fresh_source_passes_but_missing_contract_blocks_before_docker(tmp_path):
    import shutil
    report=inspect_assembly(ROOT)
    assert report['status']=='PASS'
    assert report['observed_alembic_heads']==['20261021_0006']
    assert report['legacy_upgrade_allowed'] is False and report['historical_graph_verified'] is False
    source=tmp_path/'source'
    shutil.copytree(ROOT,source,ignore=shutil.ignore_patterns('.git','__pycache__','.pytest_cache','runtime','evidence'))
    (source/'backend/canonical_schema.json').unlink()
    class NoCommands:
        def run(self,*args,**kwargs):raise AssertionError('must not invoke any command with incomplete source')
    p=Pipeline(source,NoCommands())
    with pytest.raises(ControlError,match='source assembly incomplete'):p.run_upgrade('new/api:x','new/front:x')


def test_maintenance_rejects_symlink_ancestor_without_touching_target(tmp_path):
    outside=tmp_path/'another-school';outside.mkdir()
    project=tmp_path/'source';project.mkdir();(project/'runtime').symlink_to(outside,target_is_directory=True)
    p=Pipeline(project,DockerFaultDriver(project))
    with pytest.raises(ControlError,match='path component'):
        with Maintenance(p,'upgrade'):pass
    assert list(outside.iterdir())==[]
    assert not p.runner.calls


def test_maintenance_rejects_hardlinked_lock(tmp_path):
    (tmp_path/'runtime').mkdir();outside=tmp_path/'other.lock';outside.write_text('preserve')
    os.link(outside,tmp_path/'runtime/maintenance.lock')
    p=Pipeline(tmp_path,DockerFaultDriver(tmp_path))
    with pytest.raises(ControlError,match='regular'):
        with Maintenance(p,'upgrade'):pass
    assert outside.read_text()=='preserve'
    assert not (tmp_path/'runtime/maintenance/active').exists()


def test_failed_stop_is_explicitly_not_claimed_as_stopped(pipeline):
    def cannot_stop():raise ControlError('daemon unavailable')
    pipeline.stop_writers=cannot_stop
    with pytest.raises(ControlError):
        with Maintenance(pipeline,'upgrade') as owner:
            owner.mark('stopping_writers')
            pipeline.stop_writers()
    marker=json.loads((pipeline.root/'runtime/maintenance/active').read_text())
    assert marker['stop_confirmed'] is False
    assert marker['manual_isolation_required'] is True
    assert pipeline.runner.running=={'api','worker','frontend'}


def test_failed_operation_reports_confirmed_stop(pipeline):
    with pytest.raises(ValueError):
        with Maintenance(pipeline,'upgrade') as owner:raise ValueError('fault')
    marker=json.loads((pipeline.root/'runtime/maintenance/active').read_text())
    assert marker['stop_confirmed'] is True
    assert not marker['manual_isolation_required']


def test_quoted_deployment_config_with_comments(tmp_path):
    from atomic_env import read_env
    p=tmp_path/'.env';p.write_text('ND_API_IMAGE="my/api:tag" # approved image\nND_FRONTEND_IMAGE=\'my/front:tag\' # local tag\n')
    assert read_env(p)=={'ND_API_IMAGE':'my/api:tag','ND_FRONTEND_IMAGE':'my/front:tag'}


def test_failure_to_durably_save_backup_keeps_upgrade_closed(pipeline,monkeypatch):
    import deploy_control
    def disk_failure(root):raise OSError('injected disk fsync failure')
    monkeypatch.setattr(deploy_control,'sync_backup_tree',disk_failure)
    with pytest.raises(OSError):pipeline.run_upgrade('new/api:x','new/front:x')
    assert not pipeline.runner.running
    assert (pipeline.root/'runtime/maintenance/active').exists()
    assert list((pipeline.root/'runtime/backups').glob('.partial-*'))
    assert not list((pipeline.root/'runtime/backups').glob('*.receipt.json'))
