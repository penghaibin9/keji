"""老师删除还没生效的记录：资质、培训课程/培训师/基地申请、培训项目申报。

规则（设计见 docs/历史版本/20261104_老师端删除功能设计.md）：
- 只删没生效的：资质草稿/被退回，申请被退回/已撤回，项目草稿/被退回且从未备案、没有培训明细。
- 审批中的先撤回再删；已通过/已入库/已备案的不能删。
- 不物理删除：状态改为 DELETED，列表默认不显示，可以恢复；删除和恢复都留办理记录。
- 只有本人（申请人、代登记人、项目负责人）能删。
"""
import uuid
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import Qualification, WorkflowEvent, Audit
from app.social_models import SocialResource, SocialProject
from conftest import auth, post, put
from test_api import qual, REASON
from test_applications import setup as app_setup, apply_course, act
from test_project_apply import setup as project_setup, teacher_project
from test_social_training import action, detail, proof


def qual_action(c, ident, operation, version=None):
    if version is None:
        version = c.get('/api/qualifications/' + ident).json()['qualification']['version']
    return post(c, '/api/qualifications/' + ident + '/actions', {'action': operation, 'expected_version': version, **REASON})


def qual_ids(c, **params):
    r = c.get('/api/qualifications', params=params)
    assert r.status_code == 200, r.text
    return [x['id'] for x in r.json()['items']]


def test_teacher_deletes_and_restores_draft_qualification(app2, client2):
    c = client2
    auth(c, 'teacher')
    q = qual(c)
    r = qual_action(c, q['id'], 'delete')
    assert r.status_code == 200, r.text
    assert r.json()['state'] == 'DELETED'
    assert q['id'] not in qual_ids(c)
    assert q['id'] in qual_ids(c, state='DELETED')
    summary = c.get('/api/qualification-summary').json()
    assert summary['total'] == sum(x['count'] for x in summary['items'])
    assert all(x['key'] != 'DELETED' for x in summary['items']) and summary['deleted'] == 1
    # 删了不能改、不能提交、不能重复登记同一张证书
    current = c.get('/api/qualifications/' + q['id']).json()['qualification']
    body = {k: current[k] for k in ('teacher_id', 'category', 'name', 'certificate_no', 'issuer', 'obtained', 'expires')}
    assert put(c, '/api/qualifications/' + q['id'], {**body, 'expected_version': current['version'], **REASON}).status_code == 409
    assert qual_action(c, q['id'], 'submit').status_code == 409
    dup = post(c, '/api/qualifications', {**body, **REASON})
    assert dup.status_code == 409 and '已删除' in dup.text
    # 别人不能恢复
    auth(c, 'schooladmin')
    assert qual_action(c, q['id'], 'restore', current['version']).status_code in (403, 404)
    auth(c, 'teacher')
    r = qual_action(c, q['id'], 'restore')
    assert r.status_code == 200, r.text
    assert r.json()['state'] == 'DRAFT'
    assert q['id'] in qual_ids(c)
    with Session(app2.state.engine) as db:
        actions = [e.action for e in db.scalars(select(WorkflowEvent).where(WorkflowEvent.object_id == q['id']).order_by(WorkflowEvent.created_at))]
        assert '删除资质' in actions and '恢复已删除资质' in actions
        assert db.get(Qualification, q['id']) is not None


def test_qualification_in_review_or_approved_cannot_be_deleted(app2, client2):
    c = client2
    auth(c, 'teacher')
    q = qual(c)
    image = __import__('test_api').png()
    up = c.post('/api/attachments/qualification/' + q['id'], headers={'Idempotency-Key': str(uuid.uuid4())},
                data={'expected_version': str(q['version']), 'reason': '上传证书'}, files={'file': ('cert.png', image, 'image/png')})
    assert up.status_code == 200, up.text
    assert qual_action(c, q['id'], 'submit').status_code == 200
    r = qual_action(c, q['id'], 'delete')
    assert r.status_code == 409 and '先撤回' in r.text
    auth(c, 'schooladmin')
    assert qual_action(c, q['id'], 'approve').status_code == 200
    auth(c, 'teacher')
    r = qual_action(c, q['id'], 'delete')
    assert r.status_code == 409 and '审核通过' in r.text


def test_teacher_deletes_withdrawn_course_application_and_can_apply_again(app2, client2):
    c = client2
    ids = app_setup(app2)
    auth(c, 'teacher')
    r = apply_course(c, ids['K1'])
    assert r.status_code == 200, r.text
    ident = r.json()['item']['id']
    original_code = r.json()['item']['code']
    assert r.json()['permissions']['delete'] is False
    r = act(c, ident, 'delete', '不想申报了')
    assert r.status_code == 409 and '先撤回' in r.text
    r = act(c, ident, 'withdraw', '先撤回')
    assert r.status_code == 200 and r.json()['permissions']['delete'] is True
    # 不是申请人不能删
    auth(c, 'collegehead')
    assert act(c, ident, 'delete', '替他删').status_code == 403
    auth(c, 'teacher')
    r = act(c, ident, 'delete', '不想申报了')
    assert r.status_code == 200, r.text
    assert r.json()['item']['state'] == 'DELETED' and r.json()['permissions']['restore'] is True
    mine = c.get('/api/applications/mine').json()
    assert ident not in [x['id'] for x in mine['items']]
    assert ident in [x['id'] for x in mine['deleted']]
    # 编号让出来了：同一门课可以重新申报
    again = apply_course(c, ids['K1'])
    assert again.status_code == 200, again.text
    assert again.json()['item']['code'] == original_code
    # 已经重新申报，旧的那份不能再恢复
    r = act(c, ident, 'restore', '恢复')
    assert r.status_code == 409 and '重新申报' in r.text
    with Session(app2.state.engine) as db:
        old = db.get(SocialResource, ident)
        assert old is not None and old.state == 'DELETED' and old.data['deleted_code'] == original_code
        assert [e.action for e in db.scalars(select(WorkflowEvent).where(WorkflowEvent.object_id == ident))].count('删除培训课程申报') == 1


