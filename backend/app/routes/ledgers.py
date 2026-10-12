"""学院台账报送、口径体检、继续教育学院核定，以及首页五项指标。"""
import re
import os
import secrets
from datetime import date, timedelta
from hashlib import sha256
from uuid import uuid4
from decimal import Decimal, ROUND_FLOOR
from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form, Query
from typing import Literal
from pydantic import BaseModel, Field
from sqlalchemy import select, func, or_, and_
from starlette.concurrency import run_in_threadpool
from ..core import command, read_operation, serial, current_actor, workflow, check_version
from ..models import Org, User, Role, Qualification, PointEntry, Period, Setting, Attachment
from ..safe_files import open_nofollow
from ..reference_data import TrainingProjectMaster
from ..social_models import SocialResource, SocialProject, SocialClaim, SocialUnit, SocialPolicy
from .. import social_training as st
from ..social_schemas import ProjectData
from .. import ledger_check as lc

router = APIRouter(prefix='/api/social', tags=['学院台账与口径体检'])
RECOMMENDED_NOTE = '推荐值按系统推荐口径计算，学校书面确认前仅供核对，不是正式认定结果。'


class ReviewRow(BaseModel):
    row_no: int = Field(ge=1)
    approved: Decimal | None = Field(default=None, ge=0, le=10_000_000, allow_inf_nan=False)
    reason: str = Field(default='', max_length=500)


class FigureIn(BaseModel):
    expected_version: int = Field(ge=1)
    value: Decimal | None = Field(default=None, ge=0, le=100_000_000, allow_inf_nan=False)
    reason: str = Field(min_length=2, max_length=2000)


class DraftsIn(BaseModel):
    expected_version: int = Field(ge=1)
    rows: list[int] = Field(default_factory=list, max_length=500)
    reason: str = Field(min_length=2, max_length=2000)


class PersonBindingIn(BaseModel):
    expected_version: int = Field(ge=1)
    allocation_index: int = Field(ge=0, le=500)
    teacher_id: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=2, max_length=2000)


class ProjectBindingIn(BaseModel):
    expected_version: int = Field(ge=1)
    action: Literal['link', 'new', 'owner']
    project_id: str | None = Field(default=None, max_length=64)
    owner_id: str | None = Field(default=None, max_length=64)
    reason: str = Field(min_length=2, max_length=2000)


class TargetRow(BaseModel):
    org_id: str = Field(min_length=1, max_length=64)
    income: Decimal | None = Field(default=None, ge=0, le=10_000_000_000, allow_inf_nan=False)
    participants: Decimal | None = Field(default=None, ge=0, le=100_000_000, allow_inf_nan=False)
    priority: Decimal | None = Field(default=None, ge=0, le=100_000_000, allow_inf_nan=False)
    priority_actual: Decimal | None = Field(default=None, ge=0, le=100_000_000, allow_inf_nan=False)
    students: Decimal | None = Field(default=None, ge=0, le=1_000_000, allow_inf_nan=False)
    teachers: Decimal | None = Field(default=None, ge=0, le=100_000, allow_inf_nan=False)
    compliance_failures: int | None = Field(default=None, ge=0, le=100)
    compliance_scope: Literal['other_only'] | None = None
    veto_reason: str | None = Field(default=None, max_length=500)


class TargetsIn(BaseModel):
    year: int = Field(ge=2020, le=2100)
    items: list[TargetRow] = Field(max_length=200)
    reason: str = Field(min_length=2, max_length=2000)


class ReviewIn(BaseModel):
    expected_version: int = Field(ge=1)
    rows: list[ReviewRow] = Field(max_length=500)
    reason: str = Field(min_length=2, max_length=2000)
    basis: str = Field(default='', max_length=2000)


def college_scope(db, a):
    """当前账号能看的学院：学校看全部，学院看本院，教研室和老师看所属学院。"""
    if a.role.kind == 'teacher' or a.org.kind != 'college' and a.role.kind != 'school':
        org = a.org if a.org.kind == 'college' else db.get(Org, a.org.parent_id)
        return [org] if org else []
    return [o for o in db.scalars(select(Org).where(Org.id.in_(a.org_ids), Org.kind == 'college', Org.active.is_(True)).order_by(Org.name))]


def require_college(db, a, org_id):
    org = db.get(Org, org_id)
    if not org or org.kind != 'college' or not org.active or org_id not in a.org_ids: raise HTTPException(403, '学院超出授权范围')
    return org


def match_college(db, a, name):
    if not name: return None
    for org in college_scope(db, a):
        if org.name == name or name in org.name or org.name in name: return org.id
    return None


def ledgers(db, org_ids, year=None):
    query = select(SocialResource).where(SocialResource.kind == 'ledger', SocialResource.org_id.in_(org_ids))
    rows = db.scalars(query.order_by(SocialResource.created_at, SocialResource.id)).all()
    return [r for r in rows if year is None or r.data.get('year') == year]


def latest_by_college(rows):
    latest = {}
    for r in rows: latest[(r.org_id, r.data['year'])] = r
    return latest


def online(rows):
    """线上浏览量单独登记为“线上影响力”，不计人次。"""
    hits = [r for r in rows if any(i['code'] == 'ONLINE_VIEWS' for i in r.get('issues', []))]
    return {'views': lc.q2(sum((Decimal(r['people'] or 0) for r in hits), Decimal(0))), 'projects': len(hits)}


def figure_diff(r):
    fig = r.data.get('school_figure')
    if not fig or fig.get('value') is None: return None
    final = Decimal(lc.totals(r.data['rows'])['final_total'])
    return {**fig, 'diff': lc.q2(final - Decimal(fig['value']))}


def public(r, rows=True):
    data = dict(r.data)
    if not rows: data.pop('rows', None)
    return {'id': r.id, 'org_id': r.org_id, 'code': r.code, 'name': r.name, 'state': r.state, 'version': r.version,
            'created_at': serial(r.created_at), 'data': data, 'totals': lc.totals(r.data['rows']),
            'online': online(r.data['rows']), 'school_figure': figure_diff(r), 'drafts': sum(1 for x in r.data['rows'] if x.get('project_id'))}


def bind_allocations(db, org_id, row):
    allocations = []
    for item in row.get('allocations', []):
        teacher = st.resolve_teacher(db, org_id, item['name'], item.get('teacher_id'))
        allocations.append({**item, 'teacher_id': teacher.id if teacher else None,
                            'binding_status': '已关联' if teacher else '待确认人员'})
    return {**row, 'allocations': allocations}


def row_identity(row):
    # 行号、核定数字和表格位置会随换版改变，不能作为项目身份。
    return tuple(str(row.get(k) or '').strip() for k in ('name', 'people', 'hours', 'coeff', 'allocation', 'materials', 'remark'))


def link_previous_rows(rows, previous):
    old_rows = [row for ledger in previous for row in ledger.data['rows']]
    source_projects = {row['source_key']: row['project_id'] for row in old_rows if row.get('source_key') and row.get('project_id')}
    out = []
    for row in rows:
        same_name = [old for old in old_rows if old.get('name') == row.get('name')]
        exact = [old for old in same_name if row_identity(old) == row_identity(row)]
        identities = {old.get('project_id') or source_projects.get(old.get('source_key')) or old.get('source_key') for old in exact}
        ambiguous = sum(other.get('name') == row.get('name') for other in rows) != 1
        chosen = next((old for old in reversed(exact) if old.get('project_id')), exact[-1]) if exact and None not in identities and len(identities) == 1 and not ambiguous else None
        linked = {k: chosen[k] for k in ('source_key', 'project_id', 'project_code', 'owner_id') if k in chosen} if chosen else {}
        if chosen:
            old_allocations = chosen.get('allocations', [])
            if [(x['name'], x['value']) for x in old_allocations] == [(x['name'], x['value']) for x in row.get('allocations', [])]:
                row = {**row, 'allocations': old_allocations}
        out.append({**row, **linked, 'source_key': linked.get('source_key') or uuid4().hex,
                    'project_link_status': 'matched' if chosen else 'pending' if same_name or ambiguous else 'new'})
    return out


