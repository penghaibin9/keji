"""Shared query / deterministic calculation services. No eval; no UI scoring."""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy import select, func, distinct
from fastapi import HTTPException
from .core import *
from .schemas import RecordIn
from .read_queries import record_query, assessment_query, stats
from .calculation_freshness import source_changes, require_current_sources
from .settings_catalog import validate_manual_source

D = Decimal

def rounded(value): return D(str(value)).quantize(D("0.01"), rounding=ROUND_HALF_UP)





def insert_record(db,actor,payload:RecordIn,batch_id=None,*,channel='manual'):
    actor.check_teacher(db,payload.teacher_id,active=True)
    values=payload.model_dump(exclude={"reason","basis"})
    if channel=='manual':validate_manual_source(db,payload.source)
    elif channel in {'import','middle'} and batch_id:values['source']='Excel导入' if channel=='import' else '学校数据中台'
    else:raise HTTPException(422,'接入渠道或批次无效')
    obj=TrainingRecord(**values,batch_id=batch_id)
    db.add(obj);db.flush()
    db.add(RecordRevision(record_id=obj.id,version=obj.version,data=serial(obj),reason=payload.reason,actor_id=actor.id))
    audit(db,actor,"records",obj.id,"写入培训业务数据",after=serial(obj),reason=payload.reason)
    return obj


def qualification_revision(db,actor,obj,reason):
    db.flush()
    data=serial(obj);data.pop("current_revision_id",None)
    rev=QualificationRevision(qualification_id=obj.id,version=obj.version,data=data,
        attachment_ids=list(obj.attachment_ids or []),actor_id=actor.id,reason=reason)
    db.add(rev);db.flush();obj.current_revision_id=rev.id
    return rev


def facts(db,teacher_id,period):
    records=db.scalars(select(TrainingRecord).where(TrainingRecord.teacher_id==teacher_id,
        TrainingRecord.state=="VALID",TrainingRecord.event_date>=period.start_date,TrainingRecord.event_date<=period.end_date)
        .order_by(TrainingRecord.id)).all()
    if len(records)>20000:raise HTTPException(422,"该教师本周期明细超过单次安全计算上限，请缩小周期")
    quals=db.scalars(select(Qualification).where(Qualification.teacher_id==teacher_id,Qualification.state=="APPROVED",
        Qualification.obtained<=period.end_date, (Qualification.expires.is_(None))|(Qualification.expires>=period.end_date))).all()
    points=db.scalars(select(PointEntry).where(PointEntry.teacher_id==teacher_id,PointEntry.period_id==period.id).order_by(PointEntry.created_at)).all()
    previous=db.scalar(select(Assessment).join(Period,Period.id==Assessment.period_id)
        .where(Assessment.teacher_id==teacher_id,Assessment.state=="ARCHIVED",Period.end_date<period.start_date)
        .order_by(Period.end_date.desc()).limit(1))
    from .assessment_evidence import verified_archive
    previous_frozen=verified_archive(previous) if previous else None
    snapshots=[]
    for q in quals:
        rev=db.get(QualificationRevision,q.current_revision_id) if q.current_revision_id else None
        snapshots.append({"id":q.id,"version":q.version,"revision":serial(rev),
                          "attachments":[serial(db.get(Attachment,a)) for a in (rev.attachment_ids if rev else [])]})
    from .reference_data import teaching_credit_facts
    credits,credit_basis=teaching_credit_facts(db,db.get(User,teacher_id),period)
    raw={"hours":sum((D(str(r.hours)) for r in records),D(0)),
         "participants":D(sum(r.participants for r in records)),
         "income":sum((D(str(r.income)) for r in records),D(0)),
         "qualifications":D(len(quals)),"points":sum((D(str(p.amount)) for p in points),D(0)),
         "assessment_score":D(str(previous_frozen["assessment"]["score"])) if previous_frozen else D(0),
         "credits":credits}
    snapshot={"as_of":utcnow().isoformat(),"period":serial(period),"training_records":serial(records),
              "qualifications":snapshots,"point_entries":[{"id":p.id,"item_key":p.item_key,"amount":str(p.amount),"rule_id":p.rule_id,"batch_id":p.batch_id,"evidence_sha256":digest(p.source_snapshot)} for p in points],
              "previous_archived_assessment":({"id":previous.id,"period_id":previous.period_id,"score":str(previous_frozen["assessment"]["score"]),"archive_sha256":previous.archive_sha256} if previous else None),
              "values":serial(raw),"qualification_basis":"审核通过、取得日期不晚于周期结束、有效期覆盖周期结束日；无有效期视为长期有效",
              "assessment_score_basis":"本周期开始日前最近一个已归档考核结果，不引用当期未完成考核",
              "teaching_credits":credit_basis,
              "credits_basis":"只算教研室主任已认定的课；教务授课按课程号取课程总库学分，超星课程用自带学分（只算创建人）；第一学期按 9月1日、第二学期按次年 3月1日 落入考核周期"}
    return raw,snapshot


