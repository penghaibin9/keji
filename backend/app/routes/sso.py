"""Protocol-neutral school SSO bridge.

The real CAS/OIDC/SAML/custom protocol remains in a deployment-installed adapter.
This route owns only browser state correlation, local account binding, R11 session
creation and fail-closed authorization boundaries.
"""
from __future__ import annotations
from datetime import timedelta
from hashlib import sha256
import hmac, secrets, time
from urllib.parse import urlsplit
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select, delete
from ..models import Connection, User, Role, Org, AuthSession, Audit, Setting, utcnow
from ..core import Actor, audit, current_actor, command
from ..integrations import ADAPTERS, live_connection, transport_kwargs, configuration_hash
from ..adapters.contracts import AdapterContractError, normalize_sso_identity

router = APIRouter(prefix='/api/auth/sso', tags=['统一认证'])
_STATE_MAX_AGE = 300


def _state_cookie(settings):
    return '__Host-nd_sso_state' if settings.secure_cookie else 'nd_test_sso_state'

def _state_key(state):
    return 'ssostate:'+sha256(state.encode()).hexdigest()


def _cancel_pending_state(db, request):
    state=request.cookies.get(_state_cookie(request.app.state.settings),'')
    if not state or len(state)>128:return False
    removed=db.execute(delete(Setting).where(Setting.key==_state_key(state)))
    return removed.rowcount==1

def _consume_state(db,state,connection):
    key=_state_key(state)
    row=db.scalar(select(Setting).where(Setting.key==key).with_for_update())
    if row is None:return False
    valid=(row.value.get('expires',0)>time.time() and row.value.get('connection_hash')==configuration_hash(connection))
    removed=db.execute(delete(Setting).where(Setting.key==key))
    return valid and removed.rowcount==1


def _connection(db):
    return db.scalar(select(Connection).where(Connection.code == 'sso'))


def _adapter_context(request, db):
    connection = _connection(db)
    if not connection or not live_connection(db, connection, ADAPTERS):
        raise HTTPException(503, '学校统一认证尚未完成真实联调或当前连接不可用')
    adapter = ADAPTERS.get('sso')
    if adapter is None:
        raise HTTPException(503, '当前发布未安装学校统一认证生产适配器')
    return connection, adapter


def _adapter_kwargs(connection):
    if ADAPTERS.production:
        return transport_kwargs(connection, ADAPTERS)
    # Explicit isolated-test context; never used by production startup.
    return {'config': dict(connection.config or {}), 'credential': 'TEST_ONLY', 'timeout_seconds': 10}


def _safe_redirect_url(value: str, *, production: bool) -> str:
    parsed = urlsplit(str(value or ''))
    if not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise AdapterContractError('SSO_REDIRECT_INVALID')
    if production and parsed.scheme != 'https':
        raise AdapterContractError('SSO_REDIRECT_MUST_BE_HTTPS')
    if parsed.scheme not in {'http', 'https'}:
        raise AdapterContractError('SSO_REDIRECT_INVALID')
    return parsed.geturl()


def _identity_setting_key(identity):
    stable = str(identity.get('stable_id') or '').strip()
    return 'ssoid:' + sha256((identity.get('_issuer','')+'|'+stable).encode()).hexdigest() if stable else ''


def _candidate_users(db, identity):
    matches = []
    if identity['staff_no']:
        user = db.scalar(select(User).where(User.staff_no == identity['staff_no']))
        if user:
            matches.append(user)
    if identity['account']:
        user = db.scalar(select(User).where(User.username == identity['account']))
        if user and all(user.id != x.id for x in matches):
            matches.append(user)
    return matches


