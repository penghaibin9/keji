"""老师发起、一级一级往上审的通用审批规则（培训项目、培训课程、培训基地共用）。

不改数据库结构：当前办到哪一级由业务对象自己的 state 表示，退回到哪一级记在 data 里，
每一步谁办、何时办、是否代办或同一人连审，都写进现有的 workflow_events（办理记录），
进度显示从这些记录里读出来。

规则：
- 本人的申请回避：负责人是申请人本人时，这一级交上一级办理。
- 缺负责人上交：教研室没有负责人由学院负责人代办，学院也没有由学校代办，并标“代办”。
- 学校一级由“归口学院复审”职责（继续教育学院）办理，和原来的审核备案是同一批人。
- 同一个人连着审两级允许，标“同一人连审”。
- 任何一级都能退回，必须写原因；老师补正后从退回的那一级重新审，不从头走。
"""
from __future__ import annotations
from datetime import datetime, timedelta
from fastapi import HTTPException
from sqlalchemy import select
from .core import school_today
from .models import User, Org, WorkflowEvent
from .identities import stage_handler, org_heads, VACANCY_LABEL

LEVEL_LABEL = {'dept': '教研室', 'college': '学院', 'school': '学校'}
LEVEL_STAGE = {'dept': 'DEPARTMENT', 'college': 'COLLEGE'}
SAME_PERSON = '同一人连审'

# 每类申请：审批链、每一级对应的 state、生效后的 state、名称。
FLOWS = {
    'project': {'label': '培训项目申请', 'chain': ('college', 'school'), 'states': {'college': 'COLLEGE', 'school': 'SUBMITTED'},
                'done': 'FILED', 'final': '已备案', 'object_type': 'social_project'},
    'project_close': {'label': '培训项目结项', 'chain': ('college', 'school'), 'states': {'college': 'CLOSE_COLLEGE', 'school': 'CLOSE_REVIEW'},
                      'done': 'CLOSED', 'final': '已结项', 'object_type': 'social_project'},
    # 培训课程申报（管理办法第十六条课程遴选）：从我的课程带出（teaching_course）和新填一门（course）是同一条流程。
    'course': {'label': '培训课程申报', 'chain': ('dept', 'college', 'school'), 'states': {'dept': 'DEPT', 'college': 'COLLEGE', 'school': 'SCHOOL'},
               'done': 'ACTIVE', 'final': '进入培训课程库', 'object_type': 'social_resource'},
    'teaching_course': {'label': '培训课程申报', 'chain': ('dept', 'college', 'school'), 'states': {'dept': 'DEPT', 'college': 'COLLEGE', 'school': 'SCHOOL'},
                        'done': 'ACTIVE', 'final': '进入培训课程库', 'object_type': 'social_resource'},
    'base': {'label': '培训基地申请', 'chain': ('college', 'school'), 'states': {'college': 'COLLEGE', 'school': 'SCHOOL'},
             'done': 'DRAFT', 'final': '进入基地清单', 'object_type': 'social_resource'},
}
LEVEL_STATES = {'DEPT': '待教研室审核', 'COLLEGE': '待学院审批', 'SCHOOL': '待学校审批', 'CLOSE_COLLEGE': '待学院结项核验'}


def level_of(flow, state):
    for level, value in FLOWS[flow]['states'].items():
        if value == state:
            return level
    return None


def first_state(flow):
    f = FLOWS[flow]
    return f['states'][f['chain'][0]]


def next_state(flow, level):
    f = FLOWS[flow]
    chain = f['chain']
    i = chain.index(level)
    return f['states'][chain[i + 1]] if i + 1 < len(chain) else f['done']


def resume_state(flow, returned_level):
    """退回后补正重交：从退回的那一级重新审；没记下退回级别的从第一级开始。"""
    f = FLOWS[flow]
    return f['states'].get(returned_level) or first_state(flow)


def level_handler(db, applicant, level, heads=None, orgs=None):
    """这一级实际由谁办：('dept'|'college'|'school', 代办说明或 None)。申请人本人是负责人时自动交上一级。"""
    if level == 'school':
        return 'school', None
    kind, vacant = stage_handler(db, applicant, LEVEL_STAGE[level], heads, orgs)
    return kind, VACANCY_LABEL.get(vacant)


