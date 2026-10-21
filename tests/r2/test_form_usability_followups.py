from datetime import datetime
from app.models import WorkflowEvent
from app.social_models import SocialUnit
from app.social_training import project_followups,closing_effective_counts,remember_latest_case
from test_project_course_link import link_case
from test_social_training import row


def test_followup_uses_project_version_when_timestamps_and_uuid_order_disagree(link_case):
    app,_=link_case
    with app.state.sessions.begin() as db:
        db.add(SocialUnit(project_id='link-project',external_key='case-unit',data=row(count=3)))
        for ident,version,invalidated,reply in [('a-new',6,False,'最新续办'),('z-old',5,True,'原处理')]:
            db.add(WorkflowEvent(id=ident,created_at=datetime(2026,10,21,0,0,0),object_type='social_project',
                object_id='link-project',actor_id='schooladmin',actor_name='合成办理人',org_id='school',
                action='投诉与项目跟踪',before={},after={'case_reference':'CASE-ONE','expected_version':version,
                'kind':'violation','invalidate_cohort':invalidated,'reply':reply},reason='合成回归'))
    with app.state.sessions() as db:
        followups=project_followups(db,'link-project')
        assert len(followups)==1 and followups[0]['reply']=='最新续办'
        assert closing_effective_counts(db,['link-project'])['link-project']==3


def test_legacy_followups_without_versions_keep_existing_time_order():
    latest={}
    remember_latest_case(latest,'case',{'case_reference':'case','reply':'原记录'})
    remember_latest_case(latest,'case',{'case_reference':'case','reply':'后续记录'})
    assert latest['case']['reply']=='后续记录'
