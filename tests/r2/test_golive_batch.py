"""上线前一批：账号人事状态、新建账号对应学校数据、对接与同步条数和问题、人均授课学分、按教研室筛学分。"""
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.reference_data import TeacherHrProfile,TeacherCourseTerm,SchoolCourse
from conftest import auth,post
from test_staff_roster import seed

def add_catalogue(app2):
    with Session(app2.state.engine) as db:
        db.add(SchoolCourse(external_key='K404|1',code='K404',name='补上学分的课',credit=Decimal('3'),hours=Decimal('48'),course_version='1'))
        db.add(SchoolCourse(external_key='K999|1',code='K999',name='总库里没学分',credit=None,course_version='1'))
        db.commit()

def test_users_carry_hr_state_and_filter(client2,app2):
    seed(client2);c=client2
    auth(c,'schooladmin')
    body=c.get('/api/users',params={'size':200}).json()
    states={x['staff_no']:x['hr_state'] for x in body['items']}
    assert states['J001']=='active' and states['J002']=='active'
    assert body['hr_synced'] is True and body['hr_unmatched']==1
    assert {x['hr_state'] for x in body['items'] if not x['staff_no']}=={'none'}
    with Session(app2.state.engine) as db:
        db.get(TeacherHrProfile,db.scalar(select(TeacherHrProfile.id).where(TeacherHrProfile.staff_no=='J002'))).staff_no='J002-OLD';db.commit()
    assert [x['staff_no'] for x in c.get('/api/users',params={'hr_state':'missing'}).json()['items']]==['J002']
    only=c.get('/api/users',params={'hr_state':'active','size':200}).json()['items']
    assert {x['staff_no'] for x in only}=={'J001'}
    assert all(x['staff_no'] is None for x in c.get('/api/users',params={'hr_state':'none'}).json()['items'])
    assert c.get('/api/users',params={'hr_state':'bad'}).status_code==422
    unmatched=c.get('/api/reference/teacher-hr',params={'unmatched':'true'}).json()
    assert [x['staff_no'] for x in unmatched['items']]==['T7788']

def test_new_account_takes_over_synced_school_rows(client2,app2):
    seed(client2);c=client2
    auth(c,'schooladmin')
    r=post(c,'/api/users',{'username':'t7788','staff_no':'T7788','name':'未建账号教师','org_id':'dept2','role_id':'role-teacher',
        'password':'Temp-Password-2026!','reason':'按人事表补建账号'})
    assert r.status_code==200,r.text
    uid=r.json()['id']
    with Session(app2.state.engine) as db:
        assert db.scalar(select(TeacherHrProfile.user_id).where(TeacherHrProfile.staff_no=='T7788'))==uid
        assert set(db.scalars(select(TeacherCourseTerm.user_id).where(TeacherCourseTerm.staff_no=='T7788')))=={uid}
    rows={x['staff_no']:x for x in c.get('/api/reference/staff-roster').json()['items']}
    assert 'no_account' not in rows['T7788']['problems']
    assert c.get('/api/users',params={'size':200}).json()['hr_unmatched']==0

def test_source_status_counts_and_problems(client2,app2):
    seed(client2);add_catalogue(app2);c=client2
    auth(c,'depthead');assert c.get('/api/reference/source-status').status_code==403
    auth(c,'schooladmin')
    r=c.get('/api/reference/source-status');assert r.status_code==200,r.text
    items=r.json()['items']
    assert items['teacher_hr']['active']==2 and items['teacher_hr']['inactive']==1
    # J001 单位对不上（K404 现在有学分）；T7788 没账号、不在职但有授课、缺学分。
    assert items['teacher_hr']['problems']==2 and items['teacher_hr']['problem_detail']['no_account']==1
    assert items['school_course']=={**items['school_course'],'active':2,'inactive':0,'problems':1}
    jw=items['teacher_course']
    assert jw['active']==2 and jw['problem_detail']=={'missing_credit':1,'unknown_year':0,'not_in_staff_table':1}
    assert items['online_course']['active']==0 and items['online_course']['problems']==0

