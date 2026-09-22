#!/usr/bin/env python3
"""Destructive only to two NEW OWNED temporary Docker projects; never real school data.

Requires explicit --run-isolated, local images built from these exact source
bytes, root for bind-mount ownership, Docker Compose, and OpenSSL. There is no
SQLite fallback, SQLAlchemy create_all, fake adapter, remote DB URL, prune, or
release-gate override. Missing prerequisites produce BLOCKED, not PASS.
"""
from __future__ import annotations
import argparse, hashlib, json, os, shutil, socket, subprocess, sys, tempfile, uuid
from pathlib import Path
if __name__=='__main__' and os.name!='posix':
    # Check before importing the POSIX-only deployment controller (fcntl).
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-isolated',action='store_true',required=True)
    parser.add_argument('--output',type=Path,default=Path(__file__).resolve().parents[1]/'evidence/r7/mysql')
    args,_=parser.parse_known_args()
    args.output.mkdir(parents=True,exist_ok=True)
    report={'status':'BLOCKED','reason':['POSIX_RUNTIME_REQUIRED'],'mysql_tested':False,'fresh_executed':False,'restore_executed':False,'production_contacted':False,'synthetic_school_sample':True,'fallback_engine_used':False}
    try:
        with (args.output/'mysql_acceptance.json').open('x',encoding='utf-8') as stream:json.dump(report,stream,indent=2)
    except FileExistsError:parser.exit(2,'BLOCKED: use a new empty evidence output directory.\n')
    print(json.dumps(report));raise SystemExit(2)
from atomic_env import read_env,validate_image
from deploy_control import Pipeline,Runner,ControlError,write_json
from deployment_config import prepare
from school_http_acceptance import Client,run_fresh_school,AcceptanceFailure,PNG

ROOT=Path(__file__).resolve().parents[1]


def preconditions(images):
    missing=[]
    if os.geteuid()!=0:missing.append('ADMINISTRATOR_REQUIRED')
    for cmd in ('docker','openssl'):
        if shutil.which(cmd) is None:missing.append(cmd.upper()+'_UNAVAILABLE')
    for image in images:
        if not image:missing.append('LOCAL_IMAGE_ARGUMENT_REQUIRED')
        else:validate_image(image)
    if missing:return missing,{}
    runner=Runner()
    try:
        runner.run(['docker','version','--format','{{.Server.Version}}'],timeout=15)
        runner.run(['docker','compose','version'],timeout=15)
    except ControlError:return ['DOCKER_SERVER_OR_COMPOSE_UNAVAILABLE'],{}
    resolved={}
    for role,image in zip(('api','frontend','mysql'),images):
        try:
            info=json.loads(runner.run(['docker','image','inspect',image],timeout=15))
            if len(info)!=1 or not info[0].get('Id','').startswith('sha256:'):raise ValueError()
            resolved[role]={'reference':image,'id':info[0]['Id']}
        except (ControlError,ValueError,KeyError):missing.append('LOCAL_IMAGE_MISSING_'+role.upper())
    return missing,resolved


