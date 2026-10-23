#!/usr/bin/env python3
"""Online backup: no business service is stopped and no maintenance marker is written.

The database is exported with mysqldump --single-transaction (one consistent InnoDB
snapshot while teachers keep working). Row digests are then taken from a throwaway,
network-isolated MySQL loaded from that very dump, so database-reconciliation.json
matches the dump exactly and every night doubles as a restore drill. Attachments are
content-addressed and write-once; they are copied before and after the dump without
deleting anything, so every file the dump refers to is present.

The backup directory has the same layout, manifest and receipt as deploy_control.py
create_backup, so run_restore and prune_backups.py work unchanged. A failure only
writes runtime/logs/ALERT-backup-failed and a diagnostic line; services keep running.
Usage (root): python3 scripts/online_backup.py
"""
from __future__ import annotations
from datetime import datetime, timezone
import fcntl
import gzip
import json
import os
from pathlib import Path
import secrets
import shutil
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from deploy_control import (ControlError, Pipeline, diagnostic_error, fsync_dir, safe_directory, sync_backup_tree,
                            validate_installation_receipt, write_json)
from backup_manifest import create as create_manifest, verify as verify_manifest, inventory
from atomic_env import read_env

DB_NAME = 'nondegree'


def copy_new_files(source, target):
    """Copy attachments that are not yet in the backup; never delete (files are write-once)."""
    inventory(source)  # rejects links and special files, as the stopped backup does
    target.mkdir(exist_ok=True)
    for directory, dirs, files in os.walk(source, followlinks=False):
        relative = Path(directory).relative_to(source)
        (target / relative).mkdir(exist_ok=True)
        for name in files:
            destination = target / relative / name
            if not destination.exists():
                shutil.copy2(Path(directory) / name, destination)


class OnlineBackup:
    def __init__(self, root, runner=None, clock=time.monotonic):
        self.pipeline = Pipeline(root, runner)
        self.root = self.pipeline.root
        self.run = self.pipeline.runner.run
        self.clock = clock
        self.stage = 'starting'
        self.token = secrets.token_hex(4)
        self.network = 'nd-backup-verify-' + self.token
        self.verify_db = 'nd-backup-verify-db-' + self.token

    def step(self, stage):
        self.stage = stage
        self.pipeline.stage = stage

    def docker(self, *args, **kwargs):
        return self.run(['docker', *args], root=self.root, stage=self.stage, **kwargs)

    def dump(self, raw):
        with raw.open('xb') as output:
            os.chmod(raw, 0o600)
            self.pipeline.dc('exec', '-T', 'db', 'mysqldump', '--defaults-extra-file=/run/secrets/root_cnf',
                             '--single-transaction', '--routines', '--triggers', '--events', '--hex-blob',
                             '--no-tablespaces', '--set-gtid-purged=OFF', DB_NAME, output=output, timeout=1800)
            output.flush()
            os.fsync(output.fileno())
        if raw.stat().st_size == 0:
            raise ControlError('empty database dump')

    def start_verify_db(self, config):
        """A private MySQL with no published port on an internal network, removed afterwards."""
        password = secrets.token_hex(16)
        self.docker('network', 'create', '--internal', self.network)
        self.docker('run', '-d', '--name', self.verify_db, '--network', self.network, '--pull', 'never',
                    '-e', 'MYSQL_ROOT_PASSWORD=' + password, '-e', 'MYSQL_DATABASE=' + DB_NAME, '-e', 'TZ=UTC',
                    config['ND_MYSQL_IMAGE'], '--character-set-server=utf8mb4', '--collation-server=utf8mb4_0900_ai_ci',
                    '--skip-name-resolve', '--local-infile=0', '--secure-file-priv=NULL')
        deadline = self.clock() + 300
        while True:
            try:
                self.docker('exec', '-e', 'MYSQL_PWD=' + password, self.verify_db, 'mysql', '-uroot', '--protocol=tcp',
                            '-h', '127.0.0.1', '-N', '-e', 'SELECT 1', timeout=20)
                return password
            except ControlError:
                if self.clock() > deadline:
                    raise ControlError('verification database did not start')
                time.sleep(3)

    def load_dump(self, dump_gz, password):
        with tempfile.TemporaryFile(dir=self.root / 'runtime', mode='w+b') as raw:
            with gzip.open(dump_gz, 'rb') as source:
                shutil.copyfileobj(source, raw, 1024 * 1024)
            raw.flush()
            raw.seek(0)
            self.docker('exec', '-i', '-e', 'MYSQL_PWD=' + password, self.verify_db, 'mysql', '-uroot', DB_NAME,
                        input_stream=raw, timeout=3600)

    def app_on_verify_db(self, config, password, *module_args):
        url = f'mysql+pymysql://root:{password}@{self.verify_db}:3306/{DB_NAME}'
        # Same school settings as the migrate service (origin, hosts), but pointed at the isolated copy.
        return self.docker('run', '--rm', '--network', self.network, '--pull', 'never', '--entrypoint', 'python',
                           '--env-file', str(self.root / 'deploy/.env'), '-e', 'TZ=Asia/Shanghai', '-e', 'ND_ENV=production', '-e', 'ND_DATABASE_URL=' + url, '-e', 'ND_SEED_ENABLED=false',
                           '-e', 'ND_SECURE_COOKIE=true', config['ND_API_IMAGE'], '-m', *module_args, timeout=1800)

    def remove_verify_db(self):
        for command in (['rm', '-f', '-v', self.verify_db], ['network', 'rm', self.network]):
            try:
                self.docker(*command, timeout=120)
            except ControlError:
                pass

    def create(self):
        self.step('preflight')
        env = self.root / 'deploy/.env'
        if env.is_symlink() or not env.is_file():
            raise ControlError('private deployment environment file missing')
        config = read_env(env)
        source = self.root / 'runtime/files'
        if not source.is_dir():
            raise ControlError('existing private file store missing')
        base = safe_directory(self.root / 'runtime/backups', 0o700)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + self.token
        stage = Path(tempfile.mkdtemp(prefix='.partial-' + stamp + '-', dir=base))
        os.chmod(stage, 0o700)
        try:
            self.step('copying_files_before_dump')
            copy_new_files(source, stage / 'files')
            self.step('online_database_dump')
            raw = stage / 'database.sql'
            self.dump(raw)
            with raw.open('rb') as plain, gzip.open(stage / 'database.sql.gz', 'wb') as target:
                shutil.copyfileobj(plain, target, 1024 * 1024)
            raw.unlink()
            self.step('copying_files_after_dump')
            copy_new_files(source, stage / 'files')
            shutil.copy2(env, stage / 'school-config.env')
            self.step('restore_drill_in_isolated_database')
            password = self.start_verify_db(config)
            self.load_dump(stage / 'database.sql.gz', password)
            self.step('reconciliation_from_restored_dump')
            receipt = json.loads(self.app_on_verify_db(config, password, 'app.installation', 'verify'))
            provenance = validate_installation_receipt(self.root, receipt)
            snapshot = json.loads(self.app_on_verify_db(config, password, 'app.database_snapshot'))
            if not isinstance(snapshot, dict) or not snapshot.get('snapshot_sha256') or not isinstance(snapshot.get('tables'), dict):
                raise ControlError('database reconciliation receipt invalid')
            write_json(stage / 'installation-provenance.json', provenance)
            write_json(stage / 'database-reconciliation.json', snapshot)
            write_json(stage / 'backup-metadata.json', {
                'operation': 'online-backup', 'time': datetime.now(timezone.utc).isoformat(), 'source_database': DB_NAME,
                'mode': 'online-consistent-snapshot', 'restore_drill': 'dump loaded into isolated MySQL and row digests taken there',
                'contains_secrets': 'school-config.env is private', 'restore_policy': 'empty school instance only'})
            for directory, dirs, files in os.walk(stage):
                os.chmod(directory, 0o700)
                for name in files:
                    os.chmod(Path(directory) / name, 0o600)
            self.step('backup_manifest_verification')
            result = create_manifest(stage)
            verify_manifest(stage)
            sync_backup_tree(stage)
            dest = base / stamp
            os.rename(stage, dest)
            fsync_dir(base)
            write_json(base / (stamp + '.receipt.json'), {'backup': stamp, **result, 'status': 'HASH_VERIFIED_RESTORE_DRILLED'})
            return {'status': 'BACKUP_HASH_VERIFIED', 'backup': str(dest), 'mode': 'online', 'services_stopped': False,
                    'restore_drill': 'PASS', 'tables': len(snapshot['tables']),
                    'rows': sum(t['rows'] for t in snapshot['tables'].values())}
        except BaseException:
            shutil.rmtree(stage, ignore_errors=True)
            raise
        finally:
            self.remove_verify_db()


