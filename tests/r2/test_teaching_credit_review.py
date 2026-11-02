"""授课认定三级：教务、超星拉来的课先到教研室审核，再到学院审批，最后学校认定。

每门课按学时算建议积分（1 学时 1 分），每一级都能改积分，改了必须写审批意见；学校看得到前面谁通过、
积分怎么改、意见是什么。学校认定后积分记入老师个人积分（授课认定），课程进入老师的培训课程库。
教研室缺负责人交学院、学院缺院长交学校；本人的课回避。学分学时在源头变了，从教研室重新审，已入账积分冲销。
"""
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import Audit,Period,PointEntry,Role,User
from app.permissions import TEACHER
from app.reference_data import TeacherHrProfile
from conftest import auth,post,put
from test_procurement_inbound_rollback import REASON,inbound
from test_r4_internal_closeout import configure_middle
from test_teacher_course_inbound import typed

URL='/api/reference/teacher-credits'
MAPS=(typed('school_course',{'KCH':'code','KCMC':'name','XF':'credit','ZXS':'hours','VERSION':'course_version'},{'code','name'})
    +typed('teacher_course',{'ZGH':'staff_no','XM':'teacher_name','KCH':'course_code','KCMC':'course_name','XQMC':'term_name'},{'staff_no','course_code','course_name','term_name'})
    +typed('online_course',{'creater_login_name':'staff_no','teachername':'teacher_name','courseid':'course_code','coursename':'course_name','xn':'school_year','xq':'term_no','credit':'credit','courseIdentifier':'jw_course_code'},{'staff_no','course_code','course_name'}))
CATALOGUE=[{'KCH':'K1','KCMC':'高等数学','XF':'4','ZXS':'64','VERSION':'2023'},{'KCH':'K2','KCMC':'线性代数','XF':'2','ZXS':'32','VERSION':'2023'}]


def setup(c,app2):
    auth(c,'schooladmin');conn=configure_middle(c,MAPS)
    inbound(c,conn,'school_course',CATALOGUE)
    inbound(c,conn,'teacher_course',[
        {'ZGH':'J001','XM':'测试教师一','KCH':'K1','KCMC':'高等数学','XQMC':'2025-2026学年第二学期'},   # 2026-03-01，落在 2026 周期
        {'ZGH':'J001','XM':'测试教师一','KCH':'K2','KCMC':'线性代数','XQMC':'2026-2027学年第一学期'},   # 2026-09-01
        {'ZGH':'J002','XM':'测试教师二','KCH':'K1','KCMC':'高等数学','XQMC':'2025-2026学年第二学期'},   # 另一个教研室
        {'ZGH':'T9001','XM':'未建账号','KCH':'K1','KCMC':'高等数学','XQMC':'2025-2026学年第二学期'},   # 没有本地账号
        {'ZGH':'J900','XM':'教务处老师','KCH':'K2','KCMC':'线性代数','XQMC':'2025-2026学年第二学期'}])  # 认定人本人也上课
    # 超星课挂了教务课号 K1，同学年已有教务 K1，按规则只算一次，不用认定。
    inbound(c,conn,'online_course',[{'creater_login_name':'J001','teachername':'测试教师一','courseid':'X1','coursename':'高数线上版','xn':'2025','xq':'2','credit':'4','courseIdentifier':'K1'}])
    with Session(app2.state.engine) as db:
        db.add(TeacherHrProfile(staff_no='J001',user_id='teacher',name='测试教师一',org_code='dept1'))
        # 教务处：学校层级、不是系统管理员，只多一个“考核审核”权限。
        db.add(Role(id='role-jwc',code='jwc',name='教务处审核',kind='school',permissions=sorted(TEACHER|{'assessment.review'})))
        db.add(User(id='jwc',username='jwc',name='教务处测试账号',staff_no='J900',org_id='school',role_id='role-jwc',
            password_hash=db.get(User,'teacher').password_hash,is_admin=False,must_change_password=False))
        db.commit()
    return conn


def credits(c,staff,**kw):
    r=c.get(URL,params={'staff_no':staff,'detail':'true',**kw});assert r.status_code==200,r.text
    return {x['school_year']:x for x in r.json()['items']}


def course(year,code,origin='JW'):
    return next(d for d in year['details'] if d['course_code']==code and d['origin']==origin)


def review(c,ids,decision,reason='',**kw):
    return post(c,URL+'/review',{'ids':ids,'decision':decision,'reason':reason,**kw})


