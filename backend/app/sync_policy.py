"""Shared execution/retry policy. Historical attempts are never reset or deleted.

The configured retry_count is retries AFTER the first transport call (PDF 11.4).
Manual retry starts another bounded cycle with the same business idempotency key.
"""
from __future__ import annotations
from fastapi import HTTPException
from sqlalchemy import select
from .core import audit, serial, digest
from .models import Task, TaskAttempt, Connection, utcnow


def retry_budget(connection):
    value=(connection.config or {}).get('retry_count',3)
    if type(value) is not int or not 3<=value<=10:
        raise HTTPException(409,'重试次数配置无效，请重新核对接口配置')
    return value


def retry_exhausted(total_attempts, base_attempt, connection):
    if type(base_attempt) is not int or not 0<=base_attempt<=total_attempts:
        raise HTTPException(409,'任务重试起点异常，请人工核对')
    return total_attempts-base_attempt >= 1+retry_budget(connection)


def sync_actor(db, task):
    from .inbound_sync import _actor
    actor=_actor(db,(task.payload or {}).get('retry_authorized_by') or task.owner_id)
    if actor is None:raise HTTPException(403,'同步执行授权人账号已失效')
    actor.require_admin();actor.require('sync.manage')
    return actor


def block_task(db, task, message, code):
    task.state='BLOCKED';task.error=message;task.version+=1;task.attempts+=1
    db.add(TaskAttempt(task_id=task.id,attempt=task.attempts,result='BLOCKED',message=code))
    return task


def schedule_context(schedule):
    # Deliberately exclude next_at, last_run_at, cursor and version, which the
    # scheduler itself updates without changing the administrator's approval.
    return digest({k:getattr(schedule,k) for k in ('id','connection_id','data_type',
        'frequency_minutes','active','auto_commit','approved_by')})


def invalidate_schedule_tasks(db, schedule_id, reason):
    rows=db.scalars(select(Task).where(Task.kind=='inbound_pull',Task.state!='DONE',
        Task.payload['schedule_id'].as_string()==schedule_id).with_for_update()).all()
    for task in rows:
        task.payload={**task.payload,'approval_revoked':True}
        task.state='BLOCKED';task.error=reason;task.version+=1
    return len(rows)


