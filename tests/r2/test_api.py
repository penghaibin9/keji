import io,uuid
from datetime import timedelta
from pathlib import Path
import pytest
from sqlalchemy import select,func,event,delete
from PIL import Image
from app.models import *
from app.core import digest
from app.config import Settings
from app.passwords import verify_password
from conftest import auth,post,put
from support import FIXTURE_PASSWORD
REASON={'reason':'隔离流程核验','basis':'合成测试案例，不是学校验收'}

def png():
    out=io.BytesIO();Image.new('RGB',(16,16)).save(out,format='PNG');return out.getvalue()

def qual(client):
    r=post(client,'/api/qualifications',{'teacher_id':'teacher','category':'职业资格','name':'隔离证书','certificate_no':str(uuid.uuid4()),'issuer':'合成发证单位','obtained':'2026-01-01','expires':'2026-12-31',**REASON})
    assert r.status_code==200,r.text
    return r.json()

def rule(client,kind='assessment',weight=100):
    r=post(client,'/api/rules',{'kind':kind,'name':'隔离规则','period_id':'period2026','config':{'components':[{'key':'hours','label':'授课学时','source':'hours','factor':'2','weight':str(weight),'target':'10','cap':None}]},**REASON})
    assert r.status_code==200,r.text
    return r.json()

def activate(client,x):
    r=post(client,f"/api/rules/{x['id']}/trial",{'teacher_ids':['teacher']});assert r.status_code==200,r.text
    return post(client,f"/api/rules/{x['id']}/actions",{'expected_version':x['version'],'action':'activate',**REASON})

def make_assessment(client):
    auth(client,'schooladmin');x=rule(client);r=activate(client,x);assert r.status_code==200,r.text
    r=post(client,'/api/assessments/calculate',{'period_id':'period2026','teacher_ids':['teacher'],**REASON});assert r.status_code==200,r.text
    return r.json()['items'][0]

def test_real_app_login_cookie_database_hash(client2,app2):
    c=client2;me=auth(c,'teacher')
    assert me['user']['id']=='teacher' and me['permissions']
    assert 'password_hash' not in me['user'] and 'auth_version' not in me['user']
    token=c.cookies.get('nd_test_session')
    from hashlib import sha256
    with app2.state.sessions() as db:
        session=db.get(AuthSession,sha256(token.encode()).hexdigest());assert session and session.user_id=='teacher'
        assert token not in str([a.after for a in db.scalars(select(Audit))])
    assert c.get('/api/records').json()['total']==1

@pytest.mark.parametrize('path',['/api/records','/api/statistics','/api/qualifications','/api/assessments','/api/points','/api/point-balances','/api/teachers','/api/organizations','/api/todos','/api/notices'])
def test_teacher_boot_endpoints_real(client2,path):
    auth(client2,'teacher');r=client2.get(path);assert r.status_code==200,r.text

@pytest.mark.parametrize('path',['/api/users','/api/roles','/api/settings','/api/rules','/api/connections','/api/audit','/api/operations'])
def test_teacher_cannot_manage(client2,path):
    auth(client2,'teacher');assert client2.get(path).status_code==403

@pytest.mark.parametrize('path',['/api/users','/api/roles','/api/settings','/api/rules','/api/connections','/api/audit','/api/operations'])
def test_school_config_reads(client2,path):
    auth(client2,'schooladmin');r=client2.get(path);assert r.status_code==200,r.text

@pytest.mark.parametrize('kind,visible',[('teacher',1),('depthead',1),('collegehead',1),('schooladmin',2)])
def test_four_role_scope(client2,kind,visible):
    auth(client2,kind);assert client2.get('/api/records').json()['total']==visible
    if kind!='schooladmin':assert client2.get('/api/records/rec2').status_code==403

@pytest.mark.parametrize('headers',[{'Origin':'https://evil.invalid'},{'Origin':'null'},{'X-CSRF-Token':'invalid'},{'Sec-Fetch-Site':'same-site'}])
def test_cross_site_and_wrong_csrf(client2,headers):
    auth(client2,'teacher');r=post(client2,'/api/auth/logout',headers=headers);assert r.status_code==403


