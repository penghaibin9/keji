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
from sqlalchemy import select, case
from .models import User, Period, PointEntry, PointBalance, utcnow
from .core import serial, audit, archive_exists
from .social_models import SocialResource
from .identities import stage_handler, org_heads, org_map, VACANCY_LABEL, check_not_principal, agent_item
from .reference_data import (TeacherCourseTerm, CREDIT_REVIEW_KIND, TEACHING_STAGES, TEACHER_APPLY, credit_review_code, credit_reviews,
                             annual_teaching_credits, can_review_credits, term_anchor, teaching_point_rates)

LEVEL_NAME = {'teacher': '老师', 'dept': '教研室', 'college': '学院', 'school': '学校'}
STEP_LABEL = {'apply': '申请认定', 'withdraw': '撤回申请', 'approve': '通过', 'exclude': '不计分', 'return': '退回', 'reset': '改回重审', 'restart': '学分学时变化，重新审核'}
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


HR_MISSING = '工号在学校教职工表里没有有效记录，不能认定计分；请人事信息补齐后再认定'


def in_staff_table(db, staff_no):
    """和授课学分取数同一条件：教职工表里有这个工号、且在职（active）。"""
    from .reference_data import TeacherHrProfile
    return bool(staff_no) and db.scalar(select(TeacherHrProfile.id).where(TeacherHrProfile.staff_no == staff_no,
                                                                          TeacherHrProfile.active.is_(True)).limit(1)) is not None


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
    candidates = [g for g in groups if any(v for k, v in (g.get('waiting') or {}).items() if k != TEACHER_APPLY)]
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
            if not count or stage == TEACHER_APPLY:
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
    owner = teacher is not None and teacher.id == actor.id
    for d in group.get('details', []):
        d.update(can_apply=False, can_withdraw=False)
        if d.get('review') != 'pending' or not d.get('counted'):
            d.update(handler=None, handler_label=None, acting_for=None, can_act=False)
            continue
        if d['stage'] == TEACHER_APPLY:
            d.update(handler='teacher', handler_label='待老师申请' if teacher is not None else '待老师申请（还没有本地账号）',
                     acting_for=None, can_act=False, can_apply=owner)
            continue
        d['can_withdraw'] = owner and d['stage'] == 'dept' and all(x.get('level') == 'teacher' for x in d.get('steps') or [])
        level, acting = effective_level(db, teacher, d['stage'], heads, orgs)
        if level == 'school' and not in_staff_table(db, group['staff_no']):
            d['blocked_reason'] = HR_MISSING
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
    # 覆盖这个学期的周期有好几个时（例如已关闭的试验周期和新建的正式周期日期重叠），优先记入开放的周期。
    return db.scalar(select(Period).where(Period.start_date <= anchor, Period.end_date >= anchor)
                     .order_by(case((Period.state == 'OPEN', 0), else_=1), Period.start_date.desc(), Period.id).limit(1))


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


def unbook_withdrawn(db, actor, rows, reason='源头已撤下这门课，自动冲销授课认定积分'):
    """源头（教务、超星全量对账或整批撤销）停用了课程学期时，自动冲销它已入账的授课认定积分。

    原入账保留，追加一条反向积分；认定记录改为“已撤下”，留一条办理记录。老师当期考核已归档的不冲销，
    仍由 stale_entries 拦住后续确认、交学校更正。返回冲销了的 {课程学期编号: 分值}。"""
    rows = [r for r in rows if r is not None and not r.active]
    if not rows:
        return {}
    done = {}
    reviews = credit_reviews(db, [r.id for r in rows])
    for r in rows:
        obj = reviews.get(r.id)
        booked = (obj.data or {}).get('booked') if obj is not None else None
        if not booked or not booked.get('booked'):
            continue
        teacher_id = db.scalar(select(PointEntry.teacher_id).where(PointEntry.id == booked['entry_id']))
        if teacher_id is None or archive_exists(db, teacher_id, booked['period_id']):
            continue
        before = serial(obj)
        unbook(db, actor, r, booked, reason)
        data = dict(obj.data or {})
        history = list(data.get('history') or [])
        history.append({'decision': 'withdrawn', 'by': actor.id, 'by_name': actor.name, 'at': utcnow().isoformat(timespec='seconds'), 'reason': reason})
        data.update(booked=None, history=history, withdrawn=True)
        obj.data = data
        obj.version += 1
        db.flush()
        audit(db, actor, 'teacher_course', r.id, '源头撤课，冲销授课认定积分', before=before, after=serial(obj), reason=reason)
        done[r.id] = booked.get('amount')
    return done


