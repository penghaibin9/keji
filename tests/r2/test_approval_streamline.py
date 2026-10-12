"""审批流程精简第一、二期：前端只编排原单条接口，后端校验与留痕不因此削弱。

批量办理在前端逐条调用原单条接口，这里按同样方式逐条请求，确认每条独立校验、独立留痕：
本人事项被拦、来源变化被拦、一条失败不影响其余条，归档仍校验附件并入账；多附件按版本顺序上传，
失败项不增加版本，只需补传失败项；退回补正期限口径未配置时保存成功、提交被拦。
"""
from datetime import date
from io import BytesIO
import copy
import uuid
import pytest
from PIL import Image
from sqlalchemy import select, func
from app.models import User, PointEntry, WorkflowEvent, Attachment
from app.social_models import SocialClaim, SocialUnit
from app import social_training as st
from conftest import auth, post, put
from support import HASH
from test_social_training import setup_social, row, proof, detail, action, import_rows, close_project, policy  # noqa: F401


def png(color='white'):
    image=BytesIO();Image.new('RGB',(2,2),color).save(image,format='PNG');return image.getvalue()


def upload(client,kind,ident,version,name='evidence.png',content=None,mime='image/png'):
    return client.post('/api/attachments/'+kind+'/'+ident,headers={'Idempotency-Key':str(uuid.uuid4())},
                       data={'expected_version':str(version),'reason':'审批精简多附件测试'},files={'file':(name,content if content is not None else png(),mime)})


def events(app,ident):
    with app.state.sessions() as db:
        return db.scalars(select(WorkflowEvent).where(WorkflowEvent.object_type=='social_claim',WorkflowEvent.object_id==ident).order_by(WorkflowEvent.created_at,WorkflowEvent.id)).all()


@pytest.fixture
def submitted_claims(setup_social,client2,app2,monkeypatch):
    """同一项目、同一环节（待院长初审）的多条申报，供逐条批量办理。"""
    monkeypatch.setattr(st,'today',lambda:date(2026,9,3));pid=setup_social
    assert import_rows(client2,pid,[row()]).status_code==200;close_project(client2,pid);pol=policy(client2,True)
    auth(client2,'teacher')
    r=post(client2,'/api/social/claims',{'project_id':pid,'period_id':'period2026','policy_id':pol,'recognition_form_reference':'学校制式认定表','reason':'本人申报'})
    assert r.status_code==200,r.text
    first=r.json()['item'];proof(client2,'social_claim',first['id'],first['version'])
    assert action(client2,'claims','social_claim',first['id'],'submit').status_code==200
    ids={'teacher':first['id']}
    with app2.state.sessions.begin() as db:
        extra=['batch1','batch2','batch3']
        for n,ident in enumerate(extra):
            db.add(User(id=ident,username=ident,name='批量测试教师'+str(n),staff_no='JB'+str(n),org_id='dept1',role_id='role-teacher',password_hash=HASH,must_change_password=False,active=True))
        db.flush()
        unit=db.scalar(select(SocialUnit).where(SocialUnit.project_id==pid))
        unit.data={**unit.data,'teachers':[*unit.data['teachers'],*({'teacher_id':t,'staff_type':'internal','role':'instructor'} for t in extra)]}
        db.flush()
        base=db.get(SocialClaim,first['id'])
        for ident in extra:
            claim=SocialClaim(project_id=pid,teacher_id=ident,period_id='period2026',policy_id=pol,state='SUBMITTED',data={'auxiliary':[],'recognition_form_reference':'学校制式认定表','submitted_on':'2026-09-03'})
            db.add(claim);db.flush();claim.snapshot=st.freeze(st.point_trial(db,claim));ids[ident]=claim.id
        base.snapshot=st.freeze(st.point_trial(db,base))  # 参训明细变化后按最新依据冻结
    return pid,pol,ids


