#!/usr/bin/env python3
"""R11 restricted server deployment: inspect -> explicit approval -> new instance.
No command installs Docker, edits host nginx/firewall, deletes data or opens a public port.
"""
from __future__ import annotations
import argparse, datetime as dt, fcntl, hashlib, io, json, os, platform, re, secrets, shutil, socket, subprocess, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from delivery.common import Blocked,command,digest,load_private,safe_path,secure_json,verify_baseline
from atomic_env import read_env
DEFAULT_TARGET='/opt/yueke/nondegree-r11-preview'

def now():return dt.datetime.now(dt.timezone.utc)
def host_id():
    machine=Path('/etc/machine-id')
    return hashlib.sha256((socket.gethostname()+'|'+(machine.read_text().strip() if machine.exists() else platform.node())).encode()).hexdigest()
def port_available(port):
    if isinstance(port,bool) or not isinstance(port,int) or not 1024<=port<=65535:return False
    try:
        with socket.socket() as s:s.bind(('127.0.0.1',port))
        return True
    except OSError:return False

def probe(args):
    try:return command(args,timeout=12).decode().strip()
    except Blocked:return None

def local_docker():
    version=probe(['docker','version','--format','{{.Server.Version}}'])
    context=probe(['docker','context','show'])
    endpoint=probe(['docker','context','inspect','default','--format','{{.Endpoints.docker.Host}}'])
    blockers=[]
    if not version:blockers.append('DOCKER_ENGINE_UNAVAILABLE')
    elif not re.match(r'^(?:2[89]|[3-9][0-9])\.',version):blockers.append('DOCKER_28_OR_NEWER_REQUIRED_FOR_LOCALHOST_PUBLISH')
    if context!='default' or not endpoint or not endpoint.startswith('unix://'):
        blockers.append('LOCAL_DEFAULT_DOCKER_CONTEXT_REQUIRED')
    compose=probe(['docker','compose','version','--short'])
    if not compose:blockers.append('DOCKER_COMPOSE_UNAVAILABLE')
    return {'server_version':version,'compose_version':compose,'context':context,'endpoint':endpoint},blockers

def inspect_host(target,port):
    target=safe_path(target)
    if len(target.parts)<4 or target in (Path('/var/lib/mysql'),Path('/opt/yueke')):raise Blocked('DEDICATED_TARGET_REQUIRED')
    docker,blockers=local_docker()
    if os.path.lexists(target):blockers.append('TARGET_ALREADY_EXISTS_NEVER_OVERWRITE')
    if not port_available(port):blockers.append('PROPOSED_PORT_NOT_AVAILABLE')
    if not shutil.which('openssl'):blockers.append('OPENSSL_REQUIRED')
    ancestor=target.parent
    while not ancestor.exists():ancestor=ancestor.parent
    free=shutil.disk_usage(ancestor).free
    mem=None
    if Path('/proc/meminfo').exists():
        m=re.search(r'^MemAvailable:\s+(\d+)',Path('/proc/meminfo').read_text(),re.M)
        if m:mem=int(m.group(1))*1024
    if free<8*1024**3:blockers.append('FREE_DISK_BELOW_8_GIB')
    if mem is not None and mem<5*1024**3:blockers.append('AVAILABLE_MEMORY_BELOW_5_GIB')
    return {'docker':docker,'platform':platform.platform(),'cpu_count':os.cpu_count(),'available_memory_bytes':mem,'free_disk_bytes':free,
        'listening_tcp':probe(['ss','-ltn']),'containers':probe(['docker','ps','--format','{{.Names}}\t{{.Image}}\t{{.Ports}}']),
        'blockers':blockers,'target':str(target),'port':port,'bind_ip':'127.0.0.1','configured_service_memory_ceiling_mib':4352,'configured_cpu_limits':{'db':1,'api':2,'worker':1,'frontend':0.5},'host_overhead_not_included':True,'server_modified':False}

def make_plan(target,port,out):
    verify_baseline(ROOT)
    report=inspect_host(target,port)
    p={'format':'R11_RESTRICTED_PLAN_1','created_at':now().isoformat(),'expires_at':(now()+dt.timedelta(hours=12)).isoformat(),
       'host_id':host_id(),'source_baseline':'dd938989030f217851667c487f64234cfe3ec95acf4a589351e4add12358d546',
       'nonce':secrets.token_hex(12),'proposal':report,'approval_scope':['create_new_dedicated_directory','create_local_CA_and_TLS',
       'build_unique_images','start_new_mysql_8_4_instance','canonical_empty_school_install','seed_synthetic_data_through_authorized_API'],
       'excluded':['host_nginx_changes','firewall_changes','production_DB','existing_directories','public_port_publication','external_adapters'],
       'status':'BLOCKED' if report['blockers'] else 'AWAITING_USER_CONFIRMATION'}
    p['approval_id']=digest(p);secure_json(out,p,exclusive=True)
    return {'status':p['status'],'report':str(out),'approval_id':p['approval_id'],'proposal':report,
            'next':'Review plan with owner. Do not prepare while blockers exist.'}

