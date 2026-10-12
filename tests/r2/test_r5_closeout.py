"""R5 isolated SQL/API contract fixtures. NO real external connection acceptance."""
import json
from datetime import timedelta
import pytest
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from fastapi import HTTPException
from conftest import auth,post,put
from test_r3_org_assessment import make_rule,calculate,action
from test_r4_internal_closeout import configure_middle
from app.models import Connection,Task,User,Org,Assessment,Rule,utcnow
from app.core import digest
from app.integrations import (ADAPTERS,AdapterRegistry,ConnectionCheck,probe_connection,activate_connection,
    live_connection,configuration_hash,enqueue_sync,process_sync_task_once,SyncItem,SyncCallLog,task_sync_items)
from app.inbound_sync import _actor,create_pull_task,process_pull_task_once,IntegrationSchedule
from app.reference_data import (TrainingProjectMaster,TrainingCourseMaster,InboundBatch,InboundRow,
    preview_inbound,confirm_inbound,validate_inbound)
REASON={'reason':'R5隔离回归测试','basis':'合成测试，不是学校验收'}

def run_due_sync(db,task,registry):
    # Explicit due tick survives MySQL's whole-second timestamp rounding.
    for item in task_sync_items(db,task):
        if item.state in {'PENDING','RETRY'}:item.next_at=utcnow()-timedelta(seconds=2)
    return process_sync_task_once(db,task,registry)


class ContractAdapter:
    """No network operations: a deliberate protocol double, test DB only."""
    adapter_id='unit.protocol.contract'
    def __init__(self,response=None):self.calls=[];self.response=response
    def probe(self,**kwargs):
        self.calls.append('probe')
        return self.response if self.response is not None else {'authenticated':True,'tls_verified':True,'protocol_verified':True,'token':'NEVER_PERSIST_TOKEN'}
    def send(self,**kwargs):
        self.calls.append(kwargs)
        return self.response if self.response is not None else {'accepted':True,'code':'ACK','receipt_id':'fixture-001','token':'NEVER_PERSIST_TOKEN'}
    def pull(self,**kwargs):self.calls.append(kwargs);return self.response

def connection(db):
    c=db.scalar(select(Connection).where(Connection.code=='middle'))
    c.config={'endpoint':'https://unit-school.invalid/inbound','secret_env':'ND_UNIT_TOKEN','retry_count':3}
    c.mappings=[{'source':k,'target':k,'transform':'text','required':True} for k in ('code','name')]
    db.flush();return c

def fresh_preview(client,typ,records,mappings):
    c=configure_middle(client,mappings)
    r=post(client,'/api/connections/'+c['id']+'/inbound/preview',{'data_type':typ,'records':records,'source_label':'R5合成预览',**REASON})
    assert r.status_code==200,r.text
    return c,r.json()

@pytest.mark.parametrize('response',[{}, {'authenticated':True}, {'authenticated':1,'tls_verified':True,'protocol_verified':True}])
def test_incomplete_handshake_never_activates(app2,monkeypatch,response):
    monkeypatch.setenv('ND_UNIT_TOKEN','NEVER_PERSIST_TOKEN')
    with Session(app2.state.engine) as db:
        c=connection(db);registry=AdapterRegistry();registry.register_production('middle',ContractAdapter(response),endpoint=c.config['endpoint'],credential_env='ND_UNIT_TOKEN');registry.configure(True)
        check=probe_connection(db,_actor(db,'schooladmin'),c,registry,production=True)
        assert not check.passed and c.state=='NOT_CONNECTED'
        with pytest.raises(HTTPException):activate_connection(db,_actor(db,'schooladmin'),c,check.id,registry)
        assert 'NEVER_PERSIST_TOKEN' not in json.dumps(check.receipt)

def test_test_registry_cannot_be_used_in_production_or_activate(app2,monkeypatch):
    monkeypatch.setenv('ND_UNIT_TOKEN','NEVER_PERSIST_TOKEN');registry=AdapterRegistry();registry.register_for_test('middle',ContractAdapter())
    with Session(app2.state.engine) as db:
        c=connection(db);a=_actor(db,'schooladmin');check=probe_connection(db,a,c,registry,production=False)
        assert check.passed and check.mode=='TEST_ONLY'
        with pytest.raises(HTTPException):activate_connection(db,a,c,check.id,registry)
    registry.configure(True);assert registry.get('middle') is None
    with pytest.raises(RuntimeError):registry.register_for_test('middle',ContractAdapter())

