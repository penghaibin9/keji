"""Local fault injection only; Windows shims do not prove Linux permissions/locks."""
from datetime import datetime,timezone
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from types import ModuleType,SimpleNamespace
import pytest
import prune_backups

ROOT=Path(__file__).resolve().parents[2]


@pytest.fixture
def control(monkeypatch):
    with monkeypatch.context() as imports:
        if os.name=='nt':imports.setitem(sys.modules,'fcntl',ModuleType('fcntl'))
        spec=importlib.util.spec_from_file_location('codex_deploy_diag_control',ROOT/'scripts/deploy_control.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.checked_modes=[];module.checked_flags=[]
    if os.name=='nt':
        # Only diagnostic syscalls are simulated; no maintenance lock is acquired.
        proxy=SimpleNamespace(**vars(os));proxy.O_NOFOLLOW=1<<28;proxy.O_NONBLOCK=1<<29
        def open_log(path,flags,mode):
            module.checked_flags.append(flags)
            if Path(path).is_symlink():raise OSError('link refused by simulated O_NOFOLLOW')
            return os.open(path,flags&~(proxy.O_NOFOLLOW|proxy.O_NONBLOCK),mode)
        proxy.open=open_log;proxy.geteuid=lambda:0
        proxy.fchmod=lambda fd,mode:module.checked_modes.append(mode)
        module.os=proxy
    return module


def mark(control,pipeline,monkeypatch,stage='schema_migration'):
    owner=control.Maintenance(pipeline,'upgrade');owner.owned=True;owner.fd=1
    owner.directory.mkdir(parents=True,exist_ok=True)
    monkeypatch.setattr(control,'write_json',lambda path,data,mode:path.write_text(json.dumps(data),encoding='utf-8'))
    owner.mark(stage)
    assert json.loads(owner.active.read_text())['stage']==stage


def read_log(root):
    return [json.loads(line) for line in (root/'runtime/logs/deploy-diagnostics.log').read_text(encoding='utf-8').splitlines()]


def test_command_failure_appends_private_redacted_diagnostics(control,tmp_path,monkeypatch):
    pipeline=control.Pipeline(tmp_path);mark(control,pipeline,monkeypatch)
    password='FakeDbPass!';connection='mysql+pymysql://school:'+password+'@db/nondegree'
    token='aB7xQ9zK2mP4nR6sT8uV0wY3cD5eF1gH';quoted='Fake quoted password!'
    stderr='\n'.join('line '+str(i) for i in range(45))
    stderr+='\n'+connection+'\npassword=FakeShortPass!\n{"password": "'+quoted+'"}\nBearer '+token+'\nerror: missing table'
    monkeypatch.setattr(control.subprocess,'run',lambda *a,**kw:subprocess.CompletedProcess(a[0],17,b'PRIVATE_STDOUT',stderr.encode()))
    errors=[]
    for _ in range(2):
        with pytest.raises(control.ControlError) as caught:
            pipeline.dc('run','--rm','--pull','never','migrate','alembic','upgrade','head',
                        input_bytes=b'PRIVATE_SQL',extra_env={'PRIVATE_VALUE':'PRIVATE_ENV'})
        errors.append(caught.value)
    path=tmp_path/'runtime/logs/deploy-diagnostics.log';raw=path.read_text(encoding='utf-8');records=read_log(tmp_path)
    assert len(records)==2 and records[0]['id']!=records[1]['id']
    for row,error in zip(records,errors):
        assert re.fullmatch('[0-9a-f]{8}',row['id']) and row['id'] in str(error)
        assert error.diagnostic_written and error.stage==row['stage']=='schema_migration'
        assert datetime.fromisoformat(row['time']).utcoffset()==timezone.utc.utcoffset(None)
        assert row['command']=='docker compose run migrate alembic upgrade head' and row['returncode']==17
        assert len(row['stderr'].splitlines())==40 and row['stderr'].endswith('error: missing table')
        assert 'line 0\n' not in row['stderr'] and '***' in row['stderr']
    assert all(secret not in raw for secret in (password,connection,token,quoted,'FakeShortPass!','PRIVATE_STDOUT','PRIVATE_SQL','PRIVATE_ENV',str(tmp_path)))
    if os.name=='nt':
        assert control.checked_modes==[0o600,0o600]
        assert all(flags&control.os.O_NOFOLLOW for flags in control.checked_flags)
    else:
        assert stat.S_IMODE(path.stat().st_mode)==0o600
        assert stat.S_IMODE(path.parent.stat().st_mode)==0o700


@pytest.mark.parametrize('options',[
    ['--env-file','head','-f','api'],['--env-file=head','-fapi'],
    ['--defaults-extra-file','worker','-e','upgrade'],['--defaults-extra-file=worker','-eupgrade'],
    ['--password','frontend','--secret','db','--token','mysql'],
    ['password=Fake!','mysql+pymysql://school:Fake!@db/nondegree','UnknownPositionalSecret'],
    ['-c','print(secret)'],
])
def test_command_summary_excludes_sensitive_arguments(control,options):
    assert control.command_summary(['docker','compose',*options,'exec','db','mysql'])=='docker compose exec db mysql'


@pytest.mark.parametrize('fault',[
    subprocess.TimeoutExpired(['docker'],1,stderr=b'password=TimeoutFake!\ntimed out'),
    OSError('password=LaunchFake! unavailable'),
])
def test_launch_failure_and_timeout_are_diagnosed(control,tmp_path,monkeypatch,fault):
    def fail(*a,**kw):raise fault
    monkeypatch.setattr(control.subprocess,'run',fail)
    with pytest.raises(control.ControlError,match='diagnostic id='):
        control.Runner().run(['docker','version'],root=tmp_path)
    row=read_log(tmp_path)[0]
    assert row['returncode'] is None and row['stage']=='unknown'
    assert 'Fake!' not in row['stderr'] and '***' in row['stderr']


def test_success_creates_no_diagnostic(control,tmp_path,monkeypatch):
    monkeypatch.setattr(control.subprocess,'run',lambda *a,**kw:subprocess.CompletedProcess(a[0],0,b'OK',b''))
    assert control.Runner().run(['docker','version'],root=tmp_path)==b'OK'
    assert not (tmp_path/'runtime').exists()


def test_log_write_failure_preserves_command_error(control,tmp_path,monkeypatch):
    def fail(*a,**kw):raise OSError('simulated full disk')
    monkeypatch.setattr(control,'safe_directory',fail)
    monkeypatch.setattr(control.subprocess,'run',lambda *a,**kw:subprocess.CompletedProcess(a[0],9,b'',b'password=DoNotLeak!'))
    with pytest.raises(control.ControlError,match='command failed;.*diagnostic id=') as caught:
        control.Runner().run(['docker','compose','up'],root=tmp_path)
    assert not caught.value.diagnostic_written and 'DoNotLeak!' not in str(caught.value)


def test_hardlinked_diagnostic_file_is_not_modified(control,tmp_path):
    outside=tmp_path/'preserve';outside.write_text('preserve')
    logdir=tmp_path/'runtime/logs';logdir.mkdir(parents=True)
    os.link(outside,logdir/'deploy-diagnostics.log')
    error=control.diagnostic_error(tmp_path,None,['docker'],1,b'failure','command failed')
    assert not error.diagnostic_written and outside.read_text()=='preserve'


@pytest.mark.parametrize('failure',['command','validation','log_unavailable'])
def test_main_reports_original_stage_log_and_id(control,tmp_path,monkeypatch,capsys,failure):
    pipeline=control.Pipeline(tmp_path);mark(control,pipeline,monkeypatch)
    def run_backup():
        if failure=='validation':raise ValueError('invalid input password=FakeValidation!')
        try:pipeline.dc('run','migrate','alembic','upgrade','head')
        finally:pipeline.stage='FAILED_AT_schema_migration'
    pipeline.run_backup=run_backup
    monkeypatch.setattr(control,'Pipeline',lambda root:pipeline)
    monkeypatch.setattr(control.os,'geteuid',lambda:0)
    monkeypatch.setattr(control.subprocess,'run',lambda *a,**kw:subprocess.CompletedProcess(a[0],1,b'',b'password=FakeCommand!'))
    if failure=='log_unavailable':
        def fail(*a,**kw):raise OSError('full disk')
        monkeypatch.setattr(control,'safe_directory',fail)
    monkeypatch.setattr(sys,'argv',['deploy_control.py','backup','--allow-maintenance-window'])
    with pytest.raises(SystemExit) as caught:control.main()
    output=capsys.readouterr();assert caught.value.code==2 and not output.out
    assert 'BLOCKED: operation failed at stage schema_migration; see runtime/logs/deploy-diagnostics.log id=' in output.err
    assert 'Fake' not in output.err and 'FAILED_AT_' not in output.err
    if failure=='log_unavailable':assert 'diagnostic log unavailable' in output.err
    else:
        row=read_log(tmp_path)[0];assert row['id'] in output.err and 'Fake' not in row['stderr']


def backup(root,day):
    path=root/'runtime/backups'/f'202610{day:02d}T010203Z-{day:08x}'
    path.mkdir(parents=True);(path/'database.sql.gz').write_bytes(b'synthetic backup')
    path.with_name(path.name+'.receipt.json').write_text('{}')
    return path


@pytest.mark.parametrize('dry_run',[False,True])
def test_prune_keeps_latest_and_skips_unrelated_entries(tmp_path,dry_run):
    backups=[backup(tmp_path,day) for day in (3,1,2)];base=tmp_path/'runtime/backups'
    partial=base/'.partial-20261001T010203Z-00000001-extra';partial.mkdir();(partial/'keep').write_text('keep')
    other=base/'manual-backup';other.mkdir();(other/'keep').write_text('keep')
    unrelated=base/'20261000T010203Z-00000000';unrelated.write_text('not a directory')
    orphan=base/'20260901T010203Z-00000001.receipt.json';orphan.write_text('orphan')
    result=prune_backups.prune(tmp_path,keep=2,dry_run=dry_run)
    assert result['kept']==sorted([backups[0].name,backups[2].name])
    assert result['would_delete' if dry_run else 'deleted']==[backups[1].name]
    assert result['deleted' if dry_run else 'would_delete']==[]
    assert backups[1].exists()==dry_run and backups[1].with_name(backups[1].name+'.receipt.json').exists()==dry_run
    assert (partial/'keep').read_text()=='keep' and (other/'keep').read_text()=='keep'
    assert unrelated.read_text()=='not a directory' and orphan.read_text()=='orphan'


@pytest.mark.parametrize('kind',['directory','receipt','nested','ancestor'])
def test_prune_never_touches_links(tmp_path,monkeypatch,kind):
    old=backup(tmp_path,1);new=backup(tmp_path,2)
    path={'directory':old,'receipt':old.with_name(old.name+'.receipt.json'),
          'nested':old/'database.sql.gz','ancestor':tmp_path/'runtime'}[kind]
    original=Path.lstat;info=original(path)
    def linked(candidate,*a,**kw):
        if candidate==path:return SimpleNamespace(st_mode=stat.S_IFLNK|0o777,st_nlink=info.st_nlink,st_file_attributes=0)
        return original(candidate,*a,**kw)
    monkeypatch.setattr(Path,'lstat',linked)
    if kind=='ancestor':
        with pytest.raises(ValueError,match='unsafe'):prune_backups.prune(tmp_path,keep=1)
    else:
        result=prune_backups.prune(tmp_path,keep=1)
        assert result['deleted']==[] and result['kept']==[new.name]
    assert (old/'database.sql.gz').read_bytes()==b'synthetic backup' and new.is_dir()


def test_prune_actual_directory_link_leaves_target_untouched(tmp_path):
    outside=tmp_path/'outside';outside.mkdir();(outside/'keep').write_text('preserve')
    new=backup(tmp_path,2);link=new.with_name('20261001T010203Z-00000001')
    try:link.symlink_to(outside,target_is_directory=True)
    except OSError as exc:
        if getattr(exc,'winerror',None)!=1314:raise
        pytest.skip('OS does not permit test symlinks: 1314')
    result=prune_backups.prune(tmp_path,keep=1)
    assert result['deleted']==[] and link.is_symlink() and (outside/'keep').read_text()=='preserve'


def test_prune_cli_default_dry_run_and_invalid_keep(tmp_path,monkeypatch,capsys):
    backups=[backup(tmp_path,day) for day in range(1,10)]
    monkeypatch.setattr(prune_backups,'ROOT',tmp_path)
    assert prune_backups.main(['--dry-run'])==0
    result=json.loads(capsys.readouterr().out)
    assert result['keep']==7 and result['would_delete']==[p.name for p in backups[:2]] and result['deleted']==[]
    assert all(p.exists() for p in backups)
    for keep in (0,-1):
        with pytest.raises(SystemExit) as caught:prune_backups.main(['--keep',str(keep)])
        assert caught.value.code==2
        with pytest.raises(ValueError):prune_backups.prune(tmp_path,keep=keep)


def test_prune_missing_directory_is_noop(tmp_path):
    assert prune_backups.prune(tmp_path,dry_run=True)['deleted']==[]
    assert not (tmp_path/'runtime').exists()


def test_prune_unreadable_tree_aborts_before_deleting(tmp_path,monkeypatch):
    old=backup(tmp_path,1);new=backup(tmp_path,2)
    def walk(path,*,followlinks,onerror):onerror(PermissionError('cannot inspect backup'))
    monkeypatch.setattr(prune_backups.os,'walk',walk)
    with pytest.raises(PermissionError):prune_backups.prune(tmp_path,keep=1)
    assert old.is_dir() and new.is_dir()


def test_prune_hardlinked_receipt_preserves_backup_and_other_file(tmp_path):
    base=tmp_path/'runtime/backups';old=base/'20261001T010203Z-00000001';old.mkdir(parents=True)
    outside=tmp_path/'preserve';outside.write_text('preserve')
    os.link(outside,old.with_name(old.name+'.receipt.json'));new=backup(tmp_path,2)
    result=prune_backups.prune(tmp_path,keep=1)
    assert result['deleted']==[] and old.is_dir() and new.is_dir() and outside.read_text()=='preserve'
