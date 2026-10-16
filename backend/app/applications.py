"""老师发起的申请：培训课程、社会培训课（把本人教务、超星的课申报为社会培训课）、培训基地，以及培训项目的进度。

申请单存在现有的 social_resources 表（kind='course_apply' 或 'base'），不改数据库结构。
审批链、回避、代办、同一人连审和进度显示见 approvals.py。
"""
from __future__ import annotations
import hashlib
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select
from .core import serial, school_today
from .models import User, Org, Setting, Period, PointBalance, PointEntry
from .reference_data import TeacherCourseTerm, TrainingCourseMaster, annual_teaching_credits, school_year_of, school_year_now, term_in_scope, UNKNOWN_YEAR
from .social_models import SocialResource, SocialProject
from .social_schemas import TEACHING_MODES, IDEOLOGY, BASE_USAGES
from . import approvals as ap

APP_KINDS = ('course_apply', 'base')
PENDING_STATES = ('DEPT', 'COLLEGE', 'SCHOOL')
CX_KEYS = ('course_url', 'cover_url', 'chapters', 'team_names', 'group_name', 'course_type', 'jw_course_code')
POINTS_PARAM = 'param:social_course_points'


def flow_of(obj):
    if isinstance(obj, SocialProject):
        return 'project_close' if obj.state in ('CLOSE_COLLEGE', 'CLOSE_REVIEW', 'CLOSED') or obj.data.get('returned_flow') == 'project_close' and obj.state == 'RETURNED' else 'project'
    if obj.kind == 'base':
        return 'base'
    return 'teaching_course' if obj.data.get('source') == 'teaching' else 'course'


def applicant_of(db, obj):
    ident = obj.owner_id if isinstance(obj, SocialProject) else (obj.data or {}).get('teacher_id')
    return db.get(User, ident) if ident else None


def is_application(obj):
    """基地里只有走申请流程的才有审批链；学院以前直接登记的基地视为已生效。"""
    return isinstance(obj, SocialResource) and obj.kind in APP_KINDS and bool((obj.data or {}).get('application'))


def college_for(db, user):
    org = ap.college_of(db, user)
    if org is None or org.kind != 'college':
        raise HTTPException(422, '申请人须属于某个二级学院（或其下的教研室）')
    return org


def resolve_applicant(db, a, teacher_id):
    """老师只能为本人申请；学院、学校有登记权限的账号可以代老师登记，负责人选老师本人。"""
    if a.role.kind == 'teacher' or not teacher_id or teacher_id == a.id:
        if teacher_id and teacher_id != a.id:
            raise HTTPException(403, '老师只能为本人申请')
        if not a.user.staff_no:
            raise HTTPException(403, '账号没有工号，不能申请；请联系学校管理员')
        return a.user
    a.require('records.write')
    return a.check_teacher(db, teacher_id, active=True)


def can_edit(a, obj):
    return obj.state in ('RETURNED', 'WITHDRAWN') and a.id in {obj.data.get('teacher_id'), obj.data.get('created_by')}


def read_check(db, a, obj):
    """申请人、代登记人、本级可办理的人、以及组织范围内的学院和学校可以看。"""
    if not is_application(obj):
        raise HTTPException(404, '申请不存在')
    applicant = applicant_of(db, obj)
    if a.id in {obj.data.get('teacher_id'), obj.data.get('created_by')}:
        return applicant
    if a.role.kind in ('college', 'school') and obj.org_id in a.org_ids:
        return applicant
    if a.role.kind == 'dept' and applicant and applicant.org_id in a.org_ids:
        return applicant
    level = ap.level_of(flow_of(obj), obj.state)
    if level and ap.can_handle(db, a, applicant, level, obj.org_id):
        return applicant
    raise HTTPException(403, '申请超出你的查看范围')


# ---- 社会培训课：老师本人的教务、超星课 ----

def _norm(name):
    return ' '.join(str(name or '').split())


