"""Real loopback TLS against a synthetic HTTP server, not the school application."""
import json,ssl,subprocess,threading
from http.server import HTTPServer,BaseHTTPRequestHandler
from urllib.error import URLError
import pytest
from deployment_smoke import run_smoke

@pytest.fixture
def tls_fixture(tmp_path):
    cert,key=tmp_path/'cert.pem',tmp_path/'key.pem'
    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(key),'-out',str(cert),'-days','1',
                    '-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost'],check=True,capture_output=True,timeout=15)
    state={'bad_asset':False,'maintenance':True,'block_business':True}
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            code=200
            if self.path=='/':body=b'<html><script type="module" src="/assets/app.js"></script></html>'
            elif self.path=='/assets/app.js':body=b"import {scope} from './scope.js'; console.log(scope);"
            elif self.path=='/assets/scope.js':body=state.get('html_fallback',b'<!doctype html>fallback') if state['bad_asset'] else b"export const scope='synthetic HTTPS fixture';"
            elif self.path=='/api/health':body=json.dumps({'status':'ok','database':{'status':'ok'},'migration':{'status':'ok'},'initialization':{'status':'ok'},'maintenance':'ACTIVE' if state['maintenance'] else 'OPEN','accepting_requests':not state['maintenance']}).encode()
            elif self.path=='/api/records':
                code=503 if state['block_business'] else 200;body=b'{"code":"MAINTENANCE"}'
            else:code=404;body=b'not found'
            self.send_response(code);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def log_message(self,*args):pass
    server=HTTPServer(('127.0.0.1',0),Handler)
    ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);ctx.load_cert_chain(cert,key);server.socket=ctx.wrap_socket(server.socket,server_side=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    yield 'https://localhost:'+str(server.server_port),cert,state
    server.shutdown();server.server_close();thread.join(timeout=3)


def test_tls_smoke_checks_imported_modules_and_latch(tls_fixture):
    origin,cert,state=tls_fixture
    r=run_smoke(origin,cert)
    assert r['status']=='PASS' and r['asset_count']==2 and r['business_e2e'] is False

@pytest.mark.parametrize('flag',['bad_asset','maintenance','block_business'])
def test_smoke_rejects_false_success(tls_fixture,flag):
    origin,cert,state=tls_fixture;state[flag]=not state[flag]
    with pytest.raises(ValueError):run_smoke(origin,cert)


def test_untrusted_tls_does_not_fall_back_to_insecure(tls_fixture):
    origin,cert,state=tls_fixture
    with pytest.raises(URLError):run_smoke(origin)


@pytest.mark.parametrize('html',[b'<html>fallback',b' <HEAD>missing resource',b'<body class="fallback">not javascript'])
def test_html_asset_fallback_without_doctype_is_rejected(tls_fixture,html):
    origin,cert,state=tls_fixture;state['bad_asset']=True;state['html_fallback']=html
    with pytest.raises(ValueError,match='asset missing'):run_smoke(origin,cert)
