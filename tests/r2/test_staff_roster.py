"""教职工名册: unit handling on HR inbound, role scope, privacy, this year's credits and problems."""
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import User,Setting
from app.reference_data import TeacherHrProfile,school_year_now
from conftest import auth
from test_procurement_inbound_rollback import inbound
from test_r4_internal_closeout import configure_middle
from test_teacher_course_inbound import typed

def hr_maps():
    m=typed('teacher_hr',{'ZGH':'staff_no','XM':'name','ZCMC':'title','SZDWDM':'org_code','SZDWMC':'org_name',
        'XLM':'edu','XBM':'gender','JZGLBM':'staff_type','ZWMC':'duty'},{'staff_no','name','org_code'})
    m.append({'source':'ZT','target':'active','transform':'bool','required':True,'default':True,'data_type':'teacher_hr'})
    return m+typed('teacher_course',{'ZGH':'staff_no','XM':'teacher_name','KCH':'course_code','KCMC':'course_name','XQMC':'term_name'},
        {'staff_no','course_code','course_name','term_name'})

def seed(c,mismatch=False):
    auth(c,'schooladmin');conn=configure_middle(c,hr_maps())
    inbound(c,conn,'teacher_hr',[
        # J001 sits in dept1 (college1) locally; HR names its unit by a code we do not have, but the same name as college2.
        {'ZGH':'J001','XM':'测试教师一','ZCMC':'副教授','SZDWDM':'HR-0302','SZDWMC':'测试学院二' if mismatch else '测试学院一','XLM':'14','XBM':'2','JZGLBM':'11','ZWMC':'教研室副主任','ZT':True},
        # J002 sits in dept2 (college2); HR unit is college2 by code: consistent.
        {'ZGH':'J002','XM':'测试教师二','ZCMC':'讲师','SZDWDM':'college2','SZDWMC':'测试学院二','XLM':'21','XBM':'1','JZGLBM':'11','ZT':True},
        # No local account yet; unit unknown to this system.
        {'ZGH':'T7788','XM':'未建账号教师','ZCMC':'助教','SZDWDM':'HR-9999','SZDWMC':'后勤服务中心','ZT':False}])
    year=school_year_now()
    inbound(c,conn,'teacher_course',[
        {'ZGH':'J001','XM':'测试教师一','KCH':'K404','KCMC':'没有学分的课','XQMC':year+'学年第一学期'},
        {'ZGH':'T7788','XM':'未建账号教师','KCH':'K405','KCMC':'也没有学分','XQMC':year+'-2'}])
    return year

def roster(c,user,**params):
    auth(c,user);r=c.get('/api/reference/staff-roster',params=params);assert r.status_code==200,r.text
    return r.json()

def test_hr_units_that_are_not_teaching_groups_are_kept_without_moving_accounts(client2,app2):
    seed(client2,mismatch=True)
    with Session(app2.state.engine) as db:
        assert {p.staff_no for p in db.scalars(select(TeacherHrProfile))}=={'J001','J002','T7788'}
        assert db.scalar(select(User.org_id).where(User.staff_no=='J001'))=='dept1'
        assert db.scalar(select(User.org_id).where(User.staff_no=='J002'))=='dept2'
        assert db.scalar(select(TeacherHrProfile).where(TeacherHrProfile.staff_no=='J001')).extra['org_name']=='测试学院二'

def test_roster_scope_privacy_and_problems(client2,app2):
    year=seed(client2);c=client2
    school=roster(c,'schooladmin')
    rows={r['staff_no']:r for r in school['items']}
    assert school['total']==3 and school['school_year']==year and school['private_fields'] is True
    assert rows['J001']['org_name']=='测试教研室一' and rows['J001']['college_name']=='测试学院一'
    assert set(rows['J001']['problems'])=={'missing_credit'} and rows['J001']['missing_credit']==['K404']
    assert rows['J002']['problems']==[] and rows['J002']['edu']=='21'
    assert rows['T7788']['problems']==['no_account','inactive_teaching','missing_credit'] and rows['T7788']['hr_org_name']=='后勤服务中心'
    assert [r['staff_no'] for r in roster(c,'schooladmin',problem='true')['items']]==['J001','T7788']
    dept=roster(c,'depthead')
    assert [r['staff_no'] for r in dept['items']]==['J001'] and dept['private_fields'] is False and 'edu' not in dept['items'][0]
    assert [r['staff_no'] for r in roster(c,'collegehead')['items']]==['J001']
    mine=roster(c,'teacher')
    assert [r['staff_no'] for r in mine['items']]==['J001'] and mine['items'][0]['gender']=='2'

def test_managers_see_education_only_when_school_allows(client2,app2):
    seed(client2)
    with Session(app2.state.engine) as db:
        db.add(Setting(key='param:hr_managers_see_education',value={'name':'教研室学院可看学历学位','type':'bool','value':True}));db.commit()
    dept=roster(client2,'depthead')
    assert dept['private_fields'] is True and dept['items'][0]['edu']=='14'

def test_detail_is_scoped(client2,app2):
    seed(client2);c=client2
    auth(c,'depthead')
    assert c.get('/api/reference/staff-roster/J002').status_code==404
    assert c.get('/api/reference/staff-roster/T7788').status_code==404
    r=c.get('/api/reference/staff-roster/J001');assert r.status_code==200,r.text
    body=r.json();assert body['staff']['staff_no']=='J001' and body['years'][0]['missing_credit']==['K404']
    auth(c,'schooladmin');assert c.get('/api/reference/staff-roster/T7788').status_code==200
    assert c.get('/api/reference/staff-roster',params={'school_year':'2025'}).status_code==422

def test_detail_returns_every_mapped_chaoxing_field(client2,app2):
    seed(client2);c=client2
    from app.reference_data import TeacherCourseTerm
    extra={'cover_url':'https://p.ananas.chaoxing.com/c.png','course_url':'https://mooc1.chaoxing.com/course/1.html','group_name':'公共课',
        'chapters':'12','course_type':'1','course_source':'2','archived':'0','team_names':'测试教师一,测试教师二','team_staff_nos':'J001,J002',
        'jw_course_code':'K404','nature':'01','course_owner':'J001','major':'计算机','score':'2.5','period_text':'64/32',
        'created_at_source':'2025-03-01 08:00:00','edited_at_source':'2025-06-01 09:30:00','description':'简介'*1500}
    with Session(app2.state.engine) as db:
        db.add(TeacherCourseTerm(external_key='CX-1',staff_no='J001',user_id='teacher',term_name='2025-2',course_code='CX1',
            course_name='超星课',origin='CX',teacher_name='测试教师一',extra=extra));db.commit()
    auth(c,'schooladmin');r=c.get('/api/reference/staff-roster/J001');assert r.status_code==200,r.text
    o=r.json()['online_courses'][0]
    assert {k:o[k] for k in extra if k!='description'}=={k:v for k,v in extra.items() if k!='description'}
    assert len(o['description'])==2000 and o['credit'] is None
    # 超星封面图来自 *.chaoxing.com，页面安全策略只额外放行这一个图片来源。
    assert "img-src 'self' data: https://*.chaoxing.com;" in r.headers['content-security-policy']
