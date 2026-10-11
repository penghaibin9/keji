"""Procurement audit counterexamples, using only isolated fixtures and normal APIs."""
import pytest
from app.schemas import RecordIn
from conftest import auth, post, put
from test_api import make_assessment, rule, activate, REASON
from test_r3_org_assessment import make_rule, calculate, action

def changed_record(c, ident='rec1', **changes):
    row=c.get('/api/records/'+ident).json()['record']
    payload={k:row[k] for k in RecordIn.model_fields if k in row}
    return put(c,'/api/records/'+ident,{**payload,**REASON,'expected_version':row['version'],**changes})

def confirm(c,x,kind='assessments',action='confirm'):
    return post(c,f'/api/{kind}/{x["id"]}/actions',{'action':action,'expected_version':x['version'],**REASON})

@pytest.mark.parametrize('stage',['TEACHER','READY'])
def test_changed_hours_block_forward_workflow_and_recalc_recovers(client2,stage):
    c=client2;x=make_assessment(c)
    if stage=='READY':
        for actor in ['teacher','depthead','collegehead','schooladmin']:
            auth(c,actor);r=confirm(c,x);assert r.status_code==200,r.text;x=r.json()
    auth(c,'schooladmin');assert changed_record(c,hours='2').status_code==200
    auth(c,'teacher' if stage=='TEACHER' else 'schooladmin')
    detail=c.get('/api/assessments/'+x['id']).json()
    assert detail['source_changes']['changed']
    assert detail['source_changes']['items'][0]['before']=='10.00'
    assert detail['source_changes']['items'][0]['after']=='2.00'
    blocked=confirm(c,x,action='confirm' if stage=='TEACHER' else 'archive')
    assert blocked.status_code==409 and '依据' in blocked.text
    auth(c,'schooladmin')
    if stage=='READY':
        r=confirm(c,x,action='return');assert r.status_code==200;r=r.json()
    r=post(c,'/api/assessments/calculate',{'period_id':'period2026','teacher_ids':['teacher'],**REASON})
    assert r.status_code==200,r.text;x=r.json()['items'][0];assert x['score']=='20.00'
    auth(c,'teacher');assert confirm(c,x).status_code==200

def test_irrelevant_change_does_not_block_and_archive_stays_frozen(client2):
    c=client2;x=make_assessment(c)
    assert changed_record(c,income='900').status_code==200
    assert changed_record(c,'rec2',hours='2',course_code='C2').status_code==200
    for actor in ['teacher','depthead','collegehead','schooladmin']:
        auth(c,actor);r=confirm(c,x);assert r.status_code==200,r.text;x=r.json()
    r=confirm(c,x,action='archive');assert r.status_code==200,r.text
    archived=r.json();assert changed_record(c,hours='1').status_code==200
    detail=c.get('/api/assessments/'+x['id']).json()
    assert detail['assessment']['score']=='100.00'
    assert detail['assessment']['archive_sha256']==archived['archive_sha256']
    assert not detail['source_changes']['changed']

def test_record_dispute_matches_period_and_original_dependencies(client2):
    c=client2;x=make_assessment(c)
    row=c.get('/api/records/rec1').json()['record']
    payload={k:row[k] for k in RecordIn.model_fields if k in row}
    past=post(c,'/api/records',{**payload,**REASON,'external_key':'past-record','event_date':'2025-09-01'}).json()
    auth(c,'teacher')
    assert post(c,'/api/disputes',{'object_type':'record','object_id':past['id'],**REASON}).status_code==200
    assert c.get('/api/assessments/'+x['id']).json()['confirmation_blockers']['count']==0
    assert post(c,'/api/disputes',{'object_type':'record','object_id':'rec1',**REASON}).status_code==200
    assert confirm(c,x).status_code==409
    auth(c,'schooladmin');assert changed_record(c,event_date='2025-09-01').status_code==200
    assert c.get('/api/assessments/'+x['id']).json()['confirmation_blockers']['count']==1

def test_manual_cannot_claim_import_or_interface_origin(client2):
    c=client2;auth(c,'schooladmin');row=c.get('/api/records/rec1').json()['record']
    payload={k:row[k] for k in RecordIn.model_fields if k in row}
    for source in ['学校数据中台','Excel导入','表格导入']:
        r=post(c,'/api/records',{**payload,**REASON,'external_key':'source-'+str(len(source)),'source':source})
        assert r.status_code==422,r.text
        assert changed_record(c,source=source).status_code==422
    assert changed_record(c,hours='8').status_code==200

def test_spreadsheet_cannot_impersonate_interface_and_keeps_batch(client2):
    from test_r3_excel import fill_template,upload_preview
    c=client2;auth(c,'schooladmin')
    data=fill_template(c,'records',['ORIGIN-TEST','J001','2026-09-10','PX','项目X','CX','课程X','CLX','班级X',2,1,50,'学校数据中台'])
    response=upload_preview(c,'records',data);assert response.status_code==200,response.text
    job=response.json();assert job['errors']==0
    r=post(c,f'/api/imports/{job["id"]}/confirm',{'expected_version':job['version'],**REASON});assert r.status_code==200,r.text
    row=c.get('/api/records',params={'q':'ORIGIN-TEST'}).json()['items'][0]
    assert row['source']=='Excel导入' and row['batch_id']==job['id']
    assert changed_record(c,row['id'],income='40').status_code==200
    row=c.get('/api/records/'+row['id']).json()['record']
    assert row['source']=='Excel导入' and row['batch_id']==job['id']

