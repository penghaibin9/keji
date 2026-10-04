"""Versioned drafts, safe tests, explicit publication and non-destructive health."""
from datetime import date, timedelta
from typing import Literal
from fastapi import APIRouter, Request, HTTPException
from pydantic import Field
from sqlalchemy import select
from ..models import Connection, Setting, utcnow
from ..schemas import ConnectionUpdate, VersionedReason, Reason, Input
from ..core import read_operation, command, check_version, serial, audit
from ..integration_center import (candidate, stored, save_stored, workspace, configuration_issues,
    run_probe, MATERIALS, confirmed_source_codes, invalidate_acceptance, identity_policy_complete)
from ..integration_security import credential_summary, acceptance_requirements, acceptance_summary
from ..integrations import (ADAPTERS, DATA_CATALOG, ConnectionCheck, configuration_hash,
    credential_fingerprint, normalize_mappings, activate_connection, pause_schedules, live_connection)

router = APIRouter(prefix='/api', tags=['统一认证与接口适配中心'])


class DraftUpdate(ConnectionUpdate):
    expected_draft_version: int = Field(ge=0)


class DraftAction(VersionedReason):
    draft_version: int = Field(ge=1)
    confirm_schedule_pause: bool = False


class Material(Input):
    name: str = Field(max_length=40)
    owner: str = Field(default='', max_length=120)
    reference: str = Field(default='', max_length=400)
    confirmed_on: date | None = None


class MaterialsUpdate(Reason):
    expected_version: int = Field(ge=0)
    items: list[Material] = Field(max_length=6)


class CredentialMetadataUpdate(Reason):
    expected_version: int = Field(ge=0)
    expected_connection_version: int = Field(ge=1)
    expected_draft_version: int = Field(ge=0)
    credential_type: Literal['token','oauth_client','hmac','certificate','mtls','custom']
    managed_by: Literal['server_env','secret_manager','file_mount','hardware','other']
    owner: str = Field(min_length=1, max_length=120)
    certificate_fingerprint_sha256: str = Field(default='', pattern=r'^(?:[0-9A-Fa-f]{64})?$')
    certificate_subject: str = Field(default='', max_length=240)
    certificate_issuer: str = Field(default='', max_length=240)
    valid_from: date | None = None
    valid_until: date | None = None
    last_rotated_on: date | None = None
    next_rotation_on: date | None = None


class AcceptanceItem(Input):
    code: str = Field(min_length=1, max_length=40, pattern=r'^[a-z0-9_]+$')
    status: Literal['PENDING','PASSED','FAILED'] = 'PENDING'
    evidence_ref: str = Field(default='', max_length=400)
    school_contact: str = Field(default='', max_length=120)
    checked_on: date | None = None


class AcceptanceUpdate(Reason):
    expected_version: int = Field(ge=0)
    expected_connection_version: int = Field(ge=1)
    items: list[AcceptanceItem] = Field(max_length=6)
    signed_by: str = Field(default='', max_length=120)
    signed_on: date | None = None
    signed_reference: str = Field(default='', max_length=400)


def connection(db, ident):
    obj = db.get(Connection, ident)
    if not obj:
        raise HTTPException(404, '接口不存在')
    return obj


def draft_for_action(db, ident, data):
    obj = connection(db, ident)
    check_version(obj, data.expected_version)
    item, row = candidate(db, obj)
    if row is None or row.version != data.draft_version or row.value['base_version'] != obj.version:
        raise HTTPException(409, '草稿或生效版本已变化，请刷新核对')
    return obj, item, row


@router.get('/connections/{ident}/implementation')
def implementation(ident: str, request: Request):
    def load(db, a, s):
        a.require_admin()
        return workspace(db, connection(db, ident), request.app.state.settings)
    return read_operation(request, 'sync.manage', load)


@router.get('/connections/{ident}/draft')
def get_draft(ident: str, request: Request):
    def load(db, a, s):
        a.require_admin()
        obj = connection(db, ident)
        item, row = candidate(db, obj)
        return {'connection': {**serial(obj), 'config': item.config, 'mappings': item.mappings,
            'version': row.value['base_version'] if row else obj.version},
            'draft_version': row.version if row else 0, 'active_version': obj.version}
    return read_operation(request, 'sync.manage', load)


