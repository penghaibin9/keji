from datetime import date
import pytest
from sqlalchemy import select
from conftest import auth, post
from app.social_models import SocialClaim
from app.reference_data import TeacherCourseTerm
from app import social_training as st
from test_applications import act
from test_social_training import setup_social, row, import_rows, close_project, policy, proof, action, detail


def approve_manual_course(c):
    auth(c,'teacher')
    r=post(c,'/api/applications/courses',{'data':{'source':'manual','code':'FLOW-C1','name':'自建课程完整流程',
        'hours':32,'teaching_mode':'practice','ideology':'course_ideology','audience':'社区居民',
        'courseware':{'checked':True,'reviewer':'合成课件审查人','reviewed_on':'2026-09-01'}},'reason':'隔离课程申报'})
    assert r.status_code==200,r.text
    ident=r.json()['item']['id']
    for user in ('depthead','collegehead','reviewer'):
        auth(c,user);r=act(c,ident,'approve');assert r.status_code==200,r.text
    assert r.json()['item']['state']=='ACTIVE'
    auth(c,'teacher')
    return ident


def progress(c,ident):
    r=c.get('/api/applications/'+ident+'/course-points');assert r.status_code==200,r.text
    return r.json()


def test_shared_course_uses_participating_teacher_without_exposing_application(setup_social,client2,app2,monkeypatch):
    from app.models import User
    from support import HASH
    with app2.state.sessions.begin() as db:
        for ident,staff in [('sharedteacher','J003'),('unrelatedteacher','J004')]:
            db.add(User(id=ident,username=ident,name=ident,staff_no=staff,org_id='dept1',role_id='role-teacher',
                        password_hash=HASH,must_change_password=False))
    c=client2;pid=setup_social;ident=approve_manual_course(c)
    project=detail(c,'social_project',pid)['item']
    assert post(c,'/api/social/projects/'+pid+'/courses/link',{'course_code':'FLOW-C1','expected_version':project['version'],'reason':'共用课程'}).status_code==200
    auth(c,'reviewer');unit=row();unit['teachers'].append({'teacher_id':'sharedteacher','staff_type':'internal','role':'lecturer'})
    assert import_rows(c,pid,[unit]).status_code==200
    close_project(c,pid);pol=policy(c,True);monkeypatch.setattr(st,'today',lambda:date(2026,9,3))
    auth(c,'teacher')
    owner_claim=post(c,'/api/social/claims',{'project_id':pid,'period_id':'period2026','policy_id':pol,
        'recognition_form_reference':'课程申报人材料','reason':'本人申报'})
    assert owner_claim.status_code==200,owner_claim.text
    assert progress(c,ident)['can_read_application']
    auth(c,'sharedteacher')
    assert 'FLOW-C1' in [x['code'] for x in c.get('/api/social/workspace?section=courses').json()['courses']]
    p=progress(c,ident)
    assert p['applicant']['id']=='sharedteacher' and p['stage']=='ready' and p['can_claim']
    assert p['claim'] is None and not p['can_link'] and not p['can_read_application']
    assert c.get('/api/applications/'+ident).status_code==403
    assert c.get('/api/social/objects/social_resource/'+ident).status_code==403
    assert post(c,'/api/social/projects/'+pid+'/courses/link',{'course_code':'FLOW-C1','expected_version':1,'reason':'不得改挂他人课程'}).status_code==403
    own_claim=post(c,'/api/social/claims',{'project_id':pid,'period_id':p['period_id'],'policy_id':p['policy_id'],
        'recognition_form_reference':'实际参训教师材料','reason':'本人申报'})
    assert own_claim.status_code==200,own_claim.text
    assert own_claim.json()['item']['id']!=owner_claim.json()['item']['id']
    assert progress(c,ident)['claim']['id']==own_claim.json()['item']['id']
    for user in ('unrelatedteacher','otherteacher'):
        auth(c,user);assert c.get('/api/applications/'+ident+'/course-points').status_code==403