def test_deleted_application_restores_to_withdrawn(app2, client2):
    c = client2
    ids = app_setup(app2)
    auth(c, 'teacher')
    ident = apply_course(c, ids['X2']).json()['item']['id']
    act(c, ident, 'withdraw', '先撤回')
    assert act(c, ident, 'delete', '删除').status_code == 200
    r = act(c, ident, 'restore', '还是要申报')
    assert r.status_code == 200, r.text
    item = r.json()['item']
    assert item['state'] == 'WITHDRAWN' and not item['code'].startswith('DEL-') and 'deleted_code' not in item['data']
    assert act(c, ident, 'submit', '重新提交').json()['item']['state'] == 'DEPT'


def test_approved_application_cannot_be_deleted(app2, client2):
    c = client2
    ids = app_setup(app2)
    auth(c, 'teacher')
    ident = apply_course(c, ids['X2']).json()['item']['id']
    for role in ('depthead', 'collegehead', 'reviewer'):
        auth(c, role)
        assert act(c, ident, 'approve').status_code == 200
    auth(c, 'teacher')
    assert c.get('/api/applications/' + ident).json()['item']['state'] == 'ACTIVE'
    r = act(c, ident, 'delete', '删除')
    assert r.status_code == 409 and '已生效' in r.text


def project_ids(c):
    return [x['id'] for x in c.get('/api/applications/mine').json()['items'] if x['type'] == 'social_project']


def test_owner_deletes_draft_project_and_restores_it(app2, client2):
    c = client2
    project_setup(app2)
    auth(c, 'teacher')
    p = teacher_project(c)
    r = action(c, 'projects', 'social_project', p['id'], 'delete')
    assert r.status_code == 200, r.text
    assert r.json()['item']['state'] == 'DELETED'
    assert p['id'] not in project_ids(c)
    assert p['id'] in [x['id'] for x in c.get('/api/applications/mine').json()['deleted']]
    ws = c.get('/api/social/workspace')
    assert ws.status_code == 200, ws.text
    assert p['id'] not in [x['id'] for x in ws.json()['projects']]
    r = action(c, 'projects', 'social_project', p['id'], 'restore')
    assert r.status_code == 200, r.text
    assert r.json()['item']['state'] == 'DRAFT'
    with Session(app2.state.engine) as db:
        obj = db.get(SocialProject, p['id'])
        assert not obj.cohort.startswith('DEL-') and 'deleted_cohort' not in obj.data


def test_project_recreated_after_delete_blocks_restore(app2, client2):
    c = client2
    project_setup(app2)
    auth(c, 'teacher')
    p = teacher_project(c)
    assert action(c, 'projects', 'social_project', p['id'], 'delete').status_code == 200
    again = teacher_project(c)
    assert again['id'] != p['id']
    r = action(c, 'projects', 'social_project', p['id'], 'restore')
    assert r.status_code == 409 and '重新建立' in r.text


def test_project_in_review_must_be_withdrawn_and_filed_project_cannot_be_deleted(app2, client2):
    c = client2
    project_setup(app2)
    auth(c, 'teacher')
    p = teacher_project(c, total_hours='16', audiences=['企业职工'], service_types=['national'], teaching_methods=['classroom', 'case'])
    proof(c, 'social_project', p['id'], p['version'])
    assert action(c, 'projects', 'social_project', p['id'], 'submit').json()['item']['state'] == 'COLLEGE'
    r = action(c, 'projects', 'social_project', p['id'], 'delete')
    assert r.status_code == 409 and '先撤回' in r.text
    r = action(c, 'projects', 'social_project', p['id'], 'withdraw')
    assert r.status_code == 200, r.text
    assert r.json()['item']['state'] == 'DRAFT'
    assert action(c, 'projects', 'social_project', p['id'], 'submit').json()['item']['state'] == 'COLLEGE'
    auth(c, 'collegehead')
    assert action(c, 'projects', 'social_project', p['id'], 'delete').status_code == 403
    assert action(c, 'projects', 'social_project', p['id'], 'approve').json()['item']['state'] == 'SUBMITTED'
    auth(c, 'reviewer')
    assert action(c, 'projects', 'social_project', p['id'], 'file').json()['item']['state'] == 'FILED'
    auth(c, 'teacher')
    r = action(c, 'projects', 'social_project', p['id'], 'delete')
    assert r.status_code == 409 and '已备案' in r.text
    # 申请重新备案后变成“重新备案补正”，也不能删
    assert action(c, 'projects', 'social_project', p['id'], 'refile').json()['item']['state'] == 'RETURNED'
    r = action(c, 'projects', 'social_project', p['id'], 'delete')
    assert r.status_code == 409 and '已备案' in r.text
