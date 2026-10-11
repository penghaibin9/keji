"""Shared, read-only business scope. Requires the caller's real authenticated actor.

No user/role fallback is implemented here. This module deliberately does not
reconstruct the missing authentication layer. These queries perform no writes.
"""
from __future__ import annotations
from collections.abc import Mapping
from datetime import date, datetime, time, timedelta
from decimal import Decimal
import re
from fastapi import HTTPException
from sqlalchemy import select, func, distinct, case
from .models import Org, User, Period, TrainingRecord, Assessment, Setting, Audit
from .reference_data import TrainingProjectMaster,TrainingCourseMaster,TrainingClassMaster

RECORD_FILTERS = frozenset({'q','teacher_id','org_id','start','end','project_code','course_code','period_id'})
ASSESSMENT_FILTERS = RECORD_FILTERS | {'state','returned','business_scope','progress'}
STAT_FILTERS = RECORD_FILTERS | {'state','returned'}
BUSINESS_FILTERS = frozenset({'q','start','end','project_code','course_code'})
ASSESSMENT_STATES = frozenset({'TEACHER','DEPARTMENT','COLLEGE','SCHOOL','READY','ARCHIVED'})


# 10.9 quick filters: each role's "本级" maps onto the multi-state workflow.
ASSESSMENT_ORDER = ('TEACHER','DEPARTMENT','COLLEGE','SCHOOL','READY','ARCHIVED')
ROLE_STAGES = {'teacher':('TEACHER',),'dept':('DEPARTMENT',),'college':('COLLEGE',),'school':('SCHOOL','READY')}
PROGRESS_VALUES = {'pending':'本级待处理','done':'本级已完成','returned':'已退回'}


def progress_states(kind, progress):
    stages = ROLE_STAGES.get(kind, ())
    if progress == 'pending':
        return stages
    last = max(ASSESSMENT_ORDER.index(x) for x in stages) if stages else len(ASSESSMENT_ORDER)
    return ASSESSMENT_ORDER[last+1:]


def clean_filters(filters, allowed):
    if filters is None:
        return {}
    if not isinstance(filters, Mapping) or set(filters) - allowed:
        raise HTTPException(422, '含不支持的筛选字段')
    result = {}
    for key, value in filters.items():
        if value is None or value == '':
            continue
        if isinstance(value, bool) and key in {'returned','business_scope'}:
            value = 'true' if value else 'false'
        if not isinstance(value, str) or len(value) > (100 if key == 'q' else 128):
            raise HTTPException(422, '筛选值格式或长度不正确')
        if any(ord(c) < 32 for c in value):
            raise HTTPException(422, '筛选值包含控制字符')
        result[key] = value
    return result


def boolean_filter(value):
    if value in ('1', 'true'):
        return True
    if value in ('0', 'false'):
        return False
    raise HTTPException(422, '布尔筛选只允许 true/false 或 1/0')


def authorized_org_descendants(db, actor, org_id):
    # Intersect with the live actor scope. Organization membership is never an
    # alternative to permission. A malformed hierarchy fails closed.
    permitted = set(actor.org_ids)
    org = db.get(Org, org_id)
    if org is None or not org.active or org_id not in permitted:
        raise HTTPException(403, '筛选组织不在授权范围')
    found, frontier = {org_id}, {org_id}
    while frontier:
        children = set(db.scalars(select(Org.id).where(Org.parent_id.in_(frontier), Org.active.is_(True))))
        if children & found:
            raise HTTPException(503, '组织层级异常，请联系管理员')
        found |= children
        if len(found) > 10000:
            raise HTTPException(503, '组织层级超过安全检查范围')
        frontier = children
    return sorted(found & permitted)


def record_query(db, actor, filters=None):
    f = clean_filters(filters, RECORD_FILTERS)
    q = select(TrainingRecord).where(actor.scope(TrainingRecord.teacher_id), TrainingRecord.state == 'VALID')
    for name in ('teacher_id','project_code','course_code'):
        if name in f:
            q = q.where(getattr(TrainingRecord, name) == f[name])
    bounds = {}
    for name in ('start','end'):
        if name not in f:
            continue
        try:
            if re.fullmatch(r'\d{4}-\d{2}-\d{2}', f[name]) is None:
                raise ValueError('date shape')
            bounds[name] = date.fromisoformat(f[name])
        except ValueError:
            raise HTTPException(422, '日期格式应为 YYYY-MM-DD') from None
    if 'start' in bounds and 'end' in bounds and bounds['start'] > bounds['end']:
        raise HTTPException(422, '开始日期不能晚于结束日期')
    if 'start' in bounds:
        q = q.where(TrainingRecord.event_date >= bounds['start'])
    if 'end' in bounds:
        q = q.where(TrainingRecord.event_date <= bounds['end'])
    if 'period_id' in f:
        period = db.get(Period, f['period_id'])
        if period is None:
            raise HTTPException(404, '考核周期不存在')
        q = q.where(TrainingRecord.event_date >= period.start_date, TrainingRecord.event_date <= period.end_date)
    if 'q' in f:
        word = f['q']
        q = q.where(TrainingRecord.project.contains(word, autoescape=True) |
                    TrainingRecord.course.contains(word, autoescape=True) |
                    TrainingRecord.external_key.contains(word, autoescape=True) |
                    TrainingRecord.teacher_id.in_(select(User.id).where(User.name.contains(word,autoescape=True)|User.staff_no.contains(word,autoescape=True))))
    if 'org_id' in f:
        ids = authorized_org_descendants(db, actor, f['org_id'])
        q = q.where(TrainingRecord.teacher_id.in_(select(User.id).where(User.org_id.in_(ids))))
    return q


