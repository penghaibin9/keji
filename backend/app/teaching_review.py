"""授课认定三级审批：教研室审核 → 学院审批 → 学校认定。

教务、超星同步来的每门课自动进入“待教研室审核”，不用老师提交。每门课按学时算建议积分
（学时 × 每学时积分，没设按 1 学时 1 分），教研室、学院、学校每一级都可以改积分，改了必须写审批意见。
学校认定后积分记入老师课程学期所在考核周期的个人积分（类型“授课认定”），这门课同时进入老师的培训课程库，
不用关联培训项目。

谁来办（沿用培训课程申报的规则）：
- 教研室一级由老师所在教研室负责人办；没有教研室或负责人缺位、负责人就是老师本人，交学院办理，学院一次办两级。
- 学院一级由院长办，院长指定的经办人也能办；院长缺位或院长本人的课交学校。
- 学校一级由授课认定人（以及学校层面有考核审核权限的账号）办；本人的课须回避。
- 没有本地账号的工号不知道所在教研室，直接到学校。

不改数据库结构：办到哪一级、每一步谁办、积分怎么改，都记在已有的认定记录（SocialResource）里。
学分学时在源头被改，这门课自动从教研室重新开始，已入账积分在下次办理时冲销。
"""
from __future__ import annotations
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from types import SimpleNamespace
from fastapi import HTTPException
from sqlalchemy import select
from .models import User, Period, PointEntry, PointBalance, utcnow
from .core import serial, audit, archive_exists
from .social_models import SocialResource
from .identities import stage_handler, org_heads, org_map, VACANCY_LABEL, check_not_principal, agent_item
from .reference_data import (TeacherCourseTerm, CREDIT_REVIEW_KIND, TEACHING_STAGES, credit_review_code, credit_reviews,
                             annual_teaching_credits, can_review_credits, term_anchor, teaching_point_rates)

LEVEL_NAME = {'dept': '教研室', 'college': '学院', 'school': '学校'}
STEP_LABEL = {'approve': '通过', 'exclude': '不计分', 'return': '退回', 'reset': '改回重审', 'restart': '学分学时变化，重新审核'}
MAX_POINTS = Decimal('1000')


def effective_level(db, teacher, stage, heads=None, orgs=None):
    """这一级实际由哪一级办，和代办说明：教研室缺位交学院、学院缺位交学校。"""
    if stage == 'school' or teacher is None:
        return 'school', None
    kind, vacant = stage_handler(db, teacher, 'DEPARTMENT' if stage == 'dept' else 'COLLEGE', heads, orgs)
    return kind, VACANCY_LABEL.get(vacant)


def next_stage(level):
    i = TEACHING_STAGES.index(level)
    return TEACHING_STAGES[i + 1] if i + 1 < len(TEACHING_STAGES) else None


def _review_kind(actor):
    """教研室、学院负责人（含院长指定的经办人）以负责人身份办理；其他身份返回 None。"""
    if actor.role.kind in ('dept', 'college') and 'assessment.review' in actor.permissions:
        return actor.role.kind
    return None


def _own(actor, teacher, staff_no):
    return (teacher is not None and teacher.id == actor.id) or bool(actor.user.staff_no and staff_no == actor.user.staff_no)


def check_level(db, actor, teacher, staff_no, level):
    """确认 actor 能办这门课的这一级，不能办直接拒绝。"""
    from . import social_training as st
    if _own(actor, teacher, staff_no):
        raise HTTPException(403, '须回避本人的课，由其他人办理')
    if level == 'school':
        if not can_review_credits(db, actor):
            raise HTTPException(403, '这门课现在待学校认定，由学校指定的授课认定人办理')
        if teacher is not None:
            st.check_conflicts(db, actor, teacher.id)
        return
    if _review_kind(actor) != level:
        raise HTTPException(403, '这门课现在待' + LEVEL_NAME[level] + '办理，由' + LEVEL_NAME[level] + '负责人办理，不能越级')
    if teacher is None or teacher.org_id not in actor.org_ids:
        raise HTTPException(403, '这位老师不在你负责的' + LEVEL_NAME[level])
    check_not_principal(db, actor, teacher.id)
    st.check_conflicts(db, actor, teacher.id)


def can_act(db, actor, teacher, staff_no, level):
    try:
        check_level(db, actor, teacher, staff_no, level)
        return True
    except HTTPException:
        return False


def _users(db, ids):
    ids = sorted({i for i in ids if i})
    out = {}
    for i in range(0, len(ids), 500):
        out.update({u.id: u for u in db.execute(select(User.id, User.org_id, User.name).where(User.id.in_(ids[i:i + 500])))})
    return out


