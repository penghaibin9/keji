"""HTTP-level security/failure tests against full R2 application (SQLite)."""
import io,uuid,os
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from sqlalchemy import select,func,event
import pytest
from app.models import *
from app.core import serial
from app.schemas import UserIn,ResetPassword
from conftest import auth,post,put
from test_api import qual,png,REASON,make_assessment,rule,activate
from support import FIXTURE_PASSWORD

def upload(c,x):
    return c.post('/api/attachments/qualification/'+x['id'],files={'file':('evidence.png',png(),'image/png')},
                  data={'reason':'附加测试依据','expected_version':x['version']},headers={'Idempotency-Key':str(uuid.uuid4())})

@pytest.mark.parametrize('field',['password','password_hash','new_password','old_password','token','refresh_token','client_secret','storage_key','Authorization'])
def test_public_serial_never_returns_secret_keys(field):
    assert serial({'nested':{field:'MUST_NOT_LEAK','safe':'value'}})=={'nested':{'safe':'value'}}

def test_complete_password_hash_input_preserves_whitespace():
    password='  SafePassword_2026  '
    data=UserIn(username='abc',name='测试',org_id='school',role_id='role-school',password=password,**REASON)
    assert data.password==password
    reset=ResetPassword(password=password,expected_version=1,**REASON);assert reset.password==password


def test_attachment_before_parse_authentication(client2):
    r=client2.post('/api/attachments/qualification/not-found',files={'file':('a.png',b'broken')},data={'reason':'无会话测试','expected_version':1})
    assert r.status_code==401


def test_attachment_rollback_removes_new_bytes(client2,app2):
    auth(client2,'teacher');x=qual(client2)
    def fail(mapper,conn,obj):
        if obj.module=='qualification' and obj.action=='上传业务佐证':raise RuntimeError('injected')
    event.listen(Audit,'before_insert',fail)
    try:r=upload(client2,x)
    finally:event.remove(Audit,'before_insert',fail)
    assert r.status_code==500
    with app2.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Attachment))==0
        assert db.get(Qualification,x['id']).version==1
    assert not list(app2.state.settings.storage_dir.iterdir())


@pytest.mark.parametrize('attack',['tamper','symlink'])
def test_attachment_tamper_and_symlink_blocked(client2,app2,tmp_path,attack):
    auth(client2,'teacher');x=qual(client2);r=upload(client2,x);assert r.status_code==200
    ident=r.json()['id']
    with app2.state.sessions() as db:key=db.get(Attachment,ident).storage_key
    path=app2.state.settings.storage_dir/key;original=path.read_bytes()
    if attack=='tamper':path.write_bytes(b'corrupt')
    else:
        path.unlink();outside=tmp_path/'outside';outside.write_bytes(original)
        try:path.symlink_to(outside)
        except OSError as exc:
            if os.name=='nt' and getattr(exc,'winerror',None)==1314:
                pytest.skip('Windows account lacks symlink privilege; junction rejection tested separately')
            raise
    assert client2.get(f'/api/attachments/{ident}/download').status_code==503


def test_attachment_old_revision_remains_and_revoked_permission(client2,app2):
    auth(client2,'teacher');x=qual(client2);r=upload(client2,x);ident=r.json()['id']
    r=post(client2,f'/api/attachments/{ident}/detach',{'expected_version':2,**REASON});assert r.status_code==200,r.text
    assert client2.get(f'/api/attachments/{ident}/download').content==png()
    with app2.state.sessions.begin() as db:
        role=db.get(Role,'role-teacher');role.permissions=[p for p in role.permissions if p!='file.read'];role.version+=1
    assert client2.get(f'/api/attachments/{ident}/download').status_code==403


def test_receipt_recheck_after_scope_change(client2,app2):
    auth(client2,'schooladmin');key=str(uuid.uuid4())
    payload={'external_key':'receipt-scope','teacher_id':'teacher','event_date':'2026-09-17','project_code':'P3','project':'合成项目','course_code':'C3','course':'合成课程','class_code':'CL3','class_name':'合成班级','hours':'1','income':'5','participants':1,**REASON}
    r=post(client2,'/api/records',payload,key=key);assert r.status_code==200,r.text
    with app2.state.sessions.begin() as db:
        db.get(User,'otherteacher').staff_no=None
    assert post(client2,'/api/records',payload,key=key).status_code==409


