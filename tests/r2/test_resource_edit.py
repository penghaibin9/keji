"""资源补正走正常权限、版本与审计；只用隔离合成数据。"""
from conftest import auth,post,put
from test_social_training import setup_social
from app.social_models import SocialResource


def test_resource_edit_scope_version_identity_and_history(setup_social,client2,app2):
    body={'kind':'achievement','org_id':'college1','code':'EDIT-A1','name':'隔离成果','recognition':'隔离认定依据','reason':'隔离登记'}
    auth(client2,'collegehead');r=post(client2,'/api/social/resources',body);assert r.status_code==200,r.text
    x=r.json()['item'];assert r.json()['state_label']=='待补认定日期'
    edit={**body,'expected_version':x['version'],'confirmed_on':'2026-10-11','name':'隔离补正成果','reason':'补齐日期'}
    auth(client2,'otherdept');assert put(client2,'/api/social/resources/'+x['id'],edit).status_code in (403,404)
    auth(client2,'depthead');assert put(client2,'/api/social/resources/'+x['id'],edit).status_code==403
    auth(client2,'teacher');assert put(client2,'/api/social/resources/'+x['id'],edit).status_code==403
    auth(client2,'collegehead');assert put(client2,'/api/social/resources/'+x['id'],{**edit,'org_id':'college2'}).status_code==422
    r=put(client2,'/api/social/resources/'+x['id'],edit);assert r.status_code==200,r.text
    assert r.json()['item']['data']['confirmed_on']=='2026-10-11' and r.json()['state_label']=='已登记'
    assert r.json()['events'][-1]['action']=='补正培训资源资料'
    assert put(client2,'/api/social/resources/'+x['id'],edit).status_code==409
    with app2.state.sessions.begin() as db:
        obj=db.get(SocialResource,x['id']);obj.data={**obj.data,'auto':True}
    edit['expected_version']=r.json()['item']['version']
    assert put(client2,'/api/social/resources/'+x['id'],edit).status_code==409


def test_course_resource_edit_preserves_import_metadata_and_rechecks_course(setup_social,client2,app2):
    auth(client2,'collegehead')
    body={'kind':'course_resource','org_id':'college1','code':'EDIT-C1','name':'隔离视频','recognition':'隔离课程依据','course_code':'SOC-C1','resource_type':'video','duration_minutes':'10','teacher_id':'teacher','reason':'登记课程资源'}
    r=post(client2,'/api/social/resources',body);assert r.status_code==200,r.text
    x=r.json()['item']
    with app2.state.sessions.begin() as db:
        obj=db.get(SocialResource,x['id']);obj.data={**obj.data,'source':'chaoxing','video_count':12}
    edit={**body,'expected_version':x['version'],'duration_minutes':'12.5'}
    assert put(client2,'/api/social/resources/'+x['id'],{**edit,'course_code':'not-a-course'}).status_code==422
    r=put(client2,'/api/social/resources/'+x['id'],edit);assert r.status_code==200,r.text
    assert r.json()['item']['data']['video_count']==12 and r.json()['item']['data']['source']=='chaoxing'


def test_school_public_reports_stay_in_recognition_and_obey_pagination(app2,client2):
    with app2.state.sessions.begin() as db:
        db.add(SocialResource(kind='base',org_id='college1',code='BASE-SCOPE',name='隔离基地',data={'onsite':True}))
        db.add(SocialResource(kind='point_report',org_id='school',code='REPORT-SCOPE',name='全校积分公示',state='ARCHIVED',data={'rows':[]}))
    auth(client2,'teacher')
    for section in ['bases','courses','outcomes']:
        r=client2.get('/api/social/workspace',params={'section':section});assert r.status_code==200,r.text
        assert all(x['kind']!='point_report' for x in r.json()['resources'])
    r=client2.get('/api/social/workspace',params={'section':'recognition'}).json()
    assert [x['kind'] for x in r['resources']]==['point_report'] and r['resource_pagination']['total']==1
    r=client2.get('/api/social/workspace',params={'section':'recognition','resource_page':2}).json()
    assert r['resources']==[] and r['resource_pagination']['total']==1