def jw_codes(db, staff_nos=None):
    """{(工号, 教务课号)}：判断超星课是否挂到本人教过的教务课。"""
    q = select(TeacherCourseTerm.staff_no, TeacherCourseTerm.course_code).where(TeacherCourseTerm.origin == 'JW', TeacherCourseTerm.active.is_(True))
    if staff_nos is not None:
        q = q.where(TeacherCourseTerm.staff_no.in_(sorted(staff_nos) or ['']))
    return set(db.execute(q).all())


def course_identity(db, row, jw=None):
    """同一门课只申报一次、只算一次分：教务课按课程号；超星课按课程名（每学期一个超星课号也算同一门），
    挂了本人教过的教务课时按那门教务课算。"""
    link = str((row.extra or {}).get('jw_course_code') or '').strip()
    if row.origin == 'CX':
        if link and (row.staff_no, link) in (jw if jw is not None else jw_codes(db, [row.staff_no])):
            return 'JW|' + link
        return 'CX|' + _norm(row.course_name)
    return 'JW|' + row.course_code


def application_code(teacher_id, identity):
    return 'SC-' + hashlib.sha256((teacher_id + '|' + identity).encode()).hexdigest()[:20].upper()


def teaching_rows(db, user):
    if not user or not user.staff_no:
        return []
    rows = db.scalars(select(TeacherCourseTerm).where(TeacherCourseTerm.staff_no == user.staff_no, TeacherCourseTerm.active.is_(True))
                      .order_by(TeacherCourseTerm.term_name.desc(), TeacherCourseTerm.course_code)).all()
    return [r for r in rows if term_in_scope(r.term_name)]


def course_facts(db, row):
    """这门课的学分、学时（教务课按课程总库补学分），和计分用同一套口径。"""
    peers = db.scalars(select(TeacherCourseTerm).where(TeacherCourseTerm.staff_no == row.staff_no, TeacherCourseTerm.active.is_(True))).all()
    for g in annual_teaching_credits(db, peers):
        for d in g['details']:
            if d['id'] == row.id:
                return {**d, 'school_year': g['school_year']}
    return {'credit': None, 'hours': None, 'school_year': school_year_of(row.term_name) or UNKNOWN_YEAR}


def source_course(db, row):
    facts = course_facts(db, row)
    extra = row.extra or {}
    return {'course_term_id': row.id, 'origin': row.origin, 'origin_label': '教务' if row.origin == 'JW' else '超星',
            'course_code': row.course_code, 'course_name': row.course_name, 'term_name': row.term_name,
            'school_year': facts.get('school_year'), 'credit': facts.get('credit'), 'hours': facts.get('hours'),
            'description': str(extra.get('description') or '')[:2000], **{k: extra.get(k) for k in CX_KEYS if extra.get(k) not in (None, '')}}


def applications_by_code(db, codes):
    codes = sorted(set(codes))
    out = {}
    for i in range(0, len(codes), 500):
        for x in db.scalars(select(SocialResource).where(SocialResource.kind == 'course_apply', SocialResource.code.in_(codes[i:i + 500]))):
            out[x.code] = x
    return out


ONLINE_KEYS = ('cover_url', 'course_url', 'group_name', 'chapters', 'course_type', 'course_source', 'archived', 'team_names', 'team_staff_nos',
               'jw_course_code', 'nature', 'course_owner', 'major', 'period_text', 'created_at_source', 'edited_at_source')


def course_problems(origin, credit):
    if credit is not None:
        return []
    if origin == 'CX':
        return ['超星没填学分：这门课暂不计授课学分。请在超星平台补上，下周同步后自动更新；不影响申报为社会培训课。']
    return ['课程总库里这门课没有学分：暂不计授课学分，请联系教务处核对；不影响申报为社会培训课。']


def app_brief(app):
    return {'id': app.id, 'state': app.state, 'state_label': state_label(app), 'version': app.version} if app else None


