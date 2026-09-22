"""R8 regressions first executed against unmodified R7; synthetic inputs only."""
from datetime import datetime, timedelta
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from conftest import auth, post
from app.models import Connection, Task, User, Role, Org, utcnow
from app.integrations import AdapterRegistry, enqueue_sync, process_sync_task_once, SyncItem, SyncCallLog, convert
from app.inbound_sync import _actor, create_pull_task, process_pull_task_once, enqueue_due_schedules, IntegrationSchedule
from app.reference_data import (TrainingProjectMaster, TrainingCourseMaster, TrainingClassMaster,
    TeacherHrProfile, preview_inbound, confirm_inbound, ensure_reference_from_training_record)

class Adapter:
    def __init__(self, response=None, fail=False):
        self.calls=[]; self.response=response if response is not None else {'records':[]}; self.fail=fail
    def send(self, **kw):
        self.calls.append(kw)
        if self.fail: raise RuntimeError('synthetic transport failure')
        return {'accepted':True, 'code':'ACK'}
    def pull(self, **kw):
        self.calls.append(kw)
        if self.fail: raise RuntimeError('synthetic transport failure')
        return self.response

def setup(db, *, data_type='training_project', adapter=None):
    a=_actor(db,'schooladmin'); c=db.scalar(select(Connection).where(Connection.code=='middle'))
    c.state='CONNECTED';c.config={'retry_count':3}
    fields=('staff_no','name','title','org_code','active','source_updated_at') if data_type=='teacher_hr' else ('code','name')
    c.mappings=[{'data_type':data_type,'source':n,'target':n,'transform':'text','required':False} for n in fields]
    registry=AdapterRegistry();registry.register_for_test('middle',adapter or Adapter());db.flush()
    return a,c,registry

def scheduled(db, c):
    s=IntegrationSchedule(connection_id=c.id,data_type='training_project',frequency_minutes=30,
        auto_commit=True,active=True,approved_by='schooladmin',next_at=utcnow()-timedelta(seconds=1))
    db.add(s);db.flush();return s

def test_pdf_three_retries_are_in_addition_to_initial_call(app2):
    with Session(app2.state.engine) as db:
        adapter=Adapter(fail=True);a,c,r=setup(db,adapter=adapter)
        t=enqueue_sync(db,a,c,'training_project',[{'business_key':'P8','code':'P8','name':'合成项目'}]);db.flush()
        for _ in range(3):
            for x in db.scalars(select(SyncItem).where(SyncItem.task_id==t.id)): x.next_at=utcnow()
            process_sync_task_once(db,t,r);db.flush()
        assert t.state=='RETRY', 'initial call + only two retries must not exhaust 3 retries'
        for x in db.scalars(select(SyncItem).where(SyncItem.task_id==t.id)): x.next_at=utcnow()
        process_sync_task_once(db,t,r);db.flush()
        assert t.state=='FAILED' and len(adapter.calls)==4
        assert list(db.scalars(select(SyncCallLog.attempt).order_by(SyncCallLog.attempt)))==[1,2,3,4]

def test_removed_sync_permission_stops_queued_send(app2):
    with Session(app2.state.engine) as db:
        adapter=Adapter();a,c,r=setup(db,adapter=adapter)
        t=enqueue_sync(db,a,c,'training_project',[{'business_key':'P8','code':'P8','name':'合成项目'}]);db.flush()
        role=db.get(Role,'role-school');role.permissions=[x for x in role.permissions if x!='sync.manage'];db.flush()
        process_sync_task_once(db,t,r)
        assert t.state=='BLOCKED' and not adapter.calls

def test_removed_sync_permission_stops_queued_pull(app2):
    with Session(app2.state.engine) as db:
        adapter=Adapter();a,c,r=setup(db,adapter=adapter)
        t=create_pull_task(db,a,c,'training_project','FULL');db.flush()
        role=db.get(Role,'role-school');role.permissions=[x for x in role.permissions if x!='sync.manage'];db.flush()
        process_pull_task_once(db,t,r)
        assert t.state=='BLOCKED' and not adapter.calls

def test_failed_first_full_does_not_mark_incremental_initialization(app2):
    with Session(app2.state.engine) as db:
        a,c,r=setup(db,adapter=Adapter({'records':[{'code':'P8'}],'next_cursor':'bad-cursor'}))
        s=scheduled(db,c);t=create_pull_task(db,a,c,'training_project','FULL',schedule=s);db.flush()
        process_pull_task_once(db,t,r);db.flush()
        assert t.state=='FAILED'
        assert s.last_run_at is None and s.last_cursor is None
        s.next_at=utcnow()-timedelta(seconds=1)
        ids=enqueue_due_schedules(db,registry=r);db.flush();assert len(ids)==1
        assert db.get(Task,ids[0]).payload['mode']=='FULL'

