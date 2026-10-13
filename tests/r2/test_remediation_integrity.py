"""整改报告的数据保护回归；只使用隔离数据库。"""
from sqlalchemy import select
from app.models import Setting, User
from app.social_models import SocialResource
from conftest import auth, post, put
from datetime import date
from types import SimpleNamespace
import pytest
from app import social_training as st
from app.models import Period
from app.social_models import SocialClaim, SocialPolicy, SocialProject
from test_social_training import setup_social, action, detail, proof, payload, row, import_rows


def policy_draft(client):
    auth(client,'schooladmin')
    response=post(client,'/api/social/policies',{'name':'隔离口径','period_id':'period2026','data':{},'reason':'隔离回归'})
    assert response.status_code==200,response.text
    return response.json()['item']['id']


def test_annual_collects_all_resources_and_edit_preserves_achievements(client2,app2):
    policy=policy_draft(client2)
    with app2.state.sessions.begin() as db:
        for i in range(205):
            db.add(SocialResource(org_id='college1',kind='achievement',code=f'REMEDY-{i:03}',name='隔离成果',
                data={'level':'school','confirmed_on':'2026-09-01','recognition':'学校隔离依据'}))
        db.add(SocialResource(org_id='college1',kind='achievement',code='OTHER-YEAR',name='往年成果',
            data={'level':'national','confirmed_on':'2025-09-01','recognition':'往年依据'}))
    body={'org_id':'college1','period_id':'period2026','policy_id':policy,'reason':'隔离回归','data':{'self_report':'隔离年度自评'}}
    response=post(client2,'/api/social/annuals',body);assert response.status_code==200,response.text
    item=response.json()['item'];original=item['data']['achievements']
    assert len(original)==205 and 'REMEDY-204' in {x['reference'] for x in original}
    body['expected_version']=item['version'];body['data']['self_report']='只修改说明，保留全部成果'
    response=put(client2,'/api/social/annuals/'+item['id'],body)
    assert response.status_code==200,response.text
    assert response.json()['item']['data']['achievements']==original


def test_duty_assignment_accepts_active_extra_identity_but_not_expired(client2,app2):
    auth(client2,'schooladmin')
    with app2.state.sessions.begin() as db:
        db.add(Setting(key='account_identities',value={'items':[{'id':'extra-dean','user_id':'teacher','role_id':'role-college','org_id':'college1'}]}))
    r=client2.get('/api/social/duties');assert r.status_code==200
    payload={'expected_version':r.json()['version'],'assignments':{'dean':['teacher']},'reason':'核对兼任职责'}
    r=put(client2,'/api/social/duties',payload);assert r.status_code==200,r.text
    options=client2.get('/api/social/duty-options',params={'duty':'dean','q':'teacher'}).json()
    assert next(x for x in options['items'] if x['id']=='teacher')['eligible']
    with app2.state.sessions.begin() as db:
        setting=db.get(Setting,'account_identities');setting.value={'items':[{**setting.value['items'][0],'valid_until':'2000-01-01'}]}
    payload['expected_version']=r.json()['version']
    assert put(client2,'/api/social/duties',payload).status_code==422


def test_duties_return_selected_people_independently_of_user_page(client2,app2):
    auth(client2,'schooladmin')
    with app2.state.sessions.begin() as db:
        db.add(Setting(key='social_training_duties',value={'dean':['collegehead']}))
        for i in range(205):
            db.add(User(id=f'early-{i}',username=f'000-{i:03}',name='隔离普通账号',org_id='dept1',role_id='role-teacher',password_hash='unused',active=True,must_change_password=False))
    first=client2.get('/api/users?size=200').json()
    assert 'collegehead' not in {x['id'] for x in first['items']}
    response=client2.get('/api/social/duties');assert response.status_code==200,response.text
    assert response.json()['assignments']['dean']==['collegehead']
    assert next(x for x in response.json()['people'] if x['id']=='collegehead')['name']
    auth(client2,'teacher')
    assert client2.get('/api/social/duty-options',params={'duty':'dean'}).status_code==403


