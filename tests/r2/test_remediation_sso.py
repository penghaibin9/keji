"""统一认证简化入口保留原校验；本文件不调用学校网络。"""
from types import SimpleNamespace
from urllib.parse import urlsplit, parse_qs
import pytest
from sqlalchemy import select, func
from app.models import Connection, Setting, AuthSession
from app.integrations import ADAPTERS, credential_fingerprint, transport_kwargs
from app.adapters.sso_configurable import ConfigurableSsoAdapter
from app.adapters.contracts import AdapterContractError
from conftest import auth, post
from test_integration_workspace import setup_trial, connection_id, make_draft, sso_config, TrialAdapter


def test_trial_uses_formal_callback_without_business_session(client2,app2,monkeypatch):
    ident,action,state=setup_trial(client2,app2,monkeypatch)
    session=client2.cookies.get(app2.state.settings.cookie_name)
    response=client2.get('/api/auth/sso/callback',params={'state':state,'ticket':'ST-fixture'},follow_redirects=False)
    assert response.status_code==303,response.text
    assert response.headers['location'].endswith('/#sso?tab=maintenance')
    assert client2.cookies.get(app2.state.settings.cookie_name)==session
    with app2.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(AuthSession))==1
        assert not db.scalar(select(Setting).where(Setting.key.like('ssoid:%')))
    assert post(client2,f'/api/connections/{ident}/draft/publish',action).status_code==409
    assert client2.get('/api/auth/sso/callback',params={'state':state,'ticket':'ST-fixture'}).status_code==401


def test_prepare_copies_active_config_but_never_overwrites_a_stale_draft(client2,app2):
    auth(client2,'schooladmin');ident=connection_id(client2)
    with app2.state.sessions.begin() as db:
        obj=db.get(Connection,ident);obj.config=sso_config();obj.state='CONNECTED';version=obj.version
    result=post(client2,f'/api/connections/{ident}/draft/prepare',{'expected_version':version,'reason':'准备隔离试登录'})
    assert result.status_code==200,result.text
    with app2.state.sessions.begin() as db:
        obj=db.get(Connection,ident);obj.version+=1;new_version=obj.version
        row=db.get(Setting,'integration.draft:'+ident);before=dict(row.value)
        assert obj.state=='CONNECTED'
    result=post(client2,f'/api/connections/{ident}/draft/prepare',{'expected_version':new_version,'reason':'核对旧草稿'})
    assert result.status_code==409
    with app2.state.sessions() as db:assert db.get(Setting,'integration.draft:'+ident).value==before


def test_credentialless_cas_uses_exact_same_service_and_other_protocols_stay_closed(monkeypatch):
    calls=[]
    class Transport:
        def __init__(self,endpoint):self.endpoint=endpoint
        def target(self,path):return self.endpoint+path
        def request_text(self,method,path,**kwargs):
            calls.append(parse_qs(urlsplit(path).query))
            return '<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas"><cas:authenticationSuccess><cas:user>J001</cas:user></cas:authenticationSuccess></cas:serviceResponse>'
    adapter=ConfigurableSsoAdapter();adapter.transport_cls=Transport
    config={'endpoint':'https://synthetic.invalid','secret_env':'ND_EMPTY_CAS','adapter':{'protocol':'cas','login_path':'/login','validate_path':'/serviceValidate','identity_fields':{'staff_no':'user','name':'user'},'active_default':True}}
    kwargs={'config':config,'credential':'','timeout_seconds':1,'callback_url':'https://local.invalid/api/auth/sso/callback'}
    login=adapter.build_login_url(state='one-time-fixture',**kwargs)
    service=parse_qs(urlsplit(login['redirect_url']).query)['service'][0]
    identity=adapter.complete_login(callback={'state':'one-time-fixture','ticket':'ST-fixture'},**kwargs)
    assert identity['staff_no']=='J001' and calls[0]['service']==[service]
    monkeypatch.setattr(ADAPTERS,'_items',{'sso':adapter});monkeypatch.setattr(ADAPTERS,'production',True)
    monkeypatch.setattr(ADAPTERS,'_endpoints',{'sso':'https://synthetic.invalid'})
    monkeypatch.setattr(ADAPTERS,'_credential_envs',{'sso':'ND_EMPTY_CAS'});monkeypatch.delenv('ND_EMPTY_CAS',raising=False)
    connection=SimpleNamespace(code='sso',config=config)
    assert credential_fingerprint(connection) and transport_kwargs(connection,ADAPTERS)['credential']==''
    for key,value in [('endpoint','https://unapproved.invalid'),('secret_env','ND_UNAPPROVED_CAS')]:
        with pytest.raises(RuntimeError,match='NOT_PINNED'):
            transport_kwargs(SimpleNamespace(code='sso',config={**config,key:value}),ADAPTERS)
    monkeypatch.setattr(ADAPTERS,'_items',{'sso':TrialAdapter()})
    assert credential_fingerprint(connection) is None
    with pytest.raises(AdapterContractError):adapter.build_login_url(state='fixture',**{**kwargs,'config':{**config,'adapter':{'protocol':'oidc'}}})