def test_batch_one_failure_leaves_others_and_each_keeps_own_trail(submitted_claims,client2,app2):
    pid,pol,ids=submitted_claims
    # batch2：提交后来源变化（冻结依据与当前试算不一致），必须被 require_fresh 拦下
    with app2.state.sessions.begin() as db:
        stale=db.get(SocialClaim,ids['batch2']);trial=copy.deepcopy(stale.snapshot['trial'])
        trial['basis']['facts']['units'][0]['data']['learners']=trial['basis']['facts']['units'][0]['data']['learners'][:-1]
        stale.snapshot=st.freeze(trial)
    before={k:len(events(app2,v)) for k,v in ids.items()}
    auth(client2,'collegehead')
    results={}
    for key in ['teacher','batch1','batch2','batch3']:  # 前端批量：每条先取最新版本，再调用原单条接口
        item=detail(client2,'social_claim',ids[key])['item']
        results[key]=post(client2,'/api/social/claims/'+ids[key]+'/actions',{'action':'approve','expected_version':item['version'],'reason':'核对无误，审核通过','basis':'批量办理第1/4条'})
    assert {k:r.status_code for k,r in results.items()}=={'teacher':200,'batch1':200,'batch2':409,'batch3':200}
    assert '审批依据已变化' in results['batch2'].json()['detail']
    with app2.state.sessions() as db:
        states={k:db.get(SocialClaim,v).state for k,v in ids.items()}
    assert states=={'teacher':'DEAN','batch1':'DEAN','batch2':'SUBMITTED','batch3':'DEAN'}
    for key in ('teacher','batch1','batch3'):
        rows=events(app2,ids[key]);assert len(rows)==before[key]+1
        assert rows[-1].actor_id=='collegehead' and rows[-1].reason=='核对无误，审核通过' and rows[-1].after['state']=='DEAN'
    assert len(events(app2,ids['batch2']))==before['batch2']
    # 旧版本号（批量开始前读到的版本）不能继续办理
    old=post(client2,'/api/social/claims/'+ids['batch1']+'/actions',{'action':'approve','expected_version':1,'reason':'核对无误','basis':''})
    assert old.status_code==409


def test_self_and_conflicted_items_in_batch_are_blocked_without_trail(submitted_claims,client2,app2):
    pid,pol,ids=submitted_claims
    with app2.state.sessions.begin() as db:
        db.get(User,'collegehead').staff_no='DEAN-SELF'
        db.get(SocialClaim,ids['batch1']).teacher_id='collegehead'  # 院长本人的申报混在批量里
    before={k:len(events(app2,v)) for k,v in ids.items()}
    auth(client2,'collegehead')
    def approve(key):
        item=detail(client2,'social_claim',ids[key])['item']
        return post(client2,'/api/social/claims/'+ids[key]+'/actions',{'action':'approve','expected_version':item['version'],'reason':'核对无误，审核通过','basis':''})
    own,other=approve('batch1'),approve('batch2')
    assert own.status_code==403 and '回避' in own.json()['detail'],own.text
    assert other.status_code==200,other.text
    # 院长申报与某教师存在利益冲突后，该教师参与项目的申报一律回避
    from app.models import Setting
    with app2.state.sessions.begin() as db:
        db.add(Setting(key=st.CONFLICTS_KEY,value=[{'user_id':'collegehead','target_kind':'teacher','target_id':'batch3','target_name':'批量测试教师2','active':True}]))
    conflicted=approve('batch3')
    assert conflicted.status_code==403 and '利益冲突' in conflicted.json()['detail'],conflicted.text
    with app2.state.sessions() as db:
        assert db.get(SocialClaim,ids['batch1']).state=='SUBMITTED' and db.get(SocialClaim,ids['batch3']).state=='SUBMITTED'
        assert db.get(SocialClaim,ids['batch2']).state=='DEAN'
    assert len(events(app2,ids['batch1']))==before['batch1'] and len(events(app2,ids['batch3']))==before['batch3']
    assert len(events(app2,ids['batch2']))==before['batch2']+1


def test_batch_archive_verifies_attachments_and_books_only_successful_items(submitted_claims,client2,app2):
    pid,pol,ids=submitted_claims
    for user in ('collegehead','reviewer','vice'):
        auth(client2,user)
        for key in ('teacher','batch1'):
            r=action(client2,'claims','social_claim',ids[key],'approve');assert r.status_code==200,r.text
    with app2.state.sessions() as db:
        assert {db.get(SocialClaim,ids[k]).state for k in ('teacher','batch1')}=={'APPROVED'}
        stored=db.scalar(select(Attachment).where(Attachment.object_type=='social_claim',Attachment.object_id==ids['teacher']))
    # teacher 的认定表在磁盘上被改动：归档必须拦下且不入账；batch1 照常归档入账
    (app2.state.settings.storage_dir/stored.storage_key).write_bytes(b'tampered')
    auth(client2,'depthead')
    archive={key:action(client2,'claims','social_claim',ids[key],'approve') for key in ('teacher','batch1')}
    assert archive['teacher'].status_code==503 and archive['batch1'].status_code==200,archive['batch1'].text
    with app2.state.sessions() as db:
        assert db.get(SocialClaim,ids['teacher']).state=='APPROVED' and db.get(SocialClaim,ids['batch1']).state=='ARCHIVED'
        booked={e.item_key for e in db.scalars(select(PointEntry).where(PointEntry.kind=='SOCIAL'))}
    assert booked=={'social_teaching_'+ids['batch1'],'social_auxiliary_'+ids['batch1']}


