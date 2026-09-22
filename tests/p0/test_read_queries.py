from datetime import date
import pytest
from fastapi import HTTPException
from sqlalchemy import select,event
from app import models as m
from app.read_queries import record_query,stats,assessment_query

@pytest.mark.parametrize('filters,teachers,assessment_count,income',[
 ({'project_code':'P1'},1,1,'150.00'),
 ({'course_code':'C2'},1,1,'200.00'),
 ({'start':'2026-09-03','end':'2026-09-03'},1,1,'50.00'),
 ({'teacher_id':'t2','project_code':'P1'},0,0,'0.00'),
 ({'period_id':'old'},0,0,'0.00'),
 ({'period_id':'p','org_id':'c1','project_code':'P1'},1,1,'150.00'),
 ({'q':'P2'},1,1,'200.00'),
 ({'q':'%'},0,0,'0.00'),
 ({},2,2,'350.00'),
])
def test_statistics_scope_matches_business_and_drill(db,actor,filters,teachers,assessment_count,income):
    result=stats(db,actor,filters)
    assert result['teachers']==teachers
    assert sum(result['assessment_states'].values())==assessment_count
    from decimal import Decimal
    assert Decimal(result['income'])==Decimal(income)
    drill=db.scalars(assessment_query(db,actor,result['assessment_scope'])).all()
    assert len(drill)==assessment_count
    assert all(x.teacher_id!='t3' for x in drill)


def test_native_assessment_keeps_qualification_only_teachers(db,actor):
    assert {a.teacher_id for a in db.scalars(assessment_query(db,actor,{'period_id':'p'}))}=={'t1','t2','t4'}
    assert {a.teacher_id for a in db.scalars(assessment_query(db,actor,{'period_id':'p','business_scope':'true'}))}=={'t1','t2'}


def test_returned_is_independent_of_stage(db,actor):
    r=db.scalars(assessment_query(db,actor,{'returned':'true','state':'TEACHER'})).all()
    assert [a.id for a in r]==['a1']
    r=db.scalars(assessment_query(db,actor,{'returned':'false','state':'TEACHER'})).all()
    assert [a.id for a in r]==['a4']

@pytest.mark.parametrize('filters,code',[
 ({'start':'20260917'},422),({'start':'2026-02-30'},422),({'start':'2026-09-10','end':'2026-01-01'},422),
 ({'period_id':'missing'},404),({'org_id':'d2'},403),({'org_id':'missing'},403),
 ({'made_up':'x'},422),({'teacher_id':['t1']},422),({'q':'x'*101},422),
 ({'returned':'sometimes'},422),({'business_scope':'sometimes'},422),({'state':'APPROVE_ALL'},422),
])
def test_invalid_or_unauthorized_scope_fails(db,actor,filters,code):
    with pytest.raises(HTTPException) as exc:assessment_query(db,actor,filters)
    assert exc.value.status_code==code


def test_filters_never_change_scores_or_archives(db,actor,engine):
    before=[(a.id,a.score,a.version,a.state,a.archive_sha256,a.archive) for a in db.scalars(select(m.Assessment).order_by(m.Assessment.id))]
    statements=[]
    def capture(conn,cursor,statement,parameters,context,executemany):statements.append(statement.lstrip().upper())
    event.listen(engine,'before_cursor_execute',capture)
    try:
        for f in ({},{'project_code':'P1'},{'project_code':'P2'},{'teacher_id':'t1','course_code':'C3'}):stats(db,actor,f)
    finally:event.remove(engine,'before_cursor_execute',capture)
    after=[(a.id,a.score,a.version,a.state,a.archive_sha256,a.archive) for a in db.scalars(select(m.Assessment).order_by(m.Assessment.id))]
    assert before==after
    assert all(s.startswith('SELECT') for s in statements)


def test_missing_statistics_settings_not_silent_defaults(db,actor):
    db.delete(db.get(m.Setting,'metrics'));db.flush()
    with pytest.raises(HTTPException) as exc:stats(db,actor,{})
    assert exc.value.status_code==503

def test_cockpit_score_distribution_is_descriptive_and_uses_same_business_scope(db,actor):
    all_scope=stats(db,actor,{})
    assert all_scope['assessment_score_summary']['count']==2
    assert float(all_scope['assessment_score_summary']['average'])==85.0
    bands={x['label']:x['count'] for x in all_scope['assessment_score_bands']}
    assert bands['80–<90分']==2 and sum(bands.values())==2
    p1=stats(db,actor,{'project_code':'P1'})
    assert p1['assessment_score_summary']['count']==1
    assert sum(x['count'] for x in p1['assessment_score_bands'])==1
