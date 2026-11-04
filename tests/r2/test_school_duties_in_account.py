"""在“调整账号”里直接勾选学校审批职责（归口学院复审等），以及学校系统管理员首页的缺人提醒。"""
from sqlalchemy import select
from app.models import Role, Setting, Audit
from app.permissions import SCHOOL_REVIEW
from app import social_training as st
from app.identities import extras_for, identity_actor
from app.models import User
from conftest import auth, put


def _role(app2):
    with app2.state.sessions.begin() as db:
        if db.get(Role, 'role-school-review') is None:
            db.add(Role(id='role-school-review', code='school_review', name='学校业务审核', kind='school',
                        permissions=sorted(SCHOOL_REVIEW), active=True))


def _user(client, ident):
    return next(x for x in client.get('/api/users?size=200').json()['items'] if x['id'] == ident)


def _save(client, ident, extras=None, duties=None):
    x = _user(client, ident)
    body = {'name': x['name'], 'title': x['title'], 'org_id': x['org_id'], 'role_id': x['role_id'], 'active': x['active'],
            'is_admin': x['is_admin'], 'expected_version': x['version'], 'reason': '设学校审核人'}
    if extras is not None:
        body['extra_identities'] = extras
    if duties is not None:
        body['school_duties'] = duties
    return put(client, '/api/users/' + ident, body)


REVIEW = [{'role_id': 'role-school-review', 'org_id': 'school'}]


def _duties(app2):
    with app2.state.sessions.begin() as db:
        s = db.get(Setting, 'social_training_duties')
        return (dict(s.value), s.version) if s else ({}, 0)


def test_identity_and_duty_saved_together(client2, app2):
    _role(app2)
    auth(client2, 'schooladmin')
    labels = client2.get('/api/users?size=200').json()['duty_labels']
    assert 'coordinator' in labels and 'dean' not in labels  # 院长是学院一级，不在学校职责里
    r = _save(client2, 'teacher', REVIEW, ['coordinator'])
    assert r.status_code == 200, r.text
    assert _user(client2, 'teacher')['school_duties'] == ['coordinator']
    value, version = _duties(app2)
    assert value['coordinator'] == ['teacher'] and version == 1
    with app2.state.sessions.begin() as db:
        assert db.scalar(select(Audit).where(Audit.module == 'social_duties', Audit.object_id == 'social_training_duties')) is not None
        # 以学校业务审核身份办理时，确实带着归口学院复审职责（学校环节的待办按它派单）
        user = db.get(User, 'teacher')
        extra = extras_for(db, user.id)[0]
        assert 'coordinator' in st.actor_duties(db, identity_actor(db, user, extra['id']))
    # 不传 school_duties 表示不改
    assert _save(client2, 'teacher', REVIEW).status_code == 200
    assert _duties(app2)[0]['coordinator'] == ['teacher']


def test_needs_school_review_identity_and_valid_code(client2, app2):
    _role(app2)
    auth(client2, 'schooladmin')
    r = _save(client2, 'teacher', [], ['coordinator'])
    assert r.status_code == 422 and '学校业务审核' in r.json()['detail']
    assert _save(client2, 'teacher', REVIEW, ['dean']).status_code == 422
    assert _save(client2, 'teacher', REVIEW, ['no-such']).status_code == 422
    assert _duties(app2) == ({}, 0)  # 整个保存回滚，账号和职责都没改
    assert _user(client2, 'teacher')['extra_identities'] == []


def test_only_this_person_changes_and_removal_clears(client2, app2):
    _role(app2)
    with app2.state.sessions.begin() as db:
        db.add(Setting(key='social_training_duties', value={'coordinator': ['schooladmin'], 'secretary': ['schooladmin']}, version=3))
    auth(client2, 'schooladmin')
    assert _save(client2, 'teacher', REVIEW, ['coordinator', 'finance']).status_code == 200
    value, version = _duties(app2)
    assert value['coordinator'] == ['schooladmin', 'teacher'] and value['finance'] == ['teacher']
    assert value['secretary'] == ['schooladmin'] and version == 4
    # 去掉学校审核身份、清空职责：只把 teacher 移出，其他人原样保留
    assert _save(client2, 'teacher', [], []).status_code == 200
    value, _ = _duties(app2)
    assert value['coordinator'] == ['schooladmin'] and value['finance'] == [] and value['secretary'] == ['schooladmin']


def test_admin_home_alert_until_two_coordinators(client2, app2):
    _role(app2)
    auth(client2, 'schooladmin')
    alerts = client2.get('/api/portal/workbench').json()['duty_alerts']
    assert [(a['duty'], a['staff']) for a in alerts if a['duty'] == 'coordinator'] == [('coordinator', 0)]
    assert _save(client2, 'teacher', REVIEW, ['coordinator']).status_code == 200
    alerts = client2.get('/api/portal/workbench').json()['duty_alerts']
    assert [(a['duty'], a['staff']) for a in alerts if a['duty'] == 'coordinator'] == [('coordinator', 1)]
    assert client2.get('/api/users?size=200').json()['duty_staffing']['coordinator'] == 1
    assert _save(client2, 'schooladmin', duties=['coordinator']).status_code == 200  # 学校管理员主身份本身就能担任
    auth(client2, 'schooladmin')  # 调整账号后本人要重新登录
    assert not [a for a in client2.get('/api/portal/workbench').json()['duty_alerts'] if a['duty'] == 'coordinator']
    # 其他角色首页不出这条提醒
    auth(client2, 'teacher')
    assert client2.get('/api/portal/workbench').json()['duty_alerts'] == []
