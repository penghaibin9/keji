"""R8 import/worker boundaries: isolated synthetic database only."""
from datetime import timedelta
import json
import pytest
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from conftest import auth,post
from test_r3_excel import fill_template,upload_preview,REASON
from test_r8_regressions import setup,scheduled,Adapter
from app.models import ImportJob,ImportRow,TrainingRecord,Task,TaskAttempt,utcnow
from app.worker import run_once
from app.integrations import normalize_mapping
from app.inbound_sync import create_pull_task,process_pull_task_once
from app.reference_data import TrainingCourseMaster


def preview_one(client):
    auth(client,'depthead')
    data=fill_template(client,'records',['R8-X1','J001','2026-09-10','PR8','项目','CR8','课程','KR8','班级',2,10,123,'Excel导入'])
    response=upload_preview(client,'records',data)
    assert response.status_code==200,response.text
    assert response.json()['errors']==0
    return response.json()

@pytest.mark.parametrize('change',['delete','normalized','raw','clear_proof'])
def test_confirm_rejects_missing_or_changed_staging(client2,app2,change):
    job=preview_one(client2)
    with app2.state.sessions.begin() as db:
        row=db.scalar(select(ImportRow).where(ImportRow.job_id==job['id']))
        if change=='delete':db.delete(row)
        elif change=='clear_proof':db.get(ImportJob,job['id']).receipt={}
        else:
            payload=dict(row.payload);data=dict(payload[change]);data['income' if change=='normalized' else '归属培训收入']='999';payload[change]=data;row.payload=payload
    response=post(client2,f"/api/imports/{job['id']}/confirm",{'expected_version':job['version'],**REASON})
    assert response.status_code==409,response.text
    with app2.state.sessions() as db:
        assert db.get(ImportJob,job['id']).state=='PREVIEW'
        assert db.scalar(select(func.count()).select_from(TrainingRecord).where(TrainingRecord.external_key=='R8-X1'))==0


def queue_task(app):
    with app.state.sessions.begin() as db:
        task=Task(kind='sync',owner_id='schooladmin',key='R8-WORKER',payload={},state='PENDING')
        db.add(task);db.flush();return task.id

@pytest.mark.parametrize('condition',['expired','terminal','maintenance'])
def test_worker_rechecks_execution_boundary_after_claim(app2,monkeypatch,condition):
    import app.worker as worker
    ident=queue_task(app2);original=worker.claim_task;calls=[]
    def claim(db,*args,**kwargs):
        result=original(db,*args,**kwargs)
        task=db.get(Task,ident)
        if condition=='expired':task.lease_until=utcnow()-timedelta(seconds=1)
        if condition=='terminal':task.state='DONE'
        return result
    checks=[]
    def maintenance(cfg):
        checks.append(1);return {'blocked':condition=='maintenance' and len(checks)>1}
    monkeypatch.setattr(worker,'claim_task',claim)
    monkeypatch.setattr(worker,'configured_maintenance',maintenance)
    monkeypatch.setattr(worker,'process_sync_task_once',lambda *args,**kwargs:calls.append('sent'))
    result=run_once(app2.state.settings)
    assert calls==[],f'must not send for {condition}; got {result}'


def test_worker_unexpected_processor_error_isolated_and_lease_released(app2,monkeypatch):
    import app.worker as worker
    ident=queue_task(app2)
    def fail(*args,**kwargs):raise RuntimeError('secret://password-must-not-enter-task')
    monkeypatch.setattr(worker,'process_sync_task_once',fail)
    result=run_once(app2.state.settings)
    assert result['status']=='FAILED'
    with app2.state.sessions() as db:
        task=db.get(Task,ident)
        assert task.state=='FAILED' and task.lease_token is None and task.lease_until is None
        assert 'password-must' not in (task.error or '')
        assert list(db.scalars(select(TaskAttempt).where(TaskAttempt.task_id==ident)))

@pytest.mark.parametrize('partial',[{'has_more':True},{'complete':False},{'truncated':True},{'next_cursor':{'bad':'type'}}])
def test_partial_or_invalid_cursor_response_is_not_full_completion(app2,partial):
    with app2.state.sessions() as db:
        adapter=Adapter({'records':[],**partial});a,c,r=setup(db,adapter=adapter)
        schedule=scheduled(db,c);task=create_pull_task(db,a,c,'training_project','FULL',schedule=schedule)
        process_pull_task_once(db,task,r);db.flush()
        assert task.state!='DONE'
        assert schedule.last_run_at is None and schedule.last_cursor is None


def test_mapping_required_flag_is_strict_boolean():
    with pytest.raises(Exception):normalize_mapping({'source':'a','target':'b','required':'false'})


def test_nonfinite_untyped_json_has_validation_response(client2,app2):
    auth(client2,'schooladmin')
    with app2.state.sessions() as db:
        from app.models import Connection
        c=db.scalar(select(Connection).where(Connection.code=='middle'));ident,version=c.id,c.version
    # Send exact raw JSON because standard HTTP client's encoder forbids NaN.
    response=client2.put('/api/connections/'+ident,content=json.dumps({'expected_version':version,'mappings':[],'config':{'retry_count':3,'x':float('nan')},**REASON}),headers={'content-type':'application/json','Idempotency-Key':'r8-nonfinite-test'})
    assert response.status_code==422,response.text


def test_manual_participation_cannot_contradict_master_binding(client2,app2):
    auth(client2,'depthead')
    with app2.state.sessions.begin() as db:db.add(TrainingCourseMaster(code='CR8',name='课程',project_code='OTHER'))
    response=post(client2,'/api/participations',{'external_key':'R8-PART','teacher_id':'teacher','event_date':'2026-09-10','project_code':'PR8','project':'项目','course_code':'CR8','course':'课程','hours':2,'source':'经核对人工录入',**REASON})
    assert response.status_code in (409,422),response.text
