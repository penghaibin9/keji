"""4.4 撤销本批入库: restore prior values, refuse on later changes, idempotent, keep audit."""
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from app.models import User,Audit,TrainingRecord
from app.reference_data import TrainingProjectMaster,TeacherHrProfile,InboundBatch
from conftest import auth,post
from test_r4_internal_closeout import configure_middle

REASON={'reason':'撤销本批入库测试','basis':'合成隔离数据'}
PROJECT=[{'source':'projectCode','target':'code','transform':'text','required':True,'default':None},
         {'source':'projectName','target':'name','transform':'text','required':True,'default':None},
         {'source':'enabled','target':'active','transform':'bool','required':True,'default':True}]
HR=[{'source':'staff','target':'staff_no','transform':'text','required':True,'default':None},
    {'source':'name','target':'name','transform':'text','required':True,'default':None},
    {'source':'title','target':'title','transform':'text','required':False,'default':''},
    {'source':'org','target':'org_code','transform':'text','required':True,'default':None},
    {'source':'active','target':'active','transform':'bool','required':True,'default':True}]


def inbound(c,conn,data_type,records):
    p=post(c,'/api/connections/'+conn['id']+'/inbound/preview',{'data_type':data_type,'records':records,'source_label':'回滚样本',**REASON})
    assert p.status_code==200,p.text;p=p.json();assert p['errors']==0,p
    r=post(c,'/api/inbound-batches/'+p['id']+'/confirm',{'expected_version':p['version'],**REASON});assert r.status_code==200,r.text
    return r.json()


def rollback(c,batch,key=None):
    kw={'key':key} if key else {}
    return post(c,'/api/inbound-batches/'+batch['id']+'/rollback',{'expected_version':batch['version'],**REASON},**kw)


def test_rollback_restores_prior_project_values_and_deactivates_created(client2,app2):
    c=client2;auth(c,'schooladmin');conn=configure_middle(c,PROJECT)
    first=inbound(c,conn,'training_project',[{'projectCode':'RB-P1','projectName':'原名称','enabled':True}])
    second=inbound(c,conn,'training_project',[{'projectCode':'RB-P1','projectName':'中台新名称','enabled':False},{'projectCode':'RB-P2','projectName':'本批新建','enabled':True}])
    row=second['receipt']['rows'][0];assert row['before']['name']=='原名称' and row['after']['name']=='中台新名称'
    # The earlier batch cannot be rolled back over the later one.
    r=rollback(c,first);assert r.status_code==409 and '后续批次' in r.json()['detail']
    r=rollback(c,second,key='rollback-second-0001');assert r.status_code==200,r.text
    body=r.json();assert body['state']=='VOID' and body['receipt']['rollback']['actor_id']=='schooladmin'
    assert {x['action'] for x in body['receipt']['rollback']['objects']}=={'RESTORED','DEACTIVATED'}
    with Session(app2.state.engine) as db:
        p1=db.scalar(select(TrainingProjectMaster).where(TrainingProjectMaster.code=='RB-P1'))
        p2=db.scalar(select(TrainingProjectMaster).where(TrainingProjectMaster.code=='RB-P2'))
        assert p1.name=='原名称' and p1.active is True and p2 is not None and p2.active is False
        audits=db.scalars(select(Audit).where(Audit.module.in_(['training_project','inbound']))).all()
        assert any(a.action=='撤销数据中台入站批次' and a.reason==REASON['reason'] for a in audits)
        assert any(a.action=='确认数据中台项目主数据入库' for a in audits)  # history kept
        restore=next(a for a in audits if a.action=='撤销数据中台入站：恢复主数据前值')
        assert restore.before['name']=='中台新名称' and restore.after['name']=='原名称'
        count=db.scalar(select(func.count()).select_from(Audit).where(Audit.module!='access'))
    # Idempotent: replay and a fresh request both return the rolled-back batch without re-applying.
    again=rollback(c,second,key='rollback-second-0001');assert again.status_code==200 and again.json()==body
    fresh=post(c,'/api/inbound-batches/'+second['id']+'/rollback',{'expected_version':body['version'],**REASON})
    assert fresh.status_code==200 and fresh.json()['state']=='VOID'
    with Session(app2.state.engine) as db:
        assert db.scalar(select(func.count()).select_from(Audit).where(Audit.module!='access'))==count
        assert db.scalar(select(TrainingProjectMaster.version).where(TrainingProjectMaster.code=='RB-P1'))==3
    # Now that the later batch is undone, the first batch can be undone too.
    first=c.get('/api/inbound-batches/'+first['id']).json()['batch']
    assert rollback(c,first).status_code==200
    assert c.get('/api/inbound-batches',params={'state':'VOID'}).json()['total']==2


def test_rollback_refuses_local_edit_and_restores_teacher_account(client2,app2):
    c=client2;auth(c,'schooladmin');conn=configure_middle(c,HR)
    batch=inbound(c,conn,'teacher_hr',[{'staff':'J001','name':'测试教师一（中台）','title':'副教授','org':'dept2','active':True}])
    with Session(app2.state.engine) as db:
        u=db.get(User,'teacher');assert u.org_id=='dept2';auth_version=u.auth_version
    r=rollback(c,batch);assert r.status_code==200,r.text
    with Session(app2.state.engine) as db:
        u=db.get(User,'teacher');assert u.org_id=='dept1' and u.name=='测试教师一' and u.auth_version==auth_version+1
        profile=db.scalar(select(TeacherHrProfile).where(TeacherHrProfile.staff_no=='J001'));assert profile.active is False
    # A batch whose objects were edited locally afterwards is refused with a clear conflict.
    batch=inbound(c,conn,'teacher_hr',[{'staff':'J001','name':'再次入库','title':'教授','org':'dept2','active':True}])
    with app2.state.sessions.begin() as db:
        u=db.get(User,'teacher');u.title='本地调整';u.version+=1
    r=rollback(c,batch);assert r.status_code==409 and '账号入库后已被调整' in r.json()['detail']
    with Session(app2.state.engine) as db:
        assert db.get(User,'teacher').title=='本地调整'
        assert db.get(InboundBatch,batch['id']).state=='COMMITTED'


def test_rollback_voids_inserted_ledger_records_and_requires_admin(client2,app2):
    c=client2;auth(c,'schooladmin')
    fields=['external_key','staff_no','event_date','project_code','project','course_code','course','class_code','class_name','hours','participants','income']
    conn=configure_middle(c,[{'source':k,'target':k,'transform':'text','required':True,'default':None} for k in fields])
    data={'external_key':'RB-REC-1','staff_no':'J001','event_date':'2026-09-20','project_code':'P1','project':'合成项目P1','course_code':'C1','course':'合成课程','class_code':'CLP1','class_name':'合成班级','hours':'2','participants':'3','income':'50'}
    batch=inbound(c,conn,'training_income',[data])
    auth(c,'depthead');assert rollback(c,batch).status_code==403
    auth(c,'schooladmin');r=rollback(c,batch);assert r.status_code==200,r.text
    with Session(app2.state.engine) as db:
        rec=db.scalar(select(TrainingRecord).where(TrainingRecord.external_key=='RB-REC-1'))
        assert rec.state=='VOID' and rec.version==2
    assert all(x['external_key']!='RB-REC-1' for x in c.get('/api/records').json()['items'])
