"""Regression evidence for the cross-entry review; isolated synthetic data only."""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from sqlalchemy import select, event
from app.models import User, Period, Role, Org, Task
from app.core import Actor
from app import reference_data as rd
from app.services import require_complete_credits
from app.social_models import SocialPolicy, SocialClaim
from conftest import auth, post, put
from support import FIXTURE_PASSWORD
from test_social_training import setup_social
from test_codex_reference_rules import confirm


def test_resource_url_create_update_and_idempotent_replay(client2):
    auth(client2,'schooladmin')
    payload={'kind':'base','org_id':'college1','code':'URL-1','name':'网址资源','recognition':'合成依据',
             'resource_url':'https://example.org/resource?a=1','reason':'隔离保存回归'}
    response=post(client2,'/api/social/resources',payload,key='review-url-create-20261012')
    assert response.status_code==200,response.text
    assert post(client2,'/api/social/resources',payload,key='review-url-create-20261012').json()==response.json()
    item=response.json()['item']
    payload.update(expected_version=item['version'],resource_url='https://example.org/updated')
    response=put(client2,'/api/social/resources/'+item['id'],payload)
    assert response.status_code==200,response.text
    assert response.json()['item']['data']['resource_url']=='https://example.org/updated'


def test_credit_gate_only_blocks_selected_dependent_items():
    rule=SimpleNamespace(config={'components':[{'key':'c','source':'credits'},{'key':'h','source':'hours'}]})
    missing={'teaching_credits':{'courses':[{'course_code':'K1','counted':True,'credit':None}]}}
    require_complete_credits(rule,missing,['h'])
    with pytest.raises(HTTPException):require_complete_credits(rule,missing,['c'])
    with pytest.raises(HTTPException):require_complete_credits(rule,missing)
    require_complete_credits(rule,{'teaching_credits':{'courses':[{'counted':True,'credit':'0'}]}})


def test_unknown_term_cannot_silently_count_as_first_term(app2):
    assert rd.term_anchor('2025-2026',None) is None
    with app2.state.sessions.begin() as db:
        db.add(rd.TeacherHrProfile(staff_no='J001',user_id='teacher',name='合成教师',org_code='dept1'))
        confirm(db,'teacher_course',[{'staff_no':'J001','course_code':'UNK','course_name':'学期不明',
                                     'term_name':'2025-2026暑期','credit':'2','hours':'32'}])
        teacher=db.get(User,'teacher')
        total,evidence=rd.teaching_credit_facts(db,teacher,SimpleNamespace(start_date=date(2025,9,1),end_date=date(2026,8,31)))
        assert total==0 and len(evidence['excluded'])==1
        total,evidence=rd.teaching_credit_facts(db,teacher,SimpleNamespace(start_date=date(2022,9,1),end_date=date(2023,8,31)))
        assert total==0 and evidence['excluded']==[]


def test_archived_summary_and_home_use_closeout_year_and_frozen_title_rule(setup_social,client2,app2):
    with app2.state.sessions.begin() as db:
        period=db.get(Period,'period2026');period.start_date=date(2025,9,1);period.end_date=date(2026,8,31)
        policy=SocialPolicy(period_id=period.id,name='冻结规则',data={},created_by='schooladmin');db.add(policy);db.flush()
        db.add(SocialClaim(project_id=setup_social,teacher_id='teacher',period_id=period.id,policy_id=policy.id,
            state='ARCHIVED',data={},snapshot={'trial':{'teaching':'100','auxiliary':'100','basis':{
                'facts':{'project':{'closeout':{'closed_on':'2026-02-01'}}},
                'policy':{'data':{'title_scope':'teaching','title_precision':0,'title_rounding':'half_up'}}}}}))
    auth(client2,'teacher')
    summary=client2.get('/api/social/ledger-summary').json()['items'][0]['years']['2026']
    response=client2.get('/api/social/overview?year=2026');assert response.status_code==200,response.text
    points=response.json()['points']
    assert Decimal(points['year'])==200 and points['title_points']==summary['title_score']=='1'
    assert client2.get('/api/social/overview?year=2025').json()['points']['year']=='0'


