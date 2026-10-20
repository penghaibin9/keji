import pytest
from sqlalchemy import select
from conftest import auth, post
from app.models import WorkflowEvent
from app.reference_data import TrainingCourseMaster, TrainingProjectMaster
from app.social_models import SocialProject, SocialResource


@pytest.fixture
def link_case(app2, client2):
    with app2.state.sessions.begin() as db:
        master=TrainingProjectMaster(code='LINK-P1',name='合成关联项目')
        db.add(master);db.flush()
        db.add(SocialProject(id='link-project',master_id=master.id,org_id='college1',owner_id='teacher',
            cohort='测试期次',state='FILED',data={'code':'LINK-P1','name':'合成关联项目'}))
        db.add(TrainingCourseMaster(id='link-course',code='LINK-C1',name='已审批合成课程',source='老师申请'))
        db.add(SocialResource(id='link-application',org_id='college1',kind='course_apply',code='APP-LINK-C1',
            name='已审批合成课程',state='ACTIVE',data={'application':True,'course_code':'LINK-C1','teacher_id':'teacher','hours':2}))
    auth(client2,'schooladmin')
    return app2,client2


def link(client,version=1,code='LINK-C1',**options):
    return post(client,'/api/social/projects/link-project/courses/link',
        {'expected_version':version,'course_code':code,'reason':'本轮合成项目复用已审批课程','basis':'合成核对依据'},**options)


@pytest.mark.parametrize('username,status',[('teacher',200),('collegehead',200),('schooladmin',200),
    ('depthead',403),('otherteacher',403),('otherdept',403)])
def test_searchable_course_options_respect_existing_link_scope(link_case,username,status):
    app,c=link_case;auth(c,username)
    response=c.get('/api/social/projects/link-project/course-options?q=合成&size=1')
    assert response.status_code==status,response.text
    if status==200:
        result=response.json()
        assert result['items']==[{'code':'LINK-C1','name':'已审批合成课程'}]
        assert result['total']==1 and result['size']==1
        assert c.get('/api/social/projects/link-project/course-options?q=%25').json()['items']==[]
        assert c.get('/api/social/projects/link-project/course-options?page=2&size=1').json()['items']==[]


@pytest.mark.parametrize('change',['inactive','linked','not_approved','not_application','other_college','other_owner'])
def test_course_picker_never_offers_ineligible_courses(link_case,change):
    app,c=link_case
    with app.state.sessions.begin() as db:
        course=db.get(TrainingCourseMaster,'link-course');application=db.get(SocialResource,'link-application')
        if change=='inactive':course.active=False
        if change=='linked':course.project_code='OTHER'
        if change=='not_approved':application.state='SUBMITTED'
        if change=='not_application':application.data={**application.data,'application':False}
        if change=='other_college':application.org_id='college2'
        if change=='other_owner':application.data={**application.data,'teacher_id':'otherteacher'}
    auth(c,'teacher')
    result=c.get('/api/social/projects/link-project/course-options')
    assert result.status_code==200,result.text
    assert result.json()['items']==[] and result.json()['total']==0


def test_link_reuses_course_and_preserves_approved_application(link_case):
    app,c=link_case
    with app.state.sessions() as db:
        original=dict(db.get(SocialResource,'link-application').data)
    result=link(c,key='link-once-0001')
    assert result.status_code==200,result.text
    assert link(c,key='link-once-0001').status_code==200
    with app.state.sessions() as db:
        course=db.get(TrainingCourseMaster,'link-course')
        assert course.project_code=='LINK-P1' and course.version==2
        assert len(db.scalars(select(TrainingCourseMaster).where(TrainingCourseMaster.code=='LINK-C1')).all())==1
        application=db.get(SocialResource,'link-application')
        assert application.data==original and application.state=='ACTIVE' and application.version==1
        project=db.get(SocialProject,'link-project')
        assert project.state=='FILED' and project.version==2
        events=db.scalars(select(WorkflowEvent).where(WorkflowEvent.object_id==project.id)).all()
        assert len(events)==1 and '关联已入库课程' in events[0].action
    assert link(c,version=2).status_code==409


@pytest.mark.parametrize('username,status',[('teacher',200),('collegehead',200),('depthead',403),('otherteacher',403),('otherdept',403)])
def test_link_respects_course_owner_and_project_management_scope(link_case,username,status):
    app,c=link_case;auth(c,username)
    response=link(c);assert response.status_code==status,response.text
    with app.state.sessions() as db:assert db.get(TrainingCourseMaster,'link-course').project_code==('LINK-P1' if status==200 else None)


@pytest.mark.parametrize('change',[ 'other_owner','other_course_owner','under_review'])
def test_teacher_cannot_link_others_courses_or_projects_or_change_reviewing_project(link_case,change):
    app,c=link_case
    with app.state.sessions.begin() as db:
        if change=='other_owner':db.get(SocialProject,'link-project').owner_id='otherteacher'
        elif change=='other_course_owner':
            a=db.get(SocialResource,'link-application');a.data={**a.data,'teacher_id':'otherteacher'}
        else:db.get(SocialProject,'link-project').state='COLLEGE'
    auth(c,'teacher');assert link(c).status_code in (403,409)
    with app.state.sessions() as db:assert db.get(TrainingCourseMaster,'link-course').project_code is None


def test_course_progress_and_link_candidates_are_scoped(link_case):
    app,c=link_case;auth(c,'teacher')
    response=c.get('/api/applications/link-application/course-points');assert response.status_code==200,response.text
    assert response.json()['stage']=='link' and response.json()['can_link']
    options=c.get('/api/social/project-options?course_application_id=link-application').json()
    assert [p['id'] for p in options['items']]==['link-project']
    assert link(c).status_code==200
    response=c.get('/api/applications/link-application/course-points').json()
    assert response['stage']=='work' and response['project']['id']=='link-project' and not response['can_claim']
    auth(c,'otherteacher')
    assert c.get('/api/applications/link-application/course-points').status_code==403
    assert c.get('/api/social/project-options?course_application_id=link-application').status_code==403


@pytest.mark.parametrize('change,status',[('other_college',403),('unapproved',403),('not_application',403),
    ('inactive',409),('already_linked',409),('closed_project',409),('stale_version',409),('missing',409)])
def test_link_rejects_invalid_source_without_mutation(link_case,change,status):
    app,c=link_case
    with app.state.sessions.begin() as db:
        source=db.get(SocialResource,'link-application');course=db.get(TrainingCourseMaster,'link-course')
        if change=='other_college':source.org_id='college2'
        elif change=='unapproved':source.state='DEPT'
        elif change=='not_application':source.data={**source.data,'application':False}
        elif change=='inactive':course.active=False
        elif change=='already_linked':course.project_code='OTHER-PROJECT'
        elif change=='closed_project':db.get(SocialProject,'link-project').state='CLOSED'
    result=link(c,version=9 if change=='stale_version' else 1,code='MISSING' if change=='missing' else 'LINK-C1')
    assert result.status_code==status,result.text
    with app.state.sessions() as db:
        assert db.get(TrainingCourseMaster,'link-course').project_code==('OTHER-PROJECT' if change=='already_linked' else None)
        assert db.get(SocialProject,'link-project').version==1


def test_registering_existing_course_returns_link_guidance(link_case):
    _,c=link_case
    response=post(c,'/api/social/courses',{'code':'LINK-C1','name':'不能覆盖原名称','project_code':'LINK-P1','reason':'重复登记测试'})
    assert response.status_code==409
    assert '关联已入库课程' in response.json()['detail']
