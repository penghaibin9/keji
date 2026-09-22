import json, base64, time
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes
from app.adapters.oidc import login_proof
from urllib.parse import urlsplit, parse_qs

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.contracts import AdapterContractError
from app.adapters.sso_configurable import ConfigurableSsoAdapter
from app.adapters.datahub import ConfigurableDataHubAdapter
from app.adapters.province import ConfigurableProvinceAdapter
from app.adapters.common import validate_json_config
from app.models import Connection, Setting
from conftest import auth, post


class CasTransport:
    calls=[]
    def __init__(self, base_url): self.base=base_url.rstrip('/')+'/'
    def target(self,path): return self.base+path.lstrip('/')
    def request_text(self, method, path, **kwargs):
        self.calls.append((method,path,kwargs))
        return '''<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
          <cas:authenticationSuccess><cas:user>teacher</cas:user><cas:attributes>
          <cas:uid>SUB-J001</cas:uid><cas:employeeNo>J001</cas:employeeNo><cas:name>张三</cas:name>
          <cas:orgCode>dept1</cas:orgCode><cas:role>teacher</cas:role><cas:active>1</cas:active>
          </cas:attributes></cas:authenticationSuccess></cas:serviceResponse>'''


class OidcTransport:
    calls=[]
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    @staticmethod
    def encoded(value):
        return base64.urlsafe_b64encode(value).decode().rstrip('=')
    @classmethod
    def signed_token(cls, **changes):
        claims={'iss':'https://idp.example','aud':'client-1','sub':'SUB-1','exp':int(time.time())+300,'iat':int(time.time()),'nonce':login_proof('S1','unused')[2],**changes}
        value=cls.encoded(json.dumps({'alg':'RS256','kid':'test'}).encode())+'.'+cls.encoded(json.dumps(claims).encode())
        return value+'.'+cls.encoded(cls.key.sign(value.encode(),padding.PKCS1v15(),hashes.SHA256()))
    def __init__(self, base_url): self.base=base_url.rstrip('/')+'/'
    def target(self,path): return self.base+path.lstrip('/')
    def request_form_json(self,path,form,headers=None,**kwargs):
        self.calls.append(('FORM',path,dict(form),dict(headers or {})))
        return {'access_token':'ACCESS','token_type':'Bearer','expires_in':300,'id_token':self.signed_token()}
    def request_json(self,method,path,headers=None,payload=None,**kwargs):
        self.calls.append((method,path,dict(headers or {}),payload))
        if path=='jwks':
            numbers=self.key.public_key().public_numbers()
            return {'keys':[{'kid':'test','kty':'RSA','n':self.encoded(numbers.n.to_bytes(256,'big')),'e':self.encoded(numbers.e.to_bytes(3,'big'))}]}
        if path=='/.well-known/openid-configuration':
            return {'authorization_endpoint':self.base+'authorize','token_endpoint':self.base+'token'}
        return {'sub':'SUB-1','preferred_username':'teacher','employee_no':'J001','name':'测试教师一','org':{'code':'dept1'},'roles':['teacher'],'enabled':True}


class JsonTransport:
    calls=[]
    response={}
    def __init__(self, base_url): self.base=base_url
    def request_json(self,method,path,headers=None,payload=None,**kwargs):
        self.calls.append((method,path,dict(headers or {}),payload))
        return self.response
    def request_form_json(self,*args,**kwargs):
        raise AssertionError('not expected')


def test_public_institution_code_expands_in_authenticated_rest_probe():
    JsonTransport.calls=[];JsonTransport.response={'code':0}
    adapter=ConfigurableDataHubAdapter();adapter.transport_cls=JsonTransport
    cfg={'endpoint':'https://hub.example/api','adapter':{
        'public_parameters':{'institution_code':'HNZY001'},
        'probe':{'method':'GET','path':'health','query':{'institutionCode':'${institution_code}'},
                 'auth':{'mode':'bearer','credential_key':'token'},'success_path':'code','success_values':[0]}}}
    result=adapter.probe(config=cfg,credential='TOKEN',timeout_seconds=10)
    method,path,headers,payload=JsonTransport.calls[-1]
    assert result['authenticated'] is True
    assert method=='GET' and parse_qs(urlsplit(path).query)['institutionCode']==['HNZY001']
    assert headers['Authorization']=='Bearer TOKEN' and payload is None
    assert 'TOKEN' not in path and cfg['adapter']['public_parameters']=={'institution_code':'HNZY001'}


