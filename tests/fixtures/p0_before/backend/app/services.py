"""Shared query / deterministic calculation services. No eval; no UI scoring."""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy import select, func, distinct
from fastapi import HTTPException
from .core import *
from .schemas import RecordIn

D = Decimal

def rounded(value): return D(str(value)).quantize(D("0.01"), rounding=ROUND_HALF_UP)

def record_query(db, actor, filters=None):
    filters = filters or {}
    allowed={"q","teacher_id","org_id","start","end","project_code","course_code","period_id"}
    if set(filters)-allowed: raise HTTPException(422,"含不支持的筛选字段")
    q=select(TrainingRecord).where(actor.scope(TrainingRecord.teacher_id),TrainingRecord.state=="VALID")
    for name in ["teacher_id","project_code","course_code"]:
        if filters.get(name): q=q.where(getattr(TrainingRecord,name)==filters[name])
    for name,comparison in [("start",lambda x: TrainingRecord.event_date>=x),("end",lambda x: TrainingRecord.event_date<=x)]:
        if filters.get(name):
            try: value=date.fromisoformat(str(filters[name]))
            except ValueError: raise HTTPException(422,"日期格式应为 YYYY-MM-DD")
            q=q.where(comparison(value))
    if filters.get("period_id"):
        period=db.get(Period,filters["period_id"])
        if not period: raise HTTPException(404,"考核周期不存在")
        q=q.where(TrainingRecord.event_date>=period.start_date,TrainingRecord.event_date<=period.end_date)
    if filters.get("q"):
        text=str(filters["q"])[:100]
        q=q.where(TrainingRecord.project.contains(text,autoescape=True)|TrainingRecord.course.contains(text,autoescape=True)|TrainingRecord.external_key.contains(text,autoescape=True))
    if filters.get("org_id"):
        org=db.get(Org,filters["org_id"])
        if not org or org.id not in actor.org_ids: raise HTTPException(403,"筛选组织不在授权范围")
        ids=org_scope(db,org,org.kind)
        q=q.where(TrainingRecord.teacher_id.in_(select(User.id).where(User.org_id.in_(ids))))
    return q


def stats(db, actor, filters=None):
    sub=record_query(db,actor,filters).subquery()
    values=db.execute(select(func.count(),func.coalesce(func.sum(sub.c.income),0),func.coalesce(func.sum(sub.c.hours),0),
        func.coalesce(func.sum(sub.c.participants),0),func.count(distinct(sub.c.teacher_id)),func.count(distinct(sub.c.project_code)),
        func.count(distinct(sub.c.course_code)),func.count(distinct(sub.c.class_code))).select_from(sub)).one()
    # The same filtered subquery is used for totals, ranking and trends.
    groups=db.execute(select(User.org_id,func.sum(sub.c.income),func.sum(sub.c.participants),func.count(distinct(sub.c.teacher_id)))
        .join(User,User.id==sub.c.teacher_id).group_by(User.org_id).order_by(func.sum(sub.c.income).desc())).all()
    months=db.execute(select(func.substr(sub.c.event_date,1,7).label("month"),func.sum(sub.c.income),func.sum(sub.c.participants))
        .group_by("month").order_by("month")).all()
    orgs={o.id:o for o in db.scalars(select(Org)).all()}
    colleges={}
    for oid,income,people,teachers in groups:
        o=orgs.get(oid);co=orgs.get(o.parent_id) if o and o.kind=="dept" else o
        if co:
            c=colleges.setdefault(co.id,{"id":co.id,"name":co.name,"income":D(0),"participants":0,"teachers":0})
            c["income"]+=income or D(0);c["participants"]+=people;c["teachers"]+=teachers
    aq=select(Assessment).where(actor.scope(Assessment.teacher_id))
    if filters and filters.get("period_id"):aq=aq.where(Assessment.period_id==filters["period_id"])
    if filters and filters.get("teacher_id"):aq=aq.where(Assessment.teacher_id==filters["teacher_id"])
    if filters and filters.get("org_id"):
        org=db.get(Org,filters["org_id"])
        aq=aq.where(Assessment.teacher_id.in_(select(User.id).where(User.org_id.in_(org_scope(db,org,org.kind)))))
    a_sub=aq.subquery()
    distribution=db.execute(select(a_sub.c.state,func.count()).group_by(a_sub.c.state)).all()
    return serial({"records":values[0],"income":values[1],"hours":values[2],"participants":values[3],"teachers":values[4],
        "projects":values[5],"courses":values[6],"classes":values[7],
        "ranking":[{"org_id":oid,"name":orgs[oid].name,"income":income,"participants":people,"teachers":tc} for oid,income,people,tc in groups],
        "colleges":sorted(colleges.values(),key=lambda x:x["income"],reverse=True),
        "trend":[{"month":m,"income":i,"participants":p} for m,i,p in months],
        "assessment_states":dict(distribution),
        "metric_notes":db.get(Setting,"metrics").value,
        "qualification_warning_days":db.get(Setting,"qualification").value["expiry_days"]})


