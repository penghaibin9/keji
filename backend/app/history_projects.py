"""已报送原表的历史项目来源；未知事实保持空值，不建立普通业务项目。"""
from datetime import date
import re
from typing import Literal
from fastapi import HTTPException
from pydantic import Field, model_validator
from sqlalchemy import select
from .schemas import Input, Ident, VersionedReason
from .models import Attachment, Org, User
from .social_models import SocialResource
from .school_cockpit import load_reports


class OwnerFact(Input):
    name: str | None = Field(default=None, max_length=160)
    role: str | None = Field(default=None, max_length=160)
    evidence: str | None = Field(default=None, max_length=2000)
    account_id: Ident | None = None
    @model_validator(mode='after')
    def responsible_role(self):
        if (self.name or self.account_id) and (self.role != '项目负责人' or not self.evidence):
            raise ValueError('负责人姓名或账号须有明确项目负责人角色及材料依据；联系人、完成人和分配人员请保留在待核说明')
        return self


class DateFact(Input):
    kind: Literal['actual', 'planned', 'news', 'source']
    text: str = Field(min_length=1, max_length=1000)
    evidence: str = Field(min_length=1, max_length=2000)
    start_date: date | None = None
    end_date: date | None = None
    @model_validator(mode='after')
    def ordered(self):
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError('日期事实的结束日期不能早于开始日期')
        return self


class DatePrefill(DateFact):
    kind: Literal['actual', 'news', 'source'] = 'source'
    start_date: date
    end_date: date

    @model_validator(mode='after')
    def evidence_required(self):
        if not self.text.strip() or not self.evidence.strip():
            raise ValueError('历史日期预填须保留判断说明和原件依据')
        return self


class HistoryFacts(Input):
    owner: OwnerFact = Field(default_factory=OwnerFact)
    date_facts: list[DateFact] = Field(default_factory=list, max_length=50)
    date_prefill: DatePrefill | None = None
    confirmed_start: date | None = None
    confirmed_end: date | None = None
    conflicts: list[str] = Field(default_factory=list, max_length=30)
    pending_notes: list[str] = Field(default_factory=list, max_length=50)
    attachment_ids: list[Ident] = Field(default_factory=list, max_length=50)
    @model_validator(mode='after')
    def confirmed(self):
        if self.conflicts and (self.confirmed_start or self.confirmed_end):
            raise ValueError('冲突尚未解决，确认培训起止必须保持空白')
        if self.confirmed_start and self.confirmed_end and self.confirmed_start > self.confirmed_end:
            raise ValueError('确认结束日期不能早于确认开始日期')
        for field, endpoint in (('confirmed_start', 'start_date'), ('confirmed_end', 'end_date')):
            value = getattr(self, field)
            if value and not any(f.kind == 'actual' and getattr(f, endpoint) == value for f in self.date_facts):
                raise ValueError('确认起止必须对应有依据的实际培训日期，计划或报道时间不能代替')
        if self.confirmed_start and self.confirmed_end and not any(f.kind == 'actual' and f.start_date == self.confirmed_start and f.end_date == self.confirmed_end for f in self.date_facts):
            raise ValueError('确认完整期间须由同一条实际培训事实支持，不能拼接离散日期')
        if len(self.attachment_ids) != len(set(self.attachment_ids)):
            raise ValueError('项目材料引用不能重复')
        if any(not v.strip() or len(v) > 2000 for v in self.conflicts + self.pending_notes):
            raise ValueError('冲突和待核说明须为有效文字，每项不超过2000字')
        return self


class HistoryFactsIn(VersionedReason):
    history: HistoryFacts


def require_history(actor):
    actor.require('records.read')
    if actor.role.kind not in ('school', 'college'):
        raise HTTPException(403, '历史项目原始资料仅由学校和所属学院核对')


def source_groups(ledger, catalog=None):
    rows = ledger.data['rows']
    if any('source_sequence' not in row for row in rows):
        report = next((r for r in (catalog or {}).get('reports', []) if r['id'] == ledger.data['file']['sha256']), None)
        original = {r['source_row']: r for r in report['rows']} if report else {}
        if len(original) != len(rows) or any(row['row_no'] not in original or row['name'] != original[row['row_no']]['name'] for row in rows):
            raise HTTPException(503, '旧台账与采用原件的行号或名称不一致，请先核对')
        # 仅补全读取视图；不重算或写回已有核定、关联与历史事实。
        rows = [{**row, 'source_sequence': original[row['row_no']]['source_sequence']} for row in rows]
    groups, current = [], None
    for row in rows:
        if re.fullmatch(r'\d+', str(row.get('source_sequence') or '')):
            current = {'head': row, 'rows': []}
            groups.append(current)
        elif current is None:
            raise HTTPException(503, '历史原表续行缺少所属编号项目，请先核对')
        current['rows'].append(row)
    return groups


