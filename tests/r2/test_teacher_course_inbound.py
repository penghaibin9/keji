"""Teacher-course-term inbound: 教务排课 (JW) and 超星课程库 (CX) land in one table, dedupe, roll back."""
from decimal import Decimal
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from app.models import User
from app.reference_data import TeacherCourseTerm
from conftest import auth,post
from test_procurement_inbound_rollback import REASON,inbound,rollback
from test_r4_internal_closeout import configure_middle

def maps(**extra):
    base={'ZGH':'staff_no','XM':'teacher_name','KCH':'course_code','KCMC':'course_name','XQMC':'term_name'}
    return [{'source':s,'target':t,'transform':'text','required':t in {'staff_no','course_code','course_name','term_name'},'default':None} for s,t in base.items()]

def test_jw_rows_dedupe_per_term_and_roll_back(client2,app2):
    c=client2;auth(c,'schooladmin');conn=configure_middle(c,maps())
    rows=[{'ZGH':'T9001','XM':'张老师','KCH':'C1','KCMC':'课程一','XQMC':'2025-2026-1'},
          {'ZGH':'T9001','XM':'张老师','KCH':'C1','KCMC':'课程一','XQMC':'2025-2026-1'},  # same course, another weekly slot
          {'ZGH':'T9001','XM':'张老师','KCH':'C1','KCMC':'课程一','XQMC':'2025-2026-2'}]
    batch=inbound(c,conn,'teacher_course',rows)
    with Session(app2.state.engine) as db:
        got=db.scalars(select(TeacherCourseTerm).order_by(TeacherCourseTerm.term_name)).all()
        assert [(x.origin,x.staff_no,x.term_name) for x in got]==[('JW','T9001','2025-2026-1'),('JW','T9001','2025-2026-2')]
        assert got[0].external_key=='JW|T9001|C1|2025-2026-1'
    r=rollback(c,batch);assert r.status_code==200,r.text
    with Session(app2.state.engine) as db:
        assert all(not x.active for x in db.scalars(select(TeacherCourseTerm)))

def test_conflicting_duplicate_rows_are_rejected(client2):
    c=client2;auth(c,'schooladmin');conn=configure_middle(c,maps())
    rows=[{'ZGH':'T9002','XM':'李老师','KCH':'C2','KCMC':'课程二','XQMC':'2025-2026-1'},
          {'ZGH':'T9002','XM':'李老师','KCH':'C2','KCMC':'课程二改名','XQMC':'2025-2026-1'}]
    p=post(c,'/api/connections/'+conn['id']+'/inbound/preview',{'data_type':'teacher_course','records':rows,'source_label':'冲突样本',**REASON})
    assert p.status_code==200 and p.json()['errors']==1

def test_cx_origin_and_missing_term_rejected(client2,app2):
    cx=[{'source':'staff','target':'staff_no','transform':'text','required':True,'default':None},
        {'source':'name','target':'course_name','transform':'text','required':True,'default':None},
        {'source':'cid','target':'course_code','transform':'text','required':True,'default':None},
        {'source':'xn','target':'school_year','transform':'text','required':False,'default':None},
        {'source':'xq','target':'term_no','transform':'text','required':False,'default':None},
        {'source':'credit','target':'credit','transform':'text','required':False,'default':None}]
    c=client2;auth(c,'schooladmin');conn=configure_middle(c,cx)
    bad=post(c,'/api/connections/'+conn['id']+'/inbound/preview',{'data_type':'online_course','records':[{'staff':'T9003','name':'线上课','cid':'X1'}],'source_label':'缺学期',**REASON})
    assert bad.status_code==200 and bad.json()['errors']==1
    inbound(c,conn,'online_course',[{'staff':'T9003','name':'线上课','cid':'X1','xn':'2025','xq':'1','credit':'2.5'}])
    with Session(app2.state.engine) as db:
        x=db.scalar(select(TeacherCourseTerm))
        assert x.origin=='CX' and x.term_name=='2025-1' and float(x.credit)==2.5

def typed(data_type,pairs,required=()):
    return [{'source':s,'target':t,'transform':'text','required':t in required,'default':None,'data_type':data_type} for s,t in pairs.items()]

