"""Five procurement-scoped fixes; all data and accounts are isolated fixtures."""
from datetime import date
from decimal import Decimal
import pytest
from sqlalchemy import select
from conftest import auth,post,put
from test_social_training import setup_social,recognized,payload,row,proof,detail,action,import_rows,close_project,policy
from app import social_training as st
from app.models import Assessment,Period,Setting,PointEntry,Org
from app.social_models import SocialProject,SocialPolicy,SocialClaim,SocialUnit,SocialAnnual,SocialResource
from app.routes.ledgers import college_funding,quick_annual


def refile(client,pid,**values):
    auth(client,'schooladmin')
    response=action(client,'projects','social_project',pid,'refile');assert response.status_code==200,response.text
    data=payload();data['data'].update(values);data['expected_version']=detail(client,'social_project',pid)['item']['version']
    response=put(client,'/api/social/projects/'+pid,data);assert response.status_code==200,response.text
    return action(client,'projects','social_project',pid,'submit')


def file_project(client,pid):
    auth(client,'reviewer');response=action(client,'projects','social_project',pid,'file')
    assert response.status_code==200,response.text


def second_period(app,policy_id):
    with app.state.sessions.begin() as db:
        db.add(Period(id='overlap',name='重叠统计周期',start_date=date(2026,7,1),end_date=date(2026,12,31)))
        db.flush();source=db.get(SocialPolicy,policy_id)
        db.add(SocialPolicy(id='overlap-rule',period_id='overlap',name='同规则重叠周期',state='ACTIVE',data=dict(source.data),created_by='schooladmin'))


def claim_payload(pid,pol,period='period2026'):
    return {'project_id':pid,'period_id':period,'policy_id':pol,'recognition_form_reference':'学校制式认定表','reason':'本人申报隔离回归'}


def test_archived_project_cannot_be_recognized_in_another_period(recognized,client2,app2):
    ident,pol=recognized;second_period(app2,pol)
    with app2.state.sessions() as db:pid=db.get(SocialClaim,ident).project_id
    auth(client2,'teacher');r=post(client2,'/api/social/claims',claim_payload(pid,'overlap-rule','overlap'))
    assert r.status_code==409 and '同一项目' in r.text
    with app2.state.sessions() as db:
        assert len(list(db.scalars(select(SocialClaim))))==1
        assert sum(db.scalars(select(PointEntry.amount).where(PointEntry.kind=='SOCIAL')))==Decimal('1.56')


def test_two_drafts_only_one_can_submit_and_returned_draft_does_not_reserve(setup_social,client2,app2,monkeypatch):
    monkeypatch.setattr(st,'today',lambda:date(2026,9,3));pid=setup_social
    assert import_rows(client2,pid,[row()]).status_code==200;close_project(client2,pid);pol=policy(client2,True);second_period(app2,pol)
    auth(client2,'teacher');ids=[]
    for period,rule in [('period2026',pol),('overlap','overlap-rule')]:
        r=post(client2,'/api/social/claims',claim_payload(pid,rule,period));assert r.status_code==200,r.text
        item=r.json()['item'];ids.append(item['id']);proof(client2,'social_claim',item['id'],item['version'])
    assert action(client2,'claims','social_claim',ids[0],'submit').status_code==200
    overview=client2.get('/api/social/overview?year=2026').json()['points']
    assert Decimal(overview['trial'])==Decimal('1.56') and overview['trial_claims']==1
    rejected=action(client2,'claims','social_claim',ids[1],'submit')
    assert rejected.status_code==409 and '重复认定' in rejected.text
    auth(client2,'collegehead');assert action(client2,'claims','social_claim',ids[0],'return').status_code==200
    auth(client2,'teacher');r=action(client2,'claims','social_claim',ids[1],'submit');assert r.status_code==200,r.text
    assert action(client2,'claims','social_claim',ids[0],'submit').status_code==409


def test_legacy_pending_duplicate_is_rejected_at_archive(recognized,client2,app2):
    ident,pol=recognized;second_period(app2,pol)
    with app2.state.sessions.begin() as db:
        original=db.get(SocialClaim,ident)
        db.add(SocialClaim(id='legacy-duplicate',project_id=original.project_id,teacher_id=original.teacher_id,
            period_id='overlap',policy_id='overlap-rule',state='APPROVED',data=dict(original.data),snapshot=dict(original.snapshot)))
    auth(client2,'depthead');r=action(client2,'claims','social_claim','legacy-duplicate','approve')
    assert r.status_code==409
    with app2.state.sessions() as db:
        assert db.get(SocialClaim,'legacy-duplicate').state=='APPROVED'
        assert sum(db.scalars(select(PointEntry.amount).where(PointEntry.kind=='SOCIAL')))==Decimal('1.56')


