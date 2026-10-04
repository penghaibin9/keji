"""12.5 attachments bound to teacher/organisation assessments and sync tasks."""
import uuid
from hashlib import sha256
from sqlalchemy import select
from app.models import Audit,Attachment
from conftest import auth,post
from test_api import make_assessment,png
from test_r3_org_assessment import make_rule,calculate

REASON={'reason':'佐证上传测试','basis':'合成隔离数据'}


def upload(c,kind,ident,version,name='佐证.png',data=None):
    data=data or png()
    return c.post(f'/api/attachments/{kind}/{ident}',files={'file':(name,data,'image/png')},
        data={'reason':'绑定业务佐证','expected_version':version},headers={'Idempotency-Key':str(uuid.uuid4())})


def listing(c,kind,ident):
    return c.get('/api/attachments',params={'object_type':kind,'object_id':ident})


def test_teacher_assessment_evidence_permission_hash_and_download_audit(client2,app2):
    c=client2;x=make_assessment(c);data=png()
    auth(c,'otherteacher');assert upload(c,'assessment',x['id'],x['version']).status_code==403
    auth(c,'otherdept');assert upload(c,'assessment',x['id'],x['version']).status_code==403
    auth(c,'teacher');r=upload(c,'assessment',x['id'],x['version'],data=data);assert r.status_code==200,r.text
    item=r.json();assert item['sha256']==sha256(data).hexdigest() and 'storage_key' not in item and item['object_type']=='assessment'
    assert upload(c,'assessment',x['id'],x['version']+5).status_code==409  # stale version
    auth(c,'depthead');r=upload(c,'assessment',x['id'],x['version'],name='复核意见.png');assert r.status_code==200,r.text
    items=listing(c,'assessment',x['id']).json()['items'];assert len(items)==2
    d=c.get('/api/attachments/'+item['id']+'/download');assert d.status_code==200 and d.content==data
    auth(c,'otherdept');assert listing(c,'assessment',x['id']).status_code==403
    assert c.get('/api/attachments/'+item['id']+'/download').status_code==403
    auth(c,'otherteacher');assert c.get('/api/attachments/'+item['id']+'/download').status_code==403
    with app2.state.sessions() as db:
        assert db.scalar(select(Attachment).where(Attachment.id==item['id'])).teacher_id=='teacher'
        assert db.scalar(select(Audit).where(Audit.module=='attachments',Audit.object_id==item['id'],Audit.action=='下载业务附件',Audit.actor_id=='depthead'))
    auth(c,'teacher');detail=c.get('/api/assessments/'+x['id']).json()
    assert any(e['action']=='上传考核佐证材料' for e in detail['events'])


def test_org_assessment_and_sync_task_evidence(client2,app2):
    c=client2;auth(c,'schooladmin');make_rule(c,'dept','dept1');x=calculate(c,'dept','dept1')
    assert upload(c,'org_assessment',x['id'],x['version']).status_code==200
    auth(c,'depthead');r=upload(c,'org_assessment',x['id'],x['version'],name='教研室说明.png');assert r.status_code==200,r.text
    assert len(listing(c,'org_assessment',x['id']).json()['items'])==2
    auth(c,'otherdept');assert listing(c,'org_assessment',x['id']).status_code==403
    assert c.get('/api/attachments/'+r.json()['id']+'/download').status_code==403
    auth(c,'teacher');assert upload(c,'org_assessment',x['id'],x['version']).status_code==403
    # 同步佐证: school admin with sync.manage only.
    auth(c,'schooladmin');middle=next(m for m in c.get('/api/connections').json()['items'] if m['code']=='middle')
    task=post(c,'/api/connections/'+middle['id']+'/inbound/pull',{'data_type':'teacher_hr','mode':'FULL',**REASON});assert task.status_code==200,task.text;task=task.json()
    r=upload(c,'sync_task',task['id'],task['version'],name='对方回执.png');assert r.status_code==200,r.text
    assert c.get('/api/attachments/'+r.json()['id']+'/download').status_code==200
    assert listing(c,'sync_task',task['id']).json()['items'][0]['name']=='对方回执.png'
    auth(c,'depthead');assert upload(c,'sync_task',task['id'],task['version']).status_code==403
    assert c.get('/api/attachments/'+r.json()['id']+'/download').status_code==403
    with app2.state.sessions() as db:
        assert db.scalar(select(Audit).where(Audit.module=='sync',Audit.object_id==task['id'],Audit.action=='上传同步佐证材料'))
    # Unsupported kinds are still refused.
    auth(c,'schooladmin');assert upload(c,'records','rec1',1).status_code==422
