from pathlib import Path
import os,sys,uuid
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.config import Settings
sys.path.insert(0,str(Path(__file__).parent))
from support import populate,FIXTURE_PASSWORD

def _database_url(tmp_path):
    # ND_TEST_MYSQL_URL=mysql+pymysql://user:pw@host:port runs the same tests on a throwaway MySQL database each.
    base=os.environ.get('ND_TEST_MYSQL_URL')
    if not base:return 'sqlite:///'+str(tmp_path/'r2-test.sqlite'),None
    import sqlalchemy as sa
    name='t_'+uuid.uuid4().hex[:16];server=sa.create_engine(base)
    with server.begin() as c:c.execute(sa.text(f'CREATE DATABASE {name} CHARACTER SET utf8mb4'))
    def drop():
        with server.begin() as c:c.execute(sa.text(f'DROP DATABASE IF EXISTS {name}'))
        server.dispose()
    return f'{base}/{name}?charset=utf8mb4',drop

@pytest.fixture
def app2(tmp_path,monkeypatch):
    url,drop=_database_url(tmp_path)
    if drop:
        # MySQL DATETIME has no fractional seconds and rounds up, so a row written a moment ago can look 1s in the
        # future to a worker polling immediately. Production polls every 2s; tests poll at once, so read the clock 1s late.
        from datetime import timedelta
        import app.worker as worker
        real=worker.utcnow
        monkeypatch.setattr(worker,'utcnow',lambda:real()+timedelta(seconds=1))
    cfg=Settings(env='test',database_url=url,secure_cookie=False,
       public_origin='http://testserver',allowed_hosts='testserver',storage_dir=tmp_path/'files')
    app=create_app(cfg);populate(app.state.engine)
    yield app
    if drop:app.state.engine.dispose();drop()

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