def alert(root, stage, message):
    logdir = safe_directory(Path(root) / 'runtime/logs', 0o700)
    write_json(logdir / 'ALERT-backup-failed', {'time': datetime.now(timezone.utc).isoformat(), 'stage': stage,
               'message': message, 'services': 'not stopped; the system kept running',
               'action': 'check runtime/logs/deploy-diagnostics.log, fix, then run scripts/online_backup.py again'})


def main(root=None, runner=None):
    if os.name == 'posix' and os.geteuid() != 0:
        print('BLOCKED: run as the deployment administrator (root).')
        return 2
    root = Path(root or Path(__file__).resolve().parents[1])
    backup = OnlineBackup(root, runner)
    # Share the deployment lock so an upgrade or restore never runs at the same time; never write the active marker.
    lock = os.open(root / 'runtime/maintenance.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(json.dumps({'status': 'SKIPPED', 'reason': 'another maintenance operation is running'}))
            return 0
        try:
            result = backup.create()
        except (ControlError, ValueError, OSError) as exc:
            error = exc if getattr(exc, 'diagnostic_id', None) else diagnostic_error(root, backup.stage, [], None, str(exc), 'online backup failed')
            alert(root, backup.stage, f'online backup failed; diagnostic id={getattr(error, "diagnostic_id", "")}')
            print(json.dumps({'status': 'FAILED', 'stage': backup.stage, 'diagnostic_id': getattr(error, 'diagnostic_id', ''),
                              'services_stopped': False}))
            return 1
        stale = root / 'runtime/logs/ALERT-backup-failed'
        if stale.exists():
            stale.unlink()
        print(json.dumps(result, ensure_ascii=False))
        return 0
    finally:
        os.close(lock)


if __name__ == '__main__':
    raise SystemExit(main())