@pytest.mark.parametrize('separate_batches',[False,True])
def test_person_day_same_learner_across_classes_is_atomic(setup_social,client2,separate_batches):
    pid=setup_social;assert refile(client2,pid,mode='person_day').status_code==200;file_project(client2,pid)
    first=row('day-a',2);first['mode']='person_day'
    second=row('day-b',2);second.update(mode='person_day',class_code='OTHER-CLASS')
    if separate_batches:assert import_rows(client2,pid,[first]).status_code==200
    response=import_rows(client2,pid,[second] if separate_batches else [first,second])
    assert response.status_code==409 and '同一学员同一天' in response.text
    facts=detail(client2,'social_project',pid)['facts']
    assert facts['effective']==(2 if separate_batches else 0)
    assert len(facts['units'])==(1 if separate_batches else 0)


def test_person_day_distinct_days_and_exclusions_keep_valid_counts(setup_social,client2):
    pid=setup_social;assert refile(client2,pid,mode='person_day').status_code==200;file_project(client2,pid)
    first=row('day-a',1);first['mode']='person_day';first['teachers'].append({'teacher_id':'EXT-1','staff_type':'external','role':'instructor'})
    second=row('day-b',1);second.update(mode='person_day',event_date='2026-09-02')
    excluded=row('excluded',1);excluded.update(mode='person_day',class_code='OTHER-CLASS');excluded['learners'][0]['passed']=False
    r=import_rows(client2,pid,[first,second,excluded]);assert r.status_code==200,r.text
    assert r.json()['effective']==2 and r.json()['excluded']==1


def test_legacy_person_day_duplicates_block_formal_claim(setup_social,client2,app2,monkeypatch):
    monkeypatch.setattr(st,'today',lambda:date(2026,9,3));pid=setup_social
    assert refile(client2,pid,mode='person_day').status_code==200;file_project(client2,pid)
    first=row('original',1);first['mode']='person_day';assert import_rows(client2,pid,[first]).status_code==200
    close_project(client2,pid);pol=policy(client2,True)
    with app2.state.sessions.begin() as db:
        duplicate={**first,'external_key':'old-import','class_code':'OTHER-CLASS'}
        db.add(SocialUnit(project_id=pid,external_key='old-import',data=duplicate))
    auth(client2,'teacher');r=post(client2,'/api/social/claims',claim_payload(pid,pol));assert r.status_code==200,r.text
    assert any('同一学员同一天' in s for s in r.json()['trial']['blockers'])
    item=r.json()['item'];proof(client2,'social_claim',item['id'],item['version'])
    assert action(client2,'claims','social_claim',item['id'],'submit').status_code==409


@pytest.mark.parametrize('category,level,basis,allowed',[
    ('enterprise','school','专项说明也不能降低到校级',False),('enterprise','city','',True),
    ('enterprise','province','',False),('enterprise','province','省级重点专项正式认定',True),
    ('community','province','',False),('community','school','',True),('rural','school','',True)])
def test_category_and_weight_checked_before_filing(setup_social,client2,category,level,basis,allowed):
    r=refile(client2,setup_social,category=category,level=level,level_basis=basis,scene='ordinary')
    assert r.status_code==(200 if allowed else 409),r.text


def test_enterprise_city_weight_computes_correctly_and_archives(setup_social,client2,monkeypatch):
    monkeypatch.setattr(st,'today',lambda:date(2026,9,3));pid=setup_social
    assert refile(client2,pid,category='enterprise',level='city',level_basis='',scene='ordinary').status_code==200;file_project(client2,pid)
    assert import_rows(client2,pid,[row()]).status_code==200;close_project(client2,pid);pol=policy(client2,True)
    auth(client2,'teacher');r=post(client2,'/api/social/claims',claim_payload(pid,pol));assert r.status_code==200,r.text
    assert r.json()['trial']['teaching']=='1.10' and not r.json()['trial']['blockers']
    item=r.json()['item'];proof(client2,'social_claim',item['id'],item['version']);assert action(client2,'claims','social_claim',item['id'],'submit').status_code==200
    for user in ('collegehead','reviewer','vice','depthead'):
        auth(client2,user);r=action(client2,'claims','social_claim',item['id'],'approve');assert r.status_code==200,r.text
    assert r.json()['item']['snapshot']['trial']['teaching']=='1.10'


def annual(client,**extra):
    pol=policy(client,True,annual_model='four_indicators',bonus_pool='all_bonus_shared_ten',total_cap=110,grade_mode='four',
        step_mode='full_steps',satisfaction_inclusive=False,achievement_dedup='highest_per_reference',organization_basis='project_units')
    auth(client,'collegehead')
    r=post(client,'/api/social/annuals',{'org_id':'college1','period_id':'period2026','policy_id':pol,'reason':'年度回归',
        'data':{'self_report':'单位自评','income_target':10000,'participants_target':30,'priority_target':30,'target_reference':'年度目标',**extra}})
    assert r.status_code==200,r.text
    return r.json()


def settlement(client,pid,pol,result=None,**extra):
    return post(client,'/api/social/projects/'+pid+'/notes',{'expected_version':detail(client,'social_project',pid)['item']['version'],
        'kind':'settlement','received_on':'2027-04-01','completed_on':'2027-04-03','policy_id':pol,'case_reference':'SETTLE-1',
        'settlement_result':result,'reason':'结算核验','basis':'财务正式核验文号',**extra})