def validate_plan(p,approval):
    body={k:v for k,v in p.items() if k!='approval_id'}
    if not approval or p.get('approval_id')!=approval or digest(body)!=approval:raise Blocked('APPROVAL_OR_PLAN_MISMATCH')
    if p.get('format')!='R11_RESTRICTED_PLAN_1' or p.get('host_id')!=host_id():raise Blocked('PLAN_WRONG_HOST')
    if dt.datetime.fromisoformat(p['expires_at'])<now():raise Blocked('PLAN_EXPIRED_RERUN_READ_ONLY_INSPECTION')
    if p.get('status')!='AWAITING_USER_CONFIRMATION' or p['proposal']['blockers']:raise Blocked('PLAN_BLOCKERS_UNRESOLVED')
    if inspect_host(p['proposal']['target'],p['proposal']['port'])['blockers']:raise Blocked('ENVIRONMENT_CHANGED_REPLAN')

def generate_tls(where):
    where.mkdir(mode=0o700);key=where/'ca.key';crt=where/'ca.crt';leafkey=where/'server.key';csr=where/'server.csr';cert=where/'server.crt'
    command(['openssl','req','-x509','-newkey','rsa:3072','-sha256','-nodes','-days','365','-keyout',key,'-out',crt,
      '-subj','/CN=Yueke R11 Restricted Showcase Local CA','-addext','basicConstraints=critical,CA:TRUE','-addext','keyUsage=critical,keyCertSign,cRLSign'])
    command(['openssl','req','-newkey','rsa:2048','-sha256','-nodes','-keyout',leafkey,'-out',csr,'-subj','/CN=127.0.0.1'])
    ext=where/'server.ext';ext.write_text('basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\nsubjectAltName=IP:127.0.0.1,DNS:localhost\n')
    command(['openssl','x509','-req','-in',csr,'-CA',crt,'-CAkey',key,'-CAcreateserial','-days','90','-sha256','-extfile',ext,'-out',cert])
    for f in where.iterdir():f.chmod(0o600)
    return crt,cert,leafkey

def prepare(plan_file,approval):
    if os.geteuid()!=0:raise Blocked('ROOT_REQUIRED_TO_SET_CONTAINER_FILE_OWNERSHIP')
    verify_baseline(ROOT);p=load_private(plan_file);validate_plan(p,approval)
    target=Path(p['proposal']['target']);parent=safe_path(target.parent);parent.mkdir(parents=True,exist_ok=True,mode=0o750)
    target.mkdir(mode=0o750) # exclusive; never reuse even an empty old installation
    # Copy original R11 plus packaged delivery files; never copy runtime/private state.
    names=set(json.loads((ROOT/'delivery/R11_BASE_MANIFEST.json').read_text())['files'])
    names.update(str(f.relative_to(ROOT)) for f in (ROOT/'delivery').rglob('*') if f.is_file() and not f.is_symlink() and '__pycache__' not in f.parts)
    names.update(n for n in ['开始部署.sh','先读我_部署与演示.html','R11_DEPLOYMENT_SHA256SUMS.txt'] if (ROOT/n).is_file())
    for name in sorted(names):
        src=ROOT/name
        if src.is_symlink():raise Blocked('SYMLINK_SOURCE_REFUSED')
        dst=target/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
    state=target/'delivery-state';state.mkdir(mode=0o700)
    secure_json(state/'approval.json',p,exclusive=True)
    secure_json(state/'state.json',{'state':'PREPARING','approval_id':approval,'target':str(target),'port':p['proposal']['port'],'host_id':host_id()},exclusive=True)
    ca,cert,key=generate_tls(state/'tls')
    from deployment_config import prepare as original_prepare
    token=secrets.token_hex(6);tag='r11-restricted-'+token
    r=original_prepare(target,school_name='跃科非学历教育体验学校（合成演示数据）',origin=f'https://127.0.0.1:{p["proposal"]["port"]}',
      api_image='yueke/nondegree-api:'+tag,frontend_image='yueke/nondegree-frontend:'+tag,mysql_image='mysql:8.4',certificate=str(cert),private_key=str(key))
    # Only new instance configuration changes. Original R11 compose/source stays byte-identical.
    env=target/'deploy/.env';text=env.read_text().replace('ND_BIND_IP=0.0.0.0','ND_BIND_IP=127.0.0.1')
    text+='ND_TLS_CA_FILE=delivery-state/tls/ca.crt\n'
    env.write_text(text);env.chmod(0o600)
    trust=target/'client-access';trust.mkdir(mode=0o700)
    shutil.copyfile(ca,trust/'R11_Local_CA.cer')
    shutil.copyfile(target/'delivery/Windows_受限访问.ps1',trust/'Windows_受限访问.ps1')
    (trust/'访问端口.txt').write_text(str(p['proposal']['port']))
    secure_json(state/'state.json',{'state':'PREPARED','approval_id':approval,'host_id':host_id(),'target':str(target),
      'port':p['proposal']['port'],'project':r['project'],'origin':f'https://127.0.0.1:{p["proposal"]["port"]}',
      'public_access':False,'production_approved':False,'mysql_tested':False,'browser_tested':False})
    return {'status':'PREPARED_NOT_STARTED','target':str(target),'next':'Use target/开始部署.sh build, then install and seed.','credentials_printed':False}