def college_of(db, user):
    org = db.get(Org, user.org_id) if user else None
    while org is not None and org.kind not in ('college', 'school'):
        org = db.get(Org, org.parent_id) if org.parent_id else None
    return org


def check_handler(db, actor, applicant, level, org_id):
    """确认 actor 能办这一级，返回要写进办理记录的 handling。不能办直接拒绝。"""
    from . import social_training as st
    if applicant is None:
        raise HTTPException(409, '申请人账号已不存在，请学校管理员核对')
    if actor.id == applicant.id:
        raise HTTPException(403, '须回避本人的申请，由上一级或其他负责人办理')
    kind, acting = level_handler(db, applicant, level)
    if kind == 'school':
        st.duty(db, actor, 'coordinator', applicant.id, org_id)
        if level != 'school' and actor.role.kind != 'school':
            raise HTTPException(403, LEVEL_LABEL[level] + '没有可办理的负责人，由学校（继续教育学院）代办')
    else:
        actor.require('assessment.review')
        if actor.role.kind != kind:
            raise HTTPException(403, '这一步由' + LEVEL_LABEL[kind] + '负责人办理，不能越级')
        if applicant.org_id not in actor.org_ids:
            raise HTTPException(403, '申请人不在你负责的' + LEVEL_LABEL[kind])
        st.check_conflicts(db, actor, applicant.id, org_id)
    return {'level': level, 'handled_by_level': kind, 'acting_for': acting}


def can_handle(db, actor, applicant, level, org_id):
    try:
        check_handler(db, actor, applicant, level, org_id)
        return True
    except HTTPException:
        return False


def events(db, object_type, ident):
    return db.scalars(select(WorkflowEvent).where(WorkflowEvent.object_type == object_type, WorkflowEvent.object_id == ident)
                      .order_by(WorkflowEvent.created_at, WorkflowEvent.id)).all()


def _handling(ev):
    return (ev.after or {}).get('handling') or {}


def same_person(db, object_type, ident, actor):
    """上一步（本轮提交以来）的审批人就是本人时，标“同一人连审”。"""
    for ev in reversed(events(db, object_type, ident)):
        h = _handling(ev)
        if h.get('decision') == 'approve':
            return ev.actor_id == actor.id
        if h.get('decision') in ('submit', 'return'):
            return False
    return False


def handling_after(after, handling):
    after = dict(after)
    after['handling'] = {k: v for k, v in handling.items() if v not in (None, '', False)}
    return after


def _names(db, ids):
    ids = sorted({i for i in ids if i})
    return dict(db.execute(select(User.id, User.name).where(User.id.in_(ids or ['']))).all())


def handler_names(db, applicant, level):
    """当前这一级应由谁办（给老师看的名字）。"""
    from . import social_training as st
    kind, acting = level_handler(db, applicant, level)
    if kind == 'school':
        ids = [i for i in st.assignments(db).get('coordinator', []) if i != applicant.id]
        return [n for n in _names(db, ids).values()], '学校（继续教育学院）', acting
    heads = org_heads(db, (kind,))
    org = db.get(Org, applicant.org_id)
    target = org if kind == 'dept' else college_of(db, applicant)
    if kind == 'college' and org is not None and org.kind == 'college':
        target = org
    rows = heads.get(target.id, []) if target else []
    names = sorted({h['name'] for h in rows if h['usable'] and h['user_id'] != applicant.id})
    return names, (target.name if target else LEVEL_LABEL[kind]) + '负责人', acting


def _iso(value):
    return value.isoformat(timespec='seconds') if isinstance(value, datetime) else value


