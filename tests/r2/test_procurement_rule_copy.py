"""9.8/10.8 backend teacher-rule copy records its source; org-rule copy follows rules.manage."""
from copy import deepcopy
from sqlalchemy import select
from app.models import Audit,Role,User,Rule,RuleTrial
from app.permissions import SCHOOL
from conftest import auth,post
from support import HASH
from test_api import rule,activate,REASON
from test_r3_org_assessment import make_rule


def test_teacher_rule_copy_creates_draft_with_source_and_requires_trial(client2,app2):
    c=client2;auth(c,'schooladmin');source=rule(c,'assessment');r=activate(c,source);assert r.status_code==200;source=r.json()
    config=deepcopy(source['config']);config['components'][0]['label']='复制后调整'
    r=post(c,'/api/rules/'+source['id']+'/copy',{'expected_version':source['version'],'name':'复制的考核规则','period_id':'period2026','config':config,**REASON})
    assert r.status_code==200,r.text;copied=r.json()
    assert copied['state']=='DRAFT' and copied['copied_from']==source['id'] and copied['kind']=='assessment'
    assert copied['version_no']==source['version_no']+1 and copied['config']['components'][0]['label']=='复制后调整'
    listed=next(x for x in c.get('/api/rules').json()['items'] if x['id']==copied['id']);assert listed['copied_from']==source['id']
    with app2.state.sessions() as db:
        a=db.scalar(select(Audit).where(Audit.module=='rules',Audit.object_id==copied['id'],Audit.action=='复制为新的教师规则草稿'))
        assert a.after['source_rule_id']==source['id'] and a.reason==REASON['reason']
        assert db.get(Rule,source['id']).state=='ACTIVE' and db.get(Rule,source['id']).config==source['config']
        assert not db.scalar(select(RuleTrial.id).where(RuleTrial.rule_id==copied['id']))
    r=post(c,f"/api/rules/{copied['id']}/actions",{'expected_version':copied['version'],'action':'activate',**REASON});assert r.status_code==409
    # Default copy keeps the source config; stale version and invalid weight are refused.
    r=post(c,'/api/rules/'+source['id']+'/copy',{'expected_version':source['version'],'name':'原样复制','period_id':'period2026',**REASON})
    assert r.status_code==200 and r.json()['config']==source['config']
    assert post(c,'/api/rules/'+source['id']+'/copy',{'expected_version':source['version']+9,'name':'x','period_id':'period2026',**REASON}).status_code==409
    pts=rule(c,'points');bad=deepcopy(pts['config']);bad['components'][0]['source']='points'
    assert post(c,'/api/rules/'+pts['id']+'/copy',{'expected_version':pts['version'],'name':'循环','period_id':'period2026','config':bad,**REASON}).status_code==422
    auth(c,'depthead')
    assert post(c,'/api/rules/'+source['id']+'/copy',{'expected_version':source['version'],'name':'越权','period_id':'period2026',**REASON}).status_code==403


def test_org_rule_copy_allowed_for_non_admin_rules_manager(client2,app2):
    c=client2;auth(c,'schooladmin');source=make_rule(c,'dept','dept1')
    with app2.state.sessions.begin() as db:
        db.add(Role(id='role-rule-manager',code='rule-manager',name='规则管理员',kind='school',permissions=sorted(SCHOOL-{'users.manage','roles.manage'})))
        db.flush()
        db.add(User(id='rulemgr',username='rulemgr',name='规则管理员',org_id='school',role_id='role-rule-manager',password_hash=HASH,is_admin=False,must_change_password=False))
    auth(c,'rulemgr')
    r=post(c,'/api/organization-assessment-rules/'+source['id']+'/copy',{'expected_version':source['version'],'name':'非管理员复制','period_id':'period2026',**REASON})
    assert r.status_code==200,r.text
    assert r.json()['copied_from']==source['id']
    from pathlib import Path
    js=(Path(__file__).resolve().parents[2]/'frontend/app.js').read_text(encoding='utf-8')
    assert "'/rules/'+x.id+'/copy'" in js and "can('rules.manage')?link('复制新版本'" in js