def test_todo_archive_list_is_read_only_filter(submitted_claims,client2,app2):
    pid,pol,ids=submitted_claims
    for user in ('collegehead','reviewer','vice'):
        auth(client2,user);assert action(client2,'claims','social_claim',ids['batch1'],'approve').status_code==200
    auth(client2,'depthead')
    listed=client2.get('/api/todos?stage=archive');assert listed.status_code==200,listed.text
    items=listed.json()['items']
    assert [x['id'] for x in items if x['type']=='social_claim']==[ids['batch1']]
    assert all(x['state'] in {'待教学秘书归档','READY'} for x in items)
    assert client2.get('/api/todos?stage=approve').status_code==422
    with app2.state.sessions() as db:assert db.get(SocialClaim,ids['batch1']).state=='APPROVED'


def test_multiple_attachments_upload_in_version_order_and_only_failed_is_retried(setup_social,client2,app2,monkeypatch):
    monkeypatch.setattr(st,'today',lambda:date(2026,9,3));pid=setup_social
    assert import_rows(client2,pid,[row()]).status_code==200;close_project(client2,pid);pol=policy(client2,True)
    auth(client2,'teacher')
    r=post(client2,'/api/social/claims',{'project_id':pid,'period_id':'period2026','policy_id':pol,'recognition_form_reference':'学校制式认定表','reason':'本人申报'})
    claim=r.json()['item'];ident=claim['id'];version=claim['version']
    assert upload(client2,'social_claim',ident,version,'第1页.png',png('red')).status_code==200;version+=1
    bad=upload(client2,'social_claim',ident,version,'第2页.png',b'not really an image')
    assert bad.status_code in (415,422),bad.text
    assert detail(client2,'social_claim',ident)['item']['version']==version  # 失败项不增加版本
    assert upload(client2,'social_claim',ident,version,'第3页.png',png('blue')).status_code==200;version+=1
    assert upload(client2,'social_claim',ident,version-1,'并发.png',png('green')).status_code==409  # 旧版本不能并发上传
    assert upload(client2,'social_claim',ident,version,'第2页.png',png('black')).status_code==200;version+=1  # 只补传失败项
    names=[a['name'] for a in detail(client2,'social_claim',ident)['attachments']]
    assert sorted(names)==['第1页.png','第2页.png','第3页.png']
    with app2.state.sessions.begin() as db:
        sample=db.scalar(select(Attachment).where(Attachment.object_type=='social_claim',Attachment.object_id==ident))
        for n in range(47):
            db.add(Attachment(object_type='social_claim',object_id=ident,teacher_id='teacher',uploaded_by='teacher',name=f'占位{n}.png',storage_key=uuid.uuid4().hex+uuid.uuid4().hex,sha256=sample.sha256,size=sample.size,mime=sample.mime))
    over=upload(client2,'social_claim',ident,version,'第51份.png',png('white'))
    assert over.status_code==422 and '50' in over.json()['detail']


@pytest.mark.parametrize('mode,expected',[(None,409),('original_submission',200)])
def test_resubmit_saves_correction_and_upload_before_submit_check(setup_social,client2,app2,monkeypatch,mode,expected):
    monkeypatch.setattr(st,'today',lambda:date(2026,9,3));pid=setup_social
    assert import_rows(client2,pid,[row()]).status_code==200;close_project(client2,pid);pol=policy(client2,True,resubmission_mode=mode)
    auth(client2,'teacher')
    r=post(client2,'/api/social/claims',{'project_id':pid,'period_id':'period2026','policy_id':pol,'recognition_form_reference':'学校制式认定表','reason':'本人申报'})
    claim=r.json()['item'];proof(client2,'social_claim',claim['id'],claim['version'])
    assert action(client2,'claims','social_claim',claim['id'],'submit').status_code==200
    auth(client2,'collegehead');assert action(client2,'claims','social_claim',claim['id'],'return').status_code==200
    auth(client2,'teacher');item=detail(client2,'social_claim',claim['id'])['item']
    # 前端“保存补正并重新提交”：PUT → 上传 → submit，版本每步加一
    edit=put(client2,'/api/social/claims/'+claim['id'],{'project_id':pid,'period_id':'period2026','policy_id':pol,'recognition_form_reference':'补正后的认定表编号','auxiliary':[],'expected_version':item['version'],'reason':'按退回意见补正'})
    assert edit.status_code==200,edit.text;version=edit.json()['item']['version'];assert version==item['version']+1
    assert upload(client2,'social_claim',claim['id'],version,'补正材料.png').status_code==200
    submit=post(client2,'/api/social/claims/'+claim['id']+'/actions',{'action':'submit','expected_version':version+1,'reason':'补正后重新提交','basis':''})
    assert submit.status_code==expected,submit.text
    saved=detail(client2,'social_claim',claim['id'])
    assert saved['item']['data']['recognition_form_reference']=='补正后的认定表编号' and len(saved['attachments'])==2  # 原材料与补正材料都保留
    assert saved['item']['state']==('RETURNED' if expected==409 else 'SUBMITTED')
    if expected==409:assert '退回补正的期限口径' in submit.json()['detail']