def assessment_query(db, actor, filters=None, *, business_query=None):
    """Preserve cycle scores; filter only the set of assessments being viewed.

    Native assessment lists include qualified teachers with no training rows.
    A dashboard drill explicitly passes business_scope=true, or a training-only
    filter, to use the same participating teacher set as the dashboard.
    """
    f = clean_filters(filters, ASSESSMENT_FILTERS)
    rf = {k:v for k,v in f.items() if k in RECORD_FILTERS}
    # Validates every supplied scope/period/date, even if there are no matches.
    rq = business_query if business_query is not None else record_query(db, actor, rf)
    q = select(Assessment).where(actor.scope(Assessment.teacher_id))
    for name in ('period_id','teacher_id'):
        if name in f:
            q = q.where(getattr(Assessment, name) == f[name])
    if 'org_id' in f:
        ids = authorized_org_descendants(db, actor, f['org_id'])
        q = q.where(Assessment.teacher_id.in_(select(User.id).where(User.org_id.in_(ids))))
    use_business = boolean_filter(f['business_scope']) if 'business_scope' in f else False
    if business_query is not None or use_business or BUSINESS_FILTERS & f.keys():
        # IN(subquery) avoids multiplying assessment counts for multiple records.
        scope = rq.subquery()
        q = q.where(Assessment.teacher_id.in_(select(scope.c.teacher_id).distinct()))
    if 'state' in f:
        if f['state'] not in ASSESSMENT_STATES:
            raise HTTPException(422, '考核环节不正确')
        q = q.where(Assessment.state == f['state'])
    if 'returned' in f:
        q = q.where(Assessment.returned.is_(boolean_filter(f['returned'])))
    if 'progress' in f:
        if f['progress'] not in PROGRESS_VALUES:
            raise HTTPException(422, '进度筛选只允许 pending / done / returned')
        if f['progress'] == 'returned':
            q = q.where(Assessment.returned.is_(True))
        else:
            q = q.where(Assessment.state.in_(progress_states(actor.role.kind, f['progress'])))
    return q


def _json_values(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key:_json_values(item) for key,item in value.items()}
    if isinstance(value, (tuple,list)):
        return [_json_values(item) for item in value]
    return value


def _record_totals(db, sub):
    # The single source for the dashboard KPI totals; comparison() reuses it so
    # 同比/环比 can never drift from the dashboard numbers (7.5 同源同口径).
    return db.execute(select(func.count(),func.coalesce(func.sum(sub.c.income),0),func.coalesce(func.sum(sub.c.hours),0),
        func.coalesce(func.sum(sub.c.participants),0),func.count(distinct(sub.c.teacher_id)),func.count(distinct(sub.c.project_code)),
        func.count(distinct(sub.c.course_code)),func.count(distinct(sub.c.class_code))).select_from(sub)).one()