def waiting_for(db, actor, groups):
    """老师学年里等 actor 办理的课：教研室、学院负责人看本组织老师在本级的课，学校看到学校这一级的课。"""
    school = can_review_credits(db, actor)
    kind = _review_kind(actor)
    if not school and not kind:
        return []
    candidates = [g for g in groups if any((g.get('waiting') or {}).values())]
    if not candidates:
        return []
    users = _users(db, [g.get('user_id') for g in candidates])
    heads, orgs = org_heads(db), org_map(db)
    out = []
    for g in candidates:
        teacher = users.get(g.get('user_id'))
        if _own(actor, teacher, g['staff_no']):
            continue
        n = 0
        for stage, count in (g.get('waiting') or {}).items():
            if not count:
                continue
            level, _ = effective_level(db, teacher, stage, heads, orgs)
            if level == 'school' and school:
                n += count
            elif level == kind and teacher is not None and teacher.org_id in actor.org_ids:
                n += count
        if n:
            out.append({**g, 'mine_courses': n})
    return out


def annotate(db, actor, group):
    """单个老师学年的明细：每门课实际在哪一级、谁在办、当前账号能不能办。"""
    teacher = db.get(User, group['user_id']) if group.get('user_id') else None
    heads, orgs = org_heads(db), org_map(db)
    for d in group.get('details', []):
        if d.get('review') != 'pending' or not d.get('counted'):
            d.update(handler=None, handler_label=None, acting_for=None, can_act=False)
            continue
        level, acting = effective_level(db, teacher, d['stage'], heads, orgs)
        d.update(handler=level, handler_label='待' + LEVEL_NAME[level] + ('认定' if level == 'school' else '审核' if level == 'dept' else '审批'),
                 acting_for=acting, can_act=can_act(db, actor, teacher, group['staff_no'], level))
    group['can_return'] = can_review_credits(db, actor) and not _own(actor, teacher, group['staff_no'])
    return group


def _points(value, field='积分'):
    if value is None or value == '':
        return None
    try:
        out = Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        raise HTTPException(422, field + '必须是数字')
    if out < 0 or out > MAX_POINTS:
        raise HTTPException(422, field + '应在 0 到 %s 之间' % MAX_POINTS)
    return out


def _period_for(db, anchor):
    if anchor is None:
        return None
    return db.scalar(select(Period).where(Period.start_date <= anchor, Period.end_date >= anchor).order_by(Period.start_date.desc(), Period.id).limit(1))


def _balance(db, teacher_id, period):
    if archive_exists(db, teacher_id, period.id):
        raise HTTPException(409, '这门课所在的考核周期“' + period.name + '”已归档，积分不能再变动，请走积分更正')
    bal = db.scalar(select(PointBalance).where(PointBalance.teacher_id == teacher_id, PointBalance.period_id == period.id).with_for_update())
    if bal and bal.confirmed:
        raise HTTPException(409, '老师在考核周期“' + period.name + '”的积分已确认，须先留痕解锁再认定')
    if bal is None:
        bal = PointBalance(teacher_id=teacher_id, period_id=period.id, confirmed=False, version=1)
        db.add(bal)
        db.flush()
    return bal


def book(db, actor, row, teacher, fact, points, steps, reason):
    """学校认定后把积分记入课程学期所在的考核周期。返回入账信息；记不了时说明原因（不阻止认定）。"""
    if teacher is None:
        return {'booked': False, 'note': '工号没有本地账号，积分暂未入账'}
    period = _period_for(db, term_anchor(fact['school_year'], fact['term_no']))
    if period is None:
        return {'booked': False, 'note': '还没有覆盖这个学期的考核周期，积分暂未入账'}
    bal = _balance(db, teacher.id, period)
    entry = PointEntry(teacher_id=teacher.id, period_id=period.id, item_key=('teach_' + row.id)[:64], kind='TEACHING', amount=points,
                       raw_value=str(fact['hours'] if fact['hours'] is not None else ''),
                       formula='授课认定：%s 学时，建议 %s 分，学校认定 %s 分' % (fact['hours'] or '—', fact['suggested_points'] or '—', points),
                       source_snapshot={'teaching_course': row.id, 'course': row.course_name, 'course_code': row.course_code, 'origin': row.origin,
                                        'term_name': row.term_name, 'basis': fact['basis'], 'steps': steps},
                       actor_id=actor.id, reason=reason or '学校认定计分', basis='教研室、学院、学校三级认定')
    db.add(entry)
    db.flush()
    bal.version += 1
    return {'booked': True, 'entry_id': entry.id, 'period_id': period.id, 'period_name': period.name, 'amount': str(points)}