def progress(db, flow, obj, applicant, *, returned_level=None):
    """三处进度显示用同一份数据：节点（已通过/正在办/被退回/未到）、一句话说明、第几步。"""
    f = FLOWS[flow]
    chain = f['chain']
    evs = events(db, f['object_type'], obj.id)
    # 只看本流程（项目申请和结项共用一个对象，用 handling.flow 区分）。
    evs = [e for e in evs if _handling(e).get('flow') == flow]
    last_submit = None
    done_by = {}
    for e in evs:
        h = _handling(e)
        if h.get('decision') == 'submit':
            last_submit = e
            done_by = {}
        elif h.get('decision') == 'approve':
            done_by[h.get('level')] = e
        elif h.get('decision') == 'return':
            done_by = {k: v for k, v in done_by.items() if chain.index(k) < chain.index(h.get('level'))} if h.get('level') in chain else {}
    current = level_of(flow, obj.state)
    finished = obj.state == f['done'] and last_submit is not None
    returned = obj.state == 'RETURNED'
    nodes = [{'key': 'submit', 'label': '提交', 'state': 'done' if last_submit else 'current',
              'who': last_submit.actor_name if last_submit else applicant.name if applicant else '', 'at': _iso(last_submit.created_at) if last_submit else None}]
    today = school_today()
    arrived = None
    if evs:
        arrived = evs[-1].created_at
    headline = ''
    step = 1
    for i, level in enumerate(chain):
        node = {'key': level, 'label': LEVEL_LABEL[level] + ('审核' if level == 'dept' else '审批'), 'state': 'todo'}
        ev = done_by.get(level)
        before_current = current in chain and chain.index(level) < chain.index(current)
        if finished or (ev is not None and current != level) or before_current:
            node.update(state='done')
            if ev is not None:
                h = _handling(ev)
                node.update(who=ev.actor_name, at=_iso(ev.created_at), acting_for=h.get('acting_for'), same_person=h.get('same_person'))
            elif last_submit is not None and _handling(last_submit).get('college_by_registrant'):
                node.update(who=last_submit.actor_name, acting_for=_handling(last_submit)['college_by_registrant'])
        elif returned and returned_level == level:
            node.update(state='returned')
            back = next((e for e in reversed(evs) if _handling(e).get('decision') == 'return'), None)
            if back is not None:
                node.update(who=back.actor_name, at=_iso(back.created_at), reason=back.reason)
            step = i + 2
        elif current == level:
            names, title, acting = handler_names(db, applicant, level) if applicant else ([], LEVEL_LABEL[level], None)
            waited = (today - (arrived + timedelta(hours=8)).date()).days if arrived else 0
            node.update(state='current', who='、'.join(names) or title, title=title, acting_for=acting,
                        since=_iso(arrived), waiting_days=max(waited, 0))
            step = i + 2
            headline = title + (('（' + '、'.join(names) + '）') if names else '') + '正在' + node['label'][-2:] + \
                ('，已等 %d 天' % waited if waited > 0 else '') + '。'
            if acting:
                headline += '本级' + acting + '。'
        nodes.append(node)
    nodes.append({'key': 'done', 'label': f['final'], 'state': 'done' if finished else 'todo',
                  'at': _iso(evs[-1].created_at) if finished and evs else None})
    total = len(chain) + 2  # 提交 + 各级审批 + 办结，与进度条节点数一致
    if finished:
        step = total
        text = f['final']
        headline = '已办结：' + f['final'] + '。'
    elif returned:
        back = next((n for n in nodes if n['state'] == 'returned'), None)
        who = LEVEL_LABEL.get(returned_level, '审批人')
        text = who + '退回，待你补正'
        headline = who + '退回' + ('：' + back['reason'] if back and back.get('reason') else '') + '。请补正后重新提交，会从' + who + '这一级接着审。'
    elif current:
        text = LEVEL_LABEL[current] + ('审核中' if current == 'dept' else '审批中') + ' · 第 %d 步 / 共 %d 步' % (step, total)
    else:
        text = '草稿，尚未提交'
        headline = '还没有提交。填好后点“提交”，会先到' + LEVEL_LABEL[chain[0]] + '。'
        step = 1
    tone = 'green' if finished else 'red' if returned else 'blue' if current else 'gray'
    return {'flow': flow, 'label': f['label'], 'nodes': nodes, 'text': text, 'headline': headline, 'step': step, 'total': total,
            'tone': tone, 'needs_applicant': returned or not current and not finished}
