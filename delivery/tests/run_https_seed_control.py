#!/usr/bin/env python3
"""Development-only real HTTPS control on a fresh local SQLite database.
Not a server installer, MySQL substitute or browser acceptance. Never public-bind.
"""
import hashlib,json,os,secrets,shutil,socket,ssl,subprocess,sys,tempfile,time
from pathlib import Path
from urllib.request import build_opener,ProxyHandler,HTTPSHandler
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'scripts'),str(ROOT/'backend')]
from delivery.manage import generate_tls
from delivery.seed import populate,ResumableClient
from delivery.common import secure_json

def main(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    lab=Path(tempfile.mkdtemp(prefix='r11-delivery-https-'));lab.chmod(0o700)
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    origin='https://127.0.0.1:'+str(port);ca,cert,key=generate_tls(lab/'tls')
    password=secrets.token_urlsafe(32);secret=lab/'initial-password';secret.write_text(password);secret.chmod(0o600)
    env={k:v for k,v in os.environ.items() if not k.startswith('ND_')}
    env.update(PYTHONPATH=str(ROOT/'backend'),ND_ENV='test',ND_DATABASE_URL='sqlite:///'+str(lab/'canonical.sqlite'),ND_STORAGE_DIR=str(lab/'files'),ND_SECURE_COOKIE='true',ND_ALLOWED_HOSTS='127.0.0.1',ND_PUBLIC_ORIGIN=origin,ND_SCHOOL_NAME='跃科非学历教育体验学校（合成演示数据）')
    (lab/'files').mkdir()
    for args in (['alembic','upgrade','head'],['app.cli','init','--password-file',str(secret)]):
        r=subprocess.run([sys.executable,'-m',*args],cwd=ROOT/'backend',env=env,capture_output=True,timeout=30)
        if r.returncode:raise RuntimeError('Local control initialization failed')
    events=[];server=None
    try:
        with (out/'server.log').open('w') as log:
            server=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:create_app','--factory','--host','127.0.0.1','--port',str(port),'--ssl-certfile',str(cert),'--ssl-keyfile',str(key),'--no-access-log'],cwd=ROOT/'backend',env=env,stdout=log,stderr=subprocess.STDOUT)
            opener=build_opener(ProxyHandler({}),HTTPSHandler(context=ssl.create_default_context(cafile=str(ca))))
            for _ in range(80):
                try:
                    if opener.open(origin+'/api/health',timeout=1).status==200:break
                except Exception:time.sleep(.15)
            else:raise RuntimeError('HTTPS control did not start')
            result=populate(lambda role:ResumableClient(origin,ca,events,role),lab,password,'SQLITE_LOCAL_CONTROL_NOT_MYSQL')
            before=len(events)
            second=populate(lambda role:ResumableClient(origin,ca,events,role),lab,password,'SQLITE_LOCAL_CONTROL_NOT_MYSQL')
            assert len(events)==before and second['repeated_run']=='READ_ONLY_NO_RESEED'
            secure_json(out/'seed_https.json',{'status':'PASS','engine':'SQLite','canonical_migration':True,'real_https':True,
               'tls_verification':True,'request_count':len(events),'requests':events,'summary':result,
               'repeat_no_writes':True,'real_mysql':False,'normal_browser_business':False,'user_server_contacted':False})
            # Trust only this generated local CA in an isolated browser HOME. Do not alter managed policy.
            browser_report={'status':'BLOCKED','normal_browser_business':False,'policy_changed':False,'tls_check_disabled':False}
            try:
                from playwright.sync_api import sync_playwright
                home=lab/'browser-home';nss=home/'.pki/nssdb';nss.mkdir(parents=True)
                if shutil.which('certutil'):
                    subprocess.run(['certutil','-N','-d','sql:'+str(nss),'--empty-password'],check=True,capture_output=True)
                    subprocess.run(['certutil','-A','-d','sql:'+str(nss),'-n','R11 local control CA','-t','C,,','-i',str(ca)],check=True,capture_output=True)
                with sync_playwright() as pw:
                    b=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,env={**os.environ,'HOME':str(home)},args=['--no-sandbox'])
                    try:
                        pg=b.new_page();r=pg.goto(origin,wait_until='domcontentloaded',timeout=10000)
                        browser_report.update(status='NAVIGATION_ONLY',http_status=r.status if r else None)
                    finally:b.close()
            except Exception as exc:browser_report['error']=str(exc)[:1800]
            secure_json(out/'browser_probe.json',browser_report)
            print(json.dumps({'status':'HTTPS_SEED_CONTROL_PASS','requests':len(events),'counts':result['counts'],'browser_probe':browser_report['status'],'mysql':False},ensure_ascii=False))
    finally:
        if server:
            server.terminate()
            try:server.wait(timeout=5)
            except subprocess.TimeoutExpired:server.kill();server.wait()
        shutil.rmtree(lab)
if __name__=='__main__':main(sys.argv[1])
