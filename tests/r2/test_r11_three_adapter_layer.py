from urllib.parse import urlsplit, parse_qs
from sqlalchemy.orm import Session
from sqlalchemy import select
from conftest import auth, post
from app.models import Connection, AuthSession, Audit
from app.integrations import ADAPTERS, AdapterRegistry
from app.adapters.contracts import AdapterContractError, normalize_sso_identity
from app.adapters.http_transport import PinnedHttpsTransport


class SsoAdapter:
    adapter_id='unit.sso.contract'
    def probe(self, **kwargs):
        return {'authenticated':True,'tls_verified':True,'protocol_verified':True}
    def build_login_url(self, state, callback_url, **kwargs):
        return {'redirect_url':f'https://idp.example/login?state={state}&redirect_uri={callback_url}'}
    def complete_login(self, callback, **kwargs):
        return {'stable_id':'PERSON-J001','account':'teacher','staff_no':'J001','name':'测试教师一',
                'org_code':'dept1','external_roles':['teacher'],'active':True}
    def build_logout_url(self, post_logout_redirect_uri, **kwargs):
        return {'redirect_url':'https://idp.example/logout?return='+post_logout_redirect_uri}


def _enable_sso(app2):
    with Session(app2.state.engine) as db:
        c=db.scalar(select(Connection).where(Connection.code=='sso'))
        c.state='CONNECTED';c.config={};db.commit()
    ADAPTERS.register_for_test('sso',SsoAdapter())


def test_sso_identity_contract_is_strict():
    value=normalize_sso_identity({'stable_id':'A','account':'teacher','staff_no':'J001','name':'张三','org_code':'dept1','external_roles':['teacher','teacher'],'active':True})
    assert value['external_roles']==['teacher'] and value['active'] is True
    try:normalize_sso_identity({'name':'张三','active':'true'})
    except AdapterContractError as exc:assert exc.code=='SSO_ACTIVE_MUST_BE_BOOL'
    else:raise AssertionError('string boolean must fail')


def test_pinned_transport_rejects_non_https_and_cross_origin():
    try:PinnedHttpsTransport('http://example.invalid/api')
    except ValueError:pass
    else:raise AssertionError('http must fail')
    t=PinnedHttpsTransport('https://school.example/api/')
    assert t.target('teachers').startswith('https://school.example/')
    for bad in ('https://evil.example/x','//evil.example/x'):
        try:t.target(bad)
        except ValueError:pass
        else:raise AssertionError('cross-origin target must fail')


def test_sso_status_is_fail_closed_without_real_connection(client2):
    r=client2.get('/api/auth/sso/status');assert r.status_code==200
    assert r.json()=={'available':False,'connection_state':'NOT_CONNECTED'}
    r=client2.get('/api/auth/sso/start');assert r.status_code==503


def test_sso_start_callback_creates_local_session_and_keeps_local_permissions(app2):
    _enable_sso(app2)
    try:
        from fastapi.testclient import TestClient
        with TestClient(app2,raise_server_exceptions=False) as c:
            r=c.get('/api/auth/sso/status');assert r.json()['available'] is True
            start=c.get('/api/auth/sso/start',follow_redirects=False);assert start.status_code==302
            location=start.headers['location'];query=parse_qs(urlsplit(location).query);state=query['state'][0]
            callback=c.get('/api/auth/sso/callback?state='+state+'&code=fixture',follow_redirects=False)
            assert callback.status_code==303 and callback.headers['location']=='http://testserver/'
            me=c.get('/api/auth/me');assert me.status_code==200,me.text
            body=me.json();assert body['user']['username']=='teacher' and body['role']['kind']=='teacher' and body['org']['code']=='dept1'
    finally:ADAPTERS.clear()


def test_sso_state_mismatch_rejected(app2):
    _enable_sso(app2)
    try:
        from fastapi.testclient import TestClient
        with TestClient(app2,raise_server_exceptions=False) as c:
            c.get('/api/auth/sso/start',follow_redirects=False)
            bad=c.get('/api/auth/sso/callback?state=wrong&code=fixture',follow_redirects=False)
            assert bad.status_code==401
            with Session(app2.state.engine) as db:
                row=db.scalar(select(Audit).where(Audit.action=='统一认证登录拒绝').order_by(Audit.created_at.desc()))
                assert row is not None and row.result=='DENIED'
    finally:ADAPTERS.clear()


def test_sso_logout_clears_local_cookie_even_if_remote_url_is_only_advice(app2):
    _enable_sso(app2)
    try:
        from fastapi.testclient import TestClient
        with TestClient(app2,raise_server_exceptions=False) as c:
            start=c.get('/api/auth/sso/start',follow_redirects=False)
            state=parse_qs(urlsplit(start.headers['location']).query)['state'][0]
            assert c.get('/api/auth/sso/callback?state='+state+'&code=fixture',follow_redirects=False).status_code==303
            me=c.get('/api/auth/me');csrf=me.json()['csrf'];c.headers['x-csrf-token']=csrf;c.headers['origin']='http://testserver'
            out=post(c,'/api/auth/sso/logout',{},key='sso-logout-001');assert out.status_code==200,out.text
            assert out.json()['logged_out'] is True and out.json()['sso_logout_url'].startswith('https://idp.example/logout')
            assert c.get('/api/auth/me').status_code==401
    finally:ADAPTERS.clear()


def test_production_registry_requires_complete_wire_contract_for_each_connection():
    class ProbeOnly:
        adapter_id='unit.incomplete'
        def probe(self, **kwargs): return {'authenticated':True,'tls_verified':True,'protocol_verified':True}
    for code in ('sso','middle','province'):
        registry=AdapterRegistry()
        try:
            registry.register_production(code,ProbeOnly(),endpoint='https://school.example/api',credential_env='ND_TEST_SECRET')
        except ValueError as exc:
            assert str(exc)=='INVALID_PRODUCTION_ADAPTER_CONTRACT'
        else:
            raise AssertionError(code+' incomplete production adapter must be rejected')