def test_expired_trial_browser_error_has_return_path(client2):
    response=client2.get('/api/auth/sso/implementation-callback',headers={'Accept':'text/html'})
    assert response.status_code==401 and '返回统一登录维护页' in response.text
    assert '没有创建业务登录会话' in response.text


def test_trial_callback_rejects_changed_active_revision(client2,app2,monkeypatch):
    ident,action,state=setup_trial(client2,app2,monkeypatch)
    with app2.state.sessions.begin() as db:
        obj=db.get(Connection,ident);obj.version+=1
        obj.config={'owner':'另一位管理员已更新'}
    response=client2.get('/api/auth/sso/callback',params={'state':state,'ticket':'ST-fixture'},follow_redirects=False)
    assert response.status_code==409,response.text
    with app2.state.sessions() as db:
        assert 'check_id' not in db.get(Setting,'integration.draft:'+ident).value
        assert db.get(Connection,ident).config=={'owner':'另一位管理员已更新'}


def test_shared_callback_accepts_custom_trial_state_and_preserves_live_connection(client2,app2,monkeypatch):
    ident,action,state=setup_trial(client2,app2,monkeypatch)
    config=sso_config();config['adapter']['state_param']='request_nonce'
    action=make_draft(client2,ident,config)
    with app2.state.sessions.begin() as db:
        obj=db.get(Connection,ident);obj.state='CONNECTED';obj.config=sso_config()
        before=(obj.version,dict(obj.config))
    response=post(client2,f'/api/connections/{ident}/draft/login-test',action)
    assert response.status_code==200,response.text
    state=parse_qs(urlsplit(response.json()['redirect_url']).query)['state'][0]
    session=client2.cookies.get(app2.state.settings.cookie_name)
    response=client2.get('/api/auth/sso/callback',params={'request_nonce':state,'ticket':'ST-fixture'},follow_redirects=False)
    assert response.status_code==303,response.text
    assert client2.cookies.get(app2.state.settings.cookie_name)==session
    with app2.state.sessions() as db:
        obj=db.get(Connection,ident)
        assert obj.state=='CONNECTED' and (obj.version,obj.config)==before
        assert db.scalar(select(func.count()).select_from(AuthSession))==1


def test_pending_trial_cookie_does_not_capture_normal_login(client2,app2,monkeypatch):
    ident,action,trial_state=setup_trial(client2,app2,monkeypatch)
    with app2.state.sessions.begin() as db:
        obj=db.get(Connection,ident);obj.state='CONNECTED';obj.config=sso_config()
    response=client2.get('/api/auth/sso/start',follow_redirects=False)
    assert response.status_code==302,response.text
    state=parse_qs(urlsplit(response.headers['location']).query)['state'][0]
    assert state!=trial_state
    response=client2.get('/api/auth/sso/callback',params={'state':state,'ticket':'ST-fixture'},follow_redirects=False)
    assert response.status_code==303,response.text
    assert client2.get('/api/auth/me').json()['user']['id']=='teacher'
    with app2.state.sessions() as db:
        assert 'check_id' not in db.get(Setting,'integration.draft:'+ident).value