def test_policy_draft_can_be_completed_but_closed_period_blocks_changes(client2,app2):
    ident=policy_draft(client2);item=detail(client2,'social_policy',ident)['item']
    body={'expected_version':item['version'],'name':'补齐后的口径','period_id':'period2026','reason':'补齐已确认内容','data':{'title_precision':0,'calendar_start':'2026-01-01'}}
    r=put(client2,'/api/social/policies/'+ident,body);assert r.status_code==200,r.text
    assert r.json()['item']['data']['title_precision']==0
    assert put(client2,'/api/social/policies/'+ident,body).status_code==409
    with app2.state.sessions.begin() as db:db.get(Period,'period2026').state='CLOSED'
    body['expected_version']=r.json()['item']['version']
    assert put(client2,'/api/social/policies/'+ident,body).status_code==409
    assert action(client2,'policies','social_policy',ident,'activate').status_code==409
    assert action(client2,'policies','social_policy',ident,'record_basis').status_code==409


def test_wrong_period_is_rejected_and_old_draft_can_move_to_correct_period(setup_social,client2,app2):
    pid=setup_social;assert import_rows(client2,pid,[row()]).status_code==200;correct=policy_draft(client2)
    with app2.state.sessions.begin() as db:
        db.add(Period(id='next-year',name='下一年',start_date=date(2027,1,1),end_date=date(2027,12,31)));db.flush()
        db.add(SocialPolicy(id='next-policy',period_id='next-year',name='下一年口径',data={},created_by='schooladmin'))
        project=db.get(SocialProject,pid);project.state='CLOSED';project.closeout={'closed_on':'2026-09-02'}
    auth(client2,'teacher')
    body={'project_id':pid,'period_id':'next-year','policy_id':'next-policy','recognition_form_reference':'隔离依据','reason':'周期纠错验证'}
    assert post(client2,'/api/social/claims',body).status_code==422
    with app2.state.sessions.begin() as db:
        db.add(SocialClaim(id='legacy-wrong-period',project_id=pid,teacher_id='teacher',period_id='next-year',policy_id='next-policy',data={'auxiliary':[],'recognition_form_reference':'原材料说明'}))
    r=put(client2,'/api/social/claims/legacy-wrong-period',{**body,'period_id':'period2026','policy_id':correct,'expected_version':1})
    assert r.status_code==200,r.text
    assert r.json()['item']['period_id']=='period2026'


def test_draft_policy_switch_unblocks_replacement_without_overwriting_old_policy(setup_social,client2,app2):
    old=policy_draft(client2);new=policy_draft(client2)
    with app2.state.sessions.begin() as db:
        policy=db.get(SocialPolicy,old);policy.state='ACTIVE';policy.data={'calendar_end':'2026-12-31'}
        newer=db.get(SocialPolicy,new);newer.data={'calendar_start':'2026-01-01','calendar_end':'2027-12-31','calendar_reference':'新校历','interpretation_reference':'学校已确认'}
        db.add(SocialClaim(id='move-policy',project_id=setup_social,teacher_id='teacher',period_id='period2026',policy_id=old,data={'auxiliary':[],'recognition_form_reference':'原申报依据'}))
    auth(client2,'reviewer');assert action(client2,'policies','social_policy',old,'deactivate').status_code==409
    auth(client2,'teacher')
    r=put(client2,'/api/social/claims/move-policy',{'expected_version':1,'project_id':setup_social,'period_id':'period2026','policy_id':new,'recognition_form_reference':'原申报依据','reason':'切换待启用的新口径'})
    assert r.status_code==200,r.text
    auth(client2,'reviewer');assert action(client2,'policies','social_policy',old,'deactivate').status_code==200
    auth(client2,'schooladmin');proof(client2,'social_policy',new,detail(client2,'social_policy',new)['item']['version'])
    auth(client2,'reviewer');r=action(client2,'policies','social_policy',new,'activate');assert r.status_code==200,r.text
    with app2.state.sessions() as db:
        assert db.get(SocialPolicy,old).data['calendar_end']=='2026-12-31'
        assert db.get(SocialClaim,'move-policy').policy_id==new


