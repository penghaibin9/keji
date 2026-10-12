"""Background worker with leased claims, revalidation and isolated failures.

A lease permits a worker to TRY an execution, not to override cancellation,
maintenance, or current business authorization. Remote retries still depend on
stable business idempotency keys; MySQL concurrency is a separate release gate.
"""
from __future__ import annotations
import logging,os,secrets,time
from datetime import timedelta
from sqlalchemy import select,text
from sqlalchemy.orm import sessionmaker
from . import installation
from .config import Settings
from .core import make_engine
from .models import Task,TaskAttempt,RuntimeState,utcnow
from .maintenance_guard import configured_maintenance
from .integrations import process_sync_task_once,ADAPTERS
from .inbound_sync import process_pull_task_once,enqueue_due_schedules
from .excel_io import process_export_task

log=logging.getLogger(__name__)


def heartbeat(db,*,healthy=True,maintenance=False,note=''):
    obj=db.get(RuntimeState,'worker')
    value={'healthy':healthy,'maintenance':maintenance,'pid':os.getpid(),'note':note}
    if obj is None:obj=RuntimeState(key='worker',value=value,updated_at=utcnow());db.add(obj)
    else:obj.value=value;obj.updated_at=utcnow()
    db.flush()


def claim_task(db,lease_seconds=300):
    if type(lease_seconds) is not int or not 1<=lease_seconds<=3600:raise ValueError('invalid lease duration')
    now=utcnow()
    q=select(Task).where(Task.state.in_(['PENDING','RETRY']),Task.next_at<=now,
        ((Task.lease_until.is_(None))|(Task.lease_until<=now))).order_by(Task.created_at,Task.id).limit(1)
    task=db.scalar(q.with_for_update(skip_locked=True).execution_options(populate_existing=True))
    if not task:return None
    token=secrets.token_hex(16);task.lease_token=token;task.lease_until=now+timedelta(seconds=lease_seconds);task.version+=1;db.flush()
    return task.id,token


def _release(task):
    task.lease_token=None;task.lease_until=None;task.version+=1


def _record_executor_failure(sessions,ident,token,exc):
    # A fresh transaction is essential: an SQL error may invalidate the execution
    # transaction. Never overwrite a newer worker's token or a completed task.
    with sessions.begin() as db:
        task=db.scalar(select(Task).where(Task.id==ident,Task.lease_token==token).with_for_update())
        if not task:return {'status':'LOST_LEASE','claimed':True,'task_id':ident}
        if task.state not in {'PENDING','RETRY'}:
            _release(task)
            return {'status':task.state,'claimed':True,'task_id':ident}
        task.state='FAILED';task.error='WORKER_EXECUTOR_ERROR:'+type(exc).__name__;task.attempts+=1
        _release(task)
        db.add(TaskAttempt(task_id=ident,attempt=task.attempts,result='ERROR',message=task.error))
        heartbeat(db,healthy=False,note=f'任务 {ident} 执行失败，等待核对；原因类型 '+type(exc).__name__)
        return {'status':'FAILED','claimed':True,'task_id':ident}


def run_once(cfg=None,registry=ADAPTERS,*,engine=None,sessions=None,check_schema=True):
    cfg=cfg or Settings();registry.configure(cfg.env == 'production', [x.strip() for x in cfg.adapter_modules.split(',') if x.strip()]);owns_engine=engine is None
    engine=engine if engine is not None else make_engine(cfg.database_url);sessions=sessions if sessions is not None else sessionmaker(bind=engine,expire_on_commit=False)
    try:
        if cfg.env == 'production':
            with engine.connect() as connection:
                if check_schema:installation.require_canonical(connection,require_mysql=True)
                elif list(connection.execute(text('SELECT version_num FROM alembic_version')).scalars())!=[installation.CURRENT_REVISION]:raise installation.InstallationRejected('LEGACY_OR_UNKNOWN_REVISION')
        if configured_maintenance(cfg)['blocked']:
            with sessions.begin() as db:heartbeat(db,healthy=True,maintenance=True,note='维护期间停止领取业务任务')
            return {'status':'MAINTENANCE','claimed':False}
        with sessions.begin() as db:
            heartbeat(db,healthy=True,maintenance=False);enqueue_due_schedules(db,registry=registry);claim=claim_task(db)
        if not claim:return {'status':'IDLE','claimed':False}
        ident,token=claim
        try:
            with sessions.begin() as db:
                task=db.scalar(select(Task).where(Task.id==ident,Task.lease_token==token).with_for_update())
                if not task:return {'status':'LOST_LEASE','claimed':False}
                now=utcnow()
                if task.state not in {'PENDING','RETRY'} or not task.lease_until or task.lease_until<=now or task.next_at>now:
                    _release(task)
                    return {'status':'NO_LONGER_ELIGIBLE','claimed':True,'task_id':ident}
                if configured_maintenance(cfg)['blocked']:
                    _release(task);heartbeat(db,healthy=True,maintenance=True,note='领取后进入维护，未执行业务任务')
                    return {'status':'MAINTENANCE','claimed':True,'task_id':ident}
                if task.kind=='sync':process_sync_task_once(db,task,registry)
                elif task.kind=='inbound_pull':process_pull_task_once(db,task,registry)
                elif task.kind=='export':process_export_task(db,task,cfg.storage_dir)
                else:
                    task.state='BLOCKED';task.error='当前worker未注册该任务执行器';task.version+=1
                _release(task)
                heartbeat(db,healthy=True,maintenance=False,note=f'处理任务 {task.id} -> {task.state}')
                return {'status':task.state,'claimed':True,'task_id':task.id}
        except Exception as exc:
            return _record_executor_failure(sessions,ident,token,exc)
    finally:
        if owns_engine:engine.dispose()


def main():
    cfg=Settings();engine=make_engine(cfg.database_url);sessions=sessionmaker(bind=engine,expire_on_commit=False);next_schema_check=0
    try:
        while True:
            try:
                if cfg.env=='production' and time.monotonic()>=next_schema_check:
                    with engine.connect() as connection:installation.require_canonical(connection,require_mysql=True)
                    next_schema_check=time.monotonic()+600
                run_once(cfg,engine=engine,sessions=sessions,check_schema=False)
            except Exception as exc:
                # Database/preflight failures must not reveal DSNs or interrupt all
                # future polling. Missing heartbeats remain unhealthy to the monitor.
                log.error('worker iteration failed: %s',type(exc).__name__)
            time.sleep(2)
    finally:engine.dispose()

if __name__=='__main__':main()