def test_credit_summary_per_capita_and_colleges(client2,app2):
    seed(client2);add_catalogue(app2);c=client2
    auth(c,'teacher');assert c.get('/api/reference/credit-summary').status_code==403
    auth(c,'schooladmin')
    s=c.get('/api/reference/credit-summary').json()
    # 在职 J001（3 学分）、J002（0）；T7788 不在职不算。
    assert s['staff']==2 and s['teaching_staff']==1 and s['total_credit']=='3.00' and s['avg_credit']=='1.50' and s['avg_teaching']=='3.00'
    colleges={x['name']:x for x in s['colleges']}
    assert colleges['测试学院一']['avg_credit']=='3.00' and colleges['测试学院二']['avg_credit']=='0.00'
    auth(c,'depthead')
    d=c.get('/api/reference/credit-summary').json()
    assert d['staff']==1 and d['avg_credit']=='3.00'
    assert c.get('/api/reference/credit-summary',params={'school_year':'2025'}).status_code==422

def test_teacher_credits_filter_by_org(client2,app2):
    seed(client2);add_catalogue(app2);c=client2
    auth(c,'schooladmin')
    rows=c.get('/api/reference/teacher-credits',params={'org_id':'dept1'}).json()['items']
    assert {x['staff_no'] for x in rows}=={'J001'}
    assert c.get('/api/reference/teacher-credits',params={'org_id':'dept2'}).json()['items']==[]
    auth(c,'depthead')
    assert c.get('/api/reference/teacher-credits',params={'org_id':'dept2'}).status_code==403


def test_code_tables_import_and_hr_status_codes(client2,app2):
    from test_procurement_inbound_rollback import REASON
    from test_r4_internal_closeout import configure_middle
    from test_teacher_course_inbound import typed
    from conftest import put
    c=client2;auth(c,'schooladmin')
    conn=configure_middle(c,typed('teacher_hr',{'ZGH':'staff_no','XM':'name','SZDWDM':'org_code','DQZTM':'hr_status_code','JZGLBM':'staff_type'},{'staff_no','name','org_code'}))
    rows=[{'ZGH':'J001','XM':'测试教师一','SZDWDM':'dept1','DQZTM':'01','JZGLBM':'11'},{'ZGH':'J002','XM':'测试教师二','SZDWDM':'dept2','DQZTM':'07','JZGLBM':'11'}]
    preview=lambda:post(c,'/api/connections/'+conn['id']+'/inbound/preview',{'data_type':'teacher_hr','records':rows,'source_label':'码表样本',**REASON}).json()
    # 没导入在职状态码表：不猜，整行提示。
    p=preview();assert p['errors']==2
    detail=c.get('/api/inbound-batches/'+p['id']).json()
    assert all(any('在职状态码表还没导入' in e for e in r['errors']) for r in detail['rows']['items'])
    bad=put(c,'/api/reference/code-tables/hr_status',{'text':'01\t在职\n07\t退休','reason':'导入学校码表'})
    assert bad.status_code==422 and '第三列' in bad.text
    assert put(c,'/api/reference/code-tables/nope',{'text':'1\t一','reason':'导入学校码表'}).status_code==422
    ok=put(c,'/api/reference/code-tables/hr_status',{'text':'代码\t名称\t是否在职\n01\t在职\t是\n07\t退休\t否','reason':'导入学校码表'})
    assert ok.status_code==200,ok.text
    assert ok.json()['rows']==2
    assert put(c,'/api/reference/code-tables/staff_type',{'text':'11,专任教师\n12,行政人员','reason':'导入学校码表'}).status_code==200
    p=preview();assert p['errors']==0,p
    r=post(c,'/api/inbound-batches/'+p['id']+'/confirm',{'expected_version':p['version'],**REASON});assert r.status_code==200,r.text
    with Session(app2.state.engine) as db:
        state={x.staff_no:(x.active,x.extra.get('hr_status_code')) for x in db.scalars(select(TeacherHrProfile))}
    assert state=={'J001':(True,'01'),'J002':(False,'07')}
    rows.append({'ZGH':'J003','XM':'码不在表里','SZDWDM':'dept1','DQZTM':'99'})
    assert preview()['errors']==1
    tables=c.get('/api/reference/code-tables').json()['tables']
    assert tables['staff_type']=={'11':{'label':'专任教师'},'12':{'label':'行政人员'}} and tables['hr_status']['07']=={'label':'退休','active':False}
    auth(c,'teacher')
    assert c.get('/api/reference/code-tables').status_code==200
    assert put(c,'/api/reference/code-tables/staff_type',{'text':'11\t改','reason':'越权导入码表'}).status_code==403
    auth(c,'schooladmin')
    assert all(x['key']!='code_tables' for x in c.get('/api/settings').json()['items'])
