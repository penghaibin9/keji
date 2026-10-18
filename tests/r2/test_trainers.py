"""培训师遴选（管理办法第十五条）：校内老师教研室→学院→学校→组织人事部认定，外聘由学院登记→教务处备案，通过后进师资库。"""
from sqlalchemy.orm import Session
from app.models import User, Setting, Qualification
from conftest import auth, post
from test_social_training import HASH
from test_applications import act, todo_ids

REASON = {'reason': '提交申请'}


def setup(app2):
    with app2.state.sessions.begin() as db:
        for ident, name in (('reviewer', '继续教育学院审核人'), ('hruser', '组织人事部办理人'), ('jwcuser', '教务处办理人')):
            db.add(User(id=ident, username=ident, name=name, org_id='school', role_id='role-school', password_hash=HASH, must_change_password=False, active=True))
        db.add(Setting(key='social_training_duties', value={'coordinator': ['reviewer'], 'trainer_hr': ['hruser'], 'trainer_filing': ['jwcuser']}))


def internal(c, **kw):
    data = {'source': 'internal', 'directions': ['community', 'one_skill'], 'qualification_basis': '讲师，十年职业技能培训经验', **kw}
    return post(c, '/api/applications/trainers', {'data': data, **REASON})


def approve(c, ident, basis=''):
    item = c.get('/api/applications/' + ident).json()['item']
    return post(c, '/api/applications/' + ident + '/actions', {'action': 'approve', 'expected_version': item['version'], 'reason': '审核意见：同意', 'basis': basis})


def test_internal_trainer_goes_four_levels_and_enters_library(app2, client2):
    c = client2
    setup(app2)
    auth(c, 'teacher')
    r = internal(c)
    assert r.status_code == 200, r.text
    d = r.json()
    ident = d['item']['id']
    assert d['flow'] == 'trainer' and d['item']['state'] == 'DEPT' and d['progress']['total'] == 6
    assert [n['label'] for n in d['progress']['nodes']] == ['提交', '教研室审核', '学院审批', '学校审批', '组织人事部认定', '进入培训师资库']
    assert internal(c).status_code == 409  # 一人一单
    assert approve(c, ident).status_code == 403  # 本人不能办
    for user in ('depthead', 'collegehead', 'reviewer'):
        auth(c, user)
        assert ident in todo_ids(c)
        assert approve(c, ident).status_code == 200
    auth(c, 'jwcuser')
    assert ident not in todo_ids(c)  # 教务处不办校内培训师
    auth(c, 'hruser')
    assert ident in todo_ids(c)
    assert approve(c, ident).status_code == 422  # 认定要写文号
    r = approve(c, ident, '湘科人认〔2026〕12号')
    assert r.status_code == 200, r.text
    d = r.json()
    assert d['item']['state'] == 'ACTIVE' and d['state_label'] == '已入师资库' and d['item']['data']['filing_basis'] == '湘科人认〔2026〕12号'
    lib = c.get('/api/applications/trainers').json()
    assert [x['name'] for x in lib['items']] == ['测试教师一'] and lib['items'][0]['directions'] == ['社区公益培训', '“一人一技”专项']
    for user in ('depthead', 'collegehead', 'reviewer'):
        auth(c, user)
        assert c.get('/api/applications/trainers').json()['items'][0]['can_view_detail'] is True
        assert c.get('/api/applications/' + ident).status_code == 200


def test_internal_trainer_can_only_cite_own_approved_qualifications(app2, client2):
    c = client2
    setup(app2)
    with app2.state.sessions.begin() as db:
        from datetime import date
        db.add(Qualification(id='q-ok', teacher_id='teacher', category='职业资格', name='高级技师', certificate_no='GJ-1', issuer='人社厅', obtained=date(2020, 1, 1), state='APPROVED'))
        db.add(Qualification(id='q-draft', teacher_id='teacher', category='职业资格', name='草稿证书', certificate_no='GJ-2', issuer='人社厅', obtained=date(2020, 1, 1), state='DRAFT'))
        db.add(Qualification(id='q-other', teacher_id='collegehead', category='职业资格', name='别人的证书', certificate_no='GJ-3', issuer='人社厅', obtained=date(2020, 1, 1), state='APPROVED'))
    auth(c, 'teacher')
    assert internal(c, qualification_ids=['q-draft']).status_code == 422
    assert internal(c, qualification_ids=['q-other']).status_code == 422
    r = internal(c, qualification_ids=['q-ok'])
    assert r.status_code == 200, r.text
    assert r.json()['item']['data']['qualifications'][0]['name'] == '高级技师'
    assert ('资质', '高级技师 · 证书编号 G***1 · 人社厅') in [tuple(x) for x in r.json()['fields']]  # 证书编号在申请详情里脱敏