def _find_local_user(db, identity):
    """Stable external subject wins after first verified binding.

    The first binding still requires an existing unique local account. This does
    not auto-provision users or import external roles into R11 permissions.
    """
    candidates = _candidate_users(db, identity)
    if len(candidates) > 1:
        raise HTTPException(409, '统一认证身份同时匹配多个本地账号，请管理员先清理映射')
    key = _identity_setting_key(identity)
    mapping = db.get(Setting, key) if key else None
    if mapping:
        user_id = str((mapping.value or {}).get('user_id') or '')
        user = db.get(User, user_id) if user_id else None
        if not user:
            raise HTTPException(409, '统一认证稳定身份映射指向的本地账号不存在，请管理员处理')
        if candidates and candidates[0].id != user.id:
            raise HTTPException(409, '学校稳定身份与当前工号/账号字段指向不同本地人员，禁止自动改绑')
        return user, mapping
    if not candidates:
        # No automatic provisioning until the school confirms first-login policy.
        raise HTTPException(403, '统一认证已通过，但本系统尚未建立该人员账号映射，请联系学校管理员')
    return candidates[0], None


def _bind_identity(db, identity, user, mapping):
    key = _identity_setting_key(identity)
    if not key:
        return False
    value = {
        'user_id': user.id,
        'identity_digest': key.split(':', 1)[1],
        'staff_no_snapshot': identity.get('staff_no') or '',
        'account_snapshot': identity.get('account') or '',
        'org_code_snapshot': identity.get('org_code') or '',
        'last_seen_at': utcnow().isoformat(),
    }
    if mapping is None:
        db.add(Setting(key=key, value=value, version=1))
        return True
    mapping.value = value
    mapping.version += 1
    return False


def _record_rejection(db, request, reason, status=401):
    db.add(Audit(actor_id=None, actor_name='未登录', org_id=None, module='auth', object_id='sso', action='统一认证登录拒绝',
        before={}, after={'status': status}, reason=reason[:2000], result='DENIED', request_id=getattr(request.state, 'request_id', '')))


@router.get('/status')
def sso_status(request: Request):
    with request.app.state.sessions.begin() as db:
        connection = _connection(db)
        adapter = ADAPTERS.get('sso') if connection else None
        available = bool(connection and live_connection(db, connection, ADAPTERS) and adapter
            and callable(getattr(adapter, 'build_login_url', None))
            and callable(getattr(adapter, 'complete_login', None)))
        return {'available': available, 'connection_state': 'CONNECTED' if available else 'NOT_CONNECTED'}


@router.get('/start')
def sso_start(request: Request):
    cfg = request.app.state.settings
    with request.app.state.sessions.begin() as db:
        connection, adapter = _adapter_context(request, db)
        method = getattr(adapter, 'build_login_url', None)
        if not callable(method):
            raise HTTPException(503, '学校统一认证适配器尚未实现登录跳转')
        state = secrets.token_urlsafe(32)
        callback_url = cfg.public_origin + '/api/auth/sso/callback'
        try:
            result = method(state=state, callback_url=callback_url, **_adapter_kwargs(connection))
            if not isinstance(result, dict):
                raise AdapterContractError('SSO_LOGIN_URL_INVALID')
            redirect_url = _safe_redirect_url(result.get('redirect_url'), production=cfg.env == 'production')
        except AdapterContractError:
            raise HTTPException(503, '学校统一认证适配器返回无效，请联系部署人员') from None
        except Exception:
            raise HTTPException(503, '学校统一认证暂不可用，请稍后重试') from None
        db.execute(delete(Setting).where(Setting.key.like('ssostate:%'),Setting.value['expires'].as_integer()<=int(time.time())))
        db.add(Setting(key=_state_key(state),value={'expires':int(time.time())+_STATE_MAX_AGE,'connection_hash':configuration_hash(connection)},version=1))
    response = RedirectResponse(redirect_url, status_code=302)
    response.set_cookie(_state_cookie(cfg), state, max_age=_STATE_MAX_AGE, httponly=True, secure=cfg.secure_cookie,
        samesite='lax', path='/')
    return response


