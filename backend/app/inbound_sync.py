"""Scheduled/manual school-data-hub pull substrate.

A pull task can only call an adapter after the Connection is genuinely CONNECTED.
Scheduled auto-commit additionally requires explicit school-admin approval. The
production adapter registry is empty in this checkpoint, so no external network
call can be faked by this module.
"""
from __future__ import annotations
import uuid
from datetime import datetime,timedelta
from sqlalchemy import String,Integer,DateTime,Boolean,ForeignKey,UniqueConstraint,Index,select
from sqlalchemy.orm import Mapped,mapped_column
from fastapi import HTTPException
from .models import Base,Entity,Connection,Task,TaskAttempt,User,Role,Org,utcnow
from .core import Actor,audit,serial,digest
from .integrations import ADAPTERS,live_connection,configuration_hash,transport_kwargs
from .reference_data import SUPPORTED_INBOUND,InboundBatch,preview_inbound,confirm_inbound

class IntegrationSchedule(Entity,Base):
    __tablename__='integration_schedules'
    connection_id: Mapped[str]=mapped_column(ForeignKey('connections.id'),index=True)
    data_type: Mapped[str]=mapped_column(String(64),index=True)
    frequency_minutes: Mapped[int]=mapped_column(Integer)
    auto_commit: Mapped[bool]=mapped_column(Boolean,default=False)
    active: Mapped[bool]=mapped_column(Boolean,default=False,index=True)
    approved_by: Mapped[str]=mapped_column(ForeignKey('users.id'),index=True)
    next_at: Mapped[datetime]=mapped_column(DateTime,default=utcnow,index=True)
    last_run_at: Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
    last_cursor: Mapped[str|None]=mapped_column(String(500),nullable=True)
    last_error: Mapped[str]=mapped_column(String(500),default='')
    version: Mapped[int]=mapped_column(Integer,default=1)
    __table_args__=(UniqueConstraint('connection_id','data_type'),Index('ix_integration_schedule_due','active','next_at'))

class PullContractError(RuntimeError):
    """Internal fixed reason codes only; never copy an upstream exception body."""
    def __init__(self,code):
        super().__init__(code);self.code=code


def _actor(db,user_id):
    user=db.get(User,user_id)
    if not user:return None
    role,org=db.get(Role,user.role_id),db.get(Org,user.org_id)
    if not role or not org:return None
    try:return Actor(db,user,role,org,None)
    except HTTPException:return None

def create_pull_task(db,actor,connection,data_type,mode,reason='',schedule=None):
    actor.require_admin();actor.require('sync.manage')
    if connection.code!='middle':raise HTTPException(422,'只有学校数据中台支持入站拉取')
    if data_type not in SUPPORTED_INBOUND:raise HTTPException(422,'该数据类型尚未建立正式入站落库契约')
    if mode not in {'FULL','INCREMENTAL'}:raise HTTPException(422,'同步模式必须为 FULL 或 INCREMENTAL')
    cursor=(schedule.last_cursor if schedule and mode=='INCREMENTAL' else None)
    key='inpull-'+uuid.uuid4().hex
    from .sync_policy import schedule_context
    payload={'connection_id':connection.id,'connection_code':connection.code,'data_type':data_type,'mode':mode,'cursor':cursor,
             'reason':reason,'configuration_hash':configuration_hash(connection),'schedule_version':schedule.version if schedule else None,'schedule_id':schedule.id if schedule else None,'auto_commit':bool(schedule and schedule.auto_commit),'schedule_authorization':schedule_context(schedule) if schedule else None}
    task=Task(kind='inbound_pull',owner_id=actor.id,key=key,payload=payload,state='PENDING')
    db.add(task);db.flush()
    if not live_connection(db,connection):
        task.state='BLOCKED';task.error='外部接口未真实连接';task.version+=1
        db.add(TaskAttempt(task_id=task.id,attempt=1,result='BLOCKED',message='NOT_CONNECTED'));task.attempts=1
    audit(db,actor,'sync',task.id,'创建数据中台全量/增量拉取任务',after={'data_type':data_type,'mode':mode,'scheduled':bool(schedule),'state':task.state},reason=reason or '数据中台拉取')
    return task

