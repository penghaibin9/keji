"""Isolated test fixtures only. Not the missing school authentication layer."""
from __future__ import annotations
from datetime import date
from pathlib import Path
import sys
from types import SimpleNamespace
import pytest
from sqlalchemy import create_engine,event,select
from sqlalchemy.orm import Session,sessionmaker
from fastapi import HTTPException
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'));sys.path.insert(0,str(ROOT/'scripts'))
from app import models as m
from app.settings_catalog import DEFAULT_BUSINESS_DICTIONARY,DEFAULT_IMPORT_POLICY

class FixtureActor:
    def __init__(self,ids=('t1','t2','t4'),org_ids=('school','c1','d1')):
        self.id='admin';self.ids=ids;self.org_ids=org_ids
    def scope(self,column):return column.in_(self.ids)
    def check_teacher(self,db,teacher_id,active=True):
        u=db.get(m.User,teacher_id)
        if teacher_id not in self.ids or u is None or (active and not u.active):raise HTTPException(403,'fixture scope denied')

@pytest.fixture
def actor():return FixtureActor()

@pytest.fixture
def engine(tmp_path):
    e=create_engine('sqlite:///'+str(tmp_path/'isolated.sqlite'),connect_args={'check_same_thread':False})
    @event.listens_for(e,'connect')
    def foreign_keys(connection,_):connection.execute('PRAGMA foreign_keys=ON')
    m.Base.metadata.create_all(e) # Test database only; never used by production code.
    with e.begin() as c:
        c.exec_driver_sql('CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)')
        c.exec_driver_sql("INSERT INTO alembic_version VALUES ('20260918_0001')")
    with Session(e) as db:
        for o in [('school','学校','school',None),('c1','学院一','college','school'),('c2','学院二','college','school'),('d1','教研室一','dept','c1'),('d2','教研室二','dept','c2')]:
            db.add(m.Org(id=o[0],code=o[0],name=o[1],kind=o[2],parent_id=o[3]));db.flush()
        for k in ('teacher','dept','college','school'):
            db.add(m.Role(id='role-'+k,code=k,name=k,kind=k,permissions=['portal.read']))
        db.flush()
        for ident,org,role in [('admin','school','school'),('t1','d1','teacher'),('t2','d1','teacher'),('t3','d2','teacher'),('t4','d1','teacher')]:
            db.add(m.User(id=ident,username=ident,name='隔离样本'+ident,staff_no=ident if role=='teacher' else None,
                          org_id=org,role_id='role-'+role,password_hash='NOT_A_REAL_LOGIN_CREDENTIAL',must_change_password=True))
        db.add(m.Period(id='p',name='2026隔离周期',start_date=date(2026,1,1),end_date=date(2026,12,31)))
        db.add(m.Period(id='old',name='2025隔离周期',start_date=date(2025,1,1),end_date=date(2025,12,31)))
        for key,value in [('branding',{'school_name':'隔离样本学校'}),('metrics',{'income_note':'样本收入口径','participants_note':'样本人次口径'}),('qualification',{'expiry_days':30,'categories':['样本类别']}),('business_dictionary',DEFAULT_BUSINESS_DICTIONARY),('import_policy',DEFAULT_IMPORT_POLICY)]:
            db.add(m.Setting(key=key,value=value))
        db.add(m.Guard(key='calculations',version=1));db.flush()
        db.add(m.Rule(id='r',kind='assessment',name='隔离规则',version_no=1,period_id='p',config={'components':[]},fingerprint='f'*64,created_by='admin',reason='隔离测试'))
        db.flush()
        for ident,tid,project,course,day,income,state in [('r1','t1','P1','C1',1,100,'VALID'),('r2','t2','P2','C2',2,200,'VALID'),('r3','t1','P1','C3',3,50,'VALID'),('r4','t3','P1','C1',1,999,'VALID'),('r5','t1','P1','C1',1,999,'VOID')]:
            db.add(m.TrainingRecord(id=ident,external_key=ident,teacher_id=tid,event_date=date(2026,9,day),project_code=project,
               project='项目'+project,course_code=course,course='课程'+course,class_code=ident,class_name='班级'+ident,hours=2,participants=10,income=income,state=state))
        for ident,tid,state,returned in [('a1','t1','TEACHER',True),('a2','t2','ARCHIVED',False),('a3','t3','TEACHER',False),('a4','t4','TEACHER',False)]:
            db.add(m.Assessment(id=ident,teacher_id=tid,period_id='p',rule_id='r',score=85,detail=[],source_snapshot={'immutable':'sample'},state=state,returned=returned,
                archive={'frozen':'sample'} if state=='ARCHIVED' else None,archive_sha256='a'*64 if state=='ARCHIVED' else None))
        db.commit()
    yield e
    e.dispose()

@pytest.fixture
def db(engine):
    with Session(engine) as s:yield s

@pytest.fixture
def cfg():return SimpleNamespace(env='test',secure_cookie=False)