def test_current_probe_activation_expiry_and_config_change_are_enforced(app2,monkeypatch):
    monkeypatch.setenv('ND_UNIT_TOKEN','NEVER_PERSIST_TOKEN')
    with Session(app2.state.engine) as db:
        c=connection(db);a=_actor(db,'schooladmin');registry=AdapterRegistry();adapter=ContractAdapter()
        registry.register_production('middle',adapter,endpoint=c.config['endpoint'],credential_env='ND_UNIT_TOKEN');registry.configure(True)
        check=probe_connection(db,a,c,registry,production=True);activate_connection(db,a,c,check.id,registry)
        assert live_connection(db,c,registry)
        original=dict(c.config);c.config={**original,'owner':'changed'};assert not live_connection(db,c,registry)
        with pytest.raises(HTTPException):activate_connection(db,a,c,check.id,registry)
        c.config=original;check.expires_at=utcnow()-timedelta(seconds=1);assert live_connection(db,c,registry)
        # Publication survives proof age; expiry still prevents NEW activation.
        fresh=probe_connection(db,a,c,registry,production=True)
        fresh.expires_at=utcnow()-timedelta(seconds=1)
        with pytest.raises(HTTPException):activate_connection(db,a,c,fresh.id,registry)
        assert not live_connection(db,c,registry)
        assert 'NEVER_PERSIST_TOKEN' not in json.dumps(check.receipt)

def test_probe_api_missing_adapter_and_replay_do_not_claim_connected(client2,app2):
    auth(client2,'schooladmin')
    c=next(x for x in client2.get('/api/connections/catalog').json()['items'] if x['connection']['code']=='middle')['connection']
    payload={'expected_version':c['version'],**REASON}
    r=post(client2,f"/api/connections/{c['id']}/probe",payload,key='r5_probe_replay_001');assert r.status_code==200,r.text
    assert r.json()['check']['passed'] is False and r.json()['connection']['state']=='NOT_CONNECTED'
    same=post(client2,f"/api/connections/{c['id']}/probe",payload,key='r5_probe_replay_001')
    assert same.status_code==200 and same.json()==r.json()
    with Session(app2.state.engine) as db:assert db.scalar(select(func.count()).select_from(ConnectionCheck))==1
    auth(client2,'teacher');assert client2.get(f"/api/connections/{c['id']}/checks").status_code==403

@pytest.mark.parametrize('response',[None,{}, {'accepted':False}, {'accepted':'true'}])
def test_sync_requires_explicit_positive_ack_and_logs_failure(app2,response):
    with Session(app2.state.engine) as db:
        c=connection(db);c.state='CONNECTED';adapter=ContractAdapter(response)
        if response is None:adapter.send=lambda **kwargs:None
        registry=AdapterRegistry();registry.register_for_test('middle',adapter)
        task=enqueue_sync(db,_actor(db,'schooladmin'),c,'training_project',[{'business_key':'R5ACK','code':'RP','name':'项目'}],'测试')
        run_due_sync(db,task,registry);db.flush()
        item=task_sync_items(db,task)[0];log=db.scalar(select(SyncCallLog).where(SyncCallLog.item_id==item.id))
        assert task.state=='RETRY' and item.state=='RETRY' and log.result=='ERROR' and not log.acknowledged