@router.put('/connections/{ident}/draft')
def save_draft(ident: str, data: DraftUpdate, request: Request):
    def apply(db, a, s):
        from .integrations import _clean_config
        a.require_admin()
        obj = connection(db, ident)
        check_version(obj, data.expected_version)
        old = stored(db, 'draft', ident)
        if (old.version if old else 0) != data.expected_draft_version:
            raise HTTPException(409, '其他实施人员已修改草稿，请刷新核对')
        mappings = normalize_mappings(data.mappings)
        allowed = {item[0] for item in DATA_CATALOG[obj.code]}
        if any(m.get('data_type') and m['data_type'] not in allowed for m in mappings):
            raise HTTPException(422, '字段映射类型不属于当前接口')
        before = serial(old) if old else {}
        row = save_stored(db, 'draft', ident, {'base_version': obj.version,
            'config': _clean_config(data.config), 'mappings': mappings})
        audit(db, a, 'connections', ident, '保存接口草稿（不改变运行连接）', before, serial(row), data.reason)
        return {'draft_version': row.version, 'active_unchanged': True, 'connection_version': obj.version}
    return command(request, data.model_dump(), 'sync.manage', apply)


@router.post('/connections/{ident}/draft/reset')
def reset_draft(ident: str, data: DraftAction, request: Request):
    def apply(db, a, s):
        a.require_admin()
        obj = connection(db, ident)
        check_version(obj, data.expected_version)
        row = stored(db, 'draft', ident)
        if row is None or row.version != data.draft_version:
            raise HTTPException(409, '草稿已变化')
        before = serial(row)
        row.value = {'base_version': obj.version, 'config': obj.config, 'mappings': obj.mappings}
        row.version += 1
        audit(db, a, 'connections', ident, '从生效版重新建立草稿', before, serial(row), data.reason)
        return {'draft_version': row.version, 'active_unchanged': True}
    return command(request, data.model_dump(), 'sync.manage', apply)


@router.post('/connections/{ident}/draft/probe')
def test_draft(ident: str, data: DraftAction, request: Request):
    def apply(db, a, s):
        a.require_admin()
        obj, item, row = draft_for_action(db, ident, data)
        issues = configuration_issues(item, confirmed_source_codes(db, obj.id))
        if issues:
            raise HTTPException(422, {'message': '请先补齐草稿配置', 'issues': issues})
        code, receipt = run_probe(item, production=request.app.state.settings.env == 'production')
        receipt.update(_draft_version=row.version, layer='protocol_auth')
        check = ConnectionCheck(connection_id=ident, configuration_hash=configuration_hash(item),
            adapter_id=receipt['adapter_id'], mode=receipt['mode'], passed=receipt['passed'],
            reason_code=code, receipt=receipt, actor_id=a.id, expires_at=utcnow()+timedelta(hours=24))
        db.add(check)
        db.flush()
        row.value = {**row.value, 'check_id': check.id}
        audit(db, a, 'connections', ident, '测试接口草稿（不改变运行连接）',
              after={'check_id': check.id, 'passed': check.passed, 'mode': check.mode}, reason=data.reason)
        return {'check': check, 'active_unchanged': True}
    return command(request, data.model_dump(), 'sync.manage', apply)


@router.post('/connections/{ident}/health')
def check_health(ident: str, data: VersionedReason, request: Request):
    def apply(db, a, s):
        a.require_admin()
        obj = connection(db, ident)
        check_version(obj, data.expected_version)
        code, result = run_probe(obj, production=request.app.state.settings.env == 'production', health=True)
        save_stored(db, 'health', ident, result)
        audit(db, a, 'connections', ident, '检查连接健康（不撤销发布授权）',
              after={'passed': result['passed'], 'code': code}, reason=data.reason)
        return {'health': serial(result), 'connection_version': obj.version, 'active_unchanged': True}
    return command(request, data.model_dump(), 'sync.manage', apply)


