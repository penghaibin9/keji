"""10.1 / 9.1 extended scoring methods: tier, deduction/bonus, cap/floor; legacy unchanged."""
from decimal import Decimal
from types import SimpleNamespace
from sqlalchemy import select
from app.models import Rule,Assessment
from app.services import evaluate,evaluate_rule
from app.scoring_methods import score_component,normalize_method
from conftest import auth,post
from test_api import rule,activate,REASON
from test_r3_org_assessment import calculate,action


def make(client,kind,components):
    r=post(client,'/api/rules',{'kind':kind,'name':'扩展评分规则','period_id':'period2026','config':{'components':components},**REASON})
    return r


def test_legacy_rule_config_and_formula_unchanged(client2):
    auth(client2,'schooladmin');x=rule(client2,'assessment')
    assert x['config']=={'components':[{'key':'hours','label':'授课学时','source':'hours','factor':'2','weight':'100','target':'10','cap':None}]}
    t=post(client2,f"/api/rules/{x['id']}/trial",{'teacher_ids':['teacher']}).json()['items'][0]['detail'][0]
    assert t['formula']=='max(0, min(10.00 ÷ 10, 1)) × 100' and t['score']=='100.00' and 'method' not in t
    legacy=SimpleNamespace(id='r',kind='points',version_no=1,config={'components':[{'key':'a','label':'A','source':'hours','factor':'2','weight':'0','target':'1','cap':'15'}]})
    assert evaluate_rule(legacy,{'hours':Decimal('10')})==evaluate(legacy,{'hours':Decimal('10')})


def test_tier_assessment_rule_trial_calculation_and_explanation(client2,app2):
    auth(client2,'schooladmin')
    comps=[{'key':'hours','label':'授课学时分档','source':'hours','weight':'100','target':'1','method':'tier','tier_mode':'score',
            'tiers':[{'min':'0','value':'20'},{'min':'8','value':'60'},{'min':'20','value':'100'}]}]
    r=make(client2,'assessment',comps);assert r.status_code==200,r.text;x=r.json()
    stored=x['config']['components'][0]
    assert stored['method']=='tier' and stored['tiers'][1]=={'min':'8','value':'60'} and 'base' not in stored and 'floor' not in stored
    assert activate(client2,x).status_code==200
    r=post(client2,'/api/assessments/calculate',{'period_id':'period2026','teacher_ids':['teacher'],**REASON});assert r.status_code==200,r.text
    item=r.json()['items'][0];d=item['detail'][0]
    assert item['score']=='60.00' and d['score']=='60.00' and d['method']=='tier' and d['tier_hit']['index']==2
    assert '命中第 2 档' in d['formula'] and d['rule_version']==x['version_no'] and d['steps'][-1]=='本项得分 60.00'
    # Rule versioning: a new version is a new row; the old one keeps its config.
    with app2.state.sessions() as db:assert db.get(Rule,x['id']).config['components'][0]['tiers'][2]['value']=='100'


def test_deduct_bonus_cap_floor_points_rule(client2):
    auth(client2,'schooladmin')
    comps=[{'key':'late','label':'人次扣分','source':'participants','method':'deduct','base':'20','unit':'1','per_unit':'3','floor':'8'},
           {'key':'extra','label':'学时加分','source':'hours','method':'bonus','unit':'2','per_unit':'3','cap':'12'},
           {'key':'base','label':'学时','source':'hours','factor':'1'}]
    r=make(client2,'points',comps);assert r.status_code==200,r.text;x=r.json()
    assert x['config']['components'][2]=={'key':'base','label':'学时','source':'hours','factor':'1','weight':0,'target':1,'cap':None}  # legacy default serialization unchanged
    detail=post(client2,f"/api/rules/{x['id']}/trial",{'teacher_ids':['teacher']}).json()['items'][0]
    by={d['key']:d for d in detail['detail']}
    # participants=5 -> 20-5*3=5 -> floor 8
    assert by['late']['score']=='8.00' and by['late']['bounds']['applied']=='floor' and '低于保底 8' in by['late']['formula']
    # hours=10 -> floor(10/2)=5 -> 0+15 -> cap 12
    assert by['extra']['score']=='12.00' and by['extra']['bounds']['applied']=='cap'
    assert by['base']['formula']=='10.00 × 1' and detail['total']=='30.00'
    assert activate(client2,x).status_code==200
    r=post(client2,'/api/points/calculate',{'period_id':'period2026','teacher_ids':['teacher'],**REASON});assert r.status_code==200,r.text
    assert client2.get('/api/points?teacher_id=teacher').json()['sum']=='30.00'


