"""PDF 8.5 / 10.5-10.7: frozen teacher assessment projections.

Authorization always uses current membership; snapshots are evidence, not grants.
Old valid archives lacking identity snapshots are explicitly labelled, never
silently supplemented with today's teacher, organization, rule or period values.
"""
from __future__ import annotations
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from fastapi import HTTPException
from .models import User, Org, Rule, Period, Attachment, utcnow
from .core import serial, digest


def teacher_identity(db, teacher_id):
    user = db.get(User, teacher_id)
    if not user:
        raise HTTPException(409, '考核人员身份缺失')
    return {k: getattr(user, k) for k in ('id', 'name', 'staff_no', 'org_id')}


def organization_chain(db, org_id):
    result, seen = [], set()
    while org_id:
        if org_id in seen or len(seen) >= 20:
            raise HTTPException(409, '考核人员组织链异常')
        seen.add(org_id)
        org = db.get(Org, org_id)
        if org is None:
            raise HTTPException(409, '考核人员组织链不完整')
        result.append({k: getattr(org, k) for k in ('id', 'code', 'name', 'kind', 'parent_id')})
        org_id = org.parent_id
    return result


def verified_archive(obj):
    """Return a detached verified snapshot. No writes, repair or live fallbacks."""
    payload = obj.archive
    try:
        frozen = payload['assessment']
        valid = (
            obj.state == 'ARCHIVED' and bool(obj.archive_sha256)
            and digest(payload) == obj.archive_sha256
            and frozen['state'] == 'ARCHIVED'
            and all(frozen[k] == getattr(obj, k) for k in ('id', 'teacher_id', 'period_id', 'rule_id'))
            and payload['rule']['id'] == frozen['rule_id']
            and payload['period']['id'] == frozen['period_id']
            and isinstance(frozen['detail'], list)
            and Decimal(str(frozen['score'])).is_finite()
            and Decimal(str(frozen['score'])) == Decimal(str(obj.score))
            and frozen['version'] == obj.version and frozen['returned'] == obj.returned
            and digest(frozen['detail']) == digest(obj.detail)
            and digest(frozen['source_snapshot']) == digest(obj.source_snapshot)
            and digest(payload['source_snapshot']) == digest(obj.source_snapshot)
        )
        if not valid:
            raise ValueError('archive mismatch')
        if payload.get('schema_version') == 2:
            identity=payload['teacher']
            if (identity.get('id') != obj.teacher_id or not all(isinstance(identity.get(k),str) and identity[k] for k in ('name','staff_no','org_id'))
                or not isinstance(payload.get('organization_chain'),list) or not payload['organization_chain']
                or payload['organization_chain'][0].get('id') != identity['org_id']
                or not isinstance(payload.get('events'),list)):
                raise ValueError('archive identity incomplete')
    except (KeyError, TypeError, ValueError, InvalidOperation, AttributeError):
        raise HTTPException(409, '考核归档证据校验失败，禁止按可信历史结果查看、打印或导出') from None
    return deepcopy(payload)


def attachment_index(source_snapshot, teacher_id):
    """Index only exact, historically referenced qualification attachments."""
    out = {}
    for q in source_snapshot.get('qualifications', []):
        if not isinstance(q, dict):
            raise HTTPException(409, '归档资质依据结构异常')
        for item in q.get('attachments', []):
            if (not isinstance(item, dict) or not item.get('id')
                or item.get('teacher_id') != teacher_id
                or item.get('object_type') != 'qualification'
                or item.get('object_id') != q.get('id')):
                raise HTTPException(409, '归档附件与教师、资质的关联不一致')
            if item['id'] in out and out[item['id']] != item:
                raise HTTPException(409, '归档附件证据重复且内容冲突')
            out[item['id']] = deepcopy(item)
    return out


def make_archive(db, obj, actor, events, reason, basis, storage_dir):
    from .routes.files import verify_file
    identity = teacher_identity(db, obj.teacher_id)
    # Verify originally calculated bytes, not a later qualification revision.
    for item in attachment_index(obj.source_snapshot, obj.teacher_id).values():
        current = db.get(Attachment, item['id'])
        if not current or any(getattr(current, k) != item.get(k) for k in ('teacher_id','object_type','object_id','sha256','size')):
            raise HTTPException(409, '归档所用附件元数据已变化或缺失')
        verify_file(storage_dir, current)
    at = utcnow().isoformat()
    closed_event = {'actor_id': actor.id, 'actor_name': actor.name, 'org_id': actor.org.id,
        'action': '考核归档', 'created_at': at, 'reason': reason, 'basis': basis}
    frozen = {k:v for k,v in serial(obj).items() if k not in {'archive','archive_sha256'}}
    frozen.update(state='ARCHIVED', version=obj.version + 1)
    return {'schema_version': 2, 'assessment': frozen,
        'rule': serial(db.get(Rule, obj.rule_id)), 'period': serial(db.get(Period, obj.period_id)),
        'teacher': identity, 'organization_chain': organization_chain(db, identity['org_id']),
        'source_snapshot': deepcopy(obj.source_snapshot),
        'events': [*serial(events), closed_event], 'archived_by': actor.id,
        'archived_by_name': actor.name, 'archived_at': at, 'reason': reason, 'basis': basis}


def assessment_projection(db, obj, live_events=None):
    if obj.state != 'ARCHIVED':
        identity = teacher_identity(db, obj.teacher_id)
        return {'assessment': serial(obj), 'rule': serial(db.get(Rule, obj.rule_id)),
            'period': serial(db.get(Period, obj.period_id)), 'teacher': identity,
            'organization_chain': organization_chain(db, identity['org_id']),
            'events': serial(live_events or []), 'immutable': False,
            'document_status': 'DRAFT_NOT_FINAL', 'identity_frozen': False}
    frozen = verified_archive(obj)
    identity = frozen.get('teacher')
    identity_frozen = isinstance(identity, dict) and identity.get('id') == obj.teacher_id
    if not identity_frozen:
        identity = {'id':obj.teacher_id, 'name':'归档时未冻结姓名', 'staff_no':'未冻结', 'org_id':None}
    return {'assessment': {**frozen['assessment'], 'archive': frozen, 'archive_sha256': obj.archive_sha256},
        'rule': frozen['rule'], 'period': frozen['period'], 'teacher': identity,
        'organization_chain': frozen.get('organization_chain', []),
        'events': frozen.get('events', []), 'immutable': True, 'identity_frozen': identity_frozen,
        'document_status': 'ARCHIVED',
        'identity_note': '' if identity_frozen else '旧归档未保存人员组织快照，不以当前信息补写历史。'}
