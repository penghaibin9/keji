"""Implementation workspace over existing versioned connections and Settings.

No new schema and no automatic acceptance: draft, tests, release, health and
school sign-off are intentionally different facts.
"""
from copy import deepcopy
from types import SimpleNamespace
from datetime import timedelta
from sqlalchemy import select
from .models import Setting, utcnow
from .integrations import ADAPTERS, ConnectionCheck, configuration_hash, credential_fingerprint, live_connection
from .integration_diagnostics import diagnostic, safe_code
from .integration_security import credential_summary, acceptance_summary

MATERIALS = ('正式接口规范', '责任边界与联系人', '字段与组织字典',
             '同步或登录规则', '脱敏样本与异常规则', '凭据安全交接记录')


def stored(db, kind, ident):
    return db.get(Setting, 'integration.' + kind + ':' + ident)


def save_stored(db, kind, ident, value):
    row = stored(db, kind, ident)
    if row is None:
        row = Setting(key='integration.' + kind + ':' + ident, value=value, version=1)
        db.add(row)
    else:
        row.value = value
        row.version += 1
    db.flush()
    return row


def candidate(db, connection):
    row = stored(db, 'draft', connection.id)
    value = row.value if row else {}
    item = SimpleNamespace(id=connection.id, code=connection.code, name=connection.name,
        config=deepcopy(value.get('config', connection.config or {})),
        mappings=deepcopy(value.get('mappings', connection.mappings or [])))
    return item, row


def source_records(db, connection_id):
    row = stored(db, 'sources', connection_id)
    items = deepcopy((row.value or {}).get('items', [])) if row else []
    return row, items


def source_record_complete(item):
    return bool(isinstance(item, dict) and item.get('data_type') and item.get('source_system')
                and item.get('data_method') and item.get('frequency') and item.get('history_range')
                and item.get('owner') and item.get('responsibility')
                and item.get('reference') and item.get('confirmed_on'))


def source_record_map(db, connection_id):
    row, items = source_records(db, connection_id)
    return row, {item.get('data_type'): item for item in items
                 if isinstance(item, dict) and item.get('data_type')}


def confirmed_source_codes(db, connection_id):
    _, items = source_records(db, connection_id)
    return {item.get('data_type') for item in items if source_record_complete(item)}


def invalidate_acceptance(db, connection_id, actor_id, reason):
    row = stored(db, 'acceptance', connection_id)
    if not row or not (row.value or {}).get('signed_by'):
        return None
    value = deepcopy(row.value or {})
    value.update(invalidated_at=utcnow().isoformat(), invalidated_by=actor_id,
                 invalidation_reason=str(reason)[:400])
    row.value = value
    row.version += 1
    db.flush()
    return row


def identity_policy_complete(value):
    value = dict(value or {})
    items = [x for x in value.get('items', []) if isinstance(x, dict)]
    expected = {'teacher','dept','college','school'}
    by_kind = {x.get('kind'):x for x in items if x.get('kind') in expected}
    return bool(value.get('authorization_mode') == 'LOCAL_ROLE_AUTHORITATIVE'
                and set(by_kind) == expected and len(items) == 4
                and all(by_kind[k].get('external_roles') and by_kind[k].get('confirmed_by')
                        and by_kind[k].get('confirmed_on') for k in expected))


