"""培训业务展示图片：封面、场地照片与证明材料分开，权限按记录可见范围，更换留痕且不改审批状态。"""
import io,uuid
from PIL import Image
from conftest import auth,post
from test_social_training import setup_social,detail
from app.models import Attachment
from app.social_models import SocialProject


def png(color=(20,90,200)):
    out=io.BytesIO();Image.new('RGB',(24,16),color).save(out,format='PNG');return out.getvalue()


def upload(client,target,ident,version,purpose='cover',name='封面.png',data=None,mime='image/png'):
    return client.post(f'/api/social/images/{target}/{ident}',files={'file':(name,data if data is not None else png(),mime)},
                       data={'purpose':purpose,'expected_version':str(version)},headers={'Idempotency-Key':str(uuid.uuid4())})


def test_project_cover_is_display_only_versioned_and_scoped(setup_social,app2,client2):
    pid=setup_social
    auth(client2,'schooladmin');item=detail(client2,'social_project',pid)['item'];state=item['state']
    evidence_before=len(detail(client2,'social_project',pid)['attachments'])
    r=upload(client2,'project',pid,item['version']);assert r.status_code==200,r.text
    first=r.json()['image']['id'];version=r.json()['version']
    d=detail(client2,'social_project',pid)
    assert d['item']['data']['cover_id']==first and d['item']['state']==state
    # 展示图片不进入证明材料，不能代替佐证。
    assert len(d['attachments'])==evidence_before
    assert d['events'][-1]['action']=='培训项目：更换封面'
    # 旧版本号被拒绝；更换后旧图保留但不再是当前封面。
    assert upload(client2,'project',pid,item['version']).status_code==409
    r=upload(client2,'project',pid,version,data=png((200,30,30)));assert r.status_code==200,r.text
    second=r.json()['image']['id'];assert second!=first
    with app2.state.sessions.begin() as db:
        assert db.get(Attachment,first) is not None and db.get(SocialProject,pid).data['cover_id']==second
    img=client2.get('/api/social/images/'+second)
    assert img.status_code==200 and img.headers['content-type']=='image/png' and 'inline' in img.headers['content-disposition']
    # 非图片、伪装扩展名、场地照片用在项目上，都拒绝。
    v=r.json()['version']
    assert upload(client2,'project',pid,v,name='方案.pdf',data=b'%PDF-1.4',mime='application/pdf').status_code==422
    assert upload(client2,'project',pid,v,name='假图.png',data=b'not an image').status_code==422
    assert upload(client2,'project',pid,v,purpose='photo').status_code==422
    # 其他学院看不到图片，也不能维护。
    auth(client2,'otherdept')
    assert client2.get('/api/social/images/'+second).status_code==403
    assert upload(client2,'project',pid,v).status_code==403
    # 移除只改当前引用，原图仍在。
    auth(client2,'schooladmin')
    r=post(client2,f'/api/social/images/project/{pid}/remove',{'expected_version':v,'purpose':'cover','image_id':second});assert r.status_code==200,r.text
    assert r.json()['refs']['cover_id'] is None
    assert client2.get('/api/social/images/'+second).status_code==200


def test_base_photos_limited_and_kept_after_edit(setup_social,app2,client2):
    auth(client2,'collegehead')
    body={'kind':'base','org_id':'college1','code':'IMG-B1','name':'隔离基地','recognition':'隔离认定依据','reason':'隔离登记','usages':['practice']}
    r=post(client2,'/api/social/resources',body);assert r.status_code==200,r.text
    x=r.json()['item'];version=x['version'];ids=[]
    for i in range(6):
        r=upload(client2,'resource',x['id'],version,purpose='photo',name=f'场地{i}.jpg' if i%2 else f'场地{i}.png',
                 data=None if i%2==0 else jpg(),mime='image/jpeg' if i%2 else 'image/png')
        assert r.status_code==200,r.text;version=r.json()['version'];ids.append(r.json()['image']['id'])
    assert upload(client2,'resource',x['id'],version,purpose='photo').status_code==422
    r=upload(client2,'resource',x['id'],version);assert r.status_code==200,r.text;version=r.json()['version']
    # 修改基地资料不会丢掉封面和场地照片。
    r=client2.put('/api/social/resources/'+x['id'],json={**body,'name':'隔离基地（改名）','reason':'改名','expected_version':version},headers={'Idempotency-Key':str(uuid.uuid4())})
    assert r.status_code==200,r.text
    data=r.json()['item']['data'];assert data['photo_ids']==ids and data['cover_id']
    # 同学院教师可以看图，但不能维护。
    auth(client2,'teacher')
    assert client2.get('/api/social/images/'+ids[0]).status_code==200
    assert upload(client2,'resource',x['id'],r.json()['item']['version']).status_code==403


def jpg():
    out=io.BytesIO();Image.new('RGB',(16,16),(10,120,60)).save(out,format='JPEG');return out.getvalue()


def test_workspace_summary_metrics_and_cover_reference(setup_social,client2):
    pid=setup_social
    auth(client2,'schooladmin')
    item=detail(client2,'social_project',pid)['item']
    assert upload(client2,'project',pid,item['version']).status_code==200
    w=client2.get('/api/social/workspace?section=projects').json()
    p=next(x for x in w['projects'] if x['id']==pid)
    assert p['metrics']['courses']==1 and p['metrics']['materials']>=1 and 'effective' not in p['metrics']
    assert p['data']['cover_id']
    w=client2.get('/api/social/workspace?section=courses').json()
    assert all('cover_id' in v and 'info_id' in v for v in w['course_info'].values())


