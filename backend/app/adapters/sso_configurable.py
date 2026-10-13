"""Configurable SSO adapter for common CAS, OIDC/OAuth2 and JSON-ticket flows.

The adapter intentionally does not implement SAML XML signatures. If the school
formally requires SAML POST/XML-DSig, install a dedicated audited SAML adapter
instead of weakening signature validation here.
"""
from __future__ import annotations

import base64
import re
from urllib.parse import urlencode
from xml.etree import ElementTree

from .contracts import AdapterContractError
from .common import (list_value, normalized_bool, parse_credential, path_get,
                     credential_value, validate_json_config, apply_auth, apply_credential_bindings, encode_query, matches_value)
from .http_transport import PinnedHttpsTransport
from .oidc import login_proof, verify_id_token


class ConfigurableSsoAdapter:
    adapter_id = 'yueke.sso.configurable.v2'
    supports_credentialless_cas = True
    transport_cls = PinnedHttpsTransport

    def _cfg(self, config):
        if not isinstance(config, dict):
            raise AdapterContractError('SSO_CONFIG_INVALID')
        adapter = config.get('adapter') or {}
        validate_json_config(adapter)
        if not isinstance(adapter, dict):
            raise AdapterContractError('SSO_CONFIG_INVALID')
        protocol = str(adapter.get('protocol', '')).strip().lower()
        if protocol not in {'cas', 'oidc', 'oauth2', 'json_ticket'}:
            raise AdapterContractError('SSO_PROTOCOL_UNSUPPORTED')
        return adapter, protocol

    def _url(self, transport, path, params):
        return transport.target(path) + ('?' + urlencode([(k, str(v)) for k, v in params.items() if v not in (None, '')]) if params else '')

    def probe(self, *, config, credential, timeout_seconds):
        adapter, protocol = self._cfg(config)
        transport = self.transport_cls(str(config.get('endpoint', '')).strip())
        credentials = {} if protocol == 'cas' and not credential else parse_credential(credential)
        probe = adapter.get('probe') or {}
        kind = str(probe.get('kind', '')).strip().lower()
        if kind in {'cas_ticket','authorization_code'}:
            callback_url=str(probe.get('callback_url','')).strip()
            if not callback_url.startswith('https://'):raise AdapterContractError('SSO_PROBE_CALLBACK_MISSING')
            state=credential_value(credentials,probe.get('state_key','probe_state'),required=protocol!='cas')
            value=credential_value(credentials,probe.get('credential_key','probe_ticket' if protocol=='cas' else 'probe_code'))
            callback={str(adapter.get('state_param','state') if protocol=='cas' else 'state'):state,str(adapter.get('ticket_param','ticket') if protocol=='cas' else adapter.get('code_param','code')):value}
            identity=self.complete_login(callback=callback,callback_url=callback_url,config=config,credential=credential,timeout_seconds=timeout_seconds)
            return {'authenticated':identity.get('active') is True,'tls_verified':True,'protocol_verified':True,'probe_kind':kind}
        if protocol == 'cas' and kind == 'cas_validate_reject':
            path = str(adapter.get('validate_path', '')).strip()
            if not path:
                raise AdapterContractError('SSO_CAS_VALIDATE_PATH_MISSING')
            route = path + ('&' if '?' in path else '?') + urlencode({
                str(adapter.get('service_param', 'service')): 'https://invalid.example/sso-probe',
                str(adapter.get('ticket_param', 'ticket')): 'ST-YUEKE-PROBE-INVALID',
            })
            text = transport.request_text('GET', route, timeout_seconds=timeout_seconds,
                allowed_content_types={'application/xml', 'text/xml', 'text/plain'})
            if '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper() or 'authenticationFailure' not in text:
                raise AdapterContractError('SSO_CAS_PROBE_INVALID')
            return {'authenticated': False, 'tls_verified': True, 'protocol_verified': True, 'probe_kind': kind}
        if protocol in {'oidc', 'oauth2'} and kind == 'oidc_metadata':
            discovery = str(probe.get('path', '/.well-known/openid-configuration')).strip()
            data = transport.request_json('GET', discovery, timeout_seconds=timeout_seconds)
            if not isinstance(data, dict) or not data.get('authorization_endpoint') or not data.get('token_endpoint'):
                raise AdapterContractError('SSO_OIDC_METADATA_INVALID')
            credential_value(credentials, adapter.get('client_id_key', 'client_id'))
            return {'authenticated': False, 'tls_verified': True, 'protocol_verified': True, 'probe_kind': kind}
        if kind == 'json':
            if not probe.get('credential_header') or not probe.get('success_path'):raise AdapterContractError('SSO_AUTHENTICATED_PROBE_REQUIRED')
            path = str(probe.get('path', '')).strip()
            if not path:
                raise AdapterContractError('SSO_PROBE_PATH_MISSING')
            headers = {}
            if probe.get('credential_header'):
                headers[str(probe['credential_header'])] = credential_value(credentials, probe.get('credential_key', 'token'))
            data = transport.request_json(str(probe.get('method', 'GET')).upper(), path, headers=headers,
                                          payload=probe.get('body') if str(probe.get('method', 'GET')).upper() != 'GET' else None,
                                          timeout_seconds=timeout_seconds)
            expected_path = str(probe.get('success_path', '')).strip()
            if expected_path:
                allowed = probe.get('success_values', [True, 0, '0', 'SUCCESS', 'OK'])
                if not matches_value(path_get(data, expected_path),allowed):
                    raise AdapterContractError('SSO_PROBE_EXPECTATION_FAILED')
            return {'authenticated': True, 'tls_verified': True, 'protocol_verified': True, 'probe_kind': kind}
        raise AdapterContractError('SSO_PROBE_CONFIG_MISSING')

    def build_login_url(self, *, state, callback_url, config, credential, timeout_seconds):
        adapter, protocol = self._cfg(config)
        transport = self.transport_cls(str(config.get('endpoint', '')).strip())
        credentials = {} if protocol == 'cas' and not credential else parse_credential(credential)
        if protocol == 'cas':
            path = str(adapter.get('login_path', '')).strip()
            if not path:
                raise AdapterContractError('SSO_LOGIN_PATH_MISSING')
            # CAS does not define an OAuth-style state parameter. Put the R11
            # state in the service URL so the IdP returns it unchanged with ticket.
            state_param = str(adapter.get('state_param', 'state'))
            service_url = callback_url + ('&' if '?' in callback_url else '?') + urlencode({state_param: state})
            params = {str(adapter.get('service_param', 'service')): service_url}
            return {'redirect_url': self._url(transport, path, params)}
        if protocol in {'oidc', 'oauth2'}:
            path = str(adapter.get('authorize_path', '')).strip()
            if not path:
                raise AdapterContractError('SSO_AUTHORIZE_PATH_MISSING')
            client_id = credential_value(credentials, adapter.get('client_id_key', 'client_id'))
            params = {'response_type': 'code', 'client_id': client_id, 'redirect_uri': callback_url,
                      'state': state, 'scope': str(adapter.get('scope', 'openid profile'))}
            _,challenge,nonce=login_proof(state,credential_value(credentials,adapter.get('client_secret_key','client_secret')))
            params.update(code_challenge=challenge,code_challenge_method='S256')
            if protocol=='oidc':params['nonce']=nonce
            extra = adapter.get('authorize_params') or {}
            if not isinstance(extra, dict) or len(extra) > 30:
                raise AdapterContractError('SSO_AUTHORIZE_PARAMS_INVALID')
            for key, value in extra.items():
                if key not in params:
                    params[str(key)] = str(value)
            return {'redirect_url': self._url(transport, path, params)}
        path = str(adapter.get('login_path', '')).strip()
        if not path:
            raise AdapterContractError('SSO_LOGIN_PATH_MISSING')
        params = {str(adapter.get('state_param', 'state')): state,
                  str(adapter.get('redirect_param', 'redirect_uri')): callback_url}
        client_id = credential_value(credentials, adapter.get('client_id_key', 'client_id'), required=False)
        if client_id and adapter.get('client_id_param', 'client_id'):
            params[str(adapter.get('client_id_param', 'client_id'))] = client_id
        for key, value in (adapter.get('login_params') or {}).items():
            if key in params:raise AdapterContractError('SSO_RESERVED_LOGIN_PARAM')
            params[str(key)] = str(value)
        headers = {}
        apply_credential_bindings(headers, params, None, adapter.get('login_credential_bindings'), credentials)
        if any(v and str(v) in [str(x) for x in params.values()] for k,v in credentials.items() if k not in {'client_id','app_id','institution_code'}):
            raise AdapterContractError('SSO_BROWSER_SECRET_FORBIDDEN')
        if headers:
            raise AdapterContractError('SSO_BROWSER_REDIRECT_HEADER_AUTH_UNSUPPORTED')
        apply_auth(headers, params, None, adapter.get('login_auth'), credentials, method='GET', path=path)
        if any(v and str(v) in [str(x) for x in params.values()] for k,v in credentials.items() if k not in {'client_id','app_id','institution_code'}):
            raise AdapterContractError('SSO_BROWSER_SECRET_FORBIDDEN')
        if headers:
            raise AdapterContractError('SSO_BROWSER_REDIRECT_HEADER_AUTH_UNSUPPORTED')
        return {'redirect_url': transport.target(encode_query(path, params))}

    def _identity(self, payload, adapter):
        root_path = str(adapter.get('identity_root', '')).strip()
        root = path_get(payload, root_path) if root_path else payload
        if not isinstance(root, dict):
            raise AdapterContractError('SSO_IDENTITY_ROOT_INVALID')
        fields = adapter.get('identity_fields') or {}
        if not isinstance(fields, dict):
            raise AdapterContractError('SSO_IDENTITY_FIELDS_INVALID')
        def take(name, default=''):
            path = str(fields.get(name, '')).strip()
            return path_get(root, path, default) if path else default
        external_org = str(take('org_code', '') or '').strip()
        org_map = adapter.get('org_map') or {}
        if org_map and not isinstance(org_map, dict):
            raise AdapterContractError('SSO_ORG_MAP_INVALID')
        org_code = str(org_map.get(external_org, external_org)).strip() if external_org else ''
        roles = list_value(take('roles', []), delimiter=str(adapter.get('roles_delimiter', ',')))
        active_path = str(fields.get('active', '')).strip()
        if active_path:
            active = normalized_bool(take('active'), true_values=adapter.get('active_true_values'), false_values=adapter.get('active_false_values'))
        elif type(adapter.get('active_default')) is bool:
            active = adapter['active_default']
        else:
            raise AdapterContractError('SSO_ACTIVE_RULE_MISSING')
        return {
            'stable_id': str(take('stable_id', '') or '').strip(),
            'account': str(take('account', '') or '').strip(),
            'staff_no': str(take('staff_no', '') or '').strip(),
            'name': str(take('name', '') or '').strip(),
            'org_code': org_code,
            'external_roles': roles,
            'active': active,
        }

    def _parse_cas(self, text):
        upper = text.upper()
        if '<!DOCTYPE' in upper or '<!ENTITY' in upper:
            raise AdapterContractError('SSO_CAS_XML_FORBIDDEN')
        try:
            root = ElementTree.fromstring(text)
        except Exception:
            raise AdapterContractError('SSO_CAS_XML_INVALID') from None
        success = None
        for node in root.iter():
            if node.tag.split('}')[-1] == 'authenticationSuccess':
                success = node
                break
        if success is None:
            raise AdapterContractError('SSO_CAS_AUTHENTICATION_FAILED')
        result = {}
        attrs = {}
        for node in success:
            name = node.tag.split('}')[-1]
            if name == 'user':
                result['user'] = (node.text or '').strip()
            elif name == 'attributes':
                for item in node:
                    key = item.tag.split('}')[-1]
                    value = (item.text or '').strip()
                    if key in attrs:
                        attrs[key] = attrs[key] + [value] if isinstance(attrs[key], list) else [attrs[key], value]
                    else:
                        attrs[key] = value
        result['attributes'] = attrs
        return result

    def complete_login(self, *, callback, callback_url, config, credential, timeout_seconds):
        adapter, protocol = self._cfg(config)
        transport = self.transport_cls(str(config.get('endpoint', '')).strip())
        credentials = {} if protocol == 'cas' and not credential else parse_credential(credential)
        if protocol == 'cas':
            ticket_name = str(adapter.get('ticket_param', 'ticket'))
            ticket = str((callback or {}).get(ticket_name, '')).strip()
            if not ticket or len(ticket) > 2048:
                raise AdapterContractError('SSO_CAS_TICKET_MISSING')
            path = str(adapter.get('validate_path', '')).strip()
            if not path:
                raise AdapterContractError('SSO_CAS_VALIDATE_PATH_MISSING')
            state_param = str(adapter.get('state_param', 'state'))
            state = str((callback or {}).get(state_param, '')).strip()
            service_url = callback_url + (('&' if '?' in callback_url else '?') + urlencode({state_param: state}) if state else '')
            route = path + ('&' if '?' in path else '?') + urlencode({
                str(adapter.get('service_param', 'service')): service_url,
                ticket_name: ticket,
            })
            text = transport.request_text('GET', route, timeout_seconds=timeout_seconds,
                allowed_content_types={'application/xml', 'text/xml', 'text/plain'})
            return self._identity(self._parse_cas(text), adapter)
        if protocol in {'oidc', 'oauth2'}:
            code = str((callback or {}).get(str(adapter.get('code_param', 'code')), '')).strip()
            if not code or len(code) > 4096:
                raise AdapterContractError('SSO_CODE_MISSING')
            token_path = str(adapter.get('token_path', '')).strip()
            userinfo_path = str(adapter.get('userinfo_path', '')).strip()
            if not token_path or not userinfo_path:
                raise AdapterContractError('SSO_OAUTH_ENDPOINT_MISSING')
            client_id = credential_value(credentials, adapter.get('client_id_key', 'client_id'))
            client_secret = credential_value(credentials, adapter.get('client_secret_key', 'client_secret'))
            form = {'grant_type': 'authorization_code', 'code': code, 'redirect_uri': callback_url, 'client_id': client_id}
            state=str(callback.get('state',''))
            if not state:raise AdapterContractError('SSO_STATE_MISSING')
            verifier,_,nonce=login_proof(state,client_secret)
            form['code_verifier']=verifier
            headers = {}
            style = str(adapter.get('client_auth_style', 'client_secret_post'))
            if style == 'client_secret_post':
                form['client_secret'] = client_secret
            elif style == 'basic':
                headers['Authorization'] = 'Basic ' + base64.b64encode((client_id + ':' + client_secret).encode()).decode()
            else:
                raise AdapterContractError('SSO_CLIENT_AUTH_STYLE_INVALID')
            token = transport.request_form_json(token_path, form=form, headers=headers, timeout_seconds=timeout_seconds)
            if not isinstance(token, dict):
                raise AdapterContractError('SSO_TOKEN_RESPONSE_INVALID')
            access_token = str(token.get('access_token', '')).strip()
            if not access_token or len(access_token) > 8192:
                raise AdapterContractError('SSO_ACCESS_TOKEN_MISSING')
            if str(token.get('token_type','Bearer')).lower()!='bearer':raise AdapterContractError('SSO_TOKEN_TYPE_INVALID')
            claims=None
            if protocol=='oidc':
                jwks_path=str(adapter.get('jwks_path','')).strip()
                if not jwks_path:raise AdapterContractError('SSO_JWKS_PATH_MISSING')
                jwks=transport.request_json('GET',jwks_path,timeout_seconds=timeout_seconds)
                claims=verify_id_token(token.get('id_token'),issuer=adapter.get('issuer'),client_id=client_id,nonce=nonce,jwks=jwks,access_token=access_token)
            userinfo = transport.request_json('GET', userinfo_path, headers={'Authorization': 'Bearer ' + access_token}, timeout_seconds=timeout_seconds)
            if claims and (not isinstance(userinfo,dict) or userinfo.get('sub')!=claims['sub']):raise AdapterContractError('SSO_USERINFO_SUBJECT_MISMATCH')
            return self._identity(userinfo, adapter)
        verify = adapter.get('verify') or {}
        if not isinstance(verify, dict):
            raise AdapterContractError('SSO_VERIFY_CONFIG_MISSING')
        param = str(adapter.get('callback_param', 'code'))
        ticket = str((callback or {}).get(param, '')).strip()
        if not ticket or len(ticket) > 4096:
            raise AdapterContractError('SSO_CALLBACK_VALUE_MISSING')
        path = str(verify.get('path', '')).strip()
        method = str(verify.get('method', 'POST')).upper()
        name = str(verify.get('ticket_field', param))
        fields = {name: ticket, str(verify.get('redirect_field', 'redirect_uri')): callback_url}
        client_id = credential_value(credentials, adapter.get('client_id_key', 'client_id'), required=False)
        if client_id and verify.get('client_id_field'):
            fields[str(verify['client_id_field'])] = client_id
        headers = {};query = fields if method == 'GET' else {};body = None if method == 'GET' else fields
        apply_credential_bindings(headers, query, body, verify.get('credential_bindings'), credentials)
        apply_auth(headers, query, body, verify.get('auth'), credentials, method=method, path=path)
        if method == 'GET':
            data = transport.request_json('GET', encode_query(path, query), headers=headers, timeout_seconds=timeout_seconds)
        elif str(verify.get('body_type', 'form')) == 'json':
            data = transport.request_json(method, path, headers=headers, payload=body, timeout_seconds=timeout_seconds)
        else:
            data = transport.request_form_json(path, form=body, headers=headers, timeout_seconds=timeout_seconds)
        success_path = str(verify.get('success_path', '')).strip()
        if success_path:
            allowed = verify.get('success_values', [True, 0, '0', 'SUCCESS', 'OK'])
            if not matches_value(path_get(data, success_path),allowed):
                raise AdapterContractError('SSO_VERIFY_REJECTED')
        return self._identity(data, adapter)

    def build_logout_url(self, *, post_logout_redirect_uri, config, credential, timeout_seconds):
        adapter, protocol = self._cfg(config)
        path = str(adapter.get('logout_path', '')).strip()
        if not path:
            return {}
        transport = self.transport_cls(str(config.get('endpoint', '')).strip())
        params = {}
        redirect_param = str(adapter.get('logout_redirect_param', 'service' if protocol == 'cas' else 'post_logout_redirect_uri'))
        if redirect_param:
            params[redirect_param] = post_logout_redirect_uri
        for key, value in (adapter.get('logout_params') or {}).items():
            params[str(key)] = str(value)
        return {'redirect_url': self._url(transport, path, params)}
