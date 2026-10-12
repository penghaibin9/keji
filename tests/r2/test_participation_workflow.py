from conftest import auth, post, put
from sqlalchemy import select, func
from app.models import TrainingRecord
from app.reference_data import TeacherParticipation


def test_participation_create_correct_scope_and_teaching_separation(client2, app2):
    payload = {'external_key':'GAP-LEARN','teacher_id':'teacher','event_date':'2026-10-11',
               'project_code':'GAP-P','project':'隔离参训','course_code':'GAP-C','course':'学习课程',
               'hours':'8','source':'经核对人工录入','reason':'隔离参训登记','basis':'合成依据'}
    with app2.state.sessions() as db:
        before = db.execute(select(func.count(), func.sum(TrainingRecord.hours), func.sum(TrainingRecord.income))).one()
    auth(client2,'teacher')
    assert post(client2,'/api/participations',payload).status_code == 403
    auth(client2,'depthead')
    r=post(client2,'/api/participations',payload);assert r.status_code==200,r.text
    item=r.json();ident=item['id']
    assert post(client2,'/api/participations',payload).status_code==409
    for actor in ['teacher','depthead','collegehead','schooladmin']:
        auth(client2,actor);assert client2.get('/api/participations/'+ident).status_code==200
    for actor in ['otherteacher','otherdept']:
        auth(client2,actor);assert client2.get('/api/participations/'+ident).status_code==404
    auth(client2,'collegehead')
    edit={**payload,'expected_version':item['version'],'hours':'9','reason':'更正合成参训学时'}
    r=put(client2,'/api/participations/'+ident,edit)
    assert r.status_code==200,r.text
    assert put(client2,'/api/participations/'+ident,edit).status_code==409
    with app2.state.sessions() as db:
        assert db.execute(select(func.count(), func.sum(TrainingRecord.hours), func.sum(TrainingRecord.income))).one()==before
        assert db.get(TeacherParticipation,ident).hours==9
