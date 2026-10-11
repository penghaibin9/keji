"""教研室发现已归档积分有误：核对单 → 教师回应 → 更正单走原审批，或学院裁定。"""
from decimal import Decimal
from sqlalchemy import select
from app.models import PointEntry
from conftest import auth, post
from test_social_training import setup_social, recognized, detail, action, proof  # noqa: F401


def review(client,claim_id,**over):
    r=post(client,'/api/social/point-reviews',{'claim_id':claim_id,'period_id':'period2026','teaching':'-0.56','auxiliary':'0','reason':'按签到表核实，授课多计','basis':'签到表',**over})
    return r


def sent_review(client,claim_id):
    # 发起人是教学秘书，核对流程须另有无需回避的秘书负责最终归档。
    from app.models import Setting
    with client.app.state.sessions.begin() as db:
        setting=db.get(Setting,'social_training_duties')
        setting.value={**setting.value,'secretary':['depthead','schooladmin']}
    auth(client,'depthead');r=review(client,claim_id);assert r.status_code==200,r.text
    item=r.json()['item'];assert item['state']=='DRAFT'
    assert action(client,'point-reviews','social_resource',item['id'],'send').status_code==409
    proof(client,'social_resource',item['id'],item['version'])
    r=action(client,'point-reviews','social_resource',item['id'],'send');assert r.status_code==200,r.text
    assert r.json()['item']['state']=='TEACHER'
    return item['id']


def test_teacher_agrees_and_correction_goes_through_approvals(recognized,client2,app2):
    claim_id,_=recognized
    auth(client2,'teacher');assert review(client2,claim_id).status_code==403
    ident=sent_review(client2,claim_id)
    assert review(client2,claim_id).status_code==409
    auth(client2,'teacher')
    r=post(client2,'/api/social/corrections',{'claim_id':claim_id,'period_id':'period2026','teaching':'-0.56','auxiliary':'0','decision_reference':'另行更正','reason':'核对期间另提更正'})
    assert r.status_code==409,r.text
    r=action(client2,'point-reviews','social_resource',ident,'agree');assert r.status_code==200,r.text
    item=r.json()['item'];assert item['state']=='CLOSED' and item['data']['outcome']=='corrected'
    fix=item['data']['correction_id']
    c=detail(client2,'social_resource',fix)
    assert c['item']['state']=='SUBMITTED' and c['item']['data']['created_by']=='depthead'
    auth(client2,'depthead');assert review(client2,claim_id).status_code==409
    with app2.state.sessions() as db:
        from app.routes.calculations import st_reviews
        assert st_reviews(db,'teacher')
    auth(client2,'collegehead');r=action(client2,'corrections','social_resource',fix,'return');assert r.status_code==200,r.text
    auth(client2,'depthead');item=detail(client2,'social_resource',fix)['item']
    r=client2.put('/api/social/corrections/'+fix,json={'claim_id':claim_id,'period_id':'period2026','teaching':'-5','auxiliary':'0','decision_reference':'改分','reason':'改分','expected_version':item['version']},headers={'Idempotency-Key':'edit-'+fix})
    assert r.status_code==409,r.text
    assert action(client2,'corrections','social_resource',fix,'submit').status_code==200
    for user in ('collegehead','reviewer','vice'):
        auth(client2,user);r=action(client2,'corrections','social_resource',fix,'approve');assert r.status_code==200,r.text
    auth(client2,'depthead');assert action(client2,'corrections','social_resource',fix,'approve').status_code==403
    with app2.state.sessions.begin() as db:
        from app.models import Setting
        s=db.get(Setting,'social_training_duties');s.value={**s.value,'secretary':['schooladmin']}
    auth(client2,'schooladmin');r=action(client2,'corrections','social_resource',fix,'approve');assert r.status_code==200,r.text
    with app2.state.sessions() as db:
        assert sum(db.scalars(select(PointEntry.amount).where(PointEntry.kind=='SOCIAL',PointEntry.teacher_id=='teacher')))==Decimal('1.00')
        from app.routes.calculations import st_reviews
        assert not st_reviews(db,'teacher')


