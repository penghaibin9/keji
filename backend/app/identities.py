"""一人多身份：账号的主身份仍是 users.role_id/org_id，兼任身份存在 settings 的一行里。

不改数据库结构（学校服务器已上线，不加迁移）。每次请求只有一个“当前身份”，
由签名的 HttpOnly Cookie 选定；没有选定或签名失效时用主身份。权限、数据范围、
审核级别都按当前身份判断，原有按角色分支的业务代码不用改。

缺负责人时的上交规则也在这里：教研室没有负责人，由学院负责人代办；学院也没有，
由学校代办。
"""
from __future__ import annotations
import hashlib
import hmac
import uuid
from fastapi import HTTPException
from sqlalchemy import select
from .models import Setting, User, Role, Org, utcnow

KEY = 'account_identities'
HEAD_KINDS = ('dept', 'college')
STAGE_KIND = {'DEPARTMENT': 'dept', 'COLLEGE': 'college', 'SCHOOL': 'school', 'READY': 'school'}
KIND_LABEL = {'teacher': '普通教师', 'dept': '教研室负责人', 'college': '学院负责人', 'school': '学校管理员'}
MAX_EXTRA_PER_USER = 6


def _row(db, lock=False):
    q = select(Setting).where(Setting.key == KEY)
    return db.scalar(q.with_for_update() if lock else q)


def all_extras(db, lock=False):
    row = _row(db, lock)
    return list((row.value or {}).get('items', [])) if row else []


def extras_for(db, user_id):
    return [x for x in all_extras(db) if x.get('user_id') == user_id]


def save_extras(db, items):
    row = _row(db, True)
    if row is None:
        db.add(Setting(key=KEY, value={'items': items}, version=1))
    else:
        row.value = {'items': items}; row.version += 1
    db.flush()


def validate_extra(db, user, role_id, org_id, staff_no):
    """Same rule as the primary identity: role level must match the organization level."""
    from .routes.admin import account_shape
    org, role = account_shape(db, org_id, role_id, staff_no)
    if role.kind == 'school':
        raise HTTPException(422, '学校管理员只能作为主身份，不能作为兼任身份')
    return org, role


def replace_user_extras(db, actor, user, wanted, reason):
    """Replace one account's extra identities; returns (before, after) for the audit."""
    items = all_extras(db, lock=True)
    before = [x for x in items if x.get('user_id') == user.id]
    keep = {(x['role_id'], x['org_id']): x for x in before}
    seen, result = set(), []
    if len(wanted) > MAX_EXTRA_PER_USER:
        raise HTTPException(422, '兼任身份最多 %d 个' % MAX_EXTRA_PER_USER)
    for w in wanted:
        pair = (w['role_id'], w['org_id'])
        if pair in seen: raise HTTPException(422, '同一角色和组织不能重复添加')
        if pair == (user.role_id, user.org_id): raise HTTPException(422, '兼任身份不能和主身份相同')
        seen.add(pair)
        org, role = validate_extra(db, user, w['role_id'], w['org_id'], user.staff_no)
        if org.id not in actor.org_ids or not set(role.permissions) <= actor.permissions:
            raise HTTPException(403, '不能分配超出本人授权的角色')
        result.append(keep.get(pair) or {'id': str(uuid.uuid4()), 'user_id': user.id, 'role_id': role.id, 'org_id': org.id,
                                         'granted_by': actor.id, 'granted_at': utcnow().isoformat(timespec='seconds'), 'reason': reason[:200]})
    save_extras(db, [x for x in items if x.get('user_id') != user.id] + result)
    return before, result


def describe(db, role_id, org_id):
    role, org = db.get(Role, role_id), db.get(Org, org_id)
    return {'role_id': role_id, 'org_id': org_id, 'role_name': role.name if role else '', 'role_kind': role.kind if role else '',
            'org_name': org.name if org else ''}


# ---- 当前身份 -------------------------------------------------------------

def cookie_name(cfg):
    return cfg.identity_cookie_name


def signed_selection(session, user, identity_id):
    payload = f'{identity_id}|{user.id}|{user.auth_version}'
    signature = hmac.new(session.csrf.encode(), (session.token_hash + '|' + payload).encode(), hashlib.sha256).hexdigest()
    return payload + '|' + signature


def selected_identity_id(request, session, user):
    raw = request.cookies.get(cookie_name(request.app.state.settings), '')
    parts = raw.split('|')
    if not raw or len(parts) != 4 or len(raw) > 300:
        return None
    # 签名不对（换了会话、刷新了校验码）就回到主身份，不会因此获得任何权限。
    if not hmac.compare_digest(raw, signed_selection(session, user, parts[0])):
        return None
    return parts[0]


def apply_selection(db, request, actor, session):
    """Narrow or switch the primary actor to the selected extra identity of the same person."""
    from .core import Actor
    actor.identity_id = None
    actor.primary_role, actor.primary_org = actor.role, actor.org
    ident = selected_identity_id(request, session, actor.user)
    if not ident:
        return actor
    extra = next((x for x in extras_for(db, actor.user.id) if x.get('id') == ident), None)
    if extra is None:
        raise HTTPException(401, '当前身份已被管理员调整，请重新登录')
    role, org = db.get(Role, extra['role_id']), db.get(Org, extra['org_id'])
    if not role or not org:
        raise HTTPException(403, '兼任身份的组织或角色已不存在，请联系学校管理员')
    switched = Actor(db, actor.user, role, org, request)
    switched.identity_id = ident
    switched.primary_role, switched.primary_org = actor.role, actor.org
    return switched