def stale_entries(db, teacher_id, period_id):
    """仍有效（没被冲销）的授课认定入账里，所依据课程的学分学时已变或课已撤下的那些。

    冲销流水在 source_snapshot.reverses 里记着它冲的是哪条原入账，按这条关联认冲销，不看净额或最后一条，
    多次重审也不会误判。依据用入账时记下的 basis（工号、来源、课号、学期、学分、学时）和现在重新算出的比，
    课程名称等无关字段变了不算。
    """
    from .reference_data import credit_basis
    entries = db.scalars(select(PointEntry).where(PointEntry.teacher_id == teacher_id, PointEntry.period_id == period_id,
                                                  PointEntry.kind == 'TEACHING').order_by(PointEntry.id)).all()
    reversed_ids = {(e.source_snapshot or {}).get('reverses') for e in entries} - {None}
    live = [e for e in entries if 'reverses' not in (e.source_snapshot or {}) and e.id not in reversed_ids
            and (e.source_snapshot or {}).get('teaching_course') and (e.source_snapshot or {}).get('basis')]
    if not live:
        return []
    ids = {e.source_snapshot['teaching_course'] for e in live}
    rows = {r.id: r for r in db.scalars(select(TeacherCourseTerm).where(TeacherCourseTerm.id.in_(ids)))}
    facts = _facts(db, [r for r in rows.values() if r.active])
    out = []
    for e in live:
        snap = e.source_snapshot
        r = rows.get(snap['teaching_course'])
        d = facts.get(r.id) if r is not None and r.active else None
        if d is None or not d['counted']:
            now = None
        else:
            now = credit_basis(r, None if d['credit'] is None else Decimal(d['credit']), None if d['hours'] is None else Decimal(d['hours']))
        if now == snap['basis']:
            continue
        old_hours = (snap['basis'] or {}).get('hours')
        out.append({'entry_id': e.id, 'course_term_id': snap['teaching_course'], 'course': snap.get('course') or (r.course_name if r else ''),
                    'course_code': snap.get('course_code'), 'amount': str(e.amount),
                    'before': '%s 学时' % old_hours if old_hours else '入账时的学分学时',
                    'after': ('%s 学时' % now['hours'] if now and now.get('hours') else '学分学时已变化') if now else '课程已撤下或不再计入'})
    return out


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
        points_after = points_now
        if data.decision in ('apply', 'withdraw'):
            if teacher is None or teacher.id != actor.id:
                raise HTTPException(403, '课程认定积分由任课老师本人申请或撤回')
            if d['review'] != 'pending':
                raise HTTPException(409, r.course_name + ' 已' + ('认定计分' if d['review'] == 'approved' else '认定不计分') + '，不用再申请')
            if data.decision == 'apply':
                if stage != TEACHER_APPLY:
                    raise HTTPException(409, r.course_name + ' 已经申请过，正在审核中')
                if points_now is None and len(reason) < 2:
                    raise HTTPException(422, r.course_name + ' 缺学时，算不出建议积分：请在申请说明里写明实际学时，由审核人填积分')
                entry.update(level='teacher', decision='apply', points_after=str(points_now) if points_now is not None else None)
                stage = 'dept'
            else:
                if stage != 'dept' or any(s.get('level') != 'teacher' for s in steps):
                    raise HTTPException(409, r.course_name + ' 已经有人审核过，不能撤回')
                entry.update(level='teacher', decision='withdraw')
                stage = TEACHER_APPLY
            steps.append({k: v for k, v in entry.items() if v not in (None, '')})
            history.append({k: v for k, v in entry.items() if v not in (None, '')})
        elif data.decision != 'reset' and stage == TEACHER_APPLY:
            raise HTTPException(409, r.course_name + ' 老师还没申请认定')
        if data.decision in ('apply', 'withdraw'):
            pass
        elif data.decision == 'reset':
            if not can_review_credits(db, actor) or _own(actor, teacher, r.staff_no):
                raise HTTPException(403, '改回重审由学校授课认定人办理' if not _own(actor, teacher, r.staff_no) else '须回避本人的课，由其他人办理')
            if len(reason) < 2:
                raise HTTPException(422, '改回重审请写明原因')
            if d['review'] == 'pending' and stage in ('dept', TEACHER_APPLY) and not steps:
                continue
            unbook(db, actor, r, booked, reason)
            booked = None
            entry.update(level='school', decision='reset', points_before=str(points_now) if points_now is not None else None)
            history.append(entry)
            state, stage, steps = 'PENDING', 'dept' if r.user_id else TEACHER_APPLY, []
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
                        # 最终认定前再查一次人事：审批期间资格可能失效。不合格整批拒绝、回滚，课停在待学校认定，补齐后原单继续办。
                        if not in_staff_table(db, r.staff_no):
                            raise HTTPException(409, r.course_name + '（工号 ' + r.staff_no + '）：' + HR_MISSING)
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
        label = {'apply': '老师申请认定', 'withdraw': '老师撤回申请',
                 'approve': '认定计分' if state == 'APPROVED' else LEVEL_NAME.get(entry.get('level'), '') + '通过',
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