def ledger_conflicts(db, a, obj):
    st.check_conflicts(db, a, org=obj.org_id)
    org_ids = [obj.org_id] + [o.id for o in db.scalars(select(Org).where(Org.parent_id == obj.org_id))]
    for row in obj.data['rows']:
        owners = {x.get('teacher_id') for x in row.get('allocations', [])} | {row.get('owner_id')}
        pending_names = {x['name'] for x in row.get('allocations', []) if not x.get('teacher_id')}
        if pending_names:
            owners.update(db.scalars(select(User.id).where(User.org_id.in_(org_ids), User.name.in_(pending_names))))
        project = db.get(SocialProject, row['project_id']) if row.get('project_id') else None
        if project: owners.add(project.owner_id)
        for owner in owners - {None}: st.check_conflicts(db, a, owner=owner, org=obj.org_id)


async def _read(request, file, permission, store=False):
    def authorize():
        with request.app.state.sessions.begin() as db:
            a, s = current_actor(db, request, write=True); a.require(permission); require_ledger_role(a)
            if store: a.require('file.write')
    await run_in_threadpool(authorize)
    data = await file.read(lc.MAX_BYTES + 1); await file.close()
    name = file.filename or ''
    if not name or len(name) > 200 or '/' in name or '\\' in name or any(ord(c) < 32 for c in name):
        raise HTTPException(422, '台账文件名无效')
    result = await run_in_threadpool(lambda: lc.check(lc.parse(data, name)))
    return data, name, result


@router.post('/ledgers/preview')
async def ledger_preview(request: Request, file: UploadFile = File(...)):
    data, name, result = await _read(request, file, 'records.write')
    with request.app.state.sessions.begin() as db:
        a, s = current_actor(db, request)
        result['suggested_org_id'] = match_college(db, a, result['meta']['college'])
        result['colleges'] = [{'id': o.id, 'name': o.name} for o in college_scope(db, a)]
        if result['suggested_org_id']:
            result['rows'] = [bind_allocations(db, result['suggested_org_id'], row) for row in result['rows']]
    result['file'] = {'name': name, 'sha256': sha256(data).hexdigest(), 'size': len(data)}
    result['note'] = RECOMMENDED_NOTE
    return serial(result)


@router.post('/ledgers')
async def ledger_submit(request: Request, file: UploadFile = File(...), org_id: str = Form(...), year: int = Form(..., ge=2020, le=2100), reason: str = Form(...)):
    if not 2 <= len(reason.strip()) <= 2000: raise HTTPException(422, '请填写报送说明')
    data, name, result = await _read(request, file, 'records.write', store=True)
    digest = sha256(data).hexdigest()
    payload = {'org_id': org_id, 'year': year, 'sha256': digest, 'reason': reason}
    written = []

    def apply(db, a, s):
        org = require_college(db, a, org_id)
        a.require('file.write')
        previous = [r for r in ledgers(db, [org.id], year)]
        if any(r.data['file']['sha256'] == digest for r in previous): raise HTTPException(409, '这份表格已经报送过，不用重复上传')
        stored = {'year': year, 'file': {'name': name, 'sha256': digest, 'size': len(data)}, 'meta': result['meta'],
                  'template': result['template'], 'template_label': result['template_label'], 'sheet_total': result['sheet_total'],
                  'notes': result['notes'], 'summary': result['summary'], 'submitted_by': a.id, 'submit_reason': reason,
                  'version_no': len(previous) + 1, 'rows': [bind_allocations(db, org.id, row) for row in link_previous_rows([{**row, 'approved': None, 'approved_reason': ''} for row in result['rows']], previous)]}
        obj = SocialResource(kind='ledger', org_id=org.id, code=f'TZ-{year}-{uuid4().hex[:12]}',
                             name=f'{org.name}{year}年社会培训人次统计表（第{len(previous) + 1}版）', state='SUBMITTED', data=serial(stored))
        db.add(obj); db.flush()
        root = request.app.state.settings.storage_dir
        if root.is_symlink() or not root.is_dir(): raise HTTPException(503, '附件目录未就绪')
        key = secrets.token_hex(32); path = root / key
        fd = open_nofollow(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600); written.append(path)
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data); handle.flush(); os.fsync(handle.fileno())
        mime = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' if name.lower().endswith('.xlsx') else 'application/vnd.ms-excel'
        attachment = Attachment(object_type='social_resource', object_id=obj.id, teacher_id=a.id, uploaded_by=a.id,
                                name=name, storage_key=key, sha256=digest, size=len(data), mime=mime)
        db.add(attachment); db.flush()
        stored['file'] = {**stored['file'], 'id': attachment.id, 'download_url': f'/api/attachments/{attachment.id}/download'}
        obj.data = serial(stored)
        workflow(db, a, 'social_resource', obj.id, '报送学院培训台账', {}, {'file': stored['file'], 'summary': stored['summary']}, reason)
        return public(obj)
    def run():
        try: return command(request, payload, 'records.write', apply)
        except Exception:
            for path in written:
                try: path.unlink()
                except OSError: pass # 回滚失败的孤立文件仍处于非公开附件目录。
            raise
    return await run_in_threadpool(run)


@router.get('/ledgers')
def ledger_list(request: Request, year: int | None = Query(None, ge=2020, le=2100)):
    def load(db, a, s):
        require_ledger_role(a)
        colleges = college_scope(db, a)
        rows = ledgers(db, [o.id for o in colleges], year)
        latest = latest_by_college(rows)
        versions = {}
        for r in rows: versions.setdefault((r.org_id, r.data['year']), []).append({'id': r.id, 'version_no': r.data['version_no'], 'created_at': serial(r.created_at), 'claimed_total': lc.totals(r.data['rows'])['claimed_total']})
        names = {o.id: o.name for o in colleges}
        items = []
        for (org_id, y), r in sorted(latest.items(), key=lambda kv: (-kv[0][1], names.get(kv[0][0], ''))):
            items.append({**public(r, rows=False), 'org_name': names.get(org_id, ''), 'versions': versions[(org_id, y)]})
        missing = [{'org_id': o.id, 'org_name': o.name} for o in colleges if year and (o.id, year) not in latest]
        return {'items': items, 'missing': missing, 'year': year, 'note': RECOMMENDED_NOTE,
                'online': {'views': lc.q2(sum((Decimal(x['online']['views']) for x in items), Decimal(0))), 'projects': sum(x['online']['projects'] for x in items)},
                'can_review': a.role.kind == 'school' and 'records.write' in a.permissions,
                'can_submit': a.role.kind in LEDGER_ROLES and 'records.write' in a.permissions and 'file.write' in a.permissions}
    return read_operation(request, 'records.read', load)


LEDGER_ROLES = ('college', 'school')


def require_ledger_role(a):
    """学院台账逐行含全院教师人次分配：由学院报送、学校核定。教研室和教师不能读取整院明细（招标第2项：教师仅本人、教研室仅本教研室）。"""
    if a.role.kind not in LEDGER_ROLES: raise HTTPException(403, '学院台账由学院报送、学校核定；教师请在“个人培训”查看分给本人的人次')


def scoped_ledger(db, a, ident):
    require_ledger_role(a)
    obj = db.get(SocialResource, ident)
    if not obj or obj.kind != 'ledger' or obj.org_id not in {o.id for o in college_scope(db, a)}: raise HTTPException(404, '台账不存在或超出授权范围')
    return obj