def test_missing_origin_and_csrf(client2):
    auth(client2,'teacher');client2.headers.pop('origin');assert post(client2,'/api/auth/logout').status_code==403
    client2.headers['origin']='http://testserver';client2.headers.pop('x-csrf-token');assert post(client2,'/api/auth/logout').status_code==403


def test_first_password_gate_and_revocation(client2,app2):
    with app2.state.sessions.begin() as db:db.get(User,'teacher').must_change_password=True
    auth(client2,'teacher');assert client2.get('/api/records').status_code==403
    old=client2.cookies.get('nd_test_session')
    r=post(client2,'/api/auth/password',{'old_password':FIXTURE_PASSWORD,'new_password':'Changed_2026_Safe'});assert r.status_code==200,r.text
    client2.cookies.set('nd_test_session',old);assert client2.get('/api/auth/me').status_code==401
    with app2.state.sessions() as db:
        u=db.get(User,'teacher');assert not u.must_change_password and verify_password(u.password_hash,'Changed_2026_Safe')
        assert not db.scalar(select(AuthSession.token_hash).where(AuthSession.user_id=='teacher'))
        assert 'Changed_2026_Safe' not in str([serial_dict.after for serial_dict in db.scalars(select(Audit))])


def test_login_lockout_and_no_secret_error(client2,app2):
    for i in range(app2.state.settings.login_attempts):
        r=client2.post('/api/auth/login',json={'username':'teacher','password':'not_the_password'});assert r.status_code==401
    r=client2.post('/api/auth/login',json={'username':'teacher','password':FIXTURE_PASSWORD});assert r.status_code==429
    assert FIXTURE_PASSWORD not in r.text


def test_disabled_old_session_and_role_revocation(client2,app2):
    auth(client2,'teacher')
    with app2.state.sessions.begin() as db:db.get(User,'teacher').active=False
    assert client2.get('/api/records').status_code==401
    with app2.state.sessions.begin() as db:db.get(User,'teacher').active=True;db.get(Role,'role-teacher').permissions=['portal.read']
    assert client2.get('/api/records').status_code==403


def test_live_organization_change(client2,app2):
    auth(client2,'depthead');assert client2.get('/api/records').json()['total']==1
    with app2.state.sessions.begin() as db:db.get(User,'teacher').org_id='dept2'
    assert client2.get('/api/records').json()['total']==0
    assert client2.get('/api/records/rec1').status_code==403


def test_idempotency_same_key_conflicting_and_new_duplicate(client2,app2):
    auth(client2,'teacher');payload={'teacher_id':'teacher','category':'职业资格','name':'资格测试','certificate_no':'IDEMP','issuer':'测试单位','obtained':'2026-01-01',**REASON}
    key=str(uuid.uuid4());r=post(client2,'/api/qualifications',payload,key=key);assert r.status_code==200,r.text
    assert post(client2,'/api/qualifications',payload,key=key).json()==r.json()
    assert post(client2,'/api/qualifications',{**payload,'name':'changed'},key=key).status_code==409
    assert post(client2,'/api/qualifications',payload).status_code==409
    with app2.state.sessions() as db:assert db.scalar(select(func.count()).select_from(Qualification))==1


def test_critical_audit_failure_rolls_back_all(client2,app2):
    auth(client2,'teacher')
    def broken(mapper,conn,obj):
        if obj.module=='qualification':raise RuntimeError('secret_do_not_echo')
    event.listen(Audit,'before_insert',broken)
    try:
        r=post(client2,'/api/qualifications',{'teacher_id':'teacher','category':'职业资格','name':'资格测试','certificate_no':'ROLLBACK','issuer':'测试单位','obtained':'2026-01-01',**REASON})
    finally:event.remove(Audit,'before_insert',broken)
    assert r.status_code==500 and 'secret_do_not_echo' not in r.text
    with app2.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Qualification))==0
        assert db.scalar(select(func.count()).select_from(Receipt))==0


