"""Recovery, replay and master identity regression contracts (synthetic only)."""
from datetime import datetime,timedelta
import pytest
from fastapi import HTTPException
from sqlalchemy import select,func
from conftest import auth,post,put
from test_r3_excel import fill_template,upload_preview,REASON
from test_r8_regressions import setup,scheduled,Adapter,record
from test_r5_closeout import run_due_sync
from app.models import Task,User,Role,Connection,ImportJob,ImportRow,TrainingRecord,utcnow
from app.sync_policy import retry_sync_items,retry_pull_task,invalidate_schedule_tasks
from app.integrations import enqueue_sync,SyncItem,SyncCallLog,finalize_sync_task
from app.inbound_sync import create_pull_task,process_pull_task_once,_actor
from app.reference_data import (TeacherHrProfile,TrainingCourseMaster,TrainingProjectMaster,TeacherParticipation,
    preview_inbound,confirm_inbound,record_reference_errors,ensure_reference_from_training_record)


def test_mixed_failed_and_waiting_rows_do_not_strand_unfinished_work(app2):
    with app2.state.sessions() as db:
        a,c,r=setup(db);task=enqueue_sync(db,a,c,'training_project',[{'business_key':k,'code':k,'name':k} for k in ('P81','P82')]);db.flush()
        items=db.scalars(select(SyncItem).where(SyncItem.task_id==task.id).order_by(SyncItem.business_key)).all()
        items[0].state='FAILED';items[0].attempts=4
        finalize_sync_task(db,task)
        assert task.state=='RETRY' and task.result['failed']==1 and task.result['waiting']==1
        run_due_sync(db,task,r)
        assert items[1].state=='DONE' and task.state=='FAILED'


def test_worker_failure_with_pending_rows_can_be_explicitly_resumed(app2):
    with app2.state.sessions() as db:
        a,c,r=setup(db);task=enqueue_sync(db,a,c,'training_project',[{'business_key':'P81','code':'P81','name':'P81'}]);db.flush()
        task.state='FAILED';task.error='WORKER_EXECUTOR_ERROR:RuntimeError'
        item=db.scalar(select(SyncItem).where(SyncItem.task_id==task.id));key=item.idempotency_key
        retry_sync_items(db,a,task,'执行器异常后人工核对补传');run_due_sync(db,task,r)
        assert task.state=='DONE' and item.idempotency_key==key


def test_manual_retry_uses_new_cycle_without_losing_historical_attempts(app2):
    with app2.state.sessions() as db:
        adapter=Adapter(fail=True);a,c,r=setup(db,adapter=adapter)
        task=enqueue_sync(db,a,c,'training_project',[{'business_key':'P81','code':'P81','name':'P81'}]);db.flush()
        item=db.scalar(select(SyncItem).where(SyncItem.task_id==task.id));key=item.idempotency_key
        for _ in range(4):item.next_at=utcnow();run_due_sync(db,task,r);db.flush()
        assert task.state=='FAILED'
        retry_sync_items(db,a,task,'经确认重新尝试');db.flush()
        for _ in range(3):item.next_at=utcnow();run_due_sync(db,task,r);db.flush()
        assert task.state=='RETRY' and item.attempts==7
        adapter.fail=False;item.next_at=utcnow();run_due_sync(db,task,r);db.flush()
        assert task.state=='DONE' and item.attempts==8 and key==item.idempotency_key
        assert list(db.scalars(select(SyncCallLog.attempt).where(SyncCallLog.item_id==item.id).order_by(SyncCallLog.attempt)))==list(range(1,9))
        assert len({x['idempotency_key'] for x in adapter.calls})==1


def test_reused_failed_rows_retry_original_parent_not_successful_siblings(app2):
    with app2.state.sessions() as db:
        adapter=Adapter();a,c,r=setup(db,adapter=adapter)
        records=[{'business_key':k,'code':k,'name':k} for k in ('P81','P82')]
        old=enqueue_sync(db,a,c,'training_project',records);run_due_sync(db,old,r);db.flush()
        items=db.scalars(select(SyncItem).where(SyncItem.task_id==old.id).order_by(SyncItem.business_key)).all()
        items[0].state='FAILED';old.state='FAILED';db.flush()
        wrapper=enqueue_sync(db,a,c,'training_project',records);finalize_sync_task(db,wrapper)
        retry_sync_items(db,a,wrapper,'仅补传失败项');run_due_sync(db,old,r);finalize_sync_task(db,wrapper);db.flush()
        assert old.state==wrapper.state=='DONE'
        assert len(adapter.calls)==3 and items[1].attempts==1


def test_other_admin_can_reauthorize_but_revoked_permissions_cannot_execute(app2):
    with app2.state.sessions() as db:
        a,c,r=setup(db);task=enqueue_sync(db,a,c,'training_project',[{'business_key':'P81','code':'P81','name':'P81'}]);db.flush()
        item=db.scalar(select(SyncItem).where(SyncItem.task_id==task.id));item.state='FAILED';task.state='FAILED'
        original=db.get(User,'schooladmin')
        db.add(User(id='r8-new-admin',username='r8-new-admin',name='合成管理员',org_id=original.org_id,role_id=original.role_id,password_hash=original.password_hash,active=True,is_admin=True,must_change_password=False));db.flush()
        new=_actor(db,'r8-new-admin');retry_sync_items(db,new,task,'明确接管失败补传');original.active=False;db.flush()
        run_due_sync(db,task,r);assert task.state=='DONE' and task.owner_id=='schooladmin'


