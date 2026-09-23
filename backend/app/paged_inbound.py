"""Durable, one-page-per-transaction ingestion; never claim whole-run rollback.

Earlier confirmed pages survive interruption. The next page is accepted only after
its predecessor is committed; final incremental watermarks advance at run completion.
"""
from copy import deepcopy
from datetime import timedelta
from sqlalchemy import select
from fastapi import HTTPException
from .models import Task, TaskAttempt, utcnow
from .core import digest
from .reference_data import InboundBatch, InboundRow, preview_inbound, confirm_inbound, inbound_content_hash
from .integrations import transport_kwargs
from .adapters.contracts import AdapterContractError
from .integration_diagnostics import diagnostic, safe_code
from .sync_policy import retry_budget


def _advance(task, state, pending, schedule):
    batch_id = pending.get('batch_id')
    chunks = list(state.get('chunks', []))
    if batch_id:
        chunks.append({'batch_id': batch_id, 'records': pending['rows'], 'committed': True, 'transport_evidence':pending.get('transport_evidence',{})})
    state.update(chunks=chunks, records=pending['received_total'],
                 committed_records=pending['received_total'], pending=None,
                 checkpoint=pending['checkpoint'], requires_confirmation=False,
                 page_failures=0, source_total=pending['source_total'])
    complete = not pending['has_more']
    state['committed'] = complete
    task.state = 'DONE' if complete else 'PENDING'
    task.next_at = utcnow()
    task.error = ''
    if complete:
        state['next_cursor'] = pending['next_cursor']
        if schedule:
            schedule.last_run_at = utcnow()
            schedule.next_at = utcnow() + timedelta(minutes=schedule.frequency_minutes)
            if pending['next_cursor'] is not None:
                schedule.last_cursor = pending['next_cursor']
            schedule.last_error = ''
            schedule.version += 1
    task.result = state


def _check_cross_page_keys(db, batch, state):
    ids = [x['batch_id'] for x in state.get('chunks', [])]
    if not ids:
        return
    rows = db.scalars(select(InboundRow).where(InboundRow.batch_id == batch.id)).all()
    repeated = set(db.scalars(select(InboundRow.business_key).where(
        InboundRow.batch_id.in_(ids), InboundRow.business_key.in_([x.business_key for x in rows]))))
    for row in rows:
        if row.business_key in repeated:
            if not row.errors:
                batch.errors += 1
            row.errors = [*row.errors, '同一次采集跨页业务唯一键重复，请核对源端分页规则']
    batch.content_hash = inbound_content_hash(sorted(rows, key=lambda row: row.row_no))

def process_page(db, task, connection, actor, schedule, adapter, registry):
    state = deepcopy(task.result or {})
    state.setdefault('paged', True)
    state.setdefault('records', 0)
    state.setdefault('chunks', [])
    task.attempts += 1
    try:
        response = adapter.pull_chunk(data_type=task.payload['data_type'],
            mode=task.payload['mode'], cursor=task.payload.get('cursor'), limit=1000,
            checkpoint=state.get('checkpoint'), **transport_kwargs(connection, registry))
        if not isinstance(response, dict) or type(response.get('has_more')) is not bool:
            raise AdapterContractError('PULL_RESPONSE_NOT_ACKNOWLEDGED')
        records = response.get('records')
        if not isinstance(records, list) or len(records) > 1000 or any(not isinstance(x, dict) for x in records):
            raise AdapterContractError('PULL_RECORDS_INVALID')
        if response['has_more'] and (not records or not isinstance(response.get('checkpoint'), dict)):
            raise AdapterContractError('PULL_CURSOR_NOT_ADVANCING')
        total = response.get('source_total')
        if total is not None and (type(total) is not int or total < 0):
            raise AdapterContractError('PULL_RESPONSE_TOTAL_MISMATCH')
        prior_total = state.get('source_total')
        if prior_total is not None and total is not None and prior_total != total:
            raise AdapterContractError('PULL_RESPONSE_TOTAL_MISMATCH')
        total = prior_total if total is None else total
        received = state['records'] + len(records)
        if not response['has_more'] and total is not None and total != received:
            raise AdapterContractError('PULL_RESPONSE_TOTAL_MISMATCH')
        proof={'request_digest':digest({'connection':connection.id,'type':task.payload['data_type'],'mode':task.payload['mode'],'checkpoint':state.get('checkpoint')}),'response_digest':digest(response),'received_at':utcnow().isoformat(),'records':len(records),'page':response.get('page')}
        batch = None
        if records:
            batch = preview_inbound(db, actor, connection, task.payload['data_type'], records,
                                    source_label='分页采集 / ' + task.payload['mode'])
            batch.receipt = {'pull_task_id': task.id, 'pull_page': response.get('page'), 'transport_evidence':proof}
            _check_cross_page_keys(db, batch, state)
            state.update(batch_id=batch.id, errors=batch.errors, received_records=received)
            if batch.errors:
                task.state = 'FAILED'
                task.error = '当前页存在质量问题；已确认前页保留，本页未入库'
                state['pending'] = None
                task.result = state
                task.version += 1
                db.add(TaskAttempt(task_id=task.id, attempt=task.attempts, result='FAILED', message='DATA_QUALITY'))
                if schedule:
                    schedule.last_error = task.error
                return task
        pending = {'batch_id': batch.id if batch else None, 'rows': len(records),
                   'received_total': received, 'source_total': total,
                   'has_more': response['has_more'], 'checkpoint': response.get('checkpoint'),
                   'next_cursor': response.get('next_cursor'), 'transport_evidence':proof}
        if batch and not task.payload.get('auto_commit'):
            state.update(pending=pending, requires_confirmation=True, committed=False, page_failures=0)
            task.state = 'WAITING_CONFIRMATION'
            task.error = ''
            task.result = state
        else:
            if batch:
                confirm_inbound(db, actor, batch, batch.version, '已批准的分页采集自动确认', '原同步计划授权')
            _advance(task, state, pending, schedule)
        task.version += 1
        db.add(TaskAttempt(task_id=task.id, attempt=task.attempts, result=task.state,
                           message='PAGE_PREVIEW' if task.state == 'WAITING_CONFIRMATION' else 'PAGE_COMMITTED'))
        return task
    except Exception as exc:
        failures = state.get('page_failures', 0) + 1
        detail = diagnostic(safe_code(exc), status=getattr(exc, 'status', None))
        state.update(page_failures=failures, diagnostic=detail)
        task.result = state
        task.error = detail['code']
        task.state = 'FAILED' if failures >= 1 + retry_budget(connection) else 'RETRY'
        task.next_at = utcnow() + timedelta(seconds=min(300, 2 ** min(failures, 8)))
        task.version += 1
        db.add(TaskAttempt(task_id=task.id, attempt=task.attempts, result=task.state, message=detail['code']))
        if schedule:
            schedule.last_error = detail['message']
        return task