@router.get('/ledgers/{ident}')
def ledger_detail(ident: str, request: Request):
    def load(db, a, s):
        obj = scoped_ledger(db, a, ident)
        org = db.get(Org, obj.org_id)
        others = [{'id': r.id, 'version_no': r.data['version_no'], 'created_at': serial(r.created_at), 'totals': lc.totals(r.data['rows'])} for r in ledgers(db, [obj.org_id], obj.data['year'])]
        submitter = db.get(User, obj.data.get('submitted_by'))
        can_bind = 'records.write' in a.permissions and a.role.kind in ('school', 'college')
        org_ids = [obj.org_id] + [o.id for o in db.scalars(select(Org).where(Org.parent_id == obj.org_id))]
        teachers = db.scalars(select(User).join(Role, Role.id == User.role_id).where(User.org_id.in_(org_ids), User.active.is_(True), Role.kind == 'teacher')).all() if can_bind else []
        projects = db.scalars(select(SocialProject).where(SocialProject.org_id == obj.org_id)).all() if can_bind else []
        return {**public(obj), 'org_name': org.name if org else '', 'versions': others, 'submitted_by_name': submitter.name if submitter else '',
                'note': RECOMMENDED_NOTE, 'can_review': a.role.kind == 'school' and 'records.write' in a.permissions,
                'can_draft': can_bind, 'teacher_options': [{'id': u.id, 'name': u.name, 'employee_no': u.staff_no} for u in teachers],
                'project_options': [{'id': p.id, 'code': p.data.get('code'), 'name': p.data.get('name')} for p in projects]}
    return read_operation(request, 'records.read', load)


@router.post('/ledgers/{ident}/review')
def ledger_review(ident: str, data: ReviewIn, request: Request):
    def apply(db, a, s):
        if a.role.kind != 'school': raise HTTPException(403, '核定由继续教育与乡村振兴学院（学校账号）办理')
        obj = scoped_ledger(db, a, ident); check_version(obj, data.expected_version)
        ledger_conflicts(db, a, obj)
        rows = [dict(r) for r in obj.data['rows']]; index = {r['row_no']: r for r in rows}
        changed = []
        for item in data.rows:
            row = index.get(item.row_no)
            if row is None: raise HTTPException(422, f'第 {item.row_no} 行不在这份台账里')
            if item.approved is not None and item.approved != Decimal(row['recommended']) and len(item.reason.strip()) < 2:
                raise HTTPException(422, f'第 {item.row_no} 行核定值和推荐值不同，请写核减或调整理由')
            before = (row['approved'], row['approved_reason'])
            row['approved'] = None if item.approved is None else lc.q2(item.approved)
            row['approved_reason'] = item.reason.strip()
            if before != (row['approved'], row['approved_reason']): changed.append({'row_no': row['row_no'], 'before': before[0], 'after': row['approved']})
        if not changed: raise HTTPException(409, '没有需要保存的核定变化')
        before = {'totals': lc.totals(obj.data['rows'])}
        obj.data = {**obj.data, 'rows': rows}
        totals = lc.totals(rows)
        obj.state = 'ACTIVE' if totals['state'] == '已核定' else 'SUBMITTED'
        obj.version += 1; db.flush()
        workflow(db, a, 'social_resource', obj.id, '核定学院培训台账', before, {'totals': totals, 'changed': changed}, data.reason, data.basis)
        return public(obj)
    return command(request, data.model_dump(mode='json'), 'records.write', apply)


@router.post('/ledgers/{ident}/school-figure')
def ledger_school_figure(ident: str, data: FigureIn, request: Request):
    """学校人工核定总数：和系统核定后人次逐份对比，一致后再切正式口径（规划第 8 步）。"""
    def apply(db, a, s):
        if a.role.kind != 'school': raise HTTPException(403, '学校人工核定数由学校账号登记')
        obj = scoped_ledger(db, a, ident); check_version(obj, data.expected_version)
        ledger_conflicts(db, a, obj)
        before = {'school_figure': obj.data.get('school_figure')}
        figure = None if data.value is None else {'value': lc.q2(data.value), 'reason': data.reason.strip(), 'by': a.id, 'on': date.today().isoformat()}
        obj.data = {**obj.data, 'school_figure': figure}
        obj.version += 1; db.flush()
        workflow(db, a, 'social_resource', obj.id, '登记学校人工核定人次', before, {'school_figure': figure}, data.reason)
        return public(obj)
    return command(request, data.model_dump(mode='json'), 'records.write', apply)


DATE_IN_NAME = re.compile(r'(20\d{2})[.\-/年](\d{1,2})[.\-/月](\d{1,2})')


def binding_row(db, a, ident, row_no, version):
    if a.role.kind not in ('school', 'college'): raise HTTPException(403, '台账关联由学院或学校账号确认')
    obj = scoped_ledger(db, a, ident); check_version(obj, version)
    rows = [dict(r) for r in obj.data['rows']]
    row = next((r for r in rows if r['row_no'] == row_no), None)
    if row is None: raise HTTPException(404, '台账行不存在')
    return obj, rows, row


@router.post('/ledgers/{ident}/rows/{row_no}/person')
def bind_person(ident: str, row_no: int, data: PersonBindingIn, request: Request):
    def apply(db, a, s):
        obj, rows, row = binding_row(db, a, ident, row_no, data.expected_version)
        allocations = [dict(x) for x in row.get('allocations', [])]
        if data.allocation_index >= len(allocations): raise HTTPException(422, '个人分配条目不存在')
        item = allocations[data.allocation_index]
        teacher = st.resolve_teacher(db, obj.org_id, item['name'], data.teacher_id)
        if not teacher: raise HTTPException(422, '请选择本学院与原表姓名相符的有效教师')
        before = dict(item); item.update(teacher_id=teacher.id, binding_status='已确认')
        row['allocations'] = allocations; obj.data = {**obj.data, 'rows': rows}; obj.version += 1
        workflow(db, a, 'social_resource', obj.id, '确认台账个人归属', before, item, data.reason)
        return public(obj)
    return command(request, data.model_dump(mode='json'), 'records.write', apply)


@router.post('/ledgers/{ident}/rows/{row_no}/project-link')
def bind_project(ident: str, row_no: int, data: ProjectBindingIn, request: Request):
    def apply(db, a, s):
        obj, rows, row = binding_row(db, a, ident, row_no, data.expected_version)
        before = {k: row.get(k) for k in ('project_id', 'project_code', 'owner_id', 'project_link_status')}
        if row.get('project_id'): raise HTTPException(409, '该行已经关联项目，不能覆盖既有项目关联')
        if data.action == 'link':
            project = db.get(SocialProject, data.project_id) if data.project_id else None
            if not project or project.org_id != obj.org_id: raise HTTPException(422, '请选择本学院已有项目')
            if any(r.get('project_id') == project.id for r in rows): raise HTTPException(409, '同一份台账不能重复关联一个项目')
            row.update(project_id=project.id, project_code=project.data.get('code'), project_link_status='matched')
        elif data.action == 'new':
            row.update(source_key=uuid4().hex, project_link_status='new')
        else:
            owner = db.get(User, data.owner_id) if data.owner_id else None
            org_ids = [obj.org_id] + [o.id for o in db.scalars(select(Org).where(Org.parent_id == obj.org_id))]
            if not owner or not owner.active or owner.org_id not in org_ids: raise HTTPException(422, '请选择本学院有效负责人账号')
            row['owner_id'] = owner.id
        obj.data = {**obj.data, 'rows': rows}; obj.version += 1
        workflow(db, a, 'social_resource', obj.id, '确认台账项目关联', before,
                 {k: row.get(k) for k in ('project_id', 'project_code', 'owner_id', 'project_link_status')}, data.reason)
        return public(obj)
    return command(request, data.model_dump(mode='json'), 'records.write', apply)


