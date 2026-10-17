"""导出上报表：先预检缺项，再导出“项目清单”（每个项目一行，与领导给的项目列表字段一致）和“绩效数据”（全校或本院一条）。

口径（见申报与审批改造总体规划）：
- 只统计已备案及以后的项目（已备案、待学院结项核验、待结项核验、已结项），申报中、被退回的不算。
- 统计区间按上级给的起止日期，培训起止日期与区间有重叠的项目都算；也可以选学年。
- 项目清单的视频时长、基地数量取项目申报时填的数；视频时长没填时用课程视频合计。
- 绩效数据的实践教学基地统计全部已生效基地。
- 能自动算的数不让人填：基地名称、非讲授式占比从系统里算。
"""
from __future__ import annotations
from datetime import date, timedelta
from decimal import Decimal as D
from io import BytesIO
from fastapi import HTTPException
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from sqlalchemy import select
from .models import Org
from .reference_data import TrainingCourseMaster
from .social_models import SocialProject, SocialResource
from .social_schemas import SERVICE_TYPES, TEACHING_METHODS, application_blockers
from . import social_training as st

REPORT_STATES = ('FILED', 'CLOSE_COLLEGE', 'CLOSE_REVIEW', 'CLOSED')
APPLYING = ('DEPT', 'COLLEGE', 'SCHOOL', 'RETURNED', 'WITHDRAWN')
DEFAULT_RANGE = ('2023-07-01', '2026-06-30')
SHEET_12 = '项目清单'
SHEET_PERF = '绩效数据'
COLUMNS_12 = ['序号', '项目名称', '服务面向类型', '总学时', '视频资源总时长（分钟）', '实践教学基地数量（个）', '教学实施方式',
              '项目编号（核对用）', '承办学院（核对用）']
COLUMNS_PERF = ['统计范围', '统计区间', '项目数（个）', '总学时数', '视频资源总时长（分钟）', '实践教学基地数量（个）', '实践教学基地名称',
                '近一年新增培训课程数（门）', '近一年新增视频资源时长（分钟）', '近一年新增实践教学基地数（个）', '非讲授式教学学时占比（%）']


def parse_range(start, end):
    try:
        s, e = date.fromisoformat(start or DEFAULT_RANGE[0]), date.fromisoformat(end or DEFAULT_RANGE[1])
    except ValueError:
        raise HTTPException(422, '统计区间请写成 2023-07-01 这样的日期')
    if s > e or (e - s).days > 3700:
        raise HTTPException(422, '统计区间起止日期不对（开始不能晚于结束，最长 10 年）')
    return s, e


def scope_check(a):
    if a.role.kind not in ('school', 'college'):
        raise HTTPException(403, '上报表由学校导出全校、学院导出本院自查')


def num(value):
    if value in (None, ''):
        return None
    try:
        return D(str(value))
    except Exception:
        return None


def plain(value):
    """Excel 里数字照数字写：整数不带 .0，小数去掉多余的 0。"""
    if value is None:
        return None
    value = D(value)
    return int(value) if value == value.to_integral() else float(value.normalize())


def projects(db, a, start, end):
    rows = db.scalars(select(SocialProject).where(SocialProject.org_id.in_(a.org_ids), SocialProject.state.in_(REPORT_STATES))
                      .order_by(SocialProject.org_id, SocialProject.data['code'].as_string(), SocialProject.cohort)).all()
    out = []
    for p in rows:
        try:
            s, e = date.fromisoformat(p.data.get('start_date')), date.fromisoformat(p.data.get('end_date'))
        except (TypeError, ValueError):
            continue
        if s <= end and e >= start:
            out.append(p)
    return out


def org_names(db, ids):
    return dict(db.execute(select(Org.id, Org.name).where(Org.id.in_(sorted(set(ids)) or ['']))).all())


def course_facts(db, codes):
    """项目课程：课程编号 → (学时、教学方式、课件审查)；以及每门课的视频分钟合计。"""
    codes = sorted(set(codes))
    courses = {}
    if not codes:
        return courses
    for m in db.scalars(select(TrainingCourseMaster).where(TrainingCourseMaster.project_code.in_(codes), TrainingCourseMaster.active == True)):
        courses[m.code] = {'project_code': m.project_code, 'created_at': m.created_at, 'hours': None, 'mode': None, 'courseware': None, 'minutes': D(0), 'recent_minutes': D(0)}
    keys = list(courses)
    for i in range(0, len(keys), 500):
        part = keys[i:i + 500]
        for r in db.scalars(select(SocialResource).where(SocialResource.kind == 'course_apply', SocialResource.state == 'ACTIVE',
                                                         SocialResource.data['course_code'].as_string().in_(part))):
            c = courses[r.data['course_code']]
            c.update(hours=num(r.data.get('hours')), mode=r.data.get('teaching_mode'), courseware=r.data.get('courseware'))
        for r in db.scalars(select(SocialResource).where(SocialResource.kind == 'course_resource', SocialResource.data['course_code'].as_string().in_(part))):
            if r.data.get('resource_type') == 'video' and r.data.get('duration_minutes') not in (None, ''):
                c = courses[r.data['course_code']]
                c['minutes'] += D(str(r.data['duration_minutes']))
                c.setdefault('resources', []).append((r.created_at, D(str(r.data['duration_minutes']))))
    return courses