def retry_sync_items(db, actor, task, reason, *, item_ids=None, expected_item_versions=None, expected_task_version=None):
    from .integrations import task_sync_items, live_connection, configuration_hash, SyncItem
    from .core import check_version
    actor.require_admin();actor.require('sync.manage')
    if task.kind!='sync':raise HTTPException(422,'当前任务不是逐笔同步任务')
    rows=task_sync_items(db,task)
    if item_ids is not None:rows=[x for x in rows if x.id in item_ids]
    parents={t.id:t for t in db.scalars(select(Task).where(Task.id.in_({x.task_id for x in rows}|{task.id})).order_by(Task.id).with_for_update().execution_options(populate_existing=True))}
    # A lock does not refresh already loaded ORM objects. Read again AFTER all
    # parent locks are held, otherwise a just-completed row can be retransmitted.
    if task.id not in parents:raise HTTPException(409,'同步任务已失效')
    task=parents[task.id]
    if expected_task_version is not None:check_version(task,expected_task_version)
    ids={x.id for x in rows}
    rows=db.scalars(select(SyncItem).where(SyncItem.id.in_(ids)).order_by(SyncItem.id)
        .with_for_update().execution_options(populate_existing=True)).all()
    if len(rows)!=len(ids) or any(x.task_id not in parents for x in rows):
        raise HTTPException(409,'同步明细或所属任务已变化，请刷新核对')
    for item in rows:
        if expected_item_versions is not None:
            if item.id not in expected_item_versions:raise HTTPException(409,'缺少同步明细版本')
            check_version(item,expected_item_versions[item.id])
    # A rolled-back executor can leave durable PENDING rows under a FAILED task.
    # Resuming them is explicit, audited, and uses the original idempotency keys.
    rows=[x for x in rows if x.state in {'FAILED','RETRY','BLOCKED'} or
          (x.state=='PENDING' and parents[x.task_id].state in {'FAILED','BLOCKED'})]
    if not rows:raise HTTPException(409,'没有可补传的失败记录；成功记录不会重复发送')
    relevant={x.task_id for x in rows}|{task.id}
    parents={key:value for key,value in parents.items() if key in relevant}
    for parent in parents.values():
        if parent.lease_token and parent.lease_until and parent.lease_until>utcnow():
            raise HTTPException(409,'任务正在执行，请等待本次处理结束后再补传')
        connection=db.get(Connection,(parent.payload or {}).get('connection_id'))
        if not live_connection(db,connection):
            block_task(db,task,'外部接口未真实连接','NOT_CONNECTED')
            audit(db,actor,'sync',task.id,'补传被阻断',after={'state':'NOT_CONNECTED'},reason=reason)
            return task
        if parent.payload.get('configuration_hash')!=configuration_hash(connection):
            raise HTTPException(409,'原同步任务的接口配置或映射已变化，不能重发旧报文')
    for item in rows:
        item.result={**(item.result or {}),'retry_base_attempt':item.attempts}
        item.state='RETRY';item.next_at=utcnow();item.error='';item.version+=1
    for parent in parents.values():
        before=serial(parent)
        parent.payload={**parent.payload,'retry_authorized_by':actor.id,'retry_authorized_at':utcnow().isoformat()}
        parent.state='RETRY';parent.next_at=utcnow();parent.error='';parent.lease_token=None;parent.lease_until=None;parent.version+=1
        audit(db,actor,'sync',parent.id,'重新授权同步补传（保留原失败及幂等键）',before,
            {'retry_item_ids':[x.id for x in rows if x.task_id==parent.id],'requested_from_task':task.id},reason)
    return task


def retry_pull_task(db, actor, task, reason):
    from .integrations import live_connection,configuration_hash
    from .inbound_sync import IntegrationSchedule
    actor.require_admin();actor.require('sync.manage')
    task=db.scalar(select(Task).where(Task.id==task.id).with_for_update().execution_options(populate_existing=True))
    if task is None or task.state not in {'FAILED','BLOCKED'}:raise HTTPException(409,'任务状态已变化，请刷新核对')
    if task.lease_token and task.lease_until and task.lease_until>utcnow():
        raise HTTPException(409,'任务仍由其他worker持有有效租约，不能抢占')
    connection=db.get(Connection,task.payload.get('connection_id'))
    if not live_connection(db,connection):raise HTTPException(409,'请先完成真实连接验证后再重试拉取')
    if task.payload.get('configuration_hash')!=configuration_hash(connection):
        raise HTTPException(409,'接口配置已经变化，请创建新拉取任务')
    if task.payload.get('approval_revoked'):
        raise HTTPException(409,'原同步计划批准已撤销，请由新计划产生任务')
    sid=task.payload.get('schedule_id')
    if sid:
        schedule=db.get(IntegrationSchedule,sid)
        if not schedule or not schedule.active or not schedule.auto_commit or schedule.approved_by!=actor.id or task.payload.get('schedule_authorization')!=schedule_context(schedule):
            raise HTTPException(409,'原定时计划授权已变化，不能重试原自动入库任务')
    task.payload={**task.payload,'retry_authorized_by':actor.id,'retry_base_attempt':task.attempts}
    if (task.result or {}).get('paged'):task.result={**task.result,'page_failures':0}
    task.state='PENDING';task.next_at=utcnow();task.error='';task.lease_token=None;task.lease_until=None;task.version+=1
    audit(db,actor,'sync',task.id,'重新授权数据中台拉取',after={'attempts_preserved':task.attempts},reason=reason)
    return task