def insert_record(db,actor,payload:RecordIn,batch_id=None):
    actor.check_teacher(db,payload.teacher_id,active=True)
    obj=TrainingRecord(**payload.model_dump(exclude={"reason","basis"}),batch_id=batch_id)
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
    snapshots=[]
    for q in quals:
        rev=db.get(QualificationRevision,q.current_revision_id) if q.current_revision_id else None
        snapshots.append({"id":q.id,"version":q.version,"revision":serial(rev),
                          "attachments":[serial(db.get(Attachment,a)) for a in (rev.attachment_ids if rev else [])]})
    raw={"hours":sum((D(str(r.hours)) for r in records),D(0)),
         "participants":D(sum(r.participants for r in records)),
         "income":sum((D(str(r.income)) for r in records),D(0)),
         "qualifications":D(len(quals)),"points":sum((D(str(p.amount)) for p in points),D(0)),
         "assessment_score":D(str(previous.score)) if previous else D(0)}
    snapshot={"as_of":utcnow().isoformat(),"period":serial(period),"training_records":serial(records),
              "qualifications":snapshots,"point_entries":[{"id":p.id,"item_key":p.item_key,"amount":str(p.amount),"rule_id":p.rule_id,"batch_id":p.batch_id,"evidence_sha256":digest(p.source_snapshot)} for p in points],
              "previous_archived_assessment":({"id":previous.id,"period_id":previous.period_id,"score":str(previous.score),"archive_sha256":previous.archive_sha256} if previous else None),
              "values":serial(raw),"qualification_basis":"审核通过、取得日期不晚于周期结束、有效期覆盖周期结束日；无有效期视为长期有效",
              "assessment_score_basis":"本周期开始日前最近一个已归档考核结果，不引用当期未完成考核"}
    return raw,snapshot


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
        if archive_exists(db,teacher_id,period.id):raise HTTPException(409,"已归档周期的积分依据不可修改")
        bal=db.scalar(select(PointBalance).where(PointBalance.teacher_id==teacher_id,PointBalance.period_id==period.id).with_for_update())
        if bal and bal.confirmed:raise HTTPException(409,"该教师已确认积分；如需纠错应先留痕解锁，已归档不可解锁")
        if not bal:bal=PointBalance(teacher_id=teacher_id,period_id=period.id,confirmed=False,version=1);db.add(bal)
        raw,snapshot=facts(db,teacher_id,period);details=evaluate(rule,raw)
        entries=db.scalars(select(PointEntry).where(PointEntry.teacher_id==teacher_id,PointEntry.period_id==period.id)).all()
        old={}
        for e in entries:
            if e.kind!="MANUAL":old[e.item_key]=old.get(e.item_key,D(0))+D(str(e.amount))
        targets={d["key"]:d for d in details if not item_keys or d["key"] in item_keys}
        if not item_keys:
            for removed in set(old)-keys:targets[removed]={"key":removed,"label":"规则移除项","raw":"0","formula":"新规则移除本项；追加冲销，保留历史","score":"0"}
        added=[]
        for key,detail in targets.items():
            target=D(detail["score"]);delta=rounded(target-old.get(key,D(0)))
            if delta==0 and key in old:continue
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
        raw,snap=facts(db,tid,period);detail=evaluate(rule,raw)
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
