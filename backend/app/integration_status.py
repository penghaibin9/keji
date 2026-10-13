"""Read-only synchronization status: transport completion is not business commit."""
from sqlalchemy import select, func
from .models import Task, TaskAttempt
from .integrations import SyncItem, SyncCallLog, task_sync_items
from .reference_data import batch_facts


def latest_task_status(db, connection, data_type=None):
    query=select(Task).where(Task.kind.in_(['sync','inbound_pull']),
        Task.payload['connection_id'].as_string()==connection.id)
    if data_type:query=query.where(Task.payload['data_type'].as_string()==data_type)
    task=db.scalar(query.order_by(Task.created_at.desc(),Task.id.desc()).limit(1))
    if task is None:return None
    success=failed=pending=0;stage=task.state
    activity=db.scalar(select(func.max(TaskAttempt.created_at)).where(TaskAttempt.task_id==task.id)) or task.created_at
    failures=[]
    if task.kind=='sync':
        rows=task_sync_items(db,task)
        success=sum(x.state=='DONE' for x in rows);failed=sum(x.state in {'FAILED','BLOCKED'} for x in rows)
        # 4.9 latest failure reason: first failed items with their last error code.
        failures=[{'business_key':x.business_key,'state':x.state,'error':x.error} for x in rows if x.state in {'FAILED','BLOCKED','RETRY'} and x.error][:3]
        last_call=db.scalar(select(func.max(SyncCallLog.created_at)).where(SyncCallLog.item_id.in_([x.id for x in rows])))
        if last_call:activity=max(activity,last_call)
    elif (task.result or {}).get('paged'):
        from .paged_inbound import run_counts
        success,failed,pending,stage=run_counts(db,task,connection)
    else:
        result=task.result or {};batch=batch_facts(db,result.get('batch_id')) if result.get('batch_id') else None
        if batch and batch.connection_id==connection.id and batch.data_type==(task.payload or {}).get('data_type'):
            if batch.state=='COMMITTED' and (batch.receipt or {}).get('written')==batch.total:
                success=batch.total;stage='COMMITTED'
                activity=(batch.receipt or {}).get('committed_at') or activity
            elif batch.state=='PREVIEW':
                failed=batch.errors
                if not failed and task.state=='DONE':pending=batch.total;stage='PREVIEW'
                elif failed:stage='FAILED'
        elif result.get('batch_id'):
            stage='BLOCKED'  # Missing/mismatched evidence must never turn green.
        elif task.state=='DONE' and result.get('records')==0:
            stage='NO_CHANGES'
    return {'id':task.id,'kind':task.kind,'data_type':(task.payload or {}).get('data_type'),
        'state':task.state,'display_state':stage,'created_at':task.created_at.isoformat(),
        'error':task.error,'failure_items':failures,
        'failure_reason':task.error or (failures[0]['error'] if failures else '') or ((task.result or {}).get('message') if task.state in {'FAILED','BLOCKED'} else ''),
        'success_count':success,'failed_count':failed,
        'pending_confirmation_count':pending,'count_unit':'records',
        'last_activity_at':activity if isinstance(activity,str) else activity.isoformat()}
