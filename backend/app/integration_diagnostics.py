"""Allowlisted, credential-free integration diagnostics shared by UI and workers."""
from __future__ import annotations
from datetime import datetime, timezone
import uuid

CATALOG = {
    'VERIFIED': ('complete', '本次真实协议与鉴权检查通过', '继续核对身份或业务样本；本结果不是学校验收。'),
    'ADAPTER_NOT_REGISTERED': ('deployment', '适配器尚未部署', '请部署人员安装适配器并重启该服务。'),
    'CREDENTIAL_MISSING': ('credential', '服务器凭据未配置', '由服务器管理员通过安全渠道配置凭据，勿填入网页。'),
    'CONNECTION_CONTEXT_NOT_PINNED': ('deployment', '网页配置与部署白名单不一致', '核对正式地址和凭据引用；不得关闭地址校验。'),
    'PROBE_NOT_IMPLEMENTED': ('protocol', '适配器未实现探测', '由实施人员补全真实探测接口。'),
    'PROBE_REJECTED': ('authentication', '对方未确认身份验证成功', '公开元数据或拒绝测试不能代替成功的身份验证。'),
    'PROBE_FAILED': ('unknown', '探测未完成', '凭追踪编号核查服务日志；不要重复粘贴密钥。'),
    'UPSTREAM_DNS_FAILED': ('dns', '无法解析对方域名', '核对学校 DNS 和域名登记。'),
    'UPSTREAM_DNS_EMPTY': ('dns', '域名没有可用地址', '请学校网络管理员核对域名解析。'),
    'UPSTREAM_ADDRESS_FORBIDDEN': ('network', '目标地址不在允许范围', '学校内网域名须由部署端明确放行；禁止放行环回或元数据地址。'),
    'UPSTREAM_TLS_VERIFY_FAILED': ('tls', '证书校验未通过', '核对证书链、有效期和域名；禁止关闭 TLS 验证。'),
    'UPSTREAM_TIMEOUT': ('network', '对方接口响应超时', '检查网络、防火墙和接口负载，再按重试策略处理。'),
    'UPSTREAM_TRANSPORT_ERROR': ('network', '无法建立安全连接', '检查网络、端口、证书和对方服务状态。'),
    'UPSTREAM_HTTP_ERROR': ('http', '对方返回 HTTP 错误', '结合 HTTP 状态检查授权、路径或限流。'),
    'UPSTREAM_JSON_INVALID': ('response', '对方返回格式不是有效 JSON', '核对响应格式；不要把登录页当成业务接口。'),
    'PULL_COMPLETENESS_RULE_REQUIRED': ('pagination', '缺少分页结束判定', '登记 has_more 字段，或明确确认短页结束规则。'),
    'PULL_CURSOR_NOT_ADVANCING': ('pagination', '分页游标没有推进', '请数据责任方核对游标；系统不会静默漏页或重复入库。'),
    'PULL_PAGE_LIMIT_EXCEEDED': ('pagination', '达到本次同步安全页数上限', '核对总量和分页规则；保留已确认批次，勿盲目扩大限制。'),
    'PULL_RESPONSE_TOTAL_MISMATCH': ('reconciliation', '源端总量与累计接收量不一致', '核对快照和分页规则，不能将本次同步视为完整。'),
    'SSO_ID_TOKEN_INVALID': ('signature', '身份令牌验证未通过', '核对签发方、客户端、公钥和服务器时间。'),
    'SSO_IDENTITY_ROOT_INVALID': ('mapping', '身份根路径不匹配', '对照脱敏身份样本调整根路径后重新预览。'),
    'SSO_ACTIVE_RULE_MISSING': ('mapping', '账号启停规则未配置', '登记真实启停字段和取值，不得猜测账号状态。'),
    'SSO_USERINFO_SUBJECT_MISMATCH': ('identity', '令牌与用户信息主体不一致', '停止上线，请学校认证责任方核对主体映射。'),
    'SSO_CAS_AUTHENTICATION_FAILED': ('authentication', 'CAS 票据验证失败', '重新从测试登录入口获取一次性票据，不重复使用旧票据。'),
    'INTEGRATION_CONFIG_INCOMPLETE': ('configuration', '配置校验尚未通过', '先处理配置页面列出的缺项。'),
    'INTEGRATION_EXTERNAL_FAILURE': ('protocol', '外部协议处理未完成', '使用追踪编号和受控错误码核查，不记录原始凭据或报文。'),
}


def safe_code(error) -> str:
    code = getattr(error, 'code', '')
    return code if code in CATALOG else 'INTEGRATION_EXTERNAL_FAILURE'


def diagnostic(code: str, *, status=None, trace_id: str | None = None) -> dict:
    code = code if code in CATALOG else 'INTEGRATION_EXTERNAL_FAILURE'
    stage, message, remedy = CATALOG[code]
    return {'code': code, 'stage': stage, 'message': message, 'remedy': remedy,
            'http_status': status if type(status) is int and 100 <= status <= 599 else None,
            'trace_id': trace_id or uuid.uuid4().hex,
            'checked_at': datetime.now(timezone.utc).isoformat()}
