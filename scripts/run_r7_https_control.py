#!/usr/bin/env python3
"""Real HTTPS + canonical SQLite control; explicitly NOT MySQL/browser acceptance."""
from pathlib import Path
import json,os,socket,ssl,subprocess,sys,tempfile,time
from urllib.request import build_opener,ProxyHandler,HTTPSHandler
from school_http_acceptance import run_fresh_school
ROOT=Path(__file__).resolve().parents[1]

def main(output=None,*,label="R7"):
    out=Path(output) if output is not None else ROOT/'evidence/r7/https_control';out.mkdir(parents=True,exist_ok=True)
    lab=Path(tempfile.mkdtemp(prefix=f'nondegree-{label.lower()}-https-control-'));lab.chmod(0o700)
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    origin='https://127.0.0.1:'+str(port);key=lab/'key.pem';cert=lab/'cert.pem'
    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','3','-subj','/CN=127.0.0.1','-addext','subjectAltName=IP:127.0.0.1','-keyout',str(key),'-out',str(cert)],check=True,capture_output=True,timeout=15)
    password=lab/'admin_password';password.write_text(__import__('secrets').token_urlsafe(32));password.chmod(0o600)
    env={k:v for k,v in os.environ.items() if not k.startswith('ND_')}
    env.update(PYTHONPATH=str(ROOT/'backend'),ND_ENV='test',ND_DATABASE_URL='sqlite:///'+str(lab/'canonical.sqlite'),ND_PUBLIC_ORIGIN=origin,ND_SCHOOL_NAME=label+'独立合成验收学校',ND_STORAGE_DIR=str(lab/'files'),ND_SECURE_COOKIE='true',ND_ALLOWED_HOSTS='127.0.0.1')
    def cmd(args):
        r=subprocess.run([sys.executable,*args],cwd=ROOT/'backend',env=env,capture_output=True,timeout=25)
        if r.returncode:raise RuntimeError('control command failed: '+r.stderr.decode()[:500])
        return r
    cmd(['-m','alembic','upgrade','head']);cmd(['-m','app.cli','init','--password-file',str(password)])
    with (out/'server.log').open('w') as log:
        server=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:create_app','--factory','--host','127.0.0.1','--port',str(port),'--ssl-keyfile',str(key),'--ssl-certfile',str(cert),'--no-access-log'],cwd=ROOT/'backend',env=env,stdout=log,stderr=subprocess.STDOUT)
        try:
            opener=build_opener(ProxyHandler({}),HTTPSHandler(context=ssl.create_default_context(cafile=str(cert))))
            for _ in range(100):
                try:
                    with opener.open(origin+'/',timeout=.3) as response:
                        if response.status==200:break
                except Exception:pass
                if server.poll() is not None:raise RuntimeError('control server exited')
                time.sleep(.1)
            else:raise RuntimeError('control HTTPS not ready')
            report,client=run_fresh_school(origin,cert,password,out,process_tasks=lambda:cmd(['-c','from app.worker import run_once;run_once()']))
            report.update(engine='SQLITE_CONTROL_ONLY',mysql_tested=False,tls_tested=True,canonical_migration_used=True,raw_school_data_seeded=False)
            (out/'business_http.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
            print(json.dumps({'status':report['status'],'checks':len(report['checks']),'requests':len(report['requests']),'mysql_tested':False,'tls_tested':True},indent=2))
            browser_report={'status':'BLOCKED','native_business_flows_pass':False,'mysql_tested':False,'policy_modified':False,'tls_verification_disabled':False}
            # Ordinary navigation to the normal endpoint; no policy overrides.
            try:
                from playwright.sync_api import sync_playwright
                with sync_playwright() as p:
                    b=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
                    try:
                        page=b.new_page();response=page.goto(origin,wait_until='domcontentloaded',timeout=10000)
                        browser_report.update(status='NAVIGATION_ONLY',http_status=response.status if response else None)
                    finally:b.close()
            except Exception as exc:browser_report['error']=str(exc)[:2000]
            (out/'browser_probe.json').write_text(json.dumps(browser_report,ensure_ascii=False,indent=2))
        finally:
            server.terminate()
            try:server.wait(timeout=5)
            except subprocess.TimeoutExpired:server.kill();server.wait()
            (out/'boundary.json').write_text(json.dumps({'source':label+' canonical empty-school migration + CLI init','business_data':'synthetic via HTTP only','engine':'SQLite control','production_contacted':False,'server_stopped':True,'private_db_not_packaged':True},indent=2))
            # Keep only public certificate fingerprint; never package temporary keys/DB.
            import hashlib,shutil
            (out/'tls_identity.json').write_text(json.dumps({'certificate_sha256':hashlib.sha256(cert.read_bytes()).hexdigest(),'scope':'self-signed loopback test certificate','school_certificate_verified':False}))
            shutil.rmtree(lab)

if __name__=='__main__':main()
