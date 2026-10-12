"""Reusable, fail-closed helpers for deployment-installed integration adapters.

No helper in this module grants application permissions. It only prepares and
validates external protocol requests/responses after the school/province has
provided the formal specification.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from typing import Any
from urllib.parse import urlencode

from .contracts import AdapterContractError


_MISSING = object()

def matches_value(actual, allowed):
    # JSON false must never compare equal to the numeric success code zero.
    return isinstance(allowed,list) and any(type(actual) is type(v) and actual==v for v in allowed)
_CREDENTIAL_KEY = re.compile(r'^[A-Za-z][A-Za-z0-9_.-]{0,79}$')
_PLACEHOLDER = re.compile(r'^\$\{([A-Za-z][A-Za-z0-9_]*)\}$')
_INLINE_PLACEHOLDER = re.compile(r'\$\{([A-Za-z][A-Za-z0-9_]*)\}')


def parse_credential(raw: str) -> dict[str, str]:
    """Parse a secret env value without ever logging it.

    Plain text means ``{"token": value}``; JSON objects are useful when a
    protocol needs client_id/client_secret/app_id/signing_key together.
    """
    value = str(raw or '')
    if not value or len(value) > 32768:
        raise AdapterContractError('CREDENTIAL_INVALID')
    if value.lstrip().startswith('{'):
        try:
            obj = json.loads(value)
        except Exception:
            raise AdapterContractError('CREDENTIAL_JSON_INVALID') from None
        if not isinstance(obj, dict) or not 1 <= len(obj) <= 40:
            raise AdapterContractError('CREDENTIAL_JSON_INVALID')
        out: dict[str, str] = {}
        for key, item in obj.items():
            key = str(key)
            if not _CREDENTIAL_KEY.fullmatch(key) or isinstance(item, (dict, list)):
                raise AdapterContractError('CREDENTIAL_JSON_INVALID')
            text = str(item if item is not None else '')
            if len(text) > 8192:
                raise AdapterContractError('CREDENTIAL_JSON_INVALID')
            out[key] = text
        return out
    return {'token': value}


def credential_value(credentials: dict[str, str], key: str, *, required: bool = True) -> str:
    name = str(key or '').strip()
    if not _CREDENTIAL_KEY.fullmatch(name):
        raise AdapterContractError('CREDENTIAL_KEY_INVALID')
    value = str(credentials.get(name, ''))
    if required and not value:
        raise AdapterContractError('CREDENTIAL_FIELD_MISSING')
    return value


def path_get(value: Any, path: str, default: Any = _MISSING) -> Any:
    """Safe dotted-path extraction with integer list indexes; no expressions."""
    text = str(path or '').strip()
    if text in {'', '$'}:
        return value
    current = value
    for piece in text.split('.'):
        if not piece or len(piece) > 100:
            raise AdapterContractError('RESPONSE_PATH_INVALID')
        if isinstance(current, dict) and piece in current:
            current = current[piece]
        elif isinstance(current, list) and piece.isdigit() and int(piece) < len(current):
            current = current[int(piece)]
        else:
            if default is _MISSING:
                raise AdapterContractError('RESPONSE_PATH_MISSING')
            return default
    return current


def expand_template(value: Any, context: dict[str, Any], *, depth: int = 0) -> Any:
    """Expand a small allow-listed placeholder language in JSON-like config."""
    if depth > 8:
        raise AdapterContractError('ADAPTER_TEMPLATE_TOO_DEEP')
    if isinstance(value, dict):
        if len(value) > 100:
            raise AdapterContractError('ADAPTER_TEMPLATE_TOO_LARGE')
        out = {}
        for key, item in value.items():
            key = str(key)
            if not key or len(key) > 120:
                raise AdapterContractError('ADAPTER_TEMPLATE_INVALID')
            expanded = expand_template(item, context, depth=depth + 1)
            if expanded is not _MISSING:
                out[key] = expanded
        return out
    if isinstance(value, list):
        if len(value) > 100:
            raise AdapterContractError('ADAPTER_TEMPLATE_TOO_LARGE')
        return [expand_template(item, context, depth=depth + 1) for item in value]
    if isinstance(value, str):
        match = _PLACEHOLDER.fullmatch(value)
        if match:
            return context.get(match.group(1), _MISSING)
        def repl(found):
            item = context.get(found.group(1), '')
            if isinstance(item, (dict, list)):
                raise AdapterContractError('ADAPTER_TEMPLATE_OBJECT_INLINE')
            return '' if item is None else str(item)
        return _INLINE_PLACEHOLDER.sub(repl, value)
    return value


def encode_query(path: str, params: dict[str, Any] | None) -> str:
    route = str(path or '').strip()
    if not route or '://' in route or route.startswith('//'):
        raise AdapterContractError('ADAPTER_PATH_INVALID')
    cleaned = []
    for key, value in (params or {}).items():
        if value is _MISSING or value is None or value == '':
            continue
        if isinstance(value, (dict, list)):
            raise AdapterContractError('QUERY_VALUE_INVALID')
        cleaned.append((str(key), str(value)))
    if not cleaned:
        return route
    return route + ('&' if '?' in route else '?') + urlencode(cleaned)


def json_bytes(payload: Any) -> bytes:
    try:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    except Exception:
        raise AdapterContractError('REQUEST_JSON_INVALID') from None


def normalized_bool(value: Any, *, true_values=None, false_values=None, default=_MISSING) -> bool:
    if type(value) is bool:
        return value
    true_values = [True, 1, '1', 'true', 'TRUE', 'yes', 'YES', 'active', 'ACTIVE', '启用'] if true_values is None else true_values
    false_values = [False, 0, '0', 'false', 'FALSE', 'no', 'NO', 'inactive', 'INACTIVE', '停用'] if false_values is None else false_values
    if matches_value(value,true_values):
        return True
    if matches_value(value,false_values):
        return False
    if default is not _MISSING and type(default) is bool:
        return default
    raise AdapterContractError('BOOLEAN_VALUE_INVALID')


def list_value(value: Any, *, delimiter: str = ',') -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        items = value
    elif isinstance(value, str):
        items = value.split(delimiter) if delimiter else [value]
    else:
        items = [value]
    out = []
    for item in items:
        text = str(item).strip()
        if text and len(text) <= 100 and text not in out:
            out.append(text)
    if len(out) > 50:
        raise AdapterContractError('LIST_VALUE_TOO_LARGE')
    return out


def timestamp_value(mode: str = 'unix_seconds') -> str:
    now = time.time()
    if mode == 'unix_seconds':
        return str(int(now))
    if mode in {'unix_millis', 'unix_milliseconds'}:
        return str(int(now * 1000))
    if mode == 'iso8601':
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    raise AdapterContractError('TIMESTAMP_MODE_INVALID')


def apply_credential_bindings(headers: dict, query: dict, body: dict | None,
                              bindings: list | None, credentials: dict[str, str]):
    for binding in bindings or []:
        if not isinstance(binding, dict):
            raise AdapterContractError('CREDENTIAL_BINDING_INVALID')
        source = str(binding.get('source', '')).strip()
        target = str(binding.get('target', '')).strip()
        name = str(binding.get('name', '')).strip()
        if target not in {'header', 'query', 'body'} or not name or len(name) > 120:
            raise AdapterContractError('CREDENTIAL_BINDING_INVALID')
        value = credential_value(credentials, source)
        if target == 'header':
            headers[name] = value
        elif target == 'query':
            query[name] = value
        else:
            if body is None or not isinstance(body, dict):
                raise AdapterContractError('CREDENTIAL_BODY_BINDING_INVALID')
            body[name] = value


def apply_auth(headers: dict, query: dict, body: Any, auth: dict | None,
               credentials: dict[str, str], *, method: str, path: str,
               idempotency_key: str = '') -> dict[str, str]:
    """Apply common token/basic/HMAC schemes using secret-env values only."""
    cfg = auth or {'mode': 'none'}
    if not isinstance(cfg, dict):
        raise AdapterContractError('AUTH_CONFIG_INVALID')
    mode = str(cfg.get('mode', 'none')).strip().lower()
    if mode == 'none':
        return {}
    if mode == 'bearer':
        token = credential_value(credentials, cfg.get('credential_key', 'token'))
        headers[str(cfg.get('header', 'Authorization'))] = str(cfg.get('prefix', 'Bearer ')) + token
        return {}
    if mode == 'header':
        headers[str(cfg.get('header', 'X-Api-Key'))] = credential_value(credentials, cfg.get('credential_key', 'token'))
        return {}
    if mode == 'basic':
        user = credential_value(credentials, cfg.get('username_key', 'client_id'))
        password = credential_value(credentials, cfg.get('password_key', 'client_secret'))
        headers['Authorization'] = 'Basic ' + base64.b64encode((user + ':' + password).encode()).decode()
        return {}
    if mode not in {'hmac_sha256','signature'}:
        raise AdapterContractError('AUTH_MODE_UNSUPPORTED')

    def put(target, name, value):
        target = str(target or 'header')
        name = str(name or '').strip()
        if not name or target not in {'header', 'query', 'body'}:
            raise AdapterContractError('HMAC_FIELD_TARGET_INVALID')
        if target == 'header':
            headers[name] = value
        elif target == 'query':
            query[name] = value
        else:
            if not isinstance(body, dict):
                raise AdapterContractError('HMAC_BODY_TARGET_REQUIRES_OBJECT')
            body[name] = value

    secret = credential_value(credentials, cfg.get('secret_key', 'secret'))
    ts = timestamp_value(str(cfg.get('timestamp_mode', 'unix_seconds')))
    nonce = secrets.token_hex(16)
    app_id = credential_value(credentials, cfg.get('app_id_key', 'app_id'), required=False)

    put(cfg.get('timestamp_target', 'header'), cfg.get('timestamp_name', cfg.get('timestamp_header', 'X-Timestamp')), ts)
    put(cfg.get('nonce_target', 'header'), cfg.get('nonce_name', cfg.get('nonce_header', 'X-Nonce')), nonce)
    if app_id and cfg.get('app_id_name', cfg.get('app_id_header')):
        put(cfg.get('app_id_target', 'header'), cfg.get('app_id_name', cfg.get('app_id_header')), app_id)
    if idempotency_key and cfg.get('idempotency_name', cfg.get('idempotency_header')):
        put(cfg.get('idempotency_target', 'header'), cfg.get('idempotency_name', cfg.get('idempotency_header')), idempotency_key)

    body_hash = hashlib.sha256(json_bytes(body) if body is not None else b'').hexdigest()
    query_string = urlencode(sorted((str(k), str(v)) for k, v in query.items() if v is not None))
    body_json = (json_bytes(body).decode('utf-8') if body is not None else '')
    values = {
        'method': method.upper(), 'path': path, 'path_with_query': path + (('?' + query_string) if query_string else ''),
        'query_string': query_string, 'timestamp': ts, 'nonce': nonce,
        'body_sha256': body_hash, 'body_json': body_json, 'app_id': app_id,
        'idempotency_key': idempotency_key, 'secret': secret,
    }
    template = cfg.get('canonical_template')
    if template is not None:
        if not isinstance(template, str) or not 1 <= len(template) <= 4000:
            raise AdapterContractError('HMAC_CANONICAL_INVALID')
        try:
            canonical_text = _INLINE_PLACEHOLDER.sub(lambda m: str(values[m.group(1)]), template)
        except KeyError:
            raise AdapterContractError('HMAC_CANONICAL_INVALID') from None
        if _INLINE_PLACEHOLDER.search(canonical_text):
            raise AdapterContractError('HMAC_CANONICAL_INVALID')
    else:
        parts = cfg.get('canonical_parts', ['method', 'path', 'timestamp', 'nonce', 'body_sha256'])
        if not isinstance(parts, list) or not parts or any(x not in values for x in parts):
            raise AdapterContractError('HMAC_CANONICAL_INVALID')
        separator = str(cfg.get('separator', '\n'))
        if len(separator) > 8:
            raise AdapterContractError('HMAC_CANONICAL_INVALID')
        canonical_text = separator.join(str(values[x]) for x in parts)
    canonical = canonical_text.encode('utf-8')
    algorithm = str(cfg.get('algorithm', 'hmac_sha256' if mode == 'hmac_sha256' else 'hmac_sha256')).lower()
    if algorithm == 'hmac_sha256':
        signed = hmac.new(secret.encode('utf-8'), canonical, hashlib.sha256).digest()
    elif algorithm == 'sha256':
        signed = hashlib.sha256(canonical).digest()
    elif algorithm == 'md5':
        signed = hashlib.md5(canonical).digest()
    else:
        raise AdapterContractError('SIGNATURE_ALGORITHM_INVALID')
    encoding = str(cfg.get('encoding', 'hex')).lower()
    signature = signed.hex() if encoding == 'hex' else base64.b64encode(signed).decode() if encoding == 'base64' else None
    if signature is not None and cfg.get('uppercase') is True:
        signature = signature.upper()
    if signature is None:
        raise AdapterContractError('HMAC_ENCODING_INVALID')
    put(cfg.get('signature_target', 'header'), cfg.get('signature_name', cfg.get('signature_header', 'X-Signature')), signature)
    return {'timestamp': ts, 'nonce': nonce, 'body_sha256': body_hash, 'app_id': app_id}


def validate_adapter_config(adapter):
    """Validate filled parameter shapes; empty templates stay intentionally pending."""
    validate_json_config(adapter)
    if not isinstance(adapter,dict):raise AdapterContractError('ADAPTER_CONFIG_INVALID')
    if adapter.get('protocol','') not in {'','cas','oidc','oauth2','json_ticket'}:
        raise AdapterContractError('SSO_PROTOCOL_UNSUPPORTED')
    from .http_transport import PinnedHttpsTransport
    transport=PinnedHttpsTransport('https://configuration.invalid/')
    endpoint_paths={'path','login_path','validate_path','authorize_path','token_path','userinfo_path','jwks_path','logout_path'}
    object_keys={'headers','query','auth','request','response','pagination','identity_fields','org_map','probe','verify','login_auth'}
    def walk(value):
        if isinstance(value,list):
            for v in value:walk(v)
        elif isinstance(value,dict):
            for key,item in value.items():
                if key in endpoint_paths and item:
                    if not isinstance(item,str):raise AdapterContractError('ADAPTER_PATH_INVALID')
                    try:transport.target(item)
                    except ValueError:raise AdapterContractError('ADAPTER_PATH_INVALID') from None
                if key in object_keys and not isinstance(item,dict):raise AdapterContractError('ADAPTER_CONFIG_INVALID')
                if key=='method' and item not in {'GET','POST','PUT','PATCH','DELETE'}:raise AdapterContractError('REQUEST_METHOD_INVALID')
                if key in {'auth','login_auth'} and item.get('mode','none') not in {'none','bearer','header','basic','hmac_sha256','signature','oauth2_client_credentials','datahub_access_token'}:
                    raise AdapterContractError('AUTH_MODE_UNSUPPORTED')
                if key=='pagination':
                    if item.get('mode','cursor') not in {'cursor','page'}:raise AdapterContractError('PULL_PAGING_INVALID')
                    for name,low,high in [('page_size',1,1000),('max_pages',1,1000),('start_page',0,1000000)]:
                        if name in item and (type(item[name]) is not int or not low<=item[name]<=high):raise AdapterContractError('PULL_PAGING_INVALID')
                if key=='credential_bindings' and not isinstance(item,list):raise AdapterContractError('CREDENTIAL_BINDING_INVALID')
                if key not in {'body','query','headers','identity_fields','org_map','authorize_params','login_params','logout_params'}:walk(item)
    walk(adapter)

def validate_json_config(value: Any, *, depth: int = 0, nodes: list[int] | None = None):
    """Bound admin-editable adapter config and reject embedded secret material."""
    nodes = nodes or [0]
    nodes[0] += 1
    if nodes[0] > 1500 or depth > 12:
        raise AdapterContractError('ADAPTER_CONFIG_TOO_LARGE')
    if isinstance(value, dict):
        if len(value) > 120:
            raise AdapterContractError('ADAPTER_CONFIG_TOO_LARGE')
        forbidden = {'secret','password','clientsecret','privatekey','accesstoken','refreshtoken','apikey','token','authorization','cookie','setcookie','xapikey','xtoken','xauthtoken'}
        for key, item in value.items():
            name = str(key)
            if not name or len(name) > 120:
                raise AdapterContractError('ADAPTER_CONFIG_INVALID')
            normalized=re.sub(r'[^a-z0-9]','',name.lower())
            if normalized in forbidden and item not in (None, '', False):
                raise AdapterContractError('SECRET_MATERIAL_FORBIDDEN_IN_CONFIG')
            validate_json_config(item, depth=depth + 1, nodes=nodes)
    elif isinstance(value, list):
        if len(value) > 300:
            raise AdapterContractError('ADAPTER_CONFIG_TOO_LARGE')
        for item in value:
            validate_json_config(item, depth=depth + 1, nodes=nodes)
    elif isinstance(value, str):
        if len(value) > 10000:
            raise AdapterContractError('ADAPTER_CONFIG_TOO_LARGE')
        if re.search(r'-----BEGIN .*PRIVATE KEY-----|(?:Bearer|Basic)\s+\S+',value,re.I):
            raise AdapterContractError('SECRET_MATERIAL_FORBIDDEN_IN_CONFIG')
    elif value is not None and not isinstance(value, (int, float, bool)):
        raise AdapterContractError('ADAPTER_CONFIG_INVALID')
