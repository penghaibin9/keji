#!/usr/bin/env python3
"""Real nginx + loopback HTTPS static/API contract control. Not Docker or MySQL.
Starts only fresh temporary loopback services. No policy or TLS verification bypass.
"""
from pathlib import Path
import hashlib,http.cookiejar,json,os,re,socket,ssl,subprocess,sys,tempfile,time,urllib.request,urllib.error
ROOT=Path(__file__).resolve().parents[1]

def port():
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));return sock.getsockname()[1]

def main():
    output=ROOT/'evidence/r11/proxy_control';output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='nd-r11-proxy-') as d:
        lab=Path(d);ap=port();np=port();origin=f'https://127.0.0.1:{np}'
        key=lab/'key.pem';cert=lab/'cert.pem'
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=127.0.0.1','-addext','subjectAltName=IP:127.0.0.1','-keyout',str(key),'-out',str(cert)],check=True,capture_output=True,timeout=15)
        module=lab/'proxy_control_app.py'
        module.write_text("from app.main import create_app\nfrom app.config import Settings\nfrom support import populate\n"+f"app=create_app(Settings(env='test',database_url='sqlite:///{lab}/fixture.sqlite',storage_dir='{lab}/files',secure_cookie=True,public_origin='{origin}',allowed_hosts='127.0.0.1'))\npopulate(app.state.engine)\n")
        env={k:v for k,v in os.environ.items() if not k.startswith('ND_')};env['PYTHONPATH']=':'.join(map(str,[lab,ROOT/'backend',ROOT/'tests/r2']))
        source=(ROOT/'deploy/nginx.conf').read_text()
        config=source.replace('pid /tmp/nginx.pid;',f'pid {lab}/nginx.pid;\ndaemon off;\nmaster_process off;').replace('listen 8443 ssl;',f'listen 127.0.0.1:{np} ssl;').replace('/run/tls/fullchain.pem',str(cert)).replace('/run/tls/privkey.pem',str(key)).replace('/usr/share/nginx/html',str(ROOT/'frontend')).replace('http://api:8000',f'http://127.0.0.1:{ap}').replace('/tmp/client_body',str(lab/'body')).replace('/tmp/proxy',str(lab/'proxy')).replace('access_log /dev/stdout;','access_log off;').replace('error_log /dev/stderr warn;',f'error_log {lab}/nginx-error.log warn;')
        (lab/'body').mkdir();(lab/'proxy').mkdir();path=lab/'nginx.conf';path.write_text(config)
        syntax=subprocess.run(['nginx','-t','-p',str(lab),'-c',str(path)],capture_output=True,text=True)
        (output/'nginx-syntax.log').write_text(syntax.stdout+syntax.stderr);assert syntax.returncode==0,syntax.stderr
        with (output/'backend.log').open('w') as backendlog,(output/'nginx.log').open('w') as nginxlog:
            backend=subprocess.Popen([sys.executable,'-m','uvicorn','proxy_control_app:app','--host','127.0.0.1','--port',str(ap),'--no-access-log'],env=env,stdout=backendlog,stderr=subprocess.STDOUT)
            nginx=subprocess.Popen(['nginx','-p',str(lab),'-c',str(path)],stdout=nginxlog,stderr=subprocess.STDOUT)
            try:
                jar=http.cookiejar.CookieJar();opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=str(cert))),urllib.request.HTTPCookieProcessor(jar))
                for _ in range(100):
                    try:
                        with opener.open(origin+'/api/health',timeout=.3):break
                    except urllib.error.HTTPError as ex:
                        if ex.code not in [502,503,504]:break
                    except Exception:pass
                    if backend.poll() is not None or nginx.poll() is not None:raise RuntimeError('Proxy control service exited')
                    time.sleep(.1)
                checks=[]
                with opener.open(origin+'/',timeout=3) as r:
                    html=r.read();assert b'/assets/app.js' in html;assert r.headers.get('X-Content-Type-Options')=='nosniff';checks.append({'url':'/','status':r.status,'content_type':r.headers.get('Content-Type')})
                for name in ['app.js','scope.js','icons.js','portal-ui.js','styles.css','integration.css','portal.css']:
                    with opener.open(origin+'/assets/'+name,timeout=3) as r:
                        data=r.read();expected=(ROOT/'frontend'/name).read_bytes()
                        assert data==expected,name
                        assert 'html' not in r.headers.get('Content-Type',''),name
                        assert r.headers.get('Cache-Control')=='no-store'
                        checks.append({'url':'/assets/'+name,'status':r.status,'bytes':len(data),'content_type':r.headers.get('Content-Type'),'sha256':hashlib.sha256(data).hexdigest()})
                try:opener.open(origin+'/assets/does-not-exist.js',timeout=3);raise AssertionError('Missing asset must not fall back to HTML')
                except urllib.error.HTTPError as e:assert e.code==404;checks.append({'url':'/assets/does-not-exist.js','status':404})
                request=urllib.request.Request(origin+'/api/auth/login',data=json.dumps({'username':'schooladmin','password':'FixtureOnly_2026_Local'}).encode(),headers={'Origin':origin,'Content-Type':'application/json'},method='POST')
                with opener.open(request,timeout=3) as r:assert r.status==200;checks.append({'url':'/api/auth/login','status':r.status})
                assert any(c.secure for c in jar),'secure cookie must be set through HTTPS proxy'
                with opener.open(origin+'/api/auth/me',timeout=3) as r:user=json.load(r);assert user['user']['id']=='schooladmin';checks.append({'url':'/api/auth/me','status':r.status})
                with opener.open(origin+'/api/statistics',timeout=3) as r:stats=json.load(r);assert str(stats['income']) in ['300','300.00'];checks.append({'url':'/api/statistics','status':r.status})
                with opener.open(origin+'/api/connections/coordination.xlsx',timeout=3) as r:assert r.read().startswith(b'PK');checks.append({'url':'/api/connections/coordination.xlsx','status':r.status})
                report={'status':'PASS','scope':'actual system nginx binary, temporary paths and loopback ports, self-signed certificate explicitly trusted, real API with synthetic SQLite fixture','docker_tested':False,'mysql_tested':False,'browser_business_tested':False,'tls_verification_disabled':False,'original_nginx_config_sha256':hashlib.sha256(source.encode()).hexdigest(),'checks':checks}
                (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps({'status':'PASS','checks':len(checks)}))
            finally:
                for proc in [nginx,backend]:
                    proc.terminate()
                    try:proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:proc.kill();proc.wait()
                if (lab/'nginx-error.log').exists():(output/'nginx-error.log').write_text((lab/'nginx-error.log').read_text())
    (output/'boundary.json').write_text(json.dumps({'temporary_services_stopped':True,'private_key_and_database_removed':True,'production_contacted':False}))
if __name__=='__main__':main()
