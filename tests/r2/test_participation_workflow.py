from conftest import auth, post, put
from datetime import date
from decimal import Decimal
import pytest
from sqlalchemy import select, func
from app.models import TrainingRecord,WorkflowEvent
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


@pytest.mark.parametrize('legacy',[False,True])
def test_participation_detail_keeps_flat_fields_and_only_authorized_record_events(client2,app2,legacy):
    payload={'external_key':'PART-HISTORY','teacher_id':'teacher','event_date':'2026-10-18','project_code':'PART-P','project':'合成参训项目',
             'course_code':'PART-C','course':'合成参训课程','hours':'1.25','source':'经核对人工录入','reason':'首次登记合成参训','basis':'初始签到依据'}
    auth(client2,'schooladmin')
    if legacy:
        with app2.state.sessions.begin() as db:
            item=TeacherParticipation(**{k:v for k,v in payload.items() if k not in {'reason','basis'}})
            item.event_date=date.fromisoformat(payload['event_date']);db.add(item);db.flush();ident=item.id;version=item.version
    else:
        created=post(client2,'/api/participations',payload);assert created.status_code==200,created.text
        ident=created.json()['id'];version=created.json()['version']
    other=post(client2,'/api/participations',{**payload,'external_key':'OTHER-PART-HISTORY','teacher_id':'otherteacher','reason':'OTHER-RECORD-HISTORY-SECRET'})
    assert other.status_code==200,other.text
    edit={**payload,'expected_version':version,'hours':'0','reason':'核对<签到>后更正为零','basis':'合成依据<第2号>'}
    changed=put(client2,'/api/participations/'+ident,edit);assert changed.status_code==200,changed.text
    with app2.state.sessions.begin() as db:
        db.add(WorkflowEvent(object_type='record',object_id=ident,actor_id='schooladmin',actor_name='合成管理员',org_id='school',action='其他业务',before={},after={},reason='OTHER-TYPE-HISTORY-SECRET',basis=''))
    for account in ('teacher','depthead','collegehead','schooladmin'):
        auth(client2,account)
        response=client2.get('/api/participations/'+ident);assert response.status_code==200,response.text
        item=response.json();assert item['id']==ident and item['hours']=='0.00' and item['version']==version+1
        events=item['events'];assert len(events)==(1 if legacy else 2)
        assert all(e['object_type']=='participation' and e['object_id']==ident for e in events)
        assert Decimal(events[-1]['before']['hours'])==Decimal('1.25') and Decimal(events[-1]['after']['hours'])==0
        assert events[-1]['reason']==edit['reason'] and events[-1]['basis']==edit['basis']
        assert 'OTHER-RECORD-HISTORY-SECRET' not in response.text and 'OTHER-TYPE-HISTORY-SECRET' not in response.text
    for account in ('otherteacher','otherdept'):
        auth(client2,account);assert client2.get('/api/participations/'+ident).status_code==404
