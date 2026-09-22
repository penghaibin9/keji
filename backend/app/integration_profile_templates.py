"""Fill-in-place templates for the three procurement integrations.

These contain no credentials. They are intentionally incomplete until the school
or province platform provides the real protocol/documentation.
"""
from __future__ import annotations

from copy import deepcopy


def _request():
    return {
        'method': 'GET',
        'path': '',
        'headers': {},
        'query': {},
        'auth': {'mode': 'none'},
        'credential_bindings': [],
    }


def sso_adapter_template():
    return {
        'protocol': '',
        'probe': {},
        'login_path': '',
        'validate_path': '',
        'authorize_path': '',
        'token_path': '',
        'userinfo_path': '',
        'issuer': '',
        'jwks_path': '',
        'logout_path': '',
        'scope': 'openid profile',
        'client_auth_style': 'client_secret_post',
        'identity_root': '',
        'identity_fields': {
            'stable_id': '', 'account': '', 'staff_no': '', 'name': '',
            'org_code': '', 'roles': '', 'active': '',
        },
        'org_map': {},
        'roles_delimiter': ',',
        'active_true_values': [True, 1, '1', 'true', 'ACTIVE', '启用'],
        'active_false_values': [False, 0, '0', 'false', 'INACTIVE', '停用'],
    }


def datahub_adapter_template(data_types):
    probe = _request(); probe.update({'success_path': '', 'success_values': [True, 0, '0', 'SUCCESS', 'OK']})
    out = {'public_parameters': {'institution_code': ''}, 'probe': probe, 'data_types': {}}
    for code in data_types:
        req = _request()
        req['query'] = {'cursor': '${cursor}', 'limit': '${limit}', 'mode': '${mode}'}
        out['data_types'][code] = {
            'request': req,
            'pagination': {'mode':'cursor','page_size':1000,'max_pages':20,'start_page':1},
            'response': {
                'success_path': '', 'success_values': [True, 0, '0', 'SUCCESS', 'OK'],
                'records_path': '', 'next_cursor_path': '', 'has_more_path': '',
            },
        }
    return out


def province_adapter_template(data_types):
    probe = _request(); probe.update({'success_path': '', 'success_values': [True, 0, '0', 'SUCCESS', 'OK']})
    out = {'public_parameters': {'institution_code': ''}, 'probe': probe, 'data_types': {}}
    for code in data_types:
        req = _request(); req['method'] = 'POST'; req['body'] = {'data': '${payload}'}
        out['data_types'][code] = {
            'request': req,
            'response': {
                'accepted_path': '', 'accepted_values': [True, 1, '1', 'SUCCESS', 'OK'],
                'code_path': '', 'receipt_id_path': '', 'error_codes': [],
            },
        }
    return out


def templates(data_catalog):
    return {
        'sso': sso_adapter_template(),
        'middle': datahub_adapter_template([x[0] for x in data_catalog['middle']]),
        'province': province_adapter_template([x[0] for x in data_catalog['province']]),
    }


def merge_template(template, current):
    """Preserve already filled values while adding newly supported keys."""
    if isinstance(template, dict):
        result = deepcopy(template)
        if isinstance(current, dict):
            for key, value in current.items():
                result[key] = merge_template(result.get(key), value) if key in result else deepcopy(value)
        return result
    return deepcopy(current if current is not None else template)
