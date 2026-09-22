"""Synthetic, isolated merge regressions; never school acceptance evidence."""
import json, socket
from urllib.parse import urlsplit, parse_qs
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient
from conftest import auth, post, put
from app.models import Connection, User, TrainingRecord, Setting
from app.integrations import ADAPTERS, apply_mappings
from app.adapters.contracts import AdapterContractError
from app.adapters.oidc import verify_id_token, login_proof
from app.adapters.http_transport import PinnedHttpsTransport, _PinnedConnection, TransportError
from app.adapters.datahub import ConfigurableDataHubAdapter
from app.adapters.province import ConfigurableProvinceAdapter
from app.adapters.common import matches_value, validate_json_config
from test_r11_three_adapter_p2 import OidcTransport
from test_r11_three_adapter_layer import SsoAdapter, _enable_sso

@pytest.mark.parametrize('claims',[{'nonce':'wrong'},{'iss':'https://wrong.example'},{'aud':'other'},{'exp':0},{'exp':float('nan')},{'iat':float('nan')},{'sub':''},{'at_hash':'wrong'}])
def test_oidc_rejects_invalid_verified_claims(claims):
    jwks=OidcTransport('https://idp.example').request_json('GET','jwks')
    with pytest.raises(AdapterContractError):
        verify_id_token(OidcTransport.signed_token(**claims),issuer='https://idp.example',client_id='client-1',nonce=login_proof('S1','unused')[2],jwks=jwks,access_token='ACCESS')

def test_oidc_signature_tamper_is_rejected():
    token=OidcTransport.signed_token()
    header,payload,sig=token.split('.')
    forged=header+'.'+OidcTransport.encoded(b'{"sub":"admin"}')+'.'+sig
    with pytest.raises(AdapterContractError):
        verify_id_token(forged,issuer='https://idp.example',client_id='client-1',nonce=login_proof('S1','unused')[2],jwks=OidcTransport('https://idp.example').request_json('GET','jwks'),access_token='ACCESS')

@pytest.mark.parametrize('bad',['../secret','%2e%2e/secret','%252e%252e/secret','//evil.example','https://evil.example','x\\secret'])
def test_transport_rejects_path_escape(bad):
    with pytest.raises(ValueError):PinnedHttpsTransport('https://school.example/api').target(bad)

@pytest.mark.parametrize('ip',['127.0.0.1','169.254.169.254','10.0.0.1','::1'])
def test_transport_rejects_private_dns_before_connect(monkeypatch,ip):
    monkeypatch.delenv('ND_INTEGRATION_PRIVATE_HOSTS',raising=False)
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(socket.AF_INET,socket.SOCK_STREAM,6,'',(ip,443))])
    with pytest.raises(TransportError,match='UPSTREAM_ADDRESS_FORBIDDEN'):_PinnedConnection('school.example').connect()

@pytest.mark.parametrize('key',['client_secret','Authorization','X-Api-Key','accessToken','password','private_key'])
def test_config_forbids_secrets(key):
    with pytest.raises(AdapterContractError):validate_json_config({key:'synthetic-sensitive-value'})

def test_success_codes_do_not_equate_false_with_zero():
    assert not matches_value(False,[0,'0',True])
    assert not matches_value(1,[True])
    assert matches_value(0,[0])

class PagedTransport:
    pages=[];calls=[]
    def __init__(self,endpoint):pass
    def request_json(self,method,path,**kwargs):
        self.calls.append(path)
        return self.pages.pop(0)

def pull_config():
    return {'endpoint':'https://hub.example/api','adapter':{'data_types':{'teacher_hr':{'request':{'method':'GET','path':'teachers','query':{'cursor':'${cursor}','page':'${page}','limit':'${limit}'}},'response':{'success_path':'code','success_values':[0],'records_path':'rows','next_cursor_path':'cursor','has_more_path':'more'},'pagination':{'page_size':1,'max_pages':3}}}}}

def test_datahub_accumulates_all_pages_and_nested_field_mapping():
    PagedTransport.calls=[];PagedTransport.pages=[{'code':0,'rows':[{'person':{'no':'J1'}}],'cursor':'c1','more':True},{'code':0,'rows':[{'person':{'no':'J2'}}],'cursor':'c2','more':'false'}]
    adapter=ConfigurableDataHubAdapter();adapter.transport_cls=PagedTransport
    result=adapter.pull(data_type='teacher_hr',mode='FULL',cursor=None,limit=2,config=pull_config(),credential='fixture',timeout_seconds=1)
    assert len(result['records'])==2 and result['next_cursor']=='c2' and result['complete']
    assert 'cursor=c1' in PagedTransport.calls[1]
    connection=Connection(mappings=[{'data_type':'teacher_hr','source':'person.no','target':'staff_no','required':True,'transform':'text','default':None}])
    mapped,errors=apply_mappings(connection,result['records'][0],'teacher_hr')
    assert mapped['staff_no']=='J1' and not errors