def test_old_schedule_approval_never_revives_after_disable_and_enable(app2):
    with app2.state.sessions() as db:
        adapter=Adapter();a,c,r=setup(db,adapter=adapter);s=scheduled(db,c);task=create_pull_task(db,a,c,'training_project','FULL',schedule=s)
        invalidate_schedule_tasks(db,s.id,'停用计划');s.active=False;db.flush();s.active=True;db.flush()
        with pytest.raises(HTTPException):retry_pull_task(db,a,task,'不能复活旧授权')
        process_pull_task_once(db,task,r);assert task.state=='BLOCKED' and not adapter.calls


def test_manual_pull_cannot_override_active_worker_lease(app2):
    with app2.state.sessions() as db:
        a,c,r=setup(db);task=create_pull_task(db,a,c,'training_project','FULL');task.state='FAILED';task.lease_token='some-worker';task.lease_until=utcnow()+timedelta(minutes=1)
        with pytest.raises(HTTPException):retry_pull_task(db,a,task,'不能抢占未过期的租约')


def test_equal_hr_timestamp_replay_does_not_reverse_local_suspension(app2):
    with app2.state.sessions() as db:
        a,c,r=setup(db,data_type='teacher_hr')
        data=[{'staff_no':'J001','name':'样本教师','org_code':'dept1','active':'true','source_updated_at':'2026-09-18T18:00:00+08:00'}]
        one=preview_inbound(db,a,c,'teacher_hr',data);confirm_inbound(db,a,one,one.version,'首次源数据');db.flush()
        teacher=db.get(User,'teacher');teacher.active=False;teacher.auth_version+=1;version=teacher.auth_version;db.flush()
        two=preview_inbound(db,a,c,'teacher_hr',data);confirm_inbound(db,a,two,two.version,'重复报文');db.flush()
        assert two.receipt['rows'][0]['unchanged'] is True and teacher.active is False and teacher.auth_version==version

@pytest.mark.parametrize('stamp',['2026-09-18T10:00:00Z','', '2026-09-18T10:00:00'])
def test_conflicting_same_timestamp_missing_stamp_and_naive_time_rejected(app2,stamp):
    with app2.state.sessions() as db:
        a,c,r=setup(db,data_type='teacher_hr')
        db.add(TeacherHrProfile(staff_no='J001',user_id='teacher',name='源数据名称',title='',org_code='dept1',active=True,source_updated_at=datetime(2026,9,18,10),extra={}));db.flush()
        batch=preview_inbound(db,a,c,'teacher_hr',[{'staff_no':'J001','name':'冲突名称','org_code':'dept1','active':'true','source_updated_at':stamp}])
        assert batch.errors==1


def test_explicit_global_course_may_be_used_across_projects(app2):
    with app2.state.sessions() as db:
        db.add(TrainingCourseMaster(code='C8',name='通用课程',project_code=None));db.flush()
        ensure_reference_from_training_record(db,record(class_code='K81'))
        ensure_reference_from_training_record(db,record(project_code='P9',class_code='K82'))
        assert db.scalar(select(TrainingCourseMaster).where(TrainingCourseMaster.code=='C8')).project_code is None


def test_excel_detects_intrabatch_identity_collision(app2):
    with app2.state.sessions() as db:
        pending={};assert record_reference_errors(db,record(),pending=pending)==[]
        assert record_reference_errors(db,record(project_code='P9'),pending=pending)


def test_new_course_binding_cannot_contradict_established_ledger(app2):
    with app2.state.sessions() as db:
        a,c,r=setup(db)
        db.add(TrainingProjectMaster(code='WRONG',name='其他项目'));db.flush()
        # Existing synthetic record uses C001/P001. Read rather than guess.
        old=db.scalar(select(TrainingRecord).limit(1))
        c.mappings=[{'data_type':'course','source':k,'target':k,'transform':'text','required':True} for k in ('code','name','project_code')];db.flush()
        batch=preview_inbound(db,a,c,'course',[{'code':old.course_code,'name':'课程','project_code':'WRONG'}]);assert batch.errors==1


def test_confirm_valid_preview_preserves_checksum_in_receipt(client2,app2):
    auth(client2,'depthead')
    payload=fill_template(client2,'records',['R8-CHECK','J001','2026-09-10','PR8','项目','CR8','课程','KR8','班级',2,10,123,'Excel导入'])
    response=upload_preview(client2,'records',payload);job=response.json();proof=job['receipt']['preview_rows_sha256']
    response=post(client2,f"/api/imports/{job['id']}/confirm",{'expected_version':job['version'],**REASON})
    assert response.status_code==200,response.text
    assert response.json()['receipt']['preview_rows_sha256']==proof and response.json()['receipt']['written']==1