def test_school_course_versions_and_rollback(client2,app2):
    from app.reference_data import SchoolCourse
    c=client2;auth(c,'schooladmin')
    conn=configure_middle(c,typed('school_course',{'JX02ID':'external_key','KCH':'code','KCMC':'name','XF':'credit','ZXS':'hours','VERSION':'course_version','ISDEL':'deleted'},{'code','name'}))
    rows=[{'JX02ID':'A1','KCH':'K1','KCMC':'高等数学','XF':'4','ZXS':'64','VERSION':'2023'},
          {'JX02ID':'A1','KCH':'K1','KCMC':'高等数学','XF':'4','ZXS':'64','VERSION':'2023'},  # replayed row collapses
          {'JX02ID':'A2','KCH':'K1','KCMC':'高等数学','XF':'3.5','ZXS':'56','VERSION':'2025'},
          {'JX02ID':'A3','KCH':'K2','KCMC':'已删课程','XF':'2','ISDEL':'1'}]
    batch=inbound(c,conn,'school_course',rows)
    with Session(app2.state.engine) as db:
        got={x.external_key:(x.code,float(x.credit),x.active) for x in db.scalars(select(SchoolCourse))}
        assert got=={'A1':('K1',4.0,True),'A2':('K1',3.5,True),'A3':('K2',2.0,False)}
    listed=c.get('/api/reference/school-courses?code=K1');assert listed.status_code==200 and listed.json()['total']==2
    r=rollback(c,batch);assert r.status_code==200,r.text
    with Session(app2.state.engine) as db:
        assert not any(x.active for x in db.scalars(select(SchoolCourse)))

def test_annual_credits_sum_both_terms_and_count_linked_cx_once(client2):
    c=client2;auth(c,'schooladmin')
    maps=(typed('school_course',{'KCH':'code','KCMC':'name','XF':'credit','ZXS':'hours','VERSION':'course_version'},{'code','name'})
        +typed('teacher_course',{'ZGH':'staff_no','XM':'teacher_name','KCH':'course_code','KCMC':'course_name','XQMC':'term_name'},{'staff_no','course_code','course_name','term_name'})
        +typed('online_course',{'creater_login_name':'staff_no','teachername':'teacher_name','courseid':'course_code','coursename':'course_name','xn':'school_year','xq':'term_no','credit':'credit','coursePeriod':'hours','courseIdentifier':'jw_course_code'},{'staff_no','course_code','course_name'}))
    conn=configure_middle(c,maps)
    inbound(c,conn,'school_course',[{'KCH':'K1','KCMC':'高等数学','XF':'4','ZXS':'64','VERSION':'2023'},
        {'KCH':'K2','KCMC':'线性代数','XF':'2','ZXS':'32','VERSION':'2023'}])
    inbound(c,conn,'teacher_course',[
        {'ZGH':'T9101','XM':'王老师','KCH':'K1','KCMC':'高等数学','XQMC':'2025-2026学年第一学期'},
        {'ZGH':'T9101','XM':'王老师','KCH':'K2','KCMC':'线性代数','XQMC':'2025-2026学年第二学期'},
        {'ZGH':'T9101','XM':'王老师','KCH':'K9','KCMC':'无学分课','XQMC':'2025-2026学年第二学期'},
        {'ZGH':'T9101','XM':'王老师','KCH':'K1','KCMC':'高等数学','XQMC':'2024-2025学年第二学期'}])
    inbound(c,conn,'online_course',[
        {'creater_login_name':'T9101','teachername':'王老师','courseid':'X1','coursename':'线上课','xn':'2025','xq':'2','credit':'1.5','coursePeriod':'24'},
        {'creater_login_name':'T9101','teachername':'王老师','courseid':'X2','coursename':'高数线上版','xn':'2025','xq':'1','credit':'4','courseIdentifier':'K1'}])
    r=c.get('/api/reference/teacher-credits?staff_no=T9101');assert r.status_code==200,r.text
    items=r.json()['items'];assert [x['school_year'] for x in items]==['2025-2026','2024-2025']
    y=items[0]
    assert (y['jw_credit'],y['cx_credit'],y['total_credit'],y['hours'])==('6.00','1.50','7.50','120.00')
    assert y['courses']==4 and y['duplicates_skipped']==1 and y['missing_credit']==['K9'] and len(y['terms'])==4
    assert items[1]['total_credit']=='4.00'
    one=c.get('/api/reference/teacher-credits?school_year=2024-2025');assert one.json()['total']==1