def test_datahub_does_not_accept_partial_page_window():
    PagedTransport.pages=[{'code':0,'rows':[{'a':1}],'cursor':'c1','more':True}]
    adapter=ConfigurableDataHubAdapter();adapter.transport_cls=PagedTransport
    with pytest.raises(AdapterContractError,match='PULL_WINDOW_EXCEEDS_LIMIT'):
        adapter.pull(data_type='teacher_hr',mode='FULL',cursor=None,limit=1,config=pull_config(),credential='fixture',timeout_seconds=1)

def test_province_rejection_retains_documented_error_code_only():
    adapter=ConfigurableProvinceAdapter();adapter.transport_cls=PagedTransport
    cfg={'endpoint':'https://province.example','adapter':{'data_types':{'course':{'request':{'method':'POST','path':'send','body':{'key':'${idempotency_key}','data':'${payload}'}},'response':{'accepted_path':'ok','accepted_values':[True],'code_path':'code','error_codes':['E01']}}}}}
    for code,expected in [('E01','E01'),('secret-from-upstream','')]:
        PagedTransport.pages=[{'ok':False,'code':code}]
        with pytest.raises(AdapterContractError) as error:
            adapter.send(data_type='course',payload={'id':'1'},idempotency_key='fixture-1',config=cfg,credential='fixture',timeout_seconds=1)
        assert getattr(error.value,'upstream_code','')==expected

@pytest.mark.parametrize('blocked',['none','external_disabled','local_disabled','org_mismatch'])
def test_sso_keeps_local_authority_and_blocks_disabled_identity(app2,blocked):
    class ExternalAdmin(SsoAdapter):
        def complete_login(self,**kwargs):
            result=super().complete_login(**kwargs);result['external_roles']=['admin','superadmin']
            if blocked=='external_disabled':result['active']=False
            if blocked=='org_mismatch':result['org_code']='dept2'
            return result
    _enable_sso(app2);ADAPTERS.register_for_test('sso',ExternalAdmin())
    if blocked=='local_disabled':
        with Session(app2.state.engine) as db:
            db.get(User,'teacher').active=False;db.commit()
    try:
        with TestClient(app2,raise_server_exceptions=False) as client:
            start=client.get('/api/auth/sso/start',follow_redirects=False)
            state=parse_qs(urlsplit(start.headers['location']).query)['state'][0]
            result=client.get('/api/auth/sso/callback',params={'state':state,'code':'fixture'},follow_redirects=False)
            if blocked=='none':
                assert result.status_code==303,result.text
                me=client.get('/api/auth/me').json()
                assert me['role']['kind']=='teacher' and not me['user']['is_admin'] and me['sso_session']
                client.cookies.set('nd_test_sso_state',state)
                assert client.get('/api/auth/sso/callback',params={'state':state,'code':'fixture'},follow_redirects=False).status_code==401
                assert client.get('/api/auth/me').status_code==200
            else:
                assert result.status_code==403,result.text
                assert client.get('/api/auth/me').status_code==401
                with Session(app2.state.engine) as db:
                    assert not db.scalar(select(Setting).where(Setting.key.like('ssoid:%')))
    finally:ADAPTERS.clear()

def test_income_participants_preview_confirm_idempotence_and_local_preservation(client2,app2):
    auth(client2,'schooladmin')
    c=next(x for x in client2.get('/api/connections').json()['items'] if x['code']=='middle')
    data={'external_key':'ADAPTER-NEW-FACT','staff_no':'J001','event_date':'2026-09-18','project_code':'P-MERGE','project':'合成项目','course_code':'C-MERGE','course':'合成课程','class_code':'B-MERGE','class_name':'合成班级','hours':'2','participants':8,'income':'100.00'}
    mappings=[{'source':key,'target':key,'required':True,'transform':'identity','default':None} for key in data]
    # Existing field transformations are used, no new schema or parallel ledger.
    for mapping in mappings: mapping['transform']='text' if mapping['target']!='participants' else 'int'
    changed=put(client2,'/api/connections/'+c['id'],{'expected_version':c['version'],'config':c['config'],'mappings':mappings,'reason':'隔离合并测试'})
    assert changed.status_code==200,changed.text
    for kind in ['training_income','course_participants']:
        preview=post(client2,'/api/connections/'+c['id']+'/inbound/preview',{'data_type':kind,'records':[data],'reason':'合成入站验证'})
        assert preview.status_code==200,preview.text
        batch=preview.json();assert batch['errors']==0,batch
        confirm=post(client2,'/api/inbound-batches/'+batch['id']+'/confirm',{'expected_version':batch['version'],'reason':'明确确认合成测试批次'})
        assert confirm.status_code==200,confirm.text
    with Session(app2.state.engine) as db:
        rows=list(db.scalars(select(TrainingRecord).where(TrainingRecord.external_key==data['external_key'])))
        assert len(rows)==1 and str(rows[0].income)=='100.00'
    data['income']='999'
    preview=post(client2,'/api/connections/'+c['id']+'/inbound/preview',{'data_type':'training_income','records':[data],'reason':'不得覆盖本地测试'})
    assert preview.status_code==200 and preview.json()['errors']==1,preview.text
    batch=preview.json()
    assert post(client2,'/api/inbound-batches/'+batch['id']+'/confirm',{'expected_version':batch['version'],'reason':'尝试非法覆盖'}).status_code==409
    with Session(app2.state.engine) as db:
        assert str(db.scalar(select(TrainingRecord).where(TrainingRecord.external_key==data['external_key'])).income)=='100.00'
    del data['participants']
    preview=post(client2,'/api/connections/'+c['id']+'/inbound/preview',{'data_type':'training_income','records':[data],'reason':'缺失人次不得猜零'})
    assert preview.json()['errors']==1