def selected(target):
    target=safe_path(target);s=load_private(target/'delivery-state/state.json')
    if s['host_id']!=host_id() or s['target']!=str(target):raise Blocked('DEPLOYMENT_MARKER_WRONG_HOST_OR_PATH')
    verify_baseline(target)
    c=read_env(target/'deploy/.env')
    if c.get('ND_BIND_IP')!='127.0.0.1' or c.get('ND_ENV')!='production' or c.get('ND_SEED_ENABLED')!='false' or c.get('ND_ADAPTER_MODULES'):
        raise Blocked('RESTRICTED_BOUNDARY_CHANGED')
    if c.get('ND_PUBLIC_ORIGIN')!=s['origin'] or c.get('ND_PROJECT_NAME')!=s['project']:raise Blocked('PROJECT_OR_ORIGIN_CHANGED')
    d,errs=local_docker()
    if errs:raise Blocked(','.join(errs))
    return target,s,c

def pipeline(target):
    if os.environ.get('DOCKER_HOST') or os.environ.get('DOCKER_CONTEXT'):
        raise Blocked('UNSET_DOCKER_OVERRIDE_VARIABLES_FOR_LOCAL_DEPLOYMENT')
    from deploy_control import Pipeline
    pp=Pipeline(target)
    pp.compose+=['-f',str(Path(target)/'delivery/compose.restricted.yml')]
    return pp

def build_images(target):
    target,s,c=selected(target)
    if s['state'] not in ('PREPARED','BUILD_FAILED'):raise Blocked('BUILD_ONLY_BEFORE_INSTALL')
    log=target/'delivery-state/build.log'
    command(['docker','pull',c['ND_MYSQL_IMAGE']],timeout=1200,log=log)
    # A whitelist-only build context excludes local passwords/CA private keys and runtime data.
    names=json.loads((target/'delivery/R11_BASE_MANIFEST.json').read_text())['files']
    try:
        for image,df in ((c['ND_API_IMAGE'],'deploy/Dockerfile.api'),(c['ND_FRONTEND_IMAGE'],'deploy/Dockerfile.frontend')):
            # Build from a new whitelist-only directory. Docker 29 treats a streamed
            # context plus an explicit Dockerfile as ambiguous.
            context=Path(tempfile.mkdtemp(prefix='.build-context-',dir=target/'delivery-state'))
            os.chmod(context,0o700)
            try:
                for name in sorted(names):
                    if name.startswith(('backend/','frontend/','deploy/')) or name=='scripts/check_assembly.py':
                        dst=context/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(target/name,dst)
                with log.open('ab') as out:
                    env={k:v for k,v in os.environ.items() if not k.startswith(('ND_','COMPOSE_')) and k not in ('DOCKER_HOST','DOCKER_CONTEXT')}
                    r=subprocess.run(['docker','build','--pull','-t',image,'-f',str(context/df),str(context)],stdout=out,stderr=subprocess.STDOUT,env=env,timeout=1800)
            finally:
                shutil.rmtree(context,ignore_errors=True)
            if r.returncode:raise Blocked('IMAGE_BUILD_FAILED_SEE_PRIVATE_LOG')
        ids=json.loads(command(['docker','image','inspect',c['ND_API_IMAGE'],c['ND_FRONTEND_IMAGE'],c['ND_MYSQL_IMAGE']]))
        s['image_ids']=[{'id':x['Id'],'tags':x.get('RepoTags',[])} for x in ids];s['state']='BUILT'
        secure_json(target/'delivery-state/state.json',s)
    except Exception:
        s['state']='BUILD_FAILED';secure_json(target/'delivery-state/state.json',s);raise
    return {'status':'IMAGES_BUILT','image_ids':s['image_ids'],'mysql_started':False}

