"""School integration intake workbook: download, preview, and draft-only apply."""
from __future__ import annotations
from datetime import date
from hashlib import sha256
from pathlib import Path
from urllib.parse import quote, unquote
import re

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from ..core import current_actor, command, audit, serial
from ..models import Connection, Setting, utcnow
from ..integrations import DATA_CATALOG, normalize_mappings
from ..integration_center import (
    candidate, stored, save_stored, configuration_issues, source_record_complete,
    invalidate_acceptance, MATERIALS
)
from ..integration_security import CREDENTIAL_TYPES, MANAGED_BY, credential_summary
from ..integration_intake import FORMAT, CODES, NAMES, build_intake_workbook, parse_intake_workbook, overlay_intake
from .integrations import _clean_config

router = APIRouter(prefix='/api', tags=['统一认证与接口适配中心'])


def _version(row):
    return row.version if row else 0

def _safe_credential(value, reference):
    value = dict(value or {})
    if value.get('credential_type') not in CREDENTIAL_TYPES:
        raise HTTPException(422, '凭据类型不在系统允许范围')
    if value.get('managed_by') not in MANAGED_BY:
        raise HTTPException(422, '凭据安全保管方式不在系统允许范围')
    fingerprint = str(value.get('certificate_fingerprint_sha256') or '')
    if fingerprint and not re.fullmatch(r'[0-9A-Fa-f]{64}', fingerprint):
        raise HTTPException(422, '证书SHA-256指纹必须是64位十六进制')
    def parsed(name):
        raw = value.get(name)
        return date.fromisoformat(raw) if raw else None
    start, end = parsed('valid_from'), parsed('valid_until')
    last, next_at = parsed('last_rotated_on'), parsed('next_rotation_on')
    if start and end and end < start:
        raise HTTPException(422, '证书到期日不能早于生效日')
    if last and next_at and next_at < last:
        raise HTTPException(422, '下次轮换日期不能早于上次轮换日期')
    value['credential_reference'] = reference
    return value, credential_summary(value)


def _expected_version(parsed, code, key):
    return parsed['expected'][code][key]

def _plan(db, parsed, lock=False):
    plans = []
    for code in CODES:
        query = select(Connection).where(Connection.code == code)
        if lock:
            query = query.with_for_update()
        obj = db.scalar(query)
        if not obj:
            raise HTTPException(503, '三大接口初始化记录不完整')
        expected = parsed['expected'][code]
        if obj.id != expected['connection_id'] or obj.version != expected['connection_version']:
            raise HTTPException(409, f'{NAMES[code]}生效配置已变化，请重新下载学校资料表')
        if lock:
            db.scalar(select(Setting).where(Setting.key == 'integration.draft:'+obj.id).with_for_update())
        item, draft = candidate(db, obj)
        if _version(draft) != expected['draft_version']:
            raise HTTPException(409, f'{NAMES[code]}草稿已变化，请重新下载学校资料表')
        for kind, key in [('materials','materials_version'),('credential','credential_version'),
                          ('sources','source_version'),('acceptance','acceptance_version'),
                          ('identity_policy','identity_policy_version')]:
            row = stored(db, kind, obj.id)
            if _version(row) != expected[key]:
                raise HTTPException(409, f'{NAMES[code]}实施资料已变化，请重新下载学校资料表')
        overlay = overlay_intake(item, parsed, code)
        config = _clean_config(overlay['config'])
        mappings = normalize_mappings(overlay['mappings'])
        allowed = {x[0] for x in DATA_CATALOG[code]}
        invalid = sorted({m.get('data_type') for m in mappings
                          if m.get('data_type') and m.get('data_type') not in allowed})
        if invalid:
            raise HTTPException(422, f'{NAMES[code]}字段映射数据类型不属于采购目录')
        item.config, item.mappings = config, mappings

        sources = overlay['sources']
        confirmed = {x.get('data_type') for x in sources if source_record_complete(x)}
        issues = configuration_issues(item, confirmed)
        source_gaps = [name for dtype, name, status in DATA_CATALOG[code]
                       if status == 'WAITING_SOURCE' and dtype not in confirmed]

        credential, asset = _safe_credential(overlay['credential'], config.get('secret_env',''))
        material_complete = sum(bool(x.get('owner') and x.get('reference') and x.get('confirmed_on'))
                                for x in overlay['materials'])
        plans.append({
            'code':code, 'obj':obj, 'draft':draft, 'config':config, 'mappings':mappings,
            'materials':overlay['materials'], 'credential':credential, 'asset':asset,
            'sources':sources, 'role_policy':overlay['role_policy'],
            'issues':issues, 'source_gaps':source_gaps,
            'material_complete':material_complete
        })
    return plans