def test_profile_rejects_plain_secret_without_partial_writes(client2,app2):
    auth(client2,'schooladmin')
    profile=client2.get('/api/connections/profile-template.json').json()
    profile['connections']['province']['config']['adapter']['headers']={'Authorization':'Bearer synthetic'}
    result=post(client2,'/api/connections/profile-apply',profile)
    assert result.status_code==422,result.text
    with Session(app2.state.engine) as db:
        for code,item in profile['connections'].items():
            conn=db.scalar(select(Connection).where(Connection.code==code))
            assert conn.version==item['expected_version'] and conn.state=='NOT_CONNECTED'

@pytest.mark.parametrize('config',[
    {'protocol':'not-a-protocol'},
    {'data_types':{'course':{'request':{'path':'https://evil.example/api'}}}},
    {'probe':{'method':'TRACE'}},
    {'probe':{'auth':{'mode':'unknown'}}},
    {'data_types':{'course':{'pagination':{'max_pages':10000}}}}
])
def test_profile_parameter_validation_rejects_invalid_protocol_and_paths(config):
    from app.adapters.common import validate_adapter_config
    with pytest.raises(AdapterContractError):validate_adapter_config(config)

def test_hmac_request_signs_timestamp_nonce_idempotency_and_body():
    import hmac,hashlib
    from app.adapters.common import apply_auth,json_bytes
    headers={};query={};body={'course':'C1'}
    ctx=apply_auth(headers,query,body,{'mode':'hmac_sha256','idempotency_name':'Idempotency-Key'}, {'secret':'synthetic-test-secret'},method='POST',path='send',idempotency_key='IDEM-1')
    expected='\n'.join(['POST','send',ctx['timestamp'],ctx['nonce'],hashlib.sha256(json_bytes(body)).hexdigest()])
    assert headers['X-Signature']==hmac.new(b'synthetic-test-secret',expected.encode(),hashlib.sha256).hexdigest()
    assert headers['Idempotency-Key']=='IDEM-1' and len(headers['X-Nonce'])==32

@pytest.mark.parametrize('mode',['basic','bearer','header'])
def test_rest_auth_uses_server_credentials_only(mode):
    from app.adapters.common import apply_auth
    headers={}
    apply_auth(headers,{},None,{'mode':mode},{'token':'test-token','client_id':'test-client','client_secret':'test-secret'},method='GET',path='read')
    assert headers and all('test' not in name for name in headers)

def test_oauth2_client_credentials_reuses_token_but_not_after_secret_rotation():
    from app.adapters.rest import ConfigurableRestBase
    class TokenTransport:
        calls=[]
        def __init__(self,endpoint):pass
        def request_form_json(self,path,**kwargs):
            self.calls.append(kwargs['form'])
            return {'access_token':'synthetic-token','token_type':'Bearer','expires_in':300}
    adapter=ConfigurableRestBase();adapter.transport_cls=TokenTransport
    auth_config={'token_path':'token'}
    for secret in ['a','a','b']:
        assert adapter._oauth2_token('https://school.example',auth_config,{'client_id':'client','client_secret':secret},10)=='synthetic-token'
    assert len(TokenTransport.calls)==2

def test_anonymous_health_probe_is_not_connection_proof():
    from app.adapters.rest import ConfigurableRestBase
    adapter=ConfigurableRestBase()
    with pytest.raises(AdapterContractError,match='AUTHENTICATED_PROBE_REQUIRED'):
        adapter._probe(config={'endpoint':'https://school.example','adapter':{'probe':{'path':'health','success_path':'ok'}}},credential='fixture',timeout_seconds=1)

