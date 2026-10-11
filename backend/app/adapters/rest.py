"""Config-driven HTTPS JSON request helpers for data-hub/province adapters."""
from __future__ import annotations

from typing import Any
import base64, time, threading, hashlib
from .contracts import AdapterContractError
from .common import (apply_auth, apply_credential_bindings, encode_query, expand_template,
                     parse_credential, path_get, validate_json_config, matches_value)
from .http_transport import PinnedHttpsTransport


class ConfigurableRestBase:
    transport_cls = PinnedHttpsTransport
    def __init__(self):
        self._token_cache = {}
        self._token_lock = threading.Lock()

    def _adapter_config(self, config: dict) -> dict:
        if not isinstance(config, dict):
            raise AdapterContractError('ADAPTER_CONFIG_INVALID')
        adapter = config.get('adapter') or {}
        validate_json_config(adapter)
        if not isinstance(adapter, dict):
            raise AdapterContractError('ADAPTER_CONFIG_INVALID')
        return adapter

    def _request_context(self, adapter: dict, runtime: dict[str, Any]) -> dict[str, Any]:
        """Merge non-secret school identifiers into the allow-listed request template context."""
        public = adapter.get('public_parameters') or {}
        if not isinstance(public, dict) or len(public) > 20:
            raise AdapterContractError('PUBLIC_PARAMETER_CONFIG_INVALID')
        context: dict[str, Any] = {}
        for key, value in public.items():
            name = str(key)
            if not name or not name.replace('_', '').isalnum() or not name[0].isalpha() or len(name) > 80:
                raise AdapterContractError('PUBLIC_PARAMETER_CONFIG_INVALID')
            if value is not None and not isinstance(value, (str, int, float, bool)):
                raise AdapterContractError('PUBLIC_PARAMETER_CONFIG_INVALID')
            context[name] = value
        context.update(runtime)
        return context

    def _request_json(self, *, endpoint: str, spec: dict, context: dict[str, Any], credentials: dict[str, str], timeout_seconds: int):
        if not isinstance(spec, dict):
            raise AdapterContractError('REQUEST_SPEC_INVALID')
        method = str(spec.get('method', 'GET')).upper()
        if method not in {'GET', 'POST', 'PUT', 'PATCH', 'DELETE'}:
            raise AdapterContractError('REQUEST_METHOD_INVALID')
        path = str(spec.get('path', '')).strip()
        if not path:
            raise AdapterContractError('REQUEST_PATH_MISSING')
        headers = expand_template(spec.get('headers', {}), context)
        query = expand_template(spec.get('query', {}), context)
        body = expand_template(spec.get('body'), context) if 'body' in spec else None
        if not isinstance(headers, dict) or not isinstance(query, dict) or (body is not None and not isinstance(body, (dict, list))):
            raise AdapterContractError('REQUEST_SPEC_INVALID')
        apply_credential_bindings(headers, query, body if isinstance(body, dict) else None,
                                  spec.get('credential_bindings'), credentials)
        auth = spec.get('auth') or {'mode':'none'}
        if isinstance(auth, dict) and str(auth.get('mode','')).lower() == 'oauth2_client_credentials':
            headers['Authorization'] = 'Bearer ' + self._oauth2_token(endpoint, auth, credentials, timeout_seconds)
            signing_context = {}
        elif isinstance(auth, dict) and str(auth.get('mode','')).lower() == 'datahub_access_token':
            self._inject_datahub_token(endpoint, auth, credentials, timeout_seconds, query, body)
            signing_context = {}
        else:
            signing_context = apply_auth(headers, query, body, auth, credentials,
                                         method=method, path=path, idempotency_key=str(context.get('idempotency_key', '')))
        context.update({k: v for k, v in signing_context.items() if k not in context})
        target = encode_query(path, query)
        transport = self.transport_cls(endpoint)
        return transport.request_json(method, target, headers=headers, payload=body, timeout_seconds=timeout_seconds)

    def _oauth2_token(self, endpoint, auth, credentials, timeout_seconds):
        token_path = str(auth.get('token_path','')).strip()
        if not token_path:
            raise AdapterContractError('OAUTH2_TOKEN_PATH_MISSING')
        client_id = credentials.get(str(auth.get('client_id_key','client_id')), '')
        client_secret = credentials.get(str(auth.get('client_secret_key','client_secret')), '')
        if not client_id or not client_secret:
            raise AdapterContractError('OAUTH2_CLIENT_CREDENTIAL_MISSING')
        scope = str(auth.get('scope','')).strip()
        cache_key = (endpoint, token_path, client_id, scope, hashlib.sha256(client_secret.encode()).hexdigest())
        now = time.monotonic()
        with self._token_lock:
            cached = self._token_cache.get(cache_key)
            if cached and cached[1] > now + 10:
                return cached[0]
        form = {'grant_type':'client_credentials','client_id':client_id}
        if scope: form['scope'] = scope
        headers = {}
        style = str(auth.get('client_auth_style','client_secret_post'))
        if style == 'client_secret_post':
            form['client_secret'] = client_secret
        elif style == 'basic':
            headers['Authorization'] = 'Basic ' + base64.b64encode((client_id+':'+client_secret).encode()).decode()
        else:
            raise AdapterContractError('OAUTH2_CLIENT_AUTH_STYLE_INVALID')
        data = self.transport_cls(endpoint).request_form_json(token_path, form=form, headers=headers, timeout_seconds=timeout_seconds)
        if not isinstance(data, dict) or not str(data.get('access_token','')).strip() or str(data.get('token_type','Bearer')).lower()!='bearer':
            raise AdapterContractError('OAUTH2_TOKEN_INVALID')
        token = str(data['access_token']).strip()
        try: expires = max(30, min(86400, int(data.get('expires_in',300))))
        except Exception: expires = 300
        with self._token_lock:
            self._token_cache[cache_key] = (token, now + expires)
        return token

    def _inject_datahub_token(self, endpoint, auth, credentials, timeout_seconds, query, body):
        target = str(auth.get('token_in', 'body')).lower()
        field = str(auth.get('token_field', 'access_token')).strip() or 'access_token'
        if target == 'body':
            if not isinstance(body, dict):
                raise AdapterContractError('DATAHUB_TOKEN_BODY_REQUIRED')
            body[field] = self._datahub_token(endpoint, auth, credentials, timeout_seconds)
        elif target == 'query':
            query[field] = self._datahub_token(endpoint, auth, credentials, timeout_seconds)
        else:
            raise AdapterContractError('DATAHUB_TOKEN_TARGET_INVALID')

    def _datahub_token(self, endpoint, auth, credentials, timeout_seconds):
        """GAIA/Pangu data-platform token: key+secret -> result.access_token (code 10000)."""
        token_path = str(auth.get('token_path', '/open_api/authentication/get_access_token')).strip()
        method = str(auth.get('token_method', 'POST')).upper()
        if method not in {'GET', 'POST'}:
            raise AdapterContractError('DATAHUB_TOKEN_METHOD_INVALID')
        key = credentials.get(str(auth.get('key_credential', 'app_key')), '')
        secret = credentials.get(str(auth.get('secret_credential', 'app_secret')), '')
        if not key or not secret:
            raise AdapterContractError('DATAHUB_CREDENTIAL_MISSING')
        cache_key = ('datahub', endpoint, token_path, key, hashlib.sha256(secret.encode()).hexdigest())
        now = time.monotonic()
        with self._token_lock:
            cached = self._token_cache.get(cache_key)
            if cached and cached[1] > now + 60:
                return cached[0]
        transport = self.transport_cls(endpoint)
        if method == 'POST':
            data = transport.request_json('POST', token_path, payload={'key': key, 'secret': secret},
                                          timeout_seconds=timeout_seconds)
        else:
            data = transport.request_json('GET', encode_query(token_path, {'key': key, 'secret': secret}),
                                          timeout_seconds=timeout_seconds)
        if not isinstance(data, dict) or data.get('code') not in (10000, '10000'):
            raise AdapterContractError('DATAHUB_TOKEN_REJECTED')
        result = data.get('result')
        token = str((result or {}).get('access_token', '')).strip() if isinstance(result, dict) else ''
        if not token:
            raise AdapterContractError('DATAHUB_TOKEN_INVALID')
        try: expires = max(120, min(86400, int(result.get('expires_in', 7199))))
        except Exception: expires = 7199
        with self._token_lock:
            self._token_cache[cache_key] = (token, now + expires)
        return token

    def _probe(self, *, config: dict, credential: str, timeout_seconds: int) -> dict:
        adapter = self._adapter_config(config)
        probe = adapter.get('probe')
        if not isinstance(probe, dict):
            raise AdapterContractError('PROBE_CONFIG_MISSING')
        if (probe.get('auth') or {}).get('mode','none')=='none' and not probe.get('credential_bindings'):
            raise AdapterContractError('AUTHENTICATED_PROBE_REQUIRED')
        if not probe.get('success_path'):raise AdapterContractError('PROBE_SUCCESS_RULE_REQUIRED')
        credentials = parse_credential(credential)
        endpoint = str(config.get('endpoint', '')).strip()
        context = self._request_context(adapter, {'limit': 1, 'mode': 'PROBE', 'cursor': None, 'idempotency_key': ''})
        response = self._request_json(endpoint=endpoint, spec=probe, context=context, credentials=credentials, timeout_seconds=timeout_seconds)
        expected_path = str(probe.get('success_path', '')).strip()
        expected = probe.get('success_values', [True, 0, '0', 'SUCCESS', 'OK'])
        if expected_path:
            actual = path_get(response, expected_path)
            if not matches_value(actual,expected):
                raise AdapterContractError('PROBE_EXPECTATION_FAILED')
        return {'authenticated': True, 'tls_verified': True, 'protocol_verified': True,
                'response_shape': type(response).__name__}