def draft_owner(db, org, row, actor):
    """项目负责人：先找台账里分到人次的老师，再找本院负责人账号。"""
    org_ids = [org.id] + [o.id for o in db.scalars(select(Org).where(Org.parent_id == org.id))]
    users = db.scalars(select(User).where(User.org_id.in_(org_ids), User.active.is_(True)).order_by(User.id)).all()
    if row.get('owner_id'): return next((u for u in users if u.id == row['owner_id']), None)
    for alloc in row.get('allocations', []):
        if not alloc.get('teacher_id'): return None
    for alloc in row.get('allocations', []):
        hit = next((u for u in users if u.id == alloc.get('teacher_id')), None)
        if hit: return hit
    if actor.org.id in org_ids: return db.get(User, actor.id)
    return None


@router.post('/ledgers/{ident}/projects')
def ledger_drafts(ident: str, data: DraftsIn, request: Request):
    """台账一行生成一个培训项目草稿（规划第 3 步），再由学院补全材料走申报备案。"""
    def apply(db, a, s):
        if a.role.kind not in ('school', 'college'): raise HTTPException(403, '项目草稿由学院或学校账号生成')
        obj = scoped_ledger(db, a, ident); check_version(obj, data.expected_version)
        org = require_college(db, a, obj.org_id); year = obj.data['year']
        rows = [dict(r) for r in obj.data['rows']]
        wanted = set(data.rows) or {r['row_no'] for r in rows}
        made, skipped = [], []
        for row in rows:
            if row['row_no'] not in wanted or row.get('project_id'): continue
            if row.get('project_link_status') == 'pending':
                skipped.append({'row_no': row['row_no'], 'reason': '同名项目对应关系待确认，请关联已有项目或明确新建'}); continue
            source_key = row.get('source_key') or uuid4().hex
            existing = db.scalar(select(SocialProject).where(SocialProject.org_id == org.id, SocialProject.data['source']['source_key'].as_string() == source_key))
            if existing:
                row.update(project_id=existing.id, project_code=existing.data.get('code'), source_key=source_key, project_link_status='matched')
                skipped.append({'row_no': row['row_no'], 'reason': '已关联同一来源项目'}); continue
            final = Decimal(row['approved'] if row.get('approved') not in (None, '') else row['recommended'])
            if final <= 0: skipped.append({'row_no': row['row_no'], 'reason': '人次为 0（如线上浏览量），不生成项目'}); continue
            owner = draft_owner(db, org, row, a)
            if not owner: skipped.append({'row_no': row['row_no'], 'reason': '人员归属或负责人待确认，请先明确关联人员'}); continue
            m = DATE_IN_NAME.search(row['name'] or '')
            try: start = end = date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None
            except ValueError: start = end = None
            dates_pending = start is None
            if dates_pending: start, end = date(year, 1, 1), date(year, 12, 31)
            name = (row['name'] or f'第{row["row_no"]}行项目')[:160]
            code = f'TZ{year}-{source_key}'[:64]
            lecture = any(w in name for w in ('公益', '讲座', '宣讲', '普及', '启蒙'))
            p = ProjectData(code=code, name=name, cohort='第1期', org_id=org.id, owner_id=owner.id,
                            category='community' if '公益' in name else 'other', expected_income=Decimal(0),
                            expected_participants=int(final), expected_outcomes=f'由{year}年学院台账第{row["row_no"]}行生成，预期成果待学院补充',
                            start_date=start, end_date=end, mode='person_day' if row.get('mode') == '人天式' else 'module',
                            class_type='lecture' if lecture else 'technical', level='school', scene='ordinary')
            master = db.scalar(select(TrainingProjectMaster).where(TrainingProjectMaster.code == code))
            if master and db.scalar(select(SocialProject).where(SocialProject.master_id == master.id, SocialProject.cohort == '第1期')):
                skipped.append({'row_no': row['row_no'], 'reason': f'项目 {code} 已存在'}); continue
            if not master:
                master = TrainingProjectMaster(code=code, name=name, start_date=start, end_date=end, source='学院台账生成'); db.add(master); db.flush()
            project = SocialProject(master_id=master.id, org_id=org.id, owner_id=owner.id, cohort='第1期',
                                    data={**serial(p.model_dump()), 'source': {'ledger_id': obj.id, 'row_no': row['row_no'], 'source_key': source_key,
                                          'dates_pending': dates_pending, 'mode_pending': bool(row.get('needs_mode_confirmation')),
                                          'policy_pending': ['level', 'scene']}})
            db.add(project); db.flush()
            workflow(db, a, 'social_project', project.id, '由学院台账生成项目草稿', {}, serial(project), data.reason)
            row['project_id'], row['project_code'] = project.id, code
            row.update(source_key=source_key, owner_id=owner.id, project_link_status='matched')
            made.append({'row_no': row['row_no'], 'project_id': project.id, 'code': code, 'owner': owner.name})
        if not made and not skipped: raise HTTPException(409, '所选的行都已经生成过项目')
        before = {'drafts': sum(1 for x in obj.data['rows'] if x.get('project_id'))}
        obj.data = {**obj.data, 'rows': rows}; obj.version += 1; db.flush()
        workflow(db, a, 'social_resource', obj.id, '台账生成项目草稿', before, {'made': made, 'skipped': skipped}, data.reason)
        return {**public(obj), 'made': made, 'skipped': skipped}
    return command(request, data.model_dump(mode='json'), 'records.write', apply)


TARGETS_KEY = 'social_targets'
NOTE_ESTIMATE = '速算按系统推荐口径（考核细则四项：收入、人次、成果、资金管理）。逾期结算由财务在项目跟踪中认定不合规或批准例外，未核验时不出资金分和总分；与正式考核共用项目核验事实，其他不合规次数不含已在项目中认定的结算事项。学校书面确认前仅供参考。'


def steps(value, unit):
    return (value / Decimal(unit)).to_integral_value(rounding=ROUND_FLOOR)


def quick_annual(income, participants, priority, targets, achievement_levels, funding=None):
    """学院年度考核速算：与 annual_trial 同一套推荐口径（满 10% 才扣/加一档，加分合计不超过 10）。"""
    metrics, bonus, missing = [], Decimal(0), []
    for label, key, actual, base, loss_unit, loss, extra_cap in [('收入', 'income', income, 40, 1, 1, 10), ('培训人次', 'participants', participants, 20, 10, 2, 5), ('重点群体', 'priority', priority, 10, 10, 1, 5)]:
        target = targets.get(key)
        no_target = target in (None, '') or Decimal(str(target)) <= 0
        if no_target or actual is None:
            missing += [label + '目标'] * no_target + [label + '实际数'] * (actual is None); metrics.append({'label': label, 'actual': None if actual is None else lc.q2(actual), 'target': target, 'score': None}); continue
        percent = actual / Decimal(str(target)) * 100
        score = max(Decimal(0), Decimal(base) - steps(max(Decimal(0), 100 - percent), loss_unit) * loss)
        extra = min(Decimal(extra_cap), steps(max(Decimal(0), percent - 100), 10))
        bonus += extra
        metrics.append({'label': label, 'actual': lc.q2(actual), 'target': lc.q2(Decimal(str(target))), 'completion': lc.q2(percent), 'score': lc.q2(score), 'bonus': lc.q2(extra)})
    recognized = Decimal(achievement_levels.get('national', 0) * 10 + achievement_levels.get('province', 0) * 5 + achievement_levels.get('school', 0) * 2)
    results = min(Decimal(10), recognized); bonus += max(Decimal(0), recognized - 10)
    # 两个年度入口共用财务认定事实，待核验的逾期不能直接当成不合规。
    funding = funding or {'late': 0, 'penalty': Decimal(0), 'details': [], 'veto': []}
    manual = int(targets.get('compliance_failures') or 0)
    cost, funding_blockers = st.funding_cost(funding, manual, targets.get('compliance_scope'))
    missing += funding_blockers
    cost_details = funding['details'] + ([f'学校确认其他不合规 {manual} 次，扣 {manual * 5} 分'] if manual else [])
    veto = [x for x in [targets.get('veto_reason')] + funding['veto'] if x]
    extra = {'cost_details': cost_details, 'veto': '；'.join(veto) or None}
    if missing: return {'metrics': metrics, 'results': lc.q2(results), 'cost': None if funding_blockers else lc.q2(cost), 'total': None, 'grade': '不合格（一票否决）' if veto else None, 'missing': missing, **extra}
    total = min(Decimal(110), sum(Decimal(m['score']) for m in metrics) + results + cost + min(Decimal(10), bonus))
    grade = '不合格（一票否决）' if veto else '优秀' if total >= 90 else '良好' if total >= 80 else '合格' if total >= 60 else '不合格'
    return {'metrics': metrics, 'results': lc.q2(results), 'cost': lc.q2(cost), 'bonus': lc.q2(min(Decimal(10), bonus)), 'total': lc.q2(total), 'grade': grade, 'missing': [], **extra}


