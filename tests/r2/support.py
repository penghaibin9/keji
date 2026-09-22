"""Explicit synthetic school fixture. Imported only by tests and isolated browser lab.

Not a production bootstrap, not a migration, not a real school's business data.
"""
from datetime import date
from sqlalchemy.orm import Session
from sqlalchemy import inspect
from app.models import *
from app.permissions import ALLOWED
from app.passwords import hash_password
from app.settings_catalog import DEFAULT_BUSINESS_DICTIONARY,DEFAULT_IMPORT_POLICY
FIXTURE_PASSWORD='FixtureOnly_2026_Local'
HASH=hash_password(FIXTURE_PASSWORD)

def populate(engine,*,first_login=False):
    if inspect(engine).get_table_names():raise RuntimeError('Test fixture refuses a non-empty database')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        for ident,kind,parent in [('school','school',None),('college1','college','school'),('college2','college','school'),('dept1','dept','college1'),('dept2','dept','college2')]:
            db.add(Org(id=ident,code=ident,name={'school':'隔离测试学校','college1':'测试学院一','college2':'测试学院二','dept1':'测试教研室一','dept2':'测试教研室二'}[ident],kind=kind,parent_id=parent));db.flush()
        for kind in ALLOWED:
            db.add(Role(id='role-'+kind,code=kind,name={'school':'学校管理员','college':'学院负责人','dept':'教研室负责人','teacher':'普通教师'}[kind],kind=kind,permissions=sorted(ALLOWED[kind])))
        db.flush()
        for ident,kind,org,staff,name in [('schooladmin','school','school',None,'学校测试管理员'),('teacher','teacher','dept1','J001','测试教师一'),('depthead','dept','dept1',None,'测试教研室负责人'),('collegehead','college','college1',None,'测试学院负责人'),('otherteacher','teacher','dept2','J002','测试教师二'),('otherdept','dept','dept2',None,'测试教研室二负责人')]:
            db.add(User(id=ident,username=ident,name=name,staff_no=staff,org_id=org,role_id='role-'+kind,password_hash=HASH,is_admin=ident=='schooladmin',must_change_password=first_login))
        db.add(Guard(key='calculations',version=1))
        for key,value in [('branding',{'school_name':'隔离测试学校'}),('metrics',{'income_note':'合成样本按教师归属收入','participants_note':'合成样本课程人次，不代表学校确认口径'}),('qualification',{'expiry_days':30,'categories':['职业资格','教学资质']}),('business_dictionary',DEFAULT_BUSINESS_DICTIONARY),('import_policy',DEFAULT_IMPORT_POLICY)]:
            db.add(Setting(key=key,value=value))
        db.add(Period(id='period2026',name='2026隔离测试周期',start_date=date(2026,1,1),end_date=date(2026,12,31)))
        db.flush()
        for ident,teacher,project,income in [('rec1','teacher','P1',100),('rec2','otherteacher','P2',200)]:
            db.add(TrainingRecord(id=ident,external_key=ident,teacher_id=teacher,event_date=date(2026,9,1),project_code=project,project='合成项目'+project,
              course_code='C1',course='合成课程',class_code='CL'+project,class_name='合成班级',hours=10,participants=5,income=income))
        for code,name in [('sso','学校统一认证'),('middle','学校数据中台'),('province','湘培直通车')]:
            db.add(Connection(code=code,name=name,state='NOT_CONNECTED',mappings=[],config={}))
        db.commit()
