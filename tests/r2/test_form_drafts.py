import pytest
from sqlalchemy import select,func
from app.models import FormDraft,User
from app.social_models import SocialProject,SocialResource
from conftest import auth,put,post


def payload(c,kind='project',key='new:first',version=0,values=None):
    owner=c.get(f'/api/form-drafts/{kind}',params={'context_key':key}).json()['owner']
    return {'owner':owner,'expected_version':version,'title':'未填完的合成资料',
            'values':values or {'name':'半份项目','start_date':'2026-02-30','expected_income':''},
            'files':{'proof_files':['方案.pdf']},'auxiliary':[]}


def save(c,data,kind='project',key='new:first'):
    return put(c,f'/api/form-drafts/{kind}?context_key={key}',data)


def test_partial_draft_does_not_create_business_and_survives_relogin(app2,client2):
    c=client2;auth(c,'teacher')
    with app2.state.sessions() as db:
        before=(db.scalar(select(func.count()).select_from(SocialProject)),db.scalar(select(func.count()).select_from(SocialResource)))
    body=payload(c);response=save(c,body)
    assert response.status_code==200,response.text
    assert response.json()['draft']['payload']['values']['start_date']=='2026-02-30'
    auth(c,'teacher')
    read=c.get('/api/form-drafts/project?context_key=new:first').json()
    assert read['version']==1 and read['draft']['payload']['values']['expected_income']==''
    with app2.state.sessions() as db:
        assert before==(db.scalar(select(func.count()).select_from(SocialProject)),db.scalar(select(func.count()).select_from(SocialResource)))
    assert post(c,'/api/social/projects',{'data':body['values'],'reason':'未完成申报'}).status_code==422


def test_drafts_do_not_cross_user_role_org_or_business_kind(app2,client2):
    c=client2;auth(c,'teacher');assert save(c,payload(c)).status_code==200
    auth(c,'otherteacher')
    assert c.get('/api/form-drafts/project?context_key=new:first').json()['draft'] is None
    assert c.get('/api/form-drafts?kind=project').json()['total']==0
    auth(c,'teacher')
    assert c.get('/api/form-drafts/course?context_key=new:first').json()['draft'] is None
    with app2.state.sessions.begin() as db:
        u=db.get(User,'teacher');role=u.role_id;org=u.org_id;u.role_id='role-college';u.org_id='college1'
    auth(c,'teacher')
    assert c.get('/api/form-drafts/project?context_key=new:first').json()['draft'] is None
    with app2.state.sessions.begin() as db:
        u=db.get(User,'teacher');u.role_id=role;u.org_id=org
    auth(c,'teacher')
    assert c.get('/api/form-drafts/project?context_key=new:first').json()['draft'] is not None


def test_stale_identity_and_versions_never_overwrite_or_finish_another_draft(app2,client2):
    c=client2;auth(c,'teacher');body=payload(c)
    assert save(c,body).status_code==200
    assert save(c,{**body,'values':{'name':'另一个窗口'}}).status_code==409
    update={**body,'expected_version':1,'values':{'name':'第二版'}}
    assert save(c,update).status_code==200
    assert post(c,'/api/form-drafts/project/finish?context_key=new:first',{'owner':body['owner'],'expected_version':1,'action':'complete'}).status_code==409
    auth(c,'schooladmin')
    assert save(c,body).status_code==409
    with app2.state.sessions() as db:
        rows=db.scalars(select(FormDraft)).all()
        assert len(rows)==1 and rows[0].version==2 and rows[0].payload['values']['name']=='第二版'


def test_multiple_new_forms_and_paging_are_independent_and_soft_finished(app2,client2):
    c=client2;auth(c,'teacher')
    first=payload(c,key='new:one',values={'name':'第一份'});second=payload(c,key='new:two',values={'name':'第二份'})
    assert save(c,first,key='new:one').status_code==200
    assert save(c,second,key='new:two').status_code==200
    listing=c.get('/api/form-drafts?kind=project&prefix=new:&size=1').json()
    assert listing['total']==2 and len(listing['items'])==1
    assert len(c.get('/api/form-drafts?kind=project&prefix=new:&size=1&page=2').json()['items'])==1
    assert c.get('/api/form-drafts?kind=project&prefix=%25').json()['items']==[]
    result=post(c,'/api/form-drafts/project/finish?context_key=new:one',{'owner':first['owner'],'expected_version':1,'action':'complete'})
    assert result.status_code==200 and result.json()['draft'] is None
    assert c.get('/api/form-drafts?kind=project').json()['total']==1
    with app2.state.sessions() as db:
        row=db.scalar(select(FormDraft).where(FormDraft.context_key=='new:one'))
        assert row.state=='COMPLETED' and row.payload['values']['name']=='第一份'
    assert post(c,'/api/form-drafts/project/finish?context_key=new:two',{'owner':second['owner'],'expected_version':1,'action':'discard'}).status_code==200


@pytest.mark.parametrize('change',['password','owner','nested','file_path','huge','unknown_kind'])
def test_drafts_reject_secrets_unbounded_values_and_invalid_shapes(client2,change):
    c=client2;auth(c,'teacher');data=payload(c)
    if change=='password':data['values']['password']='must-not-be-echoed'
    if change=='owner':data['values']['user_id']='schooladmin'
    if change=='nested':data['values']['name']={'secret':'must-not-be-echoed'}
    if change=='file_path':data['files']['proof_files']=['C:\\private\\secret.pdf']
    if change=='huge':data['values']['name']='a'*20001
    response=save(c,data,kind='settings' if change=='unknown_kind' else 'project')
    assert response.status_code==422,response.text
    assert 'must-not-be-echoed' not in response.text


def test_own_certificate_draft_is_not_masked_and_other_identity_cannot_read(client2):
    c=client2;auth(c,'teacher')
    body=payload(c,kind='qualification',values={'name':'证书','certificate_no':'CERT-ONLY-MINE','_long_term':True})
    body['files']={}
    response=save(c,body,kind='qualification')
    assert response.status_code==200,response.text
    assert response.json()['draft']['payload']['values']['certificate_no']=='CERT-ONLY-MINE'
    auth(c,'depthead')
    assert c.get('/api/form-drafts/qualification?context_key=new:first').json()['draft'] is None


def test_claim_rows_are_saved_without_fake_scores_or_dates(client2):
    c=client2;auth(c,'teacher')
    body=payload(c,kind='claim',values={'period_id':'','policy_id':'','reason':'未填完'})
    body['auxiliary']=[{'work_date':'','amount':'','description':'只写了工作说明'}]
    response=save(c,body,kind='claim')
    assert response.status_code==200,response.text
    assert response.json()['draft']['payload']['auxiliary']==body['auxiliary']


def test_same_request_key_cannot_replay_a_different_draft_context(client2):
    c=client2;auth(c,'teacher');body=payload(c)
    key='draft-context-replay-check'
    first='/api/form-drafts/project?context_key=new:one'
    second='/api/form-drafts/project?context_key=new:two'
    assert put(c,first,body,key=key).status_code==200
    assert put(c,first,body,key=key).status_code==200
    assert put(c,second,body,key=key).status_code==409
    assert c.get(second).json()['draft'] is None
    finish={'owner':body['owner'],'expected_version':1,'action':'complete'}
    assert post(c,'/api/form-drafts/project/finish?context_key=new:one',finish,key=key+'-finish').status_code==200
    assert post(c,'/api/form-drafts/project/finish?context_key=new:two',finish,key=key+'-finish').status_code==409