def test_reset_password_different_input_same_key_conflict(client2):
    auth(client2,'schooladmin');key=str(uuid.uuid4())
    data={'password':'New_TestPassword_2026','expected_version':1,**REASON}
    r=post(client2,'/api/users/teacher/reset-password',data,key=key);assert r.status_code==200,r.text
    r=post(client2,'/api/users/teacher/reset-password',{**data,'password':'Different_TestPassword_2026'},key=key)
    assert r.status_code==409


def test_replayed_command_new_session_permission_denied(client2,app2):
    auth(client2,'schooladmin');key=str(uuid.uuid4())
    payload={'code':'t_copy','name':'教师副本','copy_from':'role-teacher',**REASON}
    r=post(client2,'/api/roles',payload,key=key);assert r.status_code==200
    with app2.state.sessions.begin() as db:
        role=db.get(Role,'role-school');role.permissions=[p for p in role.permissions if p!='roles.manage'];role.version+=1
    assert post(client2,'/api/roles',payload,key=key).status_code==403


def test_confirmation_snapshot_unchanged_after_adjust(client2,app2):
    auth(client2,'schooladmin');x=rule(client2,'points');assert activate(client2,x).status_code==200
    assert post(client2,'/api/points/calculate',{'period_id':'period2026','teacher_ids':['teacher'],**REASON}).status_code==200
    auth(client2,'teacher');b=client2.get('/api/point-balances?teacher_id=teacher').json()['items'][0]
    r=post(client2,f"/api/point-balances/{b['id']}/actions",{'action':'confirm','expected_version':b['version'],**REASON});assert r.status_code==200
    with app2.state.sessions() as db:
        snapshot=db.scalar(select(WorkflowEvent).where(WorkflowEvent.object_type=='point_balance',WorkflowEvent.action=='积分确认')).after
    auth(client2,'schooladmin');assert post(client2,f"/api/point-balances/{b['id']}/actions",{'action':'reopen','expected_version':r.json()['version'],**REASON}).status_code==200
    assert post(client2,'/api/points/adjust',{'teacher_id':'teacher','period_id':'period2026','item_key':'manual_review','amount':'-3',**REASON}).status_code==200
    assert client2.get('/api/points?teacher_id=teacher').json()['sum']=='17.00'
    with app2.state.sessions() as db:
        old=db.scalar(select(WorkflowEvent).where(WorkflowEvent.object_type=='point_balance',WorkflowEvent.action=='积分确认')).after
    assert old==snapshot and old['total']=='20.00'


def test_session_absolute_and_idle_expiration(client2,app2):
    auth(client2,'teacher')
    with app2.state.sessions.begin() as db:db.scalar(select(AuthSession).where(AuthSession.user_id=='teacher')).expires_at=utcnow()-timedelta(seconds=1)
    assert client2.get('/api/records').status_code==401
    auth(client2,'teacher')
    with app2.state.sessions.begin() as db:db.scalar(select(AuthSession).where(AuthSession.user_id=='teacher')).last_seen=utcnow()-timedelta(hours=2)
    assert client2.get('/api/records').status_code==401


def test_new_login_rotates_old_session(client2,app2):
    auth(client2,'teacher');old=client2.cookies.get('nd_test_session')
    auth(client2,'teacher');new=client2.cookies.get('nd_test_session');assert old!=new
    from hashlib import sha256
    with app2.state.sessions() as db:assert db.get(AuthSession,sha256(old.encode()).hexdigest()) is None


def test_post_limit_and_unknown_fields(client2,app2):
    auth(client2,'teacher');x=qual(client2)
    assert post(client2,f"/api/qualifications/{x['id']}/actions",{'action':'approve','expected_version':1,'is_admin':True,**REASON}).status_code==422
    app2.state.settings.upload_limit_mb=1
    # Main's body cap was constructed from original 10 MiB; route limit still applies.
    r=client2.post('/api/attachments/qualification/'+x['id'],files={'file':('large.png',b'x'*(1024*1024+1))},data={'reason':'大文件测试','expected_version':1},headers={'Idempotency-Key':str(uuid.uuid4())})
    assert r.status_code==413


