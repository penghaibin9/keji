from pathlib import Path
import sys,uuid
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.config import Settings
sys.path.insert(0,str(Path(__file__).parent))
from support import populate,FIXTURE_PASSWORD

@pytest.fixture
def app2(tmp_path):
    cfg=Settings(env='test',database_url='sqlite:///'+str(tmp_path/'r2-test.sqlite'),secure_cookie=False,
       public_origin='http://testserver',allowed_hosts='testserver',storage_dir=tmp_path/'files')
    app=create_app(cfg);populate(app.state.engine)
    return app

@pytest.fixture
def client2(app2):
    with TestClient(app2,raise_server_exceptions=False) as c:
        c.headers['origin']='http://testserver'
        yield c

def auth(client,username):
    response=client.post('/api/auth/login',json={'username':username,'password':FIXTURE_PASSWORD})
    assert response.status_code==200,response.text
    me=client.get('/api/auth/me');assert me.status_code==200,me.text
    client.headers['x-csrf-token']=me.json()['csrf']
    return me.json()

def post(client,path,payload=None,**kw):
    headers={'Idempotency-Key':kw.pop('key',str(uuid.uuid4()))}
    headers.update(kw.pop('headers',{}))
    return client.post(path,json=payload or {},headers=headers,**kw)

def put(client,path,payload,**kw):
    return client.put(path,json=payload,headers={'Idempotency-Key':kw.pop('key',str(uuid.uuid4()))},**kw)