def test_invalid_method_parameters_rejected(client2):
    auth(client2,'schooladmin')
    bad=[('assessment',[{'key':'a','label':'A','source':'hours','weight':'100','method':'tier','tiers':[{'min':'5','value':'1'},{'min':'5','value':'2'}]}]),
         ('assessment',[{'key':'a','label':'A','source':'hours','weight':'100','method':'tier','tiers':[{'min':'0','value':'120'}]}]),
         ('points',[{'key':'a','label':'A','source':'hours','method':'ratio'}]),
         ('points',[{'key':'a','label':'A','source':'hours','method':'linear','per_unit':'2'}]),
         ('points',[{'key':'a','label':'A','source':'hours','floor':'2'}]),
         ('points',[{'key':'a','label':'A','source':'hours','method':'deduct'}])]
    for kind,comps in bad:assert make(client2,kind,comps).status_code==422,comps


def test_score_component_steps_are_explicit():
    c={'method':'tier','tier_mode':'multiplier','weight':'40','tiers':[{'min':'0','value':'0.5'},{'min':'100','value':'1'}]}
    score,formula,exp=score_component(c,Decimal('50'),'assessment')
    assert score==Decimal('20.00') and exp['tier_hit']=={'index':1,'min':'0','value':'0.5','mode':'multiplier'} and '× 权重 40' in formula
    score,_,exp=score_component({'method':'ratio','weight':'30','target':'10','floor':'5'},Decimal('1'),'org')
    assert score==Decimal('5.00') and exp['bounds']['applied']=='floor'
    assert normalize_method({'method':'deduct','weight':'10','per_unit':'1'},'assessment')['base']=='10'


def test_org_extended_method_calculates_and_archives(client2,app2):
    auth(client2,'schooladmin')
    r=post(client2,'/api/organization-assessment-rules',{'target_kind':'dept','name':'分档组织规则','period_id':'period2026',
        'config':{'components':[{'key':'income','label':'收入分档','source':'income','weight':'100','target':'1','method':'tier',
                                 'tiers':[{'min':'0','value':'30'},{'min':'50','value':'70'},{'min':'500','value':'100'}]}]},**REASON})
    assert r.status_code==200,r.text;rule_obj=r.json();assert rule_obj['config']['components'][0]['tier_mode']=='score'
    t=post(client2,f"/api/organization-assessment-rules/{rule_obj['id']}/trial",{'target_ids':['dept1']});assert t.status_code==200
    assert t.json()['items'][0]['detail'][0]['score']=='70.00'
    assert post(client2,f"/api/organization-assessment-rules/{rule_obj['id']}/actions",{'expected_version':rule_obj['version'],'action':'activate',**REASON}).status_code==200
    obj=calculate(client2,'dept','dept1');assert obj['score']=='70.00' and obj['detail'][0]['tier_hit']['index']==2
    auth(client2,'depthead');obj=action(client2,obj,'review').json()
    auth(client2,'schooladmin');obj=action(client2,obj,'school_audit').json();r=action(client2,obj,'archive');assert r.status_code==200,r.text
    detail=client2.get('/api/organization-assessments/'+obj['id']).json();assert detail['immutable'] and detail['evidence'][0]['calculated_score']=='70.00'
    # legacy org cap without a method is refused instead of silently dropped
    r=post(client2,'/api/organization-assessment-rules',{'target_kind':'dept','name':'x','period_id':'period2026',
        'config':{'components':[{'key':'income','label':'收入','source':'income','weight':'100','target':'1','cap':'50'}]},**REASON})
    assert r.status_code==422