def test_concurrent_same_key_only_one_object(app2):
    with TestClient(app2,raise_server_exceptions=False) as initial:
        initial.headers['origin']='http://testserver';me=auth(initial,'teacher');token=initial.cookies.get('nd_test_session')
    key=str(uuid.uuid4());data={'teacher_id':'teacher','category':'职业资格','name':'并发证书','certificate_no':'CONCURRENT','issuer':'测试单位','obtained':'2026-01-01',**REASON}
    def send():
        with TestClient(app2,raise_server_exceptions=False) as c:
            c.cookies.set('nd_test_session',token);c.headers.update({'origin':'http://testserver','x-csrf-token':me['csrf']})
            return post(c,'/api/qualifications',data,key=key)
    with ThreadPoolExecutor(max_workers=2) as ex:responses=list(ex.map(lambda _:send(),range(2)))
    assert all(r.status_code==200 for r in responses),[r.text for r in responses]
    assert responses[0].json()['id']==responses[1].json()['id']
    with app2.state.sessions() as db:assert db.scalar(select(func.count()).select_from(Qualification))==1


def test_org_disabled_or_broken_hierarchy_rejects(client2,app2):
    auth(client2,'teacher')
    with app2.state.sessions.begin() as db:db.get(Org,'college1').active=False
    assert client2.get('/api/records').status_code==403
    with app2.state.sessions.begin() as db:db.get(Org,'college1').active=True;db.get(Org,'dept1').parent_id='dept2'
    assert client2.get('/api/records').status_code==403


def test_valid_login_does_not_consume_failed_ip_budget(client2,app2):
    for _ in range(3):auth(client2,'teacher')
    with app2.state.sessions() as db:assert db.scalar(select(Throttle)).attempts==0


def test_closed_period_and_wrong_role_state(client2):
    x=make_assessment(client2)
    # Closing with an unarchived result is refused with the exact preserved UI payload.
    r=post(client2,'/api/periods/period2026/close',{'expected_version':1,**REASON});assert r.status_code==409
    auth(client2,'collegehead')
    r=post(client2,f"/api/assessments/{x['id']}/actions",{'expected_version':x['version'],'action':'archive',**REASON});assert r.status_code==403


def test_archived_snapshot_matches_current_version(client2):
    x=make_assessment(client2)
    for user in ['teacher','depthead','collegehead','schooladmin']:
        auth(client2,user);r=post(client2,f"/api/assessments/{x['id']}/actions",{'expected_version':x['version'],'action':'confirm',**REASON});assert r.status_code==200
        x=r.json()
    r=post(client2,f"/api/assessments/{x['id']}/actions",{'expected_version':x['version'],'action':'archive',**REASON});assert r.status_code==200
    assert r.json()['archive']['assessment']['version']==r.json()['version']


@pytest.mark.parametrize('encrypted,expected',[(False,200),(True,422)])
def test_pdf_structure_upload_and_same_bytes(client2,encrypted,expected):
    from pypdf import PdfWriter
    import io
    auth(client2,'teacher');x=qual(client2)
    stream=io.BytesIO();writer=PdfWriter();writer.add_blank_page(width=300,height=300)
    if encrypted:writer.encrypt('fixture-only-pdf-password')
    writer.write(stream);data=stream.getvalue()
    r=client2.post('/api/attachments/qualification/'+x['id'],files={'file':('evidence.pdf',data,'application/pdf')},
        data={'reason':'PDF结构验证','expected_version':x['version']},headers={'Idempotency-Key':str(uuid.uuid4())})
    assert r.status_code==expected,r.text
    if expected==200:
        result=client2.get('/api/attachments/'+r.json()['id']+'/download')
        assert result.status_code==200 and result.content==data


def test_pdf_signature_alone_not_accepted(client2):
    auth(client2,'teacher');x=qual(client2)
    r=client2.post('/api/attachments/qualification/'+x['id'],files={'file':('bad.pdf',b'%PDF-1.7\nnot a pdf structure','application/pdf')},
        data={'reason':'伪造PDF测试','expected_version':x['version']},headers={'Idempotency-Key':str(uuid.uuid4())})
    assert r.status_code==422