def test_access_failure_does_not_reverse_business(client2,app2):
    auth(client2,'teacher')
    def broken(mapper,conn,obj):
        if obj.module=='access':raise RuntimeError('secret_access')
    event.listen(Audit,'before_insert',broken)
    try:x=qual(client2)
    finally:event.remove(Audit,'before_insert',broken)
    with app2.state.sessions() as db:assert db.get(Qualification,x['id']) is not None


def test_qualification_upload_return_resubmit_and_permission(client2,app2):
    auth(client2,'teacher');x=qual(client2);ident=x['id']
    def action(name,version):return post(client2,f'/api/qualifications/{ident}/actions',{'action':name,'expected_version':version,**REASON})
    assert action('submit',1).status_code==409
    r=client2.post(f'/api/attachments/qualification/{ident}',files={'file':('actual.png',png(),'image/png')},data={'reason':'测试佐证','expected_version':1},headers={'Idempotency-Key':str(uuid.uuid4())});assert r.status_code==200,r.text
    attachment=r.json()['id'];assert action('submit',2).status_code==200
    auth(client2,'otherdept');assert client2.get(f'/api/qualifications/{ident}').status_code==403
    assert client2.get(f'/api/attachments/{attachment}/download').status_code==403
    auth(client2,'depthead');assert action('return',3).status_code==200
    auth(client2,'teacher');assert action('submit',4).status_code==200
    auth(client2,'depthead');assert action('approve',5).status_code==200
    r=client2.get(f'/api/qualifications/{ident}');assert len(r.json()['revisions'])==6
    download=client2.get(f'/api/attachments/{attachment}/download');assert download.content==png()
    assert 'attachment' in download.headers['content-disposition']

@pytest.mark.parametrize('filename,data',[('bad.png',b'not a png'),('bad.html',b'<script>hi</script>'),('../a.png',b'bad'),('bad.pdf',b'%PDF-garbage')])
def test_malicious_files(client2,filename,data):
    auth(client2,'teacher');x=qual(client2)
    r=client2.post(f"/api/attachments/qualification/{x['id']}",files={'file':(filename,data)},data={'reason':'测试恶意附件','expected_version':1},headers={'Idempotency-Key':str(uuid.uuid4())});assert r.status_code==422


def test_rules_weight_trial_and_ledger(client2,app2):
    auth(client2,'schooladmin');x=rule(client2,weight=99)
    assert post(client2,f"/api/rules/{x['id']}/actions",{'action':'activate','expected_version':1,**REASON}).status_code==422
    x=rule(client2,'points');assert post(client2,f"/api/rules/{x['id']}/actions",{'action':'activate','expected_version':1,**REASON}).status_code==409
    assert activate(client2,x).status_code==200
    r=post(client2,'/api/points/calculate',{'period_id':'period2026','teacher_ids':['teacher'],'item_keys':['hours'],**REASON});assert r.status_code==200,r.text
    assert client2.get('/api/points?teacher_id=teacher').json()['sum']=='20.00'
    assert post(client2,'/api/points/calculate',{'period_id':'period2026','teacher_ids':['teacher'],**REASON}).status_code==200
    assert client2.get('/api/points?teacher_id=teacher').json()['total']==1
    auth(client2,'teacher');b=client2.get('/api/point-balances?teacher_id=teacher').json()['items'][0]
    r=post(client2,f"/api/point-balances/{b['id']}/actions",{'action':'confirm','expected_version':b['version'],**REASON});assert r.status_code==200,r.text
    auth(client2,'schooladmin');assert post(client2,'/api/points/calculate',{'period_id':'period2026','teacher_ids':['teacher'],**REASON}).status_code==409


