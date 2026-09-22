"""Dependency checks / test helpers only; not a Docker/MySQL execution."""
import io,json,os,sys
from pathlib import Path
import pytest
from run_mysql_acceptance import preconditions,main,clean_owned_projects,copy_clean_source
from school_http_acceptance import workbook,HEADERS,Client,PNG,AcceptanceFailure
from deploy_control import Pipeline,ControlError
ROOT=Path(__file__).resolve().parents[2]

def test_missing_docker_fails_closed_without_any_command(monkeypatch,tmp_path):
    import run_mysql_acceptance as mod
    monkeypatch.setattr(mod.shutil,'which',lambda name:None if name=='docker' else '/usr/bin/openssl')
    class Forbidden:
        def run(self,*a,**kw):raise AssertionError('must not start commands')
    monkeypatch.setattr(mod,'Runner',Forbidden)
    code=main(['--run-isolated','--api-image','local/api:r7','--frontend-image','local/front:r7','--mysql-image','mysql:8.4','--output',str(tmp_path)])
    r=json.loads((tmp_path/'mysql_acceptance.json').read_text())
    assert code==2 and r['status']=='BLOCKED' and r['mysql_tested'] is False
    assert r['fallback_engine_used'] is False and r['restore_executed'] is False
    with pytest.raises(SystemExit):main(['--run-isolated','--output',str(tmp_path)])

def test_no_explicit_run_flag_cannot_execute(tmp_path):
    with pytest.raises(SystemExit):main(['--output',str(tmp_path)])

@pytest.mark.parametrize('url',['http://127.0.0.1','https://school.example.test','https://localhost','https://127.0.0.1@example.com','https://127.0.0.1/path','https://127.0.0.1?x=1'])
def test_business_driver_never_targets_remote_or_insecure_endpoint(url):
    with pytest.raises(AcceptanceFailure):Client(url,'nonexistent-ca',[],'fixture')

def test_generated_excel_bytes_parse_in_actual_application():
    from app.excel_io import inspect_xlsx
    row=['r7-one','r7teacher','2026-06-01','P','项目','C','课程','B','班级',10,5,'100.00','Excel导入']
    data=workbook([HEADERS,row]);result=inspect_xlsx(data,'acceptance.xlsx','records',max_rows=100)
    assert len(result)==1

def test_fixture_png_is_valid_not_a_disabled_file_check():
    from PIL import Image
    with Image.open(io.BytesIO(PNG)) as im:im.verify()

def test_clean_copy_excludes_live_configuration_and_database(tmp_path):
    source=tmp_path/'original';dest=tmp_path/'copy'
    for name in ('backend','frontend','scripts','deploy'): (source/name).mkdir(parents=True)
    (source/'backend/real.py').write_text('CODE')
    for name in ('deploy/.env','deploy/secrets/root.cnf','deploy/tls/key.pem','runtime/live.sqlite'):
        p=source/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('PRIVATE')
    copy_clean_source(source,dest)
    assert (dest/'backend/real.py').read_text()=='CODE'
    assert not (dest/'deploy/.env').exists() and not (dest/'deploy/secrets').exists() and not (dest/'runtime').exists()

def test_cleanup_will_not_touch_another_existing_directory(tmp_path):
    base=tmp_path/'own-lab';base.mkdir();outside=tmp_path/'other-school';outside.mkdir()
    class NoCommands:
        def run(self,*a,**k):raise AssertionError('must not execute unowned commands')
    with pytest.raises(ControlError,match='UNOWNED'):clean_owned_projects(base,[Pipeline(outside,NoCommands())])

def test_no_password_module_excluded_from_image_context():
    # Docker basename globs match passwords.py too; blanket '*password*' is unsafe.
    import fnmatch
    globs=[x.strip() for x in (ROOT/'.dockerignore').read_text().splitlines() if x.strip() and not x.startswith('#')]
    assert not any(fnmatch.fnmatch('passwords.py',x) or fnmatch.fnmatch('backend/app/passwords.py',x) for x in globs)