def test_hr_unmapped_transfer_revokes_scope_until_full_admin_confirmation(client2,app2):
    auth(client2,'teacher');old=dict(client2.cookies)
    with app2.state.sessions.begin() as db:
        confirm(db,'teacher_hr',[{'staff_no':'J001','name':'测试教师一','title':'讲师','org_code':'college2','active':True}])
        user=db.get(User,'teacher');assert user.active and user.authorization_pending and user.org_id=='dept1'
        for who in ('depthead','collegehead'):
            manager=db.get(User,who);actor=Actor(db,manager,db.get(Role,manager.role_id),db.get(Org,manager.org_id))
            assert 'teacher' not in actor.teacher_ids
            assert db.scalar(select(User.id).where(User.id=='teacher',actor.scope(User.id))) is None
        confirm(db,'teacher_hr',[{'staff_no':'J001','name':'测试教师一','title':'讲师','org_code':'college2','active':True}])
        assert user.authorization_pending
    client2.cookies.clear();client2.cookies.update(old)
    assert client2.get('/api/auth/me').status_code==401
    client2.cookies.clear()
    assert client2.post('/api/auth/login',json={'username':'teacher','password':FIXTURE_PASSWORD}).status_code==403
    auth(client2,'depthead')
    assert client2.get('/api/reference/staff-roster/J001').status_code==404
    assert client2.get('/api/records/rec1').status_code==403
    auth(client2,'schooladmin')
    assert client2.get('/api/reference/staff-roster/J001').status_code==200
    with app2.state.sessions() as db:version=db.get(User,'teacher').version
    response=put(client2,'/api/users/teacher',{'name':'测试教师一','title':'讲师','org_id':'dept2','role_id':'role-teacher',
        'active':True,'is_admin':False,'expected_version':version,'reason':'核对人事调岗后重新授权'})
    assert response.status_code==200,response.text
    with app2.state.sessions() as db:assert not db.get(User,'teacher').authorization_pending
    auth(client2,'teacher');assert client2.get('/api/records').status_code==200


def test_reconcile_block_preserves_cursor_and_retry_does_not_pull_again(app2,monkeypatch):
    from app import paged_inbound as pages
    task=Task(id='review-task',kind='inbound_pull',owner_id='schooladmin',key='review-reconcile',state='PENDING',payload={'mode':'FULL','data_type':'teacher_course'},result={})
    schedule=SimpleNamespace(last_cursor='OLD',last_run_at=None,next_at=None,frequency_minutes=30,last_error='',version=1)
    pending={'batch_id':None,'rows':0,'received_total':0,'source_total':0,'has_more':False,'checkpoint':None,'next_cursor':'NEW'}
    with app2.state.sessions.begin() as db:
        monkeypatch.setattr(pages,'reconcile_full_pull',lambda *args:{'blocked':'缺失比例过高'})
        pages._advance(task,{},pending);pages._finalize(db,task,None,schedule)
        assert task.state=='BLOCKED' and schedule.last_cursor=='OLD' and schedule.last_run_at is None
        task.state='PENDING';task.attempts=0;task.version=1
        monkeypatch.setattr(pages,'reconcile_full_pull',lambda *args:{'deactivated':0})
        adapter=SimpleNamespace(pull_chunk=lambda **kw:pytest.fail('retry must not pull or commit pages again'))
        db.add(task);db.flush()
        pages.process_page(db,task,None,None,schedule,adapter,None)
        assert task.state=='DONE' and schedule.last_cursor=='NEW' and task.result['chunks']==[]


def test_mine_filters_units_in_sql(setup_social,client2,app2):
    statements=[]
    def capture(conn,cursor,statement,parameters,context,executemany):statements.append(statement)
    auth(client2,'teacher')
    event.listen(app2.state.engine,'before_cursor_execute',capture)
    try:
        response=client2.get('/api/social/mine?year=2026');assert response.status_code==200,response.text
    finally:event.remove(app2.state.engine,'before_cursor_execute',capture)
    units=[s for s in statements if 'FROM social_units' in s and 'social_units.data' in s]
    assert units and all('WHERE' in s for s in units)
    assert any('json_each' in s or 'json_contains' in s for s in units)


def test_hr_cannot_quarantine_last_recovery_admin(app2):
    with app2.state.sessions.begin() as db:
        user=db.get(User,'schooladmin');user.staff_no='RECOVERY';db.flush()
        confirm(db,'teacher_hr',[{'staff_no':'RECOVERY','name':'恢复管理员','org_code':'college1','active':True}])
        with pytest.raises(HTTPException,match='最后一位'):
            confirm(db,'teacher_hr',[{'staff_no':'RECOVERY','name':'恢复管理员','org_code':'college2','active':True}])
        db.refresh(user)
        assert user.active and not user.authorization_pending
        assert db.scalar(select(rd.TeacherHrProfile.org_code).where(rd.TeacherHrProfile.staff_no=='RECOVERY'))=='college1'


def test_unknown_resource_kind_denies_generic_entry(client2,app2):
    from app.social_models import SocialResource
    with app2.state.sessions.begin() as db:
        db.add(SocialResource(id='unknown-review-resource',kind='future_private',org_id='college1',code='UNK',name='未知私有资源',data={}))
    auth(client2,'teacher')
    for path in ['/api/social/objects/social_resource/unknown-review-resource',
                 '/api/social/objects/social_resource/unknown-review-resource/export',
                 '/api/attachments?object_type=social_resource&object_id=unknown-review-resource']:
        assert client2.get(path).status_code==403


