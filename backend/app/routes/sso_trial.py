"""Admin-owned browser SSO trial: validates identity but never creates a login session."""
from datetime import timedelta
from hashlib import sha256
from urllib.parse import urlsplit
import hmac
import os
import secrets
import time
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select, delete
from ..models import Setting, Connection, AuthSession, User, Role, Org, utcnow
from ..core import command, Actor, audit
from ..integrations import ADAPTERS, ConnectionCheck, configuration_hash, credential_fingerprint
from ..integration_center import candidate, stored, save_stored, configuration_issues
from ..integration_diagnostics import diagnostic, safe_code
from ..adapters.contracts import normalize_sso_identity, AdapterContractError
from ..sso_identity import preview_resolved_identity
from .integration_center import DraftAction, draft_for_action
from .sso import _safe_redirect_url

router = APIRouter(prefix='/api', tags=['统一认证实施试登录'])


def cookie_name(cfg):
    return '__Host-nd_sso_trial' if cfg.secure_cookie else 'nd_test_sso_trial'


def trial_key(state):
    return 'integration.sso_trial:' + sha256(state.encode()).hexdigest()


def adapter_context(item, cfg):
    adapter = ADAPTERS.get('sso')
    if not adapter or not callable(getattr(adapter, 'build_login_url', None)) or not callable(getattr(adapter, 'complete_login', None)):
        raise HTTPException(503, '尚未部署可用的统一认证适配器')
    if cfg.env == 'production' and (not ADAPTERS.is_real('sso') or not ADAPTERS.endpoint_matches(item) or not ADAPTERS.credential_matches(item)):
        raise HTTPException(503, '认证地址或凭据引用不符合部署白名单')
    credential = os.environ.get(item.config.get('secret_env', ''), '')
    if not credential:
        raise HTTPException(503, '尚未配置服务器凭据')
    return adapter, {'config': item.config, 'credential': credential, 'timeout_seconds': 10}


@router.post('/connections/{ident}/draft/login-test')
def start_trial(ident: str, data: DraftAction, request: Request):
    cfg = request.app.state.settings
    state_holder = {}
    def apply(db, a, session):
        a.require_admin()
        obj, item, row = draft_for_action(db, ident, data)
        if obj.code != 'sso':
            raise HTTPException(422, '只有统一认证使用浏览器试登录')
        if configuration_issues(item):
            raise HTTPException(422, '请先补齐认证草稿参数')
        adapter, kwargs = adapter_context(item, cfg)
        state = secrets.token_urlsafe(32)
        callback = cfg.public_origin + '/api/auth/sso/implementation-callback'
        result = adapter.build_login_url(state=state, callback_url=callback, **kwargs)
        redirect = _safe_redirect_url(result.get('redirect_url'), production=cfg.env == 'production')
        target, approved = urlsplit(redirect), urlsplit(item.config['endpoint'])
        if (target.scheme, target.hostname, target.port or 443) != (approved.scheme, approved.hostname, approved.port or 443):
            raise HTTPException(503, '试登录跳转地址不在已登记认证域名内')
        db.execute(delete(Setting).where(Setting.key.like('integration.sso_trial:%'),
            Setting.value['expires'].as_integer() <= int(time.time())))
        db.add(Setting(key=trial_key(state), value={'connection_id': ident, 'draft_version': row.version,
            'configuration_hash': configuration_hash(item), 'actor_id': a.id,
            'token_hash': session.token_hash, '_credential_sha256': credential_fingerprint(item),
            'expires': int(time.time())+300}, version=1))
        state_holder['state'] = state
        audit(db, a, 'connections', ident, '发起认证草稿浏览器试登录',
              after={'draft_version': row.version, 'session_created': False}, reason=data.reason)
        return {'redirect_url': redirect, 'callback_url': callback, 'session_created': False}
    result = command(request, data.model_dump(), 'sync.manage', apply)
    response = JSONResponse(result)
    if state_holder:
        response.set_cookie(cookie_name(cfg), state_holder['state'], max_age=300,
            httponly=True, secure=cfg.secure_cookie, samesite='lax', path='/')
    return response


def failure_response(cfg, message, status=401):
    response = JSONResponse({'detail': message, 'session_created': False}, status_code=status)
    response.delete_cookie(cookie_name(cfg), path='/', secure=cfg.secure_cookie, httponly=True, samesite='lax')
    return response