def test_external_trainer_registered_by_college_filed_by_academic_office(app2, client2):
    c = client2
    setup(app2)
    data = {'source': 'external', 'name': '陈外聘', 'unit': '湘茶集团', 'title': '高级技师', 'directions': ['enterprise'], 'qualification_basis': '行业协会推荐'}
    auth(c, 'teacher')
    assert post(c, '/api/applications/trainers', {'data': data, **REASON}).status_code == 403  # 老师不能登记外聘
    auth(c, 'collegehead')
    r = post(c, '/api/applications/trainers', {'data': data, **REASON})
    assert r.status_code == 200, r.text
    d = r.json()
    ident = d['item']['id']
    assert d['flow'] == 'trainer_external' and d['item']['state'] == 'JWC' and d['progress']['total'] == 3
    assert post(c, '/api/applications/trainers', {'data': data, **REASON}).status_code == 409
    auth(c, 'hruser')
    assert ident not in todo_ids(c)
    auth(c, 'jwcuser')
    assert ident in todo_ids(c)
    assert approve(c, ident).status_code == 422  # 备案要写依据
    r = approve(c, ident, '教务处备案〔2026〕3号')
    assert r.status_code == 200 and r.json()['item']['state'] == 'ACTIVE', r.text
    auth(c, 'schooladmin')
    lib = c.get('/api/applications/trainers').json()
    assert [(x['name'], x['unit'], x['source']) for x in lib['items']] == [('陈外聘', '湘茶集团', 'external')]
    assert lib['items'][0]['can_view_detail'] is True
    auth(c, 'collegehead')
    assert c.get('/api/applications/trainers').json()['items'][0]['can_view_detail'] is True
    assert c.get('/api/applications/' + ident).status_code == 200
    auth(c, 'depthead')
    assert c.get('/api/applications/trainers').json()['items'][0]['can_view_detail'] is False
    assert c.get('/api/applications/' + ident).status_code == 403


def test_return_resumes_at_hr_and_province_recommendation_is_logged(app2, client2):
    c = client2
    setup(app2)
    auth(c, 'teacher')
    ident = internal(c).json()['item']['id']
    for user in ('depthead', 'collegehead', 'reviewer'):
        auth(c, user)
        assert approve(c, ident).status_code == 200
    auth(c, 'hruser')
    item = c.get('/api/applications/' + ident).json()['item']
    r = post(c, '/api/applications/' + ident + '/actions', {'action': 'return', 'expected_version': item['version'], 'reason': '资质证明不全，请补充'})
    assert r.status_code == 200 and r.json()['item']['state'] == 'RETURNED'
    auth(c, 'teacher')
    item = c.get('/api/applications/' + ident).json()['item']
    r = post(c, '/api/applications/' + ident + '/actions', {'action': 'submit', 'expected_version': item['version'], 'reason': '已补充'})
    assert r.status_code == 200 and r.json()['item']['state'] == 'HR', r.text
    auth(c, 'hruser')
    assert approve(c, ident, '认定〔2026〕1号').status_code == 200
    auth(c, 'teacher')
    assert post(c, '/api/applications/trainers/' + ident + '/recommend', {'reason': '推荐'}).status_code == 403
    auth(c, 'reviewer')
    r = post(c, '/api/applications/trainers/' + ident + '/recommend', {'reason': '择优推荐进入省级师资库'})
    assert r.status_code == 200 and r.json()['item']['data']['recommended_province_on'], r.text
    assert c.get('/api/applications/trainers').json()['items'][0]['recommended_province_on']