def one(c,cid,decision,points=None,reason='',**kw):
    return post(c,URL+'/review',{'items':[{'id':cid,'points':points,'reason':reason}],'decision':decision,**kw})


def teaching_points(app2,teacher='teacher'):
    with Session(app2.state.engine) as db:
        return sum((Decimal(str(e.amount)) for e in db.scalars(select(PointEntry).where(PointEntry.teacher_id==teacher,PointEntry.kind=='TEACHING'))),Decimal('0'))


def mine(c):
    r=c.get(URL,params={'review':'mine'});assert r.status_code==200,r.text
    return {(x['staff_no'],x['school_year']):x['mine_courses'] for x in r.json()['items']}


def test_three_levels_edit_points_and_school_sees_who_approved(client2,app2):
    c=client2;setup(c,app2)
    # 1. 老师本人：两门课都在教研室，按学时算建议积分（K1 64 学时 → 64 分）。
    auth(c,'teacher')
    years=credits(c,'J001');k1=course(years['2025-2026'],'K1')
    assert (k1['review'],k1['stage'],k1['handler'],k1['suggested_points'],k1['points'])==('pending','dept','dept','64.00','64.00')
    assert course(years['2025-2026'],'X1','CX')['counted'] is False   # 重复课不用认定
    assert review(c,[k1['id']],'approve').status_code==403
    # 学院、学校都不能越级办教研室这一级。
    for user in ('collegehead','jwc','otherdept'):
        auth(c,user);assert review(c,[k1['id']],'approve').status_code==403,user
    # 2. 教研室负责人：待我办理里有本教研室老师；改了积分必须写意见。
    auth(c,'depthead')
    assert mine(c)=={('J001','2025-2026'):1,('J001','2026-2027'):1}
    r=one(c,k1['id'],'approve',points='60');assert r.status_code==422 and '审批意见' in r.json()['detail'],r.text
    assert one(c,k1['id'],'approve',points='60',reason='实际授课 60 学时').status_code==200
    assert review(c,[k1['id']],'approve').status_code==403   # 已到学院
    k1=course(credits(c,'J001')['2025-2026'],'K1')
    assert (k1['stage'],k1['points'],k1['suggested_points'])==('college','60.00','64.00')
    # 3. 学院负责人：不改积分可以不写意见。
    auth(c,'collegehead')
    assert mine(c)=={('J001','2025-2026'):1}
    assert review(c,[k1['id']],'approve').status_code==200
    # 4. 学校：看得到前面两级谁通过、积分怎么改、意见是什么。
    auth(c,'jwc')
    assert mine(c)=={('J001','2025-2026'):1}
    d=c.get(URL+'/course/'+k1['id']).json()
    steps=d['course']['steps']
    assert [(x['level'],x['decision'],x['by_name'],x.get('points_before'),x.get('points_after'),x.get('reason')) for x in steps]==[
        ('dept','approve','测试教研室负责人','64.00','60.00','实际授课 60 学时'),('college','approve','测试学院负责人','60.00','60.00',None)]
    assert d['course']['can_act'] is True and d['content']['course_code']=='K1'
    assert {x['label']:x['ok'] for x in d['conditions']}=={'在学校教职工表里':True,'有本地教师账号':True,'有学时':True,'有学分':True,'不是重复课':True,'不是本人的课':True}
    r=review(c,[k1['id']],'approve','三级核对一致');assert r.status_code==200,r.text
    # 5. 认定后积分入账（不用关联培训项目），课程进入老师的培训课程库。
    assert teaching_points(app2)==Decimal('60')
    k1=course(credits(c,'J001')['2025-2026'],'K1')
    assert k1['review']=='approved' and k1['points']=='60.00' and k1['booked']['period_id']=='period2026'
    auth(c,'teacher')
    lib=c.get(URL+'/library').json()['items']
    assert [(x['course_code'],x['points'],x['approved_by']) for x in lib]==[('K1','60.00','教务处测试账号')]
    # 6. 学校改回重审：冲销积分，从教研室重新开始；只有学校能改回。
    auth(c,'depthead');assert review(c,[k1['id']],'reset','重新核对').status_code==403
    auth(c,'jwc')
    assert review(c,[k1['id']],'reset').status_code==422
    assert review(c,[k1['id']],'reset','学时有误，重新核对').status_code==200
    assert teaching_points(app2)==Decimal('0')
    k1=course(credits(c,'J001')['2025-2026'],'K1')
    assert (k1['review'],k1['stage'],k1['steps'])==('pending','dept',[])
    with Session(app2.state.engine) as db:
        actions=[a.action for a in db.scalars(select(Audit).where(Audit.module=='teacher_course',Audit.action.startswith('授课认定')).order_by(Audit.created_at))]
    assert actions==['授课认定：教研室通过','授课认定：学院通过','授课认定：认定计分','授课认定：改回重审']