def test_reused_sync_rows_keep_receipts_and_no_duplicate_send(app2,client2):
    registry=AdapterRegistry();adapter=ContractAdapter();registry.register_for_test('middle',adapter)
    with Session(app2.state.engine) as db:
        c=connection(db);c.state='CONNECTED';a=_actor(db,'schooladmin')
        one={'business_key':'R5D1','code':'D1','name':'项目1'};two={'business_key':'R5D2','code':'D2','name':'项目2'}
        task=enqueue_sync(db,a,c,'training_project',[one],'测试');run_due_sync(db,task,registry)
        next_task=enqueue_sync(db,a,c,'training_project',[one,two],'测试');run_due_sync(db,next_task,registry)
        assert len(adapter.calls)==2 and next_task.state=='DONE'
        assert next_task.result['total']==2 and next_task.result['reused']==1
        assert 'NEVER_PERSIST_TOKEN' not in json.dumps([x.result for x in task_sync_items(db,next_task)])
        task_id=next_task.id;db.commit()
    auth(client2,'schooladmin');r=client2.get('/api/sync-tasks/'+task_id+'/evidence');assert r.status_code==200,r.text
    proof=r.json();assert proof['sha256']==digest(proof['evidence'])
    assert len(proof['evidence']['items'])==2 and len(proof['evidence']['calls'])==2
    assert proof['evidence']['external_acceptance'] is False
    auth(client2,'teacher');assert client2.get('/api/sync-tasks/'+task_id+'/evidence').status_code==403

@pytest.mark.parametrize('data',[{'records':None},{},None,{'records':[False]}])
def test_pull_invalid_response_not_success(app2,data):
    with Session(app2.state.engine) as db:
        c=connection(db);c.state='CONNECTED';registry=AdapterRegistry();adapter=ContractAdapter(data);registry.register_for_test('middle',adapter)
        task=create_pull_task(db,_actor(db,'schooladmin'),c,'training_project','FULL')
        process_pull_task_once(db,task,registry);assert task.state=='RETRY'
        assert db.scalar(select(func.count()).select_from(InboundBatch))==0

def test_revoked_schedule_blocks_queued_auto_commit(app2):
    with Session(app2.state.engine) as db:
        c=connection(db);c.state='CONNECTED';a=_actor(db,'schooladmin')
        schedule=IntegrationSchedule(connection_id=c.id,data_type='training_project',frequency_minutes=30,auto_commit=True,active=True,approved_by=a.id)
        db.add(schedule);db.flush();task=create_pull_task(db,a,c,'training_project','FULL',schedule=schedule);schedule.active=False
        registry=AdapterRegistry();adapter=ContractAdapter({'records':[{'code':'NEW','name':'新项目'}]});registry.register_for_test('middle',adapter)
        process_pull_task_once(db,task,registry);assert task.state=='BLOCKED' and adapter.calls==[]

def test_inbound_preview_relations_and_confirmation_recheck(client2,app2):
    auth(client2,'schooladmin');maps=[{'source':k,'target':k,'transform':'text','required':True} for k in ['code','name','project_code']]
    c,b=fresh_preview(client2,'course',[{'code':'C-R5','name':'课程','project_code':'P-R5'}],maps)
    assert b['errors']==1
    detail=client2.get('/api/inbound-batches/'+b['id']).json();assert '尚未入库' in str(detail['rows']['items'][0]['errors'])
    with Session(app2.state.engine) as db:db.add(TrainingProjectMaster(code='P-R5',name='项目',active=True));db.commit()
    c,b=fresh_preview(client2,'course',[{'code':'C-R5','name':'课程','project_code':'P-R5'}],maps);assert b['errors']==0
    with Session(app2.state.engine) as db:db.scalar(select(TrainingProjectMaster).where(TrainingProjectMaster.code=='P-R5')).active=False;db.commit()
    r=post(client2,'/api/inbound-batches/'+b['id']+'/confirm',{'expected_version':b['version'],**REASON});assert r.status_code==409
    with Session(app2.state.engine) as db:assert db.scalar(select(func.count()).select_from(TrainingCourseMaster))==0

@pytest.mark.parametrize('mutation',['row','mapping','row_count'])
def test_inbound_confirm_rejects_changed_preview_or_configuration(app2,mutation):
    with Session(app2.state.engine) as db:
        c=connection(db);a=_actor(db,'schooladmin');batch=preview_inbound(db,a,c,'training_project',[{'code':'T1','name':'项目'}])
        if mutation=='row':db.scalar(select(InboundRow).where(InboundRow.batch_id==batch.id)).mapped={'code':'T2','name':'被改动'}
        elif mutation=='mapping':c.mappings=[]
        else:db.delete(db.scalar(select(InboundRow).where(InboundRow.batch_id==batch.id)))
        db.flush()
        with pytest.raises(HTTPException):confirm_inbound(db,a,batch,batch.version,'测试确认')
        assert db.scalar(select(func.count()).select_from(TrainingProjectMaster))==0

