"""五项高优先级修复：只使用隔离夹具、合成来源和正常登录。"""
from datetime import timedelta
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from app import core, social_training as st
from app.models import Connection, Setting, Task, User, utcnow
from app.reference_data import InboundBatch, TeacherHrProfile, TrainingProjectMaster, cx_login_aliases
from app.social_models import SocialClaim, SocialResource, SocialUnit
from app.identities import identity_actor
from app.inbound_sync import IntegrationSchedule, create_pull_task, enqueue_due_schedules, process_pull_task_once
from app.paged_inbound import _finalize
from app.sync_policy import retry_pull_task
from conftest import auth, post, put
from test_applications import setup as app_setup, apply_course, act, todo_ids
from test_school_duties_in_account import _role, _save, REVIEW
from test_social_training import setup_social, recognized, action, detail  # noqa: F401
from test_point_review import sent_review
from test_cx_unmatched import seed_unmatched, course, cx_rows
from test_integration_closeout import SyntheticHub, prepare_run, page_config, actor


@pytest.mark.parametrize('change', ['removed', 'expired'])
def test_school_duty_requires_live_identity_and_preserves_local_duties(client2, app2, monkeypatch, change):
    c=client2;ids=app_setup(app2,coordinator='collegehead');_role(app2)
    today=core.school_today()
    auth(c,'schooladmin')
    assert _save(c,'collegehead',extras=[{**REVIEW[0],'valid_until':today.isoformat()}],duties=['coordinator']).status_code==200
    with app2.state.sessions.begin() as db:
        setting=db.get(Setting,'social_training_duties')
        setting.value={**setting.value,'dean':['collegehead'],'secretary':['depthead']}
        assert 'coordinator' in st.actor_duties(db,identity_actor(db,db.get(User,'collegehead'),''))
    auth(c,'teacher');ident=apply_course(c,ids['K1']).json()['item']['id']
    auth(c,'collegehead');assert act(c,ident,'approve').json()['item']['state']=='SCHOOL'
    auth(c,'schooladmin')
    if change=='removed':assert _save(c,'collegehead',extras=[]).status_code==200
    else:monkeypatch.setattr(core,'school_today',lambda:today+timedelta(days=1))
    assert 'collegehead' in c.get('/api/social/duties').json()['ineligible']['coordinator']
    with app2.state.sessions() as db:
        assert st.school_duty_staffing(db)['coordinator']==0
        dean=identity_actor(db,db.get(User,'collegehead'),'')
        assert 'coordinator' not in st.actor_duties(db,dean) and 'dean' in st.actor_duties(db,dean)
        st.duty(db,dean,'dean','teacher','college1')
        st.duty(db,identity_actor(db,db.get(User,'depthead'),''),'secretary','teacher','college1')
    auth(c,'collegehead')
    assert ident not in todo_ids(c)
    assert c.get('/api/applications/'+ident).json()['permissions']['approve'] is False
    assert act(c,ident,'approve').status_code==403
    auth(c,'schooladmin');assert _save(c,'collegehead',extras=REVIEW).status_code==200
    auth(c,'collegehead');assert act(c,ident,'approve').json()['item']['state']=='ACTIVE'


@pytest.mark.parametrize('decision', ['uphold', 'dismiss'])
def test_point_review_ruling_recuses_project_participant(recognized, client2, app2, decision):
    c=client2;claim_id,_=recognized
    with app2.state.sessions.begin() as db:
        claim=db.get(SocialClaim,claim_id)
        unit=db.scalar(select(SocialUnit).where(SocialUnit.project_id==claim.project_id))
        db.get(User,'collegehead').staff_no='AUDIT-DEAN'
        unit.data={**unit.data,'teachers':[*unit.data['teachers'],{'teacher_id':'collegehead','staff_type':'internal','role':'instructor'}]}
        setting=db.get(Setting,'social_training_duties');setting.value={**setting.value,'dean':['collegehead','schooladmin']}
    ident=sent_review(c,claim_id)
    auth(c,'teacher');assert action(c,'point-reviews','social_resource',ident,'explain').status_code==200
    auth(c,'collegehead')
    assert detail(c,'social_resource',ident)['can_review'] is False
    assert ident not in {x['id'] for x in c.get('/api/todos').json()['items']}
    assert action(c,'point-reviews','social_resource',ident,decision).status_code==403
    assert detail(c,'social_resource',ident)['item']['state']=='COLLEGE'
    with app2.state.sessions() as db:
        assert not db.scalar(select(SocialResource.id).where(SocialResource.kind=='correction'))
    auth(c,'schooladmin');r=action(c,'point-reviews','social_resource',ident,decision)
    assert r.status_code==200,r.text
    if decision=='uphold':
        fix=r.json()['item']['data']['correction_id']
        assert detail(c,'social_resource',fix)['item']['state']=='DEAN'
    else:assert r.json()['item']['data']['outcome']=='kept'


