from datetime import date, datetime
from conftest import auth
from app.models import Qualification, WorkflowEvent, Role, Setting
from app.social_models import SocialResource, SocialPolicy, SocialAnnual, SocialProject
from app.reference_data import TrainingProjectMaster
from app import approval_center as center


def qualification(db, ident, teacher='teacher', state='SUBMITTED'):
    db.add(Qualification(id=ident, teacher_id=teacher, category='职业资格', name='合成证书'+ident,
        certificate_no=ident, issuer='隔离机构', obtained=date(2025,1,1), state=state))


def event(db, ident, actor='collegehead', kind='qualification', action='资质审核通过',
          before='SUBMITTED', after='APPROVED', day=1):
    db.add(WorkflowEvent(object_type=kind, object_id=ident, actor_id=actor,
        actor_name='隔离办理人', org_id='college1', action=action,
        before={} if before is None else {'state':before}, after={'state':after},
        reason='仅隔离回归', basis='合成依据', created_at=datetime(2026,9,day)))


def test_center_requires_management_identity_and_current_scope(client2, app2):
    assert client2.get('/api/approval-center').status_code==401
    with app2.state.sessions.begin() as db:
        qualification(db,'own');qualification(db,'outside','otherteacher')
    auth(client2,'teacher')
    assert client2.get('/api/approval-center').status_code==403
    for user,expected in [('depthead',{'own'}),('collegehead',{'own'}),('schooladmin',{'own','outside'})]:
        auth(client2,user);r=client2.get('/api/approval-center')
        assert r.status_code==200,r.text
        assert {x['id'] for x in r.json()['items']}==expected
    auth(client2,'collegehead')
    assert client2.get('/api/approval-center?org_id=college2').status_code==403
    assert client2.get('/api/approval-center?tab=invalid').status_code==422


def test_center_searches_owner_and_business_before_paging_and_keeps_batch_state(client2, app2):
    with app2.state.sessions.begin() as db:
        for i in range(23):qualification(db,'Q'+str(i))
    auth(client2,'collegehead')
    r=client2.get('/api/approval-center?q=J001&page=2&size=20').json()
    assert r['total']==23 and len(r['items'])==3
    assert all(x['staff_no']=='J001' and x['state']=='SUBMITTED' and x['state_label']=='待审核' for x in r['items'])
    item=client2.get('/api/approval-center?q=合成证书Q17').json()['items']
    assert len(item)==1 and item[0]['id']=='Q17'
    assert 'password' not in str(r) and 'before' not in str(r) and 'attachment_ids' not in str(r)
    assert not r['can_archive']


def test_handled_uses_own_latest_decision_not_upload_or_other_scope(client2, app2):
    with app2.state.sessions.begin() as db:
        qualification(db,'done',state='APPROVED');qualification(db,'outside','otherteacher',state='APPROVED')
        qualification(db,'upload-only',state='APPROVED')
        event(db,'done',action='资质退回补充',after='RETURNED',day=1)
        event(db,'done',day=3);event(db,'done',action='上传业务佐证',before='APPROVED',day=4)
        event(db,'outside');event(db,'upload-only',action='上传业务佐证')
    auth(client2,'collegehead')
    r=client2.get('/api/approval-center?tab=handled').json()
    assert r['total']==1
    item=r['items'][0]
    assert item['id']=='done' and item['my_action']=='资质审核通过'
    assert item['handled_at'].startswith('2026-09-03') and item['state']=='已通过'
    with app2.state.sessions.begin() as db:db.get(Role,'role-college').permissions=['portal.read']
    assert client2.get('/api/approval-center?tab=handled').json()['total']==0



def test_started_includes_delegated_original_application_without_counting_submission_as_handled(client2, app2):
    with app2.state.sessions.begin() as db:
        db.add(SocialResource(id='app1',org_id='college1',kind='course_apply',code='CA-AUDIT',
            name='隔离代登记课程',state='COLLEGE',data={'application':True,'source':'manual',
                'teacher_id':'teacher','created_by':'collegehead'}))
        event(db,'app1',kind='social_resource',action='提交培训课程申报',before=None,after='COLLEGE')
    auth(client2,'collegehead')
    r=client2.get('/api/approval-center?tab=mine').json()
    assert r['total']==1 and r['items'][0]['type']=='application'
    assert r['items'][0]['business_name']=='隔离代登记课程'
    assert client2.get('/api/approval-center?tab=handled').json()['total']==0
    with app2.state.sessions.begin() as db:
        db.get(SocialResource,'app1').state='SCHOOL'
        event(db,'app1',kind='social_resource',action='学院退回培训课程申报',before='COLLEGE',after='RETURNED',day=2)
        event(db,'app1',kind='social_resource',action='学院通过培训课程申报',before='COLLEGE',after='SCHOOL',day=3)
    handled=client2.get('/api/approval-center?tab=handled').json()['items']
    assert len(handled)==1 and handled[0]['my_action']=='学院通过培训课程申报'
    assert handled[0]['handled_at'].startswith('2026-09-03')
    with app2.state.sessions.begin() as db:db.get(Role,'role-college').permissions=['portal.read']
    assert client2.get('/api/applications/app1').status_code==200
    assert client2.get('/api/approval-center?tab=mine').json()['total']==1