def configuration_issues(item, confirmed_sources=()):
    config, issues = item.config, []
    adapter = config.get('adapter') or {}
    for key, label in [('endpoint', '正式 HTTPS 总地址'), ('owner', '责任单位'), ('secret_env', '服务器凭据引用')]:
        if not config.get(key):
            issues.append(label)
    if item.code == 'sso':
        protocol = adapter.get('protocol')
        required = {'cas': ['login_path', 'validate_path'], 'oidc': ['authorize_path', 'token_path', 'userinfo_path', 'issuer', 'jwks_path'],
                    'oauth2': ['authorize_path', 'token_path', 'userinfo_path'], 'json_ticket': ['login_path']}
        if protocol not in required:
            issues.append('选择学校实际认证协议')
        else:
            issues.extend('协议参数：' + key for key in required[protocol] if not adapter.get(key))
        fields = adapter.get('identity_fields') or {}
        if not fields.get('name') or not any(fields.get(key) for key in ('stable_id', 'staff_no', 'account')):
            issues.append('姓名和稳定身份/工号/账号字段')
        if not fields.get('active') and type(adapter.get('active_default')) is not bool:
            issues.append('账号启停判定规则')
    else:
        from .integrations import DATA_CATALOG
        confirmed_sources = set(confirmed_sources or ())
        for code, name, status in DATA_CATALOG[item.code]:
            if status == 'WAITING_SOURCE' and code not in confirmed_sources:
                continue
            spec = (adapter.get('data_types') or {}).get(code) or {}
            response = spec.get('response') or {}
            if not (spec.get('request') or {}).get('path'):
                issues.append(name + '请求路径')
            if not any(m.get('data_type') in ('', None, code) for m in item.mappings):
                issues.append(name + '字段映射')
            if item.code == 'middle':
                if not response.get('records_path'):
                    issues.append(name + '记录根路径')
                if not response.get('has_more_path') and (spec.get('pagination') or {}).get('end_condition') != 'short_page':
                    issues.append(name + '分页结束判定')
            elif not (response.get('accepted_path') or response.get('success_path')):
                issues.append(name + '接收回执规则')
    return issues


def run_probe(item, *, production, health=False):
    import os
    adapter = ADAPTERS.get(item.code)
    mode = 'REAL' if production and ADAPTERS.is_real(item.code) else 'TEST_ONLY'
    code, passed = 'ADAPTER_NOT_REGISTERED', False
    receipt = {'configuration_hash': configuration_hash(item), 'mode': mode}
    if adapter is not None:
        if mode == 'REAL' and (not ADAPTERS.endpoint_matches(item) or not ADAPTERS.credential_matches(item)):
            code = 'CONNECTION_CONTEXT_NOT_PINNED'
        else:
            credential = os.environ.get(item.config.get('secret_env', ''), '')
            method = getattr(adapter, 'probe', None)
            one_time = ((item.config.get('adapter') or {}).get('probe') or {}).get('kind') in {'cas_ticket', 'authorization_code'}
            if health and item.code == 'sso' and one_time:
                method = getattr(adapter, 'health', None)
            if not credential:
                code = 'CREDENTIAL_MISSING'
            elif not callable(method):
                code = 'PROBE_NOT_IMPLEMENTED'
            else:
                try:
                    result = method(config=item.config, credential=credential, timeout_seconds=10)
                    passed = isinstance(result, dict) and all(result.get(key) is True for key in
                        ('authenticated', 'tls_verified', 'protocol_verified'))
                    code = 'VERIFIED' if passed else 'PROBE_REJECTED'
                except Exception as exc:
                    code = safe_code(exc)
                    receipt['diagnostic'] = diagnostic(code, status=getattr(exc, 'status', None))
    receipt.setdefault('diagnostic', diagnostic(code))
    receipt.update(passed=passed, adapter_id=str(getattr(adapter, 'adapter_id', '')),
                   _credential_sha256=credential_fingerprint(item))
    return code, receipt