def test_old_pending_schedule_outside_recent_500_prevents_overlap(app2):
    with Session(app2.state.engine) as db:
        a,c,r=setup(db);s=scheduled(db,c)
        old=create_pull_task(db,a,c,'training_project','FULL',schedule=s);old.created_at=utcnow()-timedelta(days=2)
        for i in range(501):db.add(Task(kind='inbound_pull',owner_id=a.id,key=f'r8-other-{i}',payload={'schedule_id':'other'},state='PENDING'))
        db.flush()
        assert enqueue_due_schedules(db,registry=r)==[]

def test_generic_task_retry_requeues_failed_sync_items(client2,app2):
    auth(client2,'schooladmin')
    with Session(app2.state.engine) as db:
        a,c,r=setup(db);t=enqueue_sync(db,a,c,'training_project',[{'business_key':'P8','code':'P8','name':'合成项目'}]);db.flush()
        x=db.scalar(select(SyncItem).where(SyncItem.task_id==t.id));x.state='FAILED';x.attempts=4;t.state='FAILED';ident=t.id;version=t.version;db.commit()
    response=post(client2,'/api/tasks/'+ident+'/retry',{'expected_version':version,'reason':'人工补传核对','basis':'合成样本'})
    assert response.status_code==200,response.text
    with Session(app2.state.engine) as db:
        x=db.scalar(select(SyncItem).where(SyncItem.task_id==ident))
        assert x.state=='RETRY', 'retry must reset rows, not only the parent task'
        assert x.attempts==4, 'retain monotonically increasing historical attempt numbers'

@pytest.mark.parametrize('kind,value',[('int',1.5),('int',True),('decimal','NaN'),('decimal','Infinity')])
def test_mapping_rejects_lossy_or_nonfinite_numbers(kind,value):
    with pytest.raises(ValueError):convert(value,kind)

def test_timestamp_offset_is_converted_to_utc_not_removed(app2):
    with Session(app2.state.engine) as db:
        a,c,r=setup(db,data_type='teacher_hr')
        batch=preview_inbound(db,a,c,'teacher_hr',[{'staff_no':'J001','name':'测试教师一','org_code':'dept1','active':'true','source_updated_at':'2026-09-18T18:00:00+08:00'}]);db.flush()
        confirm_inbound(db,a,batch,batch.version,'来源时间测试');db.flush()
        profile=db.scalar(select(TeacherHrProfile).where(TeacherHrProfile.staff_no=='J001'))
        assert profile.source_updated_at==datetime(2026,9,18,10,0,0)

def test_stale_hr_payload_cannot_reactivate_or_move_teacher(app2):
    with Session(app2.state.engine) as db:
        a,c,r=setup(db,data_type='teacher_hr')
        db.add(TeacherHrProfile(staff_no='J001',user_id='teacher',name='新名称',title='',org_code='dept2',active=False,source_updated_at=datetime(2026,9,18,10),extra={}));db.flush()
        batch=preview_inbound(db,a,c,'teacher_hr',[{'staff_no':'J001','name':'旧名称','org_code':'dept1','active':'true','source_updated_at':'2026-09-17T10:00:00Z'}]);db.flush()
        assert batch.errors==1
        with pytest.raises(HTTPException):confirm_inbound(db,a,batch,batch.version,'不应允许覆盖')

def test_hr_preview_rejects_disabled_ancestor(app2):
    with Session(app2.state.engine) as db:
        a,c,r=setup(db,data_type='teacher_hr');db.get(Org,'college1').active=False;db.flush()
        batch=preview_inbound(db,a,c,'teacher_hr',[{'staff_no':'J001','name':'样本','org_code':'dept1','active':'true'}]);db.flush()
        assert batch.errors==1

def record(**changes):
    values={'project_code':'P8','project':'流水历史名称','course_code':'C8','course':'流水课程名称','class_code':'K8','class_name':'流水班级名称'}
    return SimpleNamespace(**(values|changes))

def test_financial_record_cannot_reparent_course_master(app2):
    with Session(app2.state.engine) as db:
        db.add_all([TrainingProjectMaster(code='P8',name='项目8'),TrainingCourseMaster(code='C8',name='课程8',project_code='OTHER')]);db.flush()
        with pytest.raises(HTTPException):ensure_reference_from_training_record(db,record())

def test_financial_record_cannot_reparent_class_master(app2):
    with Session(app2.state.engine) as db:
        db.add(TrainingClassMaster(code='K8',name='班8',project_code='OTHER',course_code='OTHER'));db.flush()
        with pytest.raises(HTTPException):ensure_reference_from_training_record(db,record())

def test_financial_record_preserves_verified_master_names(app2):
    with Session(app2.state.engine) as db:
        p=TrainingProjectMaster(code='P8',name='学校确认名称',source='学校数据中台');db.add(p);db.flush()
        ensure_reference_from_training_record(db,record())
        assert p.name=='学校确认名称'
