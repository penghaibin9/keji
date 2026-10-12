"""人事同步、学期去重、字段长度、舍入与课程版本的隔离回归。"""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import Connection,User
from app import reference_data as data
from conftest import auth,post
from test_integration_closeout import actor
from test_procurement_inbound_rollback import HR,REASON
from test_r4_internal_closeout import configure_middle
from test_teacher_course_inbound import typed
from credit_review_support import assume_approved


@pytest.fixture(autouse=True)
def _approved(monkeypatch):
    # 这些用例只核对学期去重、舍入和课程版本规则；认定流程见 test_teaching_credit_review.py。
    assume_approved(monkeypatch)


def preview(db,kind,rows):
    connection=db.scalar(select(Connection).where(Connection.code=='middle'))
    connection.mappings=[{**m,'transform':'bool'} if m['target']=='active' else m for m in typed(kind,{k:k for k in rows[0]})]
    return data.preview_inbound(db,actor(db),connection,kind,rows)


def confirm(db,kind,rows):
    batch=preview(db,kind,rows);assert batch.errors==0,[(r.mapped,r.errors) for r in db.scalars(select(data.InboundRow).where(data.InboundRow.batch_id==batch.id))]
    data.confirm_inbound(db,actor(db),batch,batch.version,'隔离规则回归');db.flush()
    return batch


@pytest.mark.parametrize('username,kind,org',[
    ('depthead','dept','dept1'),('collegehead','college','college1'),
    ('otherdept','school','school'),('teacher','teacher','dept1')])
@pytest.mark.parametrize('active',[True,False])
def test_hr_links_accounts_preserves_manager_org_and_revokes_changed_sessions(client2,app2,username,kind,org,active):
    with Session(app2.state.engine) as db:
        user=db.get(User,username);user.staff_no='RR001';user.role_id='role-'+kind;user.org_id=org
        auth_version=user.auth_version;db.commit()
    auth(client2,username);old_cookies=dict(client2.cookies);client2.cookies.clear()
    auth(client2,'schooladmin');connection=configure_middle(client2,HR)
    response=post(client2,'/api/connections/'+connection['id']+'/inbound/preview',{
        'data_type':'teacher_hr','records':[{'staff':'RR001','name':'同步后的姓名','title':'教授','org':'dept2','active':active}],
        'source_label':'隔离人事同步',**REASON})
    assert response.status_code==200,response.text
    batch=response.json();assert batch['errors']==0
    rows=client2.get('/api/inbound-batches/'+batch['id']).json()['rows']['items']
    assert rows[0]['errors']==[]
    response=post(client2,'/api/inbound-batches/'+batch['id']+'/confirm',{'expected_version':batch['version'],**REASON})
    assert response.status_code==200,response.text
    changed=kind!='school' or not active
    assert response.json()['receipt']['authorization_changes']==int(changed)
    with Session(app2.state.engine) as db:
        user=db.get(User,username)
        profile=db.scalar(select(data.TeacherHrProfile).where(data.TeacherHrProfile.staff_no=='RR001'))
        assert profile.user_id==user.id and profile.org_code=='dept2'
        assert (profile.name,profile.title,profile.active)==('同步后的姓名','教授',active)
        assert (user.name,user.title,user.active)==('同步后的姓名','教授',active)
        assert user.org_id==('dept2' if kind=='teacher' else org)
        assert user.role_id=='role-'+kind and user.auth_version==auth_version+int(changed)
    client2.cookies.clear();client2.cookies.update(old_cookies)
    assert client2.get('/api/auth/me').status_code==(401 if changed else 200)


@pytest.mark.parametrize('kind',['teacher_course','online_course'])
def test_term_aliases_count_once_without_changing_stored_keys(app2,kind):
    terms=['2024-2025-1','2024-2025学年第一学期','2024-2025-2']
    with Session(app2.state.engine) as db:
        db.add(data.TeacherHrProfile(staff_no='J001',user_id='teacher',name='测试教师一',org_code='dept1'))
        confirm(db,kind,[{'staff_no':'J001','course_code':'K1','course_name':'课程','term_name':term,'credit':'2','hours':'32'} for term in terms])
        rows=db.scalars(select(data.TeacherCourseTerm)).all()
        assert {r.external_key for r in rows}=={data.TEACHING_TYPES[kind]+'|J001|K1|'+term for term in terms}
        full=data.annual_teaching_credits(db,rows)[0]
        summary=data.annual_teaching_credits(db,rows,include_details=False)[0]
        assert summary=={k:v for k,v in full.items() if k!='details'}
        assert (full['total_credit'],full['hours'],full['courses'],full['duplicates_skipped'])==('4.00','64.00',2,1)
        duplicate=next(d for d in full['details'] if d['term_name']==terms[1])
        assert duplicate['counted'] is False and duplicate['duplicate_of_term']==terms[0]
        period=SimpleNamespace(start_date=date(2024,9,1),end_date=date(2025,8,31))
        total,evidence=data.teaching_credit_facts(db,db.get(User,'teacher'),period)
        assert total==Decimal('4.00') and sum(d['counted'] for d in evidence['courses'])==2


