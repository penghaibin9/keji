"""Organization assessment extension for procurement item 10.

The preserved teacher Assessment/Rule models are intentionally untouched.
Organization-specific rules/results are separate so existing teacher history and
calculation semantics stay compatible.
"""
from __future__ import annotations
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy import String, Integer, DateTime, Numeric, JSON, Text, ForeignKey, UniqueConstraint, Index, select, func, distinct
from sqlalchemy.orm import Mapped, mapped_column
from fastapi import HTTPException
from .models import Base, Entity, Org, User, TrainingRecord, Qualification, PointEntry, Assessment, Period, WorkflowEvent, utcnow
from .core import serial, digest, org_scope


def rounded(value):
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class OrganizationAssessmentRule(Entity, Base):
    __tablename__ = "organization_assessment_rules"
    target_kind: Mapped[str] = mapped_column(String(20), index=True)
    name: Mapped[str] = mapped_column(String(100))
    version_no: Mapped[int] = mapped_column(Integer)
    period_id: Mapped[str] = mapped_column(ForeignKey("periods.id"), index=True)
    config: Mapped[dict] = mapped_column(JSON)
    fingerprint: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(20), default="DRAFT", index=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (UniqueConstraint("target_kind", "period_id", "version_no"),)


class OrganizationRuleTrial(Entity, Base):
    __tablename__ = "organization_rule_trials"
    rule_id: Mapped[str] = mapped_column(ForeignKey("organization_assessment_rules.id"), index=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    target_ids: Mapped[list] = mapped_column(JSON)
    result: Mapped[list] = mapped_column(JSON)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))


class OrganizationAssessment(Entity, Base):
    __tablename__ = "organization_assessments"
    target_kind: Mapped[str] = mapped_column(String(20), index=True)
    target_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    period_id: Mapped[str] = mapped_column(ForeignKey("periods.id"), index=True)
    rule_id: Mapped[str] = mapped_column(ForeignKey("organization_assessment_rules.id"))
    score: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    detail: Mapped[list] = mapped_column(JSON)
    source_snapshot: Mapped[dict] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String(24), default="GENERATED", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    generated_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    school_audited_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    archive: Mapped[dict | None] = mapped_column(JSON)
    archive_sha256: Mapped[str | None] = mapped_column(String(64))
    __table_args__ = (
        UniqueConstraint("target_kind", "target_id", "period_id"),
        Index("ix_org_assessment_period_state", "period_id", "state"),
    )


class OrganizationAssessmentMetricEvidence(Entity, Base):
    __tablename__ = "organization_assessment_metric_evidence"
    assessment_id: Mapped[str] = mapped_column(ForeignKey("organization_assessments.id"), index=True)
    metric_code: Mapped[str] = mapped_column(String(64))
    metric_name: Mapped[str] = mapped_column(String(100))
    raw_value: Mapped[str] = mapped_column(String(100))
    data_source: Mapped[str] = mapped_column(String(200))
    scope_snapshot: Mapped[dict] = mapped_column(JSON)
    formula: Mapped[str] = mapped_column(String(500))
    target_value: Mapped[str] = mapped_column(String(100))
    weight: Mapped[Decimal] = mapped_column(Numeric(7, 2))
    rule_version: Mapped[int] = mapped_column(Integer)
    calculated_score: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    measured_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint("assessment_id", "metric_code"),)


ORG_TARGET_KINDS = {"dept", "college", "school"}
ORG_SOURCES = {"hours", "participants", "income", "teachers", "projects", "courses", "qualifications", "points", "assessment_score"}


def validate_org_rule_config(target_kind: str, config: dict) -> dict:
    if target_kind not in ORG_TARGET_KINDS:
        raise HTTPException(422, "组织考核对象无效")
    if not isinstance(config, dict) or set(config) != {"components"} or not isinstance(config.get("components"), list):
        raise HTTPException(422, "组织考核规则配置无效")
    components = config["components"]
    if not 1 <= len(components) <= 30:
        raise HTTPException(422, "组织考核指标数量无效")
    keys = set(); total = Decimal(0)
    normalized=[]
    for item in components:
        if not isinstance(item, dict): raise HTTPException(422, "组织考核指标无效")
        required={"key","label","source","weight","target"}
        if not required <= set(item): raise HTTPException(422, "组织考核指标字段不完整")
        key=str(item["key"]).strip(); label=str(item["label"]).strip(); source=str(item["source"]).strip()
        if not key or len(key)>64 or key in keys: raise HTTPException(422, "组织考核指标编码无效或重复")
        if not label or len(label)>100 or source not in ORG_SOURCES: raise HTTPException(422, "组织考核指标名称或来源无效")
        try:
            weight=Decimal(str(item["weight"])); target=Decimal(str(item["target"]))
        except Exception: raise HTTPException(422, "组织考核权重或目标值无效") from None
        if weight < 0 or weight > 100 or target <= 0: raise HTTPException(422, "组织考核权重或目标值超出范围")
        keys.add(key); total += weight
        entry={"key":key,"label":label,"source":source,"weight":str(weight),"target":str(target)}
        # 10.1 extended methods are opt-in; a component without "method" keeps the exact legacy shape.
        from .scoring_methods import normalize_method
        if item.get("method") in (None,"") and item.get("cap") not in (None,""):raise HTTPException(422, "封顶/保底须先选择评分方式")
        try: entry.update(normalize_method(item,"org"))
        except ValueError as exc: raise HTTPException(422, str(exc)) from None
        normalized.append(entry)
    if total != Decimal("100"):
        raise HTTPException(422, "组织考核权重总和必须为100")
    return {"components": normalized}


