"""超星课程导入、满意度自动成果及推荐口径草稿。"""
from decimal import Decimal
from sqlalchemy import select
from app.models import WorkflowEvent
from app.social_models import SocialResource, SocialPolicy
from app.social_schemas import PolicyData
from app.routes.social import satisfaction_achievement
from app import social_training as st
from conftest import auth, post, put
from test_social_training import setup_social, row, import_rows, close_project, detail, action, proof

CHECKED=['plan','filing_form','roster','attendance','hours','process','assessment','outcomes']


def close_with(client,pid,satisfaction):
    r=action(client,'projects','social_project',pid,'close_submit',closeout={'closed_on':'2026-09-02','outcome_report':'完整结项报告','satisfaction':satisfaction,'actual_income':'10000','funding_source':'other_training','retained':'2000','personnel':'6000','finance_reference':'财务确认凭证','location':'onsite','implicit_cost':'0','settlement_on':'2026-09-03','materials_checked':CHECKED})
    assert r.status_code==200,r.text
    r=action(client,'projects','social_project',pid,'close');assert r.status_code==200,r.text


def achievements(app2):
    with app2.state.sessions() as db:
        return db.scalars(select(SocialResource).where(SocialResource.kind=='achievement')).all()


def recommended(client,period='period2026'):
    auth(client,'schooladmin')
    return post(client,'/api/social/policies/recommended',{'period_id':period,'reason':'生成推荐口径草稿','basis':'学校重新规划第八节'})


def test_satisfaction_above_95_records_one_school_achievement(setup_social,client2,app2):
    pid=setup_social;assert import_rows(client2,pid,[row()]).status_code==200;close_with(client2,pid,'96.5')
    rows=achievements(app2);assert len(rows)==1;item=rows[0]
    assert item.code=='SAT-'+pid and item.org_id=='college1' and item.state=='DRAFT'
    assert item.name=='隔离技能培训（满意度 96.5%）'
    assert item.data['level']=='school' and item.data['auto'] is True and item.data['source']=='satisfaction' and item.data['project_id']==pid
    events=detail(client2,'social_resource',item.id)['events'];assert len(events)==1 and events[0]['actor_id']=='reviewer'
    with app2.state.sessions.begin() as db:
        project=db.get(st.SocialProject,pid);assert satisfaction_achievement(db,None,project,'重复登记')is None
    assert len(achievements(app2))==1
    workspace=client2.get('/api/social/workspace',params={'section':'outcomes'}).json()
    assert [r['code'] for r in workspace['resources']]==['SAT-'+pid]


def test_exactly_95_satisfaction_does_not_qualify(setup_social,client2,app2):
    pid=setup_social;assert import_rows(client2,pid,[row()]).status_code==200;close_with(client2,pid,'95')
    assert achievements(app2)==[]


def test_recommended_policy_draft_and_permissions(setup_social,client2,app2):
    auth(client2,'collegehead')
    assert post(client2,'/api/social/policies/recommended',{'period_id':'period2026','reason':'越权生成'}).status_code==403
    r=recommended(client2);assert r.status_code==200,r.text
    item=r.json()['item'];assert item['state']=='DRAFT' and item['name']=='推荐口径（待学校书面确认）'
    assert item['data']==st.serial(PolicyData.model_validate(st.RECOMMENDED_POLICY).model_dump())
    assert item['data']['interpretation_reference']=='' and item['data']['satisfaction_inclusive'] is False and item['data']['calendar_start'] is None
    assert Decimal(item['data']['total_cap'])==110
    assert r.json()['events'][0]['action']=='生成推荐口径草稿'
    assert recommended(client2,'no-such-period').status_code in {404,409,422}
    proof(client2,'social_policy',item['id'],item['version'])
    auth(client2,'reviewer');r=action(client2,'policies','social_policy',item['id'],'activate')
    assert r.status_code==409 and '书面解释依据' in r.text
    with app2.state.sessions() as db:assert db.get(SocialPolicy,item['id']).state=='DRAFT'


def test_recommended_draft_trials_compute_and_auto_achievement_not_double_counted(setup_social,client2,app2):
    pid=setup_social;assert import_rows(client2,pid,[row()]).status_code==200;close_project(client2,pid)
    pol=recommended(client2).json()['item']['id']
    auth(client2,'teacher');r=post(client2,'/api/social/claims',{'project_id':pid,'period_id':'period2026','policy_id':pol,'recognition_form_reference':'学校制式认定表与佐证附件','reason':'推荐口径试算'})
    assert r.status_code==200,r.text;trial=r.json()['trial']
    assert trial['total']=='1.56' and trial['teaching']=='1.56'
    assert not any('尚待学校书面确认' in b for b in trial['blockers'])
    assert '制度执行口径尚未正式启用' in trial['blockers']
    auth(client2,'schooladmin')
    auto=[{'reference':'SAT-'+pid,'name':'满意度自动成果','level':'school'}]
    data={'org_id':'college1','period_id':'period2026','policy_id':pol,'reason':'年度自评推荐口径试算','data':{'self_report':'完整自评报告','income_target':'10000','participants_target':30,'priority_target':30,'target_reference':'年度任务确认','achievements':auto}}
    r=post(client2,'/api/social/annuals',data);assert r.status_code==200,r.text;annual=r.json()['trial'];item=r.json()['item']
    assert annual['achievement_base']=='2.00' and annual['total'] is not None and annual['grade'] is not None
    assert not any('尚待学校书面确认' in b for b in annual['blockers'])
    assert '年度规则尚未正式启用' in annual['blockers']
    data['data']['achievements']=auto+[{'reference':'A1','name':'校级成果','level':'school','confirmed_on':'2026-09-02','recognition_reference':'隔离学校成果确认决定'}];data['expected_version']=item['version']
    r=put(client2,'/api/social/annuals/'+item['id'],data);assert r.status_code==200,r.text
    assert r.json()['trial']['achievement_base']=='4.00'