def credit_gaps(snapshot):
    """授课学分缺数据的课程：计入但没有学分，或学期名识别不出学年。"""
    basis=snapshot.get("teaching_credits") or {}
    missing=[c for c in basis.get("courses",[]) if c.get("counted") and c.get("credit") is None]
    return missing+list(basis.get("excluded",[]))


def require_complete_credits(rule,snapshot,item_keys=None):
    # 缺学分会被当成 0 分算进去，正式计算前拦下，避免出“看起来正常”的错分
    if not any(c.get("source")=="credits" and (not item_keys or c["key"] in item_keys) for c in rule.config.get("components",[])):return
    gaps=credit_gaps(snapshot)
    if gaps:
        names="、".join(sorted({str(g.get("course_code") or "") for g in gaps})[:5])
        raise HTTPException(409,f"有 {len(gaps)} 门授课课程缺学分或学期名称识别不出（{names}），请先在“授课与学分”补齐后再正式计算")


def evaluate(rule,raw):
    details=[]
    for c in rule.config["components"]:
        value=D(str(raw[c["source"]]));factor=D(str(c["factor"]));weight=D(str(c["weight"]));target=D(str(c["target"]))
        if rule.kind=="points":
            result=value*factor
            if c.get("cap") is not None:result=min(result,D(str(c["cap"])))
            formula=f"{value} × {factor}"+(f"；上限 {c['cap']}" if c.get("cap") is not None else "")
        else:
            result=max(D(0),min(D(1),value/target))*weight
            formula=f"max(0, min({value} ÷ {target}, 1)) × {weight}"
        details.append({"key":c["key"],"label":c["label"],"source":c["source"],"raw":str(value),
                        "formula":formula,"score":str(rounded(result)),"rule_id":rule.id,"rule_version":rule.version_no})
    return details


def evaluate_rule(rule,raw):
    """10.1/9.1 dispatcher. Legacy components go through the untouched evaluate();
    components with an explicit extended method use scoring_methods with full steps."""
    components=rule.config["components"]
    if not any(c.get("method") for c in components):return evaluate(rule,raw)
    from types import SimpleNamespace
    from .scoring_methods import score_component
    details=[]
    for c in components:
        if not c.get("method"):
            details.extend(evaluate(SimpleNamespace(id=rule.id,kind=rule.kind,version_no=rule.version_no,config={"components":[c]}),raw));continue
        score,formula,explain=score_component(c,D(str(raw[c["source"]])),rule.kind)
        details.append({"key":c["key"],"label":c["label"],"source":c["source"],"raw":str(D(str(raw[c["source"]]))),
                        "formula":formula,"score":str(score),"rule_id":rule.id,"rule_version":rule.version_no,**explain})
    return details


def point_source_changes(db,teacher_id,period,current=None):
    current=current or facts(db,teacher_id,period)[1]
    entries=db.scalars(select(PointEntry).where(PointEntry.teacher_id==teacher_id,PointEntry.period_id==period.id,PointEntry.kind.notin_(['MANUAL','SOCIAL'])).order_by(PointEntry.created_at,PointEntry.id)).all()
    latest={p.item_key:p for p in entries};items=[]
    for key,entry in latest.items():
        frozen=entry.source_snapshot or {}
        components=[c for c in frozen.get('rule',{}).get('config',{}).get('components',[]) if c['key']==key]
        items.extend(source_changes(frozen.get('facts',{}),current,components)['items'])
    return {'changed':bool(items),'items':items}


def assessment_source_changes(db,obj):
    if obj.state=='ARCHIVED':return {'changed':False,'items':[]}
    rule=db.get(Rule,obj.rule_id);period=db.get(Period,obj.period_id)
    current=facts(db,obj.teacher_id,period)[1]
    changes=source_changes(obj.source_snapshot,current,rule.config['components'])
    if any(c['source']=='points' for c in rule.config['components']):
        upstream=point_source_changes(db,obj.teacher_id,period,current)
        if upstream['changed']:
            changes['items'].append({'label':'本期积分的原始依据','before':'计算时的依据','after':'已变化，请先重算积分','details':[]})
            changes['changed']=True
    return changes


def active_rule(db,kind,period_id):
    rule=db.scalar(select(Rule).where(Rule.kind==kind,Rule.period_id==period_id,Rule.state=="ACTIVE"))
    if not rule:raise HTTPException(409,"本周期尚未启用相应规则，请先配置、试算并启用")
    return rule