def cards_for(db, rows, details, apps_by_code, owner_id):
    """按“同一门课”合成一张卡：教务课按课程号，超星课按课程名；卡里按学期列出。计分仍按学期逐条算。"""
    jw = jw_codes(db, {r.staff_no for r in rows})
    cards = {}
    for r in sorted(rows, key=lambda r: r.term_name, reverse=True):
        ident = course_identity(db, r, jw)
        key = (r.origin, ident)
        d = details.get(r.id, {})
        card = cards.get(key)
        if card is None:
            extra = r.extra or {}
            card = cards[key] = {'identity': ident, 'origin': r.origin, 'id': r.id, 'course_code': r.course_code, 'course_name': r.course_name,
                                 'credit': d.get('credit', r.credit), 'hours': d.get('hours', r.hours), 'description': str(extra.get('description') or '')[:2000],
                                 **{k: extra.get(k) for k in ONLINE_KEYS if extra.get(k) not in (None, '')}, 'terms': [],
                                 'application': app_brief(apps_by_code.get(application_code(owner_id, ident))) if owner_id else None}
        card['terms'].append({'id': r.id, 'term_name': r.term_name, 'school_year': d.get('school_year') or school_year_of(r.term_name) or UNKNOWN_YEAR,
                              'course_code': r.course_code, 'credit': d.get('credit', r.credit), 'hours': d.get('hours', r.hours),
                              'counted': d.get('counted'), 'review': d.get('review')})
    out = list(cards.values())
    for card in out:
        card['problems'] = course_problems(card['origin'], card['credit'])
        card['years'] = sorted({t['school_year'] for t in card['terms']}, reverse=True)
    return out


def my_courses(db, user):
    """“我的课程”：本人 2020-2021 学年以后的教务、超星课。years 是学年学分汇总，courses 是合并后的课程卡，每张带社会培训课申报状态。"""
    rows = teaching_rows(db, user)
    groups = annual_teaching_credits(db, rows) if rows else []
    details = {d['id']: {**d, 'school_year': g['school_year']} for g in groups for d in g['details']}
    jw = jw_codes(db, {user.staff_no}) if rows else set()
    apps = applications_by_code(db, [application_code(user.id, course_identity(db, r, jw)) for r in rows])
    years = [{k: g[k] for k in ('school_year', 'jw_credit', 'cx_credit', 'total_credit', 'hours', 'courses', 'pending_courses', 'pending_credit', 'missing_credit')} for g in groups]
    years.sort(key=lambda y: (y['school_year'] != UNKNOWN_YEAR, y['school_year']), reverse=True)
    return {'years': years, 'courses': cards_for(db, rows, details, apps, user.id), 'school_year_now': school_year_now()}


LIBRARY_STATES = {'missing_credit': '缺学分', 'unapplied': '未申报', 'pending': '审批中', 'active': '已入库'}
STALE_DAYS = 365


