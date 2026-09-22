from sqlalchemy.orm import Session
from app.models import User
from app.passwords import hash_password
from app.org_assessment import OrganizationAssessment,OrganizationAssessmentMetricEvidence
from conftest import auth,post
from support import FIXTURE_PASSWORD


def ensure_school_reviewer(app2):
    with Session(app2.state.engine) as db:
        if not db.get(User,'schoolreviewer'):
            db.add(User(id='schoolreviewer',username='schoolreviewer',name='学校复核员',staff_no=None,org_id='school',role_id='role-school',
                        password_hash=hash_password(FIXTURE_PASSWORD),is_admin=False,must_change_password=False))
            db.commit()


def make_rule(client,target_kind,target_id):
    r=post(client,'/api/organization-assessment-rules',{
        'target_kind':target_kind,'name':target_kind+'考核规则','period_id':'period2026',
        'config':{'components':[{'key':'income','label':'培训收入','source':'income','weight':'100','target':'100'}]},
        'reason':'隔离测试组织规则','basis':'采购第10项'
    })
    assert r.status_code==200,r.text
    rule=r.json()
    t=post(client,f"/api/organization-assessment-rules/{rule['id']}/trial",{'target_ids':[target_id]})
    assert t.status_code==200,t.text
    a=post(client,f"/api/organization-assessment-rules/{rule['id']}/actions",{'expected_version':rule['version'],'action':'activate','reason':'试算通过后启用','basis':'隔离测试'})
    assert a.status_code==200,a.text
    return a.json()


def calculate(client,target_kind,target_id):
    r=post(client,'/api/organization-assessments/calculate',{'period_id':'period2026','target_kind':target_kind,'target_ids':[target_id],
          'reason':'生成组织考核','basis':'隔离测试'})
    assert r.status_code==200,r.text
    return r.json()['items'][0]


def action(client,obj,action):
    return post(client,f"/api/organization-assessments/{obj['id']}/actions",{'expected_version':obj['version'],'action':action,'reason':action+'测试','basis':'隔离测试'})


def test_org_rule_requires_weight_100(client2):
    auth(client2,'schooladmin')
    r=post(client2,'/api/organization-assessment-rules',{
        'target_kind':'dept','name':'错误规则','period_id':'period2026',
        'config':{'components':[{'key':'income','label':'培训收入','source':'income','weight':'90','target':'100'}]},
        'reason':'错误权重测试','basis':'测试'
    })
    assert r.status_code==422


def test_department_assessment_full_workflow_and_archive(client2,app2):
    auth(client2,'schooladmin');make_rule(client2,'dept','dept1');obj=calculate(client2,'dept','dept1')
    assert obj['state']=='GENERATED'
    # Generator is school admin and cannot act as department reviewer anyway.
    auth(client2,'otherdept')
    cross=action(client2,obj,'review');assert cross.status_code in {403,404}
    auth(client2,'depthead');r=action(client2,obj,'review');assert r.status_code==200,r.text;obj=r.json();assert obj['state']=='REVIEWED'
    auth(client2,'schooladmin');r=action(client2,obj,'school_audit');assert r.status_code==200,r.text;obj=r.json();assert obj['state']=='SCHOOL_APPROVED'
    r=action(client2,obj,'archive');assert r.status_code==200,r.text;obj=r.json();assert obj['state']=='ARCHIVED' and len(obj['archive_sha256'])==64
    # Archived result cannot be silently overwritten by recalculation.
    recalc=post(client2,'/api/organization-assessments/calculate',{'period_id':'period2026','target_kind':'dept','target_ids':['dept1'],'reason':'不应覆盖','basis':'测试'})
    assert recalc.status_code==409
    with Session(app2.state.engine) as db:
        stored=db.get(OrganizationAssessment,obj['id']);assert stored.archive_sha256==obj['archive_sha256']
        evidence=db.query(OrganizationAssessmentMetricEvidence).filter_by(assessment_id=obj['id']).all()
        assert len(evidence)==1 and evidence[0].metric_code=='income' and evidence[0].rule_version==1


def test_college_and_school_are_independent_targets(client2,app2):
    ensure_school_reviewer(app2)
    auth(client2,'schooladmin')
    make_rule(client2,'college','college1');college=calculate(client2,'college','college1')
    make_rule(client2,'school','school');school=calculate(client2,'school','school')
    assert college['target_kind']=='college' and school['target_kind']=='school'
    auth(client2,'collegehead');r=action(client2,college,'review');assert r.status_code==200;college=r.json()
    auth(client2,'schooladmin');r=action(client2,college,'school_audit');assert r.status_code==200;college=r.json();r=action(client2,college,'archive');assert r.status_code==200
    # School target requires a second school-level person to review because generator cannot review.
    auth(client2,'schooladmin');bad=action(client2,school,'review');assert bad.status_code==403
    auth(client2,'schoolreviewer');r=action(client2,school,'review');assert r.status_code==200;school=r.json()
    # Reviewer cannot be the school auditor.
    bad=action(client2,school,'school_audit');assert bad.status_code==403
    auth(client2,'schooladmin');r=action(client2,school,'school_audit');assert r.status_code==200;school=r.json();r=action(client2,school,'archive');assert r.status_code==200


def test_teacher_cannot_read_organization_assessment(client2):
    auth(client2,'schooladmin');make_rule(client2,'dept','dept1');obj=calculate(client2,'dept','dept1')
    auth(client2,'teacher')
    r=client2.get('/api/organization-assessments')
    assert r.status_code==403
    d=client2.get('/api/organization-assessments/'+obj['id'])
    assert d.status_code==403
