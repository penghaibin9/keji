"""11.3 湘培直通车 outbound payload assembly from the local ledger.

The builders produce records in an explicit INTERNAL canonical field set
(CANONICAL_FIELDS below).  They never invent provincial field names: the
connection's existing field-mapping layer (Connection.mappings, per data_type,
``source`` = canonical field, ``target`` = provincial field from the official
spec) translates them when the task is enqueued through ``enqueue_sync``.

Rules:
* scope   - every query goes through the live actor scope (record_query /
            assessment_query); nothing outside the authorized teachers is read.
* quality - only VALID training rows; assessment results only when ARCHIVED and
            the archive digest verifies (confirmed, frozen values are reported).
* keys    - each record carries a stable ``business_key`` derived from the local
            business identity (project/course/class code, ledger external_key,
            assessment id).  enqueue_sync/business_idempotency then reuse an
            already-queued identical item instead of sending it twice.

Four catalog types stay WAITING_SOURCE because the data is produced in school
source systems this platform does not own (WAITING_REASONS).
"""
from __future__ import annotations
from fastapi import HTTPException
from sqlalchemy import select, func
from .core import serial
from .models import TrainingRecord, User, Org, Period, Assessment
from .read_queries import record_query, assessment_query

CANONICAL_FIELDS = {
 'training_project': [('business_key','业务唯一键'),('project_code','项目编码'),('project_name','项目名称'),('start_date','项目开始日期'),('end_date','项目结束日期'),('source','数据来源')],
 'course': [('business_key','业务唯一键'),('course_code','课程编码'),('course_name','课程名称'),('project_code','所属项目编码'),('source','数据来源')],
 'class': [('business_key','业务唯一键'),('class_code','班级编码'),('class_name','班级名称'),('project_code','所属项目编码'),('course_code','所属课程编码'),('start_date','开班日期'),('end_date','结班日期'),('source','数据来源')],
 'teaching': [('business_key','业务唯一键'),('record_key','台账来源编号'),('teacher_staff_no','授课教师工号'),('teacher_name','授课教师姓名'),('org_code','教师所属组织编码'),('event_date','授课日期'),('project_code','项目编码'),('course_code','课程编码'),('class_code','班级编码'),('hours','授课学时')],
 'participants': [('business_key','业务唯一键'),('record_key','台账来源编号'),('event_date','业务日期'),('project_code','项目编码'),('course_code','课程编码'),('class_code','班级编码'),('participants','人次')],
 'training_record': [('business_key','业务唯一键'),('record_key','台账来源编号'),('event_date','业务日期'),('teacher_staff_no','授课教师工号'),('project_code','项目编码'),('project_name','项目名称'),('course_code','课程编码'),('course_name','课程名称'),('class_code','班级编码'),('class_name','班级名称'),('hours','学时'),('participants','人次'),('income','培训收入（元）'),('source','数据来源')],
 'assessment_result': [('business_key','业务唯一键'),('teacher_staff_no','教师工号'),('teacher_name','教师姓名'),('org_code','教师所属组织编码'),('period_name','考核周期'),('period_start','周期开始日期'),('period_end','周期结束日期'),('score','考核得分'),('rule_name','考核规则'),('rule_version','规则版本'),('archived_at','归档时间'),('archive_sha256','归档校验值')],
}
SOURCE_NOTES = {
 'training_project':'当前范围内有效培训台账涉及的项目，名称与起止日期取已接入的项目主数据',
 'course':'当前范围内有效培训台账涉及的课程，名称取课程主数据',
 'class':'当前范围内有效培训台账涉及的班级，名称与起止日期取班级主数据',
 'teaching':'每条有效培训台账对应一条教师授课记录',
 'participants':'每条有效培训台账的课程人次',
 'training_record':'有效（未作废）培训台账明细',
 'assessment_result':'仅已归档且归档校验通过的教师考核结果，取归档冻结值',
}
WAITING_REASONS = {
 'plan':'培训计划由学校培训管理/教务源系统编制和审批，本平台台账只记录已发生的培训业务，没有计划编制与审批数据；须学校确认计划的权威来源系统与字段后再接入。',
 'learning_process':'学员签到、学习时长、作业等学习过程数据产生在学校在线学习或教学平台，本平台不采集学员个人学习过程。',
 'completion_result':'学员结业结论由培训实施单位的教务系统判定；本平台的“考核结果”是教师考核，不是学员结业结论，不能替代。',
 'certificate':'学员培训证书由发证系统签发；本平台保存的是教师资质证书，不能替代学员结业证书。',
}
MAX_LEDGER_ROWS = 20000
CHUNK = 1000


