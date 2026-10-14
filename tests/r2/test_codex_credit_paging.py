"""授课学分分页与原全量汇总结果一致，明细计算限于当前页。"""
import pytest
from sqlalchemy import event,select
from sqlalchemy.orm import Session
from app.models import User
from app import reference_data as data
from app.routes import reference
from conftest import auth
from support import HASH


@pytest.fixture
def credit_data(app2):
    with Session(app2.state.engine) as db:
        db.add(User(id='creditteacher',username='creditteacher',name='无名册教师',staff_no='T004',org_id='dept1',
                    role_id='role-teacher',password_hash=HASH,must_change_password=False));db.flush()
        for staff,user,active in [('J001','teacher',True),('J002','otherteacher',False),('T003',None,True)]:
            db.add(data.TeacherHrProfile(staff_no=staff,user_id=user,name=staff,org_code='dept1',active=active))
        for version,credit,hours,active in [('1','2','32',True),('2','3.5','56',True),('9','99','99',False)]:
            db.add(data.SchoolCourse(external_key='K1|'+version,code='K1',name='总库课',course_version=version,
                                    credit=credit,hours=hours,active=active))
        def row(staff,user,term,code,**values):
            db.add(data.TeacherCourseTerm(external_key=str(len(db.new)),staff_no=staff,user_id=user,term_name=term,
                course_code=code,course_name='课程'+code,**{'origin':'JW','teacher_name':staff,**values}))
        row('J001','teacher','2026－2027学年第一学期','K1',teacher_name='')
        row('J001','teacher','2026-2027-2','ZERO',credit='0',hours='0',teacher_name='含100%字样')
        row('J001','teacher','2026-1','X1',origin='CX',credit='9',extra={'jw_course_code':' K1 '})
        row('J001',None,'2026-2027-2','UNBOUND',credit='0.5')
        row('J001','otherteacher','2026-2027-2','OUTSIDE',credit='7')
        row('J001','teacher','2025-2026学年第二学期','MISSING')
        row('J001','teacher','2025_1','X2',origin='CX',extra={'jw_course_code':'K1'})
        row('J001','teacher','2024至2025学年上学期','K1',credit='4')
        row('J001','teacher','秋季','K1')
        row('J001','teacher','未识别第二学期','X3',origin='CX',credit='9',extra={'jw_course_code':'K1'})
        row('J001','teacher','2099-2100-1','INACTIVE',credit='99',active=False)
        for term in ('2027-2028-1','2026-2027-1','2025-2','2025-2027-1'):
            row('J002','otherteacher',term,'K1')
        row('T003',None,'2026-2027-1','K1')
        row('T004','creditteacher','2026-2027-1','K1')
        db.commit()
    return app2


def full_result(app,params,users=None):
    # The previous route: scoped rows -> full aggregation -> years -> filters -> page.
    with Session(app.state.engine) as db:
        q=select(data.TeacherCourseTerm).where(data.TeacherCourseTerm.active.is_(True))
        if users is not None:q=q.where(data.TeacherCourseTerm.user_id.in_(users))
        if params.get('staff_no'):q=q.where(data.TeacherCourseTerm.staff_no==params['staff_no'])
        if params.get('org_id'):
            q=q.where(data.TeacherCourseTerm.user_id.in_(select(User.id).where(User.org_id==params['org_id'])))
        if params.get('q'):
            q=q.where(data.TeacherCourseTerm.teacher_name.contains(params['q'],autoescape=True)|data.TeacherCourseTerm.staff_no.contains(params['q'],autoescape=True))
        items=data.annual_teaching_credits(db,db.scalars(q))
    years=sorted({x['school_year'] for x in items},key=lambda y:(y!=data.UNKNOWN_YEAR,y),reverse=True)
    if params.get('school_year'):items=[x for x in items if x['school_year']==params['school_year']]
    if params.get('problem')=='true':items=[x for x in items if x['missing_credit'] or not x['user_id'] or not x['in_staff_table']]
    page=int(params.get('page',1));size=int(params.get('size',20));total=len(items);items=items[(page-1)*size:page*size]
    if params.get('detail')!='true':
        for x in items:x.pop('details')
    return {'items':items,'total':total,'page':page,'size':size,'years':years}


