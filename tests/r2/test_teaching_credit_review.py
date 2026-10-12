"""授课认定：教务、超星拉来的课先待认定，教研室主任认定后才计学分学时和积分。

走通整个流程：老师看到待认定 → 主任认定 / 不计分 → 计入积分 → 重新拉取后学分变了自动回到待认定。
"""
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import Audit,Period
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
        {'ZGH':'T9001','XM':'未建账号','KCH':'K1','KCMC':'高等数学','XQMC':'2025-2026学年第二学期'}])  # 没有本地账号
    # 超星课挂了教务课号 K1，同学年已有教务 K1，按规则只算一次，不用认定。
    inbound(c,conn,'online_course',[{'creater_login_name':'J001','teachername':'测试教师一','courseid':'X1','coursename':'高数线上版','xn':'2025','xq':'2','credit':'4','courseIdentifier':'K1'}])
    with Session(app2.state.engine) as db:
        db.add(TeacherHrProfile(staff_no='J001',user_id='teacher',name='测试教师一',org_code='dept1'));db.commit()
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


def test_teacher_sees_pending_and_head_approves_or_excludes(client2,app2):
    c=client2;setup(c,app2)
    # 1. 老师本人：两门课都待认定，学分 0，待认定 6 学分。
    auth(c,'teacher')
    years=credits(c,'J001');y1,y2=years['2025-2026'],years['2026-2027']
    assert (y1['total_credit'],y1['pending_credit'],y1['pending_courses'],y1['approved_courses'])==('0.00','4.00',1,0)
    assert (y2['total_credit'],y2['pending_credit'],y2['hours'],y2['pending_hours'])==('0.00','2.00','0.00','32.00')
    k1,k2=course(y1,'K1'),course(y2,'K2')
    assert k1['review']=='pending' and course(y1,'X1','CX')['counted'] is False and course(y1,'X1','CX')['review'] is None
    # 老师不能自己认定。
    assert review(c,[k1['id']],'approve').status_code==403
    # 2. 别的教研室主任管不到这位老师。
    auth(c,'otherdept')
    assert review(c,[k1['id']],'approve').status_code==403
    assert credits(c,'J001')=={}
    # 3. 本教研室主任：“只看待认定”里能看到 J001，看不到别的教研室的 J002。
    auth(c,'depthead')
    listed=c.get(URL,params={'review':'pending'}).json()
    assert {x['staff_no'] for x in listed['items']}=={'J001'} and listed['total']==2
    assert c.get(URL,params={'review':'bogus'}).status_code==422
    # 重复课不用认定；不计分必须写原因。
    assert review(c,[course(y1,'X1','CX')['id']],'approve').status_code==409
    assert review(c,[k2['id']],'exclude').status_code==422
    r=review(c,[k1['id']],'approve','已核对排课');assert r.status_code==200,r.text
    assert r.json()=={'updated':1,'unchanged':0,'decision':'approve'}
    assert review(c,[k2['id']],'exclude','该课为代课，按规定不计').status_code==200
    # 再点一次同样的认定不重复记录。
    assert review(c,[k1['id']],'approve','已核对排课').json()['unchanged']==1
    # 4. 老师本人看到结果：K1 计 4 学分 64 学时，K2 不计并能看到原因和认定人。
    auth(c,'teacher')
    years=credits(c,'J001');y1,y2=years['2025-2026'],years['2026-2027']
    assert (y1['total_credit'],y1['hours'],y1['pending_courses'],y1['approved_courses'])==('4.00','64.00',0,1)
    assert (y2['total_credit'],y2['excluded_courses'],y2['pending_credit'])==('0.00',1,'0.00')
    k2=course(y2,'K2')
    assert k2['review']=='excluded' and k2['review_reason']=='该课为代课，按规定不计' and k2['reviewed_by']=='测试教研室负责人'
    # 5. 每次认定都留审计记录。
    with Session(app2.state.engine) as db:
        actions=[a.action for a in db.scalars(select(Audit).where(Audit.module=='teacher_course',Audit.action.startswith('授课认定')).order_by(Audit.created_at))]
    assert actions==['授课认定：认定计分','授课认定：认定不计分']


def test_only_approved_courses_score_and_repull_resets_changed_courses(client2,app2):
    c=client2;conn=setup(c,app2)
    from app.services import facts,point_source_changes
    points(c,app2)
    # 都还待认定：积分 0。
    assert calculate(c)=='0.00'
    with Session(app2.state.engine) as db:
        raw,snap=facts(db,'teacher',db.get(Period,'period2026'))
        assert raw['credits']==Decimal('0') and {x['course_code'] for x in snap['teaching_credits']['unapproved']}=={'K1','K2'}
    auth(c,'depthead')
    y=credits(c,'J001');ids=[course(y['2025-2026'],'K1')['id'],course(y['2026-2027'],'K2')['id']]
    assert review(c,ids,'approve','本学年排课已核对').json()['updated']==2   # 批量认定
    with Session(app2.state.engine) as db:
        changes=point_source_changes(db,'teacher',db.get(Period,'period2026'))
        assert changes['changed'] and changes['items'][0]['after']=='6.00'   # 认定后提示积分需重算
    auth(c,'schooladmin')
    assert calculate(c)=='12.00'   # (4 + 2) x 2
    # 重新拉取：课程总库里 K1 改成 5 学分 → K1 回到待认定，K2 没变仍算。
    inbound(c,conn,'school_course',[{**CATALOGUE[0],'XF':'5'},CATALOGUE[1]])
    auth(c,'depthead')
    y=credits(c,'J001');k1=course(y['2025-2026'],'K1')
    assert k1['review']=='pending' and k1['review_stale'] is True and k1['credit']=='5.00'
    assert y['2025-2026']['total_credit']=='0.00' and y['2026-2027']['total_credit']=='2.00'
    with Session(app2.state.engine) as db:
        assert point_source_changes(db,'teacher',db.get(Period,'period2026'))['changed']
    # 主任按新学分再认定一次；也可以改回待认定。
    assert review(c,[k1['id']],'approve','学分已按课程总库更新').json()['updated']==1
    assert credits(c,'J001')['2025-2026']['total_credit']=='5.00'
    assert review(c,[k1['id']],'reset','认定有误，重新核对').json()['updated']==1
    assert credits(c,'J001')['2025-2026']['pending_courses']==1


def test_unmapped_staff_are_reviewed_by_school_admin_and_college_can_review(client2,app2):
    c=client2;setup(c,app2)
    auth(c,'schooladmin')
    row=course(credits(c,'T9001')['2025-2026'],'K1')
    auth(c,'depthead')
    assert review(c,[row['id']],'approve').status_code==403
    auth(c,'schooladmin')
    assert review(c,[row['id']],'approve','人事核对后认定').status_code==200
    assert credits(c,'T9001')['2025-2026']['total_credit']=='4.00'
    # 学校管理员不替教研室认定有账号的老师。
    k1=course(credits(c,'J001')['2025-2026'],'K1')
    assert review(c,[k1['id']],'approve').status_code==403
    # 学院负责人可以认定本学院老师的课（教研室主任本人的课由学院负责人认定）。
    auth(c,'collegehead')
    assert review(c,[k1['id']],'approve','学院核对').status_code==200
    # 不存在的课整批拒绝，一条也不写。
    k2=course(credits(c,'J001')['2026-2027'],'K2')
    assert review(c,[k2['id'],'no-such-row'],'approve').status_code==409
    assert course(credits(c,'J001')['2026-2027'],'K2')['review']=='pending'
