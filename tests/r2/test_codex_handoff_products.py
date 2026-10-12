"""First-day policy workflow and spreadsheet handoff regressions."""
from datetime import date
from decimal import Decimal
from io import BytesIO

import pytest
from openpyxl import load_workbook
from app import social_training as st
from app.models import Setting, User
from app.social_models import SocialClaim, SocialPolicy
from app.excel_io import _date, rows_to_xlsx
from conftest import auth, post, put
from test_social_training import setup_social, policy, proof, detail, action, row, import_rows, close_project, payload


CALENDAR = {'calendar_start':'2026-01-01','calendar_end':'2027-12-31','calendar_reference':'学校正式校历','reason':'核对校历依据'}


def draft_policy(client):
    auth(client,'schooladmin')
    response=post(client,'/api/social/policies/recommended',{'period_id':'period2026','reason':'隔离口径草稿'})
    assert response.status_code==200,response.text
    item=response.json()['item'];proof(client,'social_policy',item['id'],item['version'])
    response=action(client,'policies','social_policy',item['id'],'record_basis',basis='学校书面确认依据')
    assert response.status_code==200,response.text
    return response.json()['item']


def add_calendar(client,item,**extra):
    return put(client,'/api/social/policies/'+item['id']+'/calendar',{**CALENDAR,'expected_version':item['version'],**extra})


def test_calendar_is_required_before_activation_and_draft_can_be_completed(setup_social,client2):
    item=draft_policy(client2)
    auth(client2,'reviewer')
    blocked=action(client2,'policies','social_policy',item['id'],'activate')
    assert blocked.status_code==409 and '工作日历' in blocked.text
    auth(client2,'collegehead');assert add_calendar(client2,item).status_code==403
    auth(client2,'schooladmin')
    assert add_calendar(client2,item,holidays=['2026-02-01'],workdays=['2026-02-01']).status_code==422
    assert add_calendar(client2,item,calendar_end='2025-12-31').status_code==422
    assert add_calendar(client2,item,calendar_reference='  ').status_code==422
    assert add_calendar(client2,item,holidays=['2028-01-01']).status_code==422
    response=add_calendar(client2,item);assert response.status_code==200,response.text
    assert response.json()['item']['data']['cap_mode']==item['data']['cap_mode']
    assert add_calendar(client2,item).status_code==409
    auth(client2,'reviewer');assert action(client2,'policies','social_policy',item['id'],'activate').status_code==200
    active=detail(client2,'social_policy',item['id'])['item']
    assert add_calendar(client2,active).status_code==409


def test_one_active_policy_and_explicit_deactivation_preserve_history(setup_social,client2,app2):
    first=policy(client2,True)
    second=draft_policy(client2);assert add_calendar(client2,second).status_code==200
    auth(client2,'reviewer')
    blocked=action(client2,'policies','social_policy',second['id'],'activate')
    assert blocked.status_code==409 and '已有生效口径' in blocked.text
    before=detail(client2,'social_policy',first)['item']['data']
    retired=action(client2,'policies','social_policy',first,'deactivate')
    assert retired.status_code==200 and retired.json()['item']['state']=='VOID'
    assert retired.json()['item']['data']==before
    assert action(client2,'policies','social_policy',second['id'],'activate').status_code==200
    with app2.state.sessions() as db:
        assert db.get(SocialPolicy,first).state=='VOID'
        assert db.get(SocialPolicy,second['id']).state=='ACTIVE'


def claim_draft(client,pid,policy_id):
    auth(client,'teacher')
    response=post(client,'/api/social/claims',{'project_id':pid,'period_id':'period2026','policy_id':policy_id,'recognition_form_reference':'学校制式认定表','reason':'本人积分申报'})
    assert response.status_code==200,response.text
    item=response.json()['item'];proof(client,'social_claim',item['id'],item['version'])
    return item['id']


def test_pending_claim_blocks_policy_deactivation(setup_social,client2):
    pid=setup_social;assert import_rows(client2,pid,[row()]).status_code==200
    pol=policy(client2,True);claim_draft(client2,pid,pol)
    auth(client2,'reviewer')
    denied=action(client2,'policies','social_policy',pol,'deactivate')
    assert denied.status_code==409 and '未归档' in denied.text
    assert detail(client2,'social_policy',pol)['item']['state']=='ACTIVE'