def test_inbound_worker_caught_failure_rolls_back_every_formal_write(app2,monkeypatch):
    import app.reference_data as ref
    with Session(app2.state.engine) as db:
        c=connection(db);a=_actor(db,'schooladmin');batch=preview_inbound(db,a,c,'training_project',[{'code':'A','name':'甲'},{'code':'B','name':'乙'}]);db.commit()
        a=_actor(db,'schooladmin');calls=[];original=ref.audit
        def fail_on_second(db,actor,kind,*args,**kwargs):
            if kind=='training_project':
                calls.append(kind)
                if len(calls)==2:raise RuntimeError('synthetic crash')
            return original(db,actor,kind,*args,**kwargs)
        monkeypatch.setattr(ref,'audit',fail_on_second)
        with pytest.raises(RuntimeError):confirm_inbound(db,a,batch,batch.version,'模拟第二行异常')
        db.commit()  # Worker may still commit its attempt record; business writes must be absent.
        assert db.scalar(select(func.count()).select_from(TrainingProjectMaster))==0
        assert db.get(InboundBatch,batch.id).state=='PREVIEW'
        assert db.scalar(select(func.count()).select_from(InboundRow))==2

def test_hr_normalization_is_idempotent():
    x={'staff_no':'J001','name':'某教师','org_code':'dept1','source_updated_at':'2026-09-18T12:00:00+08:00','custom':'note'}
    one,errors=validate_inbound('teacher_hr',x);two,errors2=validate_inbound('teacher_hr',one)
    assert not errors and not errors2 and one==two and one['extra']=={'custom':'note'}

def test_org_rule_copy_is_draft_no_trial_no_mutation(client2,app2):
    from app.org_assessment import OrganizationRuleTrial
    auth(client2,'schooladmin');source=make_rule(client2,'dept','dept1')
    r=post(client2,'/api/organization-assessment-rules/'+source['id']+'/copy',{'expected_version':source['version'],'name':'R5复制规则','period_id':'period2026',**REASON})
    assert r.status_code==200,r.text
    copy=r.json();assert copy['id']!=source['id'] and copy['state']=='DRAFT' and copy['version_no']==source['version_no']+1
    assert copy['config']==source['config'] and copy['trial_required'] is True
    with Session(app2.state.engine) as db:assert not db.scalar(select(OrganizationRuleTrial.id).where(OrganizationRuleTrial.rule_id==copy['id']))
    r=post(client2,'/api/organization-assessment-rules/'+copy['id']+'/actions',{'action':'activate','expected_version':copy['version'],**REASON});assert r.status_code==409

def test_org_ranking_ties_pagination_and_authorization(client2):
    auth(client2,'schooladmin');rule=make_rule(client2,'dept','dept1');calculate(client2,'dept','dept1');calculate(client2,'dept','dept2')
    params={'period_id':'period2026','target_kind':'dept','rule_id':rule['id'],'size':1}
    a=client2.get('/api/organization-assessments/ranking',params=params);b=client2.get('/api/organization-assessments/ranking',params={**params,'page':2})
    assert a.status_code==b.status_code==200,(a.text,b.text)
    assert a.json()['total']==2 and a.json()['items'][0]['rank']==b.json()['items'][0]['rank']==1
    assert a.json()['items'][0]['id']!=b.json()['items'][0]['id']
    assert client2.get('/api/organization-assessments/ranking',params={**params,'target_kind':'college'}).status_code==422
    auth(client2,'depthead');r=client2.get('/api/organization-assessments/ranking',params=params);assert r.status_code==200
    assert r.json()['scope']=='own_organization_only' and r.json()['total']==1
    auth(client2,'teacher');assert client2.get('/api/organization-assessments/ranking',params=params).status_code==403

