from datetime import timedelta
from sqlalchemy import select
from sqlalchemy.orm import Session
from conftest import auth,post,put
from app.models import Connection,Task,User,utcnow
from app.integrations import ADAPTERS
from app.inbound_sync import IntegrationSchedule,enqueue_due_schedules,process_pull_task_once
from app.reference_data import InboundBatch,TrainingProjectMaster,TeacherHrProfile


class PullAdapter:
    def __init__(self,responses=None,failures=0):
        self.responses=list(responses or [])
        self.failures=failures
        self.calls=[]
    def pull(self,*,data_type,mode,cursor,limit):
        self.calls.append({'data_type':data_type,'mode':mode,'cursor':cursor,'limit':limit})
        if len(self.calls)<=self.failures:
            raise RuntimeError('synthetic pull failure')
        if self.responses:
            return self.responses.pop(0)
        return {'records':[],'next_cursor':cursor}


def middle(client):
    return next(x for x in client.get('/api/connections').json()['items'] if x['code']=='middle')


def configure_project_mapping(client):
    c=middle(client)
    r=put(client,'/api/connections/'+c['id'],{
      'mappings':[
        {'data_type':'training_project','source':'project_code','target':'code','transform':'text','required':True,'default':None},
        {'data_type':'training_project','source':'project_name','target':'name','transform':'text','required':True,'default':None},
        {'data_type':'training_project','source':'active','target':'active','transform':'bool','required':False,'default':True},
      ],
      'config':{'endpoint':'https://school.example/api','owner':'学校数据中心','retry_count':3,'secret_env':'ND_MIDDLE_TOKEN','frequency_minutes':30,'auth_mode':'token'},
      'expected_version':c['version'],'reason':'配置项目入站映射','basis':'隔离测试'})
    assert r.status_code==200,r.text
    return r.json()


def set_connected(app2,connection_id):
    with Session(app2.state.engine) as db:
        c=db.get(Connection,connection_id);c.state='CONNECTED';db.commit()


def test_manual_pull_not_connected_is_blocked_without_adapter_call(client2,app2):
    auth(client2,'schooladmin');c=configure_project_mapping(client2)
    adapter=PullAdapter([{'records':[{'project_code':'P100','project_name':'项目100'}],'next_cursor':'c1'}])
    ADAPTERS.register_for_test('middle',adapter)
    try:
        r=post(client2,'/api/connections/'+c['id']+'/inbound/pull',{'data_type':'training_project','mode':'FULL','reason':'人工全量拉取','basis':'隔离测试'})
        assert r.status_code==200,r.text
        assert r.json()['state']=='BLOCKED'
        assert adapter.calls==[]
        with Session(app2.state.engine) as db:
            task=db.get(Task,r.json()['id']);assert task.attempts==1 and '未真实连接' in task.error
            assert db.query(InboundBatch).count()==0
    finally:ADAPTERS.clear()


def test_connected_manual_pull_creates_preview_and_requires_explicit_confirmation(client2,app2):
    auth(client2,'schooladmin');c=configure_project_mapping(client2);set_connected(app2,c['id'])
    adapter=PullAdapter([{'records':[{'project_code':'P101','project_name':'项目101','active':True}],'next_cursor':'cursor-1'}])
    ADAPTERS.register_for_test('middle',adapter)
    try:
        r=post(client2,'/api/connections/'+c['id']+'/inbound/pull',{'data_type':'training_project','mode':'FULL','reason':'人工全量拉取','basis':'隔离测试'})
        assert r.status_code==200,r.text;task_id=r.json()['id']
        with Session(app2.state.engine) as db:
            task=db.get(Task,task_id);process_pull_task_once(db,task,ADAPTERS);db.commit()
        with Session(app2.state.engine) as db:
            task=db.get(Task,task_id);batch=db.get(InboundBatch,task.result['batch_id'])
            assert task.state=='DONE' and task.result['requires_confirmation'] is True and task.result['committed'] is False
            assert batch.state=='PREVIEW' and batch.errors==0
            assert db.scalar(select(TrainingProjectMaster).where(TrainingProjectMaster.code=='P101')) is None
        assert adapter.calls==[{'data_type':'training_project','mode':'FULL','cursor':None,'limit':1000}]
    finally:ADAPTERS.clear()


