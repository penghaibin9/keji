"""Online backup never stops services or writes the maintenance marker; failures only alert."""
import gzip
import json
import os
import sys
from pathlib import Path
import pytest

pytestmark = pytest.mark.skipif(os.name != 'posix', reason='deployment scripts use POSIX file locking')
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))

SNAPSHOT = {'algorithm': 'x', 'snapshot_sha256': 'abc', 'tables': {'users': {'rows': 2, 'sha256': 'd', 'columns': ['id']}}}


class FakeRunner:
    def __init__(self, fail_on=None):
        self.commands = []
        self.fail_on = fail_on

    def run(self, command, *, output=None, input_stream=None, timeout=180, root=None, stage=None, **kw):
        from deploy_control import ControlError
        text = ' '.join(command)
        self.commands.append(text)
        if self.fail_on and self.fail_on in text:
            raise ControlError('simulated failure')
        if 'mysqldump' in text:
            output.write(b'CREATE TABLE users (id int);\nINSERT INTO users VALUES (1),(2);\n')
        if 'app.installation' in text:
            return json.dumps({'installation_id': 'i'}).encode()
        if 'app.database_snapshot' in text:
            return json.dumps(SNAPSHOT).encode()
        return b''


def school(tmp_path):
    (tmp_path / 'deploy').mkdir()
    (tmp_path / 'deploy/.env').write_text('ND_API_IMAGE=yueke/nondegree-api:t\nND_MYSQL_IMAGE=yueke/nondegree-mysql:t\n')
    (tmp_path / 'runtime/files').mkdir(parents=True)
    (tmp_path / 'runtime/files/abc').write_bytes(b'attachment')
    (tmp_path / 'runtime/maintenance').mkdir()
    return tmp_path


def test_backup_keeps_services_running_and_matches_restore_layout(tmp_path, monkeypatch):
    import online_backup
    monkeypatch.setattr(online_backup, 'validate_installation_receipt', lambda root, value: value)
    root, runner = school(tmp_path), FakeRunner()
    assert online_backup.main(root, runner) == 0
    joined = '\n'.join(runner.commands)
    assert ' stop ' not in joined and ' up ' not in joined, 'business services must not be stopped or restarted'
    assert not (root / 'runtime/maintenance/active').exists()
    [backup] = [p for p in (root / 'runtime/backups').iterdir() if p.is_dir()]
    names = {p.name for p in backup.iterdir()}
    assert {'database.sql.gz', 'database-reconciliation.json', 'installation-provenance.json', 'manifest.json', 'files', 'school-config.env'} <= names
    assert gzip.open(backup / 'database.sql.gz').read().startswith(b'CREATE TABLE')
    assert json.loads((backup / 'database-reconciliation.json').read_text()) == SNAPSHOT
    assert json.loads((backup / 'backup-metadata.json').read_text())['mode'] == 'online-consistent-snapshot'
    assert (backup / 'files/abc').read_bytes() == b'attachment'
    from backup_manifest import verify
    verify(backup)
    assert '--single-transaction' in joined and 'network create --internal' in joined
    assert 'rm -f -v nd-backup-verify-db-' in joined, 'isolated verification database is always removed'


def test_failure_only_alerts_and_leaves_no_partial_backup(tmp_path, monkeypatch):
    import online_backup
    monkeypatch.setattr(online_backup, 'validate_installation_receipt', lambda root, value: value)
    root, runner = school(tmp_path), FakeRunner(fail_on='app.database_snapshot')
    assert online_backup.main(root, runner) == 1
    alert = json.loads((root / 'runtime/logs/ALERT-backup-failed').read_text())
    assert alert['stage'] == 'reconciliation_from_restored_dump' and 'not stopped' in alert['services']
    assert not (root / 'runtime/maintenance/active').exists()
    assert not [p for p in (root / 'runtime/backups').iterdir()], 'failed backup leaves nothing behind'
    assert any('rm -f -v' in c for c in runner.commands)
