import copy,datetime as dt,json,os,socket
from pathlib import Path
import pytest
from delivery import manage
from delivery.common import Blocked,digest,secure_json,load_private,verify_baseline
ROOT=Path(__file__).resolve().parents[2]

def fake_docker():return {'server_version':'28.3.0','compose_version':'2.39.0','context':'default','endpoint':'unix:///var/run/docker.sock'},[]

@pytest.mark.parametrize('port',[0,22,1023,65536,-1,True,'18443'])
def test_unsafe_port_values(port):assert not manage.port_available(port)

def test_in_use_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1',0));s.listen();assert not manage.port_available(s.getsockname()[1])

def test_plan_no_target_creation(tmp_path,monkeypatch):
    monkeypatch.setattr(manage,'local_docker',fake_docker)
    monkeypatch.setattr(manage,'probe',lambda args: 'existing service: keep unchanged')
    target=tmp_path/'new-only';out=tmp_path/'plan.json'
    result=manage.make_plan(str(target),18443,out)
    assert not target.exists() and not result['proposal']['server_modified']
    assert result['proposal']['bind_ip']=='127.0.0.1'
    with pytest.raises(FileExistsError):manage.make_plan(str(target),18443,out)

@pytest.mark.parametrize('mutation',['approval','expiry','host','target','blocker'])
def test_changed_plan_rejected(tmp_path,monkeypatch,mutation):
    monkeypatch.setattr(manage,'local_docker',fake_docker);monkeypatch.setattr(manage,'probe',lambda args:'')
    out=tmp_path/'plan.json';manage.make_plan(str(tmp_path/'new'),18443,out);p=load_private(out)
    approval=p['approval_id']
    if mutation=='approval':approval='wrong'
    elif mutation=='expiry':p['expires_at']='2020-01-01T00:00:00+00:00'
    elif mutation=='host':p['host_id']='different host'
    elif mutation=='target':p['proposal']['target']=str(tmp_path/'other')
    else:p['proposal']['blockers']=['blocked']
    with pytest.raises(Blocked):manage.validate_plan(p,approval)

def test_nonempty_target_never_accepted(tmp_path,monkeypatch):
    monkeypatch.setattr(manage,'local_docker',fake_docker);monkeypatch.setattr(manage,'probe',lambda args:'')
    target=tmp_path/'exists';target.mkdir();(target/'business.txt').write_text('unchanged')
    p=manage.inspect_host(str(target),18443)
    assert 'TARGET_ALREADY_EXISTS_NEVER_OVERWRITE' in p['blockers'];assert (target/'business.txt').read_text()=='unchanged'

def test_symlink_target_rejected(tmp_path):
    target=tmp_path/'symlink';target.symlink_to(tmp_path,target_is_directory=True)
    with pytest.raises(Blocked):manage.inspect_host(str(target),18443)

def test_secret_file_mode_required(tmp_path):
    p=tmp_path/'secret.json';p.write_text('{}');p.chmod(0o644)
    with pytest.raises(Blocked):load_private(p)
    p.chmod(0o600);assert load_private(p)=={}

def test_original_r11_unchanged():assert verify_baseline(ROOT)=='fe432df0c3edb39e8ff0078f13453e9be885b639556785a6174532c8eafe758b'

def test_real_tls_and_file_config_prepare_only(tmp_path,monkeypatch):
    # File/TLS test: mock only inventory; never claim Docker or MySQL was executed.
    monkeypatch.setattr(manage,'local_docker',fake_docker);monkeypatch.setattr(manage,'probe',lambda args:'')
    original_inspect=manage.inspect_host
    def adequate_inventory(target,port):
        report=original_inspect(target,port)
        report['blockers']=[x for x in report['blockers'] if x not in ('AVAILABLE_MEMORY_BELOW_5_GIB','FREE_DISK_BELOW_8_GIB')]
        return report
    monkeypatch.setattr(manage,'inspect_host',adequate_inventory)
    target=tmp_path/'isolated';out=tmp_path/'plan.json'
    plan=manage.make_plan(str(target),18443,out)
    assert plan['status']=='AWAITING_USER_CONFIRMATION', plan
    result=manage.prepare(out,plan['approval_id']);assert result['status']=='PREPARED_NOT_STARTED'
    cfg=(target/'deploy/.env').read_text()
    assert 'ND_BIND_IP=127.0.0.1' in cfg and 'ND_ENV=production' in cfg and 'ND_SEED_ENABLED=false' in cfg and 'ND_ADAPTER_MODULES=\n' in cfg
    assert 'runtime' not in [p.name for p in (target/'delivery-state').iterdir()]
    assert verify_baseline(target)
    assert (target/'deploy/secrets/runtime_url').read_text() not in json.dumps(result)
    with pytest.raises(Blocked):manage.prepare(out,plan['approval_id'])

def test_build_context_is_whitelist_no_secrets():
    s=(ROOT/'delivery/manage.py').read_text()
    assert "names=json.loads((target/'delivery/R11_BASE_MANIFEST.json').read_text())['files']" in s
    assert "name=='scripts/check_assembly.py'" in s
    assert "prefix='.build-context-'" in s
    assert 'docker system prune' not in s and 'iptables' not in s

def test_remote_docker_override_refused(monkeypatch):
    monkeypatch.setenv('DOCKER_HOST','tcp://remote.example.invalid:2376')
    with pytest.raises(Blocked):manage.pipeline(ROOT)

def test_restricted_override_only_caps_resources():
    import yaml
    raw=yaml.safe_load((ROOT/'delivery/compose.restricted.yml').read_text())
    assert set(raw)=={'services'}
    assert set(raw['services'])=={'db','api','worker','frontend'}
    for options in raw['services'].values():
        assert set(options)=={'mem_limit','cpus'}
        assert options['cpus']>0
