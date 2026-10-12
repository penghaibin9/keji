"""The delivery manifest must include new code without publishing private state."""
import json
from pathlib import Path
import refresh_launcher_manifest as manifest


def test_school_manifest_excludes_demo_entries_without_removing_source(tmp_path):
    for name in ('README_START_HERE.md', '开始部署.sh', '先读我_部署与演示.html'):
        (tmp_path/name).write_text('fixture')
    assert set(manifest.program_names(tmp_path))=={'README_START_HERE.md','开始部署.sh','先读我_部署与演示.html'}
    assert manifest.program_names(tmp_path,school_package=True)==['README_START_HERE.md']
    assert (tmp_path/'开始部署.sh').is_file() and (tmp_path/'先读我_部署与演示.html').is_file()


def test_school_program_manifest_uses_the_same_private_file_filter(tmp_path):
    for name in ('tests/fixtures/test-accounts.txt','frontend/assets/screenshot.png','backend/app/main.py'):
        path=tmp_path/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('fixture')
    assert manifest.program_names(tmp_path,school_package=True)==['backend/app/main.py']


def test_actual_program_files_and_untracked_migrations_are_included(tmp_path):
    for name in ('backend/alembic/versions/new.py', 'backend/auth_session_schema.json',
                 'frontend/social-training.js', 'scripts/new.py', 'tests/new.py',
                 'deploy/.env.example', 'pytest.ini'):
        p=tmp_path/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('fixture')
    for name in ('deploy/.env', 'deploy/secrets/runtime_url', 'backend/data.sqlite',
                 'frontend/node_modules/private.js', 'backend/__pycache__/cache.pyc',
                 'backend/.venv/private.py', 'frontend/uploads/private.png',
                 'backend/.keji-closeout-backup-old/model.py', 'docs/report.md'):
        p=tmp_path/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('private fixture')
    names=manifest.program_names(tmp_path)
    assert names==sorted(['backend/alembic/versions/new.py','backend/auth_session_schema.json',
                         'frontend/social-training.js','scripts/new.py','tests/new.py',
                         'deploy/.env.example','pytest.ini'])


def test_refresh_is_reproducible_without_git_and_updates_consumers(tmp_path,monkeypatch):
    (tmp_path/'backend').mkdir();(tmp_path/'backend/new.py').write_text('print(1)')
    out=tmp_path/'delivery/R11_BASE_MANIFEST.json';out.parent.mkdir()
    out.write_text(json.dumps({'input_zip_sha256':'old','files':{}}))
    consumers=('delivery/manage.py','delivery/tests/test_deploy_guards.py')
    for name in consumers:
        p=tmp_path/name;p.parent.mkdir(exist_ok=True);p.write_text("baseline='old'")
    monkeypatch.setattr(manifest,'ROOT',tmp_path);monkeypatch.setattr(manifest,'OUT',out)
    manifest.main();first=out.read_bytes();data=json.loads(first)
    assert data['files']=={'backend/new.py':manifest.hashlib.sha256(b'print(1)').hexdigest()}
    assert all(data['input_zip_sha256'] in (tmp_path/name).read_text() for name in consumers)
    assert 'delivery/R11_BASE_MANIFEST.json' not in data['files']
    manifest.main();assert out.read_bytes()==first
