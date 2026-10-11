"""Source-function HTTP harness. No real authentication or full project startup."""
import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace
import logging,time,uuid
import pytest
import httpx
from fastapi import FastAPI,Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.background import BackgroundTask,BackgroundTasks
from fastapi import HTTPException
from app.settings_catalog import validate_manual_source
from sqlalchemy import event,select,func
from sqlalchemy.orm import sessionmaker
from app import models as m
from app.access_logging import record_access_best_effort
from app.maintenance_guard import configured_maintenance
from app.readiness import collect_readiness
ROOT=Path(__file__).resolve().parents[2]


def source_function(name,namespace):
    tree=ast.parse((ROOT/'backend/app/main.py').read_text())
    node=next(n for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name==name)
    node.decorator_list=[]
    exec(compile(ast.Module(body=[node],type_ignores=[]),'actual_main_function','exec'),namespace)
    return namespace[name]


def harness(engine,cfg):
    factory=sessionmaker(engine,expire_on_commit=False)
    log=logging.getLogger('nd-isolated-http')
    namespace={'Request':Request,'JSONResponse':JSONResponse,'cfg':cfg,'sessions':factory,'log':log,
               'time':time,'uuid':uuid,'run_in_threadpool':run_in_threadpool,
               'record_access_best_effort':record_access_best_effort,'configured_maintenance':configured_maintenance,
               'BackgroundTask':BackgroundTask,'BackgroundTasks':BackgroundTasks}
    app=FastAPI();app.middleware('http')(source_function('security',namespace))
    @app.post('/api/checkpoint-fixture',status_code=201)
    def commit_fixture():
        with factory.begin() as db:
            db.add(m.Notice(id='new-notice',title='隔离HTTP事务样本',body='仅用于测试',org_id='school',author_id='admin'))
        return {'committed':True}
    health=source_function('health',{'JSONResponse':JSONResponse,'collect_readiness':collect_readiness,'engine':engine,'cfg':cfg,'__version__':'isolated-http'})
    app.get('/api/health')(health)
    return app,factory


def request(app,method,path):
    async def perform():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as c:return await c.request(method,path)
    return asyncio.run(perform())


def test_access_failure_does_not_reverse_committed_201(engine,cfg,caplog):
    app,factory=harness(engine,cfg)
    def broken(mapper,conn,target):raise RuntimeError('DO_NOT_LOG_secret_password')
    event.listen(m.Audit,'before_insert',broken)
    try:r=request(app,'POST','/api/checkpoint-fixture')
    finally:event.remove(m.Audit,'before_insert',broken)
    assert r.status_code==201 and r.json()=={'committed':True}
    assert 'x-request-id' in r.headers and r.headers['x-content-type-options']=='nosniff'
    with factory() as db:
        assert db.get(m.Notice,'new-notice') is not None
        assert db.scalar(select(func.count()).select_from(m.Audit))==0
    assert 'access_log_write_failed' in caplog.text
    assert 'DO_NOT_LOG_secret_password' not in caplog.text


def test_maintenance_rejects_before_business_commit(engine,cfg,tmp_path):
    cfg.maintenance_dir=tmp_path;(tmp_path/'active').write_text('maintenance')
    app,factory=harness(engine,cfg)
    r=request(app,'POST','/api/checkpoint-fixture')
    assert r.status_code==503 and r.json()['code']=='MAINTENANCE'
    with factory() as db:assert db.get(m.Notice,'new-notice') is None
    assert request(app,'GET','/api/health').status_code==200


def test_actual_health_endpoint_returns_503_for_missing_guard(engine,cfg):
    app,factory=harness(engine,cfg)
    with factory.begin() as db:db.delete(db.get(m.Guard,'calculations'))
    r=request(app,'GET','/api/health')
    assert r.status_code==503 and r.json()['initialization']['checks']['calculations_guard'] is False


def test_broken_fallback_logger_also_does_not_raise(engine):
    class BrokenFactory:
        def begin(self):raise RuntimeError('secret')
    class BrokenLogger:
        def error(self,*args):raise RuntimeError('broken fallback')
    assert record_access_best_effort(BrokenFactory(),BrokenLogger(),{'request_id':'controlled'}) is False


def test_existing_insert_service_propagates_critical_audit_failure(engine,actor):
    # Run the existing insert_record body under a real Session transaction.
    # The original core.audit implementation is missing; only failure propagation
    # and the service's absence of an inner commit are verified by this test.
    tree=ast.parse((ROOT/'backend/app/services.py').read_text())
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='insert_record')
    def serial(obj):return {'id':obj.id,'version':obj.version}
    def critical_failure(*args,**kwargs):raise RuntimeError('critical audit unavailable')
    # insert_record now validates the manual source against the seeded business dictionary.
    ns={**vars(m),'RecordIn':object,'serial':serial,'audit':critical_failure,'validate_manual_source':validate_manual_source,'HTTPException':HTTPException}
    exec(compile(ast.Module(body=[node],type_ignores=[]),'existing_insert_record','exec'),ns)
    class Payload:
        teacher_id='t1';reason='隔离事务回滚';source='经核对人工录入'
        def model_dump(self,**kwargs):
            from datetime import date
            return dict(id='should-rollback',external_key='newkey',teacher_id='t1',source='经核对人工录入',event_date=date(2026,9,1),project_code='p',project='p',course_code='c',course='c',class_code='b',class_name='b',hours=1,participants=1,income=1)
    factory=sessionmaker(engine)
    with pytest.raises(RuntimeError,match='critical audit'):
        with factory.begin() as db:ns['insert_record'](db,actor,Payload())
    with factory() as db:
        assert db.get(m.TrainingRecord,'should-rollback') is None
        assert db.scalar(select(func.count()).select_from(m.RecordRevision))==0