def test_same_name_claim_waits_for_admin(client2, app2):
    c=client2;auth(c,'schooladmin');seed_unmatched(c,app2)
    with app2.state.sessions.begin() as db:
        db.add(TeacherHrProfile(staff_no='J002',user_id='otherteacher',name='测试教师一',org_code='dept2'))
    auth(c,'otherteacher');before=cx_rows(app2)
    r=post(c,'/api/reference/cx-claims',{'login':'phone138'})
    assert r.status_code==200 and r.json()['state']=='PENDING' and r.json()['moved']==0
    assert cx_rows(app2)==before
    auth(c,'schooladmin')
    assert post(c,'/api/reference/cx-claims/decide',{'login':'phone138','staff_no':'J002','decision':'reject','reason':'同名但不是建课人'}).status_code==200
    assert cx_rows(app2)==before


def claim_login(c):
    auth(c,'teacher');r=post(c,'/api/reference/cx-claims',{'login':'team7'});assert r.status_code==200,r.text
    auth(c,'schooladmin');r=post(c,'/api/reference/cx-claims/decide',{'login':'team7','staff_no':'J001','decision':'approve'})
    assert r.status_code==200,r.text


@pytest.mark.parametrize('change', ['revoke','new_claim','dictionary','real_staff','legacy'])
def test_cx_preview_rechecks_current_ownership(client2, app2, change):
    c=client2;auth(c,'schooladmin');seed_unmatched(c,app2)
    if change!='new_claim':claim_login(c)
    with app2.state.sessions() as db:cid=db.scalar(select(Connection).where(Connection.code=='middle')).id
    def preview():
        r=post(c,'/api/connections/'+cid+'/inbound/preview',{'data_type':'online_course','records':[course('team7','X7','测试教师一 等')],'source_label':'隔离预览','reason':'核对映射'})
        assert r.status_code==200 and r.json()['errors']==0,r.text
        return r.json()
    def confirm(batch):
        return post(c,'/api/inbound-batches/'+batch['id']+'/confirm',{'expected_version':batch['version'],'reason':'确认隔离预览'})
    batch=preview()
    if change=='new_claim':claim_login(c)
    elif change=='revoke':assert post(c,'/api/reference/cx-claims/decide',{'login':'team7','staff_no':'J001','decision':'revoke','reason':'核实归属错误'}).status_code==200
    elif change=='dictionary':assert post(c,'/api/settings',{'key':'dict:cx_login_alias','value':{'name':'隔离对照','items':['team7=J002']},'reason':'管理员更正对照'}).status_code==200
    elif change=='real_staff':
        with app2.state.sessions.begin() as db:db.add(TeacherHrProfile(staff_no='team7',name='新增在职人员',org_code='dept1'))
    else:
        with app2.state.sessions.begin() as db:db.get(InboundBatch,batch['id']).receipt={}
    before=cx_rows(app2);r=confirm(batch)
    assert r.status_code==409 and '重新生成预览' in r.text,r.text
    assert cx_rows(app2)==before
    with app2.state.sessions() as db:assert db.get(InboundBatch,batch['id']).state=='PREVIEW'
    r=confirm(preview());assert r.status_code==200,r.text


class SmallHub(SyntheticHub):
    def __init__(self):
        super().__init__(3);self.config=page_config(2)
    def pull_chunk(self, **kwargs):
        result=super().pull_chunk(**kwargs)
        if not result['has_more']:result['next_cursor']='verified-watermark'
        return result


def process_and_confirm(app,c,ident,registry):
    with app.state.sessions.begin() as db:
        task=db.get(Task,ident);process_pull_task_once(db,task,registry)
        pending=(task.result or {}).get('pending') if task.state=='WAITING_CONFIRMATION' else None
        batch=db.get(InboundBatch,pending['batch_id']) if pending else None
        confirm=(batch.id,batch.version) if batch else None
    if confirm:
        r=post(c,'/api/inbound-batches/'+confirm[0]+'/confirm',{'expected_version':confirm[1],'reason':'确认合成分页'})
        assert r.status_code==200,r.text


def rollback_page(c,app,bid):
    with app.state.sessions() as db:version=db.get(InboundBatch,bid).version
    return post(c,'/api/inbound-batches/'+bid+'/rollback',{'expected_version':version,'reason':'撤销隔离分页','basis':'隔离核对依据'})


