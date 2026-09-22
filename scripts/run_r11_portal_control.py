#!/usr/bin/env python3
"""Actual front-end render/API control against temporary HTTP+SQLite fixtures.
No existing school database, production network, browser-policy bypass or credentials.
"""
from pathlib import Path
import json,os,socket,subprocess,sys,tempfile,time,urllib.request,shutil
ROOT=Path(__file__).resolve().parents[1]

def main():
    output=ROOT/'evidence/r11/portal_control';output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='nd-r11-portal-') as directory:
        lab=Path(directory)
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        origin=f'http://127.0.0.1:{port}'
        env={k:v for k,v in os.environ.items() if not k.startswith('ND_')}
        env['PYTHONPATH']=str(ROOT/'backend')+':'+str(ROOT/'tests/r2')
        # The module exists only in this temporary directory and uses env=test.
        module=lab/'portal_control_app.py'
        module.write_text("from app.main import create_app\nfrom app.config import Settings\nfrom support import populate\n"+
            f"app=create_app(Settings(env='test',database_url='sqlite:///{lab}/fixture.sqlite',storage_dir='{lab}/files',secure_cookie=False,public_origin='{origin}',allowed_hosts='127.0.0.1'))\n"+
            "populate(app.state.engine)\n",encoding='utf-8')
        env['PYTHONPATH']=str(lab)+':'+env['PYTHONPATH']
        with (output/'server.log').open('w') as log:
            server=subprocess.Popen([sys.executable,'-m','uvicorn','portal_control_app:app','--host','127.0.0.1','--port',str(port),'--no-access-log'],env=env,stdout=log,stderr=subprocess.STDOUT)
            try:
                opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
                for _ in range(100):
                    try:
                        with opener.open(origin+'/',timeout=.25) as response:
                            if response.status==200:break
                    except Exception:pass
                    if server.poll() is not None:raise RuntimeError('Temporary service exited; inspect server.log')
                    time.sleep(.1)
                else:raise RuntimeError('Temporary service startup timed out')
                result=subprocess.run(['node',str(ROOT/'tests/js/r11_live_portal_control.mjs'),origin,str(output)],cwd=ROOT,capture_output=True,text=True,timeout=90)
                (output/'node.log').write_text(result.stdout+'\n'+result.stderr)
                print(result.stdout[-4000:])
                if result.returncode:raise RuntimeError('Front-end live control failed; inspect node.log')
            finally:
                server.terminate()
                try:server.wait(timeout=5)
                except subprocess.TimeoutExpired:server.kill();server.wait()
        (output/'boundary.json').write_text(json.dumps({'engine':'isolated SQLite synthetic fixtures','transport':'real HTTP loopback','ui_execution':'actual application module in Node VM; no native page navigation','production_contacted':False,'server_stopped':True,'temporary_database_deleted':True,'school_credentials_used':False},indent=2))

if __name__=='__main__':main()
