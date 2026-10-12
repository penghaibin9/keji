"""Isolated SQLite regressions; CAS transport is synthetic and never connects out."""
from pathlib import Path
import json,shutil,subprocess
from urllib.parse import parse_qs,urlsplit
import pytest
from sqlalchemy import select
from app.adapters.sso_configurable import ConfigurableSsoAdapter
from app.integrations import ADAPTERS
from app.models import AuthSession,Connection,Org,Role,Setting,User
from app.permissions import ALLOWED
from app.routes.sso import _state_key
from conftest import auth,put
from test_r11_three_adapter_p2 import CasTransport

ROOT=Path(__file__).resolve().parents[2]
REASON={'reason':'隔离部署风险回归','basis':'合成测试，不是学校联调'}
COMPAT_MESSAGE='当前浏览器版本过旧，无法使用本系统。请使用最新版 Chrome/Edge，或在 360 浏览器地址栏右侧切换到‘极速模式’。'


@pytest.mark.parametrize('permission',sorted(ALLOWED['school']))
def test_last_admin_cannot_drop_any_school_permission(client2,app2,permission):
    auth(client2,'schooladmin')
    response=put(client2,'/api/roles/role-school',{'expected_version':1,'active':True,
        'permissions':sorted(ALLOWED['school']-{permission}),**REASON})
    assert response.status_code==409,response.text
    assert response.json()['detail']=='不能停用或移除最后一位可用学校管理员'
    with app2.state.sessions() as db:
        role=db.get(Role,'role-school')
        assert set(role.permissions)==ALLOWED['school'] and role.version==1
    for path in ('/api/periods','/api/teachers','/api/organizations','/api/roles'):
        assert client2.get(path).status_code==200


def test_last_admin_cannot_switch_to_incomplete_school_role(client2,app2):
    auth(client2,'schooladmin')
    with app2.state.sessions.begin() as db:
        db.add(Role(id='limited-school',code='limited-school',name='受限学校角色',kind='school',
            permissions=sorted(ALLOWED['school']-{'organization.manage'})))
    response=put(client2,'/api/users/schooladmin',{'expected_version':1,'name':'学校测试管理员',
        'org_id':'school','role_id':'limited-school','active':True,'is_admin':True,**REASON})
    assert response.status_code==409,response.text
    assert client2.get('/api/auth/me').status_code==200
    with app2.state.sessions() as db:
        user=db.get(User,'schooladmin')
        assert user.role_id=='role-school' and user.version==1


def test_reduced_school_role_allowed_when_another_full_admin_survives(client2,app2):
    auth(client2,'schooladmin')
    with app2.state.sessions.begin() as db:
        db.add(Role(id='backup-role',code='backup-role',name='备用管理员角色',kind='school',permissions=sorted(ALLOWED['school'])))
        db.flush()
        db.add(User(id='backup-admin',username='backup-admin',name='备用管理员',org_id='school',role_id='backup-role',
            password_hash=db.get(User,'schooladmin').password_hash,is_admin=True))
    response=put(client2,'/api/roles/role-school',{'expected_version':1,'active':True,
        'permissions':sorted(ALLOWED['school']-{'portal.read'}),**REASON})
    assert response.status_code==200,response.text


@pytest.fixture
def cas_sso(app2,monkeypatch):
    adapter=ConfigurableSsoAdapter();adapter.transport_cls=CasTransport
    monkeypatch.setattr(CasTransport,'calls',[])
    with app2.state.sessions.begin() as db:
        connection=db.scalar(select(Connection).where(Connection.code=='sso'))
        connection.state='CONNECTED';connection.config={'endpoint':'https://idp.example/cas','adapter':{
            'protocol':'cas','login_path':'login','validate_path':'serviceValidate','state_param':'school_state',
            'identity_fields':{'stable_id':'attributes.uid','account':'user','staff_no':'attributes.employeeNo',
                'name':'attributes.name','org_code':'attributes.orgCode','roles':'attributes.role','active':'attributes.active'},
            'active_true_values':['1'],'active_false_values':['0']}}
    ADAPTERS.register_for_test('sso',adapter)
    try:yield
    finally:ADAPTERS.clear()


def start(client):
    response=client.get('/api/auth/sso/start',follow_redirects=False)
    assert response.status_code==302,response.text
    service=parse_qs(urlsplit(response.headers['location']).query)['service'][0]
    return parse_qs(urlsplit(service).query)['school_state'][0]


def callback(client,state):
    return client.get('/api/auth/sso/callback',params={'school_state':state,'ticket':'ST-synthetic'},follow_redirects=False)


@pytest.mark.parametrize('org_code,accepted',[('dept1',True),('college1',True),('school',True),
    ('dept2',False),('college2',False),('unknown',False)])
def test_cas_organization_must_be_local_or_ancestor(client2,app2,cas_sso,monkeypatch,org_code,accepted):
    original=CasTransport.request_text
    monkeypatch.setattr(CasTransport,'request_text',lambda *a,**k:original(*a,**k).replace('<cas:orgCode>dept1</cas:orgCode>',
        '<cas:orgCode>'+org_code+'</cas:orgCode>'))
    response=callback(client2,start(client2))
    assert response.status_code==(303 if accepted else 403),response.text
    if accepted:
        me=client2.get('/api/auth/me').json()
        assert me['user']['id']=='teacher' and me['org']['code']=='dept1' and me['role']['kind']=='teacher'
        assert set(me['permissions'])==ALLOWED['teacher'] and not me['user']['is_admin']
        assert client2.get('/api/records/rec2').status_code==403
        assert client2.cookies.get('nd_test_sso_state') is None
    else:
        assert response.json()['detail']=='学校组织信息与本系统权限范围尚未同步，请联系管理员'
        assert client2.get('/api/auth/me').status_code==401
        with app2.state.sessions() as db:
            assert db.scalar(select(AuthSession)) is None
            assert db.scalar(select(Setting).where(Setting.key.like('ssoid:%'))) is None