def test_org_archive_print_is_frozen_and_rejects_tampering(client2,app2):
    from app.org_assessment import OrganizationAssessment
    auth(client2,'schooladmin');make_rule(client2,'dept','dept1');x=calculate(client2,'dept','dept1')
    draft=client2.get('/api/organization-assessments/'+x['id']+'/print');assert draft.status_code==200 and draft.json()['document_status']=='DRAFT_NOT_FINAL'
    auth(client2,'depthead');x=action(client2,x,'review').json()
    auth(client2,'schooladmin');x=action(client2,x,'school_audit').json();x=action(client2,x,'archive').json()
    with Session(app2.state.engine) as db:db.get(Org,'dept1').name='后来改的组织名称';db.commit()
    r=client2.get('/api/organization-assessments/'+x['id']+'/print');assert r.status_code==200,r.text
    assert r.json()['immutable'] and r.json()['target']['name']!='后来改的组织名称' and r.json()['assessment']['state']=='ARCHIVED'
    auth(client2,'otherdept');assert client2.get('/api/organization-assessments/'+x['id']+'/print').status_code==403
    with Session(app2.state.engine) as db:
        obj=db.get(OrganizationAssessment,x['id']);obj.archive={**obj.archive,'reason':'篡改'};db.commit()
    auth(client2,'schooladmin');assert client2.get('/api/organization-assessments/'+x['id']+'/print').status_code==409

def test_aggregate_state_filter_matches_drill_and_keeps_income_semantics(client2,app2):
    with Session(app2.state.engine) as db:
        r=Rule(kind='assessment',name='隔离教师规则',period_id='period2026',version_no=1,config={'components':[]},fingerprint='0'*64,created_by='schooladmin',reason='测试')
        db.add(r);db.flush()
        for tid,state,returned,score in [('teacher','SCHOOL',True,85),('otherteacher','ARCHIVED',False,95)]:
            db.add(Assessment(teacher_id=tid,period_id='period2026',rule_id=r.id,score=score,state=state,returned=returned,detail=[],source_snapshot={}))
        db.commit()
    auth(client2,'schooladmin');params={'period_id':'period2026','state':'SCHOOL','returned':'true'}
    r=client2.get('/api/statistics',params=params);assert r.status_code==200,r.text
    summary=r.json();assert summary['assessment_states']=={'SCHOOL':1} and summary['assessment_score_summary']['count']==1
    assert summary['records']==2 and summary['state_filter_scope']=='assessment_only'
    drill=client2.get('/api/assessments',params=summary['assessment_scope']);assert drill.status_code==200 and drill.json()['total']==1
    assert client2.get('/api/statistics',params={'state':'BROKEN'}).status_code==422
    assert client2.get('/api/statistics',params={'returned':'maybe'}).status_code==422


def test_deployment_pins_credential_reference_and_rotation_invalidates_handshake(app2,monkeypatch):
    monkeypatch.setenv('ND_UNIT_TOKEN','fixture_secret_1')
    monkeypatch.setenv('ND_DATABASE_URL','NEVER_READ_DATABASE_SECRET')
    with Session(app2.state.engine) as db:
        c=connection(db);a=_actor(db,'schooladmin');adapter=ContractAdapter();registry=AdapterRegistry()
        registry.register_production('middle',adapter,endpoint=c.config['endpoint'],credential_env='ND_UNIT_TOKEN');registry.configure(True)
        c.config={**c.config,'secret_env':'ND_DATABASE_URL'}
        rejected=probe_connection(db,a,c,registry,production=True)
        assert rejected.reason_code=='CONNECTION_CONTEXT_NOT_PINNED' and adapter.calls==[]
        c.config={**c.config,'secret_env':'ND_UNIT_TOKEN'}
        good=probe_connection(db,a,c,registry,production=True);activate_connection(db,a,c,good.id,registry)
        from app.core import serial
        assert '_credential_sha256' not in serial(good)['receipt']
        monkeypatch.setenv('ND_UNIT_TOKEN','fixture_secret_2')
        assert not live_connection(db,c,registry)
        with pytest.raises(HTTPException):activate_connection(db,a,c,good.id,registry)