def online_library(db, a, school_year='', org_id='', source='', state='', q='', page=1, size=24):
    """在线课程库：教研室看本教研室、学院看本院、学校看全校的超星课。统计、数据质量和课程卡。"""
    from datetime import timedelta
    if a.role.kind == 'teacher':
        raise HTTPException(403, '在线课程库给教研室、学院和学校使用；老师请在“我的课程”查看本人的超星课')
    rows = [r for r in db.scalars(select(TeacherCourseTerm).where(TeacherCourseTerm.origin == 'CX', TeacherCourseTerm.active.is_(True))) if term_in_scope(r.term_name)]
    users = {u.staff_no: u for u in db.scalars(select(User).where(User.staff_no.in_(sorted({r.staff_no for r in rows}) or [''])))}
    orgs = {o.id: o for o in db.scalars(select(Org))}

    def college_of_user(u):
        o = orgs.get(u.org_id) if u else None
        while o is not None and o.kind not in ('college', 'school'):
            o = orgs.get(o.parent_id)
        return o

    def visible(r):
        u = users.get(r.staff_no)
        if a.role.kind == 'school':
            return True
        return u is not None and u.org_id in a.org_ids
    rows = [r for r in rows if visible(r)]
    if school_year:
        rows = [r for r in rows if (school_year_of(r.term_name) or UNKNOWN_YEAR) == school_year]
    if org_id:
        rows = [r for r in rows if (u := users.get(r.staff_no)) is not None and (u.org_id == org_id or (orgs.get(u.org_id) and orgs[u.org_id].parent_id == org_id))]
    by_teacher = {}
    for r in rows:
        by_teacher.setdefault(r.staff_no, []).append(r)
    jw = jw_codes(db, set(by_teacher))
    codes = []
    for staff, items in by_teacher.items():
        u = users.get(staff)
        if u:
            codes += [application_code(u.id, course_identity(db, r, jw)) for r in items]
    apps = applications_by_code(db, codes)
    cards = []
    for staff, items in by_teacher.items():
        u = users.get(staff)
        for card in cards_for(db, items, {}, apps, u.id if u else None):
            college = college_of_user(u)
            card.update(staff_no=staff, teacher_name=u.name if u else (items[0].teacher_name or staff), matched=u is not None,
                        org_name=(orgs[u.org_id].name if u and u.org_id in orgs else ''), college_id=college.id if college else None,
                        college_name=college.name if college else '未对上老师')
            cards.append(card)
    stale_before = (school_today() - timedelta(days=STALE_DAYS)).isoformat()
    for card in cards:
        app = card.get('application')
        card['stale'] = bool(card.get('edited_at_source')) and str(card['edited_at_source'])[:10] < stale_before
        card['library_state'] = 'active' if app and app['state'] == 'ACTIVE' else 'pending' if app and app['state'] in PENDING_STATES else 'missing_credit' if card['credit'] is None else 'unapplied'
    colleges = {}
    for card in cards:
        x = colleges.setdefault(card['college_name'], {'name': card['college_name'], 'self': 0, 'clone': 0, 'other': 0, 'total': 0})
        x['total'] += 1
        x[{'1': 'self', '2': 'clone'}.get(str(card.get('course_source')), 'other')] += 1
    quality = {'missing_credit': sum(c['credit'] is None for c in cards), 'linked_jw': sum(c['identity'].startswith('JW|') for c in cards),
               'stale': sum(c['stale'] for c in cards), 'unmatched': sum(not c['matched'] for c in cards)}
    states = {k: sum(c['library_state'] == k for c in cards) for k in LIBRARY_STATES}
    if source:
        cards = [c for c in cards if str(c.get('course_source')) == source]
    if state:
        cards = [c for c in cards if c['library_state'] == state or (state == 'stale' and c['stale']) or (state == 'unmatched' and not c['matched'])]
    if q:
        cards = [c for c in cards if q in c['course_name'] or q in c['teacher_name'] or q in c['staff_no']]
    cards.sort(key=lambda c: (str(c.get('edited_at_source') or ''), c['course_name']), reverse=True)
    total = len(cards)
    years = sorted({school_year_of(r.term_name) or UNKNOWN_YEAR for r in rows}, reverse=True)
    return {'items': cards[(page - 1) * size: page * size], 'total': total, 'page': page, 'size': size, 'colleges': sorted(colleges.values(), key=lambda x: -x['total']),
            'quality': quality, 'states': states, 'state_labels': LIBRARY_STATES, 'years': years, 'stale_days': STALE_DAYS}


# ---- 状态与详情 ----

def state_label(obj):
    if isinstance(obj, SocialResource) and obj.kind in APP_KINDS:
        if obj.state in ap.LEVEL_STATES:
            return ap.LEVEL_STATES[obj.state]
        return {'RETURNED': '退回补正', 'WITHDRAWN': '已撤回', 'ACTIVE': '已入培训课程库', 'DRAFT': '已生效'}.get(obj.state, obj.state)
    from .social_training import state_label as social_label
    return social_label(obj)


