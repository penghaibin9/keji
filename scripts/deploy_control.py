#!/usr/bin/env python3
"""Maintenance-owned backup, upgrade and empty-school install/restore.

Only the top-level operation owns the lock. An upgrade calls create_backup with
that owner; the backup cannot restart services or remove the durable latch.
No Docker, SQL, filesystem or TLS success is simulated by production code.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import fcntl
import gzip
import json
import os
from pathlib import Path
import secrets
import shutil
import stat
import subprocess
import tempfile
import hashlib
import uuid

from atomic_env import read_env, update_images, validate_image
from backup_manifest import create as create_manifest, verify as verify_manifest, inventory
from check_assembly import inspect_assembly
from deployment_smoke import run_smoke
from deployment_config import verify_private_bundle, APP_SECRET_NAMES, ROOT_SECRET_NAMES, DB_UID, regular_bytes

WRITERS=('frontend','worker','api')
START_ORDER=('api','worker','frontend')

class ControlError(RuntimeError): pass
class MaintenanceBusy(ControlError): pass


def validate_installation_receipt(root, receipt):
    """Receipt is a safety boundary, not a signature against a privileged DBA."""
    if not isinstance(receipt, dict): raise ControlError('canonical backup provenance missing')
    required = {'installation_id','baseline_revision','source_kind','contract_sha256','installed_at'}
    if set(receipt) != required: raise ControlError('canonical backup provenance invalid')
    expected = hashlib.sha256((Path(root)/'backend/canonical_schema.json').read_bytes()).hexdigest()
    try:
        valid_id = str(uuid.UUID(receipt['installation_id'])) == receipt['installation_id']
        datetime.fromisoformat(receipt['installed_at'])
    except (TypeError, ValueError, AttributeError): raise ControlError('canonical backup provenance invalid') from None
    if (not valid_id or receipt['baseline_revision'] != '20260918_0001'
        or receipt['source_kind'] != 'canonical_empty_school' or receipt['contract_sha256'] != expected):
        raise ControlError('legacy or unknown backup restore is forbidden')
    return receipt


def fsync_dir(path):
    fd=os.open(path,os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


def write_json(path,data,mode=0o600):
    path=Path(path);fd,name=tempfile.mkstemp(prefix='.state-',dir=path.parent)
    try:
        os.fchmod(fd,mode)
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            json.dump(data,f,ensure_ascii=False,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
        os.replace(name,path);fsync_dir(path.parent)
    finally:
        if os.path.lexists(name):os.unlink(name)


def safe_directory(path,mode=0o700):
    # Check every existing ancestor, not just the final directory. Never follow a
    # runtime/backups link into a different school's data while running as root.
    path=Path(os.path.abspath(path))
    for component in (*reversed(path.parents),path):
        if os.path.lexists(component):
            if not stat.S_ISDIR(component.lstat().st_mode):
                raise ControlError('symbolic or non-directory path component rejected')
        else:
            component.mkdir(mode=mode)
    return path


def sync_backup_tree(root):
    """Make copied bytes durable before marking a backup as hash-verified."""
    for directory,dirs,files in os.walk(root,topdown=False,followlinks=False):
        for name in files:
            fd=os.open(Path(directory)/name,os.O_RDONLY|os.O_NOFOLLOW)
            try:
                info=os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:
                    raise ControlError('unsafe backup entry')
                os.fsync(fd)
            finally:os.close(fd)
        fsync_dir(directory)


class Runner:
    def run(self,command,*,extra_env=None,input_bytes=None,input_stream=None,output=None,timeout=180):
        if input_stream is not None and input_bytes is not None:raise ControlError('ambiguous command input')
        env=os.environ.copy()
        for key in list(env):
            if key.startswith('COMPOSE_') or key in {'ND_API_IMAGE','ND_FRONTEND_IMAGE','ND_PROJECT_NAME',
                   'ND_BIND_IP','ND_HTTPS_PORT','ND_MYSQL_IMAGE','ND_PYTHON_IMAGE','ND_NGINX_IMAGE'}:
                env.pop(key,None)
        env.update(extra_env or {})
        try:
            result=subprocess.run(command,stdin=input_stream,input=input_bytes,stdout=output if output is not None else subprocess.PIPE,
                                  stderr=subprocess.PIPE,env=env,timeout=timeout,check=False)
        except (OSError,subprocess.TimeoutExpired):
            raise ControlError('command unavailable or timed out; output suppressed') from None
        if result.returncode:
            raise ControlError('command failed; sensitive command output suppressed')
        return result.stdout or b''


class Maintenance:
    def __init__(self,pipeline,operation):
        self.pipeline=pipeline;self.root=pipeline.root;self.operation=operation
        self.directory=self.root/'runtime/maintenance';self.active=self.directory/'active'
        self.fd=None;self.done=False;self.owned=False;self.stage='acquiring'
        self.started=datetime.now(timezone.utc).isoformat()
    def __enter__(self):
        safe_directory(self.root/'runtime',0o750);safe_directory(self.directory,0o755)
        # App UID 10001 can inspect the directory but must not be able to modify it.
        if self.directory.stat().st_uid!=os.geteuid():
            raise ControlError('maintenance directory must be owned by deployment administrator')
        os.chmod(self.directory,0o755)
        lock=self.root/'runtime/maintenance.lock'
        self.fd=os.open(lock,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
        lock_info=os.fstat(self.fd)
        if not stat.S_ISREG(lock_info.st_mode) or lock_info.st_nlink!=1 or lock_info.st_uid!=os.geteuid():
            os.close(self.fd);self.fd=None;raise ControlError('maintenance lock must be regular')
        try:fcntl.flock(self.fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(self.fd);self.fd=None;raise MaintenanceBusy('another maintenance operation is running') from None
        if os.path.lexists(self.active):
            os.close(self.fd);self.fd=None
            raise MaintenanceBusy('unresolved maintenance latch exists; manual recovery is required')
        self.owned=True
        try:self.mark('entered')
        except Exception:
            self.__exit__(*__import__('sys').exc_info());raise
        return self
    def mark(self,stage,**diagnostics):
        if not self.owned or self.fd is None or self.done:raise ControlError('operation does not own maintenance')
        self.stage=stage
        write_json(self.active,{'operation':self.operation,'owner_pid':os.getpid(),'started_at':self.started,
                               'stage':stage,'accepting_requests':False,**diagnostics},0o644)
    def success(self):
        self.mark('verified_ready_to_open')
        logdir=safe_directory(self.root/'runtime/logs',0o700)
        write_json(logdir/('maintenance-'+secrets.token_hex(8)+'.json'),{
            'operation':self.operation,'status':'VERIFIED','started_at':self.started,
            'finished_at':datetime.now(timezone.utc).isoformat(), 'scope':'deployment smoke, not procurement acceptance'})
        self.active.unlink();fsync_dir(self.directory);self.done=True
    def __exit__(self,exc_type,exc,tb):
        try:
            if self.owned and not self.done:
                try:self.mark('FAILED_AT_'+self.stage)
                except Exception:pass
                # No trap or finally path is allowed to restart business services.
                try:
                    self.pipeline.stop_writers()
                    self.mark(self.stage,stop_confirmed=True,manual_isolation_required=False)
                except Exception:
                    # A dead Docker daemon is not proof that its containers stopped.
                    try:self.mark(self.stage,stop_confirmed=False,manual_isolation_required=True)
                    except Exception:pass
        finally:
            if self.fd is not None:
                os.close(self.fd);self.fd=None
        return False


class Pipeline:
    def __init__(self,root,runner=None):
        self.root=Path(root).resolve();self.runner=runner or Runner();self.config={}
        self.compose=['docker','compose','--env-file',str(self.root/'deploy/.env'),'-f',str(self.root/'deploy/compose.yml')]
    def dc(self,*args,**kwargs):return self.runner.run(self.compose+list(args),**kwargs)
    def preflight(self,operation):
        # Never stop a school before detecting the current missing-source baseline.
        assembly=inspect_assembly(self.root)
        if assembly['status']!='PASS':raise ControlError('source assembly incomplete; run scripts/check_assembly.py for missing files')
        env=self.root/'deploy/.env'
        if env.is_symlink() or not env.is_file() or env.stat().st_nlink!=1:raise ControlError('private deployment environment file missing')
        self.config=read_env(env)
        for key in ('ND_API_IMAGE','ND_FRONTEND_IMAGE'):
            if operation in {'install','restore'} or self.config.get(key):
                validate_image(self.config.get(key,''))
        origin=self.config.get('ND_PUBLIC_ORIGIN','')
        from urllib.parse import urlsplit
        u=urlsplit(origin)
        if u.scheme!='https' or not u.hostname or u.username or u.password or u.path not in {'','/'} or u.query or u.fragment:
            raise ControlError('ND_PUBLIC_ORIGIN must be configured before maintenance')
        for name in ('tls/fullchain.pem','tls/privkey.pem','secrets/root.cnf','secrets/runtime_url','secrets/migration_url'):
            p=self.root/'deploy'/name
            if p.is_symlink() or not p.is_file() or not p.stat().st_size:raise ControlError('deployment TLS/secrets are not complete')
        # File-backed Compose secrets retain host UID/mode; verify both identities
        # and TLS pairing/hostname before taking a school into maintenance.
        verify_private_bundle(self.root, require_ownership=operation not in {'install','restore'})
        if operation in {'backup','upgrade'} and not (self.root/'runtime/files').is_dir():raise ControlError('existing private file store missing')
        safe_directory(self.root/'runtime',0o750)
        for p in ('backups','logs'):safe_directory(self.root/'runtime'/p,0o700)
        self.dc('config','--quiet')
        # The declared MySQL image must match the private file ownership contract.
        actual_uid=self.runner.run(['docker','run','--rm','--network','none','--pull','never',
            '--entrypoint','id',self.config['ND_MYSQL_IMAGE'],'-u','mysql']).strip()
        if actual_uid!=str(DB_UID).encode():raise ControlError('MySQL image user identity mismatch')
    def installation_receipt(self):
        raw = self.dc('run','--rm','--no-deps','--pull','never','migrate',
                      'python','-m','app.installation','verify')
        try: receipt = json.loads(raw)
        except (ValueError, TypeError): raise ControlError('canonical installation verification failed') from None
        return validate_installation_receipt(self.root, receipt)
    def database_snapshot(self):
        raw=self.dc('run','--rm','--no-deps','--pull','never','migrate',
            'python','-m','app.database_snapshot',timeout=900)
        try:value=json.loads(raw)
        except (ValueError,TypeError):raise ControlError('database reconciliation receipt invalid') from None
        if not isinstance(value,dict) or not value.get('snapshot_sha256') or not isinstance(value.get('tables'),dict):
            raise ControlError('database reconciliation receipt invalid')
        return value
    def running_writers(self):
        names=self.dc('ps','--status','running','--services').decode().split()
        return [s for s in START_ORDER if s in names]
    def stop_writers(self):
        self.dc('stop','-t','45',*WRITERS,timeout=180)
        if self.running_writers():raise ControlError('one or more business services did not stop')
    def resume(self,services):
        if services:self.dc('up','-d','--no-deps','--no-build','--pull','never','--wait','--wait-timeout','120',*services,timeout=180)
    def resolve_images(self,api,frontend):
        expected={}
        for name,ref in (('api',api),('frontend',frontend)):
            validate_image(ref)
            result=json.loads(self.runner.run(['docker','image','inspect',ref]))
            if len(result)!=1 or not isinstance(result[0].get('Id'),str) or not result[0]['Id'].startswith('sha256:'):
                raise ControlError('requested image could not be resolved')
            expected[name]=result[0]['Id']
        expected['worker']=expected['api']
        return expected
    def verify_images(self,expected):
        for service in START_ORDER:
            ids=self.dc('ps','-q',service).decode().split()
            if not ids:raise ControlError('new service container missing')
            containers=json.loads(self.runner.run(['docker','inspect',*ids]))
            if len(containers)!=len(ids):raise ControlError('container inspection incomplete')
            for container in containers:
                if container.get('Image')!=expected[service] or container.get('State',{}).get('Running') is not True:
                    raise ControlError('running container does not match requested image')
                health=container['State'].get('Health',{}).get('Status')
                if (service in {'api','worker'} and health!='healthy') or health in {'unhealthy','starting'}:
                    raise ControlError('new service is not healthy')
    def migrate(self,owner):
        owner.mark('release_check')
        self.dc('run','--rm','--no-deps','--pull','never','migrate','python','-m','app.releasecheck')
        owner.mark('schema_migration')
        self.dc('run','--rm','--no-deps','--pull','never','migrate','alembic','upgrade','head',timeout=900)
    def grants_and_check(self,owner):
        owner.mark('database_grants')
        sql=self.dc('run','--rm','--no-deps','--pull','never','migrate','python','-c','from app.grants import sql; print(sql())')
        self.dc('exec','-T','db','mysql','--defaults-extra-file=/run/secrets/root_cnf',input_bytes=sql)
        owner.mark('data_consistency_check')
        self.dc('run','--rm','--no-deps','--pull','never','migrate','python','-m','app.cli','check')
    def smoke(self):
        ca=self.config.get('ND_TLS_CA_FILE') or None
        if ca:
            ca=Path(ca);ca=ca if ca.is_absolute() else self.root/ca
        return run_smoke(self.config['ND_PUBLIC_ORIGIN'],ca)
    def activate(self,owner,expected):
        owner.mark('starting_new_services')
        self.resume(START_ORDER)
        owner.mark('verify_running_images')
        self.verify_images(expected)
        owner.mark('https_readiness_and_assets_smoke')
        result=self.smoke()
        logdir=safe_directory(self.root/'runtime/logs',0o700)
        write_json(logdir/'last-deployment-smoke.json',result)
        owner.mark('final_image_recheck')
        self.verify_images(expected)
        owner.success() # Removing the durable latch is the last activation step.
    def create_backup(self,owner):
        """Called by either standalone backup or upgrade; never owns/relinquishes the lock."""
        if not owner.owned or owner.done or owner.pipeline is not self:raise ControlError('backup requires the current maintenance owner')
        if self.running_writers():raise ControlError('cannot snapshot while business services are running')
        provenance = self.installation_receipt()
        reconciliation = self.database_snapshot()
        owner.mark('database_and_file_backup')
        base=safe_directory(self.root/'runtime/backups',0o700)
        stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+secrets.token_hex(4)
        stage=Path(tempfile.mkdtemp(prefix='.partial-'+stamp+'-',dir=base));os.chmod(stage,0o700)
        # A dump command failure cannot be hidden by a successful gzip process.
        raw=stage/'database.sql'
        with raw.open('xb') as output:
            os.chmod(raw,0o600)
            self.dc('exec','-T','db','mysqldump','--defaults-extra-file=/run/secrets/root_cnf',
                    '--single-transaction','--routines','--triggers','--events','--hex-blob',
                    '--no-tablespaces','--set-gtid-purged=OFF','nondegree',output=output,timeout=900)
            output.flush();os.fsync(output.fileno())
        if raw.stat().st_size==0:raise ControlError('empty database dump')
        with raw.open('rb') as source,gzip.open(stage/'database.sql.gz','wb') as target:shutil.copyfileobj(source,target,1024*1024)
        raw.unlink()
        with gzip.open(stage/'database.sql.gz','rb') as check:
            while check.read(1024*1024):pass
        source=self.root/'runtime/files'
        inventory(source) # Reject links/special files before copying from the stopped store.
        shutil.copytree(source,stage/'files',copy_function=shutil.copy2)
        shutil.copy2(self.root/'deploy/.env',stage/'school-config.env')
        write_json(stage/'installation-provenance.json', provenance)
        write_json(stage/'database-reconciliation.json', reconciliation)
        write_json(stage/'backup-metadata.json',{'operation':owner.operation,'time':datetime.now(timezone.utc).isoformat(),
                   'source_database':'nondegree','mode':'stopped-writers','contains_secrets': 'school-config.env is private',
                   'restore_policy':'empty school instance only'})
        for d,dirs,files in os.walk(stage):
            os.chmod(d,0o700)
            for name in files:os.chmod(Path(d)/name,0o600)
        owner.mark('backup_manifest_verification')
        result=create_manifest(stage);verify_manifest(stage)
        sync_backup_tree(stage)
        dest=base/stamp;os.rename(stage,dest);fsync_dir(base)
        # Operational receipt is outside the DB snapshot; no post-dump application writes.
        write_json(base/(stamp+'.receipt.json'),{'backup':stamp,**result,'status':'HASH_VERIFIED_NOT_RESTORE_TESTED'})
        return dest
    def run_backup(self):
        self.preflight('backup');before=self.running_writers()
        with Maintenance(self,'backup') as owner:
            owner.mark('stopping_writers');self.stop_writers()
            backup=self.create_backup(owner)
            owner.mark('restoring_previously_running_services');self.resume(before)
            if self.running_writers()!=before:raise ControlError('running service set changed')
            owner.success()
        return {'status':'BACKUP_HASH_VERIFIED','backup':str(backup),'restore_tested':False}
    def run_upgrade(self,api,frontend):
        self.preflight('upgrade')
        self.installation_receipt()  # Reject legacy before stopping any writers or changing images.
        expected=self.resolve_images(api,frontend)
        with Maintenance(self,'upgrade') as owner:
            owner.mark('stopping_writers');self.stop_writers()
            backup=self.create_backup(owner)
            owner.mark('atomic_image_configuration')
            update_images(self.root/'deploy/.env',api,frontend)
            self.migrate(owner);self.grants_and_check(owner);self.activate(owner,expected)
        return {'status':'UPGRADE_SMOKE_VERIFIED','backup':str(backup),'business_e2e':False,'procurement_acceptance':False}
    def empty_school(self):
        for directory in ('runtime/mysql','runtime/files'):
            p=self.root/directory
            if p.is_symlink() or (p.exists() and (not p.is_dir() or any(p.iterdir()))):
                raise ControlError('target school is not empty; overwriting is forbidden')
        if self.dc('ps','-aq').strip():raise ControlError('existing Compose project containers found; use an independent empty instance')
    def _prepare_private_files(self):
        for name in APP_SECRET_NAMES:
            p=self.root/'deploy/secrets'/name
            regular_bytes(p,maximum=65536)
            os.chown(p,10001,10001);os.chmod(p,0o400)
        for name in ROOT_SECRET_NAMES:
            p=self.root/'deploy/secrets'/name
            regular_bytes(p,maximum=65536)
            os.chown(p,DB_UID,DB_UID);os.chmod(p,0o400)
        p=safe_directory(self.root/'runtime/files',0o700)
        for d,dirs,files in os.walk(p):
            os.chown(d,10001,10001);os.chmod(d,0o700)
            for name in files:os.chown(Path(d)/name,10001,10001);os.chmod(Path(d)/name,0o600)
        for p in (self.root/'deploy/tls',self.root/'deploy/tls/fullchain.pem',self.root/'deploy/tls/privkey.pem'):
            os.chown(p,10001,10001);os.chmod(p,0o750 if p.is_dir() else 0o640)
    def run_install(self):
        self.preflight('install');self.empty_school()
        expected=self.resolve_images(self.config['ND_API_IMAGE'],self.config['ND_FRONTEND_IMAGE'])
        with Maintenance(self,'install') as owner:
            self._prepare_private_files();owner.mark('starting_empty_database')
            self.dc('up','-d','--no-build','--pull','never','--wait','db')
            self.migrate(owner);owner.mark('empty_business_initialization')
            self.dc('run','--rm','--no-deps','--pull','never','migrate','python','-m','app.cli','init','--password-file','/run/secrets/admin_password')
            self.grants_and_check(owner);self.activate(owner,expected)
        return {'status':'EMPTY_SCHOOL_INITIALIZED','procurement_acceptance':False}
    def run_restore(self,backup,username='admin'):
        backup=Path(backup)
        verify_manifest(backup)
        proof = backup/'installation-provenance.json'
        if proof.is_symlink() or not proof.is_file() or proof.stat().st_size > 4096:
            raise ControlError('legacy backup without canonical provenance cannot be restored')
        expected_provenance = validate_installation_receipt(self.root, json.loads(proof.read_text()))
        snapshot_path=backup/'database-reconciliation.json'
        if snapshot_path.is_symlink() or not snapshot_path.is_file() or snapshot_path.stat().st_size>4*1024*1024:
            raise ControlError('backup lacks R7 database reconciliation; automatic restore refused')
        expected_rows=json.loads(snapshot_path.read_text())
        if not isinstance(expected_rows,dict) or not expected_rows.get('snapshot_sha256') or not isinstance(expected_rows.get('tables'),dict):
            raise ControlError('backup database reconciliation is invalid')
        self.preflight('restore');self.empty_school()
        expected=self.resolve_images(self.config['ND_API_IMAGE'],self.config['ND_FRONTEND_IMAGE'])
        with Maintenance(self,'restore') as owner:
            self._prepare_private_files();owner.mark('starting_empty_database')
            self.dc('up','-d','--no-build','--pull','never','--wait','db')
            count=self.dc('exec','-T','db','mysql','--defaults-extra-file=/run/secrets/root_cnf','-N','-e',
                    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='nondegree';").strip()
            if count!=b'0':raise ControlError('destination database already has tables; restore refused')
            owner.mark('restoring_database')
            # Named temporary SQL is private and removed even if restore fails.
            with tempfile.TemporaryFile(dir=self.root/'runtime',mode='w+b') as raw:
                with gzip.open(backup/'database.sql.gz','rb') as source:shutil.copyfileobj(source,raw,1024*1024)
                raw.flush();raw.seek(0)
                self._restore_sql_stream(raw)
            owner.mark('verifying_restored_canonical_provenance')
            if self.installation_receipt() != expected_provenance:
                raise ControlError('restored database identity differs from backup provenance')
            owner.mark('reconciling_database_before_sanitation')
            if self.database_snapshot()!=expected_rows:
                raise ControlError('restored database row digests differ; writes remain closed')
            owner.mark('restoring_original_files')
            shutil.copytree(backup/'files',self.root/'runtime/files',dirs_exist_ok=True)
            self._prepare_private_files()
            if inventory(self.root/'runtime/files')!=inventory(backup/'files'):
                raise ControlError('restored attachment hashes do not match backup')
            sync_backup_tree(self.root/'runtime/files')
            self.migrate(owner);owner.mark('revoking_restored_sessions')
            self.dc('run','--rm','--no-deps','--pull','never','migrate','python','-m','app.maintenance','sanitize-restore',
                    '--username',username,'--password-file','/run/secrets/admin_password')
            self.grants_and_check(owner);self.activate(owner,expected)
        return {'status':'EMPTY_SCHOOL_RESTORE_SMOKE_VERIFIED','database_row_digests_verified':True,
                'business_reconciliation_required':True}
    def _restore_sql_stream(self,stream):
        # Streaming avoids loading a school database dump into memory.
        self.dc('exec','-T','db','mysql','--defaults-extra-file=/run/secrets/root_cnf','nondegree',input_stream=stream,timeout=900)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='operation',required=True)
    b=sub.add_parser('backup');b.add_argument('--allow-maintenance-window',action='store_true',required=True)
    u=sub.add_parser('upgrade');u.add_argument('--allow-maintenance-window',action='store_true',required=True);u.add_argument('api');u.add_argument('frontend')
    i=sub.add_parser('install');i.add_argument('--initialize-new-school',action='store_true',required=True)
    r=sub.add_parser('restore');r.add_argument('--into-empty-school',action='store_true',required=True);r.add_argument('backup');r.add_argument('username',nargs='?',default='admin')
    a=p.parse_args()
    if os.geteuid()!=0:p.exit(2,'BLOCKED: run with administrator approval via sudo.\n')
    pipeline=Pipeline(Path(__file__).resolve().parents[1])
    try:
        if a.operation=='backup':result=pipeline.run_backup()
        elif a.operation=='upgrade':result=pipeline.run_upgrade(a.api,a.frontend)
        elif a.operation=='install':result=pipeline.run_install()
        else:result=pipeline.run_restore(a.backup,a.username)
    except (ControlError,ValueError,OSError):
        p.exit(2,'BLOCKED: operation failed. Inspect source assembly and runtime/maintenance/active; writes are not automatically reopened.\n')
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