@router.get('/callback')
def sso_callback(request: Request):
    cfg = request.app.state.settings
    from .sso_trial import cookie_name, finish_trial
    trial_state=request.cookies.get(cookie_name(cfg),'')
    if trial_state and len(trial_state)<=128 and trial_state.isascii() and len(request.query_params)<=30:
        if any(v.isascii() and hmac.compare_digest(v,trial_state) for v in request.query_params.values()):
            return finish_trial(request)
    with request.app.state.sessions() as db:
        connection=_connection(db)
        protocol=((connection.config or {}).get('adapter') or {}) if connection else {}
        state_param=protocol.get('state_param','state') if protocol.get('protocol') in {'cas','json_ticket'} else 'state'
    state = request.query_params.get(state_param, '')
    expected = request.cookies.get(_state_cookie(cfg), '')
    if not state or len(state)>128 or not state.isascii() or not expected or len(expected)>128 or not expected.isascii() or len(request.query_params.getlist(state_param))!=1 or not hmac.compare_digest(state, expected):
        with request.app.state.sessions.begin() as db:
            if state and len(state)<=128 and state.isascii():db.execute(delete(Setting).where(Setting.key==_state_key(state)))
            _record_rejection(db, request, '统一认证回调 state 校验失败', 401)
        detail = '同一浏览器同时打开了多个登录页，请关闭其他登录页后重试' if expected and state != expected else '统一认证回调校验失败，请重新登录'
        return JSONResponse({'detail': detail, 'request_id': getattr(request.state, 'request_id', '')}, 401)

    now = utcnow(); token = None; failure = None
    with request.app.state.sessions.begin() as db:
        try:
            connection, adapter = _adapter_context(request, db)
            if not _consume_state(db,state,connection):
                raise HTTPException(401,'统一认证请求已过期或已使用，请重新登录')
            method = getattr(adapter, 'complete_login', None)
            if not callable(method):
                failure = (503, '学校统一认证适配器尚未实现登录回调', '统一认证适配器缺少 complete_login')
            else:
                callback = {str(k): str(v) for k, v in request.query_params.items()}
                callback_url = cfg.public_origin + '/api/auth/sso/callback'
                try:
                    if len(callback)>30 or any(len(v)>8192 or len(request.query_params.getlist(k))!=1 for k,v in callback.items()):raise AdapterContractError('SSO_CALLBACK_INVALID')
                    identity = normalize_sso_identity(method(callback=callback, callback_url=callback_url, **_adapter_kwargs(connection)))
                    identity['_issuer']=str((connection.config or {}).get('endpoint',''))+'|'+str(((connection.config or {}).get('adapter') or {}).get('issuer',''))
                except AdapterContractError:
                    failure = (401, '学校返回的身份信息不完整，请联系学校信息中心', '统一认证身份报文未通过本地契约校验')
                except Exception:
                    failure = (401, '学校统一认证未通过，请重新登录', '统一认证上游回调校验失败')
        except HTTPException as exc:
            failure = (exc.status_code, exc.detail, '统一认证连接或适配器当前不可用')

        if failure is None:
            if not identity['active']:
                failure = (403, '学校账号当前不可用', '统一认证账号状态为停用')
            else:
                try:
                    user, identity_mapping = _find_local_user(db, identity)
                except HTTPException as exc:
                    failure = (exc.status_code, exc.detail, '统一认证身份未建立唯一的本地账号映射')

        if failure is None and not user.active:
            failure = (403, '本系统账号当前不可用', '本地业务账号已停用')

        if failure is None:
            role, org = db.get(Role, user.role_id), db.get(Org, user.org_id)
            if not role or not org or not role.active or not org.active:
                failure = (403, '账号组织或角色配置不可用，请联系学校管理员', '本地角色或组织配置不可用')

        # Schools may supply a parent organization; authorization still uses the local organization.
        if failure is None and identity['org_code']:
            ancestor=org;seen=set()
            while ancestor and ancestor.id not in seen and len(seen)<10:
                if identity['org_code']==ancestor.code:break
                seen.add(ancestor.id)
                ancestor=db.get(Org,ancestor.parent_id) if ancestor.parent_id else None
            else:
                failure = (403, '学校组织信息与本系统权限范围尚未同步，请联系管理员', '统一认证组织与本地权限组织不一致')

        identity_binding_created = False
        if failure is None:
            try:actor=Actor(db,user,role,org,request)
            except HTTPException as exc:failure=(exc.status_code,'账号组织或授权范围不可用，请联系管理员','本地授权范围校验失败')
        if failure is None:
            identity_binding_created = _bind_identity(db, identity, user, identity_mapping)

        if failure is not None:
            _record_rejection(db, request, failure[2], failure[0])
        else:
            actor = Actor(db, user, role, org, request)
            old = request.cookies.get(cfg.cookie_name, '')
            if old:
                db.execute(delete(AuthSession).where(AuthSession.token_hash == sha256(old.encode()).hexdigest()))
            token = secrets.token_urlsafe(32)
            session = AuthSession(token_hash=sha256(token.encode()).hexdigest(), csrf=secrets.token_urlsafe(32), user_id=user.id,
                auth_version=user.auth_version, auth_method='sso', expires_at=now + timedelta(hours=cfg.session_hours), last_seen=now)
            db.add(session)
            request.state.actor_id, request.state.actor_name, request.state.org_id = user.id, user.name, user.org_id
            audit(db, actor, 'auth', user.id, '学校统一认证登录', after={
                'identity_digest': sha256((identity['stable_id'] or identity['staff_no'] or identity['account']).encode()).hexdigest(),
                'external_role_count': len(identity['external_roles']),
                'stable_identity_binding_created': identity_binding_created,
                'authorization_source': 'R11_LOCAL_ROLE_ORG',
            }, reason='学校统一身份认证完成后建立本地会话；外部角色不直接授权')
        db.flush()

    if failure is not None:
        response = JSONResponse({'detail': failure[1], 'request_id': getattr(request.state, 'request_id', '')}, failure[0])
        return response
    response = RedirectResponse(cfg.public_origin + '/', status_code=303)
    response.set_cookie(cfg.cookie_name, token, httponly=True, secure=cfg.secure_cookie, samesite='strict', path='/', max_age=cfg.session_hours * 3600)
    response.delete_cookie('nd_sso_session',path='/',secure=cfg.secure_cookie,httponly=True,samesite='strict')
    response.delete_cookie(cfg.demo_cookie_name,path='/',secure=cfg.secure_cookie,httponly=True,samesite='strict')
    response.delete_cookie(cfg.identity_cookie_name,path='/',secure=cfg.secure_cookie,httponly=True,samesite='strict')
    response.delete_cookie(_state_cookie(cfg), path='/', secure=cfg.secure_cookie, httponly=True, samesite='lax')
    return response