def college_funding(db, org, year):
    """与正式年度考核读取相同的结项项目及财务核验记录。"""
    return st.project_funding(db, st.confirmed_projects(db, org.id, date(year,1,1), date(year,12,31)))


def college_income(db, org, year):
    return st.confirmed_project_income(db, org.id, date(year, 1, 1), date(year, 12, 31))


def annual_achievements(db, org_ids, year):
    rows = db.scalars(select(SocialResource).where(SocialResource.kind == 'achievement', SocialResource.org_id.in_(org_ids))).all()
    dated = [(row, st.achievement_year(db, row)) for row in rows]
    return [row for row, y in dated if y == year], sum(y is None for _, y in dated)


def sections(a):
    return {'records': 'records.read' in a.permissions, 'points': 'points.read' in a.permissions,
            'qualifications': 'qualification.read' in a.permissions}


def targets_for(db, year):
    setting = db.get(Setting, TARGETS_KEY)
    return (setting.value if setting else {}).get(str(year), {})


def suggest_targets(t):
    """管理办法第二十三条、考核细则：人次目标一般为在校生数 2 倍，重点群体目标一般为 0.5 倍。收入目标学校没给人均标准，不能自动算。"""
    students = t.get('students')
    if students in (None, ''): return None
    n = Decimal(str(students))
    return {'participants': lc.q2(n * 2), 'priority': lc.q2(n / 2)}


@router.get('/targets')
def targets(request: Request, year: int = Query(..., ge=2020, le=2100)):
    """各学院年度目标、完成率和年度考核速算（规划第 2、7 步）。"""
    def load(db, a, s):
        require_ledger_role(a)
        colleges = college_scope(db, a); saved = targets_for(db, year)
        latest = latest_by_college(ledgers(db, [o.id for o in colleges], year))
        items = []
        for org in colleges:
            t = saved.get(org.id, {})
            led = latest.get((org.id, year))
            participants = Decimal(lc.totals(led.data['rows'])['final_total']) if led else None
            income = college_income(db, org, year)
            priority = None if t.get('priority_actual') in (None, '') else Decimal(str(t['priority_actual']))
            achievements, achievements_pending = annual_achievements(db, [org.id], year)
            best = {}
            for x in achievements:
                ref = x.data.get('reference') or x.id; lvl = x.data.get('level', 'school')
                rank = {'national': 3, 'province': 2, 'school': 1}.get(lvl, 1)
                if rank > best.get(ref, (0, ''))[0]: best[ref] = (rank, lvl)
            levels = {'national': 0, 'province': 0, 'school': 0}
            for _, lvl in best.values(): levels[lvl] = levels.get(lvl, 0) + 1
            items.append({'org_id': org.id, 'org_name': org.name, 'targets': t, 'actual': {'income': lc.q2(income), 'participants': None if participants is None else lc.q2(participants), 'priority': None if priority is None else lc.q2(priority)},
                          'achievements': levels, 'achievements_pending': achievements_pending, 'estimate': quick_annual(income, participants, priority, t, levels, college_funding(db, org, year)),
                          'suggest': suggest_targets(t)})
        return {'year': year, 'items': items, 'can_edit': a.role.kind == 'school' and 'records.write' in a.permissions, 'note': NOTE_ESTIMATE}
    return read_operation(request, 'records.read', load)


@router.put('/targets')
def save_targets(data: TargetsIn, request: Request):
    def apply(db, a, s):
        if a.role.kind != 'school': raise HTTPException(403, '年度目标由学校下达')
        allowed = {o.id for o in college_scope(db, a)}
        setting = db.get(Setting, TARGETS_KEY)
        if not setting: setting = Setting(key=TARGETS_KEY, value={}, version=1); db.add(setting); db.flush()
        before = dict(setting.value)
        year = dict(before.get(str(data.year), {}))
        for row in data.items:
            if row.org_id not in allowed: raise HTTPException(403, '学院超出授权范围')
            year[row.org_id] = {**{k: (None if v is None else lc.q2(v)) for k, v in (('income', row.income), ('participants', row.participants), ('priority', row.priority), ('priority_actual', row.priority_actual), ('students', row.students), ('teachers', row.teachers))},
                                'compliance_failures': row.compliance_failures, 'compliance_scope':row.compliance_scope, 'veto_reason': (row.veto_reason or '').strip() or None}
        setting.value = {**before, str(data.year): year}; setting.version += 1; db.flush()
        workflow(db, a, 'setting', TARGETS_KEY, '下达学院年度社会培训目标', before.get(str(data.year), {}), year, data.reason)
        return {'year': data.year, 'targets': year}
    return command(request, data.model_dump(mode='json'), 'records.write', apply)