def test_new_duties_configurable_and_library_closed_to_teachers(app2, client2):
    from conftest import put
    auth(client2, 'schooladmin')
    labels = client2.get('/api/social/duties').json()
    assert {'trainer_hr', 'trainer_filing'} <= set(labels['labels'])
    with app2.state.sessions.begin() as db:
        db.add(User(id='hr2', username='hr2', name='组织人事部二', org_id='school', role_id='role-school', password_hash=HASH, must_change_password=False, active=True))
    r = put(client2, '/api/social/duties', {'expected_version': labels['version'], 'assignments': {'trainer_hr': ['hr2']}, 'reason': '指定组织人事部认定人'})
    assert r.status_code == 200, r.text
    # 老师不能读师资库（含认定依据），也不能配置职责
    auth(client2, 'teacher')
    assert client2.get('/api/applications/trainers').status_code == 403


def test_trainer_materials_use_application_scope_version_and_live_file_permission(app2, client2):
    import uuid
    from app.models import Role
    from test_api import png
    c = client2
    setup(app2)
    auth(c, 'teacher')
    item = internal(c).json()['item']
    ident = item['id']
    def upload(version):
        return c.post('/api/attachments/social_resource/' + ident,
            files={'file': ('trainer-evidence.png', png(), 'image/png')},
            data={'expected_version': version, 'reason': '隔离培训师材料授权核验'},
            headers={'Idempotency-Key': str(uuid.uuid4())})
    response = upload(item['version'])
    assert response.status_code == 200, response.text
    attachment = response.json()['id']
    detail = c.get('/api/social/objects/social_resource/' + ident)
    assert detail.status_code == 200, detail.text
    assert detail.json()['state_label'] == '待教研室审核'
    assert detail.json()['item']['version'] == item['version'] + 1
    assert upload(item['version']).status_code == 409
    assert c.get('/api/attachments/' + attachment + '/download').content == png()
    for actor in ('otherteacher', 'otherdept'):
        auth(c, actor)
        assert c.get('/api/social/objects/social_resource/' + ident).status_code == 403
        assert c.get('/api/attachments/' + attachment + '/download').status_code == 403
        assert upload(item['version'] + 1).status_code == 403
    auth(c, 'depthead')
    assert c.get('/api/attachments/' + attachment + '/download').status_code == 200
    assert upload(item['version'] + 1).status_code == 409  # 本级审核人不代申请人补材料。
    with app2.state.sessions.begin() as db:
        role = db.get(Role, 'role-teacher')
        role.permissions = [p for p in role.permissions if p != 'file.write']
    auth(c, 'teacher')
    assert upload(item['version'] + 1).status_code == 403


def test_completed_trainer_materials_stay_readable_but_cannot_be_appended(app2, client2):
    import uuid
    from test_api import png
    from test_social_training import proof
    c = client2
    setup(app2)
    auth(c, 'teacher')
    item = internal(c).json()['item']
    ident = item['id']
    proof(c, 'social_resource', ident, item['version'])
    for actor in ('depthead', 'collegehead', 'reviewer'):
        auth(c, actor)
        assert approve(c, ident).status_code == 200
    auth(c, 'teacher')
    detail = c.get('/api/social/objects/social_resource/' + ident)
    assert detail.status_code == 200 and detail.json()['state_label'] == '待组织人事部认定'
    auth(c, 'hruser')
    completed = approve(c, ident, '隔离人事认定依据').json()
    assert completed['item']['state'] == 'ACTIVE'
    auth(c, 'teacher')
    before = c.get('/api/social/objects/social_resource/' + ident).json()
    assert before['state_label'] == '已入师资库' and len(before['attachments']) == 1
    original = c.get('/api/attachments/' + before['attachments'][0]['id'] + '/download').content
    assert original.startswith(b'\x89PNG')
    response = c.post('/api/attachments/social_resource/' + ident,
        files={'file': ('frozen-trainer.png', png(), 'image/png')},
        data={'expected_version': before['item']['version'], 'reason': '已办结申请不能追加'},
        headers={'Idempotency-Key': str(uuid.uuid4())})
    assert response.status_code == 409
    after = c.get('/api/social/objects/social_resource/' + ident).json()
    assert after['item']['version'] == before['item']['version']
    assert after['attachments'] == before['attachments']
    assert c.get('/api/attachments/' + before['attachments'][0]['id'] + '/download').content == original