def ledger_catalog():
    from .integrations import DATA_CATALOG
    out = []
    for code, name, status in DATA_CATALOG['province']:
        item = {'data_type': code, 'name': name, 'buildable': code in CANONICAL_FIELDS}
        if code in CANONICAL_FIELDS:
            item.update(fields=[{'key': k, 'label': v} for k, v in CANONICAL_FIELDS[code]], source_note=SOURCE_NOTES[code])
        else:
            item['waiting_reason'] = WAITING_REASONS.get(code, '本平台没有该类数据的权威来源，须学校确认来源系统。')
        out.append(item)
    return out


def _scope_filters(f):
    return {k: v for k, v in f.items() if k in {'start', 'end', 'period_id', 'org_id'} and v}


def _records(db, actor, f):
    q = record_query(db, actor, _scope_filters(f))
    total = db.scalar(select(func.count()).select_from(q.order_by(None).subquery()))
    if total > MAX_LEDGER_ROWS:
        raise HTTPException(422, f'所选范围有效台账超过 {MAX_LEDGER_ROWS} 条，请缩小日期或周期范围后分批生成')
    return db.scalars(q.order_by(TrainingRecord.event_date, TrainingRecord.external_key, TrainingRecord.id)).all()


def _people(db, records):
    ids = {r.teacher_id for r in records}
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(ids)))} if ids else {}
    orgs = {o.id: o for o in db.scalars(select(Org).where(Org.id.in_({u.org_id for u in users.values()})))} if users else {}
    return users, orgs


def _date(value):
    return value.isoformat() if value else None