def test_public_institution_code_expands_in_datahub_pull_request():
    JsonTransport.calls=[];JsonTransport.response={'code':0,'data':{'rows':[],'hasMore':False}}
    adapter=ConfigurableDataHubAdapter();adapter.transport_cls=JsonTransport
    cfg={'endpoint':'https://hub.example/api','adapter':{
        'public_parameters':{'institution_code':'HNZY001'},
        'data_types':{'teacher_hr':{'request':{'method':'GET','path':'teachers',
            'query':{'institutionCode':'${institution_code}','limit':'${limit}'},
            'auth':{'mode':'bearer','credential_key':'token'}},
            'response':{'success_path':'code','success_values':[0],'records_path':'data.rows','has_more_path':'data.hasMore'}}}}}
    adapter.pull(data_type='teacher_hr',mode='FULL',cursor=None,limit=1000,config=cfg,credential='TOKEN',timeout_seconds=10)
    method,path,headers,payload=JsonTransport.calls[-1]
    query=parse_qs(urlsplit(path).query)
    assert method=='GET' and query['institutionCode']==['HNZY001'] and query['limit']==['1000']
    assert headers['Authorization']=='Bearer TOKEN' and payload is None
    assert 'TOKEN' not in path and cfg['adapter']['public_parameters']=={'institution_code':'HNZY001'}


def test_public_institution_code_expands_in_province_send_request():
    JsonTransport.calls=[];JsonTransport.response={'success':True,'code':'0'}
    adapter=ConfigurableProvinceAdapter();adapter.transport_cls=JsonTransport
    cfg={'endpoint':'https://province.example/api','adapter':{
        'public_parameters':{'institution_code':'HNZY001'},
        'data_types':{'training_project':{'request':{'method':'POST','path':'projects/report',
            'body':{'institutionCode':'${institution_code}','payload':'${payload}','requestId':'${idempotency_key}'},
            'auth':{'mode':'header','header':'X-Token','credential_key':'token'}},
            'response':{'accepted_path':'success','accepted_values':[True],'code_path':'code'}}}}}
    adapter.send(data_type='training_project',payload={'code':'P1'},idempotency_key='IDEM1',config=cfg,credential='TOKEN',timeout_seconds=10)
    method,path,headers,payload=JsonTransport.calls[-1]
    assert method=='POST' and path=='projects/report'
    assert headers['X-Token']=='TOKEN'
    assert payload=={'institutionCode':'HNZY001','payload':{'code':'P1'},'requestId':'IDEM1'}
    assert cfg['adapter']['public_parameters']=={'institution_code':'HNZY001'}


def test_config_validator_rejects_embedded_secret_material():
    validate_json_config({'auth':{'credential_key':'client_secret'}})
    with pytest.raises(AdapterContractError) as exc:
        validate_json_config({'client_secret':'actual-secret-must-not-be-in-db'})
    assert exc.value.code=='SECRET_MATERIAL_FORBIDDEN_IN_CONFIG'


def test_configurable_cas_builds_stateful_service_and_parses_identity():
    adapter=ConfigurableSsoAdapter();adapter.transport_cls=CasTransport
    cfg={'endpoint':'https://idp.example/cas','adapter':{
        'protocol':'cas','login_path':'login','validate_path':'serviceValidate','state_param':'state',
        'identity_fields':{'stable_id':'attributes.uid','account':'user','staff_no':'attributes.employeeNo','name':'attributes.name','org_code':'attributes.orgCode','roles':'attributes.role','active':'attributes.active'},
        'active_true_values':['1'],'active_false_values':['0']}}
    url=adapter.build_login_url(state='STATE123',callback_url='https://app.example/api/auth/sso/callback',config=cfg,credential='unused',timeout_seconds=10)['redirect_url']
    q=parse_qs(urlsplit(url).query);service=q['service'][0]
    assert 'state=STATE123' in service
    identity=adapter.complete_login(callback={'state':'STATE123','ticket':'ST-1'},callback_url='https://app.example/api/auth/sso/callback',config=cfg,credential='unused',timeout_seconds=10)
    assert identity=={'stable_id':'SUB-J001','account':'teacher','staff_no':'J001','name':'张三','org_code':'dept1','external_roles':['teacher'],'active':True}
    assert 'state%3DSTATE123' in CasTransport.calls[-1][1]


def test_configurable_oidc_uses_code_exchange_and_userinfo():
    adapter=ConfigurableSsoAdapter();adapter.transport_cls=OidcTransport
    cfg={'endpoint':'https://idp.example','adapter':{
        'protocol':'oidc','authorize_path':'authorize','token_path':'token','userinfo_path':'userinfo','scope':'openid profile','issuer':'https://idp.example','jwks_path':'jwks',
        'identity_fields':{'stable_id':'sub','account':'preferred_username','staff_no':'employee_no','name':'name','org_code':'org.code','roles':'roles','active':'enabled'}}}
    cred=json.dumps({'client_id':'client-1','client_secret':'secret-1'})
    url=adapter.build_login_url(state='S1',callback_url='https://app.example/api/auth/sso/callback',config=cfg,credential=cred,timeout_seconds=10)['redirect_url']
    assert parse_qs(urlsplit(url).query)['client_id']==['client-1']
    identity=adapter.complete_login(callback={'state':'S1','code':'CODE'},callback_url='https://app.example/api/auth/sso/callback',config=cfg,credential=cred,timeout_seconds=10)
    assert identity['stable_id']=='SUB-1' and identity['org_code']=='dept1' and identity['active'] is True
    assert any(call[0]=='FORM' and call[1]=='token' for call in OidcTransport.calls)
    assert next(call for call in reversed(OidcTransport.calls) if call[0]=='FORM')[2]['code_verifier']==login_proof('S1','secret-1')[0]


