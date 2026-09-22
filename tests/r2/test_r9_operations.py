"""R9 operator-facing state/count checks, using synthetic local data only."""
from datetime import timedelta
import pytest
from fastapi import HTTPException
from sqlalchemy import select,update
from app.models import Task,Connection,utcnow
from app.core import digest
from app.integrations import enqueue_sync,process_sync_task_once,SyncItem,task_sync_items
from app.inbound_sync import create_pull_task,process_pull_task_once
from app.routes.integrations import _clean_config
from app.sync_policy import retry_sync_items
from conftest import auth,post
from test_r8_regressions import setup,Adapter,scheduled
from test_r5_closeout import REASON


def summary(client):
    r=client.get('/api/connections/summary');assert r.status_code==200,r.text
    return next(x for x in r.json()['items'] if x['code']=='middle')['latest_task']


def test_old_connection_activity_survives_501_unrelated_tasks(app2,client2):
    with app2.state.sessions.begin() as db:
        a,c,r=setup(db);task=create_pull_task(db,a,c,'training_project','FULL')
        task.created_at=utcnow()-timedelta(days=3);ident=task.id
        province=db.scalar(select(Connection).where(Connection.code=='province'))
        for i in range(501):
            db.add(Task(kind='sync',owner_id=a.id,key=f'r9-unrelated-{i}',payload={'connection_id':province.id},state='DONE'))
    auth(client2,'schooladmin');last=summary(client2)
    assert last and last['id']==ident


def test_pull_preview_is_not_reported_as_successful_formal_import(app2,client2):
    with app2.state.sessions.begin() as db:
        a,c,r=setup(db,adapter=Adapter({'records':[{'code':'R9A','name':'合成预览'}]}))
        task=create_pull_task(db,a,c,'training_project','FULL');process_pull_task_once(db,task,r)
        assert task.state=='DONE' and task.result['committed'] is False
    auth(client2,'schooladmin');last=summary(client2)
    assert last['success_count']==0 and last.get('pending_confirmation_count')==1


def test_pull_summary_counts_formal_rows_not_one_transport_task(app2,client2):
    with app2.state.sessions.begin() as db:
        a,c,r=setup(db,adapter=Adapter({'records':[{'code':'R9A','name':'合成一'},{'code':'R9B','name':'合成二'}]}))
        sch=scheduled(db,c);task=create_pull_task(db,a,c,'training_project','FULL',schedule=sch)
        process_pull_task_once(db,task,r);assert task.result['committed'] is True
    auth(client2,'schooladmin');last=summary(client2)
    assert last['success_count']==2 and last.get('count_unit')=='records'


@pytest.mark.parametrize('field,value',[('retry_count',3.8),('frequency_minutes',1.5),('frequency_minutes',True)])
def test_config_numbers_are_not_truncated_or_boolean(field,value):
    with pytest.raises(HTTPException) as err:_clean_config({field:value})
    assert err.value.status_code==422


@pytest.mark.parametrize('state',['DONE','FAILED','BLOCKED'])
def test_pull_processor_never_resumes_terminal_without_explicit_retry(app2,state):
    with app2.state.sessions() as db:
        adapter=Adapter();a,c,r=setup(db,adapter=adapter)
        task=create_pull_task(db,a,c,'training_project','FULL');task.state=state;db.flush();before=digest(task)
        process_pull_task_once(db,task,r);db.flush()
        assert not adapter.calls and digest(task)==before


def test_sync_business_key_respects_mysql_column_capacity(app2):
    with app2.state.sessions() as db:
        a,c,r=setup(db)
        with pytest.raises(HTTPException) as err:
            enqueue_sync(db,a,c,'training_project',[{'business_key':'x'*161,'code':'P','name':'too long key'}])
        assert err.value.status_code==422


def test_single_retry_checks_version_again_after_refresh(app2):
    with app2.state.sessions() as db:
        a,c,r=setup(db);task=enqueue_sync(db,a,c,'training_project',[{'business_key':'R9K','code':'R9K','name':'版本样本'}])
        item=task_sync_items(db,task)[0];task.state='FAILED';item.state='FAILED';db.commit()
        version=item.version;task.id
        db.execute(update(SyncItem).where(SyncItem.id==item.id).values(version=version+1),execution_options={'synchronize_session':False})
        with pytest.raises(HTTPException) as err:
            retry_sync_items(db,a,task,'锁后版本测试',item_ids={item.id},expected_item_versions={item.id:version})
        assert err.value.status_code==409


def test_shared_successful_row_is_never_sent_twice(app2):
    with app2.state.sessions() as db:
        adapter=Adapter();a,c,r=setup(db,adapter=adapter)
        first={'business_key':'R9A','code':'R9A','name':'已完成'}
        t1=enqueue_sync(db,a,c,'training_project',[first]);process_sync_task_once(db,t1,r);db.flush()
        t2=enqueue_sync(db,a,c,'training_project',[first,{'business_key':'R9B','code':'R9B','name':'新行'}])
        process_sync_task_once(db,t2,r);db.flush()
        assert t2.state=='DONE' and len(adapter.calls)==2 and t2.result['reused']==1


def test_manual_confirmation_refreshes_summary_from_committed_batch(app2,client2):
    from app.reference_data import confirm_inbound,InboundBatch
    with app2.state.sessions.begin() as db:
        a,c,r=setup(db,adapter=Adapter({'records':[{'code':'R9C','name':'确认样本'}]}))
        task=create_pull_task(db,a,c,'training_project','FULL');process_pull_task_once(db,task,r)
        batch=db.get(InboundBatch,task.result['batch_id'])
        confirm_inbound(db,a,batch,batch.version,'人工核对正式入库','合成验收')
        # Preserve transport receipt rather than retroactively rewriting it.
        assert task.result['committed'] is False
    auth(client2,'schooladmin');last=summary(client2)
    assert last['success_count']==1 and last['pending_confirmation_count']==0
    assert last['display_state']=='COMMITTED'


def test_zero_row_pull_shows_no_changes_not_one_success(app2,client2):
    with app2.state.sessions.begin() as db:
        a,c,r=setup(db);task=create_pull_task(db,a,c,'training_project','FULL');process_pull_task_once(db,task,r)
    auth(client2,'schooladmin');last=summary(client2)
    assert last['success_count']==0 and last['display_state']=='NO_CHANGES'


def test_summary_data_type_filter_selects_matching_earlier_task(app2,client2):
    with app2.state.sessions.begin() as db:
        a,c,r=setup(db);old=create_pull_task(db,a,c,'training_project','FULL');ident=old.id
        old.created_at=utcnow()-timedelta(minutes=2)
        create_pull_task(db,a,c,'teacher_hr','FULL')
    auth(client2,'schooladmin')
    r=client2.get('/api/connections/summary?data_type=training_project');assert r.status_code==200
    middle=next(x for x in r.json()['items'] if x['code']=='middle')
    assert middle['latest_task']['id']==ident
    assert client2.get('/api/connections/summary?data_type=not-a-catalog-type').status_code==422
    assert client2.get('/api/connections/summary?connection_id=missing').status_code==404
    assert client2.get('/api/connections/summary?data_type=course&data_type=teacher_hr').status_code==422


@pytest.mark.parametrize('value',[3,'3','3.0'])
def test_config_allows_exact_integers(value):
    assert _clean_config({'retry_count':value})['retry_count']==3
