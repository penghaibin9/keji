"""PDF 2.3/2.5 + 12.5/12.6 authorization regression matrix.

These are negative tests: a hidden button is never treated as authorization.
"""
import pytest
from conftest import auth,post

SCHOOL_ONLY_GET=[
    '/api/users?size=5','/api/roles','/api/settings','/api/audit?size=5','/api/operations',
    '/api/connections/catalog','/api/sync-items?size=5',
]

@pytest.mark.parametrize('username',['teacher','depthead','collegehead'])
@pytest.mark.parametrize('path',SCHOOL_ONLY_GET)
def test_non_school_roles_cannot_reach_school_control_plane(client2,username,path):
    auth(client2,username)
    r=client2.get(path)
    assert r.status_code==403,(username,path,r.status_code,r.text)

@pytest.mark.parametrize('username',['teacher','depthead','collegehead'])
def test_cross_college_record_detail_is_server_side_denied(client2,username):
    auth(client2,username)
    r=client2.get('/api/records/rec2')
    assert r.status_code==403,(username,r.status_code,r.text)


def test_teacher_cannot_create_school_handover_or_sync_task(client2):
    auth(client2,'teacher')
    r=post(client2,'/api/exports',{'kind':'handover','filters':{},'confirmed':True})
    assert r.status_code==403,r.text
    r=post(client2,'/api/connections/province/sync',{'data_type':'training_record','records':[{'business_key':'x'}],'reason':'越权反向测试'})
    assert r.status_code==403,r.text


def test_teacher_cannot_read_organization_assessment(client2):
    auth(client2,'teacher')
    r=client2.get('/api/organization-assessments?size=5')
    assert r.status_code==403,r.text


def test_school_admin_can_reach_control_plane_and_cross_org_business(client2):
    auth(client2,'schooladmin')
    for path in ['/api/users?size=5','/api/roles','/api/settings','/api/audit?size=5','/api/operations','/api/connections/catalog','/api/records/rec2']:
        r=client2.get(path);assert r.status_code==200,(path,r.status_code,r.text)


def test_user_and_me_serialization_never_exposes_authentication_secrets(client2):
    me=auth(client2,'schooladmin')
    forbidden={'password_hash','token_hash','csrf','failures','locked_until','auth_version','storage_key'}
    # csrf is allowed only as the top-level anti-CSRF value, never inside serialized user.
    assert not (forbidden & set(me['user']))
    users=client2.get('/api/users?size=20').json()['items']
    assert users
    for row in users:
        assert not (forbidden & set(row))


def test_denied_cross_org_access_is_audited_for_school_investigation(client2):
    auth(client2,'teacher')
    denied=client2.get('/api/records/rec2');assert denied.status_code==403
    auth(client2,'schooladmin')
    data=client2.get('/api/audit?result=DENIED&size=50').json()['items']
    assert any(x['module']=='access' and x['object_id']=='/api/records/rec2' and x['actor_name']=='测试教师一' for x in data)
