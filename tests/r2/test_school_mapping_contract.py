"""Approved field examples land in isolated tables; no additional HR data request."""
import json
import re
from pathlib import Path
from sqlalchemy import select
from app.reference_data import TeacherHrProfile, TeacherCourseTerm, SchoolCourse
from conftest import auth, put
from test_r4_internal_closeout import configure_middle
from test_teacher_course_inbound import typed
from test_procurement_inbound_rollback import inbound

CONFIG=Path(__file__).resolve().parents[2]/'docs/学校接口字段映射模板_20261012.json'


def pairs(kind):
    return json.loads(CONFIG.read_text(encoding='utf-8'))['字段映射'][kind]


def test_config_covers_all_38_requested_fields_without_unrequested_hr_fields():
    expected={
        'teacher_hr':'ZGH XM SZDWDM SZDWMC DQZTM JZGLBM GWMC GWLB ZCMC ZWMC XLM XWM XBM TSTAMP',
        'school_course':'JX02ID KCH KCMC KKDW GLDW XF SKFSM KHFS KCXZM KCLB KCSX KCDL ISKKS QYZT ISDEL ZXS ZHOUXS VERSION',
        'teacher_course':'ZGH XM KCH KCMC XQMC TSTAMP',
    }
    for kind,fields in expected.items():assert set(pairs(kind))==set(fields.split())
    assert sum(len(pairs(kind)) for kind in expected)==38
    assert not set(pairs('teacher_hr')) & {'ZCZYJSZWMC','GWM','PRZY','ZWJBM','DSLBM','LXFS','CYM'}


def test_school_mapping_template_has_four_types_without_addresses_or_credentials():
    text=CONFIG.read_text(encoding='utf-8');template=json.loads(text)
    assert set(template['字段映射'])=={'teacher_hr','school_course','teacher_course','online_course'}
    assert len(pairs('online_course'))==20
    assert not re.search(r'https?://|(?:\d{1,3}\.){3}\d{1,3}|C:[/\\]Users|\.codex',text)
    forbidden={'base_url','endpoint','ip','auth','app_key','app_secret','secret','access_token','password','credentials'}
    def check(value):
        if isinstance(value,dict):
            assert not forbidden & set(value)
            for child in value.values():check(child)
        elif isinstance(value,list):
            for child in value:check(child)
    check(template)


def test_requested_fields_roundtrip_and_can_open_remains_raw_without_changing_active(client2,app2):
    auth(client2,'schooladmin')
    mappings=[]
    for kind,required in [('teacher_hr',{'staff_no','name','org_code'}),('school_course',{'code','name'}),('teacher_course',{'staff_no','course_code','course_name','term_name'})]:
        mappings+=typed(kind,pairs(kind),required)
    conn=configure_middle(client2,mappings)
    assert put(client2,'/api/reference/code-tables/hr_status',{'text':'01\t在职\t是','reason':'合成码表回归'}).status_code==200
    stamp='2026-10-01T00:00:00+08:00'
    hr={'ZGH':'J001','XM':'合成教师','SZDWDM':'dept1','SZDWMC':'合成单位','DQZTM':'01','JZGLBM':'11',
        'GWMC':'岗位名称','GWLB':'岗位类别','ZCMC':'职称名称','ZWMC':'职务名称','XLM':'21','XWM':'401','XBM':'2','TSTAMP':stamp}
    inbound(client2,conn,'teacher_hr',[hr])
    course={'JX02ID':'C11-ID','KCH':'C11-COURSE','KCMC':'合成课程','KKDW':'0301','GLDW':'0302','XF':'2','SKFSM':'A',
        'KHFS':'B','KCXZM':'C','KCLB':'D','KCSX':'E','KCDL':'F','ISKKS':'学校原码','QYZT':'1','ISDEL':'0',
        'ZXS':'32','ZHOUXS':'2','VERSION':'2026'}
    inbound(client2,conn,'school_course',[course])
    inbound(client2,conn,'teacher_course',[{'ZGH':'J001','XM':'合成教师','KCH':'C11-COURSE','KCMC':'合成课程','XQMC':'2026-2027-1','TSTAMP':stamp}])
    with app2.state.sessions() as db:
        profile=db.scalar(select(TeacherHrProfile).where(TeacherHrProfile.staff_no=='J001'))
        assert (profile.name,profile.title,profile.org_code,profile.active)==('合成教师','职称名称','dept1',True)
        assert profile.extra=={'org_name':'合成单位','hr_status_code':'01','staff_type':'11','post_name':'岗位名称','post_type':'岗位类别','duty':'职务名称','edu':'21','degree':'401','gender':'2'}
        saved=db.scalar(select(SchoolCourse).where(SchoolCourse.code=='C11-COURSE'))
        assert saved.active is True and saved.extra['can_open']=='学校原码'
        assert saved.extra=={'manage_dept':'0302','nature':'C','category':'D','attribute':'E','group':'F','teach_mode':'A','exam_mode':'B','can_open':'学校原码'}
        assert (str(saved.credit),str(saved.hours),str(saved.weekly_hours),saved.dept,saved.course_version)==('2.00','32.00','2.00','0301','2026')
        term=db.scalar(select(TeacherCourseTerm).where(TeacherCourseTerm.course_code=='C11-COURSE'))
        assert (term.staff_no,term.teacher_name,term.course_name,term.term_name,term.source_stamp)==('J001','合成教师','合成课程','2026-2027-1',stamp)
    staff=client2.get('/api/reference/staff-roster/J001').json()['staff']
    assert all(staff[k]==profile.extra[k] for k in ['staff_type','post_name','post_type','duty','edu','degree','gender','hr_status_code'])