def test_active_schedule_requires_connected_adapter_and_explicit_auto_commit(client2,app2):
    auth(client2,'schooladmin');c=configure_project_mapping(client2)
    payload={'connection_id':c['id'],'data_type':'training_project','frequency_minutes':30,'auto_commit':True,'active':True,'reason':'启用定时计划','basis':'隔离测试'}
    r=post(client2,'/api/integration-schedules',payload)
    assert r.status_code==409 and '真实连接' in r.text
    set_connected(app2,c['id'])
    r=post(client2,'/api/integration-schedules',payload)
    assert r.status_code==409 and '拉取适配器' in r.text
    adapter=PullAdapter()
    ADAPTERS.register_for_test('middle',adapter)
    try:
        bad=dict(payload,auto_commit=False)
        r=post(client2,'/api/integration-schedules',bad)
        assert r.status_code==409 and '自动确认' in r.text
        r=post(client2,'/api/integration-schedules',payload)
        assert r.status_code==200,r.text
        assert r.json()['active'] is True and r.json()['auto_commit'] is True
    finally:ADAPTERS.clear()


def test_due_schedule_first_full_then_incremental_and_cursor_advances(client2,app2):
    auth(client2,'schooladmin');c=configure_project_mapping(client2);set_connected(app2,c['id'])
    adapter=PullAdapter([
      {'records':[{'project_code':'P201','project_name':'项目201','active':True}],'next_cursor':'cursor-1'},
      {'records':[],'next_cursor':'cursor-2'},
    ])
    ADAPTERS.register_for_test('middle',adapter)
    try:
        r=post(client2,'/api/integration-schedules',{'connection_id':c['id'],'data_type':'training_project','frequency_minutes':30,'auto_commit':True,'active':True,'reason':'批准自动入库','basis':'隔离测试'})
        assert r.status_code==200,r.text;sid=r.json()['id']
        now=utcnow()
        with Session(app2.state.engine) as db:
            sch=db.get(IntegrationSchedule,sid);sch.next_at=now-timedelta(seconds=1);db.commit()
        with Session(app2.state.engine) as db:
            ids=enqueue_due_schedules(db,now);assert len(ids)==1;db.commit();first_id=ids[0]
        with Session(app2.state.engine) as db:
            t=db.get(Task,first_id);process_pull_task_once(db,t,ADAPTERS);db.commit()
        with Session(app2.state.engine) as db:
            sch=db.get(IntegrationSchedule,sid);proj=db.scalar(select(TrainingProjectMaster).where(TrainingProjectMaster.code=='P201'))
            assert proj and sch.last_cursor=='cursor-1' and sch.last_run_at is not None
            sch.next_at=utcnow()-timedelta(seconds=1);db.commit()
        with Session(app2.state.engine) as db:
            ids=enqueue_due_schedules(db,utcnow());assert len(ids)==1;db.commit();second_id=ids[0]
        with Session(app2.state.engine) as db:
            t=db.get(Task,second_id);process_pull_task_once(db,t,ADAPTERS);db.commit()
        with Session(app2.state.engine) as db:
            sch=db.get(IntegrationSchedule,sid);t=db.get(Task,second_id)
            assert t.state=='DONE' and t.result['records']==0 and t.result['committed'] is True
            assert sch.last_cursor=='cursor-2'
        assert [x['mode'] for x in adapter.calls]==['FULL','INCREMENTAL']
        assert adapter.calls[1]['cursor']=='cursor-1'
    finally:ADAPTERS.clear()


def test_data_quality_error_keeps_formal_master_unchanged(client2,app2):
    auth(client2,'schooladmin');c=configure_project_mapping(client2);set_connected(app2,c['id'])
    adapter=PullAdapter([{'records':[{'project_code':'P_BAD'}],'next_cursor':'bad-cursor'}])
    ADAPTERS.register_for_test('middle',adapter)
    try:
        r=post(client2,'/api/connections/'+c['id']+'/inbound/pull',{'data_type':'training_project','mode':'INCREMENTAL','reason':'质量错误测试','basis':'隔离测试'})
        assert r.status_code==200;rj=r.json()
        with Session(app2.state.engine) as db:
            t=db.get(Task,rj['id']);process_pull_task_once(db,t,ADAPTERS);db.commit()
        with Session(app2.state.engine) as db:
            t=db.get(Task,rj['id']);batch=db.get(InboundBatch,t.result['batch_id'])
            assert t.state=='FAILED' and batch.errors==1 and batch.state=='PREVIEW'
            assert db.scalar(select(TrainingProjectMaster).where(TrainingProjectMaster.code=='P_BAD')) is None
    finally:ADAPTERS.clear()


