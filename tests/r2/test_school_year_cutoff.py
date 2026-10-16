"""只认 2020-2021 学年及以后：更早的课拉取时不入库，已入库的不删但不显示、不计分。"""
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.reference_data import TeacherCourseTerm,annual_teaching_credits,year_in_scope,term_in_scope
from conftest import auth
from test_teacher_course_inbound import maps
from test_procurement_inbound_rollback import inbound
from test_r4_internal_closeout import configure_middle

def test_scope_helpers():
    assert year_in_scope('2020-2021') and year_in_scope('2025-2026') and not year_in_scope('2019-2020')
    assert year_in_scope(None) and year_in_scope('未识别学年')
    assert term_in_scope('2020-2021学年第一学期') and not term_in_scope('2019-2020-2') and not term_in_scope('2019-1')
    assert term_in_scope('秋季学期')  # 认不出学年的仍保留，归“未识别学年”

def test_old_terms_are_skipped_on_inbound_and_hidden_afterwards(client2,app2):
    c=client2;auth(c,'schooladmin');conn=configure_middle(c,maps())
    batch=inbound(c,conn,'teacher_course',[
        {'ZGH':'T9201','XM':'周老师','KCH':'C1','KCMC':'旧课','XQMC':'2019-2020-2'},
        {'ZGH':'T9201','XM':'周老师','KCH':'C2','KCMC':'新课','XQMC':'2020-2021-1'}])
    assert batch['receipt']['skipped_before_min_year']==1
    with Session(app2.state.engine) as db:
        assert [x.term_name for x in db.scalars(select(TeacherCourseTerm))]==['2020-2021-1']
        # 以前已经入库的旧课：不删除，但学分汇总里不出现。
        db.add(TeacherCourseTerm(external_key='JW|T9201|C0|2018-2019-1',origin='JW',staff_no='T9201',teacher_name='周老师',course_code='C0',
                                 course_name='更早的课',term_name='2018-2019-1',credit=2,hours=32,source='历史数据'));db.commit()
        rows=db.scalars(select(TeacherCourseTerm)).all()
        assert len(rows)==2
        assert [g['school_year'] for g in annual_teaching_credits(db,rows)]==['2020-2021']
    years=c.get('/api/reference/teacher-credits').json()['years']
    assert '2018-2019' not in years and '2020-2021' in years
    listed=c.get('/api/reference/teacher-courses?staff_no=T9201').json()
    assert [x['term_name'] for x in listed['items']]==['2020-2021-1']
    assert c.get('/api/reference/credit-summary?school_year=2019-2020').status_code==422
