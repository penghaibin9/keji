from datetime import date
from app.models import Dispute, Period, Role
from conftest import auth, post
from test_api import make_assessment, REASON


def test_blocker_details_resolution_and_confirmation(client2):
    x=make_assessment(client2);ident=x['id'];auth(client2,'teacher')
    response=post(client2,'/api/disputes',{'object_type':'assessment','object_id':ident,**REASON})
    assert response.status_code==200,response.text
    dispute=response.json()
    b=client2.get(f'/api/assessments/{ident}').json()['confirmation_blockers']
    assert b['count']==1 and b['can_view'] and not b['can_resolve']
    assert b['items'][0]['id']==dispute['id'] and b['items'][0]['reason']==REASON['reason']
    blocked=post(client2,f'/api/assessments/{ident}/actions',{'action':'confirm','expected_version':x['version'],**REASON})
    assert blocked.status_code==409
    auth(client2,'depthead')
    assert client2.get(f'/api/assessments/{ident}').json()['confirmation_blockers']['can_resolve']
    resolved=post(client2,f"/api/disputes/{dispute['id']}/resolve",{'resolution':'已核实原业务与计算依据一致','expected_version':dispute['version'],**REASON})
    assert resolved.status_code==200,resolved.text
    for actor,stage in [('teacher','DEPARTMENT'),('depthead','COLLEGE'),('collegehead','SCHOOL'),('schooladmin','READY')]:
        auth(client2,actor)
        detail=client2.get(f'/api/assessments/{ident}').json()
        assert detail['confirmation_blockers']['count']==0
        r=post(client2,f'/api/assessments/{ident}/actions',{'action':'confirm','expected_version':detail['assessment']['version'],**REASON})
        assert r.status_code==200,r.text
        assert r.json()['state']==stage


def test_blocker_scope_matches_guard_and_hides_unauthorized_details(client2,app2):
    x=make_assessment(client2);ident=x['id']
    with app2.state.sessions.begin() as db:
        db.add(Period(id='past',name='其他周期',start_date=date(2025,1,1),end_date=date(2025,12,31)));db.flush()
        for key,teacher,period,state in [('mine','teacher','period2026','OPEN'),('record','teacher',None,'OPEN'),('other','otherteacher','period2026','OPEN'),('past','teacher','past','OPEN'),('done','teacher','period2026','RESOLVED')]:
            db.add(Dispute(id=key,teacher_id=teacher,period_id=period,object_type='record' if key=='record' else 'assessment',object_id='rec1' if key=='record' else ident,reason='隔离核对原因',state=state))
    auth(client2,'depthead')
    b=client2.get(f'/api/assessments/{ident}').json()['confirmation_blockers']
    assert b['count']==2 and {i['id'] for i in b['items']}=={'mine','record'}
    auth(client2,'otherdept');assert client2.get(f'/api/assessments/{ident}').status_code==403
    with app2.state.sessions.begin() as db:
        role=db.get(Role,'role-dept');role.permissions=[p for p in role.permissions if p not in {'dispute.write','dispute.resolve'}]
    auth(client2,'depthead')
    b=client2.get(f'/api/assessments/{ident}').json()['confirmation_blockers']
    assert b=={'count':2,'items':[],'can_view':False,'can_resolve':False}