def process_pull_task_once(db,task,registry=ADAPTERS):
    if task.kind!='inbound_pull':raise ValueError('not inbound pull task')
    if task.state not in {'PENDING','RETRY'}:return task
    connection=db.get(Connection,(task.payload or {}).get('connection_id'));schedule=db.get(IntegrationSchedule,(task.payload or {}).get('schedule_id')) if (task.payload or {}).get('schedule_id') else None
    if not live_connection(db,connection,registry):
        task.state='BLOCKED';task.error='外部接口未真实连接';task.attempts+=1;task.version+=1
        db.add(TaskAttempt(task_id=task.id,attempt=task.attempts,result='BLOCKED',message='NOT_CONNECTED'))
        if schedule:schedule.last_error=task.error;schedule.version+=1
        return task
    adapter=registry.get(connection.code)
    if adapter is None or not callable(getattr(adapter,'pull',None)):
        task.state='BLOCKED';task.error='当前发布未注册数据中台拉取适配器';task.attempts+=1;task.version+=1
        db.add(TaskAttempt(task_id=task.id,attempt=task.attempts,result='BLOCKED',message='ADAPTER_NOT_REGISTERED'))
        if schedule:schedule.last_error=task.error;schedule.version+=1
        return task
    from .sync_policy import sync_actor, retry_exhausted, schedule_context
    try:actor=sync_actor(db,task)
    except HTTPException:actor=None
    if not actor:
        task.state='BLOCKED';task.error='同步计划批准人账号或权限已失效';task.attempts+=1;task.version+=1
        db.add(TaskAttempt(task_id=task.id,attempt=task.attempts,result='BLOCKED',message='APPROVER_INVALID'))
        if schedule:schedule.last_error=task.error;schedule.active=False;schedule.version+=1
        return task
    try:actor.require_admin()
    except HTTPException:
        task.state='BLOCKED';task.error='同步计划批准人不再具有学校管理员权限';task.attempts+=1;task.version+=1
        db.add(TaskAttempt(task_id=task.id,attempt=task.attempts,result='BLOCKED',message='APPROVER_NOT_ADMIN'))
        if schedule:schedule.last_error=task.error;schedule.active=False;schedule.version+=1
        return task
    if ((task.payload or {}).get('configuration_hash')!=configuration_hash(connection)
        or ((task.payload or {}).get('schedule_id') and (not schedule or not schedule.active
            or not schedule.auto_commit or schedule.approved_by!=actor.id
            or task.payload.get('approval_revoked')
            or task.payload.get('schedule_authorization')!=schedule_context(schedule)))):
        task.state='BLOCKED';task.error='连接配置已变化或定时自动入库批准已撤销';task.attempts+=1;task.version+=1
        db.add(TaskAttempt(task_id=task.id,attempt=task.attempts,result='BLOCKED',message='CONFIG_OR_APPROVAL_CHANGED'))
        return task
    from .sync_policy import retry_budget
    retry_budget(connection)
    if callable(getattr(adapter,'pull_chunk',None)):
        from .paged_inbound import process_page
        return process_page(db,task,connection,actor,schedule,adapter,registry)
    task.attempts+=1;attempt=task.attempts
    try:
        result=adapter.pull(data_type=task.payload['data_type'],mode=task.payload['mode'],cursor=task.payload.get('cursor'),limit=1000,**transport_kwargs(connection,registry))
        if not isinstance(result,dict) or 'records' not in result:raise PullContractError('PULL_RESPONSE_NOT_ACKNOWLEDGED')
        # The adapter must return one complete bounded unit. These are internal
        # adapter contract flags, not assumptions about a school's remote protocol.
        for field in ('has_more','complete','truncated'):
            if field in result and type(result[field]) is not bool:raise PullContractError('PULL_COMPLETENESS_INVALID')
        if result.get('has_more') is True or result.get('complete') is False or result.get('truncated') is True:
            raise PullContractError('PULL_INCOMPLETE_UNIT_REQUIRES_ADAPTER_PAGING')
        records=result['records']
        if not isinstance(records,list) or len(records)>1000 or any(not isinstance(x,dict) for x in records):raise PullContractError('PULL_PAYLOAD_INVALID')
        proof={'request_digest':digest({k:task.payload.get(k) for k in ('connection_id','configuration_hash','data_type','mode','cursor')}),'response_digest':digest(serial(result)),'received_records':len(records),'received_at':utcnow().isoformat(),'configuration_hash':configuration_hash(connection)}
        next_cursor=result.get('next_cursor')
        if next_cursor is not None and (not isinstance(next_cursor,str) or not next_cursor.strip() or len(next_cursor)>500):raise PullContractError('PULL_CURSOR_INVALID')
        if not records:
            task.state='DONE';task.error='';task.result={'records':0,'mode':task.payload['mode'],'next_cursor':next_cursor,'batch_id':None,'committed':bool(schedule and schedule.auto_commit)};task.version+=1
            db.add(TaskAttempt(task_id=task.id,attempt=attempt,result='DONE',message='NO_CHANGES'))
        else:
            batch=preview_inbound(db,actor,connection,task.payload['data_type'],records,source_label=f"{task.payload['mode']}接口拉取")
            if batch.errors:
                task.state='FAILED';task.error='拉取数据存在质量错误，已保留预览但未写正式主数据';task.result={'records':len(records),'batch_id':batch.id,'errors':batch.errors,'next_cursor':next_cursor};task.version+=1
                db.add(TaskAttempt(task_id=task.id,attempt=attempt,result='FAILED',message='DATA_QUALITY'))
            elif task.payload.get('auto_commit'):
                confirm_inbound(db,actor,batch,batch.version,'已批准定时同步自动确认入库','同步计划由学校管理员显式启用')
                task.state='DONE';task.error='';task.result={'records':len(records),'batch_id':batch.id,'committed':True,'next_cursor':next_cursor,'mode':task.payload['mode']};task.version+=1
                db.add(TaskAttempt(task_id=task.id,attempt=attempt,result='DONE',message='AUTO_COMMITTED'))
            else:
                task.state='DONE';task.error='';task.result={'records':len(records),'batch_id':batch.id,'committed':False,'requires_confirmation':True,'next_cursor':next_cursor,'mode':task.payload['mode']};task.version+=1
                db.add(TaskAttempt(task_id=task.id,attempt=attempt,result='DONE',message='PREVIEW_REQUIRES_CONFIRMATION'))
        task.result={**(task.result or {}),'transport_evidence':proof}
        if schedule:
            schedule.last_error=task.error
            if task.state=='DONE' and task.result.get('committed') is True:
                schedule.last_run_at=utcnow()
                if next_cursor is not None:schedule.last_cursor=str(next_cursor)
            schedule.version+=1
        return task
    except Exception as exc:
        message=exc.code if isinstance(exc,PullContractError) else type(exc).__name__  # No upstream exception text/credentials.
        task.error=message
        if retry_exhausted(attempt,task.payload.get('retry_base_attempt',0),connection):task.state='FAILED'
        else:task.state='RETRY';task.next_at=utcnow()+timedelta(seconds=min(300,2**attempt))
        task.version+=1;db.add(TaskAttempt(task_id=task.id,attempt=attempt,result=task.state,message=message))
        if schedule:schedule.last_error=message;schedule.version+=1
        return task

