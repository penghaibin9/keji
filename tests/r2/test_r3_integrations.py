from sqlalchemy.orm import Session
from sqlalchemy import select
from conftest import auth,post,put
from app.models import Connection,Task
from app.integrations import SyncItem,SyncCallLog,ADAPTERS,process_sync_task_once

class FailingAdapter:
    def __init__(self,failures=99):self.calls=[];self.failures=failures
    def send(self,*,data_type,payload,idempotency_key):
        self.calls.append((data_type,payload,idempotency_key))
        if len(self.calls)<=self.failures:raise RuntimeError('synthetic upstream failure')
        return {'code':'200','accepted':True}


def middle(client):
    d=client.get('/api/connections').json()['items']
    return next(x for x in d if x['code']=='middle')


def test_catalog_lists_procurement_data_types_without_fake_connection(client2):
    auth(client2,'schooladmin')
    r=client2.get('/api/connections/catalog');assert r.status_code==200
    item=next(x for x in r.json()['items'] if x['connection']['code']=='province')
    assert len(item['data_types'])==11
    assert all(x['connection_state']=='NOT_CONNECTED' for x in item['data_types'])
    assert any(x['data_type']=='certificate' and x['local_status']=='WAITING_SOURCE' for x in item['data_types'])


def test_mapping_update_resets_not_connected_and_local_validation_never_calls_external(client2):
    auth(client2,'schooladmin');c=middle(client2)
    r=put(client2,'/api/connections/'+c['id'],{
      'mappings':[{'source':'teacher_no','target':'staff_no','transform':'text','required':True,'default':None}],
      'config':{'endpoint':'https://school.example/api','owner':'学校数据中心','retry_count':3,'secret_env':'ND_MIDDLE_TOKEN','frequency_minutes':30,'auth_mode':'token'},
      'expected_version':c['version'],'reason':'配置字段映射','basis':'隔离测试'})
    assert r.status_code==200,r.text;assert r.json()['state']=='NOT_CONNECTED'
    r=post(client2,'/api/connections/validate',{'connection_id':c['id'],'data_type':'teacher_hr','records':[{'teacher_no':'J001'}],'reason':'本地映射校验','basis':'不调用外部接口'})
    assert r.status_code==200,r.text;body=r.json();assert body['external_called'] is False and body['items'][0]['mapped']['staff_no']=='J001'


def test_manual_sync_stays_blocked_while_not_connected(client2,app2):
    auth(client2,'schooladmin');c=middle(client2)
    # prepare mapping so payload can be normalized
    put(client2,'/api/connections/'+c['id'],{'mappings':[{'source':'teacher_no','target':'staff_no','transform':'text','required':True,'default':None}],
      'config':{'endpoint':'https://school.example/api','owner':'学校','retry_count':3,'secret_env':'ND_TOKEN','frequency_minutes':30,'auth_mode':'token'},
      'expected_version':c['version'],'reason':'配置','basis':'测试'})
    c=middle(client2)
    r=post(client2,'/api/connections/'+c['id']+'/sync',{'data_type':'teacher_hr','records':[{'business_key':'teacher:J001','teacher_no':'J001'}],'reason':'人工补传','basis':'测试'})
    assert r.status_code==200,r.text;task=r.json();assert task['state']=='BLOCKED'
    with Session(app2.state.engine) as db:
        item=db.scalar(select(SyncItem).where(SyncItem.task_id==task['id']));assert item.state=='BLOCKED' and item.attempts==0
        assert db.query(SyncCallLog).count()==0


def test_sync_retries_at_least_three_times_and_logs_each_call(client2,app2):
    auth(client2,'schooladmin');c=middle(client2)
    put(client2,'/api/connections/'+c['id'],{'mappings':[{'source':'teacher_no','target':'staff_no','transform':'text','required':True,'default':None}],
      'config':{'endpoint':'https://school.example/api','owner':'学校','retry_count':3,'secret_env':'ND_TOKEN','frequency_minutes':30,'auth_mode':'token'},
      'expected_version':c['version'],'reason':'配置','basis':'测试'})
    with Session(app2.state.engine) as db:
        conn=db.get(Connection,c['id']);conn.state='CONNECTED';db.commit()
    c=middle(client2)
    r=post(client2,'/api/connections/'+c['id']+'/sync',{'data_type':'teacher_hr','records':[{'business_key':'teacher:J001','teacher_no':'J001'}],'reason':'同步测试','basis':'测试'})
    assert r.status_code==200;rj=r.json();assert rj['state']=='PENDING'
    adapter=FailingAdapter();ADAPTERS.register_for_test('middle',adapter)
    try:
        # PDF 11.4: initial call plus at least THREE retries.
        for _ in range(4):
            with Session(app2.state.engine) as db:
                task=db.get(Task,rj['id']);
                item=db.scalar(select(SyncItem).where(SyncItem.task_id==task.id));item.next_at=task.next_at=__import__('app.models',fromlist=['utcnow']).utcnow()
                process_sync_task_once(db,task,ADAPTERS);db.commit()
                # make scheduled retry due immediately for the next explicit worker tick
                item=db.scalar(select(SyncItem).where(SyncItem.task_id==task.id));item.next_at=task.next_at=__import__('app.models',fromlist=['utcnow']).utcnow()
                item.next_at=__import__('app.models',fromlist=['utcnow']).utcnow();db.commit()
        with Session(app2.state.engine) as db:
            task=db.get(Task,rj['id']);item=db.scalar(select(SyncItem).where(SyncItem.task_id==task.id));logs=db.scalars(select(SyncCallLog).where(SyncCallLog.item_id==item.id).order_by(SyncCallLog.attempt)).all()
            assert item.state=='FAILED' and item.attempts==4 and task.state=='FAILED'
            assert [x.attempt for x in logs]==[1,2,3,4]
            assert len(adapter.calls)==4 and len({x[2] for x in adapter.calls})==1
    finally:ADAPTERS.clear()


