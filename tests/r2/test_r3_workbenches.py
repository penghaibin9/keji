from datetime import date, datetime
from sqlalchemy import select
from app.models import Period, Rule, Assessment, Qualification
from conftest import auth


def _rule(db, ident='wb-rule'):
    obj=Rule(id=ident,kind='assessment',name='工作台测试规则',version_no=1,period_id='period2026',
        config={'components':[]},fingerprint='b'*64,state='ACTIVE',created_by='schooladmin',reason='测试')
    db.add(obj);db.flush();return obj


def test_teacher_latest_assessment_is_ordered_by_period_not_list_order(client2, app2):
    with app2.state.sessions.begin() as db:
        _rule(db)
        db.add(Period(id='period2025',name='2025测试周期',start_date=date(2025,1,1),end_date=date(2025,12,31),state='CLOSED'))
        db.flush()
        db.add(Assessment(id='a-old',teacher_id='teacher',period_id='period2025',rule_id='wb-rule',score=99,
            detail=[],source_snapshot={},state='ARCHIVED',version=1,archive={'old':True},archive_sha256='c'*64,
            created_at=datetime(2030,1,1)))
        db.add(Assessment(id='a-new',teacher_id='teacher',period_id='period2026',rule_id='wb-rule',score=88,
            detail=[],source_snapshot={},state='TEACHER',version=1,created_at=datetime(2026,1,1)))
    auth(client2,'teacher')
    r=client2.get('/api/assessment-summary/latest')
    assert r.status_code==200,r.text
    data=r.json();assert data['assessment']['id']=='a-new' and data['period']['id']=='period2026'
    r=client2.get('/api/assessment-summary/latest?period_id=period2025')
    assert r.status_code==200,r.text
    assert r.json()['assessment']['id']=='a-old'


def test_latest_assessment_summary_is_teacher_self_service(client2):
    auth(client2,'depthead')
    assert client2.get('/api/assessment-summary/latest').status_code==403


def test_department_workbench_has_only_current_scope_todos_and_progress(client2, app2):
    with app2.state.sessions.begin() as db:
        _rule(db,'wb-rule-2')
        db.add(Qualification(id='q-local',teacher_id='teacher',category='职业资格',name='本教研室待审资质',certificate_no='Q-LOCAL',issuer='测试',obtained=date(2026,1,1),state='SUBMITTED'))
        db.add(Qualification(id='q-other',teacher_id='otherteacher',category='职业资格',name='其他教研室资质',certificate_no='Q-OTHER',issuer='测试',obtained=date(2026,1,1),state='SUBMITTED'))
        db.add(Assessment(id='a-local',teacher_id='teacher',period_id='period2026',rule_id='wb-rule-2',score=80,detail=[],source_snapshot={},state='DEPARTMENT'))
        db.add(Assessment(id='a-other',teacher_id='otherteacher',period_id='period2026',rule_id='wb-rule-2',score=81,detail=[],source_snapshot={},state='DEPARTMENT'))
    auth(client2,'depthead')
    r=client2.get('/api/organization-workbench?period_id=period2026&project_code=P1')
    assert r.status_code==200,r.text
    d=r.json()
    assert d['organization']['id']=='dept1'
    assert d['statistics']['teachers']==1
    assert d['assessment_states']=={'DEPARTMENT':1}
    assert d['todos']['total']==2
    assert {x['id'] for x in d['todos']['items']}=={'q-local','a-local'}
    assert client2.get('/api/organization-workbench?org_id=dept2').status_code==403


def test_college_can_drill_own_department_but_teacher_cannot_open_management_workbench(client2, app2):
    auth(client2,'collegehead')
    r=client2.get('/api/organization-workbench?org_id=dept1')
    assert r.status_code==200,r.text
    assert r.json()['organization']['id']=='dept1'
    auth(client2,'teacher')
    assert client2.get('/api/organization-workbench').status_code==403

def test_organization_assessment_enters_unified_todos_for_review_audit_and_archive(app2,client2):
    from sqlalchemy.orm import Session
    from app.org_assessment import OrganizationAssessmentRule,OrganizationAssessment
    from app.core import digest
    config={'components':[{'key':'hours','label':'学时','source':'hours','weight':'100','target':'10'}]}
    with Session(app2.state.engine) as db:
        rule=OrganizationAssessmentRule(id='todo-org-rule',target_kind='dept',name='待办组织规则',version_no=9,period_id='period2026',config=config,
            fingerprint=digest(config),state='ACTIVE',created_by='schooladmin',reason='待办测试')
        db.add(rule);db.flush()
        obj=OrganizationAssessment(id='todo-org-assess',target_kind='dept',target_id='dept1',period_id='period2026',rule_id=rule.id,score=88,detail=[],source_snapshot={},state='GENERATED',generated_by='schooladmin')
        db.add(obj);db.commit()
    auth(client2,'depthead');items=client2.get('/api/todos').json()['items']
    assert any(x['type']=='organization_assessment' and x['id']=='todo-org-assess' and x['state']=='GENERATED' for x in items)
    with Session(app2.state.engine) as db:
        obj=db.get(OrganizationAssessment,'todo-org-assess');obj.state='REVIEWED';obj.reviewed_by='depthead';db.commit()
    auth(client2,'schooladmin');items=client2.get('/api/todos').json()['items']
    assert any(x['type']=='organization_assessment' and x['id']=='todo-org-assess' and x['state']=='REVIEWED' for x in items)
    with Session(app2.state.engine) as db:
        obj=db.get(OrganizationAssessment,'todo-org-assess');obj.state='SCHOOL_APPROVED';obj.school_audited_by='schooladmin';db.commit()
    items=client2.get('/api/todos').json()['items']
    assert any(x['type']=='organization_assessment' and x['id']=='todo-org-assess' and x['state']=='SCHOOL_APPROVED' for x in items)
