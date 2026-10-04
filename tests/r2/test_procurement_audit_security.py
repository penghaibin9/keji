"""12.2 exact audit filters and 12.3 summarised security notices."""
from conftest import auth,post,put
from support import FIXTURE_PASSWORD

REASON={'reason':'审计筛选测试','basis':'合成隔离数据'}


def test_audit_exact_filters_by_actor_org_object_and_request(client2):
    c=client2;auth(c,'schooladmin')
    s={x['key']:x for x in c.get('/api/settings').json()['items']}['branding']
    r=put(c,'/api/settings/branding',{'value':{'school_name':'筛选测试学校'},'expected_version':s['version'],**REASON});assert r.status_code==200
    request_id=r.headers['x-request-id']
    auth(c,'depthead');c.get('/api/records')
    auth(c,'schooladmin')
    by_name=c.get('/api/audit',params={'actor':'schooladmin','module':'settings'}).json()
    assert by_name['total']>=1 and all(x['actor_id']=='schooladmin' for x in by_name['items'])
    assert any(x['module']=='settings' for x in c.get('/api/audit/security-alerts').json()['key_changes'])
    dept=c.get('/api/audit',params={'actor':'depthead','size':200}).json()['items']
    assert dept and all(x['actor_id']=='depthead' for x in dept)
    org=c.get('/api/audit',params={'org_id':'dept1','size':200}).json()['items']
    assert org and all(x['org_id']=='dept1' for x in org)
    obj=c.get('/api/audit',params={'object_id':'branding'}).json()['items']
    assert obj and all(x['object_id']=='branding' for x in obj)
    req=c.get('/api/audit',params={'request_id':request_id}).json()['items']
    assert req and all(x['request_id']==request_id for x in req) and any(x['module']=='settings' for x in req)
    assert c.get('/api/audit',params={'actor':'nobody'}).json()['total']==0
    # Partial object id is not matched (exact filter), and the export accepts the same filters.
    assert c.get('/api/audit',params={'object_id':'brand'}).json()['total']==0
    assert post(c,'/api/exports',{'kind':'audit','filters':{'actor':'schooladmin','request_id':request_id},'confirmed':False}).status_code==200
    auth(c,'depthead');assert c.get('/api/audit',params={'actor':'schooladmin'}).status_code==403


def test_security_alerts_summarise_denials_login_failures_and_raise_todo(client2):
    c=client2
    auth(c,'teacher')
    for _ in range(6):assert c.get('/api/users').status_code==403
    c.cookies.clear()
    for _ in range(10):
        assert c.post('/api/auth/login',json={'username':'otherteacher','password':'wrong-password-123'}).status_code in {401,429}
    auth(c,'depthead');assert c.get('/api/audit/security-alerts').status_code==403
    auth(c,'schooladmin')
    a=c.get('/api/audit/security-alerts');assert a.status_code==200,a.text;a=a.json()
    teacher=next(x for x in a['denied_by_user'] if x['actor_id']=='teacher')
    assert teacher['count']>=6 and teacher['flagged'] and '/api/users' in teacher['recent_objects']
    assert a['login']['refused']>=10 and any(u['username']=='otherteacher' and u['locked_till'] and u['failed_attempts']>=10 for u in a['login']['accounts'])
    assert a['alert'] and len(a['flags'])>=2
    todos=c.get('/api/todos',params={'type':'security'}).json()
    assert todos['total']==1 and todos['items'][0]['title'].startswith('安全提示')
    home=c.get('/api/portal/workbench').json()
    assert any(x['type']=='security' and x['owner_name']=='安全审计' for x in home['tasks']['items']) or home['tasks']['total']>6
    assert c.get('/api/audit/security-alerts',params={'days':'0'}).status_code==422
    # Non-admin users never receive the security todo.
    auth(c,'depthead');assert c.get('/api/todos',params={'type':'security'}).json()['total']==0


def test_security_alert_absent_without_threshold(client2):
    auth(client2,'schooladmin')
    a=client2.get('/api/audit/security-alerts').json()
    assert a['alert'] is False and a['flags']==[]
    assert client2.get('/api/todos',params={'type':'security'}).json()['total']==0