def fields(db, obj):
    d = obj.data
    if obj.kind == 'base':
        rows = [('基地名称', obj.name), ('来源编号', obj.code), ('校内 / 校外', '校内' if d.get('onsite') else '校外'),
                ('基地用途', '、'.join(BASE_USAGES.get(x, x) for x in d.get('usages', [])) or '待补充'),
                ('设立日期', d.get('established_on') or '待补充'), ('共建单位', d.get('partner') or ('—' if d.get('onsite') else '待补充')),
                ('地点', d.get('location') or '待补充'), ('认定依据', d.get('recognition') or '')]
        if d.get('project_id'):
            p = db.get(SocialProject, d['project_id'])
            rows.append(('来源项目', p.data['name'] if p else d['project_id']))
        return rows
    c = d.get('course') or {}
    review = d.get('courseware') or {}
    rows = [('课程名称', obj.name), ('学时', d.get('hours') or '待补充'),
            ('教学方式', TEACHING_MODES.get(d.get('teaching_mode'), '待补充')), ('思政属性', IDEOLOGY.get(d.get('ideology'), '待补充')),
            ('主讲教师', d.get('teacher_name') or ''),
            ('课件审查', ('已审查 · ' + review.get('reviewer', '') + ' · ' + str(review.get('reviewed_on') or '')) if review.get('checked') else '待审查')]
    if d.get('source') == 'teaching':
        rows[1:1] = [('原课程', c.get('origin_label', '') + ' · ' + c.get('course_code', '') + ' · ' + c.get('term_name', '')),
                     ('学分', c.get('credit') or '缺学分')]
        rows.append(('面向对象', d.get('audience') or ''))
        if c.get('course_url'):
            rows.append(('超星课程', c['course_url']))
        if c.get('chapters'):
            rows.append(('章节数', c['chapters']))
    else:
        rows[0:0] = [('课程编号', d.get('code') or '')]
        rows.append(('关联项目', d.get('project_code') or '不关联项目'))
    if d.get('intro'):
        rows.append(('课程简介', d['intro']))
    if d.get('points'):
        p = d['points']
        rows.append(('积分', (p.get('amount') + ' 分，已计入 ' + p.get('period_name', '')) if p.get('state') == 'booked' else '学校尚未设置每门课的分值，设置后补记'))
    return [(k, '' if v is None else str(v)) for k, v in rows]


def permissions(db, a, obj, applicant):
    flow = flow_of(obj)
    level = ap.level_of(flow, obj.state)
    mine = a.id in {obj.data.get('teacher_id'), obj.data.get('created_by')}
    handle = bool(level) and ap.can_handle(db, a, applicant, level, obj.org_id)
    return {'approve': handle, 'return': handle, 'edit': can_edit(a, obj), 'submit': mine and obj.state in ('RETURNED', 'WITHDRAWN'),
            'withdraw': mine and obj.state in PENDING_STATES, 'upload': mine and obj.state in ('RETURNED', 'WITHDRAWN', *PENDING_STATES)}


def detail(db, a, obj):
    from .social_training import evidence
    applicant = read_check(db, a, obj)
    flow = flow_of(obj)
    org = db.get(Org, obj.org_id)
    evs = ap.events(db, 'social_resource', obj.id)
    return {'item': serial(obj), 'flow': flow, 'label': ap.FLOWS[flow]['label'], 'state_label': state_label(obj),
            'applicant': {'id': applicant.id, 'name': applicant.name} if applicant else None, 'org_name': org.name if org else '',
            'fields': fields(db, obj), 'progress': ap.progress(db, flow, obj, applicant, returned_level=obj.data.get('returned_level')),
            'permissions': permissions(db, a, obj, applicant), 'attachments': evidence(db, 'social_resource', obj.id),
            'events': [{'action': e.action, 'actor_name': e.actor_name, 'created_at': e.created_at, 'reason': e.reason,
                        'handling': (e.after or {}).get('handling') or {}} for e in evs]}