def enqueue_due_schedules(db,now=None,registry=ADAPTERS):
    now=now or utcnow();created=[]
    schedules=db.scalars(select(IntegrationSchedule).where(IntegrationSchedule.active.is_(True),IntegrationSchedule.next_at<=now).order_by(IntegrationSchedule.next_at,IntegrationSchedule.id).with_for_update()).all()
    for schedule in schedules:
        connection=db.get(Connection,schedule.connection_id);actor=_actor(db,schedule.approved_by)
        if not actor:
            schedule.active=False;schedule.last_error='批准人账号/权限失效，计划已停用';schedule.version+=1;continue
        try:actor.require_admin();actor.require('sync.manage')
        except HTTPException:
            schedule.active=False;schedule.last_error='批准人不再具有学校管理员权限，计划已停用';schedule.version+=1;continue
        adapter=registry.get(connection.code) if connection else None
        if not live_connection(db,connection,registry):
            schedule.active=False;schedule.last_error='接口不再处于CONNECTED，计划已停用';schedule.version+=1;continue
        if adapter is None or not callable(getattr(adapter,'pull',None)):
            schedule.active=False;schedule.last_error='数据中台拉取适配器不可用，计划已停用';schedule.version+=1;continue
        # Avoid overlapping runs for one schedule.
        pending=db.scalar(select(Task.id).where(Task.kind=='inbound_pull',Task.state.in_(['PENDING','RUNNING','RETRY']),
            Task.payload['schedule_id'].as_string()==schedule.id).limit(1))
        from .paged_inbound import has_unfinished_run
        if pending is not None or has_unfinished_run(db,schedule):
            schedule.next_at=now+timedelta(minutes=schedule.frequency_minutes);schedule.version+=1;continue
        mode='INCREMENTAL' if schedule.last_run_at else 'FULL'
        task=create_pull_task(db,actor,connection,schedule.data_type,mode,'定时同步计划',schedule=schedule);created.append(task.id)
        schedule.next_at=now+timedelta(minutes=schedule.frequency_minutes);schedule.version+=1
    return created