@pytest.mark.parametrize('graph',['cycle','too_deep'])
def test_sso_organization_walk_is_bounded(client2,app2,cas_sso,monkeypatch,graph):
    original=CasTransport.request_text
    monkeypatch.setattr(CasTransport,'request_text',lambda *a,**k:original(*a,**k).replace('<cas:orgCode>dept1</cas:orgCode>',
        '<cas:orgCode>school</cas:orgCode>'))
    state=start(client2)
    with app2.state.sessions.begin() as db:
        if graph=='cycle':db.get(Org,'college1').parent_id='dept1'
        else:
            parent='school'
            for i in range(10):
                ident='extra-'+str(i)
                db.add(Org(id=ident,code=ident,name='异常层级',kind='dept',parent_id=parent));db.flush();parent=ident
            db.get(Org,'dept1').parent_id=parent
    response=callback(client2,state)
    assert response.status_code==403,response.text
    assert response.json()['detail']=='学校组织信息与本系统权限范围尚未同步，请联系管理员'
    assert client2.get('/api/auth/me').status_code==401


def test_first_of_two_states_does_not_clear_second_cookie(client2,app2,cas_sso):
    first=start(client2);second=start(client2)
    assert first!=second and client2.cookies.get('nd_test_sso_state')==second
    response=callback(client2,first)
    assert response.status_code==401,response.text
    assert response.json()['detail']=='同一浏览器同时打开了多个登录页，请关闭其他登录页后重试'
    assert not response.headers.get_list('set-cookie')
    assert client2.cookies.get('nd_test_sso_state')==second and not CasTransport.calls
    with app2.state.sessions() as db:
        assert db.get(Setting,_state_key(first)) is None
        assert db.get(Setting,_state_key(second)) is not None
        assert db.scalar(select(AuthSession)) is None
    assert callback(client2,first).status_code==401
    assert client2.cookies.get('nd_test_sso_state')==second
    response=callback(client2,second)
    assert response.status_code==303,response.text
    assert client2.cookies.get('nd_test_sso_state') is None
    assert client2.get('/api/auth/me').status_code==200
    with app2.state.sessions() as db:assert db.get(Setting,_state_key(second)) is None
    client2.cookies.set('nd_test_sso_state',second)
    assert callback(client2,second).status_code==401
    assert len(CasTransport.calls)==1


@pytest.mark.parametrize('invalid',['expired','configuration_changed'])
def test_sso_state_expiry_and_connection_binding_preserved(client2,app2,cas_sso,invalid):
    state=start(client2)
    with app2.state.sessions.begin() as db:
        if invalid=='expired':
            row=db.get(Setting,_state_key(state));row.value={**row.value,'expires':0}
        else:
            connection=db.scalar(select(Connection).where(Connection.code=='sso'))
            connection.config={**connection.config,'endpoint':'https://changed.example/cas'}
    response=callback(client2,state)
    assert response.status_code==401,response.text
    assert client2.cookies.get('nd_test_sso_state')==state
    assert not response.headers.get_list('set-cookie') and not CasTransport.calls
    with app2.state.sessions() as db:
        assert db.get(Setting,_state_key(state)) is None
        assert db.scalar(select(AuthSession)) is None


def test_index_compatibility_message_and_csp_safe_asset(client2):
    response=client2.get('/')
    assert response.status_code==200 and COMPAT_MESSAGE in response.text
    classic='<script src="/assets/compat.js"></script>'
    fallback='<script nomodule src="/assets/compat.js"></script>'
    assert response.text.index(classic)<response.text.index(fallback)<response.text.index('<script type="module"')
    assert "script-src 'self'" in response.headers['content-security-policy']
    script=client2.get('/assets/compat.js')
    assert script.status_code==200 and 'javascript' in script.headers['content-type']
    assert script.text==(ROOT/'frontend/compat.js').read_text(encoding='utf-8')


def test_compatibility_script_handles_missing_features_without_changing_modern_page():
    node=shutil.which('node')
    if not node:pytest.skip('本机未提供脚本运行时')
    script=(ROOT/'frontend/compat.js').read_text(encoding='utf-8')
    check=r'''
const vm=require('node:vm'),assert=require('node:assert/strict');
const source=JSON.parse(process.argv[1]);
for(const missing of ['', 'module', 'hasOwn', 'at', 'fetch', 'Promise']){
 const message={hidden:true,removeAttribute(key){assert.equal(key,'hidden');this.hidden=false;}};
 const body={innerHTML:'original',children:[],appendChild(node){this.children.push(node);}};
 const context=vm.createContext({HTMLScriptElement:{prototype:{noModule:false}},window:{fetch(){},Promise},
  document:{body,getElementById(id){assert.equal(id,'browser-compat');return message;}}});
 const remove={module:'delete HTMLScriptElement.prototype.noModule',hasOwn:'delete Object.hasOwn',
  at:'delete Array.prototype.at',fetch:'delete window.fetch',Promise:'delete window.Promise'};
 if(missing)vm.runInContext(remove[missing],context);
 vm.runInContext(source,context);
 assert.equal(message.hidden,!missing);
 assert.equal(body.innerHTML,missing?'':'original');
 assert.equal(body.children.length,missing?1:0);
}
'''
    result=subprocess.run([node,'-e',check,json.dumps(script)],capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stdout+result.stderr
