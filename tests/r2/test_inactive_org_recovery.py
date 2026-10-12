from conftest import auth,post
from app.models import Org


def test_inactive_org_remains_recoverable_without_expanding_business_scope(client2,app2):
    with app2.state.sessions.begin() as db:
        db.add(Org(id='other-school',code='OTHER-S',name='别校',kind='school'))
        db.flush()
        db.add(Org(id='other-inactive',code='OTHER-C',name='别校停用学院',kind='college',parent_id='other-school',active=False))
    auth(client2,'schooladmin')
    r=post(client2,'/api/organizations/college1/state',{'action':'disable','expected_version':1,'reason':'隔离停用恢复验证'})
    assert r.status_code==200,r.text
    items=client2.get('/api/organizations').json()['items'];ids={x['id'] for x in items}
    assert 'college1' in ids and 'dept1' not in ids and 'other-inactive' not in ids
    assert client2.get('/api/records?teacher_id=teacher').json()['total']==0
    auth(client2,'otherdept')
    assert 'college1' not in {x['id'] for x in client2.get('/api/organizations').json()['items']}
    auth(client2,'schooladmin')
    r=post(client2,'/api/organizations/college1/state',{'action':'enable','expected_version':r.json()['version'],'reason':'隔离恢复组织'})
    assert r.status_code==200,r.text
    assert client2.get('/api/records?teacher_id=teacher').json()['total']==1
