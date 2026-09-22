"""R9 regression probes. SQLite/state doubles do NOT claim MySQL concurrency."""
from datetime import timedelta
import pytest
from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from conftest import auth, post
from test_r5_closeout import connection, ContractAdapter, REASON
from app.models import Task, TaskAttempt, Connection, utcnow
from app.core import digest
from app.inbound_sync import _actor
from app.integrations import (AdapterRegistry, ConnectionCheck, probe_connection,
    activate_connection, live_connection, enqueue_sync, process_sync_task_once,
    task_sync_items, SyncItem, SyncCallLog)
from app.sync_policy import retry_sync_items

RECORDS=[{'business_key':'R9-P1','code':'R9-P1','name':'R9合成项目'}]


def prepare(db, response=None):
    c=connection(db);c.state='CONNECTED'
    adapter=ContractAdapter(response);registry=AdapterRegistry()
    registry.register_for_test('middle',adapter)
    a=_actor(db,'schooladmin')
    task=enqueue_sync(db,a,c,'training_project',RECORDS,'R9合成测试')
    db.flush();return a,c,adapter,registry,task


def test_disconnected_duplicate_request_cannot_destroy_success_receipt(app2,client2):
    with app2.state.sessions.begin() as db:
        a,c,adapter,registry,task=prepare(db)
        process_sync_task_once(db,task,registry)
        assert task.state=='DONE'
        ident,cid=task.id,c.id
        item=task_sync_items(db,task)[0];original=digest({'task':task,'item':item})
        c.state='NOT_CONNECTED'
    auth(client2,'schooladmin')
    r=post(client2,'/api/connections/'+cid+'/sync',{'data_type':'training_project','records':RECORDS,**REASON})
    assert r.status_code==200,r.text
    assert r.json()['state']=='DONE','same business request must return the original result, not rewrite history'
    with app2.state.sessions() as db:
        task=db.get(Task,ident);item=task_sync_items(db,task)[0]
        assert digest({'task':task,'item':item})==original
        assert len(list(db.scalars(select(SyncCallLog))))==1


def test_disconnected_duplicate_does_not_append_repeated_attempt_one(app2,client2):
    with app2.state.sessions.begin() as db:
        c=connection(db);c.state='NOT_CONNECTED';cid=c.id
    auth(client2,'schooladmin')
    payload={'data_type':'training_project','records':RECORDS,**REASON}
    first=post(client2,'/api/connections/'+cid+'/sync',payload)
    second=post(client2,'/api/connections/'+cid+'/sync',payload)
    assert first.status_code==second.status_code==200
    assert first.json()['id']==second.json()['id']
    with app2.state.sessions() as db:
        task=db.get(Task,first.json()['id'])
        attempts=list(db.scalars(select(TaskAttempt).where(TaskAttempt.task_id==task.id)))
        assert len(attempts)==1 and task.attempts==1


def test_manual_retry_reloads_item_that_finished_while_waiting_for_parent(app2):
    with app2.state.sessions() as db:
        a,c,adapter,registry,task=prepare(db)
        item=task_sync_items(db,task)[0];item.state='FAILED';item.attempts=4;task.state='FAILED';db.commit()
        # Controlled identity-map staleness: equivalent to the ORM object loaded
        # BEFORE another execution completes and this retry acquires parent locks.
        item.state;task.state
        db.execute(update(SyncItem).where(SyncItem.id==item.id).values(state='DONE',result={'accepted':True},version=item.version+1),execution_options={'synchronize_session':False})
        db.execute(update(Task).where(Task.id==task.id).values(state='DONE'),execution_options={'synchronize_session':False})
        assert item.state=='FAILED'
        with pytest.raises(HTTPException) as exc:
            retry_sync_items(db,a,task,'R9测试等待期间已经完成')
        assert exc.value.status_code==409
        db.expire_all();assert db.get(SyncItem,item.id).state=='DONE'


@pytest.mark.parametrize('mutation',['payload','hash','key','type','connection','missing'])
def test_sync_integrity_failure_is_blocked_before_any_external_call(app2,mutation):
    with app2.state.sessions() as db:
        a,c,adapter,registry,task=prepare(db)
        item=task_sync_items(db,task)[0]
        if mutation=='payload':item.payload={**item.payload,'name':'not the approved payload'}
        elif mutation=='hash':item.payload_hash='0'*64
        elif mutation=='key':item.idempotency_key='0'*64
        elif mutation=='type':item.data_type='teacher_hr'
        elif mutation=='connection':item.connection_id=db.scalar(select(Connection.id).where(Connection.code=='province'))
        else:db.delete(item)
        db.flush();process_sync_task_once(db,task,registry);db.flush()
        assert not adapter.calls,'unsafe queue contents must never reach adapter.send'
        assert task.state=='BLOCKED' and task.error