def test_exclude_and_school_returns_to_lower_level(client2,app2):
    c=client2;setup(c,app2)
    auth(c,'depthead')
    k2=course(credits(c,'J001')['2026-2027'],'K2')
    assert review(c,[k2['id']],'exclude').status_code==422   # 不计分要写原因
    assert review(c,[k2['id']],'approve').status_code==200
    auth(c,'collegehead');assert review(c,[k2['id']],'approve').status_code==200
    # 学校退回教研室，必须写原因；从教研室重新审，退回记录留在办理记录里。
    auth(c,'jwc')
    assert review(c,[k2['id']],'return','',return_to='dept').status_code==422
    assert review(c,[k2['id']],'return','请核对是否代课').status_code==422   # 没选退回哪一级
    assert review(c,[k2['id']],'return','请核对是否代课',return_to='dept').status_code==200
    auth(c,'depthead')
    k2=course(credits(c,'J001')['2026-2027'],'K2')
    assert k2['stage']=='dept' and [x['decision'] for x in k2['steps']]==['approve','approve','return']
    assert review(c,[k2['id']],'exclude','该课为代课，按规定不计').status_code==200
    # 老师看到不计分和原因；不计分不入账。
    auth(c,'teacher')
    k2=course(credits(c,'J001')['2026-2027'],'K2')
    assert k2['review']=='excluded' and k2['review_reason']=='该课为代课，按规定不计' and k2['reviewed_by']=='测试教研室负责人'
    assert teaching_points(app2)==Decimal('0')
    # 已办结的课不能再审，要学校先改回。
    auth(c,'collegehead');assert review(c,[k2['id']],'approve').status_code==409


def test_vacant_levels_unmapped_staff_recusal_and_missing_hours(client2,app2):
    c=client2;conn=setup(c,app2)
    # 测试学院二没有院长：教研室二通过后直接到学校。
    auth(c,'otherdept')
    j2=course(credits(c,'J002')['2025-2026'],'K1')
    assert review(c,[j2['id']],'approve').status_code==200
    auth(c,'jwc')
    j2=course(credits(c,'J002')['2025-2026'],'K1')
    assert (j2['stage'],j2['handler'],j2['acting_for'])==('college','school','代缺位学院负责人办理')
    assert mine(c)=={('J002','2025-2026'):1}
    assert review(c,[j2['id']],'approve').status_code==200
    assert teaching_points(app2,'otherteacher')==Decimal('64')
    # 没有本地账号的工号直接到学校，教研室不能办。
    row=course(credits(c,'T9001')['2025-2026'],'K1')
    assert row['stage']=='school'
    auth(c,'depthead');assert review(c,[row['id']],'approve').status_code==403
    auth(c,'jwc');assert review(c,[row['id']],'approve','人事核对后认定').status_code==200
    assert course(credits(c,'T9001')['2025-2026'],'K1')['booked']['booked'] is False
    # 学校账号自己的课须回避，由其他授课认定人认定。
    own=course(credits(c,'J900')['2025-2026'],'K2')
    r=review(c,[own['id']],'approve');assert r.status_code==403 and '回避' in r.json()['detail'],r.text
    auth(c,'schooladmin');assert review(c,[own['id']],'approve','学校核对').status_code==200
    # 缺学时（课程总库没有这门课）：算不出建议积分，须手工填。
    inbound(c,conn,'teacher_course',[{'ZGH':'J001','XM':'测试教师一','KCH':'K9','KCMC':'缺学时课','XQMC':'2025-2026学年第二学期'}])
    auth(c,'depthead')
    k9=course(credits(c,'J001')['2025-2026'],'K9')
    assert k9['suggested_points'] is None
    r=review(c,[k9['id']],'approve');assert r.status_code==409 and '缺学时' in r.json()['detail'],r.text
    assert one(c,k9['id'],'approve',points='16').status_code==200
    # 不存在的课整批拒绝。
    k2=course(credits(c,'J001')['2026-2027'],'K2')
    assert review(c,[k2['id'],'no-such-row'],'approve').status_code==409
    assert course(credits(c,'J001')['2026-2027'],'K2')['stage']=='dept'