@router.get('/overview')
def overview(request: Request, year: int = Query(..., ge=2020, le=2100)):
    """首页分区按当前权限读取，学院收入复用正式项目财务事实。"""
    def load(db, a, s):
        allowed = sections(a)
        colleges = college_scope(db, a); org_ids = [o.id for o in colleges]
        latest = latest_by_college(ledgers(db, org_ids, year)) if allowed['records'] else {}
        people = {'claimed': Decimal(0), 'final': Decimal(0), 'reported': len(latest), 'colleges': len(colleges), 'pending_rows': 0, 'pending_ledgers': 0, 'mine': None}
        views = sum((Decimal(online(r.data['rows'])['views']) for r in latest.values()), Decimal(0))
        saved = targets_for(db, year) if allowed['records'] else {}
        target = sum((Decimal(str(saved.get(o, {}).get('participants') or 0)) for o in org_ids), Decimal(0))
        for r in latest.values():
            t = lc.totals(r.data['rows'])
            people['claimed'] += Decimal(t['claimed_total']); people['final'] += Decimal(t['final_total']); people['pending_rows'] += t['pending_rows']
            people['pending_ledgers'] += 1 if t['pending_rows'] else 0
        if a.role.kind == 'teacher':
            mine = Decimal(0); projects = 0
            for r in latest.values():
                for row in r.data['rows']:
                    hit = [Decimal(x['value']) for x in row.get('allocations', []) if x.get('teacher_id') == a.id]
                    if hit: mine += sum(hit); projects += 1
            people['mine'] = {'value': lc.q2(mine), 'projects': projects}
        achievements, achievements_pending = annual_achievements(db, org_ids, year) if allowed['records'] else ([], 0)
        levels = {'national': 0, 'province': 0, 'school': 0}
        for x in achievements: levels[x.data.get('level', 'school')] = levels.get(x.data.get('level', 'school'), 0) + 1
        teacher_scope = [a.id] if a.role.kind == 'teacher' else None
        q = select(Qualification).where(Qualification.state == 'APPROVED', Qualification.category.like('双师型%'))
        q = q.where(Qualification.teacher_id.in_(teacher_scope)) if teacher_scope else q.where(a.scope(Qualification.teacher_id))
        dual = {'初级': set(), '中级': set(), '高级': set(), '未分级': set()}
        for item in db.scalars(q) if allowed['qualifications'] else []:
            level = next((k for k in ('高级', '中级', '初级') if k in item.category or k in item.name), '未分级')
            dual[level].add(item.teacher_id)
        holders = set().union(*dual.values())
        mine_level = next((k for k in ('高级', '中级', '初级', '未分级') if a.id in dual[k]), None)
        points = None
        if a.role.kind == 'teacher' and allowed['points']:
            # 社会培训积分：本年度与近五年合计；职称分按每 100 积分折 1 分试算（积分办法第十六条，待学校确认）。
            rows = db.execute(select(Period.start_date, PointEntry.amount).join(Period, Period.id == PointEntry.period_id).where(PointEntry.teacher_id == a.id, PointEntry.kind == 'SOCIAL')).all()
            this_year = sum((Decimal(str(v)) for d, v in rows if d.year == year), Decimal(0))
            five = sum((Decimal(str(v)) for d, v in rows if year - 4 <= d.year <= year), Decimal(0))
            # 还在申报、审批中的积分按当前规则试算（推荐口径草稿也能算出数，标“试算”）
            trial = Decimal(0); pending = 0
            for claim in db.scalars(select(SocialClaim).where(SocialClaim.teacher_id == a.id, SocialClaim.state != 'ARCHIVED')) if allowed['records'] else []:
                if st.duplicate_claim(db,claim.project_id,claim.teacher_id,claim.id):continue
                frozen = (claim.snapshot or {}).get('trial') or st.point_trial(db, claim)
                if frozen.get('total') is not None: trial += Decimal(str(frozen['total'])); pending += 1
            points = {'year': lc.q2(this_year), 'five_years': lc.q2(five), 'five_year_target': '340', 'title_points': lc.q2(this_year / 100),
                      'trial': lc.q2(trial) if pending else None, 'trial_claims': pending}
        videos = db.scalars(select(SocialResource).where(SocialResource.kind == 'course_resource', st.course_resource_scope(db,a))).all() if allowed['records'] else []
        if a.role.kind == 'teacher': videos = [v for v in videos if v.data.get('teacher_id') == a.id]
        minutes = sum((Decimal(str(v.data.get('duration_minutes') or 0)) for v in videos if v.data.get('resource_type') == 'video'), Decimal(0))
        dept = a.role.kind == 'dept'  # 教研室负责人不看整院台账合计，人次和收入由前端取本教研室授权范围统计
        return {'year': year, 'sections': allowed, 'scope': {'teacher': '本人', 'school': '全校', 'dept': '本教研室'}.get(a.role.kind, '本学院'),
                'income': {'actual': lc.q2(sum((college_income(db, org, year) for org in colleges), Decimal(0))),
                           'source_note': '学院已结项且财务核验的项目到账收入，每个项目只计一次。'} if allowed['records'] and a.role.kind not in ('teacher', 'dept') else None,
                'participants': {**people, 'claimed': lc.q2(people['claimed']), 'final': lc.q2(people['final']),
                                 'target': lc.q2(target) if target else None, 'completion': lc.q2(people['final'] / target * 100) if target else None} if allowed['records'] and not dept else None,
                'online': {'views': lc.q2(views)} if allowed['records'] else None,
                'achievements': {'total': len(achievements), 'levels': levels, 'pending': achievements_pending} if allowed['records'] else None,
                'dual': {'total': len(holders), 'levels': {k: len(v) for k, v in dual.items()}, 'mine': mine_level} if allowed['qualifications'] else None,
                'points': points, 'can_review': a.role.kind == 'school' and 'records.write' in a.permissions,
                'resources': {'items': len(videos), 'videos': sum(st.resource_video_count(v.data) for v in videos), 'minutes': lc.q2(minutes)} if allowed['records'] else None,
                'note': '点任意一格可看明细。人次和积分以学校审核认定为准，这里的数字供你核对。' if a.role.kind == 'teacher' else ('课程人次和培训收入按本教研室教师的授课业务统计；学院台账人次由学院和学校核定，不在此重复展示。' if dept else '人次取各学院最新报送台账：已核定的行用核定值，未核定的行用推荐值。')}
    return read_operation(request, 'portal.read', load)


@router.get('/resource-stats')
def resource_stats(request: Request):
    """培训课程视频分钟资源：按学院统计课程资源数、视频数和总分钟数。"""
    def load(db, a, s):
        if a.role.kind == 'teacher': raise HTTPException(403, '教师请在“个人培训”查看本人课程资源')
        colleges = college_scope(db, a)
        out = []
        for org in colleges:
            items = db.scalars(select(SocialResource).where(SocialResource.kind == 'course_resource', SocialResource.org_id == org.id, st.course_resource_scope(db,a))).all()
            videos = [x for x in items if x.data.get('resource_type') == 'video']
            out.append({'org_id': org.id, 'org_name': a.org.name if a.role.kind=='dept' else org.name, 'resources': len(items), 'videos': sum(st.resource_video_count(x.data) for x in videos),
                        'courses': len({x.data.get('course_code') for x in items}),
                        'minutes': lc.q2(sum((Decimal(str(x.data.get('duration_minutes') or 0)) for x in videos), Decimal(0)))})
        return {'items': out, 'note': '分钟数为登记的视频资源总时长，用于统计课程资源建设情况。'}
    return read_operation(request, 'records.read', load)


ROLE_LABELS = {'lecturer': '主讲', 'instructor': '实训指导', 'manager': '管理辅助'}
CLAIM_STEPS = [('DRAFT', '本人填报'), ('SUBMITTED', '院长初审'), ('DEAN', '继教复审'), ('COORDINATOR', '分管副校长审批'), ('APPROVED', '教学秘书归档'), ('ARCHIVED', '已归档')]


def claim_deadline(db, closed_on):
    """结项后 15 个工作日内申报（积分办法第十八条）。有已启用口径的校历就按校历，否则按周一至周五估算。"""
    for policy in db.scalars(select(SocialPolicy).where(SocialPolicy.state == 'ACTIVE').order_by(SocialPolicy.created_at.desc())):
        due, errors = st.calendar_block(policy.data, closed_on, 15)
        if due: return due, False
    due, left = closed_on, 15
    while left:
        due += timedelta(days=1)
        if due.weekday() < 5: left -= 1
    return due, True


