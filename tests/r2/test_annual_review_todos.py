"""Completed duty checks leave the reviewer's todo queue and cannot be overwritten."""
from app.models import User,Setting
from support import HASH
from conftest import auth,post
from test_social_training import setup_social,policy,proof,action,detail,import_rows,row,close_project


def test_completed_annual_check_leaves_only_pending_duty_todos(setup_social,app2,client2):
    assert import_rows(client2,setup_social,[row()]).status_code==200
    close_project(client2,setup_social)
    pol=policy(client2,True,annual_model='four_indicators',bonus_pool='all_bonus_shared_ten',total_cap='110',grade_mode='four',step_mode='full_steps',satisfaction_inclusive=False,achievement_dedup='highest_per_reference',organization_basis='project_units')
    with app2.state.sessions.begin() as db:
        for ident in ('finance','academic'):
            db.add(User(id=ident,username=ident,name='合成'+ident,org_id='school',role_id='role-school',password_hash=HASH,must_change_password=False,active=True))
        duties=db.get(Setting,'social_training_duties');duties.value={**duties.value,'finance':['finance'],'academic':['academic']}
    auth(client2,'collegehead')
    r=post(client2,'/api/social/annuals',{'org_id':'college1','period_id':'period2026','policy_id':pol,'reason':'合成年核验','data':{'self_report':'合成年度自评','income_target':'10000','participants_target':30,'priority_target':30,'target_reference':'合成年度任务'}})
    assert r.status_code==200,r.text
    item=r.json()['item'];ident=item['id'];proof(client2,'social_annual',ident,item['version'])
    assert action(client2,'annuals','social_annual',ident,'submit').status_code==200
    assert ident not in {x['id'] for x in client2.get('/api/todos').json()['items'] if x['type']=='social_annual'}
    auth(client2,'finance')
    assert ident in {x['id'] for x in client2.get('/api/todos').json()['items']}
    assert action(client2,'annuals','social_annual',ident,'finance').status_code==200
    frozen=detail(client2,'social_annual',ident)['item']['snapshot']['checks']['finance']
    assert ident not in {x['id'] for x in client2.get('/api/todos').json()['items']}
    assert action(client2,'annuals','social_annual',ident,'finance').status_code==409
    assert detail(client2,'social_annual',ident)['item']['snapshot']['checks']['finance']==frozen
    auth(client2,'academic')
    assert ident in {x['id'] for x in client2.get('/api/todos').json()['items']}
    assert action(client2,'annuals','social_annual',ident,'academic').status_code==200
    assert ident not in {x['id'] for x in client2.get('/api/todos').json()['items']}
    auth(client2,'reviewer')
    assert ident in {x['id'] for x in client2.get('/api/todos').json()['items']}


def test_annual_owner_with_review_duties_has_no_self_review_todo(setup_social,client2):
    assert import_rows(client2,setup_social,[row()]).status_code==200
    close_project(client2,setup_social)
    pol=policy(client2,True,annual_model='four_indicators',bonus_pool='all_bonus_shared_ten',total_cap='110',grade_mode='four',step_mode='full_steps',satisfaction_inclusive=False,achievement_dedup='highest_per_reference',organization_basis='project_units')
    auth(client2,'reviewer')
    r=post(client2,'/api/social/annuals',{'org_id':'college1','period_id':'period2026','policy_id':pol,'reason':'兼核验职责人员申报','data':{'self_report':'隔离年度自评','income_target':'10000','participants_target':30,'priority_target':30,'target_reference':'合成年度任务'}})
    assert r.status_code==200,r.text
    item=r.json()['item'];ident=item['id']
    assert ident in {x['id'] for x in client2.get('/api/todos').json()['items']}
    proof(client2,'social_annual',ident,item['version'])
    assert action(client2,'annuals','social_annual',ident,'submit').status_code==200
    assert action(client2,'annuals','social_annual',ident,'finance').status_code==403
    assert ident not in {x['id'] for x in client2.get('/api/todos').json()['items']}
