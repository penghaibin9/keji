"""Non-integration export failures must be recoverable without losing evidence."""
from sqlalchemy import select
from app.models import Task,TaskAttempt
from app.worker import run_once
from conftest import auth,post

def test_export_executor_failure_then_authorized_retry_keeps_attempt(app2,client2,monkeypatch):
    import app.worker as worker
    auth(client2,'schooladmin')
    r=post(client2,'/api/exports',{'kind':'records','filters':{'project_code':'P1'},'confirmed':False})
    assert r.status_code==200
    ident=r.json()['id']
    actual=worker.process_export_task
    def broken(*args,**kwargs):raise OSError('synthetic-private-value-do-not-log')
    monkeypatch.setattr(worker,'process_export_task',broken)
    assert run_once(app2.state.settings)['status']=='FAILED'
    detail=client2.get('/api/tasks/'+ident).json()
    assert detail['task']['state']=='FAILED' and len(detail['attempts'])==1
    assert 'synthetic-private-value' not in str(detail)
    with app2.state.sessions() as db:
        task=db.get(Task,ident)
        assert task.lease_token is None and task.lease_until is None
    r=post(client2,'/api/tasks/'+ident+'/retry',{'expected_version':detail['task']['version'],'reason':'隔离故障已排除，重试导出'})
    assert r.status_code==200,r.text
    monkeypatch.setattr(worker,'process_export_task',actual)
    assert run_once(app2.state.settings)['status']=='DONE'
    assert client2.get('/api/tasks/'+ident+'/download').status_code==200
    with app2.state.sessions() as db:
        assert db.scalar(select(TaskAttempt).where(TaskAttempt.task_id==ident,TaskAttempt.result=='ERROR'))

def test_other_role_cannot_retry_failed_export(app2,client2):
    auth(client2,'schooladmin')
    r=post(client2,'/api/exports',{'kind':'records','filters':{},'confirmed':False})
    ident=r.json()['id']
    with app2.state.sessions.begin() as db:
        task=db.get(Task,ident);task.state='FAILED';version=task.version
    auth(client2,'depthead')
    r=post(client2,'/api/tasks/'+ident+'/retry',{'expected_version':version,'reason':'不能接管其他人的导出'})
    assert r.status_code==403
    with app2.state.sessions() as db:assert db.get(Task,ident).state=='FAILED'