def test_manual_course_approval_link_work_close_claim_and_archive(setup_social,client2,app2,monkeypatch):
    c=client2;pid=setup_social;monkeypatch.setattr(st,'today',lambda:date(2026,9,3))
    ident=approve_manual_course(c)
    assert progress(c,ident)['stage']=='link'
    project=detail(c,'social_project',pid)['item']
    r=post(c,'/api/social/projects/'+pid+'/courses/link',{'course_code':'FLOW-C1','expected_version':project['version'],'reason':'本人课程用于本人项目'})
    assert r.status_code==200,r.text
    assert progress(c,ident)['stage']=='work'
    auth(c,'reviewer');unit=row();unit['course_code']='FLOW-C1';unit['class_code']='FLOW-CL1'
    assert import_rows(c,pid,[unit]).status_code==200
    auth(c,'teacher');assert progress(c,ident)['stage']=='close'
    auth(c,'reviewer');close_project(c,pid)
    auth(c,'teacher');assert progress(c,ident)['stage']=='policy'
    pol=policy(c,True);auth(c,'teacher');p=progress(c,ident)
    assert p['stage']=='ready' and p['can_claim'] and p['period_id']=='period2026' and p['policy_id']==pol
    r=post(c,'/api/social/claims',{'project_id':pid,'period_id':p['period_id'],'policy_id':p['policy_id'],
        'recognition_form_reference':'合成认定表','reason':'从自建课程申请本人积分'})
    assert r.status_code==200,r.text
    claim=r.json()['item'];p=progress(c,ident)
    assert p['stage']=='claim' and p['claim']['id']==claim['id'] and not p['can_claim']
    duplicate=post(c,'/api/social/claims',{'project_id':pid,'period_id':p['claim'].get('period_id','period2026'),'policy_id':pol,
        'recognition_form_reference':'重复课程入口','reason':'重复建草稿检查'})
    assert duplicate.status_code==409 and '已有本人积分申请' in duplicate.json()['detail']
    proof(c,'social_claim',claim['id'],claim['version']);assert action(c,'claims','social_claim',claim['id'],'submit').status_code==200
    for user in ('collegehead','reviewer','vice','depthead'):
        auth(c,user);r=action(c,'claims','social_claim',claim['id'],'approve');assert r.status_code==200,r.text
    auth(c,'teacher');p=progress(c,ident)
    assert p['label']=='已认定积分' and p['steps'][-1]['done'] and p['claim']['id']==claim['id']
    assert p['responsible']=='已归档入账，无需继续办理' and not p['project']['can_manage']
    with app2.state.sessions() as db:assert len(db.scalars(select(SocialClaim).where(SocialClaim.project_id==pid,SocialClaim.teacher_id=='teacher')).all())==1


def test_manager_cannot_claim_for_applicant_and_expired_deadline_is_explained(setup_social,client2,app2,monkeypatch):
    c=client2;pid=setup_social;ident=approve_manual_course(c)
    project=detail(c,'social_project',pid)['item']
    assert post(c,'/api/social/projects/'+pid+'/courses/link',{'course_code':'FLOW-C1','expected_version':project['version'],'reason':'隔离关联'}).status_code==200
    auth(c,'reviewer');assert import_rows(c,pid,[row()]).status_code==200;close_project(c,pid);policy(c,True)
    monkeypatch.setattr(st,'today',lambda:date(2026,9,3));auth(c,'collegehead')
    p=progress(c,ident);assert p['stage']=='ready' and not p['can_claim']
    auth(c,'teacher');monkeypatch.setattr(st,'today',lambda:date(2026,12,31))
    p=progress(c,ident);assert p['stage']=='deadline' and not p['can_claim'] and '15个工作日' in p['message']


@pytest.mark.parametrize('origin',['JW','CX'])
def test_imported_course_approval_enters_same_points_flow(setup_social,client2,app2,origin,monkeypatch):
    from app import applications as apps
    monkeypatch.setattr(apps,'school_today',lambda:date(2026,10,19))
    with app2.state.sessions.begin() as db:
        db.add(TeacherCourseTerm(id='flow-term-'+origin,external_key='flow-'+origin,origin=origin,staff_no='J001',
            teacher_name='测试教师一',course_code='FLOW-SOURCE-'+origin,course_name='合成来源课程'+origin,
            term_name='2026-1',credit=2,hours=2,source='合成来源验收',extra={}))
    c=client2;auth(c,'teacher')
    r=post(c,'/api/applications/courses',{'data':{'source':'teaching','course_term_id':'flow-term-'+origin,
        'teaching_mode':'lecture','ideology':'course_ideology','audience':'社区居民',
        'courseware':{'checked':True,'reviewer':'合成审核人','reviewed_on':'2026-10-19'}},'reason':'合成来源统一流程检查'})
    assert r.status_code==200,r.text
    ident=r.json()['item']['id']
    for user in ('depthead','collegehead','reviewer'):
        auth(c,user);r=act(c,ident,'approve');assert r.status_code==200,r.text
    auth(c,'teacher');p=progress(c,ident)
    assert p['stage']=='link' and p['can_link'] and p['application_id']==ident
    course=next(x for x in c.get('/api/applications/teaching-courses').json()['courses'] if x['origin']==origin)
    assert course['application']['id']==ident and course['application']['state']=='ACTIVE'