@router.get('/mine')
def mine(request: Request, year: int = Query(..., ge=2020, le=2100)):
    """个人培训：只列本人的项目、积分申报、台账人次、资质、课程资源和提醒（老师手写菜单“系统打开显示个人”）。"""
    def load(db, a, s):
        allowed = sections(a)
        today = st.today()
        units = db.scalars(select(SocialUnit)).all() if allowed['records'] else []
        my_roles = {}
        for u in units:
            for t in u.data.get('teachers', []):
                if t.get('teacher_id') == a.id: my_roles.setdefault(u.project_id, {}).setdefault(ROLE_LABELS.get(t.get('role'), '授课'), 0); my_roles[u.project_id][ROLE_LABELS.get(t.get('role'), '授课')] += 1
        participant_scope = SocialProject.org_id == a.org.parent_id if a.role.kind == 'teacher' else SocialProject.org_id.in_(a.org_ids)
        project_query = select(SocialProject).where(or_(SocialProject.owner_id == a.id, and_(SocialProject.id.in_(list(my_roles) or ['']), participant_scope)))
        if a.role.kind != 'teacher': project_query = project_query.where(SocialProject.org_id.in_(a.org_ids))
        projects = db.scalars(project_query.order_by(SocialProject.created_at.desc())).all() if allowed['records'] else []
        claims = db.scalars(select(SocialClaim).where(SocialClaim.teacher_id == a.id).order_by(SocialClaim.created_at.desc())).all() if allowed['records'] and allowed['points'] else []
        latest_claim = {}
        for c in claims: latest_claim.setdefault(c.project_id, c)
        names = {p.id: p.data.get('name') for p in projects}
        reminders, project_rows = [], []
        for p in projects:
            roles = (['项目负责人'] if p.owner_id == a.id else []) + [f'{k}（{v} 次）' for k, v in my_roles.get(p.id, {}).items()]
            closed = p.closeout.get('closed_on') if p.closeout else None
            claim = latest_claim.get(p.id)
            row = {'id': p.id, 'code': p.data.get('code'), 'name': p.data.get('name'), 'cohort': p.cohort, 'state': p.state, 'state_label': st.state_label(p),
                   'start_date': p.data.get('start_date'), 'end_date': p.data.get('end_date'), 'closed_on': closed, 'roles': roles,
                   'claim': {'id': claim.id, 'state': claim.state, 'state_label': st.STATES.get(claim.state, claim.state)} if claim else None, 'deadline': None}
            if allowed['points'] and p.state == 'CLOSED' and not claim and my_roles.get(p.id) and closed:
                due, estimated = claim_deadline(db, date.fromisoformat(closed))
                row['deadline'] = {'date': due.isoformat(), 'days_left': (due - today).days, 'estimated': estimated}
                if estimated:
                    text = f'“{p.data.get("name")}”已结项，申报截止日期暂估为 {due.isoformat()}；学校校历尚未确认，请联系学院核实，不据此认定逾期。'
                elif due < today:
                    text = f'“{p.data.get("name")}”已超过学校校历确定的申报截止日期 {due.isoformat()}，请查看项目并联系学院核实。'
                else:
                    text = f'“{p.data.get("name")}”已结项，请在 {due.isoformat()} 前申报积分'
                check_project = estimated or due < today
                reminders.append({'level': 'warn' if (due - today).days <= 5 else 'info', 'text': text,
                                  'action': 'social-detail' if check_project else 'social-claim-new',
                                  'id': 'social_project|' + p.id if check_project else '',
                                  'action_label': '查看项目' if check_project else '去申报'})
            if p.state == 'RETURNED' and p.owner_id == a.id:
                reminders.append({'level': 'warn', 'text': f'项目“{p.data.get("name")}”被退回，请补正后重新提交', 'action': 'social-detail', 'id': 'social_project|' + p.id})
            project_rows.append(row)
        claim_rows = []
        for c in claims:
            trial = (c.snapshot or {}).get('trial') or st.point_trial(db, c)
            order = [k for k, _ in CLAIM_STEPS]
            at = order.index(c.state) if c.state in order else 0
            claim_rows.append({'id': c.id, 'project': names.get(c.project_id) or (db.get(SocialProject, c.project_id).data.get('name')), 'state': c.state, 'state_label': st.STATES.get(c.state, c.state),
                               'total': trial.get('total'), 'blockers': len(trial.get('blockers') or []), 'deadline': trial.get('deadline'),
                               'steps': [{'label': label, 'done': i < at or c.state == 'ARCHIVED', 'current': i == at and c.state != 'ARCHIVED'} for i, (_, label) in enumerate(CLAIM_STEPS)]})
            waiting = c.state == 'DRAFT' and any('尚未正式启用' in x for x in trial.get('blockers') or [])
            if c.state in ('DRAFT', 'RETURNED'):
                text = '被退回，请补正' if c.state == 'RETURNED' else '已填好，等学校正式启用积分口径后再提交' if waiting else '还是草稿，请提交'
                reminders.append({'level': 'info' if waiting else 'warn', 'text': f'积分申报“{claim_rows[-1]["project"]}”' + text, 'action': 'social-detail', 'id': 'social_claim|' + c.id})
        allocations = []
        colleges = college_scope(db, a)
        for r in latest_by_college(ledgers(db, [o.id for o in colleges])).values() if allowed['records'] else []:
            org = next((o.name for o in colleges if o.id == r.org_id), '')
            for row in r.data['rows']:
                mine_allocations = [x for x in row.get('allocations', []) if x.get('teacher_id') == a.id]
                hit = sum((Decimal(x['value']) for x in mine_allocations), Decimal(0))
                if mine_allocations:
                    status = '待个人核定，原表分配不能作为个人认定依据' if row.get('approved') is None else f'项目核定 {lc.q2(row["approved"])} 人次，原表分配不能作为个人认定依据；个人分配待复核'
                    allocations.append({'year': r.data['year'], 'org_name': org, 'row_no': row['row_no'], 'name': row.get('name'),
                                        'value': lc.q2(hit), 'original_value': lc.q2(hit), 'approved_value': None,
                                        'reviewed': False, 'review_status': status, 'project_approved': row.get('approved'), 'project_code': row.get('project_code')})
        allocations.sort(key=lambda x: (-x['year'], x['row_no']))
        quals = []
        qualification_setting = db.get(Setting, 'qualification')
        expiry_days = qualification_setting.value['expiry_days'] if qualification_setting else 0
        for q in db.scalars(select(Qualification).where(Qualification.teacher_id == a.id).order_by(Qualification.obtained.desc())) if allowed['qualifications'] else []:
            days = (q.expires - today).days if q.expires else None
            quals.append({'id': q.id, 'category': q.category, 'name': q.name, 'state': q.state, 'expires': q.expires.isoformat() if q.expires else None, 'days_left': days})
            if q.state == 'APPROVED' and days is not None and days <= expiry_days:
                reminders.append({'level': 'warn', 'text': f'资质“{q.name}”' + ('已过期' if days < 0 else f'{days} 天后到期') + '，请及时更新', 'action': 'qualification', 'id': q.id})
        videos = [x for x in db.scalars(select(SocialResource).where(SocialResource.kind == 'course_resource', SocialResource.org_id.in_([o.id for o in colleges]))) if x.data.get('teacher_id') == a.id] if allowed['records'] else []
        courses = {'courses': len({x.data.get('course_code') for x in videos}), 'resources': len(videos),
                   'videos': sum(st.resource_video_count(x.data) for x in videos),
                   'minutes': lc.q2(sum((Decimal(str(x.data.get('duration_minutes') or 0)) for x in videos if x.data.get('resource_type') == 'video'), Decimal(0)))}
        owned = {p.id for p in projects if p.owner_id == a.id}
        dated, _ = annual_achievements(db, [o.id for o in colleges], year) if allowed['records'] else ([], 0)
        achievements = [{'code': x.code, 'name': x.name, 'level': x.data.get('level'), 'state': x.state, 'auto': bool(x.data.get('auto'))}
                        for x in dated if x.data.get('project_id') in owned]
        # 统一待办里属于本人、上面还没列出的事（教研室发来的积分核对、资质退回、本人考核确认），一并放进“需要我处理”。
        from .business import _todo_items
        listed = {r['id'] for r in reminders if r.get('id')}
        for x in _todo_items(db, a):
            code = x['type'] + '|' + str(x['id'])
            if x.get('teacher_id') != a.id or x['state'] == 'EXPIRING' or x['type'] in ('social_claim', 'social_project', 'dispute') or code in listed or ('social_resource|' + str(x['id'])) in listed: continue
            text = {'assessment': '本人年度考核结果已生成，请核对后确认'}.get(x['type'], x['title'])
            reminders.insert(0, {'level': 'warn', 'text': text, 'action': 'todo', 'id': code})
        # 申报按钮旁直接说清能不能申报，免得老师点开表单才发现。
        claimable = db.scalar(select(func.count()).select_from(st.visible_projects(db, a).where(SocialProject.id.in_(st.participated_project_ids(db, a.id) or {''}), SocialProject.state == 'CLOSED').order_by(None).subquery())) if allowed['records'] and allowed['points'] else 0
        has_policy = bool(db.scalar(select(func.count()).select_from(SocialPolicy)))
        claim_ready = {'projects': claimable, 'policy': has_policy,
                       'reason': '' if claimable and has_policy else '学校还没有登记积分认定口径，暂时不能申报，请联系学校社会培训管理员。' if not has_policy else '你还没有可申报的项目。项目须由学院办完结项，且参训明细里登记了你的工号。项目还在办理中的等结项后再来；如有遗漏，请联系学院补录参训明细。'}
        return {'year': year, 'sections': allowed, 'name': a.name, 'org_name': a.org.name, 'projects': project_rows, 'claims': claim_rows, 'allocations': allocations, 'claim_ready': claim_ready,
                'qualifications': quals, 'courses': courses if allowed['records'] else None, 'achievements': achievements, 'reminders': reminders,
                'note': '这里只显示本人的信息。积分为试算，学校书面确认口径前不是正式分数；申报期限未启用校历时按周一至周五估算。'}
    return read_operation(request, 'portal.read', load)