def build_ledger_records(db, actor, data_type, f):
    """Return canonical records (each with ``business_key``) for one data type."""
    if data_type in WAITING_REASONS:
        raise HTTPException(409, '该类数据待学校源系统提供：' + WAITING_REASONS[data_type])
    if data_type not in CANONICAL_FIELDS:
        raise HTTPException(422, '数据类型不在湘培直通车台账组装目录')
    if not any(f.get(k) for k in ('start', 'end', 'period_id')):
        raise HTTPException(422, '请选择考核周期或业务日期范围，避免一次组装全部历史')
    if data_type == 'assessment_result':
        return _assessment_results(db, actor, f)
    rows = _records(db, actor, f)
    if data_type in {'training_project', 'course', 'class'}:
        from .reference_data import TrainingProjectMaster, TrainingCourseMaster, TrainingClassMaster
        model, field = {'training_project': (TrainingProjectMaster, 'project_code'), 'course': (TrainingCourseMaster, 'course_code'),
                        'class': (TrainingClassMaster, 'class_code')}[data_type]
        first = {}
        for r in rows:
            first.setdefault(getattr(r, field), r)
        masters = {m.code: m for m in db.scalars(select(model).where(model.code.in_(list(first))))} if first else {}
        out = []
        for code in sorted(first):
            r, m = first[code], masters.get(code)
            if data_type == 'training_project':
                out.append({'business_key': 'project:' + code, 'project_code': code, 'project_name': m.name if m else r.project,
                            'start_date': _date(m.start_date) if m else None, 'end_date': _date(m.end_date) if m else None,
                            'source': m.source if m else '培训台账'})
            elif data_type == 'course':
                out.append({'business_key': 'course:' + code, 'course_code': code, 'course_name': m.name if m else r.course,
                            'project_code': (m.project_code if m and m.project_code else r.project_code), 'source': m.source if m else '培训台账'})
            else:
                out.append({'business_key': 'class:' + code, 'class_code': code, 'class_name': m.name if m else r.class_name,
                            'project_code': m.project_code if m else r.project_code, 'course_code': m.course_code if m else r.course_code,
                            'start_date': _date(m.start_date) if m else None, 'end_date': _date(m.end_date) if m else None,
                            'source': m.source if m else '培训台账'})
        return out
    users, orgs = _people(db, rows); out = []
    for r in rows:
        u = users.get(r.teacher_id); o = orgs.get(u.org_id) if u else None
        if data_type == 'teaching':
            out.append({'business_key': 'teaching:' + r.external_key, 'record_key': r.external_key,
                        'teacher_staff_no': u.staff_no if u else None, 'teacher_name': u.name if u else None,
                        'org_code': o.code if o else None, 'event_date': _date(r.event_date), 'project_code': r.project_code,
                        'course_code': r.course_code, 'class_code': r.class_code, 'hours': serial(r.hours)})
        elif data_type == 'participants':
            out.append({'business_key': 'participants:' + r.external_key, 'record_key': r.external_key, 'event_date': _date(r.event_date),
                        'project_code': r.project_code, 'course_code': r.course_code, 'class_code': r.class_code, 'participants': r.participants})
        else:
            out.append({'business_key': 'record:' + r.external_key, 'record_key': r.external_key, 'event_date': _date(r.event_date),
                        'teacher_staff_no': u.staff_no if u else None, 'project_code': r.project_code, 'project_name': r.project,
                        'course_code': r.course_code, 'course_name': r.course, 'class_code': r.class_code, 'class_name': r.class_name,
                        'hours': serial(r.hours), 'participants': r.participants, 'income': serial(r.income), 'source': r.source})
    return out


def _assessment_results(db, actor, f):
    from .assessment_evidence import assessment_projection
    filters = {'state': 'ARCHIVED', **({'period_id': f['period_id']} if f.get('period_id') else {}),
               **({'org_id': f['org_id']} if f.get('org_id') else {})}
    q = assessment_query(db, actor, filters).join(Period, Period.id == Assessment.period_id)
    # A date window selects periods that END inside it (results belong to a closed cycle).
    if f.get('start'):
        q = q.where(Period.end_date >= _parse(f['start']))
    if f.get('end'):
        q = q.where(Period.end_date <= _parse(f['end']))
    if db.scalar(select(func.count()).select_from(q.order_by(None).subquery())) > MAX_LEDGER_ROWS:
        raise HTTPException(422, '所选范围考核结果过多，请按周期分批生成')
    out = []
    orgs = {o.id: o for o in db.scalars(select(Org))}
    for obj in db.scalars(q.order_by(Period.end_date, Assessment.teacher_id, Assessment.id)):
        p = assessment_projection(db, obj)  # verifies the archive digest; never reports live values
        frozen = p['assessment']; teacher = p['teacher']; period = p['period']; rule = p['rule']
        org = orgs.get(teacher.get('org_id')) if teacher.get('org_id') else None
        out.append({'business_key': 'assessment:' + obj.id, 'teacher_staff_no': teacher.get('staff_no'), 'teacher_name': teacher.get('name'),
                    'org_code': org.code if org else None, 'period_name': period.get('name'), 'period_start': period.get('start_date'),
                    'period_end': period.get('end_date'), 'score': str(frozen['score']), 'rule_name': rule.get('name'),
                    'rule_version': rule.get('version_no'), 'archived_at': frozen['archive'].get('archived_at'),
                    'archive_sha256': obj.archive_sha256})
    return out


def _parse(value):
    import re
    from datetime import date
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise HTTPException(422, '日期格式应为 YYYY-MM-DD')
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(422, '日期格式应为 YYYY-MM-DD') from None


def chunks(records):
    return [records[i:i + CHUNK] for i in range(0, len(records), CHUNK)]
