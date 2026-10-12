"""补齐的管理要求：收入分配比例、利益冲突回避、按在校生数建议目标、资金扣分与一票否决、教研室平均积分。"""
import uuid
from app.models import PointEntry
from conftest import auth, post
from test_social_training import setup_social, row, import_rows, action

CHECKED=['plan','filing_form','roster','attendance','hours','process','assessment','outcomes']


def closeout(**extra):
    return {'closed_on':'2026-09-02','outcome_report':'结项报告','satisfaction':'90','actual_income':'10000','funding_source':'other_training','finance_reference':'财务凭证','location':'onsite','implicit_cost':'0','settlement_on':'2026-09-03','materials_checked':CHECKED,**extra}


def put_json(client,path,payload):
    return client.put(path,json=payload,headers={'Idempotency-Key':str(uuid.uuid4())})


def test_income_distribution_follows_article_21(setup_social,client2):
    pid=setup_social;assert import_rows(client2,pid,[row()]).status_code==200
    bad=action(client2,'projects','social_project',pid,'close_submit',closeout=closeout(retained='1000',personnel='7000'))
    assert bad.status_code==422 and '学校留存不能低于收入的20%' in bad.text
    half=action(client2,'projects','social_project',pid,'close_submit',closeout=closeout(retained='2000'))
    assert half.status_code==422 and '同时填写' in half.text
    ok=action(client2,'projects','social_project',pid,'close_submit',closeout=closeout(location='offsite',retained='1000',personnel='7000'))
    assert ok.status_code==200,ok.text
    assert ok.json()['item']['closeout']['retained']=='1000' and ok.json()['item']['closeout']['personnel']=='7000'


def test_declared_conflict_blocks_review_until_withdrawn(setup_social,client2):
    pid=setup_social;assert import_rows(client2,pid,[row()]).status_code==200
    assert action(client2,'projects','social_project',pid,'close_submit',closeout=closeout(retained='2000',personnel='6000')).status_code==200
    auth(client2,'reviewer')
    options=client2.get('/api/social/conflicts').json();assert any(o['id']=='college1' for o in options['orgs'])
    assert post(client2,'/api/social/conflicts',{'target_kind':'org','target_id':'nowhere','reason':'亲属在该学院'}).status_code==422
    d=post(client2,'/api/social/conflicts',{'target_kind':'org','target_id':'college1','reason':'配偶在该学院任教'});assert d.status_code==200,d.text
    assert post(client2,'/api/social/conflicts',{'target_kind':'org','target_id':'college1','reason':'重复申报'}).status_code==409
    blocked=action(client2,'projects','social_project',pid,'close');assert blocked.status_code==403 and '利益冲突' in blocked.text
    auth(client2,'schooladmin');listing=client2.get('/api/social/conflicts').json();assert listing['all'] and listing['items'][0]['target_name']=='测试学院一'
    assert post(client2,f"/api/social/conflicts/{d.json()['id']}/withdraw",{'reason':'别人的申报不能撤'}).status_code==404
    auth(client2,'reviewer');assert post(client2,f"/api/social/conflicts/{d.json()['id']}/withdraw",{'reason':'已调离，不再存在冲突'}).status_code==200
    assert action(client2,'projects','social_project',pid,'close').status_code==200


def test_targets_suggest_from_students_and_apply_veto_and_failures(client2):
    auth(client2,'schooladmin')
    r=put_json(client2,'/api/social/targets',{'year':2026,'items':[{'org_id':'college1','students':'3000','income':'100','participants':'6000','priority':'1500','priority_actual':'1500','compliance_failures':1,'veto_reason':'纪检处分文件 2026-3 号'}],'reason':'下达目标'})
    assert r.status_code==200,r.text
    row=next(x for x in client2.get('/api/social/targets?year=2026').json()['items'] if x['org_id']=='college1')
    assert row['suggest']=={'participants':'6000','priority':'1500'}
    est=row['estimate'];assert est['cost']=='5' and '学校确认其他不合规 1 次' in est['cost_details'][0]
    assert est['veto']=='纪检处分文件 2026-3 号' and est['grade']=='不合格（一票否决）'


def test_department_average_points(client2,app2):
    with app2.state.sessions.begin() as db:
        db.add(PointEntry(teacher_id='teacher',period_id='period2026',item_key='social',kind='SOCIAL',amount=12,raw_value='12',formula='试',source_snapshot={},actor_id='schooladmin',reason='演示',basis='演示'))
    auth(client2,'schooladmin');r=client2.get('/api/social/departments?year=2026');assert r.status_code==200,r.text
    d=next(x for x in r.json()['items'] if x['org_id']=='dept1')
    assert d['total']=='12' and d['with_points']==1 and d['rank']==1 and d['average']==str(round(12/d['teachers'],2)).rstrip('0').rstrip('.')