def test_pending_application_images_follow_application_scope_and_remove_needs_write(setup_social,app2,client2):
    auth(client2,'teacher')
    r=post(client2,'/api/applications/bases',{'reason':'隔离基地申请','data':{'code':'IMG-APP-B1','name':'隔离申请基地','onsite':True,'recognition':'隔离依据','usages':['practice'],'established_on':'2026-02-01'}})
    assert r.status_code==200,r.text
    x=r.json()['item'];up=upload(client2,'resource',x['id'],x['version']);assert up.status_code==200,up.text
    image=up.json()['image']['id'];version=up.json()['version']
    # 申请人、本院学院负责人可见；其他学院和无关教师不可见。
    assert client2.get('/api/social/images/'+image).status_code==200
    auth(client2,'collegehead');assert client2.get('/api/social/images/'+image).status_code==200
    auth(client2,'otherdept');assert client2.get('/api/social/images/'+image).status_code==403
    # 无写权限的账号不能移除：只读角色（教研室负责人无本人申请关系）也不能维护。
    auth(client2,'depthead')
    assert post(client2,f'/api/social/images/resource/{x["id"]}/remove',{'expected_version':version,'purpose':'cover','image_id':image}).status_code in (403,404)
    # 申请人可以移除。
    auth(client2,'teacher')
    r=post(client2,f'/api/social/images/resource/{x["id"]}/remove',{'expected_version':version,'purpose':'cover','image_id':image});assert r.status_code==200,r.text


def test_workspace_metrics_hidden_from_unrelated_teacher_and_counts_voided_cohort(setup_social,app2,client2):
    pid=setup_social
    auth(client2,'schooladmin')
    w=client2.get('/api/social/workspace?section=projects').json()
    p=next(x for x in w['projects'] if x['id']==pid)
    assert p['metrics']['courses']==1 and 'effective' not in p['metrics']  # 尚未结项
    from app import social_training as st
    with app2.state.sessions.begin() as db:
        assert st.closing_effective_counts(db,[pid])=={pid:0}
        assert st.close_returned_project_ids(db,[pid])==set()


def test_closed_project_metrics_actual_values_and_visibility(setup_social,client2):
    from test_social_training import import_rows
    pid=setup_social
    auth(client2,'schooladmin')
    assert import_rows(client2,pid,[__import__('test_social_training').row('M1',30)]).status_code==200
    auth(client2,'schooladmin');pass
    from test_social_training import action
    r=action(client2,'projects','social_project',pid,'close_submit',closeout={'closed_on':'2026-09-02','outcome_report':'完整结项报告','satisfaction':'96','actual_income':'10000','funding_source':'other_training','retained':'2000','personnel':'6000','finance_reference':'财务确认凭证','location':'onsite','implicit_cost':'0','settlement_on':'2026-09-03','materials_checked':['plan','filing_form','roster','attendance','hours','process','assessment','outcomes']});assert r.status_code==200,r.text
    auth(client2,'reviewer');r=action(client2,'projects','social_project',pid,'close');assert r.status_code==200,r.text
    auth(client2,'schooladmin')
    w=client2.get('/api/social/workspace?section=projects').json()
    p=next(x for x in w['projects'] if x['id']==pid)
    assert p['state']=='CLOSED' and p['metrics']['effective']==30 and p['metrics']['actual_income']=='10000'
    auth(client2,'collegehead')
    p=next(x for x in client2.get('/api/social/workspace?section=projects').json()['projects'] if x['id']==pid)
    assert p['metrics']['effective']==30
    # 教研室看到项目，但实际人次和收入不随摘要下发。
    auth(client2,'depthead')
    w=client2.get('/api/social/workspace?section=projects').json()
    p=next((x for x in w['projects'] if x['id']==pid),None)
    assert p is None or ('effective' not in p['metrics'] and 'actual_income' not in p['metrics'])


def test_project_one_skill_and_province_fields_validate_and_roundtrip(setup_social,client2):
    from test_social_training import payload,detail
    auth(client2,'schooladmin')
    base=payload();base['data']['code']='SOC-P-NEW';base['data']['name']='新增字段项目'
    bad=post(client2,'/api/social/projects',{**base,'data':{**base['data'],'one_skill':True}});assert bad.status_code==422
    bad=post(client2,'/api/social/projects',{**base,'data':{**base['data'],'province_report':True}});assert bad.status_code==422
    ok=post(client2,'/api/social/projects',{**base,'data':{**base['data'],'one_skill':True,'target_groups':'退役军人；对接一人一技','province_report':True,'province_basis':'省文件〔2026〕12号'}})
    assert ok.status_code==200,ok.text
    d=detail(client2,'social_project',ok.json()['item']['id'])['item']['data']
    assert d['one_skill'] is True and d['province_report'] is True and d['province_basis']=='省文件〔2026〕12号' and d['target_groups']
    # 旧项目没有这些字段时仍能读取，默认为否。
    old=detail(client2,'social_project',setup_social)['item']['data']
    assert not old.get('one_skill') and not old.get('province_report')