def source_bound_images(source,images,runner):
    # Verify ALL backend and frontend source inputs actually exist unchanged in
    # the API image, not just a hard-coded version string. No mounts or network.
    paths=[p for p in (source/'backend').rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    paths += [p for p in (source/'frontend').rglob('*') if p.is_file()]
    paths += [source/'scripts/check_assembly.py']
    relative=[str(p.relative_to(source)) for p in paths]
    program=('import json,hashlib;from pathlib import Path;'+
        'print(json.dumps({n:hashlib.sha256((Path("/opt/nondegree")/n).read_bytes()).hexdigest() for n in '+repr(relative)+'},sort_keys=True))')
    observed=json.loads(runner.run(['docker','run','--rm','--pull','never','--network','none','--entrypoint','python',images['api']['id'],'-c',program],timeout=60))
    expected={name:hashlib.sha256((source/name).read_bytes()).hexdigest() for name in relative}
    if observed!=expected:raise ControlError('API_IMAGE_SOURCE_MISMATCH')
    frontend={str(p.relative_to(source/'frontend')):hashlib.sha256(p.read_bytes()).hexdigest() for p in (source/'frontend').rglob('*') if p.is_file()}
    mapped={'/usr/share/nginx/html/'+name:digest for name,digest in frontend.items()}
    mapped['/etc/nginx/nginx.conf']=hashlib.sha256((source/'deploy/nginx.conf').read_bytes()).hexdigest()
    raw=runner.run(['docker','run','--rm','--pull','never','--network','none','--entrypoint','sha256sum',images['frontend']['id'],*sorted(mapped)],timeout=40)
    actual={}
    for line in raw.decode().splitlines():
        digest,name=line.split(None,1);actual[name.strip()]=digest
    if actual!=mapped:raise ControlError('FRONTEND_OR_NGINX_IMAGE_SOURCE_MISMATCH')
    return {'status':'MATCH','api_files':len(expected),'frontend_files':len(frontend),'network':'none','host_database_mounted':False}


def copy_clean_source(source,destination):
    ignore=shutil.ignore_patterns('runtime','evidence','acceptance','.git','__pycache__','.pytest_cache','.env','secrets','tls','.prepare-*','PREPARATION_RECEIPT.json','*.sqlite','*.db')
    # A code ZIP should not contain links. Refuse instead of following a link to
    # another school's secrets or an uncontrolled mount.
    for parent in ('backend','frontend','scripts','deploy'):
        for path in (source/parent).rglob('*'):
            if path.is_symlink():raise ControlError('SOURCE_LINK_REFUSED')
    shutil.copytree(source,destination,ignore=ignore)


def make_lab(source,base,kind,images,runner):
    root=base/kind;copy_clean_source(source,root)
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    cert=base/(kind+'-cert.pem');key=base/(kind+'-key.pem')
    runner.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','3','-subj','/CN=127.0.0.1','-addext','subjectAltName=IP:127.0.0.1','-keyout',str(key),'-out',str(cert)])
    for file in (cert,key):file.chmod(0o600)
    origin='https://127.0.0.1:'+str(port)
    prepare(root,school_name='R7独立MySQL合成验收-'+kind,origin=origin,
            api_image=images['api']['reference'],frontend_image=images['frontend']['reference'],mysql_image=images['mysql']['reference'],certificate=cert,private_key=key)
    env=root/'deploy/.env'
    content=env.read_text().replace('ND_BIND_IP=0.0.0.0','ND_BIND_IP=127.0.0.1')+'ND_TLS_CA_FILE=deploy/tls/fullchain.pem\n'
    env.write_text(content);env.chmod(0o600)
    return Pipeline(root,runner),origin,root/'deploy/tls/fullchain.pem'


def privilege_checks(pipeline):
    # Connect as the actual RUNTIME account, supplied solely by its secret file.
    program='''
import json
from pathlib import Path
from sqlalchemy import create_engine,text
from sqlalchemy.exc import DBAPIError
engine=create_engine(Path('/run/secrets/runtime_url').read_text().strip())
checks=[]
with engine.connect() as c:
    version=c.execute(text('SELECT VERSION()')).scalar()
    if not version.startswith('8.4.'):raise RuntimeError('NOT_REAL_MYSQL_84')
    c.execute(text('SELECT COUNT(*) FROM users')).scalar();c.rollback()
    statements=[('ddl','CREATE TABLE r7_forbidden(id INT)'),
      ('provenance_update','UPDATE installation_provenance SET source_kind=source_kind WHERE 1=0'),
      ('version_update','UPDATE alembic_version SET version_num=version_num WHERE 1=0'),
      ('audit_update','UPDATE audit_events SET actor_name=actor_name WHERE 1=0'),
      ('audit_delete','DELETE FROM audit_events WHERE 1=0')]
    for name,sql in statements:
        try:
            c.execute(text(sql));c.rollback()
        except DBAPIError as e:
            code=e.orig.args[0] if e.orig.args else None;c.rollback()
            if code not in (1044,1142,1143,1227):raise RuntimeError('FAILURE_IS_NOT_PERMISSION_DENIED') from None
            checks.append({'check':name,'permission_denied':True,'mysql_code':code})
        else:raise RuntimeError('RUNTIME_PRIVILEGE_TOO_BROAD')
print(json.dumps({'version':version,'checks':checks,'runtime_account_used':True}))
engine.dispose()
'''
    raw=pipeline.dc('run','--rm','--no-deps','--pull','never','api','python','-c',program)
    return json.loads(raw)


def clean_owned_projects(base,pipelines):
    results=[]
    for pipeline in reversed(pipelines):
        if pipeline.root.parent!=base or pipeline.root.name not in ('origin','restored'):
            raise ControlError('UNOWNED_CLEANUP_PATH')
        cfg=read_env(pipeline.root/'deploy/.env')
        if not cfg.get('ND_PROJECT_NAME','').startswith('nondegree-') or cfg.get('ND_BIND_IP')!='127.0.0.1':
            raise ControlError('UNOWNED_CLEANUP_PROJECT')
        # Uses exact newly-created compose file/project; never system-wide prune.
        pipeline.dc('down','--remove-orphans','--volumes',timeout=180)
        if pipeline.dc('ps','-aq').strip():raise ControlError('LAB_CLEANUP_NOT_CONFIRMED')
        results.append({'project':cfg['ND_PROJECT_NAME'],'containers_removed':True})
    return results


def execute(source,out,images):
    report={'status':'BLOCKED','engine':'MYSQL_8_4_REQUIRED','mysql_tested':False,'production_contacted':False,
            'synthetic_school_sample':True,'native_browser_tested':False,'school_acceptance':False,'legacy_upgrade_allowed':False,
            'tests':{},'images':images,'cleanup':[]}
    base=Path(tempfile.mkdtemp(prefix='nondegree-r7-mysql-'));base.chmod(0o700)
    pipelines=[];runner=Runner()
    try:
        report['tests']['image_source_binding']=source_bound_images(source,images,runner)
        origin,url,cert=make_lab(source,base,'origin',images,runner);pipelines.append(origin)
        report['tests']['fresh']=origin.run_install()
        report['tests']['runtime_privileges']=privilege_checks(origin)
        report['mysql_tested']=True;report['database_version']=report['tests']['runtime_privileges']['version']
        first=origin.installation_receipt()
        origin.dc('run','--rm','--no-deps','--pull','never','migrate','alembic','upgrade','head',timeout=900)
        if origin.installation_receipt()!=first:raise ControlError('REPEATED_MIGRATION_CHANGED_IDENTITY')
        report['tests']['repeat_migration']={'status':'PASS','installation_id_unchanged':True}
        business,old_client=run_fresh_school(url,cert,origin.root/'deploy/secrets/admin_password',out/'http')
        report['tests']['business']={'status':business['status'],'checks':len(business['checks']),'requests':len(business['requests'])}
        backup=origin.run_backup();report['tests']['backup']={'status':backup['status'],'restore_tested_at_backup':False}
        restored,restore_url,restore_cert=make_lab(source,base,'restored',images,runner);pipelines.append(restored)
        report['tests']['restore']=restored.run_restore(backup['backup'])
        # The old secure cookie still targets 127.0.0.1, but must be invalid in the
        # restored DB even when copied to a new connection/port.
        events=[];new=Client(restore_url,restore_cert,events,'restored-admin')
        for cookie in old_client.jar:new.jar.set_cookie(cookie)
        new.call('GET','/api/auth/me',expected=401)
        new.first_login('admin',(restored.root/'deploy/secrets/admin_password').read_text().strip())
        expect=business['restore_expectations'];assessment=new.call('GET','/api/assessments/'+expect['assessment_id'])['assessment']
        if assessment['archive_sha256']!=expect['archive_sha256']:raise ControlError('RESTORED_ARCHIVE_MISMATCH')
        raw,_=new.raw('GET','/api/assessments/'+expect['assessment_id']+'/attachments/'+expect['attachment_id']+'/download')
        if raw!=PNG:raise ControlError('RESTORED_ATTACHMENT_MISMATCH')
        if any(x['state']!='NOT_CONNECTED' for x in new.call('GET','/api/connections')['items']):raise ControlError('RESTORED_INTERFACE_NOT_DISCONNECTED')
        restored.privilege_result=privilege_checks(restored)
        report['tests']['restored_privileges']=restored.privilege_result
        before=restored.installation_receipt()
        try:restored.run_restore(backup['backup'])
        except ControlError as e:
            if 'not empty' not in str(e) and 'existing Compose' not in str(e):raise
        else:raise ControlError('DIRTY_TARGET_RESTORE_NOT_REJECTED')
        if restored.installation_receipt()!=before:raise ControlError('DIRTY_TARGET_WAS_CHANGED')
        report['tests']['restore_business']={'status':'PASS','old_session_rejected':True,'fresh_admin_password_required':True,'archive_and_original_attachment_match':True,'nonempty_target_rejected':True,'requests':events}
        report['status']='PASS_ISOLATED_MYSQL_SUBSET'
        report['not_covered']=['legacy upgrade (forbidden)','school real samples/signatures','external adapters','native browser','100 concurrent load','DB crash/restart fault matrix']
    except Exception as exc:
        report['status']='BLOCKED'
        # Only known fixed diagnostic codes, never DBAPI/connection/secret details.
        report['reason']=str(exc)[:400] if isinstance(exc,(ControlError,AcceptanceFailure)) else type(exc).__name__
    finally:
        try:
            report['cleanup']=clean_owned_projects(base,pipelines)
            shutil.rmtree(base);report['private_lab_removed']=True
        except Exception:
            report['status']='BLOCKED';report['cleanup_failed']=True
            report['private_lab_retained_at']=str(base);report['manual_cleanup_required']=True
        write_json(out/'mysql_acceptance.json',report)
    return report


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-isolated',action='store_true',required=True)
    p.add_argument('--api-image');p.add_argument('--frontend-image');p.add_argument('--mysql-image')
    p.add_argument('--output',type=Path,default=ROOT/'evidence/r7/mysql')
    a=p.parse_args(argv);a.output.mkdir(parents=True,exist_ok=True)
    # Refuse overwriting prior acceptance evidence.
    if (a.output/'mysql_acceptance.json').exists():p.exit(2,'BLOCKED: use a new empty evidence output directory.\n')
    try:missing,images=preconditions([a.api_image,a.frontend_image,a.mysql_image])
    except ValueError:missing,images=['IMAGE_REFERENCE_INVALID'],{}
    if missing:
        report={'status':'BLOCKED','reason':missing,'mysql_tested':False,'fresh_executed':False,'restore_executed':False,'production_contacted':False,'synthetic_school_sample':True,'fallback_engine_used':False}
        write_json(a.output/'mysql_acceptance.json',report)
    else:report=execute(ROOT,a.output,images)
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if report['status']=='PASS_ISOLATED_MYSQL_SUBSET' else 2

if __name__=='__main__':raise SystemExit(main())
