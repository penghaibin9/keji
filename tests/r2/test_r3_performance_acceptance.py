import importlib.util, json, os, sys
from pathlib import Path
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('performance_acceptance',ROOT/'scripts/performance_acceptance.py')
pa=importlib.util.module_from_spec(spec);sys.modules[spec.name]=pa;spec.loader.exec_module(pa)


def test_percentile_interpolates_deterministically():
    assert pa.percentile([1,2,3,4],50)==2.5
    assert pa.percentile([1,2,3,4],95)==3.8499999999999996
    assert pa.percentile([],95) is None


def test_default_business_workload_is_read_only_and_matches_pdf_threshold_classes():
    assert {x[0] for x in pa.DEFAULT_PATHS}=={'records','todos','assessments','statistics'}
    assert all(path.startswith('/api/') for _,path,_ in pa.DEFAULT_PATHS)
    assert dict((label,kind) for label,_,kind in pa.DEFAULT_PATHS)['statistics']=='complex'
    assert pa.ORDINARY_LIMIT_S==3.0 and pa.COMPLEX_LIMIT_S==5.0


def test_credentials_are_unique_and_not_written_to_summary(tmp_path):
    p=tmp_path/'users.csv';p.write_text('username,password\nu1,Secret-123456\nu2,Secret-abcdef\n',encoding='utf-8')
    os.chmod(p,0o600)
    users=pa.load_users(p)
    assert users==[('u1','Secret-123456'),('u2','Secret-abcdef')]
    report={'summary':pa.summary([pa.Sample('p','x',200,0.1,True)])}
    text=json.dumps(report)
    assert 'Secret-' not in text


def test_duplicate_credentials_rejected(tmp_path):
    p=tmp_path/'users.csv';p.write_text('username,password\nu1,a\nu1,b\n',encoding='utf-8');os.chmod(p,0o600)
    try:pa.load_users(p)
    except SystemExit as e: assert '重复账号' in str(e)
    else: raise AssertionError('duplicate usernames must be rejected')


def test_business_gate_applies_3s_and_5s_p95(monkeypatch):
    args=SimpleNamespace(business_concurrency=2,business_cycles=1,base_url='http://lab',timeout=5)
    sessions=[pa.SessionCtx('u1',object(),''),pa.SessionCtx('u2',object(),'')]
    def fake_http(opener,base,path,**kwargs):
        # statistics may take 4s and still pass; ordinary endpoints remain below 3s.
        return 200,(4.0 if path=='/api/statistics' else 2.0),{},''
    monkeypatch.setattr(pa,'http',fake_http)
    gate,samples=pa.run_business_gate(args,sessions)
    assert gate['pass'] is True
    assert gate['endpoints']['statistics']['threshold_p95_s']==5.0
    assert gate['endpoints']['records']['threshold_p95_s']==3.0
    assert len(samples)==8


def test_business_gate_fails_slow_ordinary_endpoint(monkeypatch):
    args=SimpleNamespace(business_concurrency=1,business_cycles=1,base_url='http://lab',timeout=5)
    sessions=[pa.SessionCtx('u1',object(),'')]
    def fake_http(opener,base,path,**kwargs):
        return 200,(3.2 if path.startswith('/api/records') else 0.1),{},''
    monkeypatch.setattr(pa,'http',fake_http)
    gate,_=pa.run_business_gate(args,sessions)
    assert gate['pass'] is False
    assert gate['endpoints']['records']['pass'] is False


def test_http_lab_end_to_end_produces_evidence_but_never_formal_pass(tmp_path):
    import threading
    from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
    class H(BaseHTTPRequestHandler):
        def log_message(self,*a): pass
        def do_POST(self):
            if self.path!='/api/auth/login':self.send_response(404);self.end_headers();return
            length=int(self.headers.get('content-length','0')); self.rfile.read(length)
            self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Set-Cookie','nd_session=abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMN1234567890; Path=/; HttpOnly');self.end_headers();self.wfile.write(b'{"authenticated":true}')
        def do_GET(self):
            if self.path=='/api/auth/me':
                if 'nd_session=' not in self.headers.get('Cookie',''):self.send_response(401);self.end_headers();return
                self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(b'{"csrf":"lab"}');return
            if self.path.startswith('/api/'):
                self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(b'{}');return
            self.send_response(404);self.end_headers()
    srv=ThreadingHTTPServer(('127.0.0.1',0),H);thread=threading.Thread(target=srv.serve_forever,daemon=True);thread.start()
    try:
        users=tmp_path/'users.csv';users.write_text('username,password\nu1,p1\nu2,p2\n',encoding='utf-8');os.chmod(users,0o600)
        out=tmp_path/'result.json'
        rc=pa.main(['--base-url',f'http://127.0.0.1:{srv.server_port}','--users-csv',str(users),'--output',str(out),'--allow-http-lab','--login-concurrency','2','--online-target','2','--online-verify-count','2','--business-concurrency','2','--business-cycles','1'])
        data=json.loads(out.read_text(encoding='utf-8'))
        assert rc==2 and data['tls_verified'] is False and data['overall_pass'] is False
        assert data['login_gate']['pass'] and data['online_session_gate']['pass'] and data['business_gate']['pass']
        assert 'p1' not in out.read_text(encoding='utf-8') and 'p2' not in out.read_text(encoding='utf-8')
    finally:
        srv.shutdown();srv.server_close();thread.join(timeout=2)