@router.post('/connections/{ident}/draft/publish')
def publish_draft(ident: str, data: DraftAction, request: Request):
    def apply(db, a, s):
        a.require_admin()
        obj, item, row = draft_for_action(db, ident, data)
        if not data.confirm_schedule_pause:
            raise HTTPException(422, '请明确确认发布后需重新批准同步计划')
        issues = configuration_issues(item, confirmed_source_codes(db, obj.id))
        if issues:
            raise HTTPException(422, {'message': '配置不完整', 'issues': issues})
        proof_id = row.value.get('check_id')
        proof = db.get(ConnectionCheck, proof_id) if proof_id else None
        adapter = ADAPTERS.get(obj.code)
        fingerprint = credential_fingerprint(item)
        if (not proof or not proof.passed or proof.mode != 'REAL' or proof.expires_at <= utcnow()
                or proof.configuration_hash != configuration_hash(item)
                or proof.receipt.get('_draft_version') != row.version
                or not fingerprint or proof.receipt.get('_credential_sha256') != fingerprint
                or not adapter or not ADAPTERS.is_real(obj.code)
                or not ADAPTERS.endpoint_matches(item) or not ADAPTERS.credential_matches(item)
                or proof.adapter_id != getattr(adapter, 'adapter_id', None)):
            raise HTTPException(409, '缺少当前草稿的有效真实验证；本地测试不能发布')
        if obj.code == 'sso' and proof.receipt.get('layer') != 'browser_identity':
            raise HTTPException(409, '统一认证还需从草稿发起浏览器试登录，核对本地账号和权限范围')
        before = serial(obj)
        obj.config, obj.mappings = item.config, item.mappings
        obj.state = 'NOT_CONNECTED'
        obj.version += 1
        release_check = ConnectionCheck(connection_id=ident, configuration_hash=configuration_hash(item),
            adapter_id=proof.adapter_id, mode='REAL', passed=True, reason_code='VERIFIED', actor_id=a.id,
            receipt={**proof.receipt, '_connection_revision': obj.version, 'draft_check_id': proof.id},
            expires_at=proof.expires_at)
        db.add(release_check)
        db.flush()
        pause_schedules(db, obj, '发布新配置后请重新批准同步计划')
        activate_connection(db, a, obj, release_check.id)
        save_stored(db, 'release', ident+'.'+str(obj.version),
                    {'connection': serial(obj), 'draft_check_id': proof.id, 'published_by': a.id,
                     'published_at': utcnow().isoformat(), 'reason': data.reason})
        db.delete(row)
        audit(db, a, 'connections', ident, '发布已验证接口草稿', before, serial(obj), data.reason)
        return {'connection': obj, 'published': True, 'school_accepted': False, 'schedules_need_approval': True}
    return command(request, data.model_dump(), 'sync.manage', apply)


@router.put('/connections/{ident}/materials')
def update_materials(ident: str, data: MaterialsUpdate, request: Request):
    def apply(db, a, s):
        a.require_admin()
        connection(db, ident)
        old = stored(db, 'materials', ident)
        if (old.version if old else 0) != data.expected_version:
            raise HTTPException(409, '资料登记已被其他人员修改')
        names = [x.name for x in data.items]
        if len(set(names)) != len(names) or any(x not in MATERIALS for x in names):
            raise HTTPException(422, '资料项重复或不在清单中')
        before = serial(old) if old else {}
        row = save_stored(db, 'materials', ident, {'items': [x.model_dump(mode='json') for x in data.items]})
        invalidate_acceptance(db, ident, a.id, '接口实施资料发生变化')
        audit(db, a, 'connections', ident, '登记接口实施资料', before, serial(row), data.reason)
        return {'version': row.version, 'school_accepted': False}
    return command(request, data.model_dump(), 'sync.manage', apply)


@router.put('/connections/{ident}/credential-metadata')
def update_credential_metadata(ident: str, data: CredentialMetadataUpdate, request: Request):
    def apply(db, a, s):
        a.require_admin()
        obj = connection(db, ident)
        check_version(obj, data.expected_connection_version)
        item, draft = candidate(db, obj)
        if (draft.version if draft else 0) != data.expected_draft_version:
            raise HTTPException(409, '接口草稿已变化，请刷新后重新登记安全元数据')
        reference = item.config.get('secret_env', '')
        if not reference:
            raise HTTPException(409, '请先在草稿中登记服务器凭据引用')
        if data.valid_from and data.valid_until and data.valid_until < data.valid_from:
            raise HTTPException(422, '证书到期日不能早于生效日')
        if data.last_rotated_on and data.next_rotation_on and data.next_rotation_on < data.last_rotated_on:
            raise HTTPException(422, '下次轮换日期不能早于上次轮换日期')
        old = stored(db, 'credential', ident)
        if (old.version if old else 0) != data.expected_version:
            raise HTTPException(409, '凭据资产登记已被其他人员修改')
        before = serial(old) if old else {}
        value = data.model_dump(mode='json', exclude={'reason','basis','expected_version',
            'expected_connection_version','expected_draft_version'})
        value.update(credential_reference=reference, recorded_at=utcnow().isoformat())
        row = save_stored(db, 'credential', ident, value)
        invalidate_acceptance(db, ident, a.id, '凭据或证书安全元数据发生变化')
        summary = credential_summary(value)
        audit(db, a, 'connections', ident, '登记凭据/证书安全元数据', before, serial(row), data.reason)
        return {'version': row.version, 'asset_status': summary, 'secret_values_stored': False}
    return command(request, data.model_dump(), 'sync.manage', apply)


