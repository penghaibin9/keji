"""超星建课人自己把登录名改成工号后，下一次全量同步自动对上；管理员能下载还没对上的名单。"""
from io import BytesIO
from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.reference_data import TeacherCourseTerm,TeacherHrProfile
from conftest import auth,post
from test_procurement_inbound_rollback import REASON
from test_teacher_course_inbound import ScheduleHub,typed

CX_MAP={'creater_login_name':'staff_no','teachername':'teacher_name','courseid':'course_code','coursename':'course_name','xn':'school_year','xq':'term_no','credit':'credit'}

class CxHub(ScheduleHub):
    def __init__(self,rows):
        super().__init__(rows)
        self.config['adapter']['data_types']={'online_course':self.config['adapter']['data_types']['teacher_course']}

def cx_full_run(app,rows):
    from app.integrations import AdapterRegistry
    from app.inbound_sync import IntegrationSchedule,create_pull_task,process_pull_task_once
    from app.models import Connection,Task
    from test_integration_closeout import actor
    hub=CxHub(rows);registry=AdapterRegistry();registry.register_for_test('middle',hub.adapter)
    with app.state.sessions.begin() as db:
        connection=db.scalar(select(Connection).where(Connection.code=='middle'))
        connection.config=hub.config;connection.mappings=typed('online_course',CX_MAP,{'staff_no','course_code','course_name'});connection.state='CONNECTED'
        schedule=db.scalar(select(IntegrationSchedule).where(IntegrationSchedule.data_type=='online_course'))
        if not schedule:
            schedule=IntegrationSchedule(connection_id=connection.id,data_type='online_course',frequency_minutes=10080,auto_commit=True,active=True,approved_by='schooladmin')
            db.add(schedule);db.flush()
        ident=create_pull_task(db,actor(db),connection,'online_course','FULL','合成全量',schedule=schedule).id
    for _ in range(50):
        with app.state.sessions.begin() as db:
            task=db.get(Task,ident);process_pull_task_once(db,task,registry)
            if task.state in {'DONE','FAILED','BLOCKED'}:return task.state,task.error,task.result
    raise AssertionError('run did not finish')

def course(login,cid,name='测试教师一'):
    return {'creater_login_name':login,'teachername':name,'courseid':cid,'coursename':'线上课'+cid,'xn':'2025','xq':'1','credit':'2'}

def cx_rows(app):
    with Session(app.state.engine) as db:
        return {(x.staff_no,x.course_code):(x.active,x.user_id) for x in db.scalars(select(TeacherCourseTerm).where(TeacherCourseTerm.origin=='CX'))}

def test_teacher_who_fixes_login_is_matched_on_next_full_sync_and_listed_until_then(client2,app2):
    c=client2;auth(c,'schooladmin')
    with Session(app2.state.engine) as db:
        db.add(TeacherHrProfile(staff_no='J001',user_id='teacher',name='测试教师一',org_code='dept1'));db.commit()
    r=post(c,'/api/settings',{'key':'dict:cx_login_alias','value':{'name':'超星登录名对照','items':['gone01=J001','J001=J777','wrong01=J001']},**REASON})
    assert r.status_code==200,r.text
    others=[course('wp9',f'X{i}','外聘老师') for i in range(2,6)]
    state,error,_=cx_full_run(app2,[course('phone138','X1')]+[course('wrong01','X9','别的老师')]+others)
    assert state=='DONE',error
    assert cx_rows(app2)[('phone138','X1')]==(True,None)
    book=c.get('/api/reference/cx-unmatched.xlsx');assert book.status_code==200,book.text
    wb=load_workbook(BytesIO(book.content))
    unmatched={row[0]:row for row in wb['还没对上工号'].iter_rows(min_row=2,values_only=True)}
    assert set(unmatched)=={'phone138','wp9'} and unmatched['wp9'][2]==4
    checks={row[0]:row[4] for row in wb['登录名对照核对'].iter_rows(min_row=2,values_only=True)}
    assert '可以删除' in checks['gone01'] and '请删除' in checks['J001'] and '不一致' in checks['wrong01']
    # 老师在超星把登录名改成工号 J001：下一次全量同步按工号入库并对上账号，旧登录名那条自动停用。
    state,error,result=cx_full_run(app2,[course('J001','X1')]+[course('wrong01','X9','别的老师')]+others)
    assert state=='DONE',error
    got=cx_rows(app2)
    assert got[('J001','X1')]==(True,'teacher') and got[('phone138','X1')][0] is False
    assert result['reconcile']['deactivated']==1
    wb=load_workbook(BytesIO(c.get('/api/reference/cx-unmatched.xlsx').content))
    assert {row[0] for row in wb['还没对上工号'].iter_rows(min_row=2,values_only=True)}=={'wp9'}