def workspace(db, connection, settings):
    from .core import serial
    from .integrations import DATA_CATALOG, current_connection_check
    item, draft = candidate(db, connection)
    source_row, sources = source_record_map(db, connection.id)
    confirmed_sources = {code for code, record in sources.items() if source_record_complete(record)}
    issues = configuration_issues(item, confirmed_sources)
    materials = stored(db, 'materials', connection.id)
    entries = (materials.value or {}).get('items', []) if materials else []
    complete = {x.get('name') for x in entries if x.get('reference') and x.get('owner') and x.get('confirmed_on')}
    check_id = (draft.value or {}).get('check_id') if draft else None
    check = db.get(ConnectionCheck, check_id) if check_id else None
    if not draft:check = current_connection_check(db, connection, activated=True)
    health = stored(db, 'health', connection.id)
    health_value = deepcopy(health.value) if health else {}
    if (health_value.get('configuration_hash') != configuration_hash(connection)
            or health_value.get('_credential_sha256') != credential_fingerprint(connection)):
        health_value = {}
    live = live_connection(db, connection)
    verified = bool(check and check.passed and check.mode == 'REAL'
        and check.configuration_hash == configuration_hash(item))
    source_gaps = [name for code, name, status in DATA_CATALOG[connection.code]
                   if status == 'WAITING_SOURCE' and code not in confirmed_sources]
    credential_row = stored(db, 'credential', connection.id)
    credential_value = deepcopy(credential_row.value) if credential_row else {}
    credential_info = credential_summary(credential_value)
    if credential_value and credential_value.get('credential_reference') != item.config.get('secret_env', ''):
        credential_info = {**credential_info, 'state': '凭据引用已变化，需重新登记',
                           'issues': [*credential_info['issues'], '凭据引用与当前草稿不一致']}
    acceptance_row = stored(db, 'acceptance', connection.id)
    acceptance_value = deepcopy(acceptance_row.value) if acceptance_row else {}
    intake_row = stored(db, 'intake', connection.id)
    intake_value = deepcopy(intake_row.value) if intake_row else {}
    identity_policy_row = stored(db, 'identity_policy', connection.id)
    identity_policy_value = deepcopy(identity_policy_row.value) if identity_policy_row else {}
    credential_current = bool(credential_row
        and credential_value.get('credential_reference') == (connection.config or {}).get('secret_env', '')
        and not credential_info['issues']
        and credential_info['state'] not in {'证书已过期','凭据轮换已到期'})
    health_current = bool(health_value.get('passed') and health_value.get('mode') == 'REAL')
    policy_current = True if connection.code != 'sso' else identity_policy_complete(identity_policy_value)
    acceptance = acceptance_summary(acceptance_value, connection.code,
        connection_version=connection.version, configuration_hash=configuration_hash(connection),
        source_gaps=source_gaps, runtime_current=live and health_current and credential_current,
        identity_policy_current=policy_current)
    return {'connection_id': connection.id, 'code': connection.code, 'name': connection.name,
        'connection_version': connection.version, 'draft_version': draft.version if draft else 0,
        'has_draft': draft is not None, 'issues': issues,
        'statuses': {'materials': '资料登记齐全' if set(MATERIALS) <= complete else '资料待登记',
            'configuration': '配置校验通过' if not issues else '配置待完善',
            'tests': '真实鉴权已验证' if verified else '待真实测试',
            'published': '已发布' if live else '未发布或授权失效',
            'health': '最近检查通过' if health_value.get('passed') and health_value.get('mode') == 'REAL' else '最近检查未通过' if health_value else '未检查',
            'acceptance': acceptance['state']},
        'callbacks': {'login': settings.public_origin + '/api/auth/sso/callback',
                      'test_login': settings.public_origin + '/api/auth/sso/implementation-callback',
                      'logout_return': settings.public_origin + '/', 'readonly': True},
        'credential': {'reference': item.config.get('secret_env', ''),
                       'configured': bool(credential_fingerprint(item)), 'values_returned': False,
                       'version': credential_row.version if credential_row else 0,
                       'metadata': serial(credential_value), 'asset_status': credential_info},
        'materials': {'version': materials.version if materials else 0, 'required': list(MATERIALS), 'items': entries},
        'acceptance': {'version': acceptance_row.version if acceptance_row else 0,
                       'record': serial(acceptance_value), 'summary': acceptance},
        'health': serial(health_value),
        'check': serial(check) if check else None,
        'data_types': [{'code': code, 'name': name, 'source_status': status,
                        'source_confirmed': code in confirmed_sources,
                        'source_system': (sources.get(code) or {}).get('source_system', ''),
                        'source_reference': (sources.get(code) or {}).get('reference', '')}
                       for code,name,status in DATA_CATALOG[connection.code]],
        'source_registry': {'version': source_row.version if source_row else 0,
                            'items': serial(list(sources.values()))},
        'intake': {'version': intake_row.version if intake_row else 0, 'record': serial(intake_value)},
        'identity_policy': {'version': identity_policy_row.version if identity_policy_row else 0,
                            'record': serial(identity_policy_value)},
        'source_gaps': source_gaps,
        'notes': ['配置发布不等于学校验收', '健康检查不撤销发布授权',
                  '改变地址、映射、适配器或凭据后，必须重新验证和发布',
                  '证书私钥及真实令牌只能通过服务器安全渠道管理']}