@pytest.mark.parametrize('include_details',[True,False])
def test_unrecognised_terms_are_not_deduplicated_and_keys_stay_separate(app2,include_details):
    with Session(app2.state.engine) as db:
        rows=[]
        for staff,origin,code,term in [
            ('J001','JW','K1','2024-2025秋季'),('J001','JW','K1','2024-2025春季'),
            ('J001','JW','K1','2024-2025-1'),('J001','CX','K1','2024-2025-1'),
            ('J001','JW','K2','2024-2025-1'),('J002','JW','K1','2024-2025-1'),
            ('J001','JW','K1','2025-2026-1')]:
            rows.append(data.TeacherCourseTerm(staff_no=staff,origin=origin,course_code=code,course_name='课程',
                term_name=term,credit=Decimal('1'),hours=Decimal('2'),teacher_name='',extra={}))
        groups=data.annual_teaching_credits(db,rows,include_details=include_details)
        assert sum(Decimal(g['total_credit']) for g in groups)==Decimal('7.00')
        assert sum(g['duplicates_skipped'] for g in groups)==0
        assert all(('details' in g)==include_details for g in groups)


@pytest.mark.parametrize('kind',['teacher_course','online_course'])
def test_composite_key_limit_reports_each_overlong_row(app2,kind):
    assert data.InboundRow.__table__.c.business_key.type.length==160
    assert data.TeacherCourseTerm.__table__.c.external_key.type.length==200
    with Session(app2.state.engine) as db:
        records=[{'staff_no':'S'*64,'course_code':'K'*64,'course_name':'课程','term_name':'T'*n} for n in (27,28,64)]
        batch=preview(db,kind,records)
        rows=db.scalars(select(data.InboundRow).where(data.InboundRow.batch_id==batch.id).order_by(data.InboundRow.row_no)).all()
        assert batch.errors==2 and rows[0].errors==[] and len(rows[0].business_key)==160
        assert [r.row_no for r in rows if '教师-课程-学期组合过长' in r.errors]==[2,3]
        assert all(r.mapped=={} and len(r.business_key)<=160 for r in rows[1:])
        assert [r.raw['term_name'] for r in rows]==[r['term_name'] for r in records]
        with pytest.raises(HTTPException) as caught:data.confirm_inbound(db,actor(db),batch,batch.version,'应阻断超长行')
        assert caught.value.status_code==409 and db.scalar(select(data.TeacherCourseTerm)) is None
        confirm(db,kind,[records[0]])
        assert db.scalar(select(data.TeacherCourseTerm.external_key))==rows[0].business_key


@pytest.mark.parametrize('kind',['teacher_course','online_course','school_course'])
def test_inbound_credit_and_hours_round_half_up(kind):
    values={'staff_no':'J001','course_code':'K1','course_name':'课程','term_name':'2024-2025-1',
        'code':'K1','name':'课程','credit':'1.005','hours':'2.005','weekly_hours':'3.005'}
    normalized,errors=data.validate_inbound(kind,values)
    assert errors==[] and normalized['credit']=='1.01' and normalized['hours']=='2.01'
    if kind=='school_course':assert normalized['weekly_hours']=='3.01'


def test_annual_details_and_per_capita_round_half_up(app2):
    with Session(app2.state.engine) as db:
        row=data.TeacherCourseTerm(staff_no='J001',origin='JW',course_code='K1',course_name='课程',
            term_name='2024-2025-1',teacher_name='',extra={},credit=Decimal('1.005'),hours=Decimal('2.005'))
        group=data.annual_teaching_credits(db,[row])[0]
        assert (group['total_credit'],group['jw_credit'],group['hours'])==('1.01','1.01','2.01')
        assert (group['details'][0]['credit'],group['details'][0]['hours'])==('1.01','2.01')
        profiles=[data.TeacherHrProfile(staff_no=staff,user_id=user,name=staff,org_code=org,active=True)
            for staff,user,org in [('J001','teacher','dept1'),('J002','otherteacher','dept2')]]
        db.add_all(profiles)
        confirm(db,'teacher_course',[{'staff_no':staff,'course_code':'K1','course_name':'课程','term_name':'2024-2025-1','credit':credit}
            for staff,credit in [('J001','1.00'),('J002','1.01')]])
        summary=data.credit_summary(db,profiles,school_year='2024-2025')
        assert summary['total_credit']=='2.01' and summary['avg_credit']=='1.01' and summary['avg_teaching']=='1.01'


@pytest.mark.parametrize('versions,winner',[
    (('9','10'),'10'),(('9.9','10.1'),'10.1'),(('A','B'),'B'),(('Z','10'),'10'),
    (('10','10.0'),'10.0'),(('10.1','10.1.2'),'10.1'),(('.5','0.4'),'.5')])
def test_catalogue_uses_numeric_versions_then_external_key(app2,versions,winner):
    with Session(app2.state.engine) as db:
        for index,version in enumerate(versions):
            db.add(data.SchoolCourse(external_key='KEY-'+str(index),code='K1',name='课程',course_version=version,credit=Decimal(index+1)))
        db.add(data.SchoolCourse(external_key='INACTIVE',code='K1',name='已停用课程',course_version='999',credit=Decimal('99'),active=False))
        db.flush()
        row=data.TeacherCourseTerm(staff_no='J001',origin='JW',course_code='K1',course_name='课程',term_name='2024-2025-1',teacher_name='',extra={})
        group=data.annual_teaching_credits(db,[row])[0]
        assert data._catalogue(db,{'K1'})['K1'].course_version==winner
        assert group['total_credit']==str(Decimal(versions.index(winner)+1).quantize(Decimal('0.01')))