def test_participation_manual_origin_and_class_filter(client2,app2):
    from app.reference_data import TrainingClassMaster
    c=client2;auth(c,'schooladmin');row=c.get('/api/records/rec1').json()['record']
    payload={k:row[k] for k in RecordIn.model_fields if k in row and k not in {'participants','income'}}
    r=post(c,'/api/participations',{**payload,**REASON,'external_key':'participation-source','source':'学校数据中台'})
    assert r.status_code==422
    with app2.state.sessions.begin() as db:
        db.add(TrainingClassMaster(code='CLASS1',name='正确班级',project_code='P1',course_code='C1'))
        db.add(TrainingClassMaster(code='CLASS2',name='其他班级',project_code='P2',course_code='C2'))
    rows=c.get('/api/reference/classes',params={'project_code':'P1','course_code':'C1'}).json()['items']
    assert [r['code'] for r in rows]==['CLASS1']

def test_teacher_keyword_search_stays_scoped(client2):
    c=client2;auth(c,'schooladmin')
    assert c.get('/api/records',params={'q':'测试教师一'}).json()['total']==1
    assert c.get('/api/statistics',params={'q':'J001'}).json()['income']=='100.00'
    auth(c,'teacher')
    assert c.get('/api/records',params={'q':'J002'}).json()['total']==0

def test_points_confirm_checks_source_and_zero_delta_recalc_refreshes_evidence(client2):
    c=client2;auth(c,'schooladmin');r=rule(c,'points');assert activate(c,r).status_code==200
    payload={'period_id':'period2026','teacher_ids':['teacher'],**REASON}
    assert post(c,'/api/points/calculate',payload).status_code==200
    assert changed_record(c,hours='2').status_code==200
    auth(c,'teacher');balance=c.get('/api/point-balances').json()['items'][0]
    assert confirm(c,balance,'point-balances').status_code==409
    auth(c,'schooladmin');assert post(c,'/api/points/calculate',payload).status_code==200
    assert changed_record(c,event_date='2026-09-02').status_code==200
    refresh=post(c,'/api/points/calculate',payload);assert refresh.status_code==200,refresh.text
    assert refresh.json()['items'][0]['entries'][0]['amount']=='0.00'
    auth(c,'teacher');balance=c.get('/api/point-balances').json()['items'][0]
    assert confirm(c,balance,'point-balances').status_code==200

def test_organization_checks_actual_record_basis_even_when_total_unchanged(client2):
    c=client2;auth(c,'schooladmin');make_rule(c,'dept','dept1');x=calculate(c,'dept','dept1')
    row=c.get('/api/records/rec1').json()['record'];payload={k:row[k] for k in RecordIn.model_fields if k in row}
    assert changed_record(c,income='90').status_code==200
    assert post(c,'/api/records',{**payload,**REASON,'external_key':'offset','income':'10'}).status_code==200
    auth(c,'depthead');assert action(c,x,'review').status_code==409
    assert c.get('/api/organization-assessments/'+x['id']).json()['source_changes']['changed']
    auth(c,'schooladmin');x=calculate(c,'dept','dept1')
    auth(c,'depthead');r=action(c,x,'review');assert r.status_code==200,r.text


def test_organization_calculation_rejects_stale_upstream_points(client2):
    c=client2;auth(c,'schooladmin');r=rule(c,'points');assert activate(c,r).status_code==200
    payload={'period_id':'period2026','teacher_ids':['teacher'],**REASON}
    assert post(c,'/api/points/calculate',payload).status_code==200
    r=post(c,'/api/organization-assessment-rules',{'target_kind':'dept','name':'积分组织考核','period_id':'period2026',
        'config':{'components':[{'key':'points','label':'教师积分','source':'points','weight':'100','target':'10'}]},**REASON})
    assert r.status_code==200,r.text;org_rule=r.json()
    assert post(c,f'/api/organization-assessment-rules/{org_rule["id"]}/trial',{'target_ids':['dept1']}).status_code==200
    assert confirm(c,org_rule,'organization-assessment-rules','activate').status_code==200
    assert changed_record(c,hours='2').status_code==200
    request={'period_id':'period2026','target_kind':'dept','target_ids':['dept1'],**REASON}
    blocked=post(c,'/api/organization-assessments/calculate',request)
    assert blocked.status_code==409 and '依据' in blocked.text
    assert post(c,'/api/points/calculate',payload).status_code==200
    assert post(c,'/api/organization-assessments/calculate',request).status_code==200


def test_print_brand_is_current_before_archive_and_frozen_afterwards(client2):
    c=client2;x=make_assessment(c);auth(c,'schooladmin')
    setting=next(s for s in c.get('/api/settings').json()['items'] if s['key']=='branding')
    r=put(c,'/api/settings/branding',{'value':{'school_name':'正式配置学校'},'expected_version':setting['version'],**REASON})
    assert r.status_code==200;version=r.json()['version']
    assert c.get('/api/assessments/'+x['id']+'/print').json()['school_name']=='正式配置学校'
    for actor in ['teacher','depthead','collegehead','schooladmin']:
        auth(c,actor);r=confirm(c,x);assert r.status_code==200,r.text;x=r.json()
    assert confirm(c,x,action='archive').status_code==200
    assert put(c,'/api/settings/branding',{'value':{'school_name':'调整后的学校'},'expected_version':version,**REASON}).status_code==200
    assert c.get('/api/assessments/'+x['id']+'/print').json()['school_name']=='正式配置学校'
