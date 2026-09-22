"""Real canonical SQLite/API controls; never labelled real MySQL acceptance."""
import json,os,subprocess,sys,uuid
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'backend')]
from delivery.seed import populate
from delivery.common import load_private,Blocked
from app.config import Settings
from app.main import create_app

class APIClient:
    def __init__(self,app,events):
        self.c=TestClient(app,base_url='https://127.0.0.1:18443',raise_server_exceptions=False);self.csrf='';self.events=events
    def call(self,method,path,body=None,*,expected=200,key=None,**kw):
        headers={'Origin':'https://127.0.0.1:18443','X-CSRF-Token':self.csrf,'Idempotency-Key':key or str(uuid.uuid4())}
        r=self.c.request(method,path,json=body,headers=headers)
        self.events.append({'method':method,'path':path,'status':r.status_code})
        if r.status_code!=expected:raise RuntimeError(f'{method} {path}: {r.status_code} {r.text[:350]}')
        return r.json()
    def upload(self,path,data,filename,content_type,fields=None,*,key=None):
        r=self.c.post(path,data=fields,files={'file':(filename,data,content_type)},headers={'Origin':'https://127.0.0.1:18443','X-CSRF-Token':self.csrf,'Idempotency-Key':key or str(uuid.uuid4())})
        self.events.append({'method':'POST','path':path,'status':r.status_code})
        if r.status_code!=200:raise RuntimeError(f'{path}: {r.status_code} {r.text[:350]}')
        return r.json()

@pytest.fixture(scope='module')
def populated(tmp_path_factory):
    lab=tmp_path_factory.mktemp('r11-synthetic-controls');db=lab/'db.sqlite';secret=lab/'initial_password'
    password='SyntheticOnly-'+str(uuid.uuid4());secret.write_text(password);secret.chmod(0o600)
    env={k:v for k,v in os.environ.items() if not k.startswith('ND_')};env.update(PYTHONPATH=str(ROOT/'backend'),ND_ENV='test',ND_DATABASE_URL='sqlite:///'+str(db),ND_STORAGE_DIR=str(lab/'files'),ND_PUBLIC_ORIGIN='https://127.0.0.1:18443',ND_SCHOOL_NAME='跃科非学历教育体验学校（合成演示数据）',ND_SECURE_COOKIE='true')
    for args in (['alembic','upgrade','head'],['app.cli','init','--password-file',str(secret)]):
        r=subprocess.run([sys.executable,'-m',*args],cwd=ROOT/'backend',env=env,capture_output=True)
        assert r.returncode==0,r.stderr.decode()[:500]
    (lab/'files').mkdir(exist_ok=True)
    app=create_app(Settings(env='test',database_url=env['ND_DATABASE_URL'],storage_dir=lab/'files',public_origin=env['ND_PUBLIC_ORIGIN'],allowed_hosts='127.0.0.1',secure_cookie=True))
    events=[];clients=[]
    def factory(role):
        c=APIClient(app,events);clients.append(c);return c
    result=populate(factory,lab,password,'sqlite-control-installation',asset_dir=ROOT/'delivery/assets')
    yield {'lab':lab,'app':app,'events':events,'factory':factory,'result':result,'password':password}
    for c in clients:c.c.close()
    app.state.engine.dispose()

def test_counts_are_real_api_reads(populated):
    assert populated['result']['counts']=={'users':9,'records':33,'participations':25,'qualifications':6,'assessments':7,'notices':3}

def test_repeated_bootstrap_is_read_only(populated):
    before=len(populated['events'])
    second=populate(populated['factory'],populated['lab'],populated['password'],'sqlite-control-installation')
    assert second['repeated_run']=='READ_ONLY_NO_RESEED';assert len(populated['events'])==before

def auth(pop,role):
    c=pop['factory'](role);cr=load_private(pop['lab']/'accounts.private.json')[role]
    c.call('POST','/api/auth/login',cr);me=c.call('GET','/api/auth/me');c.csrf=me['csrf'];return c

