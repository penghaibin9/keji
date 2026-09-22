"""R10: synthetic HTTP/data corruption controls, not MySQL concurrency proof."""
from copy import deepcopy
from decimal import Decimal
import pytest
from sqlalchemy import select
from fastapi import HTTPException
from app.core import digest
from app.models import Org, Period, WorkflowEvent, Assessment
from app.org_assessment import OrganizationAssessment, OrganizationAssessmentMetricEvidence, organization_facts
from conftest import auth, post
from test_r3_org_assessment import make_rule, calculate, action
from test_r6_evidence_chain import archive as teacher_archive


def archived_org(client, target='dept1', create_rule=True):
    auth(client, 'schooladmin')
    if create_rule: make_rule(client, 'dept', target)
    obj = calculate(client, 'dept', target)
    auth(client, 'depthead' if target == 'dept1' else 'otherdept')
    for who, step in ((None, 'review'), ('schooladmin', 'school_audit'), (None, 'archive')):
        if who: auth(client, who)
        r=action(client,obj,step); assert r.status_code==200,r.text; obj=r.json()
    return obj


def test_org_history_does_not_include_later_workflow(client2, app2):
    x=archived_org(client2)
    url=f"/api/organization-assessments/{x['id']}"
    before=client2.get(url).json()
    with app2.state.sessions.begin() as db:
        db.add(WorkflowEvent(object_type='organization_assessment',object_id=x['id'],actor_id='schooladmin',actor_name='后来改名',
            org_id='school',action='归档后追加的运维记录',before={},after={},reason='隔离合成测试',basis='不属于当期办理'))
    r=client2.get(url);assert r.status_code==200,r.text
    assert r.json()['events']==before['events']
    assert r.json()['events_frozen'] is True
    assert r.json()['events'][-1]['action']=='组织考核归档'


def test_org_list_uses_frozen_target_and_period(client2,app2):
    x=archived_org(client2)
    with app2.state.sessions.begin() as db:
        db.get(Org,'dept1').name='当前已更名的教研室'
        db.get(Period,'period2026').name='当前已更名的周期'
    r=client2.get('/api/organization-assessments');assert r.status_code==200,r.text
    row=next(a for a in r.json()['items'] if a['id']==x['id'])
    assert row['target_display_name']==x['archive']['target']['name']
    assert row['period_display_name']==x['archive']['period']['name']


@pytest.mark.parametrize('mutation',['score','version','detail','source','payload_swap','target_metadata','evidence','event_binding'])
def test_org_bad_archive_rejected_by_detail_print_list_ranking(client2,app2,mutation):
    x=archived_org(client2)
    if mutation=='payload_swap':
        other=archived_org(client2,'dept2',create_rule=False)
    with app2.state.sessions.begin() as db:
        obj=db.get(OrganizationAssessment,x['id'])
        if mutation=='score':obj.score=Decimal('99')
        elif mutation=='version':obj.version+=1
        elif mutation=='detail':obj.detail=[]
        elif mutation=='source':obj.source_snapshot={**obj.source_snapshot,'values':{}}
        else:
            p=deepcopy(obj.archive)
            if mutation=='payload_swap':p=deepcopy(db.get(OrganizationAssessment,other['id']).archive)
            elif mutation=='target_metadata':p['target']['id']='dept2'
            elif mutation=='evidence':p['evidence'][0]['assessment_id']='unrelated-assessment'
            elif mutation=='event_binding':
                # Legacy R9 has no frozen events. A new-format proof cannot bind events from another object.
                p['schema_version']=2
                p['events']=[{'object_type':'organization_assessment','object_id':'unrelated-assessment','action':'组织考核归档','actor_id':'schooladmin'}]
            obj.archive=p;obj.archive_sha256=digest(p)
    for url in (f"/api/organization-assessments/{x['id']}",f"/api/organization-assessments/{x['id']}/print",
        '/api/organization-assessments?state=ARCHIVED',
        f"/api/organization-assessments/ranking?period_id=period2026&target_kind=dept&rule_id={x['rule_id']}"):
        r=client2.get(url);assert r.status_code==409,(mutation,url,r.status_code,r.text[:200])


def test_rank_validates_corrupt_archive_outside_current_page(client2,app2):
    first=archived_org(client2)
    archived_org(client2,'dept2',create_rule=False)
    with app2.state.sessions.begin() as db:
        db.get(OrganizationAssessment,first['id']).score=Decimal('-1')
    # Low corrupt score lies off first page; it still participates in rank calculation.
    r=client2.get(f"/api/organization-assessments/ranking?period_id=period2026&target_kind=dept&rule_id={first['rule_id']}&size=1")
    assert r.status_code==409,r.text


