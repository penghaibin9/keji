"""R11 live portal contracts. SQLite/TestClient synthetic controls, not school E2E."""
from datetime import datetime,timedelta
from io import BytesIO
from zipfile import ZipFile
from pathlib import Path
import pytest
from sqlalchemy import select
from app.models import Task,Connection,User,Role
from app.reference_data import InboundBatch
from conftest import auth,post


def conns(app):
    with app.state.sessions() as db:return {x.code:x.id for x in db.scalars(select(Connection))}

def add_tasks(app,count=3):
    ids=conns(app)
    with app.state.sessions.begin() as db:
        for i in range(count):
            db.add(Task(id=f'pull-{i:03}',kind='inbound_pull',owner_id='schooladmin',key=f'pull-key-{i}',
                payload={'connection_id':ids['middle'],'connection_code':'middle','data_type':'teacher_hr','authorization':{'secret':'not-public'}},
                state='FAILED',error='合成拉取异常',created_at=datetime(2026,9,1)+timedelta(seconds=i)))
        db.add(Task(id='outbound',kind='sync',owner_id='schooladmin',key='outbound-key',payload={'connection_id':ids['province'],'connection_code':'province','data_type':'course'},state='BLOCKED'))
        db.add(Task(id='export-own',kind='export',owner_id='teacher',key='export-key',payload={},state='FAILED'))
    return ids


def test_unified_todos_include_both_inbound_and_outbound(client2,app2):
    add_tasks(app2);auth(client2,'schooladmin');r=client2.get('/api/todos');assert r.status_code==200,r.text
    items={x['id']:x for x in r.json()['items']}
    assert all(x in items for x in ['pull-000','pull-001','pull-002','outbound'])
    assert items['pull-000']['type']=='sync' and items['pull-000']['task_kind']=='inbound_pull'
    assert 'export-own' not in items

@pytest.mark.parametrize('username',['teacher','depthead','collegehead','otherdept'])
def test_external_exceptions_never_leak_to_subordinate_roles(client2,app2,username):
    add_tasks(app2);auth(client2,username);r=client2.get('/api/todos');assert r.status_code==200
    assert not any(x['type']=='sync' for x in r.json()['items'])


def test_integration_exceptions_only_on_school_workbench(client2,app2):
    add_tasks(app2);auth(client2,'schooladmin')
    all_data=client2.get('/api/organization-workbench').json()['todos']['items']
    dept=client2.get('/api/organization-workbench?org_id=dept1').json()['todos']['items']
    assert any(x['id']=='pull-000' for x in all_data)
    assert not any(x['type']=='sync' for x in dept)


def make_org_result(client,target='dept1'):
    rule=post(client,'/api/organization-assessment-rules',{'target_kind':'dept','name':'R11工作台规则',
        'period_id':'period2026','config':{'components':[{'key':'income','label':'收入','source':'income','weight':'100','target':'100'}]},
        'reason':'合成专项测试','basis':'PDF6.6'});assert rule.status_code==200,rule.text;rule=rule.json()
    trial=post(client,f"/api/organization-assessment-rules/{rule['id']}/trial",{'target_ids':[target]});assert trial.status_code==200,trial.text
    activated=post(client,f"/api/organization-assessment-rules/{rule['id']}/actions",{'expected_version':rule['version'],'action':'activate','reason':'试算后启用','basis':'合成样本'})
    assert activated.status_code==200,activated.text
    r=post(client,'/api/organization-assessments/calculate',{'period_id':'period2026','target_kind':'dept','target_ids':[target],'reason':'专项测试','basis':'PDF6.6'})
    assert r.status_code==200,r.text;return r.json()['items'][0]


def test_org_workbench_and_todos_agree_without_cross_org(client2,app2):
    auth(client2,'schooladmin');obj=make_org_result(client2)
    auth(client2,'depthead')
    unified=client2.get('/api/todos').json()['items'];local=client2.get('/api/organization-workbench').json()['todos']['items']
    assert any(x['id']==obj['id'] for x in unified)
    assert any(x['id']==obj['id'] for x in local)
    auth(client2,'otherdept')
    other=client2.get('/api/organization-workbench').json()['todos']['items']
    assert not any(x['id']==obj['id'] for x in other)
    assert client2.get('/api/organization-workbench?org_id=dept1').status_code==403


def test_tasks_connection_filter_and_second_page_are_server_side(client2,app2):
    ids=add_tasks(app2,23);auth(client2,'schooladmin')
    url=f"/api/tasks?kind=integration&connection_id={ids['middle']}&data_type=teacher_hr&state=FAILED&size=20"
    a=client2.get(url).json();b=client2.get(url+'&page=2').json()
    assert a['total']==b['total']==23 and len(a['items'])==20 and len(b['items'])==3
    assert {x['id'] for x in a['items']}.isdisjoint({x['id'] for x in b['items']})
    assert all(x['payload']['connection_id']==ids['middle'] for x in a['items']+b['items'])
    assert all('authorization' not in x['payload'] for x in a['items']+b['items'])
    p=client2.get('/api/tasks?kind=integration&connection_id='+ids['province']).json()
    assert [x['id'] for x in p['items']]==['outbound']