def organization_facts(db, target: Org, period: Period):
    if target.kind not in ORG_TARGET_KINDS:
        raise HTTPException(422, "组织考核对象层级无效")
    org_ids = org_scope(db, target, target.kind)
    teacher_ids = tuple(db.scalars(select(User.id).where(User.org_id.in_(org_ids), User.staff_no.is_not(None), User.authorization_pending.is_(False))).all())
    if not teacher_ids:
        raw={k:Decimal(0) for k in ORG_SOURCES}
        raw["teachers"]=Decimal(0)
        return raw, {"as_of":utcnow().isoformat(),"period":{"id":period.id,"start_date":period.start_date.isoformat(),"end_date":period.end_date.isoformat()},"target":{"kind":target.kind,"id":target.id,"code":target.code,"name":target.name},"org_ids":org_ids,"teacher_ids":[],"assessment_references":[],"basis_digests":organization_basis_digests(db,teacher_ids,period,[]),"values":serial(raw)}
    rq=select(TrainingRecord).where(TrainingRecord.teacher_id.in_(teacher_ids),TrainingRecord.state=="VALID",TrainingRecord.event_date>=period.start_date,TrainingRecord.event_date<=period.end_date).subquery()
    vals=db.execute(select(
        func.coalesce(func.sum(rq.c.hours),0),func.coalesce(func.sum(rq.c.participants),0),func.coalesce(func.sum(rq.c.income),0),
        func.count(distinct(rq.c.teacher_id)),func.count(distinct(rq.c.project_code)),func.count(distinct(rq.c.course_code))
    )).one()
    qual_count=db.scalar(select(func.count()).select_from(Qualification).where(Qualification.teacher_id.in_(teacher_ids),Qualification.state=="APPROVED",Qualification.obtained<=period.end_date,(Qualification.expires.is_(None))|(Qualification.expires>=period.end_date))) or 0
    points=db.scalar(select(func.coalesce(func.sum(PointEntry.amount),0)).where(PointEntry.teacher_id.in_(teacher_ids),PointEntry.period_id==period.id)) or 0
    from .assessment_evidence import verified_archive
    archived=db.scalars(select(Assessment).where(Assessment.teacher_id.in_(teacher_ids),Assessment.period_id==period.id,Assessment.state=="ARCHIVED").order_by(Assessment.id)).all()
    references=[]
    for assessment in archived:
        frozen=verified_archive(assessment)['assessment']
        references.append({'id':assessment.id,'teacher_id':assessment.teacher_id,'archive_sha256':assessment.archive_sha256,'score':frozen['score']})
    avg_score=(sum((Decimal(str(v['score'])) for v in references),Decimal(0))/Decimal(len(references))) if references else Decimal(0)
    raw={"hours":Decimal(str(vals[0])),"participants":Decimal(str(vals[1])),"income":Decimal(str(vals[2])),"teachers":Decimal(str(vals[3])),"projects":Decimal(str(vals[4])),"courses":Decimal(str(vals[5])),"qualifications":Decimal(str(qual_count)),"points":Decimal(str(points)),"assessment_score":avg_score}
    snapshot={
        "as_of":utcnow().isoformat(),
        "period":{"id":period.id,"start_date":period.start_date.isoformat(),"end_date":period.end_date.isoformat()},
        "target":{"kind":target.kind,"id":target.id,"code":target.code,"name":target.name},
        "org_ids":org_ids,"teacher_ids":sorted(teacher_ids),"assessment_references":references,
        "sources":{
            "training_records":"training_records: VALID rows within period and target organization descendants",
            "qualifications":"qualifications: APPROVED and valid at period end",
            "points":"point_entries: current period append-only ledger",
            "assessment_score":"assessments: same-period ARCHIVED teacher results average",
        },
        "values":serial(raw),
        "basis_digests":organization_basis_digests(db,teacher_ids,period,references),
    }
    return raw, snapshot