@router.get('/auth/sso/implementation-callback')
def finish_trial(request: Request):
    cfg = request.app.state.settings
    expected = request.cookies.get(cookie_name(cfg), '')
    if not expected or len(expected) > 128:
        return failure_response(cfg, '试登录请求已失效，请从实施中心重新开始')
    with request.app.state.sessions.begin() as db:
        state_row = db.scalar(select(Setting).where(Setting.key == trial_key(expected)).with_for_update())
        if state_row is None:
            return failure_response(cfg, '试登录请求已使用或不存在')
        context = dict(state_row.value)
        db.delete(state_row)
        if context.get('expires', 0) <= time.time():
            return failure_response(cfg, '试登录请求已过期')
        obj = db.get(Connection, context.get('connection_id'))
        if obj is None:
            return failure_response(cfg, '接口配置不存在', 409)
        db.scalar(select(Setting).where(Setting.key == 'integration.draft:'+obj.id)
                  .with_for_update().execution_options(populate_existing=True))
        item, row = candidate(db, obj)
        if (row is None or row.version != context['draft_version']
                or configuration_hash(item) != context['configuration_hash']
                or credential_fingerprint(item) != context['_credential_sha256']):
            return failure_response(cfg, '草稿或凭据已变化，请重新试登录', 409)
        protocol = item.config.get('adapter') or {}
        state_param = protocol.get('state_param', 'state') if protocol.get('protocol') in {'cas', 'json_ticket'} else 'state'
        params = request.query_params
        if (len(params) > 30 or len(params.getlist(state_param)) != 1
                or not hmac.compare_digest(params.get(state_param, ''), expected)
                or any(len(params.getlist(key)) != 1 or len(value) > 8192 for key, value in params.items())):
            return failure_response(cfg, '试登录回调校验未通过')
        session = db.get(AuthSession, context.get('token_hash'))
        user = db.get(User, context.get('actor_id'))
        if (not session or not user or session.user_id != user.id or not user.active
                or session.expires_at <= utcnow() or session.auth_version != user.auth_version
                or session.last_seen < utcnow()-timedelta(minutes=cfg.session_idle_minutes)):
            return failure_response(cfg, '发起试登录的管理员会话已失效')
        role, org = db.get(Role, user.role_id), db.get(Org, user.org_id)
        if not role or not org:
            return failure_response(cfg, '管理员组织或角色已失效', 403)
        try:
            a = Actor(db, user, role, org, request)
            a.require_admin()
            a.require('sync.manage')
            adapter, kwargs = adapter_context(item, cfg)
        except HTTPException:
            return failure_response(cfg, '管理员授权或部署配置已变化', 403)
        try:
            identity = normalize_sso_identity(adapter.complete_login(callback=dict(params),
                callback_url=cfg.public_origin+'/api/auth/sso/implementation-callback', **kwargs))
            preview = preview_resolved_identity(db, item.config, identity)
            passed = preview['can_login']
            code = 'VERIFIED' if passed else 'PROBE_REJECTED'
        except Exception as exc:
            passed, code = False, safe_code(exc)
            preview = {'can_login': False, 'errors': [diagnostic(code)['message']], 'session_created': False}
        mode = 'REAL' if cfg.env == 'production' and ADAPTERS.is_real('sso') else 'TEST_ONLY'
        proof = ConnectionCheck(connection_id=obj.id, configuration_hash=configuration_hash(item),
            adapter_id=str(getattr(adapter, 'adapter_id', '')), mode=mode, passed=passed,
            reason_code=code, actor_id=a.id, expires_at=utcnow()+timedelta(hours=24),
            receipt={'_draft_version': row.version, '_credential_sha256': credential_fingerprint(item),
                     'layer': 'browser_identity', 'preview': preview, 'diagnostic': diagnostic(code),
                     'session_created': False})
        db.add(proof)
        db.flush()
        row.value = {**row.value, 'check_id': proof.id}
        audit(db, a, 'connections', obj.id, '完成认证草稿浏览器试登录（未创建业务会话）',
              after={'passed': passed, 'check_id': proof.id, 'mode': mode}, reason='实施人员试登录验证')
    response = RedirectResponse(cfg.public_origin + '/#sso?tab=implementation&impl_step=tests', status_code=303)
    response.delete_cookie(cookie_name(cfg), path='/', secure=cfg.secure_cookie, httponly=True, samesite='lax')
    return response