def test_school_year_parsing():
    from app.reference_data import school_year_of
    assert school_year_of('2025-2026学年第一学期')=='2025-2026'
    assert school_year_of('2025-2026-2')=='2025-2026'
    assert school_year_of('2025-1')=='2025-2026'
    assert school_year_of('2025-2027-1') is None and school_year_of('秋季') is None

def test_term_number_parsing():
    from app.reference_data import term_no_of
    assert [term_no_of(x) for x in ['2025-2026学年第一学期','2025-2026学年第二学期','2025-2026-2','2025-1','2025-2026学年上学期','秋季']]==[1,2,2,1,1,None]

def test_credits_feed_points_by_term_inside_period(client2,app2):
    from test_api import activate
    from app.models import Period
    from app.services import facts,point_source_changes
    c=client2;auth(c,'schooladmin')
    maps=(typed('school_course',{'KCH':'code','KCMC':'name','XF':'credit'},{'code','name'})
        +typed('teacher_course',{'ZGH':'staff_no','XM':'teacher_name','KCH':'course_code','KCMC':'course_name','XQMC':'term_name'},{'staff_no','course_code','course_name','term_name'})
        +typed('online_course',{'creater_login_name':'staff_no','courseid':'course_code','coursename':'course_name','xn':'school_year','xq':'term_no','credit':'credit'},{'staff_no','course_code','course_name'}))
    conn=configure_middle(c,maps)
    inbound(c,conn,'school_course',[{'KCH':'K1','KCMC':'高等数学','XF':'4'},{'KCH':'K2','KCMC':'线性代数','XF':'2'}])
    inbound(c,conn,'teacher_course',[
        {'ZGH':'J001','XM':'测试教师一','KCH':'K1','KCMC':'高等数学','XQMC':'2025-2026学年第一学期'},   # counts on 2025-09-01: outside 2026
        {'ZGH':'J001','XM':'测试教师一','KCH':'K2','KCMC':'线性代数','XQMC':'2025-2026学年第二学期'},   # 2026-03-01
        {'ZGH':'J001','XM':'测试教师一','KCH':'K1','KCMC':'高等数学','XQMC':'2026-2027学年第一学期'},   # 2026-09-01
        {'ZGH':'J002','XM':'测试教师二','KCH':'K1','KCMC':'高等数学','XQMC':'2025-2026学年第二学期'}])
    inbound(c,conn,'online_course',[{'creater_login_name':'J001','courseid':'X1','coursename':'线上课','xn':'2025','xq':'2','credit':'1.5'}])
    with Session(app2.state.engine) as db:
        from app.reference_data import TeacherHrProfile
        db.add(TeacherHrProfile(staff_no='J001',user_id='teacher',name='测试教师一',org_code='dept1'));db.commit()
        # J002 is not in the 教职工 table: listed, flagged, never scored.
        assert facts(db,'otherteacher',db.get(Period,'period2026'))[0]['credits']==0
    flags={x['staff_no']:x['in_staff_table'] for x in c.get('/api/reference/teacher-credits?school_year=2025-2026').json()['items']}
    assert flags=={'J001':True,'J002':False}
    r=post(c,'/api/rules',{'kind':'points','name':'学分积分','period_id':'period2026','config':{'components':[{'key':'credits','label':'授课学分','source':'credits','factor':'2','weight':'0','target':'1','cap':None}]},**REASON})
    assert r.status_code==200,r.text
    assert activate(c,r.json()).status_code==200
    r=post(c,'/api/points/calculate',{'period_id':'period2026','teacher_ids':['teacher'],**REASON});assert r.status_code==200,r.text
    assert c.get('/api/points?teacher_id=teacher').json()['sum']=='15.00'   # (2 + 4 + 1.5) x 2
    with Session(app2.state.engine) as db:
        raw,snap=facts(db,'teacher',db.get(Period,'period2026'))
        assert raw['credits']==Decimal('7.50') and {x['course_code'] for x in snap['teaching_credits']['courses']}=={'K1','K2','X1'}
        assert not point_source_changes(db,'teacher',db.get(Period,'period2026'))['changed']
    inbound(c,conn,'online_course',[{'creater_login_name':'J001','courseid':'X2','coursename':'新线上课','xn':'2026','xq':'1','credit':'1'}])
    with Session(app2.state.engine) as db:
        changes=point_source_changes(db,'teacher',db.get(Period,'period2026'))
        assert changes['changed'] and changes['items'][0]['label']=='授课学分' and changes['items'][0]['after']=='8.50'