@router.put('/connections/{ident}/acceptance')
def update_acceptance(ident: str, data: AcceptanceUpdate, request: Request):
    def apply(db, a, s):
        a.require_admin()
        obj = connection(db, ident)
        check_version(obj, data.expected_connection_version)
        required = acceptance_requirements(obj.code)
        required_codes = {key for key, _ in required}
        supplied_codes = [item.code for item in data.items]
        if len(set(supplied_codes)) != len(supplied_codes) or set(supplied_codes) != required_codes:
            raise HTTPException(422, '学校验收项必须完整且不能重复')
        for item in data.items:
            if item.status != 'PENDING' and (not item.evidence_ref or not item.school_contact or not item.checked_on):
                raise HTTPException(422, '已核对的验收项必须填写学校联系人、日期和证据编号')
        sign_values = (bool(data.signed_by), bool(data.signed_on), bool(data.signed_reference))
        if any(sign_values) and not all(sign_values):
            raise HTTPException(422, '学校最终签认人、签认日期和签认依据必须同时填写')
        confirmed_sources = confirmed_source_codes(db, ident)
        source_gaps = [name for code, name, status in DATA_CATALOG[obj.code]
                       if status == 'WAITING_SOURCE' and code not in confirmed_sources]
        policy_current = True
        if obj.code == 'sso':
            policy = stored(db, 'identity_policy', ident)
            policy_current = identity_policy_complete((policy.value or {}) if policy else {})
        if all(sign_values):
            if any(item.status != 'PASSED' for item in data.items):
                raise HTTPException(409, '仍有未通过或待确认验收项，不能登记最终签认')
            if source_gaps:
                raise HTTPException(409, '仍有业务数据权威来源未确认，不能登记最终签认')
            if not policy_current:
                raise HTTPException(409, '统一认证四级外部身份与本地权限边界尚未由学校确认，不能登记最终签认')
            if not live_connection(db, obj):
                raise HTTPException(409, '当前生效连接无有效发布授权，不能登记最终签认')
            materials = stored(db, 'materials', ident)
            complete = {x.get('name') for x in ((materials.value or {}).get('items', []) if materials else [])
                        if x.get('reference') and x.get('owner') and x.get('confirmed_on')}
            if not set(MATERIALS) <= complete:
                raise HTTPException(409, '实施资料尚未登记齐全，不能登记最终签认')
            credential = stored(db, 'credential', ident)
            credential_value = dict(credential.value or {}) if credential else {}
            asset = credential_summary(credential_value)
            if (not credential or credential_value.get('credential_reference') != (obj.config or {}).get('secret_env', '')
                    or asset['issues'] or asset['state'] in {'证书已过期','凭据轮换已到期'}):
                raise HTTPException(409, '当前发布版本的凭据/证书安全资产登记不完整或已失效')
            health = stored(db, 'health', ident)
            health_value = dict(health.value or {}) if health else {}
            if (not health_value.get('passed') or health_value.get('mode') != 'REAL'
                    or health_value.get('configuration_hash') != configuration_hash(obj)
                    or health_value.get('_credential_sha256') != credential_fingerprint(obj)):
                raise HTTPException(409, '缺少当前发布版本的真实健康检查通过记录')
        old = stored(db, 'acceptance', ident)
        if (old.version if old else 0) != data.expected_version:
            raise HTTPException(409, '学校验收登记已被其他人员修改')
        before = serial(old) if old else {}
        value = data.model_dump(mode='json', exclude={'reason','basis','expected_version',
            'expected_connection_version'})
        value.update(connection_version=obj.version, configuration_hash=configuration_hash(obj),
                     recorded_by=a.id, recorded_at=utcnow().isoformat())
        row = save_stored(db, 'acceptance', ident, value)
        summary = acceptance_summary(value, obj.code, connection_version=obj.version,
            configuration_hash=configuration_hash(obj), source_gaps=source_gaps,
            identity_policy_current=policy_current)
        audit(db, a, 'connections', ident, '登记学校接口验收证据', before, serial(row), data.reason)
        return {'version': row.version, 'summary': summary, 'automatic_acceptance': False}
    return command(request, data.model_dump(), 'sync.manage', apply)