def test_todos_follow_the_course_up_the_chain(client2,app2):
    c=client2;setup(c,app2)
    def todos(user):
        auth(c,user);return {x['id'] for x in c.get('/api/todos',params={'type':'credit_review'}).json()['items']}
    assert todos('depthead')=={'J001~2025-2026','J001~2026-2027'}
    assert todos('otherdept')=={'J002~2025-2026'}
    assert todos('collegehead')==set() and todos('jwc')==set() and todos('teacher')==set()
    auth(c,'depthead')
    y=credits(c,'J001');ids=[d['id'] for g in y.values() for d in g['details'] if d['review']=='pending']
    assert review(c,ids,'approve').json()['updated']==2   # 批量通过，按各自当前积分
    assert todos('depthead')==set() and todos('collegehead')=={'J001~2025-2026','J001~2026-2027'}
    assert all(t['title'].startswith('授课认定：') for t in c.get('/api/todos',params={'type':'credit_review'}).json()['items'])


def test_repull_restarts_from_dept_and_reverses_booked_points(client2,app2):
    c=client2;conn=setup(c,app2)
    for user in ('depthead','collegehead','jwc'):
        auth(c,user);k1=course(credits(c,'J001')['2025-2026'],'K1');assert review(c,[k1['id']],'approve').status_code==200,user
    assert teaching_points(app2)==Decimal('64')
    # 学校另设了一条考核规则重算积分：授课认定积分不被当成规则项冲掉。
    from test_api import activate
    auth(c,'schooladmin')
    r=post(c,'/api/rules',{'kind':'points','name':'培训学时积分','period_id':'period2026','config':{'components':[{'key':'h','label':'培训学时','source':'hours','factor':'1','weight':'0','target':'1','cap':None}]},**REASON})
    assert r.status_code==200,r.text;assert activate(c,r.json()).status_code==200
    assert post(c,'/api/points/calculate',{'period_id':'period2026','teacher_ids':['teacher'],**REASON}).status_code==200
    assert teaching_points(app2)==Decimal('64')
    # 课程总库里 K1 学时改了：回到教研室，下次办理时冲销旧积分。
    inbound(c,conn,'school_course',[{**CATALOGUE[0],'ZXS':'48'},CATALOGUE[1]])
    auth(c,'depthead')
    k1=course(credits(c,'J001')['2025-2026'],'K1')
    assert (k1['review'],k1['stage'],k1['review_stale'],k1['suggested_points'])==('pending','dept',True,'48.00')
    assert review(c,[k1['id']],'approve').status_code==200
    assert teaching_points(app2)==Decimal('0')
    history=c.get(URL+'/course/'+k1['id']).json()['history']
    assert [x['decision'] for x in history]==['approve','approve','approve','restart','approve']


def test_school_admin_sets_points_per_hour(client2,app2):
    c=client2;setup(c,app2)
    auth(c,'depthead')
    assert c.get(URL+'/points-rule').json()=={'JW':'1','CX':'1'}
    assert put(c,URL+'/points-rule',{'JW':'2','CX':'1'}).status_code==403
    auth(c,'schooladmin')
    assert put(c,URL+'/points-rule',{'JW':'2','CX':'1','reason':'学校规定'}).status_code==200
    assert course(credits(c,'J001')['2025-2026'],'K1')['suggested_points']=='128.00'


