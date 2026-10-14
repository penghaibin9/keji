"""授课认定：教务、超星拉来的课先待认定，学校（教务处等学校层面账号）认定后才计学分学时和积分。

走通整个流程：老师看到待认定 → 教务处认定 / 不计分 → 计入积分 → 重新拉取后学分变了自动回到待认定。
教研室主任、学院负责人不认定；认定人自己的课须回避，由别的学校层面账号认定。
"""
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import Audit,Period,Role,User
from app.permissions import TEACHER
from app.reference_data import TeacherHrProfile
from conftest import auth,post
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


def review(c,ids,decision,reason=''):
    return post(c,URL+'/review',{'ids':ids,'decision':decision,'reason':reason})


def points(c,app2):
    from test_api import activate
    r=post(c,'/api/rules',{'kind':'points','name':'学分积分','period_id':'period2026','config':{'components':[{'key':'credits','label':'授课学分','source':'credits','factor':'2','weight':'0','target':'1','cap':None}]},**REASON})
    assert r.status_code==200,r.text;assert activate(c,r.json()).status_code==200


def calculate(c):
    r=post(c,'/api/points/calculate',{'period_id':'period2026','teacher_ids':['teacher'],**REASON});assert r.status_code==200,r.text
    return c.get('/api/points?teacher_id=teacher').json()['sum']


def test_teacher_sees_pending_and_school_approves_or_excludes(client2,app2):
    c=client2;setup(c,app2)
    # 1. 老师本人：两门课都待认定，学分 0，待认定 6 学分。
    auth(c,'teacher')
    years=credits(c,'J001');y1,y2=years['2025-2026'],years['2026-2027']
    assert (y1['total_credit'],y1['pending_credit'],y1['pending_courses'],y1['approved_courses'])==('0.00','4.00',1,0)
    assert (y2['total_credit'],y2['pending_credit'],y2['hours'],y2['pending_hours'])==('0.00','2.00','0.00','32.00')
    k1,k2=course(y1,'K1'),course(y2,'K2')
    assert k1['review']=='pending' and course(y1,'X1','CX')['counted'] is False and course(y1,'X1','CX')['review'] is None
    # 老师不能自己认定；教研室主任、学院负责人也不认定。
    for user in ('teacher','depthead','collegehead'):
        auth(c,user);r=review(c,[k1['id']],'approve');assert r.status_code==403,(user,r.text)
    assert '学校' in r.json()['detail']
    # 2. 教务处（学校层级，非系统管理员）：“只看待认定”里能看到全校待认定的老师，含还没建账号的工号。
    auth(c,'jwc')
    listed=c.get(URL,params={'review':'pending'}).json()
    assert {x['staff_no'] for x in listed['items']}=={'J001','J002','T9001','J900'}
    assert c.get(URL,params={'review':'bogus'}).status_code==422
    # 重复课不用认定；不计分必须写原因。
    assert review(c,[course(y1,'X1','CX')['id']],'approve').status_code==409
    assert review(c,[k2['id']],'exclude').status_code==422
    r=review(c,[k1['id']],'approve','已核对排课');assert r.status_code==200,r.text
    assert r.json()=={'updated':1,'unchanged':0,'decision':'approve'}
    assert review(c,[k2['id']],'exclude','该课为代课，按规定不计').status_code==200
    # 再点一次同样的认定不重复记录。
    assert review(c,[k1['id']],'approve','已核对排课').json()['unchanged']==1
    # 3. 老师本人看到结果：K1 计 4 学分 64 学时，K2 不计并能看到原因和认定人。
    auth(c,'teacher')
    years=credits(c,'J001');y1,y2=years['2025-2026'],years['2026-2027']
    assert (y1['total_credit'],y1['hours'],y1['pending_courses'],y1['approved_courses'])==('4.00','64.00',0,1)
    assert (y2['total_credit'],y2['excluded_courses'],y2['pending_credit'])==('0.00',1,'0.00')
    k2=course(y2,'K2')
    assert k2['review']=='excluded' and k2['review_reason']=='该课为代课，按规定不计' and k2['reviewed_by']=='教务处测试账号'
    # 4. 每次认定都留审计记录。
    with Session(app2.state.engine) as db:
        actions=[a.action for a in db.scalars(select(Audit).where(Audit.module=='teacher_course',Audit.action.startswith('授课认定')).order_by(Audit.created_at))]
    assert actions==['授课认定：认定计分','授课认定：认定不计分']