def summary(db, obj, applicant=None):
    """“我的申请”列表里一行：名称、类型、进度条文字。"""
    flow = flow_of(obj)
    applicant = applicant or applicant_of(db, obj)
    returned = (obj.data or {}).get('returned_level')
    if isinstance(obj, SocialProject):
        name, kind = obj.data['name'], 'social_project'
    else:
        name, kind = obj.name, 'application'
    p = ap.progress(db, flow, obj, applicant, returned_level=returned)
    return {'type': kind, 'id': obj.id, 'name': name, 'label': ap.FLOWS[flow]['label'], 'state': obj.state,
            'state_label': state_label(obj), 'progress': {k: p[k] for k in ('text', 'headline', 'step', 'total', 'tone', 'needs_applicant')},
            'nodes': [{k: n.get(k) for k in ('label', 'state')} for n in p['nodes']], 'updated_at': last_event_at(db, obj) or obj.created_at}


def last_event_at(db, obj):
    from .models import WorkflowEvent
    from sqlalchemy import func
    kind = 'social_project' if isinstance(obj, SocialProject) else 'social_resource'
    return db.scalar(select(func.max(WorkflowEvent.created_at)).where(WorkflowEvent.object_type == kind, WorkflowEvent.object_id == obj.id))


# ---- 生效 ----

def open_period(db):
    today = school_today()
    return db.scalar(select(Period).where(Period.state == 'OPEN', Period.start_date <= today, Period.end_date >= today).order_by(Period.start_date.desc()).limit(1))


def points_value(db):
    obj = db.get(Setting, POINTS_PARAM)
    value = (obj.value or {}).get('value') if obj else None
    try:
        return Decimal(str(value)) if value not in (None, '') else None
    except Exception:
        return None


def book_points(db, a, obj):
    """社会培训课入库后按学校设置的每门课分值给本人记积分；没设置分值的先记“待补记”。同一门课只记一次。"""
    value = points_value(db)
    period = open_period(db)
    if value is None or value <= 0 or period is None:
        obj.data = {**obj.data, 'points': {'state': 'pending', 'note': '学校尚未设置每门社会培训课的分值' if value is None else '当前没有进行中的考核周期'}}
        return None
    key = 'social_course_' + obj.code
    if db.scalar(select(PointEntry.id).where(PointEntry.item_key == key, PointEntry.teacher_id == obj.data['teacher_id'])):
        return None
    balance = db.scalar(select(PointBalance).where(PointBalance.teacher_id == obj.data['teacher_id'], PointBalance.period_id == period.id))
    if balance and balance.confirmed:
        obj.data = {**obj.data, 'points': {'state': 'pending', 'note': '本周期积分已确认，须先解锁后补记'}}
        return None
    if not balance:
        balance = PointBalance(teacher_id=obj.data['teacher_id'], period_id=period.id)
        db.add(balance); db.flush()
    db.add(PointEntry(teacher_id=obj.data['teacher_id'], period_id=period.id, item_key=key, kind='SOCIAL', amount=value, raw_value=str(value),
                      formula='学历课申报为社会培训课，经教研室、学院、学校遴选入库，每门 ' + str(value) + ' 分',
                      source_snapshot={'social_course': obj.id, 'course': obj.data.get('course'), 'rule': {'name': '社会培训课程积分（学校设置的每门分值）'}},
                      actor_id=a.id, reason='社会培训课入库', basis=obj.code))
    balance.version += 1
    obj.data = {**obj.data, 'points': {'state': 'booked', 'amount': str(value), 'period_id': period.id, 'period_name': period.name}}
    return value


def complete(db, a, obj, flow):
    today = school_today().isoformat()
    if flow in ('course', 'teaching_course'):
        code = obj.data.get('code') if flow == 'course' else obj.code
        existing = db.scalar(select(TrainingCourseMaster).where(TrainingCourseMaster.code == code))
        if existing is not None and existing.active:
            raise HTTPException(409, '培训课程库里已有编号 ' + code + ' 的课程，请核对后退回')
        if existing is None:
            db.add(TrainingCourseMaster(code=code, name=obj.name, project_code=obj.data.get('project_code') or None,
                                        source='学历课申报为社会培训课' if flow == 'teaching_course' else '老师申请'))
        else:
            existing.active = True; existing.name = obj.name; existing.version += 1
        obj.data = {**obj.data, 'effective_on': today, 'course_code': code}
        if flow == 'teaching_course':
            book_points(db, a, obj)
    else:
        obj.data = {**obj.data, 'effective_on': today}