def test_full_teacher_assessment_flow_freeze_and_filters(client2,app2):
    x=make_assessment(client2);ident=x['id'];version=x['version']
    assert post(client2,f'/api/assessments/{ident}/actions',{'action':'confirm','expected_version':version,**REASON}).status_code==403
    for username,state in [('teacher','DEPARTMENT'),('depthead','COLLEGE'),('collegehead','SCHOOL'),('schooladmin','READY')]:
        auth(client2,username);r=post(client2,f'/api/assessments/{ident}/actions',{'action':'confirm','expected_version':version,**REASON});assert r.status_code==200,r.text
        x=r.json();assert x['state']==state;version=x['version']
    r=post(client2,f'/api/assessments/{ident}/actions',{'action':'archive','expected_version':version,**REASON});assert r.status_code==200,r.text
    frozen=r.json()['archive_sha256'];assert digest(r.json()['archive'])==frozen
    assert post(client2,'/api/assessments/calculate',{'period_id':'period2026','teacher_ids':['teacher'],**REASON}).status_code==409
    assert post(client2,f'/api/assessments/{ident}/adjust',{'delta':'1','expected_version':r.json()['version'],**REASON}).status_code==409
    assert client2.get('/api/statistics?project_code=P1').json()['assessment_states']=={'ARCHIVED':1}
    assert client2.get('/api/statistics?project_code=P2').json()['assessment_states']=={}
    assert client2.get(f'/api/assessments/{ident}/print').status_code==200
    assert client2.get(f'/api/assessments/{ident}').json()['assessment']['archive_sha256']==frozen


def test_dispute_blocks_confirmation_and_reviewer_separation(client2):
    x=make_assessment(client2);ident=x['id'];auth(client2,'teacher')
    r=post(client2,'/api/disputes',{'object_type':'assessment','object_id':ident,**REASON});assert r.status_code==200,r.text
    dispute=r.json();assert post(client2,f'/api/assessments/{ident}/actions',{'action':'confirm','expected_version':x['version'],**REASON}).status_code==409
    assert post(client2,f"/api/disputes/{dispute['id']}/resolve",{'resolution':'测试结论','expected_version':1,**REASON}).status_code==403
    auth(client2,'depthead');r=post(client2,f"/api/disputes/{dispute['id']}/resolve",{'resolution':'测试复核结论','expected_version':1,**REASON});assert r.status_code==200,r.text
    auth(client2,'teacher');assert post(client2,f'/api/assessments/{ident}/actions',{'action':'confirm','expected_version':x['version'],**REASON}).status_code==200


def test_return_state_filter_and_stale_version(client2):
    x=make_assessment(client2);ident=x['id'];auth(client2,'teacher')
    r=post(client2,f'/api/assessments/{ident}/actions',{'action':'confirm','expected_version':x['version'],**REASON});assert r.status_code==200
    auth(client2,'depthead');r=post(client2,f'/api/assessments/{ident}/actions',{'action':'return','expected_version':r.json()['version'],**REASON});assert r.status_code==200
    assert client2.get('/api/assessments?returned=true').json()['total']==1
    assert client2.get('/api/assessments?returned=false').json()['total']==0
    auth(client2,'teacher');assert post(client2,f'/api/assessments/{ident}/actions',{'action':'confirm','expected_version':1,**REASON}).status_code==409


def test_last_admin_and_role_copy(client2):
    auth(client2,'schooladmin');role=client2.get('/api/roles').json()['items'];x=next(r for r in role if r['kind']=='school')
    r=put(client2,f"/api/roles/{x['id']}",{'expected_version':1,'active':True,'permissions':['portal.read'],**REASON});assert r.status_code==409
    r=post(client2,'/api/roles',{'code':'teacher_copy','name':'教师角色副本','copy_from':'role-teacher',**REASON});assert r.status_code==200,r.text
    y=r.json();assert y['kind']=='teacher'
    r=put(client2,f"/api/roles/{y['id']}",{'expected_version':1,'active':True,'permissions':['roles.manage'],**REASON});assert r.status_code==403


def test_production_refuses_sqlite_and_seed():
    with pytest.raises(ValueError):Settings(database_url='sqlite://')
    with pytest.raises(ValueError):Settings(database_url='mysql+pymysql://local:pass@localhost/db',seed_enabled=True)
    from app.releasecheck import check_source_release
    assert check_source_release()['status']=='PASS'
    assert check_source_release()['legacy_upgrade_allowed'] is False
