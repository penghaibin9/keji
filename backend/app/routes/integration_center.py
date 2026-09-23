"""Versioned drafts, safe tests, explicit publication and non-destructive health."""
from datetime import date, timedelta
from fastapi import APIRouter, Request, HTTPException
from pydantic import Field
from sqlalchemy import select
from ..models import Connection, Setting, utcnow
from ..schemas import ConnectionUpdate, VersionedReason, Reason, Input
from ..core import read_operation, command, check_version, serial, audit
from ..integration_center import candidate, stored, save_stored, workspace, configuration_issues, run_probe, MATERIALS
from ..integrations import (ADAPTERS, DATA_CATALOG, ConnectionCheck, configuration_hash,
    credential_fingerprint, normalize_mappings, activate_connection, pause_schedules)

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
        issues = configuration_issues(item)
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
        issues = configuration_issues(item)
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
        audit(db, a, 'connections', ident, '登记接口实施资料', before, serial(row), data.reason)
        return {'version': row.version, 'school_accepted': False}
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
        result = {'format': 'YUEKE_INTEGRATION_HANDOVER_R1',
            'workspace': workspace(db, obj, request.app.state.settings),
            'active': {'config': obj.config, 'mappings': obj.mappings, 'version': obj.version},
            'draft': {'config': item.config, 'mappings': item.mappings, 'version': row.version} if row else None,
            'school_acceptance': 'PENDING_SCHOOL_CONFIRMATION'}
        audit(db, a, 'connections', ident, '导出接口实施交接包',
              after={'contains_credentials': False}, reason='实施配置和资料移交；不是验收证书')
        return result
    data = read_operation(request, 'sync.manage', load)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('implementation.json', json.dumps(data, ensure_ascii=False, indent=2))
        archive.writestr('README.md', '# 接口实施交接包\n\n'
            '包含生效配置、草稿、字段映射、正式回调、资料登记和验证摘要。\n'
            '不包含服务器真实凭据、密码或私钥。请通过学校安全渠道单独交接。\n'
            '真实接口联调、脱敏样本、权限验证及学校签认应另附证据，不能用本包代替验收。\n'
            '分页采集中断会保留已确认批次；恢复从未完成页继续，不承诺整次历史入库自动回滚。\n')
    return Response(stream.getvalue(), media_type='application/zip', headers={
        'Content-Disposition': 'attachment; filename="integration-handover.zip"',
        'X-Content-Type-Options': 'nosniff'})