@pytest.mark.parametrize('query',['kind=integration&state=banana','kind=integration&data_type=secret_table','kind=export&connection_id=x','kind=integration&page=0','kind=integration&state=DONE&state=FAILED'])
def test_task_filters_reject_invalid_inputs(client2,query):
    auth(client2,'schooladmin');r=client2.get('/api/tasks?'+query);assert r.status_code==422,r.text

@pytest.mark.parametrize('username',['teacher','depthead','collegehead'])
def test_task_filters_do_not_grant_integration_permission(client2,app2,username):
    ids=add_tasks(app2);auth(client2,username)
    assert client2.get('/api/tasks?kind=integration&connection_id='+ids['middle']).status_code==403


def test_inbound_list_is_paged_metadata_not_raw_hr(client2,app2):
    ids=conns(app2)
    with app2.state.sessions.begin() as db:
        for i in range(23):db.add(InboundBatch(id=f'batch-{i:03}',connection_id=ids['middle'],data_type='teacher_hr',owner_id='schooladmin',source_label='PRIVATE FILENAME',total=1,errors=0,receipt={'private':'secret'},created_at=datetime(2026,9,1)+timedelta(seconds=i)))
    auth(client2,'schooladmin');url='/api/inbound-batches?connection_id='+ids['middle']+'&size=20'
    a=client2.get(url);b=client2.get(url+'&page=2');assert a.status_code==b.status_code==200
    x,y=a.json(),b.json();assert x['total']==23 and len(y['items'])==3
    assert {i['id'] for i in x['items']}.isdisjoint({i['id'] for i in y['items']})
    assert 'PRIVATE' not in a.text and 'secret' not in a.text and 'receipt' not in a.text

@pytest.mark.parametrize('username',['teacher','depthead','collegehead'])
def test_inbound_metadata_requires_admin_and_sync_permission(client2,username):
    auth(client2,username);assert client2.get('/api/inbound-batches').status_code==403


def test_nonadmin_school_operator_cannot_read_inbound_hr(client2,app2):
    with app2.state.sessions.begin() as db:db.get(User,'schooladmin').is_admin=False
    auth(client2,'schooladmin');assert client2.get('/api/inbound-batches').status_code==403

@pytest.mark.parametrize('query',['data_type=certificate','state=DONE','page=0','data_type=teacher_hr&data_type=course'])
def test_inbound_list_rejects_unsupported_filters(client2,query):
    auth(client2,'schooladmin');assert client2.get('/api/inbound-batches?'+query).status_code==422


def test_coordination_download_is_real_xlsx_and_not_a_filled_receipt(client2):
    auth(client2,'schooladmin');r=client2.get('/api/connections/coordination.xlsx');assert r.status_code==200,r.text
    assert 'spreadsheetml' in r.headers['content-type'] and 'attachment' in r.headers['content-disposition']
    with ZipFile(BytesIO(r.content)) as z:
        assert z.testzip() is None
        text=''.join(z.read(n).decode() for n in z.namelist() if n.endswith('.xml'))
        assert '学校统一身份认证资料清单' in text and '学校数据中台资料清单' in text and '湘培直通车资料清单' in text
        assert 'SAMPLE-001' not in text
    audit=client2.get('/api/audit').json();assert any(x['action']=='下载对接沟通清单' for x in audit['items'])

@pytest.mark.parametrize('username',['teacher','depthead'])
def test_coordination_template_not_public_admin_endpoint(client2,username):
    auth(client2,username);assert client2.get('/api/connections/coordination.xlsx').status_code==403


def test_deployment_includes_all_new_frontend_resources_and_template():
    root=Path(__file__).resolve().parents[2]
    from check_assembly import inspect_assembly
    assert inspect_assembly(root)['status']=='PASS'
    html=(root/'frontend/index.html').read_text(encoding='utf-8')
    assert '/assets/portal.css' in html
    assert (root/'backend/app/resources/integration-coordination.xlsx').read_bytes()==(root/'docs/templates/integration-coordination.xlsx').read_bytes()


def test_nginx_asset_contract_is_included_in_source_and_image_guards():
    root=Path(__file__).resolve().parents[2]
    from check_assembly import REQUIRED
    assert 'deploy/nginx.conf' in REQUIRED
    config=(root/'deploy/nginx.conf').read_text(encoding='utf-8')
    assert 'location ^~ /assets/' in config and 'alias /usr/share/nginx/html/;' in config
    assert 'Cache-Control "no-store" always' in config
    assets=config.split('location ^~ /assets/',1)[1].split('}',1)[0]
    assert 'Cache-Control "no-cache" always' in assets and 'X-Content-Type-Options nosniff always' in assets and 'X-Frame-Options DENY always' in assets
    assert 'gzip on;' in config and 'application/javascript' in config
    docker=(root/'deploy/Dockerfile.api').read_text(encoding='utf-8')
    assert 'deploy/compose.yml deploy/nginx.conf /opt/nondegree/deploy/' in docker
    compose=(root/'deploy/compose.yml').read_text(encoding='utf-8')
    assert compose.count('2026.09.19-r11')==2