@pytest.mark.parametrize('automatic',[True,False])
@pytest.mark.parametrize('finished',[True,False])
def test_page_rollback_stops_old_run_and_full_recovery_works(client2,app2,monkeypatch,automatic,finished):
    c=client2;auth(c,'schooladmin');hub=SmallHub();registry,ident=prepare_run(app2,hub,automatic)
    monkeypatch.setattr('app.routes.integrations.ADAPTERS',registry)
    process_and_confirm(app2,c,ident,registry)
    with app2.state.sessions() as db:bid=db.get(Task,ident).result['chunks'][0]['batch_id']
    if finished:process_and_confirm(app2,c,ident,registry)
    r=rollback_page(c,app2,bid);assert r.status_code==200,r.text
    if finished:
        with app2.state.sessions() as db:second=db.get(Task,ident).result['chunks'][1]['batch_id']
        r=rollback_page(c,app2,second);assert r.status_code==200,r.text
    with app2.state.sessions.begin() as db:
        task=db.get(Task,ident);assert task.state=='BLOCKED' and task.payload['approval_revoked']
        calls=len(hub.calls);process_pull_task_once(db,task,registry);assert len(hub.calls)==calls
        with pytest.raises(HTTPException):retry_pull_task(db,actor(db),task,'不能继续旧检查点')
        cid=task.payload['connection_id'];sid=task.payload.get('schedule_id')
        if sid:
            schedule=db.get(IntegrationSchedule,sid)
            assert not schedule.active and schedule.last_cursor is None
            version=schedule.version
    if automatic:
        r=put(c,'/api/integration-schedules/'+sid,{'expected_version':version,'frequency_minutes':30,'auto_commit':True,'active':True,'reason':'核对源数据后恢复全量'})
        assert r.status_code==200,r.text
        with app2.state.sessions.begin() as db:
            ids=enqueue_due_schedules(db,registry=registry);assert len(ids)==1
            new_id=ids[0];task=db.get(Task,new_id)
            assert task.payload['mode']=='FULL' and task.payload['cursor'] is None
    else:
        with app2.state.sessions.begin() as db:new_id=create_pull_task(db,actor(db),db.get(Connection,cid),'training_project','FULL','重新全量核对').id
    for _ in range(2):process_and_confirm(app2,c,new_id,registry)
    with app2.state.sessions() as db:
        assert db.get(Task,new_id).state=='DONE'
        assert len(list(db.scalars(select(TrainingProjectMaster).where(TrainingProjectMaster.active.is_(True)))))==3
    # 旧撤销请求重放不能停掉新计划。
    assert rollback_page(c,app2,bid).status_code==200
    if automatic:
        with app2.state.sessions() as db:assert db.get(IntegrationSchedule,sid).active


@pytest.mark.parametrize('stage',['next_page','finalize'])
def test_legacy_void_page_blocks_execution_and_watermark(client2,app2,stage):
    c=client2;auth(c,'schooladmin');hub=SmallHub();registry,ident=prepare_run(app2,hub,True)
    process_and_confirm(app2,c,ident,registry)
    if stage=='finalize':process_and_confirm(app2,c,ident,registry)
    with app2.state.sessions.begin() as db:
        task=db.get(Task,ident);db.get(InboundBatch,task.result['chunks'][0]['batch_id']).state='VOID';db.flush()
        schedule=db.get(IntegrationSchedule,task.payload['schedule_id']);schedule.last_cursor='before-run'
        calls=len(hub.calls)
        if stage=='next_page':process_pull_task_once(db,task,registry)
        else:_finalize(db,task,actor(db),schedule)
        assert task.state=='BLOCKED' and task.payload['approval_revoked']
        assert not schedule.active and schedule.last_cursor is None and len(hub.calls)==calls


def test_rollback_does_not_disrupt_newer_run_or_active_lease(client2,app2):
    c=client2;auth(c,'schooladmin');hub=SmallHub();registry,ident=prepare_run(app2,hub,True)
    process_and_confirm(app2,c,ident,registry)
    with app2.state.sessions.begin() as db:
        task=db.get(Task,ident);bid=task.result['chunks'][0]['batch_id']
        task.lease_token='isolated-lease';task.lease_until=utcnow()+timedelta(minutes=1)
    r=rollback_page(c,app2,bid);assert r.status_code==409 and '当前页' in r.text,r.text
    with app2.state.sessions.begin() as db:
        task=db.get(Task,ident);task.lease_until=utcnow()-timedelta(seconds=1)
        create_pull_task(db,actor(db),db.get(Connection,task.payload['connection_id']),'training_project','FULL','后续采集')
    r=rollback_page(c,app2,bid);assert r.status_code==409 and '后续采集' in r.text,r.text
    with app2.state.sessions() as db:assert db.get(InboundBatch,bid).state=='COMMITTED'


@pytest.mark.parametrize('kind',['dictionary','claim'])
def test_cx_mapping_refreshes_values_already_loaded_in_session(app2,kind):
    key='dict:cx_login_alias' if kind=='dictionary' else 'cx_login_claims'
    before={'items':['login=J001']} if kind=='dictionary' else {'items':[{'login':'login','staff_no':'J001','state':'APPROVED'}]}
    after={'items':['login=J002']} if kind=='dictionary' else {'items':[{'login':'login','staff_no':'J001','state':'REVOKED'}]}
    with app2.state.sessions.begin() as db:db.add(Setting(key=key,value=before))
    with app2.state.sessions() as reader:
        cached=reader.get(Setting,key)
        assert cx_login_aliases(reader)=={'login':'J001'}
        with app2.state.sessions.begin() as writer:writer.get(Setting,key).value=after
        assert cx_login_aliases(reader)==({'login':'J002'} if kind=='dictionary' else {})
        assert cached.value==after