def stats(db, actor, filters=None):
    f = clean_filters(filters, STAT_FILTERS)
    rq = record_query(db, actor, {k:v for k,v in f.items() if k in RECORD_FILTERS})
    sub = rq.subquery()
    values = _record_totals(db, sub)
    groups = db.execute(select(User.org_id,func.sum(sub.c.income),func.sum(sub.c.participants),func.count(distinct(sub.c.teacher_id)))
        .select_from(sub).join(User,User.id==sub.c.teacher_id).group_by(User.org_id).order_by(func.sum(sub.c.income).desc())).all()
    months = db.execute(select(func.substr(sub.c.event_date,1,7).label('month'),func.sum(sub.c.income),func.sum(sub.c.participants))
        .select_from(sub).group_by('month').order_by('month')).all()
    orgs = {o.id:o for o in db.scalars(select(Org))}
    colleges = {}
    for oid,income,people,teachers in groups:
        o = orgs.get(oid)
        co = orgs.get(o.parent_id) if o and o.kind == 'dept' else o
        if co:
            c = colleges.setdefault(co.id,{'id':co.id,'name':co.name,'income':Decimal(0),'participants':0,'teachers':0})
            c['income'] += income or Decimal(0)
            c['participants'] += people
            c['teachers'] += teachers
    aq = assessment_query(db, actor, f, business_query=rq).subquery()
    # 7.3/7.5 per-college assessment average from the SAME assessment scope as the score bands.
    for oid,count,total in db.execute(select(User.org_id,func.count(aq.c.id),func.sum(aq.c.score)).select_from(aq)
            .join(User,User.id==aq.c.teacher_id).group_by(User.org_id)).all():
        o = orgs.get(oid)
        co = orgs.get(o.parent_id) if o and o.kind == 'dept' else o
        if co and co.id in colleges:
            c = colleges[co.id]
            c['assessment_count'] = c.get('assessment_count',0) + count
            c['assessment_total'] = c.get('assessment_total',Decimal(0)) + Decimal(str(total or 0))
    for c in colleges.values():
        n = c.pop('assessment_count',0); t = c.pop('assessment_total',Decimal(0))
        c['assessment_count'] = n
        c['assessment_average'] = (t/n).quantize(Decimal('0.01')) if n else None
    distribution = db.execute(select(aq.c.state,func.count()).select_from(aq).group_by(aq.c.state)).all()
    score_stats = db.execute(select(
        func.count(aq.c.id),func.avg(aq.c.score),func.min(aq.c.score),func.max(aq.c.score),
        func.sum(case((aq.c.score>=90,1),else_=0)),
        func.sum(case(((aq.c.score>=80)&(aq.c.score<90),1),else_=0)),
        func.sum(case(((aq.c.score>=60)&(aq.c.score<80),1),else_=0)),
        func.sum(case((aq.c.score<60,1),else_=0)),
    ).select_from(aq)).one()
    master_counts={
      'projects':db.scalar(select(func.count()).select_from(TrainingProjectMaster).where(TrainingProjectMaster.active.is_(True))) or 0,
      'courses':db.scalar(select(func.count()).select_from(TrainingCourseMaster).where(TrainingCourseMaster.active.is_(True))) or 0,
      'classes':db.scalar(select(func.count()).select_from(TrainingClassMaster).where(TrainingClassMaster.active.is_(True))) or 0,
    }
    metrics, qualification = db.get(Setting,'metrics'), db.get(Setting,'qualification')
    if metrics is None or qualification is None or not isinstance(metrics.value,dict) or not isinstance(qualification.value,dict) or 'expiry_days' not in qualification.value:
        raise HTTPException(503,'统计初始化配置未就绪')
    return _json_values({'records':values[0],'income':values[1],'hours':values[2],'participants':values[3],'teachers':values[4],
        'projects':values[5],'courses':values[6],'classes':values[7],
        'ranking':[{'org_id':oid,'name':orgs[oid].name,'income':income,'participants':people,'teachers':tc} for oid,income,people,tc in groups],
        'colleges':sorted(colleges.values(),key=lambda x:x['income'],reverse=True),
        'trend':[{'month':m,'income':i,'participants':p} for m,i,p in months],
        'assessment_states':dict(distribution),
        'assessment_score_summary':{'count':score_stats[0],'average':score_stats[1],'minimum':score_stats[2],'maximum':score_stats[3]},
        'assessment_score_bands':[{'label':'90–100分','count':score_stats[4] or 0},{'label':'80–<90分','count':score_stats[5] or 0},{'label':'60–<80分','count':score_stats[6] or 0},{'label':'<60分','count':score_stats[7] or 0}],
        'assessment_scope':{**f,'business_scope':'true'},
        'state_filter_scope':'assessment_only',
        'state_filter_note':'考核环节和退回状态只筛选考核统计；不改变培训营收、授课台账、待办及全校主数据数量',
        'master_data_counts':master_counts,
        'metric_notes':metrics.value,'qualification_warning_days':qualification.value['expiry_days']})


COMPARE_KEYS = ('income','participants','teachers','records','hours','projects','courses','classes')


def _shift_year(d):
    try:
        return d.replace(year=d.year-1)
    except ValueError:
        return d.replace(year=d.year-1, day=28)