def test_schedule_auto_disables_when_approver_account_loses_authority(client2,app2):
    auth(client2,'schooladmin');c=configure_project_mapping(client2);set_connected(app2,c['id'])
    adapter=PullAdapter()
    ADAPTERS.register_for_test('middle',adapter)
    try:
        r=post(client2,'/api/integration-schedules',{'connection_id':c['id'],'data_type':'training_project','frequency_minutes':30,'auto_commit':True,'active':True,'reason':'批准计划','basis':'隔离测试'})
        assert r.status_code==200;sid=r.json()['id']
        with Session(app2.state.engine) as db:
            db.get(User,'schooladmin').active=False
            sch=db.get(IntegrationSchedule,sid);sch.next_at=utcnow()-timedelta(seconds=1);db.commit()
        with Session(app2.state.engine) as db:
            ids=enqueue_due_schedules(db,utcnow());assert ids==[];db.commit()
        with Session(app2.state.engine) as db:
            sch=db.get(IntegrationSchedule,sid);assert sch.active is False and '批准人' in sch.last_error
            assert db.scalar(select(Task.id).where(Task.kind=='inbound_pull')) is None
    finally:ADAPTERS.clear()


def test_integration_task_list_and_detail_include_inbound_pull(client2,app2):
    auth(client2,'schooladmin');c=configure_project_mapping(client2)
    r=post(client2,'/api/connections/'+c['id']+'/inbound/pull',{'data_type':'training_project','mode':'FULL','reason':'任务中心测试','basis':'隔离测试'})
    assert r.status_code==200;tid=r.json()['id']
    listing=client2.get('/api/tasks?kind=integration&size=50')
    assert listing.status_code==200 and any(x['id']==tid and x['kind']=='inbound_pull' for x in listing.json()['items'])
    detail=client2.get('/api/tasks/'+tid)
    assert detail.status_code==200 and detail.json()['task']['kind']=='inbound_pull'
    auth(client2,'teacher')
    assert client2.get('/api/tasks/'+tid).status_code==403

def test_schedule_auto_disables_when_approver_role_is_downgraded(client2,app2):
    auth(client2,'schooladmin');c=configure_project_mapping(client2);set_connected(app2,c['id'])
    adapter=PullAdapter();ADAPTERS.register_for_test('middle',adapter)
    try:
        r=post(client2,'/api/integration-schedules',{'connection_id':c['id'],'data_type':'training_project','frequency_minutes':30,'auto_commit':True,'active':True,'reason':'批准计划','basis':'隔离测试'})
        assert r.status_code==200;sid=r.json()['id']
        with Session(app2.state.engine) as db:
            u=db.get(User,'schooladmin');u.role_id='role-college';u.is_admin=False
            sch=db.get(IntegrationSchedule,sid);sch.next_at=utcnow()-timedelta(seconds=1);db.commit()
        with Session(app2.state.engine) as db:
            assert enqueue_due_schedules(db,utcnow())==[];db.commit()
        with Session(app2.state.engine) as db:
            sch=db.get(IntegrationSchedule,sid);assert sch.active is False and '权限失效' in sch.last_error
    finally:ADAPTERS.clear()


def test_schedule_auto_disables_when_connection_drops(client2,app2):
    auth(client2,'schooladmin');c=configure_project_mapping(client2);set_connected(app2,c['id'])
    adapter=PullAdapter();ADAPTERS.register_for_test('middle',adapter)
    try:
        r=post(client2,'/api/integration-schedules',{'connection_id':c['id'],'data_type':'training_project','frequency_minutes':30,'auto_commit':True,'active':True,'reason':'批准计划','basis':'隔离测试'})
        assert r.status_code==200;sid=r.json()['id']
        with Session(app2.state.engine) as db:
            db.get(Connection,c['id']).state='NOT_CONNECTED'
            sch=db.get(IntegrationSchedule,sid);sch.next_at=utcnow()-timedelta(seconds=1);db.commit()
        with Session(app2.state.engine) as db:
            assert enqueue_due_schedules(db,utcnow())==[];db.commit()
        with Session(app2.state.engine) as db:
            sch=db.get(IntegrationSchedule,sid);assert sch.active is False and 'CONNECTED' in sch.last_error
    finally:ADAPTERS.clear()
