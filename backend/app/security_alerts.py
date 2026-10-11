"""12.3 summarised security notices for authorised administrators (read-only)."""
from __future__ import annotations
from datetime import timedelta
from sqlalchemy import select, func
from .models import Audit, User, Task, Setting, utcnow

DENIED_PER_USER = 5          # repeated forbidden/denied accesses by one account in the window
LOGIN_REFUSALS = 10          # refused logins (all accounts) in the window
KEY_MODULES = ('settings','roles','users','connections','organization','rules','organization_rules','integration_center','integration_intake','sync')
KEY_SKIP_ACTIONS = ('GET',)


def _threshold(db, code, default):
    """Optional override through a 3.1 system parameter (param:<code>, integer)."""
    obj = db.get(Setting, 'param:' + code)
    value = (obj.value or {}).get('value') if obj and isinstance(obj.value, dict) and obj.value.get('type') == 'int' else None
    return value if isinstance(value, int) and value > 0 else default


def security_summary(db, actor, days=7):
    actor.require_admin(); actor.require('audit.read')
    now = utcnow(); since = now - timedelta(days=days)
    denied_limit = _threshold(db, 'security_denied_threshold', DENIED_PER_USER)
    login_limit = _threshold(db, 'security_login_threshold', LOGIN_REFUSALS)
    denied_rows = db.execute(select(Audit.actor_id, Audit.actor_name, func.count(), func.max(Audit.created_at))
        .where(Audit.result == 'DENIED', Audit.created_at >= since, Audit.actor_id.is_not(None))
        .group_by(Audit.actor_id, Audit.actor_name).order_by(func.count().desc()).limit(50)).all()
    denied = []
    for uid, name, count, last in denied_rows:
        paths = db.scalars(select(Audit.object_id).where(Audit.result == 'DENIED', Audit.actor_id == uid, Audit.created_at >= since)
            .order_by(Audit.created_at.desc()).limit(5)).all()
        denied.append({'actor_id': uid, 'actor_name': name, 'count': count, 'last_at': last, 'recent_objects': list(dict.fromkeys(paths)),
                       'flagged': count >= denied_limit})
    refusals = db.scalar(select(func.count()).select_from(Audit).where(Audit.module == 'auth', Audit.action == '登录拒绝', Audit.created_at >= since)) or 0
    locked = [{'id': u.id, 'username': u.username, 'name': u.name, 'failed_attempts': u.failures, 'locked_till': u.locked_until if u.locked_until and u.locked_until > now else None}  # serial() strips 'failures'/'locked_until'
              for u in db.scalars(select(User).where((User.locked_until > now) | (User.failures > 0)).order_by(User.failures.desc()).limit(50))]
    changes = db.scalars(select(Audit).where(Audit.module.in_(KEY_MODULES), Audit.result == 'SUCCESS', Audit.created_at >= since,
        Audit.action.not_in(KEY_SKIP_ACTIONS)).order_by(Audit.created_at.desc()).limit(20)).all()
    failures = db.scalars(select(Task).where(Task.kind.in_(['sync', 'inbound_pull']), Task.state.in_(['FAILED', 'BLOCKED']),
        Task.created_at >= since).order_by(Task.created_at.desc()).limit(20)).all()
    flags = []
    if any(x['flagged'] for x in denied):flags.append(f'有账号 {days} 天内越权或被拦截访问达到 {denied_limit} 次')
    if refusals >= login_limit:flags.append(f'{days} 天内登录被拒绝 {refusals} 次')
    if any(u['locked_till'] for u in locked):flags.append('有账号因连续登录失败被临时锁定')
    notes = [f'{days} 天内有 {len(failures)} 个接口同步任务失败或被阻断（已另列入“接口同步异常”待办）'] if failures else []
    return {'window_days': days, 'generated_at': now, 'thresholds': {'denied_per_user': denied_limit, 'login_refusals': login_limit},
            'denied_by_user': denied, 'login': {'refused': refusals, 'accounts': locked},
            'key_changes': [{'id': x.id, 'created_at': x.created_at, 'actor_name': x.actor_name, 'module': x.module, 'object_id': x.object_id,
                             'action': x.action, 'reason': x.reason, 'request_id': x.request_id} for x in changes],
            'interface_failures': [{'id': t.id, 'kind': t.kind, 'state': t.state, 'error': t.error, 'created_at': t.created_at,
                                    'data_type': (t.payload or {}).get('data_type')} for t in failures],
            'flags': flags, 'notes': notes, 'alert': bool(flags)}