def test_admin_designates_teacher_as_reviewer_without_changing_role(client2,app2):
    """组织页学校那一行设“授课认定人”：普通教师（如皮老师）不用改角色，就能办学校这一级。"""
    c=client2;setup(c,app2)
    auth(c,'jwc');assert post(c,'/api/credit-reviewers',{'user_id':'otherteacher',**REASON}).status_code==403
    auth(c,'schooladmin')
    school=next(o for o in c.get('/api/organizations').json()['items'] if o['kind']=='school')
    assert school['credit_reviewers']==[]
    found=c.get('/api/credit-reviewers/candidates',params={'q':'J002'}).json()['items']
    assert [u['id'] for u in found]==['otherteacher']
    r=post(c,'/api/credit-reviewers',{'user_id':'otherteacher',**REASON});assert r.status_code==200,r.text
    assert post(c,'/api/credit-reviewers',{'user_id':'otherteacher',**REASON}).status_code==409
    with Session(app2.state.engine) as db:
        assert db.get(User,'otherteacher').role_id=='role-teacher'
        assert db.scalar(select(Audit).where(Audit.module=='credit_reviewer',Audit.action=='设置授课认定人')) is not None
    auth(c,'otherteacher')
    me=c.get('/api/auth/me').json();assert me['credit_reviewer'] is True and me['role']['kind']=='teacher'
    listed=c.get(URL,params={'review':'pending'}).json()
    assert {x['staff_no'] for x in listed['items']}=={'J001','J002','T9001','J900'}
    # 课还在教研室时认定人不能越级；到学校后能认定，本人的课回避。
    k1=course(credits(c,'J001')['2025-2026'],'K1')
    assert review(c,[k1['id']],'approve').status_code==403
    for user in ('depthead','collegehead'):
        auth(c,user);assert review(c,[k1['id']],'approve').status_code==200
    auth(c,'otherteacher')
    assert {x['id'] for x in c.get('/api/todos',params={'type':'credit_review'}).json()['items']}=={'J001~2025-2026'}
    assert review(c,[k1['id']],'approve','已核对排课').status_code==200
    row=course(credits(c,'T9001')['2025-2026'],'K1')
    assert review(c,[row['id']],'approve','人事核对后认定').status_code==200
    auth(c,'otherdept');own=course(credits(c,'J002')['2025-2026'],'K1');assert review(c,[own['id']],'approve').status_code==200
    auth(c,'otherteacher')
    r=review(c,[own['id']],'approve');assert r.status_code==403 and '回避' in r.json()['detail'],r.text
    auth(c,'teacher')
    assert c.get('/api/auth/me').json()['credit_reviewer'] is False
    assert {x['staff_no'] for x in c.get(URL).json()['items']}=={'J001'}
    auth(c,'schooladmin')
    assert post(c,'/api/credit-reviewers/remove',{'user_id':'otherteacher',**REASON}).status_code==200
    assert post(c,'/api/credit-reviewers/remove',{'user_id':'otherteacher',**REASON}).status_code==404
    auth(c,'otherteacher')
    assert c.get('/api/auth/me').json()['credit_reviewer'] is False
    assert c.get('/api/todos',params={'type':'credit_review'}).json()['total']==0


def test_course_level_tags_follow_the_course(client2,app2):
    """授课认定菜单里给课打国家级、省级、校级标签：跟着课程走，同一门课所有老师一起显示。"""
    c=client2;setup(c,app2)
    auth(c,'teacher')
    k1=course(credits(c,'J001')['2025-2026'],'K1')
    assert k1['level'] is None
    r=post(c,URL+'/level',{'ids':[k1['id']],'level':'province'});assert r.status_code==403   # 老师不能打标签
    auth(c,'depthead');assert post(c,URL+'/level',{'ids':[k1['id']],'level':'province'}).status_code==403
    auth(c,'jwc')
    r=post(c,URL+'/level',{'ids':[k1['id']],'level':'province'});assert r.status_code==200,r.text
    assert r.json()=={'updated':1,'level':'province'}
    assert post(c,URL+'/level',{'ids':[k1['id']],'level':'province'}).json()['updated']==0   # 重复设置不重复记
    assert post(c,URL+'/level',{'ids':[k1['id']],'level':'bogus'}).status_code==422
    # 同一门教务课 K1，另一位老师那里也显示省级；超星课 X1 不受影响。
    assert course(credits(c,'J002')['2025-2026'],'K1')['level']=='province'
    assert course(credits(c,'J001')['2025-2026'],'X1','CX')['level'] is None
    auth(c,'teacher');assert course(credits(c,'J001')['2025-2026'],'K1')['level']=='province'
    auth(c,'jwc')
    assert post(c,URL+'/level',{'ids':[k1['id']],'level':''}).json()['updated']==1
    assert course(credits(c,'J001')['2025-2026'],'K1')['level'] is None
    with Session(app2.state.engine) as db:
        actions=[a.action for a in db.scalars(select(Audit).where(Audit.module=='teacher_course',Audit.action.startswith('课程级别')).order_by(Audit.created_at))]
    assert actions==['课程级别：省级','课程级别：清除级别']
