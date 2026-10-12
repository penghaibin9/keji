"""Local procurement gaps: real permissions, search, todos and rule selection."""
from datetime import date
import pytest
from app.models import Notice,Qualification,Role,Audit,Org
from sqlalchemy import select
from conftest import auth,post
from test_api import rule,activate

@pytest.mark.parametrize('actor,ids',[('teacher',{'rec1'}),('depthead',{'rec1'}),('collegehead',{'rec1'}),('schooladmin',{'rec1','rec2'})])
def test_search_applies_four_role_scope(client2,actor,ids):
    auth(client2,actor)
    r=client2.get('/api/portal/search',params={'q':'合成'})
    assert r.status_code==200,r.text
    group=next(g for g in r.json()['groups'] if g['type']=='record')
    assert {x['id'] for x in group['items']}==ids

def test_search_permissions_and_literal_wildcards(client2,app2):
    with app2.state.sessions.begin() as db:
        role=db.get(Role,'role-teacher');role.permissions=['portal.read']
    auth(client2,'teacher')
    assert client2.get('/api/portal/search?q=合成').json()['groups']==[]
    auth(client2,'schooladmin')
    assert all(not g['items'] for g in client2.get('/api/portal/search?q=%25').json()['groups'])
    for query in ['', 'q=', 'q=x&q=y', 'q='+('a'*101),'q=x&teacher_id=otherteacher']:
        assert client2.get('/api/portal/search?'+query).status_code==422
    with app2.state.sessions() as db:
        assert db.scalar(select(Audit).where(Audit.object_id=='/api/portal/search'))

def test_notice_detail_and_search_recheck_visibility(client2,app2):
    with app2.state.sessions.begin() as db:
        for ident,org,published in [('n-parent','school',True),('n-other','dept2',True),('n-draft','school',False)]:
            db.add(Notice(id=ident,title='共同通知',body='隔离测试内容',category='业务通知',org_id=org,published=published,author_id='schooladmin'))
    auth(client2,'teacher')
    assert client2.get('/api/notices/n-parent').status_code==200
    notices=client2.get('/api/notices?q=共同').json()['items']
    assert [x['id'] for x in notices]==['n-parent']
    with app2.state.sessions() as db:assert notices[0]['org_name']==db.get(Org,'school').name
    for ident in ['n-other','n-draft','absent']:
        assert client2.get('/api/notices/'+ident).status_code==404
    group=next(g for g in client2.get('/api/portal/search?q=共同').json()['groups'] if g['type']=='notice')
    assert [x['id'] for x in group['items']]==['n-parent']
    with app2.state.sessions.begin() as db:db.get(Notice,'n-parent').published=False
    assert client2.get('/api/notices/n-parent').status_code==404

def test_todos_paginate_filter_and_do_not_include_sibling(client2,app2):
    with app2.state.sessions.begin() as db:
        for i in range(24):
            db.add(Qualification(id='todo-'+str(i),teacher_id='teacher',category='职业资格',name='演练材料'+str(i),certificate_no='local-'+str(i),issuer='合成',obtained=date(2026,1,1),state='DRAFT'))
        db.add(Qualification(id='hidden',teacher_id='otherteacher',category='职业资格',name='演练材料',certificate_no='hidden',issuer='合成',obtained=date(2026,1,1),state='DRAFT'))
    auth(client2,'teacher')
    first=client2.get('/api/todos?type=qualification&q=演练&page=1&size=20').json()
    second=client2.get('/api/todos?type=qualification&q=演练&page=2&size=20').json()
    assert first['total']==second['total']==24
    assert len(first['items'])==20 and len(second['items'])==4
    ids=[x['id'] for x in first['items']+second['items']]
    assert len(set(ids))==24 and 'hidden' not in ids
    assert client2.get('/api/todos?type=invalid').status_code==422
    assert client2.get('/api/todos?q='+('a'*101)).status_code==422

def test_point_item_selector_uses_active_rule_and_permission(client2):
    auth(client2,'schooladmin')
    assert client2.get('/api/points/calculation-items?period_id=period2026').json()['items']==[]
    r=rule(client2,'points');assert activate(client2,r).status_code==200
    d=client2.get('/api/points/calculation-items?period_id=period2026')
    assert d.status_code==200,d.text
    assert d.json()['items']==[{'key':'hours','label':'授课学时'}]
    assert client2.get('/api/points/calculation-items').status_code==422
    auth(client2,'teacher')
    assert client2.get('/api/points/calculation-items?period_id=period2026').status_code==403

def test_org_copy_allows_adjustment_without_mutating_source_or_reusing_trial(client2,app2):
    from copy import deepcopy
    from test_r3_org_assessment import make_rule
    from app.org_assessment import OrganizationAssessmentRule,OrganizationRuleTrial
    auth(client2,'schooladmin');source=make_rule(client2,'dept','dept1')
    config=deepcopy(source['config']);config['components'][0]['label']='新周期收入目标'
    config['components'][0]['target']='2000'
    payload={'expected_version':source['version'],'name':'调整后的复制规则','period_id':'period2026','config':config,'reason':'隔离测试新目标'}
    r=post(client2,'/api/organization-assessment-rules/'+source['id']+'/copy',payload)
    assert r.status_code==200,r.text
    copied=r.json();assert copied['config']==config and copied['state']=='DRAFT'
    with app2.state.sessions() as db:
        assert db.get(OrganizationAssessmentRule,source['id']).config==source['config']
        assert not db.scalar(select(OrganizationRuleTrial.id).where(OrganizationRuleTrial.rule_id==copied['id']))
    r=post(client2,'/api/organization-assessment-rules/'+copied['id']+'/actions',{'action':'activate','expected_version':copied['version'],'reason':'尚未试算不能启用'})
    assert r.status_code==409
    payload['config']['components'][0]['weight']='1'
    assert post(client2,'/api/organization-assessment-rules/'+source['id']+'/copy',payload).status_code==422
    auth(client2,'depthead');payload.pop('config')
    assert post(client2,'/api/organization-assessment-rules/'+source['id']+'/copy',payload).status_code==403

def test_point_detail_exposes_business_rule_name_without_changing_amount(client2):
    auth(client2,'schooladmin');r=rule(client2,'points');assert activate(client2,r).status_code==200
    result=post(client2,'/api/points/calculate',{'period_id':'period2026','teacher_ids':['teacher'],'reason':'隔离积分演练'})
    assert result.status_code==200,result.text
    rows=client2.get('/api/points?teacher_id=teacher').json()['items'];assert rows
    detail=client2.get('/api/points/'+rows[0]['id']).json()
    assert detail['rule_display_name']==r['name'] and detail['batch_created_at']
    assert detail['amount']==rows[0]['amount']
