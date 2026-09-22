"""Strict, protocol-neutral adapter contracts.

The core application never guesses CAS/OIDC/SAML, a data-hub envelope, or the
Xiangpei signature format.  A deployment adapter translates the real upstream
protocol into these small normalized contracts.
"""
from __future__ import annotations
from typing import Any
import re


class AdapterContractError(RuntimeError):
    """Safe internal reason code; never include upstream secrets or raw bodies."""
    def __init__(self, code: str):
        code = str(code or 'ADAPTER_CONTRACT_ERROR')
        if not re.fullmatch(r'[A-Z0-9_]{3,80}', code):
            code = 'ADAPTER_CONTRACT_ERROR'
        super().__init__(code)
        self.code = code


def _text(value: Any, *, max_len: int, required: bool = False) -> str:
    text = str(value if value is not None else '').strip()
    if required and not text:
        raise AdapterContractError('SSO_IDENTITY_FIELD_MISSING')
    if len(text) > max_len:
        raise AdapterContractError('SSO_IDENTITY_FIELD_TOO_LONG')
    return text


def normalize_sso_identity(payload: Any) -> dict:
    """Normalize a real SSO adapter result without granting application rights.

    The deployment adapter is responsible for validating the school protocol,
    signatures/tickets/tokens and translating the school field names.  The core
    only accepts a small normalized identity.  External roles remain evidence;
    R11's own Role/Org/data-scope model remains authoritative for permissions.
    """
    if not isinstance(payload, dict):
        raise AdapterContractError('SSO_IDENTITY_INVALID')
    active = payload.get('active')
    if type(active) is not bool:
        raise AdapterContractError('SSO_ACTIVE_MUST_BE_BOOL')
    stable_id = _text(payload.get('stable_id'), max_len=160)
    account = _text(payload.get('account'), max_len=128)
    staff_no = _text(payload.get('staff_no'), max_len=64)
    name = _text(payload.get('name'), max_len=100, required=True)
    org_code = _text(payload.get('org_code'), max_len=64)
    if not (stable_id or account or staff_no):
        raise AdapterContractError('SSO_STABLE_IDENTITY_MISSING')
    roles = payload.get('external_roles', [])
    if roles is None:
        roles = []
    if not isinstance(roles, list) or len(roles) > 50:
        raise AdapterContractError('SSO_ROLES_INVALID')
    clean_roles = []
    for value in roles:
        role = _text(value, max_len=100)
        if role and role not in clean_roles:
            clean_roles.append(role)
    return {
        'stable_id': stable_id,
        'account': account,
        'staff_no': staff_no,
        'name': name,
        'org_code': org_code,
        'external_roles': clean_roles,
        'active': active,
    }