def test_teacher_explains_and_dean_rules(recognized,client2,app2):
    claim_id,_=recognized
    ident=sent_review(client2,claim_id)
    auth(client2,'collegehead');assert action(client2,'point-reviews','social_resource',ident,'dismiss').status_code==409
    auth(client2,'teacher');r=action(client2,'point-reviews','social_resource',ident,'explain');assert r.status_code==200 and r.json()['item']['state']=='COLLEGE'
    auth(client2,'depthead');assert action(client2,'point-reviews','social_resource',ident,'uphold').status_code==403
    auth(client2,'collegehead');r=action(client2,'point-reviews','social_resource',ident,'dismiss');assert r.status_code==200,r.text
    assert r.json()['item']['data']['outcome']=='kept'
    ident=sent_review(client2,claim_id)
    auth(client2,'depthead');r=action(client2,'point-reviews','social_resource',ident,'withdraw');assert r.status_code==200 and r.json()['item']['data']['outcome']=='withdrawn'
    ident=sent_review(client2,claim_id)
    auth(client2,'teacher');action(client2,'point-reviews','social_resource',ident,'explain')
    auth(client2,'collegehead');r=action(client2,'point-reviews','social_resource',ident,'uphold');assert r.status_code==200,r.text
    fix=r.json()['item']['data']['correction_id']
    assert detail(client2,'social_resource',fix)['item']['state']=='DEAN'
    auth(client2,'collegehead');assert action(client2,'corrections','social_resource',fix,'approve').status_code==403
    auth(client2,'depthead');assert review(client2,claim_id).status_code==409
    auth(client2,'teacher');r=post(client2,'/api/social/corrections',{'claim_id':claim_id,'period_id':'period2026','teaching':'-0.56','auxiliary':'0','decision_reference':'另行更正','reason':'重复更正'})
    assert r.status_code==409,r.text


def test_other_department_cannot_review_and_open_review_blocks_assessment(recognized,client2,app2):
    claim_id,_=recognized
    auth(client2,'otherdept');assert review(client2,claim_id).status_code in (403,404)
    auth(client2,'depthead');draft=review(client2,claim_id).json()['item']
    auth(client2,'teacher');assert client2.get('/api/social/objects/social_resource/'+draft['id']).status_code==404
    assert all(x['id']!=draft['id'] for x in client2.get('/api/social/workspace?section=recognition').json().get('resources',[]))
    auth(client2,'depthead');assert action(client2,'point-reviews','social_resource',draft['id'],'withdraw').status_code==200
    sent_review(client2,claim_id)
    from app.routes.calculations import st_reviews
    with app2.state.sessions() as db:
        assert len(st_reviews(db,'teacher'))==1 and not st_reviews(db,'otherteacher')


def test_duplicate_messages_only_for_unique_conflicts(app2):
    import asyncio
    from types import SimpleNamespace
    from sqlalchemy.exc import IntegrityError
    handler=app2.exception_handlers[IntegrityError]
    req=SimpleNamespace(state=SimpleNamespace(request_id='t'))
    def msg(text):return asyncio.run(handler(req,IntegrityError('x',{},Exception(text)))).body.decode()
    assert '项目编号已经存在' in msg('UNIQUE constraint failed: social_projects.code')
    assert '来源编号' in msg('duplicate key value violates unique constraint "uq_social_resources_code"\nDETAIL: Key (code)=(course-1) already exists.')
    assert '关联关系冲突' in msg('FOREIGN KEY constraint failed social_projects')


def test_teacher_sees_review_first_in_mine_and_todo_counts(recognized,client2,monkeypatch):
    # 老师端：教研室发来的积分核对出现在“个人培训 · 需要我处理”，统一待办按类别给出数量。
    claim_id,_=recognized
    ident=sent_review(client2,claim_id)
    auth(client2,'teacher')
    mine=client2.get('/api/social/mine?year=2026').json()
    hit=[r for r in mine['reminders'] if r['id']=='social_resource|'+ident]
    assert hit and hit[0]['action']=='todo' and '核对' in hit[0]['text']
    assert mine['claim_ready']['policy'] and mine['claim_ready']['projects']>=1 and mine['claim_ready']['reason']==''
    todos=client2.get('/api/todos').json()
    assert todos['counts'].get('social_resource')==1
    assert client2.get('/api/todos?type=qualification').json()['counts']==todos['counts']
    auth(client2,'otherteacher')
    other=client2.get('/api/social/mine?year=2026').json()
    assert other['claim_ready']['projects']==0 and '还没有可申报的项目' in other['claim_ready']['reason']
    assert not any(r['action']=='todo' for r in other['reminders'])
    # “能不能申报”的数字要和申报表里能选的项目一致，教研室主任等兼课人员也一样按本人参训算。
    from app import social_training as st_mod
    real=st_mod.participated_project_ids
    monkeypatch.setattr(st_mod,'participated_project_ids',lambda db,uid:real(db,'teacher'))
    for user in ('teacher','otherteacher','depthead','collegehead'):
        auth(client2,user)
        m=client2.get('/api/social/mine?year=2026')
        if m.status_code!=200 or not (m.json().get('sections') or {}).get('points'):continue
        options=client2.get('/api/social/project-options?mine=true')
        assert options.status_code==200 and m.json()['claim_ready']['projects']==options.json()['total'],user
