"""Real TLS/filesystem/Unix-UID checks; no Docker/MySQL success is simulated."""
from pathlib import Path
import json,os,shutil,stat,subprocess,sys,tempfile
import pytest
from deployment_config import (prepare,verify_private_bundle,origin_parts,initial_sql,
    validate_tls,ConfigurationRejected,APP_UID,DB_UID,SECRET_NAMES)

@pytest.fixture(scope='module')
def tls_pair(tmp_path_factory):
    p=tmp_path_factory.mktemp('r7-tls');cert=p/'cert.pem';key=p/'key.pem'
    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-sha256','-nodes','-days','3',
        '-keyout',str(key),'-out',str(cert),'-subj','/CN=school.example.test',
        '-addext','subjectAltName=DNS:school.example.test,IP:127.0.0.1'],check=True,capture_output=True)
    return cert,key

@pytest.fixture
def source(tmp_path):
    root=tmp_path/'school';(root/'deploy').mkdir(parents=True);(root/'deploy/compose.yml').write_text('services: {}\n')
    return root


def args(root,tls):
    return dict(root=root,school_name='隔离验收学校',origin='https://school.example.test',
        api_image='local/api:r7',frontend_image='local/front:r7',mysql_image='mysql:8.4',
        certificate=tls[0],private_key=tls[1])


def test_prepare_separated_secret_ownership_and_no_secret_output(source,tls_pair):
    report=prepare(**args(source,tls_pair));assert report['status']=='PRIVATE_CONFIGURATION_VERIFIED'
    assert not report['database_contacted'] and not report['service_started']
    assert report['tls']['key_pair_checked'] and not report['tls']['trust_chain_verified']
    content=json.dumps(report)
    for name in SECRET_NAMES:
        p=source/'deploy/secrets'/name;assert stat.S_IMODE(p.stat().st_mode)==0o400
        assert p.stat().st_uid==(APP_UID if name in ('runtime_url','migration_url','admin_password') else DB_UID)
        assert p.read_text().strip() not in content
    assert verify_private_bundle(source)['separated_accounts']

@pytest.mark.parametrize('name',['.env','secrets','tls','.prepare-incomplete'])
def test_existing_configuration_never_overwritten(source,tls_pair,name):
    p=source/'deploy'/name;p.write_text('original')
    with pytest.raises(ConfigurationRejected,match='EXISTING_CONFIGURATION'):prepare(**args(source,tls_pair))
    assert p.read_text()=='original'

@pytest.mark.parametrize('origin',['http://school.example.test','https://user:pw@school.example.test',
    'https://school.example.test/path','https://school.example.test/?q=1','https://a:99999','https://a\nND_ENV=test',
    'https://$(id)','https://a:word','https://a..b'])
def test_bad_origin_rejected(origin):
    with pytest.raises(ConfigurationRejected):origin_parts(origin)

@pytest.mark.parametrize('school',['','名字\nND_ENV=test',"a'b",'${SCHOOL}','x'*121])
def test_school_name_cannot_inject_environment(source,tls_pair,school):
    a=args(source,tls_pair);a['school_name']=school
    with pytest.raises(ConfigurationRejected):prepare(**a)
    assert not (source/'deploy/.env').exists()


def test_wrong_certificate_hostname_refused_before_any_write(source,tls_pair):
    a=args(source,tls_pair);a['origin']='https://wrong.example.test'
    with pytest.raises(ConfigurationRejected):prepare(**a)
    assert not (source/'deploy/.prepare-incomplete').exists()


def test_wrong_key_refused(source,tls_pair,tmp_path):
    wrong=tmp_path/'wrong.key';subprocess.run(['openssl','genpkey','-algorithm','RSA','-pkeyopt','rsa_keygen_bits:2048','-out',str(wrong)],check=True,capture_output=True)
    a=args(source,tls_pair);a['private_key']=wrong
    with pytest.raises(ConfigurationRejected,match='TLS_KEY'):prepare(**a)


def test_private_key_link_refused(source,tls_pair,tmp_path):
    link=tmp_path/'link.key';link.symlink_to(tls_pair[1]);a=args(source,tls_pair);a['private_key']=link
    with pytest.raises((OSError,ConfigurationRejected)):prepare(**a)
    assert not (source/'deploy/.env').exists()

@pytest.mark.parametrize('corrupt',['runtime_is_migration','reused_password','world_readable','wrong_uid','init_sql','incomplete'])
def test_preflight_fails_closed_on_bad_bundle(source,tls_pair,corrupt):
    prepare(**args(source,tls_pair));d=source/'deploy/secrets'
    if corrupt=='runtime_is_migration':(d/'runtime_url').write_bytes((d/'migration_url').read_bytes())
    if corrupt=='reused_password':(d/'admin_password').write_bytes((d/'db_root_password').read_bytes())
    if corrupt=='world_readable':(d/'runtime_url').chmod(0o444)
    if corrupt=='wrong_uid':os.chown(d/'runtime_url',0,0)
    if corrupt=='init_sql':(d/'db-init.sql').write_text("GRANT ALL ON *.* TO 'nondegree_app'@'%';")
    if corrupt=='incomplete':(source/'deploy/.prepare-incomplete').write_text('{}')
    with pytest.raises(ConfigurationRejected):verify_private_bundle(source)


def test_generated_initial_migration_privilege_is_not_runtime_privilege():
    sql=initial_sql('a'*48,'b'*48)
    assert "TO 'nondegree_migration'" in sql
    assert "TO 'nondegree_app'" not in sql
    assert '*.*' not in sql and 'GRANT OPTION' not in sql
    with pytest.raises(ConfigurationRejected):initial_sql("'; DROP DATABASE nondegree;--",'b'*48)


def test_application_and_database_uid_read_only_their_own_secret(source,tls_pair):
    prepare(**args(source,tls_pair))
    # Standalone bind-mount equivalent: a traversable directory + exact file mode/uid.
    # This checks Unix permission semantics, not Docker execution.
    p=Path(tempfile.mkdtemp(prefix='r7-uid-proof-'));p.chmod(0o755)
    try:
        for name in ('runtime_url','root.cnf'):
            old=source/'deploy/secrets'/name;target=p/name;shutil.copy2(old,target)
            os.chown(target,old.stat().st_uid,old.stat().st_gid)
        for uid,name,ok in [(APP_UID,'runtime_url',True),(APP_UID,'root.cnf',False),(DB_UID,'root.cnf',True),(DB_UID,'runtime_url',False)]:
            code="from pathlib import Path; p=Path(__import__('sys').argv[1]); p.read_bytes()"
            r=subprocess.run([sys.executable,'-c',code,str(p/name)],user=uid,group=uid,extra_groups=[],capture_output=True)
            assert (r.returncode==0)==ok
    finally:shutil.rmtree(p)


def test_secret_password_not_in_mysql_command_line():
    root=Path(__file__).resolve().parents[2];script=(root/'deploy/mysql-init/01-users.sh').read_text()
    assert '-p"' not in script and '--defaults-extra-file=/run/secrets/root_cnf' in script
    ignored=(root/'.dockerignore').read_text()
    for text in ('runtime','deploy/secrets','deploy/tls','**/.env'):assert text in ignored