def test_refile_cannot_leave_training_units_outside_new_dates(setup_social,client2):
    assert import_rows(client2,setup_social,[row()]).status_code==200
    assert action(client2,'projects','social_project',setup_social,'refile').status_code==200
    item=detail(client2,'social_project',setup_social)['item'];body=payload()
    body['expected_version']=item['version'];body['data']['start_date']='2026-09-02';body['data']['end_date']='2026-09-03'
    r=put(client2,'/api/social/projects/'+setup_social,body)
    assert r.status_code==409 and 'unit1' in r.text
    assert detail(client2,'social_project',setup_social)['item']['data']['start_date']=='2026-09-01'


@pytest.mark.parametrize('reference',['系统推荐口径（待学校书面确认）','  系统推荐口径（待学校书面确认）  '])
def test_system_recommendation_text_is_not_school_written_confirmation(setup_social,client2,reference):
    ident=policy_draft(client2);item=detail(client2,'social_policy',ident)['item']
    response=put(client2,'/api/social/policies/'+ident,{'expected_version':item['version'],'period_id':'period2026','name':'学校确认待补','reason':'隔离推荐边界',
        'data':{'interpretation_reference':reference,'calendar_start':'2026-01-01','calendar_end':'2027-12-31','calendar_reference':'隔离校历'}})
    assert response.status_code==200,response.text
    proof(client2,'social_policy',ident,response.json()['item']['version'])
    auth(client2,'reviewer');response=action(client2,'policies','social_policy',ident,'activate')
    assert response.status_code==409 and '系统推荐说明不能代替学校确认' in response.text


def test_void_policy_cannot_be_used_for_new_or_edited_work(setup_social,client2,app2):
    ident=policy_draft(client2)
    annual={'org_id':'college1','period_id':'period2026','policy_id':ident,'reason':'隔离停用规则验证','data':{'self_report':'保留自评内容'}}
    response=post(client2,'/api/social/annuals',annual);assert response.status_code==200,response.text
    item=response.json()['item']
    with app2.state.sessions.begin() as db:db.get(SocialPolicy,ident).state='VOID'
    assert post(client2,'/api/social/annuals',annual).status_code==422
    assert put(client2,'/api/social/annuals/'+item['id'],{**annual,'expected_version':item['version']}).status_code==422
    auth(client2,'teacher')
    assert post(client2,'/api/social/claims',{'project_id':setup_social,'period_id':'period2026','policy_id':ident,'reason':'隔离停用规则验证'}).status_code==422
    auth(client2,'schooladmin')
    assert detail(client2,'social_annual',item['id'])['item']['version']==item['version']


def test_review_readiness_uses_active_extra_identity(setup_social,app2):
    with app2.state.sessions.begin() as db:
        user=db.get(User,'collegehead');user.role_id='role-teacher';user.org_id='dept1'
        extra={'id':'extra-dean','user_id':'collegehead','role_id':'role-college','org_id':'college1'}
        setting=Setting(key='account_identities',value={'items':[extra]});db.add(setting)
        policy=SocialPolicy(period_id='period2026',name='兼任核验口径',data={},created_by='schooladmin');db.add(policy);db.flush()
        db.add(SocialClaim(id='extra-ready-claim',project_id=setup_social,teacher_id='teacher',period_id='period2026',policy_id=policy.id,data={}))
        db.flush()
        review=SimpleNamespace(org_id='college1',data={'claim_id':'extra-ready-claim','teacher_id':'teacher','created_by':'teacher'})
        assert not any(st.DUTIES['dean'] in value for value in st.review_staff_blockers(db,review))
        setting.value={'items':[{**extra,'valid_until':'2000-01-01'}]};db.flush()
        assert any(st.DUTIES['dean'] in value for value in st.review_staff_blockers(db,review))