def calculate_points(db,actor,period,teacher_ids,item_keys,reason):
    lock_guard(db,"calculations")
    rule=active_rule(db,"points",period.id)
    keys={x["key"] for x in rule.config["components"]}
    if item_keys and not set(item_keys)<=keys:raise HTTPException(422,"指定积分项不在当前规则中")
    batch=CalculationBatch(kind="points",period_id=period.id,rule_id=rule.id,actor_id=actor.id,reason=reason)
    db.add(batch);db.flush();out=[]
    for teacher_id in teacher_ids:
        actor.check_teacher(db,teacher_id,active=True)
        if db.scalar(select(PointEntry.id).where(PointEntry.teacher_id==teacher_id,PointEntry.period_id==period.id,PointEntry.kind=='SOCIAL').limit(1)):
            raise HTTPException(409,'本周期已有社会培训正式认定积分，不能再用旧汇总规则重复计算')
        if archive_exists(db,teacher_id,period.id):raise HTTPException(409,"已归档周期的积分依据不可修改")
        bal=db.scalar(select(PointBalance).where(PointBalance.teacher_id==teacher_id,PointBalance.period_id==period.id).with_for_update())
        if bal and bal.confirmed:raise HTTPException(409,"该教师已确认积分；如需纠错应先留痕解锁，已归档不可解锁")
        if not bal:bal=PointBalance(teacher_id=teacher_id,period_id=period.id,confirmed=False,version=1);db.add(bal)
        raw,snapshot=facts(db,teacher_id,period);require_complete_credits(rule,snapshot,item_keys);details=evaluate_rule(rule,raw)
        entries=db.scalars(select(PointEntry).where(PointEntry.teacher_id==teacher_id,PointEntry.period_id==period.id)).all()
        old={};latest={}
        for e in entries:
            if e.kind not in {"MANUAL", "SOCIAL"}:
                old[e.item_key]=old.get(e.item_key,D(0))+D(str(e.amount))
                if e.item_key not in latest or (e.created_at,e.id)>(latest[e.item_key].created_at,latest[e.item_key].id):latest[e.item_key]=e
        targets={d["key"]:d for d in details if not item_keys or d["key"] in item_keys}
        if not item_keys:
            for removed in set(old)-keys:targets[removed]={"key":removed,"label":"规则移除项","raw":"0","formula":"新规则移除本项；追加冲销，保留历史","score":"0"}
        added=[]
        for key,detail in targets.items():
            target=D(detail["score"]);delta=rounded(target-old.get(key,D(0)))
            previous=latest.get(key)
            components=[c for c in rule.config['components'] if c['key']==key]
            if delta==0 and previous and previous.rule_id==rule.id and not source_changes(previous.source_snapshot.get('facts',{}),snapshot,components)['changed']:continue
            entry=PointEntry(teacher_id=teacher_id,period_id=period.id,item_key=key,
                kind="BASE" if key not in old else "RECALC",amount=delta,raw_value=detail["raw"],
                formula=detail["formula"]+f"；本次目标 {target} − 已计 {old.get(key,D(0))} = 追加 {delta}",
                rule_id=rule.id,batch_id=batch.id,source_snapshot={"facts":snapshot,"rule":serial(rule)},
                actor_id=actor.id,reason=reason,basis="服务端根据本周期业务明细取数")
            db.add(entry);db.flush();added.append(serial(entry))
        bal.version+=1
        audit(db,actor,"points",teacher_id,"计算积分（追加差额）",after={"batch_id":batch.id,"entries":len(added)},reason=reason)
        out.append({"teacher_id":teacher_id,"entries":added})
    batch.result={"teachers":len(out),"entry_count":sum(len(x["entries"]) for x in out)}
    return {"batch_id":batch.id,"items":out,"summary":batch.result}


def calculate_assessments(db,actor,period,teacher_ids,reason):
    lock_guard(db,"calculations");rule=active_rule(db,"assessment",period.id)
    batch=CalculationBatch(kind="assessment",period_id=period.id,rule_id=rule.id,actor_id=actor.id,reason=reason)
    db.add(batch);db.flush();out=[]
    for tid in teacher_ids:
        actor.check_teacher(db,tid,active=True)
        obj=db.scalar(select(Assessment).where(Assessment.teacher_id==tid,Assessment.period_id==period.id).with_for_update())
        if obj and obj.state!="TEACHER":raise HTTPException(409,"已确认或已归档考核不能被批量重算覆盖，应先按审核流程退回")
        raw,snap=facts(db,tid,period);require_complete_credits(rule,snap)
        if any(c['source']=='points' for c in rule.config['components']):require_current_sources(point_source_changes(db,tid,period,snap))
        detail=evaluate_rule(rule,raw)
        score=rounded(sum((D(x["score"]) for x in detail),D(0)))
        if obj:
            before=serial(obj);obj.rule_id=rule.id;obj.detail=detail;obj.score=score;obj.source_snapshot=snap;obj.version+=1;obj.returned=False
        else:
            before={};obj=Assessment(teacher_id=tid,period_id=period.id,rule_id=rule.id,detail=detail,score=score,source_snapshot=snap)
            db.add(obj);db.flush()
        workflow(db,actor,"assessment",obj.id,"计算考核",before,serial(obj),reason)
        out.append(serial(obj))
    batch.result={"teachers":len(out)}
    return {"batch_id":batch.id,"items":out}