def test_scope_and_pagination(populated):
    teacher=auth(populated,'teacher');dept=auth(populated,'dept');college=auth(populated,'college');other=auth(populated,'other')
    assert teacher.call('GET','/api/records')['total']==25
    assert teacher.call('GET','/api/participations')['total']==23
    assert len(teacher.call('GET','/api/participations?page=2&size=20')['items'])==3
    assert dept.call('GET','/api/records')['total']==27
    assert college.call('GET','/api/records')['total']==29
    assert other.call('GET','/api/records')['total']==2
    teacher.call('GET','/api/users',expected=403)
    teacher.call('GET','/api/qualifications/'+populated['result']['other_qualification_id'],expected=403)

def test_current_workflow_and_historical_archive(populated):
    c=auth(populated,'teacher');r=populated['result']
    assert c.call('GET','/api/assessments/'+r['primary_assessment'])['assessment']['state']=='TEACHER'
    assert c.call('GET','/api/assessments/'+r['historical_assessment'])['assessment']['state']=='ARCHIVED'
    assert c.call('GET','/api/qualifications/'+r['qualification_returned'])['qualification']['state']=='RETURNED'

def test_documented_scores_and_main_dispute_flow(populated):
    from decimal import Decimal
    r=populated['result'];teacher=auth(populated,'teacher');dept=auth(populated,'dept')
    assessment=teacher.call('GET','/api/assessments/'+r['primary_assessment'])['assessment']
    assert Decimal(str(assessment['score']))==Decimal('92.33')
    points=teacher.call('GET','/api/points?period_id='+r['period_id'])
    assert Decimal(str(points['sum']))==Decimal('195.10')
    reason={'reason':'合成演示流程核验','basis':'测试结果不替代浏览器和学校验收'}
    teacher.call('POST','/api/assessments/'+assessment['id']+'/actions',{'action':'confirm','expected_version':assessment['version'],**reason},expected=409)
    dispute=dept.call('GET','/api/disputes/'+r['dispute_id'])['dispute']
    dept.call('POST','/api/disputes/'+r['dispute_id']+'/resolve',{'resolution':'合成来源已解释，保持原值不变','expected_version':dispute['version'],**reason})
    for role,next_state in [('teacher','DEPARTMENT'),('dept','COLLEGE'),('college','SCHOOL'),('school','READY')]:
        c=auth(populated,role);a=c.call('GET','/api/assessments/'+assessment['id'])['assessment']
        got=c.call('POST','/api/assessments/'+a['id']+'/actions',{'action':'confirm','expected_version':a['version'],**reason})
        assert got['state']==next_state
    c=auth(populated,'school');a=c.call('GET','/api/assessments/'+assessment['id'])['assessment']
    got=c.call('POST','/api/assessments/'+a['id']+'/actions',{'action':'archive','expected_version':a['version'],**reason})
    assert got['state']=='ARCHIVED'
    assert c.call('GET','/api/assessments/'+a['id'])['immutable'] is True

def test_import_samples_good_bad_and_idempotence(populated):
    c=auth(populated,'school');assets=ROOT/'delivery/assets';mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    for filename,errors in [('02_培训业务_错误样本.xlsx',1),('01_培训业务_正确样本.xlsx',0)]:
        j=c.upload('/api/imports/records/preview',(assets/filename).read_bytes(),filename,mime)
        assert j['errors']==errors
        assert c.call('GET','/api/records')['total']==33
        if errors:c.call('POST','/api/imports/'+j['id']+'/confirm',{'expected_version':j['version'],'reason':'合成错误导入应阻断'},expected=409)
        else:
            key=str(uuid.uuid4());body={'expected_version':j['version'],'reason':'演示Excel明确确认'}
            receipt=c.call('POST','/api/imports/'+j['id']+'/confirm',body,key=key)
            assert c.call('POST','/api/imports/'+j['id']+'/confirm',body,key=key)==receipt
            assert c.call('GET','/api/records')['total']==35

def test_credentials_private_and_no_fixed_passwords(populated):
    p=populated['lab']/'accounts.private.json';assert p.stat().st_mode&0o077==0
    cr=load_private(p);passwords=[v['password'] for v in cr.values()]
    assert len(passwords)==9 and len(set(passwords))==9 and all(len(p)>=30 for p in passwords)

def test_external_connections_remain_unconfigured(populated):
    c=auth(populated,'school');connections=c.call('GET','/api/connections')['items']
    assert len(connections)==3 and all(x['state']=='NOT_CONNECTED' and x['config'].get('endpoint')=='' for x in connections)