def test_chaoxing_course_import_records_video_totals(setup_social,client2,app2):
    base={'project_code':'SOC-P1','source':'chaoxing','reason':'超星导出表导入'}
    rows=[{**base,'code':'CX-1001','name':'超星课程一','teacher':'张老师','video_count':12,'video_minutes':'95.5','chapters':6,'learners':120},
          {**base,'code':'CX-1002','name':'超星课程二'}]
    data={'rows':rows,'reason':'超星导出表导入','basis':'超星学习通课程列表'}
    bad={**data,'rows':[{**rows[0],'video_minutes':None}]}
    assert post(client2,'/api/social/courses/import/preview',bad).status_code==422
    preview=post(client2,'/api/social/courses/import/preview',data);assert preview.status_code==200,preview.text
    assert preview.json()['count']==2 and preview.json()['videos']==1
    r=post(client2,'/api/social/courses/import/confirm',{**data,'preview_hash':preview.json()['preview_hash']});assert r.status_code==200,r.text
    assert r.json()=={'count':2,'video_resources':1}
    workspace=client2.get('/api/social/workspace',params={'section':'courses'}).json()
    courses={c['code']:c for c in workspace['courses']};assert courses['CX-1001']['source']=='超星学习通导出'
    assert workspace['course_stats']['CX-1001']=={'resources':1,'videos':12,'minutes':'95.5'}
    assert 'CX-1002' not in workspace['course_stats']
    resource=[x for x in workspace['resources'] if x['kind']=='course_resource'][0]
    assert resource['data']['resource_type']=='video' and resource['data']['teacher']=='张老师' and resource['data']['chapters']==6 and resource['org_id']=='college1'
    with app2.state.sessions() as db:
        assert db.scalar(select(WorkflowEvent.id).where(WorkflowEvent.object_id==resource['id']))


def test_recommended_draft_can_record_written_basis_then_activate(setup_social,client2,app2):
    item=recommended(client2).json()['item']
    proof(client2,'social_policy',item['id'],item['version'])
    assert action(client2,'policies','social_policy',item['id'],'record_basis',basis=' ').status_code==422
    auth(client2,'collegehead');assert action(client2,'policies','social_policy',item['id'],'record_basis').status_code in {403,404}
    auth(client2,'schooladmin');r=action(client2,'policies','social_policy',item['id'],'record_basis',basis='湘科职函〔2026〕XX号 书面答复')
    assert r.status_code==200,r.text
    assert r.json()['item']['data']['interpretation_reference']=='湘科职函〔2026〕XX号 书面答复' and r.json()['item']['state']=='DRAFT'
    version=r.json()['item']['version']
    r=put(client2,'/api/social/policies/'+item['id']+'/calendar',{'expected_version':version,'calendar_start':'2026-01-01','calendar_end':'2027-12-31','calendar_reference':'学校正式校历','reason':'补充已确认校历'})
    assert r.status_code==200,r.text
    auth(client2,'reviewer');r=action(client2,'policies','social_policy',item['id'],'activate')
    assert r.status_code==200,r.text
    with app2.state.sessions() as db:assert db.get(SocialPolicy,item['id']).state=='ACTIVE'
    auth(client2,'schooladmin');assert action(client2,'policies','social_policy',item['id'],'record_basis').status_code==409


def test_zero_other_bonus_does_not_require_positive_bonus_evidence(setup_social,client2):
    pol=recommended(client2).json()['item']['id']
    auth(client2,'collegehead')
    body={'org_id':'college1','period_id':'period2026','policy_id':pol,'reason':'隔离零值回归','data':{'self_report':'隔离年度报告','other_bonus':'0','other_bonus_basis':''}}
    response=post(client2,'/api/social/annuals',body)
    assert response.status_code==200,response.text
    assert '其他加分缺少正式依据' not in response.json()['trial']['blockers']
    item=response.json()['item'];body['expected_version']=item['version'];body['data']['other_bonus']='1'
    response=put(client2,'/api/social/annuals/'+item['id'],body)
    assert response.status_code==200,response.text
    assert '其他加分缺少正式依据' in response.json()['trial']['blockers']
