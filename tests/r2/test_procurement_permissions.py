"""采购第2项：角色批量授权与多账号同步生效的隔离回归。"""
from contextlib import ExitStack

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import Audit, Role, User
from conftest import auth, post, put


REASON = {'reason': '采购第2项专项核验', 'basis': '采购清单第2项第7至8条'}


def test_one_role_update_applies_to_all_bound_accounts_without_individual_edits(client2, app2):
    auth(client2, 'schooladmin')
    copied = post(client2, '/api/roles', {
        'code': 'procurement_teacher',
        'name': '采购核验教师角色',
        'copy_from': 'role-teacher',
        **REASON,
    })
    assert copied.status_code == 200, copied.text
    role = copied.json()
    original_permissions = list(role['permissions'])

    with app2.state.sessions.begin() as db:
        source = db.get(User, 'teacher')
        for ident in ('procurement-teacher-1', 'procurement-teacher-2'):
            db.add(User(
                id=ident,
                username=ident,
                name='采购权限核验账号',
                staff_no=ident,
                org_id='dept1',
                role_id=role['id'],
                password_hash=source.password_hash,
                active=True,
                is_admin=False,
                must_change_password=False,
            ))

    with ExitStack() as stack:
        account_clients=[]
        for username in ('procurement-teacher-1', 'procurement-teacher-2'):
            account = stack.enter_context(TestClient(app2, raise_server_exceptions=False))
            account.headers['origin']='http://testserver'
            auth(account, username)
            assert account.get('/api/records').status_code == 200
            account_clients.append(account)

        reduced = put(client2, f"/api/roles/{role['id']}", {
            'expected_version': role['version'],
            'active': True,
            'permissions': ['portal.read'],
            **REASON,
        })
        assert reduced.status_code == 200, reduced.text
        assert all(account.get('/api/records').status_code == 403 for account in account_clients)

        restored = put(client2, f"/api/roles/{role['id']}", {
            'expected_version': reduced.json()['version'],
            'active': True,
            'permissions': original_permissions,
            **REASON,
        })
        assert restored.status_code == 200, restored.text
        assert all(account.get('/api/records').status_code == 200 for account in account_clients)

    with app2.state.sessions() as db:
        assert all(db.get(User, ident).role_id == role['id'] for ident in (
            'procurement-teacher-1', 'procurement-teacher-2'))
        changes = db.scalars(select(Audit).where(
            Audit.module == 'roles',
            Audit.object_id == role['id'],
            Audit.action == '调整角色授权',
        )).all()
        assert len(changes) == 2
        assert all(change.before is not None and change.after is not None for change in changes)


def test_copied_teacher_role_cannot_be_escalated_to_school_permissions(client2):
    auth(client2, 'schooladmin')
    copied = post(client2, '/api/roles', {
        'code': 'procurement_no_escalation',
        'name': '不可越级教师角色',
        'copy_from': 'role-teacher',
        **REASON,
    }).json()
    response = put(client2, f"/api/roles/{copied['id']}", {
        'expected_version': copied['version'],
        'active': True,
        'permissions': list(copied['permissions']) + ['users.manage'],
        **REASON,
    })
    assert response.status_code == 403

