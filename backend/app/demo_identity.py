"""Explicit demo-only delegation, bound to an authenticated admin session.

The primary session remains owned by admin. The signed HttpOnly selection only
narrows the effective actor to one of three existing demonstration accounts.
No passwords or administrative permissions are transferred to those accounts.
"""
import hashlib
import hmac
from fastapi import HTTPException
from sqlalchemy import select
from .models import User, Role, Org

IDENTITIES = {
    'admin': ('school', '学校管理员'),
    'show_teacher': ('teacher', '教师本人'),
    'show_dept': ('dept', '教研室负责人'),
    'show_college': ('college', '二级学院负责人'),
}


def enabled_for(cfg, actor):
    return (cfg.demo_identity_switch_enabled and actor.user.username == 'admin'
            and actor.user.is_admin and actor.role.kind == 'school'
            and not actor.user.must_change_password)


def target_actor(db, controller, username, request, *, write=False):
    from .core import Actor
    if username not in IDENTITIES:
        raise HTTPException(403, '该账号不在演示身份授权范围')
    query = select(User).where(User.username == username)
    user = db.scalar(query.with_for_update() if write else query)
    if not user or not user.active or user.must_change_password:
        raise HTTPException(403, '演示账号不可用，请联系管理员')
    role, org = db.get(Role, user.role_id), db.get(Org, user.org_id)
    if (not role or not org or role.kind != IDENTITIES[username][0]
            or org.id not in controller.org_ids):
        raise HTTPException(403, '演示账号身份或学校范围已变化')
    return Actor(db, user, role, org, request)


def signed_selection(session, actor):
    payload = f'{actor.user.username}|{actor.id}|{actor.user.auth_version}'
    signature = hmac.new(session.csrf.encode(),
                         (session.token_hash + '|' + payload).encode(), hashlib.sha256).hexdigest()
    return payload + '|' + signature


def resolve(db, request, controller, session, *, write=False):
    cfg = request.app.state.settings
    selection = request.cookies.get(cfg.demo_cookie_name, '')
    if not selection:
        if enabled_for(cfg, controller):
            controller.demo_controller = controller
        return controller
    if not enabled_for(cfg, controller):
        raise HTTPException(403, '演示切换授权已失效，请重新登录')
    parts = selection.split('|')
    if len(parts) != 4 or len(selection) > 240:
        raise HTTPException(401, '演示身份已失效，请重新登录')
    actor = target_actor(db, controller, parts[0], request, write=write)
    if not hmac.compare_digest(selection, signed_selection(session, actor)):
        raise HTTPException(401, '演示身份已失效，请重新登录')
    actor.demo_controller = controller
    return actor


def options(actor):
    if not getattr(actor, 'demo_controller', None):
        return None
    return {'current': actor.user.username,
            'options': [{'username': username, 'label': label}
                        for username, (_, label) in IDENTITIES.items()]}
