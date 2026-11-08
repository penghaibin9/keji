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
- 2026-11-04 精简：培训课程 学院 → 学校；校内培训师 学院 → 组织人事部；项目结项直接到学校结项核验。
  精简前已在审批中的申请按原链路走完（见 chain_of）。
"""
from __future__ import annotations
from datetime import datetime, timedelta
from fastapi import HTTPException
from sqlalchemy import select
from .core import school_today
from .models import User, Org, WorkflowEvent
from .identities import stage_handler, org_heads, VACANCY_LABEL, check_not_principal

LEVEL_LABEL = {'dept': '教研室', 'college': '学院', 'school': '学校', 'hr': '组织人事部', 'jwc': '教务处'}
LEVEL_STAGE = {'dept': 'DEPARTMENT', 'college': 'COLLEGE'}
# 全校一级由“社会培训职责设置”里指定的人办：学校（继续教育学院）是归口学院复审；
# 培训师资格由组织人事部认定、外聘培训师由教务处审核备案（管理办法第八条、第十五条）。
LEVEL_DUTY = {'school': 'coordinator', 'hr': 'trainer_hr', 'jwc': 'trainer_filing'}
LEVEL_VERB = {'dept': '审核', 'college': '审批', 'school': '审批', 'hr': '认定', 'jwc': '备案审核'}
SAME_PERSON = '同一人连审'

# 每类申请：审批链、每一级对应的 state、生效后的 state、名称。
# 2026-11-04 精简：去掉制度未规定的审批级（培训课程去教研室；校内培训师去教研室、学校；项目结项去学院核验）。
# legacy_chain 是精简前的链路：精简前已提交、还在审批中的申请按原链路走完，新提交的走新链路
# （新提交在 data 里记 chain=2，结项记 close_chain=2；不改数据库结构）。
FLOWS = {
    'project': {'label': '培训项目申请', 'chain': ('college', 'school'), 'states': {'college': 'COLLEGE', 'school': 'SUBMITTED'},
                'done': 'FILED', 'final': '已备案', 'object_type': 'social_project'},
    'project_close': {'label': '培训项目结项', 'chain': ('school',), 'legacy_chain': ('college', 'school'), 'marker': 'close_chain',
                      'states': {'college': 'CLOSE_COLLEGE', 'school': 'CLOSE_REVIEW'},
                      'done': 'CLOSED', 'final': '已结项', 'object_type': 'social_project'},
    # 培训课程申报（管理办法第十六条课程遴选）：从我的课程带出（teaching_course）和新填一门（course）是同一条流程。
    'course': {'label': '培训课程申报', 'chain': ('college', 'school'), 'legacy_chain': ('dept', 'college', 'school'),
               'states': {'dept': 'DEPT', 'college': 'COLLEGE', 'school': 'SCHOOL'},
               'done': 'ACTIVE', 'final': '进入培训课程库', 'object_type': 'social_resource'},
    'teaching_course': {'label': '培训课程申报', 'chain': ('college', 'school'), 'legacy_chain': ('dept', 'college', 'school'),
                        'states': {'dept': 'DEPT', 'college': 'COLLEGE', 'school': 'SCHOOL'},
                        'done': 'ACTIVE', 'final': '进入培训课程库', 'object_type': 'social_resource'},
    # 培训师遴选（管理办法第十五条）：校内老师本人申报，学院审核后由组织人事部认定资格；外聘培训师由学院登记，教务处审核备案。
    'trainer': {'label': '培训师申报', 'chain': ('college', 'hr'), 'legacy_chain': ('dept', 'college', 'school', 'hr'),
                'states': {'dept': 'DEPT', 'college': 'COLLEGE', 'school': 'SCHOOL', 'hr': 'HR'},
                'done': 'ACTIVE', 'final': '进入培训师资', 'object_type': 'social_resource'},
    'trainer_external': {'label': '外聘培训师备案', 'chain': ('jwc',), 'states': {'jwc': 'JWC'},
                         'done': 'ACTIVE', 'final': '进入培训师资', 'object_type': 'social_resource'},
    'base': {'label': '培训基地申请', 'chain': ('college', 'school'), 'states': {'college': 'COLLEGE', 'school': 'SCHOOL'},
             'done': 'DRAFT', 'final': '进入基地清单', 'object_type': 'social_resource'},
    # 2026-11-07 运行中的变更申请（lifecycle.py）：只审改动的几项，通过后档案业务版本号 +1。
    'change': {'label': '变更申请', 'chain': ('college', 'school'), 'states': {'college': 'COLLEGE', 'school': 'SCHOOL'},
               'done': 'ACTIVE', 'final': '变更生效', 'object_type': 'social_resource'},
    'change_college': {'label': '变更申请', 'chain': ('college',), 'states': {'college': 'COLLEGE'},
                       'done': 'ACTIVE', 'final': '变更生效', 'object_type': 'social_resource'},
    'change_hr': {'label': '变更申请', 'chain': ('college', 'hr'), 'states': {'college': 'COLLEGE', 'hr': 'HR'},
                  'done': 'ACTIVE', 'final': '变更生效', 'object_type': 'social_resource'},
    'change_jwc': {'label': '变更申请', 'chain': ('jwc',), 'states': {'jwc': 'JWC'},
                   'done': 'ACTIVE', 'final': '变更生效', 'object_type': 'social_resource'},
}
CHAIN_VERSION = 2
LEVEL_STATES = {'DEPT': '待教研室审核', 'COLLEGE': '待学院审批', 'SCHOOL': '待学校审批', 'HR': '待组织人事部认定', 'JWC': '待教务处备案审核',
                'CLOSE_COLLEGE': '待学院结项核验'}


def chain_of(flow, obj=None):
    """这张申请走哪条链：新提交（记了链路版本）走精简后的链；精简前提交的按原链走完。"""
    f = FLOWS[flow]
    if 'legacy_chain' not in f or obj is None:
        return f['chain']
    data = getattr(obj, 'data', None) or {}
    if data.get(f.get('marker', 'chain')) == CHAIN_VERSION:
        return f['chain']
    return f['legacy_chain']


def mark_new_chain(flow, data):
    """新提交：在申请资料里记下走精简后的链路。"""
    f = FLOWS[flow]
    if 'legacy_chain' not in f:
        return dict(data)
    return {**data, f.get('marker', 'chain'): CHAIN_VERSION}


def level_of(flow, state):
    for level, value in FLOWS[flow]['states'].items():
        if value == state:
            return level
    return None


def first_state(flow, obj=None):
    f = FLOWS[flow]
    return f['states'][chain_of(flow, obj)[0]]


def next_state(flow, level, obj=None):
    f = FLOWS[flow]
    chain = chain_of(flow, obj)
    if level not in chain:
        # 在途申请停在已去掉的一级（例如旧链上的教研室）：按原链往下走。
        chain = f.get('legacy_chain', chain)
    i = chain.index(level)
    return f['states'][chain[i + 1]] if i + 1 < len(chain) else f['done']


def resume_state(flow, returned_level, obj=None):
    """退回后补正重交：从退回的那一级重新审；没记下退回级别的从第一级开始。"""
    f = FLOWS[flow]
    if returned_level in chain_of(flow, obj):
        return f['states'][returned_level]
    return first_state(flow, obj)


def level_handler(db, applicant, level, heads=None, orgs=None):
    """这一级实际由谁办：('dept'|'college'|'school', 代办说明或 None)。申请人本人是负责人时自动交上一级。"""
    if level in LEVEL_DUTY:
        return level, None
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
    if kind in LEVEL_DUTY:
        st.duty(db, actor, LEVEL_DUTY[kind], applicant.id, org_id)
        if level not in LEVEL_DUTY and actor.role.kind != 'school':
            raise HTTPException(403, LEVEL_LABEL[level] + '没有可办理的负责人，由学校（继续教育学院）代办')
    else:
        actor.require('assessment.review')
        if actor.role.kind != kind:
            raise HTTPException(403, '这一步由' + LEVEL_LABEL[kind] + '负责人办理，不能越级')
        if applicant.org_id not in actor.org_ids:
            raise HTTPException(403, '申请人不在你负责的' + LEVEL_LABEL[kind])
        check_not_principal(db, actor, applicant.id)
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
    if kind in LEVEL_DUTY:
        ids = [i for i in st.assignments(db).get(LEVEL_DUTY[kind], []) if i != applicant.id]
        return [n for n in _names(db, ids).values()], '学校（继续教育学院）' if kind == 'school' else LEVEL_LABEL[kind], acting
    heads = org_heads(db, (kind,))
    org = db.get(Org, applicant.org_id)
    target = org if kind == 'dept' else college_of(db, applicant)
    if kind == 'college' and org is not None and org.kind == 'college':
        target = org
    rows = heads.get(target.id, []) if target else []
    # 院长在前；经办人标“（经办人）”，授权院长本人的申请不列经办人。
    names = sorted({h['name'] for h in rows if h['usable'] and not h.get('agent') and h['user_id'] != applicant.id})
    names += sorted({h['name'] + '（经办人）' for h in rows if h['usable'] and h.get('agent') and h['user_id'] != applicant.id
                     and h.get('delegated_by') != applicant.id})
    return names, (target.name if target else LEVEL_LABEL[kind]) + '负责人', acting


DUTY_STATES = {'trainer_hr': ('HR',), 'trainer_filing': ('JWC',)}


def duty_gap(db, applicant, level):
    """这一级没有可办理的人时，给出明确原因和配置位置；有人可办时返回 None。"""
    from . import social_training as st
    if level in LEVEL_DUTY:
        ids = st.assignments(db).get(LEVEL_DUTY[level], [])
        label = st.DUTIES.get(LEVEL_DUTY[level], LEVEL_LABEL[level])
        if not ids:
            return '“' + label + '”尚未指定办理人，申请会停在这一步。请学校管理员在“用户与权限 › 学校审批职责”中指定。'
        if applicant is not None and all(i == applicant.id for i in ids):
            return '“' + label + '”只指定了申请人本人，本人不能审批自己的申请，请学校管理员在“用户与权限 › 学校审批职责”中另行指定办理人。'
        return None
    names, title, _ = handler_names(db, applicant, level) if applicant else ([], LEVEL_LABEL[level], None)
    if not names:
        return title + '暂无可办理的负责人，申请会停在这一步。请学校管理员在组织机构中设置负责人。'
    return None


def pending_duty_gaps(db):
    """学校级职责未指定且有申请在等的情况，给管理员看；只统计申请单数量，不读申请内容。"""
    from sqlalchemy import func
    from .social_models import SocialResource
    from . import social_training as st
    assigned = st.assignments(db)
    out = []
    for code, states in DUTY_STATES.items():
        if assigned.get(code):
            continue
        pending = db.scalar(select(func.count()).select_from(SocialResource).where(SocialResource.kind == 'trainer', SocialResource.state.in_(states))) or 0
        out.append({'duty': code, 'label': st.DUTIES[code], 'pending': pending})
    return out


def school_duty_alerts(db):
    """给学校系统管理员首页的提醒：学校环节的职责没人或只有 1 人（本人申请回避后就没人办）。

    “归口学院复审”管着项目、课程、基地等走到学校这一级的审批，不管有没有申请在等都提醒；
    培训师认定、外聘培训师备案两项只在有申请在等时提醒。只数单子，不读申请内容。"""
    from sqlalchemy import func
    from .social_models import SocialProject, SocialResource
    from . import social_training as st
    staffing = st.school_duty_staffing(db)
    out = []
    staff = staffing.get('coordinator', 0)
    if staff < 2:
        pending = (db.scalar(select(func.count()).select_from(SocialProject).where(SocialProject.state.in_(('SUBMITTED', 'CLOSE_REVIEW')))) or 0) + \
                  (db.scalar(select(func.count()).select_from(SocialResource).where(SocialResource.state == 'SCHOOL')) or 0)
        out.append({'duty': 'coordinator', 'label': st.DUTIES['coordinator'], 'staff': staff, 'pending': pending})
    for gap in pending_duty_gaps(db):
        if gap['pending']:
            out.append({**gap, 'staff': 0})
    return out


def _iso(value):
    return value.isoformat(timespec='seconds') if isinstance(value, datetime) else value


def progress(db, flow, obj, applicant, *, returned_level=None):
    """三处进度显示用同一份数据：节点（已通过/正在办/被退回/未到）、一句话说明、第几步。"""
    f = FLOWS[flow]
    chain = chain_of(flow, obj)
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
            # 旧申请转新流程时，历史上已通过的节点可能已不在新链里：先确认还在链里再比顺序，不在的不算已通过。
            done_by = {k: v for k, v in done_by.items() if k in chain and chain.index(k) < chain.index(h.get('level'))} if h.get('level') in chain else {}
    current = level_of(flow, obj.state)
    finished = obj.state == f['done'] and last_submit is not None
    close_returned = flow == 'project_close' and obj.state == 'FILED' and bool(evs) and _handling(evs[-1]).get('decision') == 'return'
    returned = obj.state == 'RETURNED' or close_returned
    refiled = obj.state == 'RETURNED' and flow == 'project' and returned_level is None and bool(evs) and _handling(evs[-1]).get('decision') == 'refile'
    if close_returned:
        returned_level = _handling(evs[-1]).get('level')
    nodes = [{'key': 'submit', 'label': '提交', 'state': 'done' if last_submit else 'current',
              'who': last_submit.actor_name if last_submit else applicant.name if applicant else '', 'at': _iso(last_submit.created_at) if last_submit else None}]
    today = school_today()
    arrived = None
    if evs:
        arrived = evs[-1].created_at
    headline = ''
    step = 1
    for i, level in enumerate(chain):
        node = {'key': level, 'label': LEVEL_LABEL[level] + LEVEL_VERB[level], 'state': 'todo'}
        ev = done_by.get(level)
        before_current = current in chain and chain.index(level) < chain.index(current)
        if finished or (ev is not None and current != level) or before_current:
            node.update(state='done')
            if ev is not None:
                h = _handling(ev)
                node.update(who=ev.actor_name, at=_iso(ev.created_at), acting_for=h.get('acting_for'), same_person=h.get('same_person'),
                            agent_for=h.get('agent_for'))
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
            gap = duty_gap(db, applicant, level) if applicant else None
            if gap:
                node.update(unassigned=True)
                headline = gap
        nodes.append(node)
    nodes.append({'key': 'done', 'label': f['final'], 'state': 'done' if finished else 'todo',
                  'at': _iso(evs[-1].created_at) if finished and evs else None})
    total = len(chain) + 2  # 提交 + 各级审批 + 办结，与进度条节点数一致
    if finished:
        step = total
        text = f['final']
        headline = '已办结：' + f['final'] + '。'
        if f.get('done') == 'FILED':
            # 备案只是立项办完，项目接着进入运行，别让老师以为整件事已经结束。
            headline = '立项已办结：' + f['final'] + '。项目进入运行阶段，培训结束并导入参训明细后再提交结项。'
    elif returned:
        back = next((n for n in nodes if n['state'] == 'returned'), None)
        who = LEVEL_LABEL.get(returned_level, '审批人')
        text = who + '退回，待你补正'
        reason = (back.get('reason') or '').rstrip() if back else ''
        reason_text = ('：' + reason if reason else '') + ('' if reason.endswith(('。','！','？','.','!','?')) else '。')
        headline = who + '退回' + reason_text + '请补正后重新提交，会从' + who + '这一级接着审。'
        if close_returned:
            headline = who + '退回结项' + reason_text + '请核对原结项资料后重新提交结项核验。'
        if refiled:
            text = '已申请重新备案，待你补正后提交'
            headline = '你已申请重新备案：请修改项目资料后重新提交，会重新经学院审批、学校备案。'
    elif current:
        text = LEVEL_LABEL[current] + LEVEL_VERB[current] + '中 · 第 %d 步 / 共 %d 步' % (step, total)
    else:
        text = '草稿，尚未提交'
        headline = '还没有提交。填好后点“提交”，会先到' + LEVEL_LABEL[chain[0]] + '。'
        step = 1
    tone = 'green' if finished else 'red' if returned else 'blue' if current else 'gray'
    return {'flow': flow, 'label': f['label'], 'nodes': nodes, 'text': text, 'headline': headline, 'step': step, 'total': total,
            'tone': tone, 'needs_applicant': returned or not current and not finished,
            'unassigned': any(n.get('unassigned') for n in nodes), 'refiled': refiled}