def test_cx_unmatched_download_is_school_admin_only(client2):
    c=client2;auth(c,'teacher')
    assert c.get('/api/reference/cx-unmatched.xlsx').status_code==403


def seed_unmatched(c,app):
    with Session(app.state.engine) as db:
        db.add(TeacherHrProfile(staff_no='J001',user_id='teacher',name='测试教师一',org_code='dept1'));db.commit()
    others=[course('wp9',f'X{i}','外聘老师') for i in range(2,6)]
    state,error,_=cx_full_run(app,[course('phone138','X1'),course('phone138','X6'),course('team7','X7','测试教师一 等')]+others)
    assert state=='DONE',error
    return others

def test_teacher_claims_login_without_password_name_match_applies_at_once_and_survives_next_sync(client2,app2):
    c=client2;auth(c,'schooladmin');others=seed_unmatched(c,app2)
    auth(c,'teacher')
    mine=c.get('/api/reference/cx-claims/mine').json()
    assert mine['name']=='测试教师一' and [x['login'] for x in mine['candidates']]==['phone138']
    r=post(c,'/api/reference/cx-claims',{'login':'phone138'});assert r.status_code==200,r.text
    assert r.json()['state']=='APPROVED' and r.json()['moved']==2
    got=cx_rows(app2)
    assert got[('J001','X1')]==(True,'teacher') and got[('J001','X6')]==(True,'teacher') and ('phone138','X1') not in got
    # 认领只是把课挂到老师名下，仍要教研室主任认定后才计学分。
    d=c.get('/api/reference/teacher-credits?staff_no=J001&detail=true').json()['items']
    cx=[r for g in d for r in g['details'] if r['origin']=='CX']
    assert len(cx)==2 and {r['review'] for r in cx}=={'pending'} and sum(g['cx_credit'] and float(g['cx_credit']) for g in d)==0
    assert post(c,'/api/reference/cx-claims',{'login':'phone138'}).status_code==409
    assert post(c,'/api/reference/cx-claims',{'login':'J001'}).status_code==422
    assert post(c,'/api/reference/cx-claims',{'login':'nosuch'}).status_code==404
    # 下一次全量同步超星仍报 phone138：按认领映射到 J001，同一条记录不变，不会重复也不会停用。
    auth(c,'schooladmin')
    state,error,result=cx_full_run(app2,[course('phone138','X1'),course('phone138','X6'),course('team7','X7','测试教师一 等')]+others)
    assert state=='DONE',error
    assert result['reconcile']['deactivated']==0
    got=cx_rows(app2);assert got[('J001','X1')]==(True,'teacher') and got[('J001','X6')]==(True,'teacher')

def test_name_mismatch_waits_for_admin_who_can_approve_reject_or_revoke(client2,app2):
    c=client2;auth(c,'schooladmin');seed_unmatched(c,app2)
    auth(c,'teacher')
    r=post(c,'/api/reference/cx-claims',{'login':'team7','note':'团队课我是建课人'});assert r.status_code==200,r.text
    assert r.json()['state']=='PENDING' and cx_rows(app2)[('team7','X7')]==(True,None)
    assert c.get('/api/reference/cx-claims').status_code==403
    assert post(c,'/api/reference/cx-claims/decide',{'login':'team7','staff_no':'J001','decision':'approve'}).status_code==403
    auth(c,'schooladmin')
    pending=c.get('/api/reference/cx-claims?state=PENDING').json()['items']
    assert [(x['login'],x['staff_no']) for x in pending]==[('team7','J001')]
    assert post(c,'/api/reference/cx-claims/decide',{'login':'team7','staff_no':'J001','decision':'reject'}).status_code==422
    r=post(c,'/api/reference/cx-claims/decide',{'login':'team7','staff_no':'J001','decision':'approve'});assert r.status_code==200,r.text
    assert cx_rows(app2)[('J001','X7')]==(True,'teacher')
    r=post(c,'/api/reference/cx-claims/decide',{'login':'team7','staff_no':'J001','decision':'revoke','reason':'核实不是本人'});assert r.status_code==200,r.text
    got=cx_rows(app2);assert got[('team7','X7')]==(True,None) and ('J001','X7') not in got
    # 撤销后登录名可以再被认领（例如真正的建课人）。
    auth(c,'teacher');assert post(c,'/api/reference/cx-claims',{'login':'team7'}).json()['state']=='PENDING'