def install(target):
    target,s,c=selected(target)
    if s['state']!='BUILT':raise Blocked('BUILD_FIRST_OR_REVIEW_PARTIAL_INSTALL')
    s['state']='INSTALLING';secure_json(target/'delivery-state/state.json',s)
    try:
        result=pipeline(target).run_install()
        pp=pipeline(target);pp.preflight('verify');proof=pp.installation_receipt()
        version=pp.dc('exec','-T','db','mysql','--defaults-extra-file=/run/secrets/root_cnf','-N','-e','SELECT VERSION();').decode().strip()
        if not re.match(r'^8\.4\.',version):raise Blocked('REAL_MYSQL_NOT_8_4')
        secure_json(target/'delivery-state/mysql-installation.json',{'version':version,'provenance':proof,'real_mysql_installation':True,'restoration_tested':False})
        s.update(state='INSTALLED',mysql_tested=True,installation_id=proof['installation_id'])
        secure_json(target/'delivery-state/state.json',s)
        return result|{'mysql_version':version,'synthetic_data_seeded':False,'browser_tested':False}
    except Exception:
        s['state']='INSTALL_FAILED';secure_json(target/'delivery-state/state.json',s);raise

def status(target):
    target,s,c=selected(target)
    return {'state':s,'services':pipeline(target).dc('ps','--format','json').decode(),'stable_demonstration_claimed':False,
        'note':'Compare the client browser acceptance report.json PASS with this instance MySQL receipt; state.browser_tested is not set automatically by the separate workstation runner.'}

def operations(target,action):
    target,s,c=selected(target);pp=pipeline(target)
    if action=='stop':
        pp.dc('stop','-t','45','frontend','worker','api','db',timeout=180)
        return {'status':'DEDICATED_PROJECT_STOPPED','data_deleted':False,'existing_services_touched':False}
    if action=='resume':
        if (target/'runtime/maintenance/active').exists():raise Blocked('UNRESOLVED_MAINTENANCE_REFUSED')
        if s['state'] not in ('INSTALLED','SEEDED'):raise Blocked('INSTALLATION_NOT_COMPLETED')
        pp.preflight('verify');pp.installation_receipt()
        pp.dc('up','-d','--no-build','--pull','never','--wait','db','api','worker','frontend',timeout=240)
        return {'status':'SERVICES_STARTED_BROWSER_RECHECK_REQUIRED'}
    if action=='backup':return pp.run_backup()
    raise Blocked('UNKNOWN_OPERATION')

def main():
    ap=argparse.ArgumentParser(description=__doc__);sub=ap.add_subparsers(dest='action',required=True)
    p=sub.add_parser('plan');p.add_argument('--target',default=DEFAULT_TARGET);p.add_argument('--port',type=int,default=18443);p.add_argument('--out',default='R11_只读预检_待确认.json')
    p=sub.add_parser('prepare');p.add_argument('--plan',required=True);p.add_argument('--confirm',required=True)
    for name in ('build','install','seed','status','stop','resume','backup'):
        p=sub.add_parser(name);p.add_argument('--target',default=str(ROOT))
    a=ap.parse_args()
    try:
        if a.action=='plan':result=make_plan(a.target,a.port,a.out)
        elif a.action=='prepare':result=prepare(a.plan,a.confirm)
        elif a.action=='build':result=build_images(a.target)
        elif a.action=='install':result=install(a.target)
        elif a.action=='status':result=status(a.target)
        elif a.action=='seed':
            from delivery.seed import seed_target
            result=seed_target(a.target)
        else:result=operations(a.target,a.action)
        print(json.dumps(result,ensure_ascii=False,indent=2));return 2 if result.get('status')=='BLOCKED' else 0
    except (Blocked,OSError,ValueError,RuntimeError) as e:
        print(json.dumps({'status':'BLOCKED','reason':str(e) if isinstance(e,Blocked) else type(e).__name__,
            'note':'No host firewall/nginx changes. Do not delete maintenance latches or seed journals to bypass failure.'},ensure_ascii=False));return 2
if __name__=='__main__':raise SystemExit(main())