def organization_basis_digests(db,teacher_ids,period,references):
    """Stream source identities/values so same-total replacements cannot pass as unchanged."""
    from hashlib import sha256
    from .calculation_freshness import RECORD_FIELDS
    hashes={source:sha256() for source in RECORD_FIELDS}
    query=select(TrainingRecord).where(TrainingRecord.teacher_id.in_(teacher_ids),TrainingRecord.state=='VALID',TrainingRecord.event_date>=period.start_date,TrainingRecord.event_date<=period.end_date).order_by(TrainingRecord.id)
    for row in db.scalars(query.execution_options(yield_per=500)):
        for source,field in RECORD_FIELDS.items():
            hashes[source].update(digest([row.id,row.teacher_id,row.event_date,row.external_key,row.source,row.batch_id,getattr(row,field)]).encode())
    result={k:v.hexdigest() for k,v in hashes.items()}
    q=select(Qualification).where(Qualification.teacher_id.in_(teacher_ids),Qualification.state=='APPROVED',Qualification.obtained<=period.end_date,(Qualification.expires.is_(None))|(Qualification.expires>=period.end_date)).order_by(Qualification.id)
    p=select(PointEntry).where(PointEntry.teacher_id.in_(teacher_ids),PointEntry.period_id==period.id).order_by(PointEntry.id)
    for source,query in [('qualifications',q),('points',p)]:
        checksum=sha256()
        for row in db.scalars(query.execution_options(yield_per=500)):checksum.update(digest(serial(row)).encode())
        result[source]=checksum.hexdigest()
    result['assessment_score']=digest(references)
    return result


def organization_source_changes(db,obj):
    from .calculation_freshness import source_changes
    from .services import point_source_changes
    if obj.state=='ARCHIVED':return {'changed':False,'items':[]}
    period=db.get(Period,obj.period_id);rule=db.get(OrganizationAssessmentRule,obj.rule_id)
    current=organization_facts(db,db.get(Org,obj.target_id),period)[1]
    result=source_changes(obj.source_snapshot,current,rule.config['components'])
    if any(c['source']=='points' for c in rule.config['components']):
        if any(point_source_changes(db,tid,period)['changed'] for tid in current['teacher_ids']):
            result['changed']=True;result['items'].append({'label':'教师积分的原始依据','before':'计算时的依据','after':'已变化，请先重算积分','details':[]})
    return result


def evaluate_org_rule(rule: OrganizationAssessmentRule, raw: dict):
    detail=[]
    for c in rule.config["components"]:
        value=Decimal(str(raw[c["source"]])); target=Decimal(str(c["target"])); weight=Decimal(str(c["weight"]))
        if c.get("method"):
            # 10.1 extended method: explainable steps are kept in the same calculation detail.
            from .scoring_methods import score_component
            score,formula,explain=score_component(c,value,"org")
            detail.append({"key":c["key"],"label":c["label"],"source":c["source"],"raw":str(value),"target":str(target),"weight":str(weight),"formula":formula,"score":str(score),"rule_id":rule.id,"rule_version":rule.version_no,**explain})
            continue
        score=max(Decimal(0),min(Decimal(1),value/target))*weight
        score=rounded(score)
        detail.append({"key":c["key"],"label":c["label"],"source":c["source"],"raw":str(value),"target":str(target),"weight":str(weight),"formula":f"max(0, min({value} ÷ {target}, 1)) × {weight}","score":str(score),"rule_id":rule.id,"rule_version":rule.version_no})
    return detail


def archive_payload(db, obj: OrganizationAssessment,*,actor=None,reason="",basis=""):
    evidence=db.scalars(select(OrganizationAssessmentMetricEvidence).where(OrganizationAssessmentMetricEvidence.assessment_id==obj.id).order_by(OrganizationAssessmentMetricEvidence.metric_code)).all()
    frozen={k:v for k,v in serial(obj).items() if k not in {"archive","archive_sha256"}}
    frozen['state']='ARCHIVED';frozen['version']=obj.version+1
    payload={"assessment":frozen,"evidence":serial(evidence),"archived_at":utcnow().isoformat(),
        "rule":serial(db.get(OrganizationAssessmentRule,obj.rule_id)),"period":serial(db.get(Period,obj.period_id)),
        "target":serial(db.get(Org,obj.target_id)),"archived_by":actor.id if actor else None,"reason":reason,"basis":basis}
    # Freeze all pre-archive events plus the final transition in the same command transaction.
    history=serial(db.scalars(select(WorkflowEvent).where(WorkflowEvent.object_type=='organization_assessment',
        WorkflowEvent.object_id==obj.id).order_by(WorkflowEvent.created_at,WorkflowEvent.id)).all())
    final={'object_type':'organization_assessment','object_id':obj.id,'actor_id':actor.id if actor else None,
        'actor_name':actor.name if actor else '', 'org_id':actor.org.id if actor else None,
        'action':'组织考核归档','created_at':payload['archived_at'],'reason':reason,'basis':basis}
    payload.update(schema_version=2,events=[*history,final])
    from .org_evidence import validate_org_payload
    validate_org_payload(payload,obj,creating=True)
    return payload, digest(payload)