def test_legacy_org_archive_never_fills_events_from_live_history(client2,app2):
    x=archived_org(client2)
    with app2.state.sessions.begin() as db:
        obj=db.get(OrganizationAssessment,x['id']);p=deepcopy(obj.archive)
        p.pop('schema_version',None);p.pop('events',None);obj.archive=p;obj.archive_sha256=digest(p)
    r=client2.get(f"/api/organization-assessments/{x['id']}/print");assert r.status_code==200,r.text
    assert r.json()['events']==[]
    assert r.json()['events_frozen'] is False
    assert '未冻结' in r.json()['history_note']


@pytest.mark.parametrize('mutation',['missing','wrong_score','wrong_scope'])
def test_org_archive_refuses_inconsistent_calculated_evidence(client2,app2,mutation):
    auth(client2,'schooladmin');make_rule(client2,'dept','dept1');x=calculate(client2,'dept','dept1')
    auth(client2,'depthead');r=action(client2,x,'review');assert r.status_code==200;x=r.json()
    auth(client2,'schooladmin');r=action(client2,x,'school_audit');assert r.status_code==200;x=r.json()
    with app2.state.sessions.begin() as db:
        ev=db.scalar(select(OrganizationAssessmentMetricEvidence).where(OrganizationAssessmentMetricEvidence.assessment_id==x['id']))
        if mutation=='missing':db.delete(ev)
        elif mutation=='wrong_score':ev.calculated_score=Decimal('33')
        else:ev.scope_snapshot={'target':{'id':'dept2'},'teacher_ids':['otherteacher'],'org_ids':['dept2']}
    r=action(client2,x,'archive');assert r.status_code==409,r.text
    with app2.state.sessions() as db:
        obj=db.get(OrganizationAssessment,x['id'])
        assert obj.state=='SCHOOL_APPROVED' and obj.archive is None and obj.version==x['version']


def test_org_facts_cannot_average_corrupt_teacher_archive(client2,app2):
    x=teacher_archive(client2)
    with app2.state.sessions.begin() as db:
        db.get(Assessment,x['id']).score=Decimal('99')
        with pytest.raises(HTTPException) as e:organization_facts(db,db.get(Org,'dept1'),db.get(Period,'period2026'))
        assert e.value.status_code==409


def test_org_facts_uses_verified_teacher_average_and_reference(client2,app2):
    x=teacher_archive(client2)
    with app2.state.sessions() as db:
        raw,snapshot=organization_facts(db,db.get(Org,'dept1'),db.get(Period,'period2026'))
        assert raw['assessment_score']==Decimal(x['score'])
        assert snapshot['assessment_references']==[{'id':x['id'],'teacher_id':x['teacher_id'],'archive_sha256':x['archive_sha256'],'score':x['score']}]


def test_org_rank_keeps_competition_ties_and_own_scope(client2):
    first=archived_org(client2);archived_org(client2,'dept2',create_rule=False)
    url=f"/api/organization-assessments/ranking?period_id=period2026&target_kind=dept&rule_id={first['rule_id']}"
    r=client2.get(url);assert r.status_code==200,r.text
    assert [a['rank'] for a in r.json()['items']]==[1,1]
    auth(client2,'depthead');r=client2.get(url);assert r.status_code==200,r.text
    assert [a['target_id'] for a in r.json()['items']]==['dept1']


@pytest.mark.parametrize('kind',['organization_assessments','handover'])
def test_org_corruption_blocks_async_excel_and_portable_export(client2,app2,kind):
    from app.worker import run_once
    from app.models import Task
    x=archived_org(client2)
    with app2.state.sessions.begin() as db:
        db.get(OrganizationAssessment,x['id']).score=Decimal('21')
    r=post(client2,'/api/exports',{'kind':kind,'filters':{},'confirmed':kind=='handover'})
    assert r.status_code==200,r.text
    task_id=r.json()['id']
    result=run_once(app2.state.settings);assert result['status']=='FAILED',result
    with app2.state.sessions() as db:
        assert not db.get(Task,task_id).result
    assert client2.get(f'/api/tasks/{task_id}/download').status_code==409


def test_org_excel_retains_frozen_target_name(client2,app2):
    from io import BytesIO
    from zipfile import ZipFile
    from test_r6_evidence_chain import export
    x=archived_org(client2)
    with app2.state.sessions.begin() as db:db.get(Org,'dept1').name='不要用于历史报表的新名称'
    blob=export(client2,app2,'organization_assessments')
    import xml.etree.ElementTree as ET
    with ZipFile(BytesIO(blob)) as z:
        text=''.join(''.join(ET.fromstring(z.read(n)).itertext()) for n in z.namelist() if n.startswith('xl/worksheets/') and n.endswith('.xml'))
    assert x['archive']['target']['name'] in text
    assert '不要用于历史报表的新名称' not in text
