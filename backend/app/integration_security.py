"""Credential/certificate metadata and school acceptance facts.

No secret, token, password, private key or certificate body is stored here.
All records reuse Settings and remain versioned/audited by the route layer.
"""
from __future__ import annotations
from datetime import date, timedelta

CREDENTIAL_TYPES = {
    'token': '令牌',
    'oauth_client': 'OAuth应用凭据',
    'hmac': '签名密钥',
    'certificate': '服务证书',
    'mtls': '双向TLS证书',
    'custom': '学校专用凭据',
}
MANAGED_BY = {
    'server_env': '服务器环境变量',
    'secret_manager': '密钥管理服务',
    'file_mount': '受控文件挂载',
    'hardware': '硬件或密码设备',
    'other': '学校指定安全方式',
}

ACCEPTANCE = {
    'sso': [
        ('real_login', '真实单点登录与状态校验'),
        ('logout', '退出登录与异常返回'),
        ('identity_mapping', '账号、姓名、组织与身份映射'),
        ('access_scope', '四级权限与越权拦截'),
        ('negative_cases', '停用、调岗、异常账号验证'),
        ('handover', '接口配置、权限说明与联调记录'),
    ],
    'middle': [
        ('real_connectivity', '真实连通性与鉴权'),
        ('field_mapping', '字段映射与脱敏样本'),
        ('full_incremental', '全量、增量、定时与人工触发'),
        ('quality_recovery', '质量异常、重试与恢复'),
        ('reconciliation', '批次数量与结果对账'),
        ('handover', '接口清单、字典、处理说明与联调记录'),
    ],
    'province': [
        ('real_connectivity', '真实连通性与鉴权'),
        ('eleven_types', '十一类业务数据范围'),
        ('field_mapping', '字段映射与脱敏报文'),
        ('retry_idempotency', '重试、补传与幂等'),
        ('negative_cases', '异常返回与失败处理'),
        ('handover', '接口文档、联调记录与问题清单'),
    ],
}

def acceptance_requirements(code):
    return list(ACCEPTANCE.get(code, ()))

def credential_summary(value, *, today=None):
    value = dict(value or {})
    today = today or date.today()
    issues = []
    kind = value.get('credential_type', '')
    if kind not in CREDENTIAL_TYPES:
        issues.append('凭据类型待登记')
    if value.get('managed_by') not in MANAGED_BY:
        issues.append('安全保管方式待登记')
    if not value.get('owner'):
        issues.append('轮换责任人待登记')
    if kind in {'certificate', 'mtls'}:
        if not value.get('certificate_fingerprint_sha256'):
            issues.append('证书SHA-256指纹待登记')
        if not value.get('valid_until'):
            issues.append('证书到期日待登记')
    def parse(name):
        raw = value.get(name)
        if not raw:
            return None
        try:
            return date.fromisoformat(str(raw))
        except ValueError:
            issues.append(name + ' 日期格式无效')
            return None
    valid_until, rotation = parse('valid_until'), parse('next_rotation_on')
    state = '安全资产元数据待完善' if issues else '安全资产有效'
    if valid_until and valid_until < today:
        state = '证书已过期'
    elif valid_until and valid_until <= today + timedelta(days=30):
        state = '证书30天内到期'
    if rotation and rotation < today:
        state = '凭据轮换已到期'
    elif rotation and rotation <= today + timedelta(days=30) and state == '安全资产有效':
        state = '凭据30天内需轮换'
    return {'state': state, 'issues': issues,
            'credential_type_name': CREDENTIAL_TYPES.get(kind, '待登记'),
            'managed_by_name': MANAGED_BY.get(value.get('managed_by'), '待登记')}

def acceptance_summary(value, code, *, connection_version, configuration_hash, source_gaps=(), runtime_current=True):
    value = dict(value or {})
    required = acceptance_requirements(code)
    by_code = {x.get('code'): x for x in value.get('items', []) if isinstance(x, dict)}
    passed = sum(by_code.get(key, {}).get('status') == 'PASSED' for key, _ in required)
    failed = [label for key, label in required if by_code.get(key, {}).get('status') == 'FAILED']
    stale = bool(value) and (value.get('connection_version') != connection_version
        or value.get('configuration_hash') != configuration_hash)
    signed = bool(value.get('signed_by') and value.get('signed_on') and value.get('signed_reference'))
    evidence_complete = all(
        by_code.get(key, {}).get('status') == 'PASSED'
        and by_code.get(key, {}).get('evidence_ref')
        and by_code.get(key, {}).get('school_contact')
        and by_code.get(key, {}).get('checked_on')
        for key, _ in required
    )
    current_signed = signed and evidence_complete and not stale and not source_gaps and runtime_current
    if current_signed:
        state = '学校已签认'
    elif stale:
        state = '配置已变化，验收需重新确认'
    elif failed:
        state = '验收存在失败项'
    elif signed and (not evidence_complete or source_gaps):
        state = '签认条件未满足'
    elif signed and not runtime_current:
        state = '运行凭据或健康状态已变化，验收需复核'
    else:
        state = '待学校签认'
    return {'state': state, 'passed': passed, 'total': len(required), 'signed': current_signed,
            'stale': stale, 'runtime_current': bool(runtime_current), 'failed': failed,
            'source_gaps': list(source_gaps),
            'requirements': [{'code': key, 'label': label} for key, label in required]}