def unbook(db, actor, row, booked, reason):
    """冲销已入账的授课认定积分：追加一条反向积分，原记录保留。"""
    if not booked or not booked.get('booked'):
        return
    period = db.get(Period, booked['period_id'])
    if period is None:
        return
    teacher_id = db.scalar(select(PointEntry.teacher_id).where(PointEntry.id == booked['entry_id']))
    if teacher_id is None:
        return
    bal = _balance(db, teacher_id, period)
    amount = Decimal(str(booked['amount']))
    db.add(PointEntry(teacher_id=teacher_id, period_id=period.id, item_key=('teach_' + row.id)[:64], kind='TEACHING', amount=-amount,
                      raw_value='', formula='冲销授课认定积分 %s 分' % amount, source_snapshot={'teaching_course': row.id, 'reverses': booked['entry_id']},
                      actor_id=actor.id, reason=reason or '授课认定改回重审', basis='授课认定改回或学分学时变化'))
    db.flush()
    bal.version += 1


def _facts(db, rows):
    staff = {r.staff_no for r in rows}
    peers = db.scalars(select(TeacherCourseTerm).where(TeacherCourseTerm.active.is_(True), TeacherCourseTerm.staff_no.in_(staff)))
    out = {}
    for g in annual_teaching_credits(db, peers):
        for d in g['details']:
            out[d['id']] = {**d, 'school_year': g['school_year']}
    return out