class ScheduleHub:
    """Synthetic 教务 schedule feed: many weekly slots per teacher-course-term, paged 2 per page."""
    def __init__(self, rows):
        from app.adapters.datahub import ConfigurableDataHubAdapter
        self.rows = rows
        self.config = {'adapter': {'data_types': {'teacher_course': {
            'request': {'method': 'GET', 'path': '/schedule', 'auth': {'mode': 'none'}},
            'pagination': {'mode': 'page', 'page_size': 2, 'max_pages': 300, 'start_page': 1, 'end_condition': 'short_page'},
            'response': {'records_path': 'items', 'total_path': 'total'}}}}}
        hub = self
        class Hub(ConfigurableDataHubAdapter):
            def _request_json(self, *, context, **kwargs):
                start = context['offset']
                return {'items': hub.rows[start:start + context['limit']], 'total': len(hub.rows)}
            def pull_chunk(self, **kwargs):
                return super().pull_chunk(config=hub.config, credential='TEST_ONLY', timeout_seconds=10, **kwargs)
        self.adapter = Hub()

def full_run(app, hub):
    from app.integrations import AdapterRegistry
    from app.inbound_sync import IntegrationSchedule, create_pull_task, process_pull_task_once
    from app.models import Connection, Task
    from test_integration_closeout import actor
    registry = AdapterRegistry(); registry.register_for_test('middle', hub.adapter)
    with app.state.sessions.begin() as db:
        connection = db.scalar(select(Connection).where(Connection.code == 'middle'))
        connection.config = hub.config
        connection.mappings = typed('teacher_course', {'ZGH': 'staff_no', 'XM': 'teacher_name', 'KCH': 'course_code', 'KCMC': 'course_name', 'XQMC': 'term_name'},
                                    {'staff_no', 'course_code', 'course_name', 'term_name'})
        connection.state = 'CONNECTED'
        schedule = db.scalar(select(IntegrationSchedule).where(IntegrationSchedule.data_type == 'teacher_course'))
        if not schedule:
            schedule = IntegrationSchedule(connection_id=connection.id, data_type='teacher_course', frequency_minutes=30,
                                           auto_commit=True, active=True, approved_by='schooladmin')
            db.add(schedule); db.flush()
        ident = create_pull_task(db, actor(db), connection, 'teacher_course', 'FULL', '合成全量', schedule=schedule).id
    for _ in range(50):
        with app.state.sessions.begin() as db:
            task = db.get(Task, ident); process_pull_task_once(db, task, registry)
            if task.state in {'DONE', 'FAILED', 'BLOCKED'}: return task.state, task.error, task.result
    raise AssertionError('run did not finish')

def slot(staff, code, term='2025-2026学年第一学期'):
    return {'ZGH': staff, 'XM': '教师' + staff, 'KCH': code, 'KCMC': '课程' + code, 'XQMC': term}

def active_keys(app):
    with Session(app.state.engine) as db:
        return sorted(x.external_key for x in db.scalars(select(TeacherCourseTerm).where(TeacherCourseTerm.active.is_(True))))

def test_full_pull_collapses_repeated_slots_across_pages_and_withdraws_removed_courses(app2):
    rows = [slot('J001', 'K1')] * 3 + [slot('J001', 'K2'), slot('J002', 'K3'), slot('J002', 'K4'), slot('J002', 'K5')]
    state, error, result = full_run(app2, ScheduleHub(rows))
    assert state == 'DONE', error
    assert len(active_keys(app2)) == 5 and result['reconcile']['deactivated'] == 0
    # K5 is cancelled at the source: the next full pull withdraws it (1 of 5 = 20%).
    state, error, result = full_run(app2, ScheduleHub(rows[:-1]))
    assert state == 'DONE', error
    assert result['reconcile']['deactivated'] == 1 and 'JW|J002|K5|2025-2026学年第一学期' not in active_keys(app2)
    # A source that suddenly drops most rows is not trusted.
    state, error, result = full_run(app2, ScheduleHub(rows[:3]))
    assert state == 'DONE', error
    assert result['reconcile'].get('blocked') and len(active_keys(app2)) == 4

def test_conflicting_repeat_on_a_later_page_is_rejected(app2):
    rows = [slot('J001', 'K1'), slot('J001', 'K2'), {**slot('J001', 'K1'), 'KCMC': '改了名'}]
    state, error, result = full_run(app2, ScheduleHub(rows))
    assert state == 'FAILED' and result['errors'] == 1