def test_only_approved_courses_score_and_repull_resets_changed_courses(client2,app2):
    c=client2;conn=setup(c,app2)
    from app.services import facts,point_source_changes
    points(c,app2)
    # 还有待认定的课：正式计算被拦下，提示先认定（不会悄悄按 0 学分出分）。
    r=post(c,'/api/points/calculate',{'period_id':'period2026','teacher_ids':['teacher'],**REASON})
    assert r.status_code==409 and '待学校认定' in r.json()['detail'] and 'K1' in r.json()['detail'],r.text
    with Session(app2.state.engine) as db:
        raw,snap=facts(db,'teacher',db.get(Period,'period2026'))
        assert raw['credits']==Decimal('0') and {x['course_code'] for x in snap['teaching_credits']['unapproved']}=={'K1','K2'}
    auth(c,'jwc')
    y=credits(c,'J001');ids=[course(y['2025-2026'],'K1')['id'],course(y['2026-2027'],'K2')['id']]
    assert review(c,ids,'approve','本学年排课已核对').json()['updated']==2   # 批量认定
    auth(c,'schooladmin')
    assert calculate(c)=='12.00'   # (4 + 2) x 2
    # 重新拉取：课程总库里 K1 改成 5 学分 → K1 回到待认定，K2 没变仍算。
    with Session(app2.state.engine) as db:
        assert not point_source_changes(db,'teacher',db.get(Period,'period2026'))['changed']
    inbound(c,conn,'school_course',[{**CATALOGUE[0],'XF':'5'},CATALOGUE[1]])
    auth(c,'jwc')
    y=credits(c,'J001');k1=course(y['2025-2026'],'K1')
    assert k1['review']=='pending' and k1['review_stale'] is True and k1['credit']=='5.00'
    assert y['2025-2026']['total_credit']=='0.00' and y['2026-2027']['total_credit']=='2.00'
    with Session(app2.state.engine) as db:
        assert point_source_changes(db,'teacher',db.get(Period,'period2026'))['changed']
    # 按新学分再认定一次；也可以改回待认定。
    assert review(c,[k1['id']],'approve','学分已按课程总库更新').json()['updated']==1
    assert credits(c,'J001')['2025-2026']['total_credit']=='5.00'
    assert review(c,[k1['id']],'reset','认定有误，重新核对').json()['updated']==1
    assert credits(c,'J001')['2025-2026']['pending_courses']==1


def test_unmapped_staff_missing_credit_and_reviewer_recusal(client2,app2):
    c=client2;setup(c,app2)
    auth(c,'schooladmin')
    row=course(credits(c,'T9001')['2025-2026'],'K1')
    # 还没建账号的工号也由学校认定，教研室不行。
    auth(c,'depthead')
    assert review(c,[row['id']],'approve').status_code==403
    auth(c,'jwc')
    assert review(c,[row['id']],'approve','人事核对后认定').status_code==200
    assert credits(c,'T9001')['2025-2026']['total_credit']=='4.00'
    # 学校系统管理员也是学校层面，同样可以认定有账号老师的课。
    auth(c,'schooladmin')
    k1=course(credits(c,'J001')['2025-2026'],'K1')
    assert review(c,[k1['id']],'approve','学校核对').status_code==200
    # 缺学分的课不能认定计分，只能等教务补齐或认定不计分。
    conn=configure_middle(c,MAPS)
    inbound(c,conn,'teacher_course',[{'ZGH':'J001','XM':'测试教师一','KCH':'K9','KCMC':'缺学分课','XQMC':'2025-2026学年第二学期'}])
    auth(c,'jwc')
    k9=course(credits(c,'J001')['2025-2026'],'K9')
    r=review(c,[k9['id']],'approve');assert r.status_code==409 and '缺学分' in r.json()['detail'],r.text
    assert review(c,[k9['id']],'exclude','课程总库无此课，不计').status_code==200
    # 不存在的课整批拒绝，一条也不写。
    k2=course(credits(c,'J001')['2026-2027'],'K2')
    assert review(c,[k2['id'],'no-such-row'],'approve').status_code==409
    assert course(credits(c,'J001')['2026-2027'],'K2')['review']=='pending'
    # 认定人本人的课须回避，由别的学校层面账号认定。
    own=course(credits(c,'J900')['2025-2026'],'K2')
    r=review(c,[own['id']],'approve');assert r.status_code==403 and '回避' in r.json()['detail'],r.text
    auth(c,'schooladmin');assert review(c,[own['id']],'approve','学校核对').status_code==200