def project_row(p, courses):
    d = p.data
    mine = [c for c in courses.values() if c['project_code'] == d['code']]
    minutes = sum((c['minutes'] for c in mine), D(0))
    if d.get('video_minutes') not in (None, ''):
        minutes = num(d['video_minutes']) or minutes
    svc = '、'.join(SERVICE_TYPES.get(x, x) for x in d.get('service_types') or [])
    methods = '、'.join(TEACHING_METHODS.get(x, x) for x in d.get('teaching_methods') or [])
    return [d['name'] + ('（' + p.cohort + '）' if p.cohort else ''), svc, plain(num(d.get('total_hours'))), plain(minutes),
            d.get('base_count') if d.get('base_count') is not None else 0, methods, d['code']]


def issues(p):
    return list(application_blockers(p.data))


def check(db, a, start, end):
    scope_check(a)
    s, e = parse_range(start, end)
    rows = projects(db, a, s, e)
    names = org_names(db, [p.org_id for p in rows])
    items = [{'id': p.id, 'name': p.data['name'], 'code': p.data['code'], 'cohort': p.cohort, 'org_name': names.get(p.org_id, ''),
              'state': p.state, 'state_label': st.state_label(p), 'issues': issues(p)} for p in rows]
    blocked = [x for x in items if x['issues']]
    return {'start': s.isoformat(), 'end': e.isoformat(), 'count': len(items), 'blocked': len(blocked), 'ready': bool(items) and not blocked,
            'scope': '全校' if a.role.kind == 'school' else '本院', 'items': blocked + [x for x in items if not x['issues']],
            'note': '只统计已备案及以后的项目；项目清单行数应等于上级 1.1 表填报的项目数（本区间 %d 个）。' % len(items)}


def bases(db, a, end):
    rows = db.scalars(select(SocialResource).where(SocialResource.kind == 'base', SocialResource.org_id.in_(a.org_ids),
                                                    SocialResource.state.notin_([*APPLYING, 'ARCHIVED', 'VOID']))).all()
    out = []
    for b in rows:
        on = b.data.get('established_on')
        try:
            on = date.fromisoformat(on) if on else None
        except ValueError:
            on = None
        if on is None or on <= end:
            out.append((b, on))
    return sorted(out, key=lambda x: (x[1] or date.min, x[0].code))


def performance(db, a, s, e, rows, courses):
    year_ago = e - timedelta(days=365)
    recent = lambda when: when is not None and year_ago < (when.date() if hasattr(when, 'date') else when) <= e
    total_hours = sum((num(p.data.get('total_hours')) or D(0) for p in rows), D(0))
    minutes = sum((c['minutes'] for c in courses.values()), D(0))
    base_rows = bases(db, a, e)
    with_hours = [c for c in courses.values() if c['hours'] is not None]
    lecture_total = sum((c['hours'] for c in with_hours), D(0))
    non_lecture = sum((c['hours'] for c in with_hours if c['mode'] and c['mode'] != 'lecture'), D(0))
    ratio = plain(round(100 * non_lecture / lecture_total, 1)) if lecture_total else '待补充（课程未登记学时和教学方式）'
    recent_minutes = sum((m for c in courses.values() for when, m in c.get('resources', []) if recent(when)), D(0))
    return ['全校' if a.role.kind == 'school' else '本院', s.isoformat() + ' 至 ' + e.isoformat(), len(rows), plain(total_hours), plain(minutes),
            len(base_rows), '；'.join(b.name for b, _ in base_rows) or '无', sum(1 for c in courses.values() if recent(c['created_at'])),
            plain(recent_minutes), sum(1 for _, on in base_rows if recent(on)), ratio]


def export(db, a, start, end):
    result = check(db, a, start, end)
    if not result['count']:
        raise HTTPException(409, '这个区间里没有已备案的项目')
    if not result['ready']:
        raise HTTPException(409, '还有 %d 个项目缺上报信息，请先补齐' % result['blocked'])
    s, e = parse_range(start, end)
    rows = projects(db, a, s, e)
    courses = course_facts(db, [p.data['code'] for p in rows])
    names = org_names(db, [p.org_id for p in rows])
    table = [[i, *project_row(p, courses), names.get(p.org_id, '')] for i, p in enumerate(rows, 1)]
    note = ('说明：总学时、视频时长为区间内项目合计；实践教学基地为已生效的全部基地（不只思政）；“近一年”指统计区间结束日前 365 天；'
            '非讲授式占比 = 教学方式不是“讲授”的课程学时 ÷ 已登记学时的课程学时合计。')
    return {SHEET_12: [COLUMNS_12, *table], SHEET_PERF: [COLUMNS_PERF, performance(db, a, s, e, rows, courses), [], [note]]}, result


def xlsx(sheets):
    book = Workbook()
    book.remove(book.active)
    for title, rows in sheets.items():
        ws = book.create_sheet(title)
        for row in rows:
            ws.append(row)
        for cell in ws[1]:
            cell.font = Font(bold=True)
            cell.alignment = Alignment(wrap_text=True, vertical='center')
        for col in ws.columns:
            ws.column_dimensions[col[0].column_letter].width = 18
        ws.freeze_panes = 'A2'
    buf = BytesIO()
    book.save(buf)
    return buf.getvalue()