def apply_review(db, actor, data):
    """办理一批课：approve 通过（学校一级即认定计分）、exclude 不计分、return 学校退回、reset 学校改回重审。"""
    from .reference_data import credit_basis
    items = {x.id: x for x in (data.items or [])}
    ids = list(dict.fromkeys([*data.ids, *items]))
    if not ids:
        raise HTTPException(422, '请先选择课程')
    rows = {r.id: r for r in db.scalars(select(TeacherCourseTerm).where(TeacherCourseTerm.id.in_(ids)).with_for_update())}
    missing = [i for i in ids if i not in rows or not rows[i].active]
    if missing:
        raise HTTPException(409, '有 %d 门课已不在当前授课数据里，请刷新后重试' % len(missing))
    if data.decision == 'return' and data.return_to not in ('dept', 'college'):
        raise HTTPException(422, '请选择退回到教研室还是学院')
    facts = _facts(db, list(rows.values()))
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_({r.user_id for r in rows.values() if r.user_id} or {''})))}
    heads, orgs = org_heads(db), org_map(db)
    reviews = credit_reviews(db, ids)
    at = utcnow().isoformat(timespec='seconds')
    agent = bool(agent_item(db, actor))
    done = 0
    labels = []
    for i in ids:
        r = rows[i]
        d = facts.get(i)
        if d is None or not d['counted']:
            raise HTTPException(409, r.course_name + ' 是重复课程，已按规则只算一次，不用认定')
        teacher = users.get(r.user_id)
        item = items.get(i)
        reason = ((item.reason if item and item.reason else '') or data.reason or '').strip()
        basis = credit_basis(r, d['credit'] if d['credit'] is None else Decimal(d['credit']), d['hours'] if d['hours'] is None else Decimal(d['hours']))
        obj = reviews.get(i)
        before = serial(obj) if obj else {}
        old = dict(obj.data or {}) if obj else {}
        current = obj is not None and old.get('basis') == basis
        steps = list(old.get('steps') or []) if current else []
        history = list(old.get('history') or [])
        booked = old.get('booked')
        if obj is not None and not current and booked and booked.get('booked'):
            # 学分学时在源头变了：先冲掉按旧依据入账的积分，从教研室重新开始。
            unbook(db, actor, r, booked, '学分学时变化，冲销后重新认定')
            booked = None
            history.append({'decision': 'restart', 'by': actor.id, 'by_name': actor.name, 'at': at, 'reason': '学分学时变化，从教研室重新审核'})
        points_now = _points(d['points']) if d['points'] is not None else None
        entry = {'by': actor.id, 'by_name': actor.name, 'at': at, 'reason': reason, 'agent': agent or None}
        state = obj.state if obj is not None and current else 'PENDING'
        stage = d['stage']
        if data.decision == 'reset':
            if not can_review_credits(db, actor) or _own(actor, teacher, r.staff_no):
                raise HTTPException(403, '改回重审由学校授课认定人办理' if not _own(actor, teacher, r.staff_no) else '须回避本人的课，由其他人办理')
            if len(reason) < 2:
                raise HTTPException(422, '改回重审请写明原因')
            if d['review'] == 'pending' and stage == 'dept' and not steps:
                continue
            unbook(db, actor, r, booked, reason)
            booked = None
            entry.update(level='school', decision='reset', points_before=str(points_now) if points_now is not None else None)
            history.append(entry)
            state, stage, steps = 'PENDING', 'dept' if r.user_id else 'school', []
            points_after = None
        else:
            if d['review'] != 'pending':
                raise HTTPException(409, r.course_name + ' 已' + ('认定计分' if d['review'] == 'approved' else '认定不计分') + '，要重新审核请学校先“改回重审”')
            level, acting = effective_level(db, teacher, stage, heads, orgs)
            entry.update(acting_for=acting)
            if data.decision == 'return':
                check_level(db, actor, teacher, r.staff_no, 'school')
                if level != 'school':
                    raise HTTPException(409, r.course_name + ' 还没到学校，不能退回')
                if len(reason) < 2:
                    raise HTTPException(422, '退回请写明原因')
                target, _ = effective_level(db, teacher, data.return_to, heads, orgs)
                if target == 'school':
                    raise HTTPException(409, r.course_name + ' 的' + LEVEL_NAME[data.return_to] + '没有可办理的负责人，不能退回')
                entry.update(level='school', decision='return', return_to=data.return_to, points_before=str(points_now) if points_now is not None else None)
                stage = data.return_to
                points_after = points_now
            else:
                check_level(db, actor, teacher, r.staff_no, level)
                if data.decision == 'exclude':
                    if len(reason) < 2:
                        raise HTTPException(422, '不计分请写明原因')
                    entry.update(level=level, decision='exclude', points_before=str(points_now) if points_now is not None else None, points_after='0')
                    state = 'EXCLUDED'
                    points_after = points_now
                else:
                    points_after = _points(item.points, r.course_name + ' 的积分') if item is not None and item.points is not None else points_now
                    if points_after is None:
                        raise HTTPException(409, r.course_name + ' 缺学时，算不出建议积分，请填写积分后再办理')
                    if points_now is not None and points_after != points_now and len(reason) < 2:
                        raise HTTPException(422, r.course_name + ' 改了积分（%s → %s），请在审批意见里写明原因' % (points_now, points_after))
                    entry.update(level=level, decision='approve', points_before=str(points_now) if points_now is not None else None, points_after=str(points_after))
                    if any(s.get('decision') == 'approve' and s.get('by') == actor.id for s in steps):
                        entry['same_person'] = True
                    nxt = next_stage(level)
                    if nxt is None:
                        state = 'APPROVED'
                    else:
                        stage = nxt
            steps.append({k: v for k, v in entry.items() if v not in (None, '')})
            history.append({k: v for k, v in entry.items() if v not in (None, '')})
        if obj is None:
            obj = SocialResource(org_id=teacher.org_id if teacher else actor.org.id, kind=CREDIT_REVIEW_KIND, code=credit_review_code(i),
                                 name=r.course_name[:160], state=state, data={})
            db.add(obj)
        else:
            obj.version += 1
        if state == 'APPROVED':
            booked = book(db, actor, r, teacher, {**d, 'basis': basis}, points_after, steps, reason)
        obj.state = state
        obj.data = {'course_term_id': i, 'external_key': r.external_key, 'staff_no': r.staff_no, 'teacher_id': r.user_id, 'basis': basis,
                    'stage': stage if state == 'PENDING' else None, 'suggested': d['suggested_points'],
                    'points': str(points_after) if points_after is not None else None, 'steps': steps[-30:], 'history': history[-100:],
                    'booked': booked, 'reason': reason, 'by': actor.id, 'by_name': actor.name, 'at': at}
        db.flush()
        label = {'approve': '认定计分' if state == 'APPROVED' else LEVEL_NAME.get(entry.get('level'), '') + '通过',
                 'exclude': '认定不计分', 'return': '学校退回' + LEVEL_NAME.get(data.return_to or '', ''), 'reset': '改回重审'}[data.decision]
        labels.append(label)
        audit(db, actor, 'teacher_course', i, '授课认定：' + label, before=before, after=serial(obj), reason=reason or label)
        done += 1
    return {'updated': done, 'unchanged': len(ids) - done, 'decision': data.decision}


def library(db, teacher):
    """老师培训课程库里“授课认定入库”的课：学校已认定计分的教务、超星课。"""
    if teacher is None or not teacher.staff_no:
        return []
    rows = db.scalars(select(TeacherCourseTerm).where(TeacherCourseTerm.staff_no == teacher.staff_no, TeacherCourseTerm.active.is_(True))).all()
    out = []
    for g in annual_teaching_credits(db, rows):
        for d in g['details']:
            if d['review'] == 'approved':
                last = (d.get('steps') or [{}])[-1]
                out.append({'id': d['id'], 'course_name': d['course_name'], 'course_code': d['course_code'], 'origin': d['origin'],
                            'school_year': g['school_year'], 'term_name': d['term_name'], 'hours': d['hours'], 'credit': d['credit'],
                            'points': d['points'], 'approved_at': last.get('at'), 'approved_by': last.get('by_name'), 'booked': d.get('booked')})
    return out