def _public(plan):
    return {
        'code':plan['code'], 'name':NAMES[plan['code']],
        'configuration_issues':list(plan['issues']),
        'mapping_count':len(plan['mappings']),
        'materials_complete':plan['material_complete'], 'materials_total':len(MATERIALS),
        'source_gaps':list(plan['source_gaps']),
        'source_confirmed':sum(source_record_complete(x) for x in plan['sources']),
        'source_total':len(plan['sources']),
        'role_confirmed':sum(bool(x.get('external_roles') and x.get('confirmed_by') and x.get('confirmed_on'))
                             for x in plan['role_policy']),
        'role_total':len(plan['role_policy']),
        'credential_state':plan['asset']['state'],
        'active_version':plan['obj'].version,
        'draft_version':_version(plan['draft'])
    }

async def _upload_bytes(request):
    content_type = request.headers.get('content-type','').split(';',1)[0].strip().lower()
    if content_type != 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':
        raise HTTPException(415, '请上传系统生成的XLSX学校资料表')
    try:
        declared = int(request.headers.get('content-length','0') or 0)
    except ValueError:
        raise HTTPException(400, '上传长度无效') from None
    if declared < 0 or declared > 5*1024*1024:
        raise HTTPException(413, '学校资料Excel不能超过5MB')
    name = unquote(request.headers.get('x-intake-filename','school-intake.xlsx'))
    if (not name or len(name) > 180 or '/' in name or '\\' in name
            or Path(name).suffix.lower() != '.xlsx'):
        raise HTTPException(422, '学校资料文件名无效')
    data = await request.body()
    if not data or len(data) > 5*1024*1024:
        raise HTTPException(413, '学校资料Excel不能超过5MB或为空')
    return name, data


@router.get('/connections/intake-template.xlsx')
def intake_template(request: Request):
    with request.app.state.sessions.begin() as db:
        actor, session = current_actor(db, request)
        actor.require_admin()
        actor.require('sync.manage')
        data = build_intake_workbook(db)
        audit(db, actor, 'connections', 'intake-template', '下载学校三大接口资料采集表',
              after={'bytes':len(data), 'format':FORMAT},
              reason='学校信息处和实施人员填写正式联调资料；不是接通或验收证明')
    filename = quote('跃科_三大接口学校资料采集表.xlsx')
    return Response(data, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    headers={'Content-Disposition':f"attachment; filename*=UTF-8''{filename}",
                             'X-Content-Type-Options':'nosniff'})


@router.post('/connections/intake-preview')
async def intake_preview(request: Request):
    with request.app.state.sessions.begin() as db:
        actor, session = current_actor(db, request, write=True)
        actor.require_admin()
        actor.require('sync.manage')
    filename, data = await _upload_bytes(request)
    digest = sha256(data).hexdigest()
    parsed = await run_in_threadpool(parse_intake_workbook, data)
    with request.app.state.sessions.begin() as db:
        actor, session = current_actor(db, request, write=True)
        actor.require_admin()
        actor.require('sync.manage')
        plans = _plan(db, parsed, lock=False)
        audit(db, actor, 'connections', 'intake-preview', '预检学校三大接口资料表',
              after={'file_sha256':digest, 'filename':filename, 'format':parsed['format']},
              reason='只做格式、版本和配置预检；未写草稿、未调用外部接口')
        return {
            'format':parsed['format'], 'file_sha256':digest, 'filename':filename,
            'connectors':[_public(plan) for plan in plans],
            'effects':{
                'active_connections_changed':False, 'external_called':False,
                'school_acceptance_changed':False, 'drafts_changed':False,
                'apply_target':'配置草稿、资料登记、凭据证书元数据、权威来源台账'
            }
        }