def test_exact_same_business_payload_is_idempotent(client2,app2):
    auth(client2,'schooladmin');c=middle(client2)
    put(client2,'/api/connections/'+c['id'],{'mappings':[{'source':'teacher_no','target':'staff_no','transform':'text','required':True,'default':None}],
      'config':{'endpoint':'https://school.example/api','owner':'学校','retry_count':3,'secret_env':'ND_TOKEN','frequency_minutes':30,'auth_mode':'token'},
      'expected_version':c['version'],'reason':'配置','basis':'测试'})
    with Session(app2.state.engine) as db:db.get(Connection,c['id']).state='CONNECTED';db.commit()
    payload={'data_type':'teacher_hr','records':[{'business_key':'teacher:J001','teacher_no':'J001'}],'reason':'同步测试','basis':'测试'}
    a=post(client2,'/api/connections/'+c['id']+'/sync',payload,key='syncsamekey1');assert a.status_code==200
    b=post(client2,'/api/connections/'+c['id']+'/sync',payload,key='syncsamekey2');assert b.status_code==200
    with Session(app2.state.engine) as db:
        assert db.query(SyncItem).count()==1

def test_school_cockpit_sync_summary_uses_real_connection_and_latest_task_state(client2):
    auth(client2,'schooladmin');c=middle(client2)
    put(client2,'/api/connections/'+c['id'],{'mappings':[{'source':'teacher_no','target':'staff_no','transform':'text','required':True,'default':None}],
      'config':{'endpoint':'https://school.example/api','owner':'学校','retry_count':3,'secret_env':'ND_TOKEN','frequency_minutes':30,'auth_mode':'token'},
      'expected_version':c['version'],'reason':'配置','basis':'测试'})
    c=middle(client2)
    task=post(client2,'/api/connections/'+c['id']+'/sync',{'data_type':'teacher_hr','records':[{'business_key':'teacher:J001','teacher_no':'J001'}],'reason':'驾驶舱状态测试','basis':'测试'}).json()
    r=client2.get('/api/connections/summary');assert r.status_code==200,r.text
    item=next(x for x in r.json()['items'] if x['code']=='middle')
    assert item['connection_state']=='NOT_CONNECTED'
    assert item['latest_task']['id']==task['id'] and item['latest_task']['state']=='BLOCKED'
    assert item['latest_task']['success_count']==0 and item['latest_task']['failed_count']==1
    auth(client2,'teacher');assert client2.get('/api/connections/summary').status_code==403

def test_sso_is_registered_for_identity_mapping_preparation_without_fake_login(client2):
    auth(client2,'schooladmin')
    items=client2.get('/api/connections/catalog').json()['items']
    sso=next(x for x in items if x['connection']['code']=='sso')
    assert sso['connection']['state']=='NOT_CONNECTED'
    assert [x['data_type'] for x in sso['data_types']]==['identity']
    assert sso['data_types'][0]['local_status']=='WAITING_PROTOCOL'
    # A local field-mapping check is allowed; it still never invokes an external SSO endpoint.
    c=sso['connection']
    r=put(client2,'/api/connections/'+c['id'],{
      'mappings':[{'data_type':'identity','source':'uid','target':'external_subject','transform':'text','required':True,'default':None}],
      'config':{'endpoint':'https://sso.school.example/auth','owner':'学校信息中心','retry_count':3,'secret_env':'ND_SSO_SECRET','frequency_minutes':30,'auth_mode':'school_sso','adapter':{'identity_fields':{'stable_id':'uid','account':'account','name':'name','active':'active'}}},
      'expected_version':c['version'],'reason':'统一认证字段准备','basis':'只做本地映射，不调用外部'})
    assert r.status_code==200 and r.json()['state']=='NOT_CONNECTED'
    v=post(client2,'/api/connections/validate',{'connection_id':c['id'],'data_type':'identity','records':[{'uid':'U001','account':'teacher','name':'合成教师','active':True}],'reason':'本地映射检查','basis':'不调用外部'})
    assert v.status_code==200 and v.json()['external_called'] is False and v.json()['items'][0]['mapped']['stable_id']=='U001'
    assert v.json()['items'][0]['binding']['role_kind']=='teacher'
    assert v.json()['items'][0]['session_created'] is False

def test_connection_mapping_rejects_data_type_outside_its_procurement_catalog(client2):
    auth(client2,'schooladmin')
    sso=next(x for x in client2.get('/api/connections').json()['items'] if x['code']=='sso')
    r=put(client2,'/api/connections/'+sso['id'],{
      'mappings':[{'data_type':'teacher_hr','source':'uid','target':'external_subject','transform':'text','required':True,'default':None}],
      'config':{'endpoint':'https://sso.school.example/auth','owner':'学校信息中心','retry_count':3,'secret_env':'ND_SSO_SECRET','frequency_minutes':30,'auth_mode':'school_sso'},
      'expected_version':sso['version'],'reason':'错误目录测试','basis':'隔离测试'})
    assert r.status_code==422 and '不属于当前接口采购目录' in r.text


def test_local_mapping_validation_rejects_empty_mapping_for_selected_data_type(client2):
    auth(client2,'schooladmin');c=middle(client2)
    r=post(client2,'/api/connections/validate',{'connection_id':c['id'],'data_type':'teacher_hr','records':[{'teacher_no':'J001'}],'reason':'空映射测试','basis':'隔离测试'})
    assert r.status_code==409 and '尚未配置字段映射' in r.text