def options(db, actor):
    """Identities the signed-in person can switch between; only shown when there is more than one."""
    extras = extras_for(db, actor.user.id)
    if not extras:
        return []
    out = [{'id': '', 'primary': True, **describe(db, actor.user.role_id, actor.user.org_id)}]
    out += [{'id': x['id'], 'primary': False, **describe(db, x['role_id'], x['org_id'])} for x in extras]
    for x in out:
        x['current'] = (x['id'] or None) == getattr(actor, 'identity_id', None)
    return out


def identity_actor(db, user, identity_id, request=None):
    """Actor for one identity of a person (primary when identity_id is empty)."""
    from .core import Actor
    if identity_id:
        extra = next((x for x in extras_for(db, user.id) if x.get('id') == identity_id), None)
        if extra is None: raise HTTPException(404, '该身份不存在或已被调整，请刷新页面')
        role, org = db.get(Role, extra['role_id']), db.get(Org, extra['org_id'])
    else:
        role, org = db.get(Role, user.role_id), db.get(Org, user.org_id)
    if not role or not org: raise HTTPException(403, '身份的组织或角色已不存在')
    actor = Actor(db, user, role, org, request)
    actor.identity_id = identity_id or None
    actor.primary_role, actor.primary_org = db.get(Role, user.role_id), db.get(Org, user.org_id)
    return actor


def audit_tag(actor):
    """Extra audit field when someone acts under an extra identity."""
    if not getattr(actor, 'identity_id', None):
        return None
    return {'role': actor.role.name, 'role_kind': actor.role.kind, 'org': actor.org.name}


# ---- 组织负责人与缺位上交 -------------------------------------------------

def _usable(user, role):
    return (user is not None and user.active and not user.authorization_pending and role is not None
            and role.active and 'assessment.review' in (role.permissions or []))


def org_heads(db, kinds=HEAD_KINDS):
    """{org_id: [head, ...]} for 教研室/学院 heads, from primary and extra identities."""
    roles = {r.id: r for r in db.scalars(select(Role))}
    out = {}
    def add(user, role, org_id, identity_id):
        if role is None or role.kind not in kinds: return
        out.setdefault(org_id, []).append({'user_id': user.id, 'name': user.name, 'staff_no': user.staff_no,
            'username': user.username, 'role_kind': role.kind, 'role_name': role.name, 'identity_id': identity_id,
            'primary': identity_id is None, 'usable': _usable(user, role)})
    head_role_ids = [r.id for r in roles.values() if r.kind in kinds]
    for user in db.scalars(select(User).where(User.role_id.in_(head_role_ids or ['']))):
        add(user, roles.get(user.role_id), user.org_id, None)
    extras = [x for x in all_extras(db) if roles.get(x.get('role_id')) is not None and roles[x['role_id']].kind in kinds]
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(sorted({x['user_id'] for x in extras}) or [''])))}
    for x in extras:
        if x['user_id'] in users: add(users[x['user_id']], roles.get(x['role_id']), x['org_id'], x['id'])
    for heads in out.values():
        heads.sort(key=lambda h: (not h['usable'], h['staff_no'] or '', h['name']))
    return out


def head_user_ids(db, kind, org_ids=None):
    """Users who are usable heads of the given level (optionally limited to some organizations)."""
    wanted = set(org_ids) if org_ids is not None else None
    return {h['user_id'] for org_id, heads in org_heads(db, (kind,)).items()
            if wanted is None or org_id in wanted for h in heads if h['usable']}


def _has_head(heads, org_id, kind, exclude_user):
    return any(h['usable'] and h['role_kind'] == kind and h['user_id'] != exclude_user for h in heads.get(org_id, []))


def org_map(db):
    """All organizations by id; the tree is small, so one query replaces a lookup per teacher."""
    return {o.id: o for o in db.scalars(select(Org))}


def teacher_orgs(db, user_ids):
    """{user_id: SimpleNamespace(id, org_id)} in a few batched queries (stage_handler needs nothing else)."""
    from types import SimpleNamespace
    ids, out = sorted({i for i in user_ids if i}), {}
    for i in range(0, len(ids), 500):
        for uid, org_id in db.execute(select(User.id, User.org_id).where(User.id.in_(ids[i:i + 500]))):
            out[uid] = SimpleNamespace(id=uid, org_id=org_id)
    return out


def stage_handler(db, teacher, state, heads=None, orgs=None):
    """Which level handles this assessment stage for this teacher, after vacancy fallback.

    Returns (kind, acting_for) where acting_for names the vacant level that was handed up, or None.
    Pass heads/orgs (org_heads, org_map) when handling many teachers so nothing is queried per teacher.
    """
    kind = STAGE_KIND.get(state)
    if kind not in HEAD_KINDS or teacher is None:
        return kind, None
    heads = org_heads(db) if heads is None else heads
    get = orgs.get if orgs is not None else db.get
    org = get(teacher.org_id) if orgs is not None else db.get(Org, teacher.org_id)
    dept = org if org is not None and org.kind == 'dept' else None
    college = (get(dept.parent_id) if orgs is not None else db.get(Org, dept.parent_id)) if dept is not None else (org if org is not None and org.kind == 'college' else None)
    if kind == 'dept':
        if dept is not None and _has_head(heads, dept.id, 'dept', teacher.id):
            return 'dept', None
        kind, vacant = 'college', 'dept'
    else:
        vacant = None
    if college is not None and _has_head(heads, college.id, 'college', teacher.id):
        return 'college', vacant
    return 'school', vacant or 'college'


VACANCY_LABEL = {'dept': '代缺位教研室负责人办理', 'college': '代缺位学院负责人办理'}