@router.post('/connections/intake-apply')
async def intake_apply(request: Request):
    with request.app.state.sessions.begin() as db:
        actor, session = current_actor(db, request, write=True)
        actor.require_admin()
        actor.require('sync.manage')
    try:
        reason = unquote(request.headers.get('x-intake-reason','')).strip()
        basis = unquote(request.headers.get('x-intake-basis','')).strip()
    except Exception:
        raise HTTPException(422, '导入原因或依据编码无效') from None
    if not 2 <= len(reason) <= 2000 or len(basis) > 2000:
        raise HTTPException(422, '请填写有效的导入原因和依据说明')
    filename, data = await _upload_bytes(request)
    digest = sha256(data).hexdigest()
    parsed = await run_in_threadpool(parse_intake_workbook, data)
    payload = {'format':parsed['format'], 'file_sha256':digest,
               'filename':filename, 'reason':reason, 'basis':basis}

    def apply(db, actor, session):
        actor.require_admin()
        plans = _plan(db, parsed, lock=True)
        results = {}
        for plan in plans:
            obj = plan['obj']
            before = {
                'draft':serial(plan['draft']) if plan['draft'] else {},
                'materials':serial(stored(db,'materials',obj.id)) if stored(db,'materials',obj.id) else {},
                'credential':serial(stored(db,'credential',obj.id)) if stored(db,'credential',obj.id) else {},
                'sources':serial(stored(db,'sources',obj.id)) if stored(db,'sources',obj.id) else {},
                'identity_policy':serial(stored(db,'identity_policy',obj.id)) if stored(db,'identity_policy',obj.id) else {}
            }
            draft = save_stored(db, 'draft', obj.id, {
                'base_version':obj.version, 'config':plan['config'], 'mappings':plan['mappings']
            })
            materials = save_stored(db, 'materials', obj.id, {'items':plan['materials']})
            credential_value = dict(plan['credential'])
            credential_value.update(recorded_at=utcnow().isoformat(), recorded_by=actor.id)
            credential = save_stored(db, 'credential', obj.id, credential_value)
            sources = None
            identity_policy = None
            if plan['code'] in {'middle','province'}:
                sources = save_stored(db, 'sources', obj.id, {'items':plan['sources']})
            if plan['code'] == 'sso':
                identity_policy = save_stored(db, 'identity_policy', obj.id, {
                    'authorization_mode':'LOCAL_ROLE_AUTHORITATIVE',
                    'items':plan['role_policy']
                })

            invalidate_acceptance(db, obj.id, actor.id, '导入新的学校联调资料')
            intake = save_stored(db, 'intake', obj.id, {
                'format':parsed['format'], 'file_sha256':digest, 'filename':filename,
                'imported_at':utcnow().isoformat(), 'imported_by':actor.id,
                'connection_version':obj.version, 'draft_version':draft.version
            })
            after = {
                'draft_version':draft.version, 'materials_version':materials.version,
                'credential_version':credential.version,
                'source_version':sources.version if sources else _expected_version(parsed,plan['code'],'source_version'),
                'identity_policy_version':identity_policy.version if identity_policy else _expected_version(parsed,plan['code'],'identity_policy_version'),
                'configuration_issues':plan['issues'], 'source_gaps':plan['source_gaps'],
                'file_sha256':digest
            }
            audit(db, actor, 'connections', obj.id, '导入学校接口资料到实施草稿',
                  before=before, after=after, reason=reason)
            results[plan['code']] = {
                'name':NAMES[plan['code']], 'draft_version':draft.version,
                'connection_version':obj.version, 'active_unchanged':True,
                'configuration_issues':list(plan['issues']),
                'source_gaps':list(plan['source_gaps']),
                'materials_complete':plan['material_complete'],
                'credential_state':plan['asset']['state']
            }

        return {
            'applied':True, 'file_sha256':digest, 'connections':results,
            'external_called':False, 'published':False,
            'school_acceptance':False,
            'note':'学校资料已写入实施草稿和台账；生效连接未改变。请逐项预览、真实测试后再明确发布。'
        }

    return command(request, payload, 'sync.manage', apply)