def test_unfinished_period_and_publication_are_waiting_not_current_approval(client2, app2, monkeypatch):
    monkeypatch.setattr(center,'school_today',lambda:date(2026,10,18))
    with app2.state.sessions.begin() as db:
        db.add(Setting(key='social_training_duties',value={'secretary':['schooladmin'],'coordinator':['schooladmin']}))
        for ident,state,data in [('period','SUBMITTED',{'year':2026,'start_month':9,'end_month':10}),
            ('public','PUBLIC',{'year':2025,'start_month':1,'end_month':12,'public_end':'2026-10-23'})]:
            db.add(SocialResource(id=ident,kind='point_report',code=ident,name='合成汇总'+ident,
                org_id='school',state=state,data={**data,'created_by':'teacher','rows':[],'disputes':[]}))
    auth(client2,'schooladmin')
    with app2.state.sessions.begin() as db:
        event(db,'period',actor='schooladmin',kind='social_resource',action='积分汇总：重新取数并保存草稿',before='SUBMITTED',after='DRAFT',day=4)
        event(db,'period',actor='schooladmin',kind='social_resource',action='积分汇总：待归口复核',before='DRAFT',after='SUBMITTED',day=5)
    assert client2.get('/api/approval-center?tab=handled').json()['total']==0
    r=client2.get('/api/approval-center').json()
    assert r['total']==0 and r['waiting']==2 and r['can_archive']
    monkeypatch.setattr(center,'school_today',lambda:date(2026,10,24))
    r=client2.get('/api/approval-center').json()
    assert {x['id'] for x in r['items']}=={'public'} and r['waiting']==1
    monkeypatch.setattr(center,'school_today',lambda:date(2026,11,1))
    assert client2.get('/api/approval-center').json()['total']==2


def test_annual_publication_state_transition_counts_as_a_decision(client2, app2):
    with app2.state.sessions.begin() as db:
        db.add(SocialPolicy(id='policy-center',period_id='period2026',name='合成制度',state='ACTIVE',data={},created_by='schooladmin'))
        db.flush()
        db.add(SocialAnnual(id='annual-center',org_id='college1',period_id='period2026',policy_id='policy-center',owner_id='collegehead',state='PUBLIC',data={'self_report':'不应出现在清单的报告'},snapshot={'public_end':'2026-10-23'}))
        event(db,'annual-center',actor='schooladmin',kind='social_annual',action='年度考核：公示中',before='COMMITTEE',after='PUBLIC')
    auth(client2,'schooladmin')
    result=client2.get('/api/approval-center?tab=handled')
    assert result.status_code==200,result.text
    assert result.json()['total']==1 and result.json()['items'][0]['state']=='公示中'
    assert '不应出现在清单的报告' not in result.text


def test_base_final_approval_remains_in_handled_despite_draft_storage_state(client2, app2):
    with app2.state.sessions.begin() as db:
        db.add(SocialResource(id='approved-base',org_id='college1',kind='base',code='BASE-CENTER',
            name='已生效合成基地',state='DRAFT',data={'application':True,'teacher_id':'teacher','created_by':'teacher'}))
        event(db,'approved-base',actor='schooladmin',kind='social_resource',
            action='学校通过培训基地申请',before='SCHOOL',after='DRAFT')
    auth(client2,'schooladmin')
    response=client2.get('/api/approval-center?tab=handled')
    assert response.status_code==200,response.text
    result=response.json()
    assert result['total']==1
    assert result['items'][0]['id']=='approved-base'
    assert result['items'][0]['my_action']=='学校通过培训基地申请'


def test_same_second_decisions_use_numeric_version_before_random_event_id(client2, app2):
    with app2.state.sessions.begin() as db:
        qualification(db,'same-second',state='APPROVED')
        for ident,version,action,after in [
            ('ffffffff-ffff-4fff-8fff-ffffffffffff',9,'资质退回补充','RETURNED'),
            ('00000000-0000-4000-8000-000000000000',12,'资质审核通过','APPROVED'),
            ('eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee',13,'上传业务佐证','APPROVED')]:
            db.add(WorkflowEvent(id=ident,object_type='qualification',object_id='same-second',
                actor_id='collegehead',actor_name='隔离办理人',org_id='college1',action=action,
                before={'state':'SUBMITTED'},after={'state':after,'version':version},
                reason='仅隔离回归',basis='合成依据',created_at=datetime(2026,9,1)))
    auth(client2,'collegehead')
    response=client2.get('/api/approval-center?tab=handled')
    assert response.status_code==200,response.text
    result=response.json()
    assert result['total']==1 and result['items'][0]['my_action']=='资质审核通过'


def test_unsubmitted_project_draft_does_not_inflate_approval_count(client2, app2):
    with app2.state.sessions.begin() as db:
        db.add(TrainingProjectMaster(id='center-master',code='CENTER-DRAFT',name='待完善合成项目'))
        db.flush()
        db.add(SocialProject(id='center-draft',master_id='center-master',org_id='college1',owner_id='teacher',
            cohort='合成第一期',state='DRAFT',data={'name':'待完善合成项目','code':'CENTER-DRAFT'}))
    auth(client2,'collegehead')
    result=client2.get('/api/approval-center').json()
    assert result['total']==0 and result['waiting']==1
    assert result['waiting_items'][0]['id']=='center-draft'
    assert result['waiting_items'][0]['business_code']=='CENTER-DRAFT'
    assert '尚未提交' in result['waiting_items'][0]['action_hint']