def test_restore_invalidates_connections_schedules_and_pending_external_tasks(app2,tmp_path):
    from app.maintenance import sanitize_restore
    secret=tmp_path/'restore_secret';secret.write_text('RestoreFresh_R5_2026!')
    with Session(app2.state.engine) as db:
        c=connection(db);c.state='CONNECTED';cid=c.id
        proof=ConnectionCheck(connection_id=cid,configuration_hash=configuration_hash(c),mode='TEST_ONLY',passed=True,
            reason_code='SYNTHETIC',actor_id='schooladmin',expires_at=utcnow()+timedelta(hours=12))
        schedule=IntegrationSchedule(connection_id=cid,data_type='training_project',frequency_minutes=30,active=True,auto_commit=True,approved_by='schooladmin')
        db.add_all([proof,schedule]);db.flush();pid=proof.id;sid=schedule.id
        tasks=[Task(kind=kind,owner_id='schooladmin',key='restore-r5-'+state+kind,payload={'connection_id':cid},state=state) for state in ['PENDING','RETRY','RUNNING','DONE'] for kind in ['sync','inbound_pull']]
        db.add_all(tasks);db.commit();ids=[t.id for t in tasks]
    sanitize_restore(app2.state.settings,'schooladmin',secret)
    with Session(app2.state.engine) as db:
        assert db.get(Connection,cid).state=='NOT_CONNECTED'
        assert db.get(ConnectionCheck,pid).expires_at<=utcnow()
        assert not db.get(IntegrationSchedule,sid).active and not db.get(IntegrationSchedule,sid).auto_commit
        states=[db.get(Task,id).state for id in ids]
        assert states.count('BLOCKED')==6 and states.count('DONE')==2


def test_sync_rejects_duplicate_business_key_without_creating_a_task(app2):
    with Session(app2.state.engine) as db:
        c=connection(db)
        before=db.scalar(select(func.count()).select_from(Task))
        with pytest.raises(HTTPException):enqueue_sync(db,_actor(db,'schooladmin'),c,'training_project',[{'business_key':'A','code':'A','name':'甲'},{'business_key':'A','code':'B','name':'乙'}])
        assert db.scalar(select(func.count()).select_from(Task))==before


def test_sync_missing_reused_item_cannot_be_reported_done(app2):
    from app.integrations import finalize_sync_task
    with Session(app2.state.engine) as db:
        c=connection(db)
        task=enqueue_sync(db,_actor(db,'schooladmin'),c,'training_project',[{'business_key':'A','code':'A','name':'甲'}])
        item=db.scalar(select(SyncItem).where(SyncItem.task_id==task.id));item.state='DONE'
        task.payload={**task.payload,'requested_rows':2,'reused_item_ids':['missing-item']}
        db.flush();finalize_sync_task(db,task)
        assert task.state=='FAILED' and task.result['total']==1 and task.result['requested_rows']==2


@pytest.mark.parametrize('override',[{'database_engine':'sqlite'},{'synthetic':True},{'mysql_version':'8.0.40'},{'mysql_version':'8.4.0-MariaDB'},{'evidence_kind':'DIALECT_COMPILE_ONLY'}])
def test_release_gate_rejects_fake_mysql_even_when_flags_are_true(override):
    import importlib.util,sys
    from pathlib import Path
    root=Path(__file__).resolve().parents[2];sys.path.insert(0,str(root/'scripts'))
    spec=importlib.util.spec_from_file_location('r5_release_gate',root/'scripts/release_gate.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    evidence={'evidence_kind':'REAL_MYSQL_8_4','database_engine':'mysql','mysql_version':'8.4.6','synthetic':False,'installation_scope':'fresh_school_only','baseline_revision':'20260918_0001',**{k:True for k in ['fresh_migration','canonical_repeat_noop','canonical_restore_drill','schema_checks','legacy_upgrade_rejected','legacy_restore_rejected','stamp_only_rejected','provenance_checked']}}
    assert m.evidence_pass('mysql',evidence)
    assert not m.evidence_pass('mysql',{**evidence,**override})
