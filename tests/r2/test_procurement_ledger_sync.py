"""11.3 湘培直通车: assemble outbound records from the local ledger with stable business keys."""
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import Audit,Task
from app.integrations import SyncItem
from app.province_payload import CANONICAL_FIELDS,WAITING_REASONS
from conftest import auth,post,put
from test_api import make_assessment,REASON


def province(c):
    return next(x['connection'] for x in c.get('/api/connections/catalog').json()['items'] if x['connection']['code']=='province')


def configure(c,data_type,mappings):
    p=province(c)
    r=put(c,'/api/connections/'+p['id'],{'mappings':[{'data_type':data_type,'source':s,'target':t,'transform':'text','required':False,'default':None} for s,t in mappings],
      'config':{'endpoint':'https://province.example/api','owner':'省平台','retry_count':3,'secret_env':'ND_PROVINCE','frequency_minutes':30,'auth_mode':'custom'},
      'expected_version':p['version'],'reason':'配置字段对应','basis':'测试'})
    assert r.status_code==200,r.text
    return province(c)


def test_catalog_lists_seven_buildable_and_explains_four_waiting(client2):
    auth(client2,'schooladmin');p=province(client2)
    items=client2.get(f"/api/connections/{p['id']}/ledger-sync/catalog").json()['items']
    assert {x['data_type'] for x in items if x['buildable']}==set(CANONICAL_FIELDS)=={'training_project','course','class','teaching','participants','training_record','assessment_result'}
    waiting={x['data_type']:x for x in items if not x['buildable']}
    assert set(waiting)==set(WAITING_REASONS)=={'plan','learning_process','completion_result','certificate'} and all(x['waiting_reason'] for x in waiting.values())
    r=client2.get(f"/api/connections/{p['id']}/ledger-sync/preview",params={'data_type':'certificate','period_id':'period2026'});assert r.status_code==409 and '证书' in r.text


def test_preview_scope_and_enqueue_with_stable_idempotency(client2,app2):
    auth(client2,'schooladmin');p=province(client2)
    params={'data_type':'training_record','start':'2026-01-01','end':'2026-12-31'}
    r=client2.get(f"/api/connections/{p['id']}/ledger-sync/preview",params=params);assert r.status_code==200,r.text;pv=r.json()
    assert pv['count']==2 and not pv['mapping_ready'] and pv['sample'][0]['business_key']=='record:rec1' and pv['external_called'] is False
    assert {f['key'] for f in pv['fields']}>={'record_key','teacher_staff_no','income'}
    assert client2.get(f"/api/connections/{p['id']}/ledger-sync/preview",params={'data_type':'training_record'}).status_code==422
    body={'data_type':'training_record','start':'2026-01-01','end':'2026-12-31','expected_count':2,**REASON}
    assert post(client2,f"/api/connections/{p['id']}/ledger-sync",body).status_code==409  # no mapping => no empty payload
    p=configure(client2,'training_record',[('record_key','PROVINCE_FIELD_A'),('income','PROVINCE_FIELD_B')])
    assert client2.get(f"/api/connections/{p['id']}/ledger-sync/preview",params=params).json()['mapped_sample'][0]=={'PROVINCE_FIELD_A':'rec1','PROVINCE_FIELD_B':'100.00'}
    assert post(client2,f"/api/connections/{p['id']}/ledger-sync",{**body,'expected_count':3}).status_code==409
    r=post(client2,f"/api/connections/{p['id']}/ledger-sync",body);assert r.status_code==200,r.text;out=r.json()
    assert out['records']==2 and out['tasks'][0]['state']=='BLOCKED' and out['tasks'][0]['created']
    # 4.9 latest sync per data type with its failure reason.
    latest=client2.get('/api/connections/summary',params={'connection_id':p['id'],'data_type':'training_record'}).json()['items'][0]['latest_task']
    assert latest['id']==out['tasks'][0]['id'] and latest['failure_reason']=='外部接口未真实连接' and latest['failure_items'][0]['error']=='NOT_CONNECTED'
    assert client2.get('/api/connections/summary',params={'connection_id':p['id'],'data_type':'course'}).json()['items'][0]['latest_task'] is None
    again=post(client2,f"/api/connections/{p['id']}/ledger-sync",body).json()
    assert again['tasks'][0]['id']==out['tasks'][0]['id'] and not again['tasks'][0]['created']
    with Session(app2.state.engine) as db:
        items=db.scalars(select(SyncItem).where(SyncItem.task_id==out['tasks'][0]['id'])).all()
        assert sorted(x.business_key for x in items)==['record:rec1','record:rec2'] and items[0].payload.keys()=={'PROVINCE_FIELD_A','PROVINCE_FIELD_B'}
        assert db.scalar(select(Audit).where(Audit.action=='从台账生成湘培直通车同步任务')).after['records']==2
        assert db.get(Task,out['tasks'][0]['id']).payload['origin']=='ledger'
    # Non-admin / other connections refused.
    mid=next(x['connection'] for x in client2.get('/api/connections/catalog').json()['items'] if x['connection']['code']=='middle')
    assert client2.get(f"/api/connections/{mid['id']}/ledger-sync/preview",params=params).status_code==422
    auth(client2,'depthead');assert client2.get(f"/api/connections/{p['id']}/ledger-sync/preview",params=params).status_code==403


def test_master_types_and_only_archived_assessments(client2,app2):
    x=make_assessment(client2);p=province(client2)
    for t,keys in [('training_project',['project:P1','project:P2']),('course',['course:C1']),('class',['class:CLP1','class:CLP2']),('teaching',['teaching:rec1','teaching:rec2']),('participants',['participants:rec1','participants:rec2'])]:
        r=client2.get(f"/api/connections/{p['id']}/ledger-sync/preview",params={'data_type':t,'period_id':'period2026'});assert r.status_code==200,r.text
        assert [s['business_key'] for s in r.json()['sample']]==keys
    pv=client2.get(f"/api/connections/{p['id']}/ledger-sync/preview",params={'data_type':'assessment_result','period_id':'period2026'}).json()
    assert pv['count']==0  # computed but not archived => not reported
    ident=x['id'];version=x['version']
    for username in ['teacher','depthead','collegehead','schooladmin']:
        auth(client2,username);version=post(client2,f'/api/assessments/{ident}/actions',{'action':'confirm','expected_version':version,**REASON}).json()['version']
    r=post(client2,f'/api/assessments/{ident}/actions',{'action':'archive','expected_version':version,**REASON});assert r.status_code==200
    pv=client2.get(f"/api/connections/{p['id']}/ledger-sync/preview",params={'data_type':'assessment_result','period_id':'period2026'}).json()
    assert pv['count']==1 and pv['sample'][0]['business_key']=='assessment:'+ident and pv['sample'][0]['score']=='100.00' and pv['sample'][0]['archive_sha256']