def test_datahub_adapter_is_driven_by_fillable_paths_and_fields():
    JsonTransport.calls=[];JsonTransport.response={'code':0,'data':{'rows':[{'teacherNo':'J001'}],'cursor':'NEXT','hasMore':False}}
    adapter=ConfigurableDataHubAdapter();adapter.transport_cls=JsonTransport
    cfg={'endpoint':'https://hub.example/api','adapter':{
        'probe':{'method':'GET','path':'health','auth':{'mode':'bearer','credential_key':'token'},'success_path':'code','success_values':[0]},
        'data_types':{'teacher_hr':{'request':{'method':'GET','path':'teachers','query':{'cursor':'${cursor}','limit':'${limit}','mode':'${mode}'},'auth':{'mode':'bearer','credential_key':'token'}},
            'response':{'success_path':'code','success_values':[0],'records_path':'data.rows','next_cursor_path':'data.cursor','has_more_path':'data.hasMore'}}}}}
    result=adapter.pull(data_type='teacher_hr',mode='INCREMENTAL',cursor='C1',limit=1000,config=cfg,credential='TOKEN',timeout_seconds=10)
    assert result['records']==[{'teacherNo':'J001'}] and result['next_cursor']=='NEXT'
    method,path,headers,payload=JsonTransport.calls[-1]
    assert method=='GET' and 'cursor=C1' in path and 'limit=1000' in path and headers['Authorization']=='Bearer TOKEN' and payload is None


def test_province_adapter_wraps_payload_and_returns_only_safe_ack():
    JsonTransport.calls=[];JsonTransport.response={'success':True,'code':'0','data':{'receipt':'R-001'}}
    adapter=ConfigurableProvinceAdapter();adapter.transport_cls=JsonTransport
    cfg={'endpoint':'https://province.example/api','adapter':{
        'probe':{'method':'GET','path':'health','success_path':'success','success_values':[True]},
        'data_types':{'training_project':{'request':{'method':'POST','path':'projects/report','body':{'payload':'${payload}','requestId':'${idempotency_key}'},'auth':{'mode':'header','header':'X-Token','credential_key':'token'}},
            'response':{'accepted_path':'success','accepted_values':[True],'code_path':'code','receipt_id_path':'data.receipt'}}}}}
    result=adapter.send(data_type='training_project',payload={'code':'P1'},idempotency_key='IDEM1',config=cfg,credential='TOKEN',timeout_seconds=10)
    assert result=={'accepted':True,'code':'0','receipt_id':'R-001'}
    assert JsonTransport.calls[-1][3]=={'payload':{'code':'P1'},'requestId':'IDEM1'}


def test_three_connection_profile_template_can_be_downloaded_and_reapplied(client2):
    auth(client2,'schooladmin')
    r=client2.get('/api/connections/profile-template.json');assert r.status_code==200,r.text
    profile=r.json();assert profile['format']=='YUEKE_R11_THREE_INTEGRATIONS_V2'
    assert set(profile['connections'])=={'sso','middle','province'}
    profile['reason']='R11 P2 参数模板回写测试';profile['basis']='隔离测试，不包含真实Secret'
    out=post(client2,'/api/connections/profile-apply',profile,key='profile-p2-apply')
    assert out.status_code==200,out.text
    assert out.json()['applied'] is True


def test_sso_stable_subject_binding_is_persisted_after_first_verified_login(app2):
    from app.integrations import ADAPTERS
    class LocalSsoAdapter:
        adapter_id='unit.sso.p2.binding'
        def probe(self, **kwargs): return {'authenticated':True,'tls_verified':True,'protocol_verified':True}
        def build_login_url(self, state, callback_url, **kwargs): return {'redirect_url':'https://idp.example/login?state='+state}
        def complete_login(self, callback, **kwargs): return {'stable_id':'PERSON-J001','account':'teacher','staff_no':'J001','name':'测试教师一','org_code':'dept1','external_roles':['teacher'],'active':True}
    with Session(app2.state.engine) as db:
        c=db.scalar(select(Connection).where(Connection.code=='sso'));c.state='CONNECTED';c.config={};db.commit()
    ADAPTERS.register_for_test('sso',LocalSsoAdapter())
    try:
        from fastapi.testclient import TestClient
        with TestClient(app2,raise_server_exceptions=False) as c:
            start=c.get('/api/auth/sso/start',follow_redirects=False)
            state=parse_qs(urlsplit(start.headers['location']).query)['state'][0]
            assert c.get('/api/auth/sso/callback?state='+state+'&code=fixture',follow_redirects=False).status_code==303
        with Session(app2.state.engine) as db:
            rows=list(db.scalars(select(Setting).where(Setting.key.like('ssoid:%'))))
            assert len(rows)==1 and rows[0].value['user_id']
            assert 'stable_id' not in rows[0].value
    finally:
        ADAPTERS.clear()
