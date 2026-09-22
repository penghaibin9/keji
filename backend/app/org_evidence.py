"""Organization evidence integrity. Frozen facts never grant access permissions.

Checks detect missing/mismatched evidence, not an administrator rewriting all
records and digests. Legacy archives are never silently re-signed or backfilled.
"""
from __future__ import annotations
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from fastapi import HTTPException
from .core import digest, serial
from .models import Org, Period


def _number(value):
    result=Decimal(str(value))
    if not result.is_finite():
        raise ValueError('nonfinite evidence')
    return result


def validate_org_payload(payload, obj, *, creating=False):
    """Bind aggregate, rule, every metric and workflow to this exact result."""
    try:
        frozen=payload['assessment'];rule=payload['rule'];scope=frozen['source_snapshot']
        keys=('id','target_id','target_kind','period_id','rule_id','generated_by','reviewed_by','school_audited_by')
        if (not isinstance(payload,dict) or frozen['state']!='ARCHIVED'
            or any(frozen[k]!=getattr(obj,k) for k in keys)
            or type(frozen['version']) is not int or frozen['version']!=obj.version+(1 if creating else 0)
            or _number(frozen['score'])!=_number(obj.score)
            or digest(frozen['detail'])!=digest(obj.detail) or digest(scope)!=digest(obj.source_snapshot)
            or rule['id']!=obj.rule_id or rule['period_id']!=obj.period_id or rule['target_kind']!=obj.target_kind
            or payload['period']['id']!=obj.period_id or scope['period']['id']!=obj.period_id
            or payload['target']['id']!=obj.target_id or payload['target']['kind']!=obj.target_kind
            or scope['target']['id']!=obj.target_id or scope['target']['kind']!=obj.target_kind):
            raise ValueError('organization archive identity mismatch')
        detail=frozen['detail'];evidence=payload['evidence'];components=rule['config']['components']
        if (not isinstance(detail,list) or not isinstance(evidence,list) or not detail
            or len(detail)!=len(evidence) or len(detail)!=len(components)):
            raise ValueError('missing metric evidence')
        by_key={e['metric_code']:e for e in evidence};rules={c['key']:c for c in components}
        if len(by_key)!=len(evidence) or len(rules)!=len(components) or {d['key'] for d in detail}!=set(by_key) or set(by_key)!=set(rules):
            raise ValueError('duplicate or mismatched metrics')
        if digest({'target_kind':rule['target_kind'],'period_id':rule['period_id'],'config':rule['config']})!=rule['fingerprint']:
            raise ValueError('rule mismatch')
        for d in detail:
            e=by_key[d['key']];c=rules[d['key']]
            if (e['assessment_id']!=obj.id or d['rule_id']!=obj.rule_id
                or e['rule_version']!=rule['version_no'] or d['rule_version']!=rule['version_no']
                or e['metric_name']!=d['label'] or d['label']!=c['label']
                or e['data_source']!=d['source'] or d['source']!=c['source'] or e['formula']!=d['formula']
                or _number(e['raw_value'])!=_number(d['raw']) or _number(e['target_value'])!=_number(d['target'])
                or _number(e['weight'])!=_number(d['weight']) or _number(e['calculated_score'])!=_number(d['score'])
                or _number(d['target'])!=_number(c['target']) or _number(d['weight'])!=_number(c['weight'])
                or digest(e['scope_snapshot'])!=digest({k:scope[k] for k in ('target','org_ids','teacher_ids')})):
                raise ValueError('metric evidence mismatch')
        if sum((_number(d['score']) for d in detail),Decimal(0))!=_number(obj.score):
            raise ValueError('metric total mismatch')
        if 'schema_version' in payload:
            if type(payload['schema_version']) is not int or payload['schema_version']!=2:
                raise ValueError('unsupported organization archive version')
            ev=payload['events']
            if (not isinstance(ev,list) or not ev or
                any(e['object_type']!='organization_assessment' or e['object_id']!=obj.id for e in ev)
                or ev[-1]['action']!='组织考核归档' or ev[-1]['actor_id']!=payload['archived_by']
                or ev[-1]['created_at']!=payload['archived_at']):
                raise ValueError('archive workflow mismatch')
        elif 'events' in payload:
            raise ValueError('unversioned workflow snapshot')
    except (KeyError,TypeError,ValueError,InvalidOperation,AttributeError,OverflowError):
        raise HTTPException(409,'组织考核归档证据与对象、规则或指标不一致，禁止作为可信结果查看、打印、导出或排名') from None
    return deepcopy(payload)


def verified_org_archive(obj):
    try:
        valid=obj.state=='ARCHIVED' and isinstance(obj.archive,dict) and bool(obj.archive_sha256) and digest(obj.archive)==obj.archive_sha256
    except (TypeError,ValueError,OverflowError):
        valid=False
    if not valid:
        raise HTTPException(409,'组织考核归档摘要校验失败')
    return validate_org_payload(obj.archive,obj)


def organization_summary(db,obj):
    if obj.state=='ARCHIVED':
        p=verified_org_archive(obj)
        return {**p['assessment'],'archive':p,'archive_sha256':obj.archive_sha256,
            'target_display_name':p['target']['name'],'period_display_name':p['period']['name']}
    target=db.get(Org,obj.target_id);period=db.get(Period,obj.period_id)
    return {**serial(obj),'target_display_name':target.name if target else '组织不存在',
        'period_display_name':period.name if period else '周期不存在'}