def adopted_ledgers(db, actor, settings):
    require_history(actor)
    catalog = load_reports(settings.school_reports_dir)
    if catalog is None:
        raise HTTPException(503, '尚未配置学校历史原始资料')
    colleges = {o.id: o.name for o in db.scalars(select(Org).where(Org.id.in_(actor.org_ids), Org.kind == 'college', Org.active.is_(True)))}
    adopted = {(r['college'], r['period']['year'], r['id']) for r in catalog['reports']}
    chosen = {}
    for ledger in db.scalars(select(SocialResource).where(SocialResource.kind == 'ledger', SocialResource.org_id.in_(colleges)).order_by(SocialResource.created_at, SocialResource.id)):
        if (colleges[ledger.org_id], ledger.data['year'], ledger.data['file']['sha256']) in adopted:
            chosen[(ledger.org_id, ledger.data['year'])] = ledger
    return catalog, colleges, list(chosen.values())


def history_row(db, actor, settings, ledger_id, row_no):
    catalog, colleges, ledgers = adopted_ledgers(db, actor, settings)
    ledger = next((x for x in ledgers if x.id == ledger_id), None)
    group = next((x for x in source_groups(ledger, catalog) if x['head']['row_no'] == row_no), None) if ledger else None
    if not group:
        raise HTTPException(404, '历史编号项目不存在或超出采用原件与学院范围')
    return ledger, group, colleges[ledger.org_id]


def public_history(db, actor, ledger, group, college, *, detail=False):
    head = group['head']
    history = HistoryFacts.model_validate(head.get('history') or {}).model_dump(mode='json')
    missing = []
    owner = history['owner']
    if not owner['name']: missing.append('负责人姓名待核实')
    if not owner['role'] or not owner['evidence']: missing.append('负责人角色或依据待核实')
    if not owner['account_id']: missing.append('负责人账号待关联')
    if not history['confirmed_start'] or not history['confirmed_end']: missing.append('实际培训起止待核实')
    if history['date_prefill']: missing.append('历史预填日期待学校复核')
    if not history['attachment_ids']: missing.append('项目专属材料待关联')
    missing += history['pending_notes']
    result = {'ledger_id': ledger.id, 'row_no': head['row_no'], 'year': ledger.data['year'],
              'org_id': ledger.org_id, 'college': college, 'name': head['name'], 'sequence': head['source_sequence'],
              'source_id': ledger.data['file']['sha256'], 'source_file': ledger.data['file']['name'],
              'source_rows': [r['row_no'] for r in group['rows']], 'ledger_version': ledger.version,
              'project_id': head.get('project_id'), 'project_code': head.get('project_code'),
              'history': history, 'missing': missing,
              'status': '有冲突待核对' if history['conflicts'] else '资料待完善' if missing else '已关联确认资料',
              'materials_count': len(history['attachment_ids'])}
    if detail:
        result['rows'] = [{k: row.get(k) for k in ('row_no', 'source_sequence', 'name', 'claimed', 'claimed_raw', 'people_raw', 'hours', 'allocation', 'materials', 'remark')} for row in group['rows']]
        result['attachments'] = []
        if 'file.read' in actor.permissions and history['attachment_ids']:
            result['attachments'] = [{'id': a.id, 'name': a.name, 'sha256': a.sha256, 'size': a.size, 'mime': a.mime}
                                     for a in db.scalars(select(Attachment).where(Attachment.id.in_(history['attachment_ids']), Attachment.object_type == 'social_resource', Attachment.object_id == ledger.id))
                                     if a.id != ledger.data['file'].get('id') and a.sha256 != ledger.data['file']['sha256']]
        result['can_read_files'] = 'file.read' in actor.permissions
    return result


def validate_facts(db, actor, ledger, history):
    owner = history.owner
    if owner.account_id:
        person = db.get(User, owner.account_id)
        orgs = {ledger.org_id} | set(db.scalars(select(Org.id).where(Org.parent_id == ledger.org_id, Org.active.is_(True))))
        if not owner.name or not owner.role or not owner.evidence or not person or not person.active or person.authorization_pending or person.org_id not in orgs or person.name != owner.name:
            raise HTTPException(422, '负责人账号须与原材料姓名及学院有效人员对应，不能使用录入人替代')
    if history.attachment_ids:
        actor.require('file.read')
        files = db.scalars(select(Attachment).where(Attachment.id.in_(history.attachment_ids))).all()
        if len(files) != len(history.attachment_ids) or any(a.object_type != 'social_resource' or a.object_id != ledger.id for a in files):
            raise HTTPException(422, '项目材料必须先上传到当前学院台账，不能引用其他业务附件')
        if any(a.id == ledger.data['file'].get('id') or a.sha256 == ledger.data['file']['sha256'] for a in files):
            raise HTTPException(422, '学院整表不能作为单个项目的专属材料')