def test_pending_courses_show_in_school_reviewer_todos(client2,app2):
    c=client2;setup(c,app2)
    auth(c,'jwc')
    todos=c.get('/api/todos',params={'type':'credit_review'}).json()
    # 全校有账号的老师都在教务处待办里；自己（J900）的课不在，须回避。
    assert {x['id'] for x in todos['items']}=={'J001~2025-2026','J001~2026-2027','J002~2025-2026'}
    assert all(x['title'].startswith('授课认定：') for x in todos['items'])
    for user in ('teacher','depthead','otherdept','collegehead'):
        auth(c,user);assert c.get('/api/todos',params={'type':'credit_review'}).json()['total']==0,user
    auth(c,'jwc')
    y=credits(c,'J001');ids=[d['id'] for g in y.values() for d in g['details'] if d['review']=='pending']
    assert review(c,ids,'approve').status_code==200
    assert {x['id'] for x in c.get('/api/todos',params={'type':'credit_review'}).json()['items']}=={'J002~2025-2026'}


def test_admin_designates_teacher_as_reviewer_without_changing_role(client2,app2):
    """组织页学校那一行设“授课认定人”：普通教师（如皮老师）不用改角色、不用切身份，就能认定全校的课。"""
    c=client2;setup(c,app2)
    # 只有学校系统管理员能设，教务处审核账号也不行。
    auth(c,'jwc');assert post(c,'/api/credit-reviewers',{'user_id':'otherteacher',**REASON}).status_code==403
    auth(c,'schooladmin')
    school=next(o for o in c.get('/api/organizations').json()['items'] if o['kind']=='school')
    assert school['credit_reviewers']==[]
    found=c.get('/api/credit-reviewers/candidates',params={'q':'J002'}).json()['items']
    assert [u['id'] for u in found]==['otherteacher']
    r=post(c,'/api/credit-reviewers',{'user_id':'otherteacher',**REASON});assert r.status_code==200,r.text
    assert post(c,'/api/credit-reviewers',{'user_id':'otherteacher',**REASON}).status_code==409
    school=next(o for o in c.get('/api/organizations').json()['items'] if o['kind']=='school')
    assert [(x['name'],x['usable']) for x in school['credit_reviewers']]==[('测试教师二',True)]
    with Session(app2.state.engine) as db:
        assert db.get(User,'otherteacher').role_id=='role-teacher'
        assert db.scalar(select(Audit).where(Audit.module=='credit_reviewer',Audit.action=='设置授课认定人')) is not None
    # 认定人用原来的教师账号登录：/me 标出认定人，待办里有全校的授课认定（自己的课须回避）。
    auth(c,'otherteacher')
    me=c.get('/api/auth/me').json();assert me['credit_reviewer'] is True and me['role']['kind']=='teacher'
    todos=c.get('/api/todos',params={'type':'credit_review'}).json()
    assert {x['id'] for x in todos['items']}=={'J001~2025-2026','J001~2026-2027'}
    # 授课与学分里能看到全校待认定的老师，含还没建账号的工号。
    listed=c.get(URL,params={'review':'pending'}).json()
    assert {x['staff_no'] for x in listed['items']}=={'J001','J002','T9001','J900'}
    assert c.get(URL,params={'review':'pending','org_id':'dept1'}).status_code==200
    y=credits(c,'J001');k1=course(y['2025-2026'],'K1')
    assert review(c,[k1['id']],'approve','已核对排课').status_code==200
    row=course(credits(c,'T9001')['2025-2026'],'K1')
    assert review(c,[row['id']],'approve','人事核对后认定').status_code==200
    own=course(credits(c,'J002')['2025-2026'],'K1')
    r=review(c,[own['id']],'approve');assert r.status_code==403 and '回避' in r.json()['detail'],r.text
    # 别的普通老师还是只能看本人的。
    auth(c,'teacher')
    assert c.get('/api/auth/me').json()['credit_reviewer'] is False
    assert {x['staff_no'] for x in c.get(URL).json()['items']}=={'J001'}
    # 移除后马上不能再认定，已认定的课不受影响。
    auth(c,'schooladmin')
    assert post(c,'/api/credit-reviewers/remove',{'user_id':'otherteacher',**REASON}).status_code==200
    assert post(c,'/api/credit-reviewers/remove',{'user_id':'otherteacher',**REASON}).status_code==404
    auth(c,'otherteacher')
    assert c.get('/api/auth/me').json()['credit_reviewer'] is False
    assert c.get('/api/todos',params={'type':'credit_review'}).json()['total']==0
    assert {x['staff_no'] for x in c.get(URL).json()['items']}=={'J002'}
    auth(c,'schooladmin')
    k2=course(credits(c,'J001')['2026-2027'],'K2')
    auth(c,'otherteacher');assert review(c,[k2['id']],'approve').status_code==403
    auth(c,'teacher');assert credits(c,'J001')['2025-2026']['total_credit']=='4.00'


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