@pytest.mark.parametrize('kind,org',[('teacher','dept1'),('dept','dept1'),('college','college1'),('school','school')])
@pytest.mark.parametrize('source',['training_income','course_participants'])
def test_staff_number_remains_valid_after_promotion(app2,kind,org,source):
    from app.models import TrainingRecord
    from app.core import serial
    with app2.state.sessions.begin() as db:
        user=db.get(User,'teacher');user.role_id='role-'+kind;user.org_id=org;db.flush()
        record=serial(db.get(TrainingRecord,'rec1'))
        fields={k:record[k] for k in ['event_date','project_code','project','course_code','course','class_code','class_name','hours','income','participants']}
        normalized,errors=rd.validate_inbound(source,{**fields,'staff_no':'J001','external_key':'PROMOTION-NEW'})
        assert errors==[]
        assert rd.validate_inbound_relations(db,source,normalized)==[]
        assert user.role_id=='role-'+kind


def test_password_reset_does_not_restore_pending_authorization(client2,app2):
    with app2.state.sessions.begin() as db:
        user=db.get(User,'teacher');user.authorization_pending=True;version=user.version
    auth(client2,'schooladmin')
    response=post(client2,'/api/users/teacher/reset-password',{'expected_version':version,'password':FIXTURE_PASSWORD,'reason':'隔离密码重置检查'})
    assert response.status_code==200,response.text
    with app2.state.sessions() as db:assert db.get(User,'teacher').authorization_pending


def test_upgrade_preflight_keeps_recovery_admin_available(app2,monkeypatch):
    import importlib.util
    from pathlib import Path
    path=Path(__file__).resolve().parents[2]/'backend/alembic/versions/20261012_0004_session_auth_method.py'
    spec=importlib.util.spec_from_file_location('review_auth_migration',path)
    migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
    with app2.state.sessions.begin() as db:
        user=db.get(User,'schooladmin');user.staff_no='RECOVERY'
        db.add(rd.TeacherHrProfile(staff_no='RECOVERY',user_id=user.id,name='恢复管理员',org_code='UNKNOWN'))
        db.add(Role(id='partial-school',code='partial-school',name='只读学校角色',kind='school',permissions=['portal.read']))
        db.flush()
        db.add(User(username='not-recovery',name='无完整权限',org_id='school',role_id='partial-school',is_admin=True,password_hash=user.password_hash))
        db.flush();monkeypatch.setattr(migration.op,'get_bind',lambda:db.connection())
        with pytest.raises(RuntimeError,match='备用管理员'):migration._existing_mismatches()
        db.refresh(user);assert not user.authorization_pending


def test_school_date_and_academic_year_ignore_host_timezone(monkeypatch):
    from datetime import datetime
    from app import core, social_training
    monkeypatch.setattr(core,'utcnow',lambda:datetime(2026,8,31,16,1))
    assert core.school_today()==social_training.today()==date(2026,9,1)
    assert rd.school_year_now()=='2026-2027'


def test_credit_problem_filter_bounds_course_batches_and_selected_year(client2,app2,monkeypatch):
    from app.routes import reference
    with app2.state.sessions.begin() as db:
        for i in range(65):
            for year in ('2025-2026','2024-2025'):
                db.add(rd.TeacherCourseTerm(external_key=f'BATCH-{i}-{year}',origin='JW',staff_no=f'P{i:03}',
                    teacher_name='合成教师',course_code='C1',course_name='缺失学分',term_name=year+'-1'))
    original=reference.annual_teaching_credits;loaded=[]
    def bounded(db,rows,**kwargs):
        rows=list(rows);loaded.append(len({r.staff_no for r in rows}))
        assert all(rd.school_year_of(r.term_name)=='2025-2026' for r in rows)
        return original(db,rows,**kwargs)
    monkeypatch.setattr(reference,'annual_teaching_credits',bounded)
    auth(client2,'schooladmin')
    response=client2.get('/api/reference/teacher-credits?problem=true&school_year=2025-2026&size=2')
    assert response.status_code==200,response.text
    assert response.json()['total']==65 and len(response.json()['items'])==2
    assert loaded==[64,1]


def test_teacher_resolution_rejects_unknown_roles_and_pending_authorization(app2):
    from app import social_training
    with app2.state.sessions.begin() as db:
        user=db.get(User,'teacher');role=db.get(Role,user.role_id)
        role.kind='unknown';db.flush()
        assert social_training.resolve_teacher(db,'college1','',user.id) is None
        role.kind='teacher';user.authorization_pending=True;db.flush()
        assert social_training.resolve_teacher(db,'college1','',user.id) is None
        user.authorization_pending=False;db.flush()
        assert social_training.resolve_teacher(db,'college1','',user.id).id==user.id