@pytest.mark.parametrize('resolution,score',[('noncompliant',Decimal(5)),('exempt',Decimal(10))])
def test_late_settlement_pending_then_same_finance_result_in_both_views(recognized,client2,app2,monkeypatch,resolution,score):
    ident,pol=recognized;monkeypatch.setattr(st,'today',lambda:date(2027,4,5))
    with app2.state.sessions() as db:pid=db.get(SocialClaim,ident).project_id
    auth(client2,'reviewer');assert settlement(client2,pid,pol).status_code==200
    result=annual(client2,discipline_reference='文字依据不能代替财务认定');aid=result['item']['id']
    assert result['trial']['cost_base'] is None and result['trial']['total'] is None
    proof(client2,'social_annual',aid,result['item']['version']);assert action(client2,'annuals','social_annual',aid,'submit').status_code==409
    with app2.state.sessions() as db:
        f=college_funding(db,db.get(Org,'college1'),2026)
        q=quick_annual(Decimal(10000),Decimal(30),Decimal(30),{'income':10000,'participants':30,'priority':30},{'school':1},f)
        assert q['cost'] is None and q['total'] is None
    auth(client2,'reviewer');r=settlement(client2,pid,pol,resolution);assert r.status_code==200,r.text
    auth(client2,'collegehead');trial=detail(client2,'social_annual',aid)['trial']
    assert Decimal(trial['cost_base'])==score and not trial['blockers']
    with app2.state.sessions() as db:
        f=college_funding(db,db.get(Org,'college1'),2026)
        q=quick_annual(Decimal(10000),Decimal(30),Decimal(30),{'income':10000,'participants':30,'priority':30},{'school':1},f)
        assert Decimal(q['cost'])==score
        legacy=quick_annual(Decimal(10000),Decimal(30),Decimal(30),{'income':10000,'participants':30,'priority':30,'compliance_failures':1},{'school':1},f)
        assert legacy['cost'] is None and any('避免重复扣分' in s for s in legacy['missing'])
        value,errors=st.funding_cost(f,1,'other_only');assert value==max(Decimal(0),score-5) and not errors
    assert action(client2,'annuals','social_annual',aid,'submit').status_code==200


def test_financial_decision_requires_finance_and_cannot_be_erased_by_coordinator(recognized,client2,app2,monkeypatch):
    ident,pol=recognized;monkeypatch.setattr(st,'today',lambda:date(2027,4,5))
    with app2.state.sessions.begin() as db:
        pid=db.get(SocialClaim,ident).project_id;s=db.get(Setting,'social_training_duties')
        s.value={**s.value,'coordinator':['reviewer','vice'],'finance':['reviewer']}
    auth(client2,'vice');assert settlement(client2,pid,pol,'exempt').status_code==403
    auth(client2,'reviewer');assert settlement(client2,pid,pol,'exempt',basis='').status_code==422
    assert settlement(client2,pid,pol,'exempt').status_code==200
    auth(client2,'vice');assert settlement(client2,pid,pol).status_code==403
    # A new settlement date needs a fresh financial decision; it does not inherit the old exception.
    assert settlement(client2,pid,pol,case_reference='SETTLE-2',completed_on='2027-04-04').status_code==200
    with app2.state.sessions() as db:
        assert college_funding(db,db.get(Org,'college1'),2026)['blockers']


@pytest.mark.parametrize('kind',['claim','annual','correction','point_review'])
def test_period_close_checks_new_period_dependent_work(client2,app2,kind):
    with app2.state.sessions.begin() as db:
        for old in db.scalars(select(Assessment)):old.state='ARCHIVED'
        from app.reference_data import TrainingProjectMaster
        db.add(TrainingProjectMaster(id='close-master',code='CLOSE-M',name='周期样本'));db.flush()
        db.add(SocialProject(id='close-project',master_id='close-master',org_id='college1',owner_id='teacher',cohort='一期',data=payload()['data']))
        db.add(SocialPolicy(id='close-policy',period_id='period2026',name='周期样本规则',data={},created_by='schooladmin'));db.flush()
        if kind=='claim':obj=SocialClaim(project_id='close-project',teacher_id='teacher',period_id='period2026',policy_id='close-policy',data={},state='SUBMITTED')
        elif kind=='annual':obj=SocialAnnual(org_id='college1',period_id='period2026',policy_id='close-policy',owner_id='collegehead',data={},state='REVIEW')
        else:obj=SocialResource(org_id='college1',kind=kind,code='CLOSE-'+kind,name='待办',state='DRAFT',data={'period_id':'period2026'})
        db.add(obj);db.flush();ident=obj.id;model=type(obj)
    auth(client2,'schooladmin');r=post(client2,'/api/periods/period2026/close',{'expected_version':1,'reason':'关闭周期检查'})
    assert r.status_code==409 and '未办结社会培训事项' in r.text
    with app2.state.sessions.begin() as db:
        assert db.get(Period,'period2026').state=='OPEN'
        db.get(model,ident).state='CLOSED' if kind=='point_review' else 'ARCHIVED'
    r=post(client2,'/api/periods/period2026/close',{'expected_version':1,'reason':'事项全部完成后关闭'})
    assert r.status_code==200,r.text