# ---- 待办 ----

def todo_items(db, a):
    """要我处理：本级可办的申请，以及本人被退回待补正的申请。"""
    items = []
    rows = db.scalars(select(SocialResource).where(SocialResource.kind.in_(APP_KINDS), SocialResource.state.in_([*PENDING_STATES, 'RETURNED']))).all()
    for obj in rows:
        if not is_application(obj):
            continue
        flow = flow_of(obj)
        applicant = applicant_of(db, obj)
        if obj.state == 'RETURNED':
            if a.id in {obj.data.get('teacher_id'), obj.data.get('created_by')}:
                items.append({'type': 'application', 'id': obj.id, 'title': '补正后重新提交：' + ap.FLOWS[flow]['label'] + ' · ' + obj.name,
                              'state': 'RETURNED', 'teacher_id': obj.data.get('teacher_id'), 'target_id': None})
            continue
        level = ap.level_of(flow, obj.state)
        if not level or a.role.kind == 'teacher' and level != 'school':
            continue
        try:
            handling = ap.check_handler(db, a, applicant, level, obj.org_id)
        except HTTPException:
            continue
        hint = '（' + handling['acting_for'] + '）' if handling.get('acting_for') else ''
        items.append({'type': 'application', 'id': obj.id, 'title': ap.FLOWS[flow]['label'] + '：' + obj.name + hint,
                      'state': state_label(obj), 'teacher_id': obj.data.get('teacher_id'), 'target_id': None,
                      'same_person': ap.SAME_PERSON if ap.same_person(db, 'social_resource', obj.id, a) else None})
    return items + project_todos(db, a)


def project_todos(db, a):
    """培训项目：学院这一级可办的申请和结项核验；老师本人被退回待补正的项目。"""
    items = []
    for p in db.scalars(select(SocialProject).where(SocialProject.state.in_(['COLLEGE', 'CLOSE_COLLEGE', 'RETURNED']))):
        if p.state == 'RETURNED':
            if a.role.kind == 'teacher' and p.owner_id == a.id:
                items.append({'type': 'social_project', 'id': p.id, 'title': '补正后重新提交：' + p.data['name'], 'state': '退回补正', 'teacher_id': a.id, 'target_id': None})
            continue
        if a.role.kind != 'college' or p.org_id not in a.org_ids:
            continue
        owner = db.get(User, p.owner_id)
        try:
            handling = ap.check_handler(db, a, owner, 'college', p.org_id)
        except HTTPException:
            continue
        hint = '（' + handling['acting_for'] + '）' if handling.get('acting_for') else ''
        items.append({'type': 'social_project', 'id': p.id, 'title': ('项目学院审批：' if p.state == 'COLLEGE' else '项目学院结项核验：') + p.data['name'] + hint,
                      'state': state_label(p), 'teacher_id': p.owner_id, 'target_id': None})
    return items


def mine(db, a):
    """我的申请：本人是申请人或代登记人的申请，以及本人负责的培训项目。"""
    out = []
    resources = db.scalars(select(SocialResource).where(SocialResource.kind.in_(APP_KINDS))).all()
    for obj in resources:
        if is_application(obj) and a.id in {obj.data.get('teacher_id'), obj.data.get('created_by')}:
            out.append(summary(db, obj))
    for p in db.scalars(select(SocialProject).where(SocialProject.owner_id == a.id)):
        out.append(summary(db, p))
    out.sort(key=lambda x: str(x['updated_at'] or ''), reverse=True)
    counts = {'pending': sum(x['progress']['tone'] == 'blue' for x in out), 'returned': sum(x['state'] == 'RETURNED' for x in out),
              'done': sum(x['progress']['tone'] == 'green' for x in out), 'draft': sum(x['state'] in ('DRAFT', 'WITHDRAWN') and x['progress']['tone'] == 'gray' for x in out)}
    return {'items': out, 'counts': counts}