class DraftPreview(DraftAction):
    data_type: str = Field(max_length=64)
    records: list[dict] = Field(min_length=1, max_length=100)


@router.post('/connections/{ident}/draft/preview')
def preview_draft(ident: str, data: DraftPreview, request: Request):
    def apply(db, a, s):
        from ..integrations import apply_mappings
        from ..sso_identity import preview_identity
        a.require_admin()
        obj, item, row = draft_for_action(db, ident, data)
        if data.data_type not in {x[0] for x in DATA_CATALOG[obj.code]}:
            raise HTTPException(422, '数据类型不属于当前接口')
        rows = []
        if obj.code != 'sso' and not any(m.get('data_type') in ('', None, data.data_type) for m in item.mappings):
            raise HTTPException(409, '当前类型尚未配置字段映射')
        for index, record in enumerate(data.records, 1):
            if obj.code == 'sso':
                value = preview_identity(db, item.config, record)
            else:
                mapped, errors = apply_mappings(item, record, data.data_type)
                value = {'mapped': mapped, 'errors': errors}
            rows.append({'row': index, **value})
        audit(db, a, 'connections', ident, '预览草稿映射（不入库不创建登录会话）',
              after={'rows': len(rows), 'draft_version': row.version}, reason=data.reason)
        return {'items': rows, 'error_rows': sum(bool(x['errors']) for x in rows),
                'external_called': False, 'session_created': False, 'draft_version': row.version}
    return command(request, data.model_dump(), 'sync.manage', apply)


@router.get('/connections/{ident}/handover.zip')
def handover(ident: str, request: Request):
    import io, json, zipfile
    from fastapi.responses import Response
    def load(db, a, s):
        a.require_admin()
        a.require('export')
        obj = connection(db, ident)
        item, row = candidate(db, obj)
        current_workspace = workspace(db, obj, request.app.state.settings)
        result = {'format': 'YUEKE_INTEGRATION_HANDOVER_R2',
            'workspace': current_workspace,
            'active': {'config': obj.config, 'mappings': obj.mappings, 'version': obj.version},
            'draft': {'config': item.config, 'mappings': item.mappings, 'version': row.version} if row else None,
            'credential_metadata': current_workspace['credential'],
            'school_acceptance': current_workspace['acceptance']}
        audit(db, a, 'connections', ident, '导出接口实施交接包',
              after={'contains_credentials': False}, reason='实施配置和资料移交；不是验收证书')
        return result
    data = read_operation(request, 'sync.manage', load)
    from ..integration_handover import build_handover_workbook
    workbook = build_handover_workbook(data)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('implementation.json', json.dumps(data, ensure_ascii=False, indent=2))
        archive.writestr('接口实施交接工作簿.xlsx', workbook)
        archive.writestr('README.md', '# 接口实施交接包\n\n'
            '包含生效配置、草稿、字段映射、正式回调、资料登记、凭据/证书安全元数据、验证摘要和学校验收台账。\n'
            '不包含服务器真实凭据、密码、令牌、私钥或证书正文。请通过学校安全渠道单独交接。\n'
            '真实接口联调、脱敏样本、权限验证及学校签认应另附证据，不能用本包代替验收。\n'
            '分页采集中断会保留已确认批次；恢复从未完成页继续，不承诺整次历史入库自动回滚。\n')
    return Response(stream.getvalue(), media_type='application/zip', headers={
        'Content-Disposition': 'attachment; filename="integration-handover.zip"',
        'X-Content-Type-Options': 'nosniff'})