def test_claim_submission_requires_available_reviewers_without_self_review(setup_social,client2,app2,monkeypatch):
    monkeypatch.setattr(st,'today',lambda:date(2026,9,3))
    pid=setup_social;assert import_rows(client2,pid,[row()]).status_code==200;close_project(client2,pid)
    pol=policy(client2,True);ident=claim_draft(client2,pid,pol)
    for assigned,active in [([],True),(['depthead'],False),(['teacher'],True)]:
        with app2.state.sessions.begin() as db:
            cfg=db.get(Setting,'social_training_duties');cfg.value={**cfg.value,'secretary':assigned}
            db.get(User,'depthead').active=active
        response=action(client2,'claims','social_claim',ident,'submit')
        assert response.status_code==409 and '教学秘书' in response.text
        with app2.state.sessions() as db:assert db.get(SocialClaim,ident).state=='DRAFT'
    with app2.state.sessions.begin() as db:
        cfg=db.get(Setting,'social_training_duties');cfg.value={**cfg.value,'secretary':['depthead']}
        db.get(User,'depthead').active=True
    assert action(client2,'claims','social_claim',ident,'submit').status_code==200


@pytest.mark.parametrize('value,expected',[('2026/9/11','2026-09-11'),('2026/09/11','2026-09-11'),('2026-09-11','2026-09-11')])
def test_import_accepts_unambiguous_school_dates(value,expected):
    assert _date(value)==expected


@pytest.mark.parametrize('value',['2026/02/30','09/11/2026','2026/13/01'])
def test_import_rejects_invalid_or_ambiguous_dates(value):
    with pytest.raises(ValueError):_date(value)


def test_export_keeps_numbers_numeric_identifiers_text_and_formulas_inert():
    data=rows_to_xlsx(['数值','工号','文本'],[[Decimal('4.00'),'0000123','=1+1']])
    book=load_workbook(BytesIO(data))
    try:
        sheet=book.active
        assert sheet['A2'].value==4 and sheet['A2'].data_type=='n'
        assert sheet['B2'].value=='0000123' and sheet['B2'].data_type=='s'
        assert sheet['C2'].value=="'=1+1" and sheet['C2'].data_type=='s'
    finally:book.close()


def test_ledger_source_id_does_not_unlock_other_read_entrypoints(client2):
    from test_ledgers import sheet, upload
    auth(client2,'collegehead')
    response=upload(client2,'/api/social/ledgers',sheet(rows=[[1,'隔离技能培训',30,8,30,'测试教师一：30','2,3,4','']]),org_id='college1',year='2026',reason='权限入口隔离回归')
    assert response.status_code==200,response.text
    ledger=response.json();ident=ledger['id'];download=ledger['data']['file']['download_url']
    generated=post(client2,f'/api/social/ledgers/{ident}/projects',{'expected_version':ledger['version'],'reason':'核验本人项目来源编号'})
    assert generated.status_code==200,generated.text
    assert generated.json()['made'],generated.text
    project_id=generated.json()['made'][0]['project_id']
    assert client2.get(download).status_code==200
    auth(client2,'teacher')
    project=client2.get('/api/social/objects/social_project/'+project_id)
    assert project.status_code==200,project.text
    assert project.json()['item']['data']['source']['ledger_id']==ident
    paths=[f'/api/social/objects/social_resource/{ident}',f'/api/social/objects/social_resource/{ident}/export',
        f'/api/attachments?object_type=social_resource&object_id={ident}',download]
    for actor in ('teacher','depthead','otherteacher'):
        auth(client2,actor)
        for path in paths:assert client2.get(path).status_code==403,(actor,path)


@pytest.mark.parametrize('field',['level','scene'])
def test_project_creation_requires_explicit_policy_condition(client2,field):
    auth(client2,'collegehead');data=payload();data['data'].pop(field)
    response=post(client2,'/api/social/projects',data)
    assert response.status_code==422,response.text
    assert any(e['field']=='body.data.'+field for e in response.json()['errors'])