def comparison(db, actor, filters=None):
    """7.4/7.5 环比 (previous equal-length window) and 同比 (same window last year).

    All three windows are computed by the same stats() function with the same
    business filters, only the date window differs, so the numbers match the
    dashboard KPIs exactly.  Assessment scores belong to their own period and
    are not compared across windows.
    """
    f = clean_filters(filters, STAT_FILTERS)
    start = end = None
    if 'period_id' in f:
        period = db.get(Period, f['period_id'])
        if period is None:
            raise HTTPException(404, '考核周期不存在')
        start, end = period.start_date, period.end_date
    for key in ('start','end'):
        if key in f:
            if re.fullmatch(r'\d{4}-\d{2}-\d{2}', f[key]) is None:
                raise HTTPException(422, '日期格式应为 YYYY-MM-DD')
            try:
                value = date.fromisoformat(f[key])
            except ValueError:
                raise HTTPException(422, '日期格式应为 YYYY-MM-DD') from None
            start = max(start, value) if key == 'start' and start else value if key == 'start' else start
            end = min(end, value) if key == 'end' and end else value if key == 'end' else end
    if start is None or end is None:
        return {'available': False, 'note': '请选择统计周期，或同时填写开始和结束日期，才能计算环比和同比。'}
    if start > end:
        raise HTTPException(422, '开始日期不能晚于结束日期')
    # 13.7: only the eight KPI totals are compared, so each window runs the one
    # shared totals query instead of the full dashboard (rankings, trend,
    # assessment bands, master counts). Same scope, same SQL, same numbers.
    def totals(window):
        rf = {k: v for k, v in window.items() if k in RECORD_FILTERS}
        values = _record_totals(db, record_query(db, actor, rf).subquery())
        return _json_values(dict(zip(('records','income','hours','participants','teachers','projects','courses','classes'), values)))
    current = totals(f)
    base = {k: v for k, v in f.items() if k not in {'period_id','start','end'}}
    days = (end - start).days + 1
    prev_end = start - timedelta(days=1); prev_start = prev_end - timedelta(days=days-1)
    yoy_start, yoy_end = _shift_year(start), _shift_year(end)
    previous = totals({**base, 'start': prev_start.isoformat(), 'end': prev_end.isoformat()})
    year_ago = totals({**base, 'start': yoy_start.isoformat(), 'end': yoy_end.isoformat()})
    pick = lambda s: {k: s[k] for k in COMPARE_KEYS}
    def change(a, b):
        a, b = Decimal(str(a)), Decimal(str(b))
        return None if b == 0 else str(((a - b) / abs(b) * 100).quantize(Decimal('0.01')))
    cur, prev, yoy = pick(current), pick(previous), pick(year_ago)
    return {'available': True,
            'windows': {'current': {'start': start.isoformat(), 'end': end.isoformat(), 'days': days},
                        'previous': {'start': prev_start.isoformat(), 'end': prev_end.isoformat(), 'days': days},
                        'year_ago': {'start': yoy_start.isoformat(), 'end': yoy_end.isoformat()}},
            'current': cur, 'previous': prev, 'year_ago': yoy,
            'mom': {k: change(cur[k], prev[k]) for k in COMPARE_KEYS},
            'yoy': {k: change(cur[k], yoy[k]) for k in COMPARE_KEYS},
            'note': '三个时间窗口均由同一统计口径计算，仅日期窗口不同；上期为0时不计算百分比。考核得分按各自周期归档，不跨期比较。'}


AUDIT_FILTERS = frozenset({'q','module','result','start','end','actor','org_id','object_id','request_id'})

def audit_query(db, actor, filters=None):
    """Identical date and text semantics for the audit screen and XLSX export."""
    actor.require_admin()
    f = clean_filters(filters, AUDIT_FILTERS)
    q = select(Audit)
    for key in ('module','result'):
        if key in f:
            q = q.where(getattr(Audit, key) == f[key])
    # 12.2 exact filters: operator (user id or login name), organisation, business object, request id.
    if 'actor' in f:
        q = q.where(Audit.actor_id.in_(select(User.id).where((User.id == f['actor']) | (User.username == f['actor']))) | (Audit.actor_id == f['actor']))
    for key in ('org_id','object_id','request_id'):
        if key in f:
            q = q.where(getattr(Audit, key) == f[key])
    if 'q' in f:
        q = q.where(Audit.action.contains(f['q'], autoescape=True)
            | Audit.actor_name.contains(f['q'], autoescape=True) | (Audit.request_id == f['q']))
    bounds = {}
    for key in ('start','end'):
        if key in f:
            try:
                if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', f[key]):
                    raise ValueError('date shape')
                bounds[key] = date.fromisoformat(f[key])
            except ValueError:
                raise HTTPException(422, '日期格式应为 YYYY-MM-DD') from None
    if bounds.get('start', date.min) > bounds.get('end', date.max):
        raise HTTPException(422, '开始日期不能晚于结束日期')
    if 'start' in bounds:
        q = q.where(Audit.created_at >= datetime.combine(bounds['start'], time.min))
    if 'end' in bounds:
        if bounds['end'] == date.max:
            q = q.where(Audit.created_at <= datetime.max)
        else:
            q = q.where(Audit.created_at < datetime.combine(bounds['end'] + timedelta(days=1), time.min))
    return q