@pytest.mark.parametrize('detail',[None,'false','true'])
@pytest.mark.parametrize('problem',[None,'false','true'])
def test_pages_match_full_aggregation(client2,credit_data,detail,problem):
    auth(client2,'schooladmin')
    for filters in ({},{'school_year':'2026-2027'},{'school_year':data.UNKNOWN_YEAR},{'school_year':'不存在'},
                    {'staff_no':'J001'},{'staff_no':'不存在'},{'q':'100%'},{'q':'J'},{'org_id':'dept1'}):
        params={'size':2,**filters}
        if detail is not None:params['detail']=detail
        if problem is not None:params['problem']=problem
        expected=full_result(credit_data,params)
        for page in range(1,(expected['total']+1)//2+2):
            params['page']=page
            response=client2.get('/api/reference/teacher-credits',params=params)
            assert response.status_code==200,response.text
            assert response.json()==full_result(credit_data,params)
            assert all(('details' in row)==(detail=='true') for row in response.json()['items'])


@pytest.mark.parametrize('viewer,admin,users',[
    ('teacher',False,['teacher']),('depthead',False,['teacher','creditteacher']),
    ('collegehead',False,['teacher','creditteacher']),('otherteacher',False,['otherteacher']),
    # 学校层级且有考核审核权限的账号（教务处等）负责授课认定，也要看到还没建账号的工号，和系统管理员一样看全部。
    ('schooladmin',False,None)])
def test_page_queries_keep_row_scope(client2,credit_data,viewer,admin,users):
    if viewer=='schooladmin':
        with Session(credit_data.state.engine) as db:
            db.get(User,viewer).is_admin=admin;db.commit()
    auth(client2,viewer)
    for problem in ('false','true'):
        for page in (1,2,3,4,5,100000):
            params={'detail':'true','problem':problem,'size':2,'page':page}
            response=client2.get('/api/reference/teacher-credits',params=params)
            assert response.status_code==200,response.text
            assert response.json()==full_result(credit_data,params,users)


@pytest.mark.parametrize('problem',['false','true'])
@pytest.mark.parametrize('detail',['false','true'])
def test_only_page_rows_build_details(client2,credit_data,monkeypatch,problem,detail):
    auth(client2,'schooladmin')
    params={'page':2,'size':2,'school_year':'2026-2027','problem':problem,'detail':detail}
    expected=full_result(credit_data,params)
    page_keys={(x['staff_no'],x['school_year']) for x in expected['items']}
    loaded=[];calls=[];details=[]
    annual=data.annual_teaching_credits;term_no=data.term_no_of
    def capture(row,context):loaded.append(row.staff_no)
    def calculate(db,rows,**kw):
        rows=list(rows);calls.append(({(r.staff_no,data.school_year_of(r.term_name) or data.UNKNOWN_YEAR) for r in rows},kw.get('include_details',True)))
        return annual(db,rows,**kw)
    def detail_term(term):details.append(term);return term_no(term)
    monkeypatch.setattr(reference,'annual_teaching_credits',calculate)
    monkeypatch.setattr(data,'term_no_of',detail_term)
    event.listen(data.TeacherCourseTerm,'load',capture)
    try:response=client2.get('/api/reference/teacher-credits',params=params)
    finally:event.remove(data.TeacherCourseTerm,'load',capture)
    assert response.status_code==200,response.text
    assert response.json()==expected
    assert len(details)==sum(len(x.get('details',[])) for x in expected['items'])
    if problem=='false':
        assert set(loaded)=={key[0] for key in page_keys}
        assert calls==[(page_keys,detail=='true')]
    else:
        assert calls[0][1] is False
        assert calls[1:]==([(page_keys,True)] if detail=='true' else [])


def test_empty_page_skips_course_loading(client2,credit_data,monkeypatch):
    auth(client2,'schooladmin');params={'page':100000,'size':2,'detail':'true'}
    expected=full_result(credit_data,params)
    def no_aggregation(*args,**kwargs):pytest.fail('空页不应加载课程并计算学分')
    monkeypatch.setattr(reference,'annual_teaching_credits',no_aggregation)
    response=client2.get('/api/reference/teacher-credits',params=params)
    assert response.status_code==200,response.text
    assert response.json()==expected
