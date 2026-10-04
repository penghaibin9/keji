"""Read-only preview using the exact identity parser used by real SSO login."""
from .adapters.sso_configurable import ConfigurableSsoAdapter
from .adapters.contracts import normalize_sso_identity, AdapterContractError
from .integration_diagnostics import diagnostic, safe_code


def preview_identity(db, config, payload):
    from fastapi import HTTPException
    from .models import Role, Org
    from .core import Actor
    from .routes.sso import _find_local_user
    adapter = (config or {}).get('adapter') or {}
    try:
        identity = normalize_sso_identity(ConfigurableSsoAdapter()._identity(payload, adapter))
    except AdapterContractError as exc:
        detail = diagnostic(safe_code(exc))
        return {'mapped': {}, 'errors': [detail['message']], 'diagnostic': detail,
                'can_login': False, 'binding': None, 'session_created': False}
    return preview_resolved_identity(db, config, identity)


def preview_resolved_identity(db, config, identity):
    from fastapi import HTTPException
    from .models import Role, Org
    from .core import Actor
    from .routes.sso import _find_local_user
    adapter = config.get('adapter') or {}
    identity = dict(identity)
    identity['_issuer'] = str(config.get('endpoint', '')) + '|' + str(adapter.get('issuer', ''))
    errors = []
    binding = None
    if not identity['active']:
        errors.append('学校账号已停用，真实登录将被拒绝')
    try:
        user, existing = _find_local_user(db, identity)
        role, org = db.get(Role, user.role_id), db.get(Org, user.org_id)
        if not role or not org:
            raise HTTPException(403, '本地组织或角色未配置')
        actor = Actor(db, user, role, org)
        if identity['org_code'] and identity['org_code'] != org.code:
            errors.append('学校组织与本地组织不一致，必须先完成调岗或映射核对')
        binding = {'account': user.username, 'name': user.name, 'organization': org.name,
                   'org_code': org.code, 'role': role.name, 'role_kind': role.kind,
                   'scope': {'teacher': '仅本人', 'dept': '本教研室', 'college': '本学院', 'school': '学校授权范围'}[role.kind],
                   'permissions': sorted(actor.permissions), 'already_bound': existing is not None,
                   'external_roles_grant_permissions': False}
    except HTTPException as exc:
        errors.append(str(exc.detail))
    identity.pop('_issuer', None)
    return {'mapped': identity, 'errors': errors, 'can_login': not errors,
            'binding': binding, 'session_created': False}
