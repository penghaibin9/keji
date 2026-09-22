#!/usr/bin/env python3
"""One new loopback-only synthetic lab; no existing databases are reset.

Runs real HTTP, then a normal native Chromium navigation attempt. An environment
administrator block is recorded as BLOCKED, never bypassed or reclassified PASS.
"""
import json,os,socket,subprocess,sys,tempfile,time
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'evidence/r6';OUT.mkdir(parents=True,exist_ok=True)
with socket.socket() as s:
    s.bind(('127.0.0.1',8768))
lab=Path(tempfile.mkdtemp(prefix='nd-r2-test-r6-http-'))
env={**os.environ,'ND_R6_HTTP_LAB':str(lab),'PYTHONPATH':str(ROOT/'backend')}
with (OUT/'http_server.log').open('w') as log:
    server=subprocess.Popen([sys.executable,str(ROOT/'tests/r2/browser_lab.py'),str(lab)],stdout=log,stderr=subprocess.STDOUT,cwd=ROOT,env=env)
    try:
        for _ in range(60):
            try:
                if httpx.get('http://127.0.0.1:8768/',timeout=.5,trust_env=False).status_code==200:break
            except httpx.RequestError:pass
            if server.poll() is not None:raise RuntimeError('synthetic server exited')
            time.sleep(.1)
        else:raise RuntimeError('synthetic server did not start')
        ran=subprocess.run([sys.executable,str(ROOT/'tests/r2/r6_http_flows.py')],cwd=ROOT,env=env,capture_output=True,text=True,timeout=30)
        (OUT/'http_flow.log').write_text(ran.stdout+ran.stderr)
        browser_result={'status':'BLOCKED','native_browser':False,'four_roles':False,'critical_flows_pass':False,
            'security_negative_pass':False,'synthetic':True,'mysql_tested':False,'tls_tested':False,
            'http_status':200,'purpose':'normal navigation capability probe, not full browser acceptance'}
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
                browser_result['browser_started']=True
                try:
                    page=browser.new_page();response=page.goto('http://127.0.0.1:8768/',wait_until='domcontentloaded',timeout=10000)
                    browser_result.update(status='NAVIGATION_ONLY',navigation_status=response.status if response else None)
                    page.screenshot(path=str(OUT/'browser_initial_page.png'),full_page=True)
                finally:browser.close()
        except Exception as exc:browser_result['error']=str(exc)[:3000]
        (OUT/'browser_probe.json').write_text(json.dumps(browser_result,ensure_ascii=False,indent=2))
        print(ran.stdout);print(json.dumps(browser_result,ensure_ascii=False,indent=2))
        if ran.returncode:raise SystemExit(ran.returncode)
    finally:
        server.terminate()
        try:server.wait(timeout=5)
        except subprocess.TimeoutExpired:server.kill();server.wait()
        (OUT/'http_lab_boundary.json').write_text(json.dumps({'lab':str(lab),'synthetic':True,'server_stopped':True,'database_packaged':False,'production_accessed':False},indent=2))