class ConflictIn(BaseModel):
    target_kind: Literal['teacher', 'org']
    target_id: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=2, max_length=500)


class WithdrawIn(BaseModel):
    reason: str = Field(min_length=2, max_length=500)


def conflict_options(db, a):
    colleges = college_scope(db, a)
    org_ids = [o.id for o in colleges] + [o.id for o in db.scalars(select(Org).where(Org.parent_id.in_([o.id for o in colleges])))]
    teachers = db.scalars(select(User).join(Role, Role.id == User.role_id).where(User.active.is_(True), Role.kind == 'teacher', User.org_id.in_(org_ids)).order_by(User.name).limit(2000)).all()
    return {'teachers': [{'id': u.id, 'name': u.name} for u in teachers], 'orgs': [{'id': o.id, 'name': o.name} for o in colleges]}


@router.get('/conflicts')
def conflict_list(request: Request):
    """利益冲突申报与回避（管理办法第二十八条）：本人看本人的申报，学校看全部，便于纪检抽查。"""
    def load(db, a, s):
        setting = db.get(Setting, st.CONFLICTS_KEY); rows = setting.value if setting else []
        mine = [x for x in rows if a.role.kind == 'school' or x['user_id'] == a.id]
        return {'items': sorted(mine, key=lambda x: x['declared_on'], reverse=True), 'can_declare': 'assessment.review' in a.permissions, 'all': a.role.kind == 'school', **conflict_options(db, a),
                'note': '参与社会培训管理、评审、考核的人员，须主动申报潜在利益冲突。申报后，系统在审批、核验、评分时自动拦下，须由其他人员办理。'}
    return read_operation(request, 'portal.read', load)


@router.post('/conflicts')
def conflict_declare(data: ConflictIn, request: Request):
    def apply(db, a, s):
        options = conflict_options(db, a)
        target = next((x for x in options['teachers' if data.target_kind == 'teacher' else 'orgs'] if x['id'] == data.target_id), None)
        if not target: raise HTTPException(422, '申报对象不在本人业务范围内')
        setting = db.get(Setting, st.CONFLICTS_KEY)
        if not setting: setting = Setting(key=st.CONFLICTS_KEY, value=[], version=1); db.add(setting); db.flush()
        if any(x['user_id'] == a.id and x['target_id'] == data.target_id and x.get('active', True) for x in setting.value): raise HTTPException(409, '已经申报过这个对象')
        item = {'id': str(uuid4()), 'user_id': a.id, 'user_name': a.name, 'target_kind': data.target_kind, 'target_id': data.target_id, 'target_name': target['name'],
                'reason': data.reason, 'declared_on': st.today().isoformat(), 'active': True}
        before = list(setting.value); setting.value = before + [item]; setting.version += 1; db.flush()
        workflow(db, a, 'setting', st.CONFLICTS_KEY, '申报利益冲突并回避', {}, item, data.reason)
        return item
    return command(request, data.model_dump(), 'assessment.review', apply)


@router.post('/conflicts/{ident}/withdraw')
def conflict_withdraw(ident: str, data: WithdrawIn, request: Request):
    def apply(db, a, s):
        setting = db.get(Setting, st.CONFLICTS_KEY)
        item = next((x for x in (setting.value if setting else []) if x['id'] == ident and x['user_id'] == a.id), None)
        if not item: raise HTTPException(404, '没有这条本人申报')
        if not item.get('active', True): raise HTTPException(409, '这条申报已撤回')
        after = {**item, 'active': False, 'withdrawn_on': st.today().isoformat(), 'withdraw_reason': data.reason}
        setting.value = [after if x['id'] == ident else x for x in setting.value]; setting.version += 1; db.flush()
        workflow(db, a, 'setting', st.CONFLICTS_KEY, '撤回利益冲突申报', item, after, data.reason)
        return after
    return command(request, data.model_dump(), 'assessment.review', apply)


@router.get('/departments')
def departments(request: Request, year: int = Query(..., ge=2020, le=2100)):
    """教研室考核要素（积分办法第十七条）：教研室全体老师的平均社会培训积分，占教研室年度考核 10%。"""
    def load(db, a, s):
        colleges = college_scope(db, a); names = {o.id: o.name for o in colleges}
        depts = db.scalars(select(Org).where(Org.parent_id.in_(list(names)), Org.active.is_(True)).order_by(Org.name)).all()
        if a.role.kind in ('teacher', 'dept'): depts = [d for d in depts if d.id == a.org.id]
        points = dict(db.execute(select(PointEntry.teacher_id, func.sum(PointEntry.amount)).join(Period, Period.id == PointEntry.period_id).where(PointEntry.kind == 'SOCIAL', Period.start_date >= date(year, 1, 1), Period.start_date <= date(year, 12, 31)).group_by(PointEntry.teacher_id)).all())
        items = []
        for d in depts:
            teachers = db.scalars(select(User).join(Role, Role.id == User.role_id).where(User.org_id == d.id, User.active.is_(True), Role.kind == 'teacher')).all()
            total = sum((Decimal(str(points.get(u.id) or 0)) for u in teachers), Decimal(0))
            items.append({'org_id': d.id, 'name': d.name, 'college': names.get(d.parent_id, ''), 'teachers': len(teachers), 'with_points': sum(1 for u in teachers if points.get(u.id)),
                          'total': lc.q2(total), 'average': lc.q2(total / len(teachers)) if teachers else None})
        ranked = sorted([x for x in items if x['average'] is not None], key=lambda x: -Decimal(x['average']))
        for i, x in enumerate(ranked, 1): x['rank'] = i
        return {'year': year, 'items': ranked + [x for x in items if x['average'] is None],
                'note': '平均积分 = 教研室全体在岗老师已归档社会培训积分之和 ÷ 老师人数（没有积分的老师也计入人数）。积分办法规定占教研室年度考核 10%，具体怎么折成分数学校还没定。'}
    return read_operation(request, 'records.read', load)