def test_invalid_reused_member_does_not_allow_own_rows_to_send(app2):
    with app2.state.sessions() as db:
        a,c,adapter,registry,task=prepare(db)
        task.payload={**task.payload,'reused_item_ids':['nonexistent-row'],'requested_rows':2}
        process_sync_task_once(db,task,registry);db.flush()
        assert not adapter.calls and task.state=='BLOCKED'


@pytest.mark.parametrize('terminal',['DONE','FAILED','BLOCKED'])
def test_processor_cannot_resume_terminal_task_without_explicit_retry(app2,terminal):
    with app2.state.sessions() as db:
        a,c,adapter,registry,task=prepare(db);task.state=terminal;db.flush()
        before=digest(task)
        process_sync_task_once(db,task,registry);db.flush()
        assert not adapter.calls and digest(task)==before


def real_contract(db,monkeypatch):
    monkeypatch.setenv('ND_UNIT_TOKEN','R9_NONPRODUCTION_TEST_ONLY')
    c=connection(db);a=_actor(db,'schooladmin');r=AdapterRegistry();adapter=ContractAdapter()
    r.register_production('middle',adapter,endpoint=c.config['endpoint'],credential_env='ND_UNIT_TOKEN');r.configure(True)
    return c,a,r,adapter


def test_failed_latest_probe_with_equal_timestamp_cannot_reactivate_old_success(app2,monkeypatch):
    import app.integrations as integrations
    moment=utcnow().replace(microsecond=0);monkeypatch.setattr(integrations,'utcnow',lambda:moment)
    with app2.state.sessions() as db:
        c,a,r,adapter=real_contract(db,monkeypatch)
        good=probe_connection(db,a,c,r,production=True);good.id='z'*36;good.created_at=moment;db.flush()
        adapter.response={'authenticated':False,'tls_verified':True,'protocol_verified':True}
        bad=probe_connection(db,a,c,r,production=True);bad.id='a'*36;bad.created_at=moment;db.flush()
        with pytest.raises(HTTPException):activate_connection(db,a,c,good.id,r)
        assert c.state=='NOT_CONNECTED' and not live_connection(db,c,r)


def test_new_successful_probe_with_equal_timestamp_is_the_one_that_can_activate(app2,monkeypatch):
    import app.integrations as integrations
    moment=utcnow().replace(microsecond=0);monkeypatch.setattr(integrations,'utcnow',lambda:moment)
    with app2.state.sessions() as db:
        c,a,r,adapter=real_contract(db,monkeypatch)
        adapter.response={'authenticated':False}
        old=probe_connection(db,a,c,r,production=True);old.id='z'*36;old.created_at=moment;db.flush()
        adapter.response=None
        new=probe_connection(db,a,c,r,production=True);new.id='a'*36;new.created_at=moment;db.flush()
        activate_connection(db,a,c,new.id,r)
        assert live_connection(db,c,r)


def test_legacy_check_missing_revision_is_not_backfilled_or_trusted(app2,monkeypatch):
    with app2.state.sessions() as db:
        c,a,r,adapter=real_contract(db,monkeypatch)
        check=probe_connection(db,a,c,r,production=True)
        check.receipt={k:v for k,v in check.receipt.items() if k!='_connection_revision'};db.flush()
        before=digest(check)
        with pytest.raises(HTTPException):activate_connection(db,a,c,check.id,r)
        assert digest(check)==before
        renewed=probe_connection(db,a,c,r,production=True);activate_connection(db,a,c,renewed.id,r)
        assert live_connection(db,c,r)


def test_duplicate_revision_evidence_fails_closed(app2,monkeypatch):
    with app2.state.sessions() as db:
        c,a,r,adapter=real_contract(db,monkeypatch)
        check=probe_connection(db,a,c,r,production=True)
        db.add(ConnectionCheck(connection_id=c.id,configuration_hash=check.configuration_hash,adapter_id=check.adapter_id,
            mode=check.mode,passed=True,reason_code='VERIFIED',receipt=dict(check.receipt),actor_id=a.id,expires_at=check.expires_at))
        db.flush()
        with pytest.raises(HTTPException):activate_connection(db,a,c,check.id,r)


def test_probe_order_is_independent_of_clock_going_backwards(app2,monkeypatch):
    with app2.state.sessions() as db:
        c,a,r,adapter=real_contract(db,monkeypatch)
        first=probe_connection(db,a,c,r,production=True);first.created_at=utcnow()+timedelta(days=1)
        second=probe_connection(db,a,c,r,production=True)
        activate_connection(db,a,c,second.id,r)
        assert second.receipt['_connection_revision']>first.receipt['_connection_revision']
        assert live_connection(db,c,r)


def test_proof_revision_predicate_compiles_for_mysql_without_schema_change():
    from sqlalchemy.dialects import mysql
    query=select(ConnectionCheck).where(ConnectionCheck.receipt['_connection_revision'].as_integer()==7)
    sql=str(query.compile(dialect=mysql.dialect(),compile_kwargs={'literal_binds':True}))
    assert 'JSON_EXTRACT' in sql and '_connection_revision' in sql