def lock_pending_task(db, batch):
    ident = (batch.receipt or {}).get('pull_task_id')
    if not ident:
        return None
    task = db.scalar(select(Task).where(Task.id == ident).with_for_update().execution_options(populate_existing=True))
    if not task or task.state != 'WAITING_CONFIRMATION':
        raise HTTPException(409, '采集任务状态已变化，请核对后再确认')
    return task


def resume_confirmed_task(db, task, batch):
    if task is None:
        return
    state = deepcopy(task.result or {})
    pending = state.get('pending') or {}
    if (pending.get('batch_id') != batch.id or pending.get('rows') != batch.total
            or batch.state != 'COMMITTED' or (batch.receipt or {}).get('written') != batch.total
            or pending.get('received_total') != state.get('records', 0) + batch.total):
        raise HTTPException(409, '采集分页证据不一致，禁止推进游标')
    _advance(task, state, pending, None)
    task.version += 1


def has_unfinished_run(db, schedule):
    """Do not start a fresh run on top of a partially committed failed run."""
    from .sync_policy import schedule_context
    tasks = db.scalars(select(Task).where(Task.kind == 'inbound_pull',
        Task.state.in_(['FAILED', 'BLOCKED', 'WAITING_CONFIRMATION']),
        Task.payload['schedule_id'].as_string() == schedule.id,
        Task.result['paged'].as_boolean().is_(True)))
    approval = schedule_context(schedule)
    return any(not (task.payload or {}).get('approval_revoked')
               and task.payload.get('schedule_authorization') == approval for task in tasks)


def run_counts(db, task, connection):
    """Reconcile persisted batch evidence instead of trusting a green task label."""
    result = task.result or {}
    success = failed = pending = 0
    ids = [x.get('batch_id') for x in result.get('chunks', [])]
    if len(set(ids)) != len(ids) or any(not value for value in ids):
        return 0, 0, 0, 'BLOCKED'
    for ident in ids:
        batch = db.get(InboundBatch, ident)
        if (not batch or batch.connection_id != connection.id or batch.data_type != task.payload['data_type']
                or batch.state != 'COMMITTED' or batch.receipt.get('written') != batch.total
                or batch.receipt.get('pull_task_id') != task.id):
            return 0, 0, 0, 'BLOCKED'
        success += batch.total
    if success != result.get('committed_records', result.get('records', 0)):
        return 0, 0, 0, 'BLOCKED'
    current = result.get('batch_id')
    if current and current not in ids:
        batch = db.get(InboundBatch, current)
        if not batch or batch.connection_id != connection.id or batch.receipt.get('pull_task_id') != task.id:
            return success, 0, 0, 'BLOCKED'
        failed = batch.errors
        if task.state == 'WAITING_CONFIRMATION' and not failed:
            pending = batch.total
    stage = 'COMMITTED' if task.state == 'DONE' and success else 'NO_CHANGES' if task.state == 'DONE' else task.state
    return success, failed, pending, stage