@router.post('/logout')
def sso_logout(request: Request):
    cfg = request.app.state.settings
    redirect_url = None
    def apply(db, actor, session):
        nonlocal redirect_url
        connection = _connection(db)
        adapter = ADAPTERS.get('sso') if connection else None
        if connection and adapter and live_connection(db, connection, ADAPTERS):
            method = getattr(adapter, 'build_logout_url', None)
            if callable(method):
                try:
                    result = method(post_logout_redirect_uri=cfg.public_origin + '/', **_adapter_kwargs(connection))
                    if isinstance(result, dict) and result.get('redirect_url'):
                        redirect_url = _safe_redirect_url(result['redirect_url'], production=cfg.env == 'production')
                except Exception:
                    # Local logout must still succeed; remote logout can be retried by user.
                    redirect_url = None
        cancelled=_cancel_pending_state(db,request)
        db.delete(session)
        audit(db, actor, 'auth', actor.id, '统一认证退出登录', after={'remote_logout_url_available': bool(redirect_url),'pending_sso_cancelled':cancelled}, reason='清理本地会话及待处理认证请求，并按学校协议提供单点退出地址')
        return {'logged_out': True, 'sso_logout_url': redirect_url}
    result = command(request, {}, None, apply, allow_password=True)
    response = JSONResponse(result)
    response.delete_cookie(_state_cookie(cfg),path='/',secure=cfg.secure_cookie,httponly=True,samesite='lax')
    response.delete_cookie('nd_sso_session',path='/',secure=cfg.secure_cookie,httponly=True,samesite='strict')
    response.delete_cookie(cfg.cookie_name, path='/', secure=cfg.secure_cookie, httponly=True, samesite='strict')
    response.delete_cookie(cfg.demo_cookie_name,path='/',secure=cfg.secure_cookie,httponly=True,samesite='strict')
    response.delete_cookie(cfg.identity_cookie_name,path='/',secure=cfg.secure_cookie,httponly=True,samesite='strict')
    return response
