"""Approval-center read models; all decisions still use the original business routes."""
from calendar import monthrange
from datetime import date
import re
from fastapi import HTTPException
from sqlalchemy import select, func
from .core import serial, school_today
from .models import User, Org, Period, Qualification, Assessment, Dispute, WorkflowEvent
from .org_assessment import OrganizationAssessment
from .social_models import SocialProject, SocialClaim, SocialAnnual, SocialResource
from . import applications as apps, social_training as st, approvals as ap

MODELS = {'qualification': Qualification, 'assessment': Assessment,
          'organization_assessment': OrganizationAssessment, 'dispute': Dispute,
          'social_project': SocialProject, 'social_claim': SocialClaim,
          'social_annual': SocialAnnual, 'social_resource': SocialResource}
TITLES = {'qualification': '教师资质', 'assessment': '教师考核',
          'organization_assessment': '组织考核', 'dispute': '数据核对',
          'social_project': '培训项目', 'social_claim': '积分认定',
          'social_annual': '学院年度考核', 'social_resource': '积分更正与公示'}
STATES = {'DRAFT': '草稿', 'SUBMITTED': '待审核', 'APPROVED': '已通过',
          'RETURNED': '退回补正', 'TEACHER': '待本人确认', 'DEPARTMENT': '待教研室确认',
          'COLLEGE': '待学院确认', 'SCHOOL': '待学校审核', 'READY': '待归档',
          'ARCHIVED': '已归档', 'GENERATED': '待组织复核', 'REVIEWED': '待学校审核',
          'SCHOOL_APPROVED': '待归档', 'OPEN': '待核对', 'RESOLVED': '已解决'}
RESOURCE_KINDS = {'course_apply', 'base', 'trainer', 'correction', 'point_review', 'point_report'}
CREATED_ACTIONS = {'新建资质', 'Excel导入资质草稿', '提出核对申请', '建立项目申报',
                   '建立本人积分申报', '建立学院年度自评', '提交培训课程申报', '提交培训基地申请',
                   '提交培训师申报', '提交外聘培训师备案', '发起积分核对', '生成已认定积分汇总',
                   '由积分核对生成更正（学院院长已裁定，免院长初审）'}


def readable(db, actor, kind, ident):
    obj = db.get(MODELS[kind], ident)
    if obj is None:
        return None
    if kind.startswith('social_'):
        if kind == 'social_resource' and apps.is_application(obj):
            actor.require('portal.read')
            apps.read_check(db, actor, obj)
            return obj
        actor.require('records.read')
        if kind == 'social_resource' and obj.kind not in RESOURCE_KINDS:
            return None
        return st.scoped(db, actor, kind, ident)
    actor.require({'qualification': 'qualification.read', 'assessment': 'assessment.read',
                   'organization_assessment': 'assessment.read', 'dispute': 'dispute.write'}[kind])
    if kind == 'organization_assessment':
        if actor.role.kind != 'school' and (obj.target_id != actor.org.id or obj.target_kind != actor.role.kind):
            raise HTTPException(403, '组织考核超出当前授权范围')
    else:
        actor.check_teacher(db, obj.teacher_id)
    return obj


def describe(db, actor, kind, obj, raw=None, entered_times=None):
    raw = raw or {}
    data = getattr(obj, 'data', None) or {}
    teacher_id = getattr(obj, 'teacher_id', None) or data.get('teacher_id') or getattr(obj, 'owner_id', None)
    person = db.get(User, teacher_id) if teacher_id else None
    org_id = person.org_id if person else getattr(obj, 'target_id', None) or getattr(obj, 'org_id', None)
    org = db.get(Org, org_id) if org_id else None
    period_id = getattr(obj, 'period_id', None) or data.get('period_id')
    period = db.get(Period, period_id) if period_id else None
    title = TITLES[kind]
    name = getattr(obj, 'name', '') or data.get('name', '') or title
    state = STATES.get(obj.state, '待核对')
    if kind == 'social_claim':
        project = db.get(SocialProject, obj.project_id)
        name = project.data['name'] if project else '原培训项目'
    if kind == 'assessment':
        name = (period.name + ' · ' if period else '') + '教师考核'
    if kind == 'organization_assessment':
        name = (org.name + ' · ' if org else '') + '组织考核'
    if kind == 'social_annual':
        name = (org.name + ' · ' if org else '') + (period.name + ' · ' if period else '') + '年度考核'
    if kind == 'dispute':
        name = obj.reason[:100]
    item_type = kind
    handler = ''
    if kind.startswith('social_'):
        state = st.state_label(obj)
    if kind == 'social_resource' and apps.is_application(obj):
        item_type, title, state = 'application', ap.FLOWS[apps.flow_of(obj)]['label'], apps.state_label(obj)
        level = ap.level_of(apps.flow_of(obj), obj.state)
        if level and person:
            names, handler_title, _ = ap.handler_names(db, person, level)
            handler = '、'.join(names) or handler_title
    elif kind == 'social_resource':
        title = {'correction': '积分更正', 'point_review': '积分核对', 'point_report': '积分汇总与公示'}.get(obj.kind, title)
    if entered_times is not None and (kind, obj.id) in entered_times:
        entered = entered_times[kind, obj.id] or obj.created_at
    else:
        entered = db.scalar(select(WorkflowEvent.created_at).where(WorkflowEvent.object_type == kind,
            WorkflowEvent.object_id == obj.id, WorkflowEvent.after['state'].as_string() == obj.state,
            func.coalesce(WorkflowEvent.before['state'].as_string(), '') != obj.state).order_by(
            WorkflowEvent.created_at.desc(), WorkflowEvent.id.desc()).limit(1)) or obj.created_at
    current_period = period.name if period else ''
    if kind in {'assessment', 'organization_assessment'} and obj.state == 'ARCHIVED':
        current_period = (obj.archive or {}).get('period', {}).get('name') or current_period
    if kind == 'social_resource' and obj.kind == 'point_report':
        current_period = f"{data['year']}年{data['start_month']}—{data['end_month']}月"
    code = getattr(obj, 'certificate_no', '') or (data.get('code', '') if kind == 'social_project' else '')
    if item_type == 'application':
        code = data.get('code') or (data.get('course') or {}).get('code') or ''
    return {**raw, 'id': obj.id, 'type': item_type, 'title': raw.get('title') or title, 'business_type_label': title, 'business_name': name,
            'business_code': code,
            'teacher_id': teacher_id, 'owner_name': person.name if person else (org.name if org else '授权组织'),
            'staff_no': person.staff_no if person and person.staff_no else '',
            'current_handler': handler,
            'org_id': org_id, 'org_name': org.name if org else '', 'period_id': period_id,
            'period_name': current_period, 'state': raw.get('state') or state, 'state_label': state, 'entered_at': serial(entered),
            'action_required': raw.get('action_required', True), 'action_label': raw.get('action_label', '查看并办理')}


def waiting_condition(db, actor, obj, row):
    """Use stored publication/period dates, never invent an approval deadline."""
    if not isinstance(obj, (SocialResource, SocialAnnual)):
        return row
    data = obj.snapshot if isinstance(obj, SocialAnnual) else obj.data
    if isinstance(obj, SocialResource) and obj.kind != 'point_report':
        return row
    duties = {key for key, users in st.assignments(db).items() if actor.id in users}
    if obj.state == 'PUBLIC':
        end = data.get('public_end')
        unresolved = any(not x.get('resolved') for x in data.get('disputes', []))
        if unresolved:
            required = 'coordinator' in duties
            hint = '有异议待核实' if required else '等待归口核实公示异议'
        else:
            required = bool(end and school_today() > date.fromisoformat(end) and 'secretary' in duties)
            hint = '公示期满，可核对后归档' if required else ('公示截止' + end + '，完整期满后才能归档' if end else '等待确认公示期限')
        row.update(action_required=required, action_hint=hint, deadline=end, deadline_label='公示截止')
    elif isinstance(obj, SocialResource) and obj.state == 'SUBMITTED':
        end = date(data['year'], data['end_month'], monthrange(data['year'], data['end_month'])[1])
        allowed = 'coordinator' in duties and data.get('created_by') != actor.id
        row.update(action_required=allowed and school_today() > end,
                   action_hint='期间尚未结束，' + end.isoformat() + '结束后可复核' if school_today() <= end else ('等待独立归口复核' if not allowed else '请核对归档来源后复核'),
                   deadline=end.isoformat(), deadline_label='汇总期间结束')
    return row


def _preload(db, items):
    """一次取齐待办要读的原单、教师、组织、周期和进入当前环节的时间，代替每条待办各查五六次库。

    取出的对象留在本次数据库会话里，后面 readable()/describe() 里的 db.get() 直接拿到，授权判断和显示内容不变。
    返回值要在循环期间一直持有：会话只弱引用对象，没人引用就会被回收，又变回逐条查询。
    """
    ids = {}
    for raw in items:
        actual = 'social_resource' if raw['type'] == 'application' else raw['type']
        if actual in MODELS and raw.get('id'):
            ids.setdefault(actual, set()).add(raw['id'])
    held, by_kind, people = [], {}, set()
    for kind, keys in ids.items():
        model, keys = MODELS[kind], sorted(keys)
        for i in range(0, len(keys), 500):
            for obj in db.scalars(select(model).where(model.id.in_(keys[i:i + 500]))):
                held.append(obj)
                by_kind.setdefault(kind, {})[obj.id] = obj
                data = getattr(obj, 'data', None) or {}
                people.update(x for x in (getattr(obj, 'teacher_id', None), getattr(obj, 'owner_id', None),
                                          data.get('teacher_id'), data.get('created_by')) if isinstance(x, str) and x)
    people = sorted(people)
    for i in range(0, len(people), 500):
        held.extend(db.scalars(select(User).where(User.id.in_(people[i:i + 500]))))
    held.extend(db.scalars(select(Org)))
    held.extend(db.scalars(select(Period)))
    # 与 describe() 里单条查询同一口径：进入当前状态的最近一次流转（时间倒序、同时间按编号倒序），没有就用建单时间。
    entered = {}
    for kind, objs in by_kind.items():
        keys = sorted(objs)
        for i in range(0, len(keys), 500):
            for oid, at, eid, before, after in db.execute(select(WorkflowEvent.object_id, WorkflowEvent.created_at, WorkflowEvent.id,
                    WorkflowEvent.before['state'].as_string(), WorkflowEvent.after['state'].as_string()).where(
                    WorkflowEvent.object_type == kind, WorkflowEvent.object_id.in_(keys[i:i + 500]))):
                state = objs[oid].state
                if after == state and (before or '') != state:
                    best = entered.get((kind, oid))
                    if best is None or (at, eid) > best:
                        entered[kind, oid] = (at, eid)
    times = {(kind, oid): (entered[kind, oid][0] if (kind, oid) in entered else None)
             for kind, objs in by_kind.items() for oid in objs}
    return held, times


def pending(db, actor, items):
    out = []
    held, entered_times = _preload(db, items)
    for raw in items:
        kind = raw['type']
        if kind in {'security', 'sync'} or raw.get('state') == 'EXPIRING':
            continue
        if kind == 'credit_review' or kind == 'social_report':
            out.append({**raw, 'business_name': raw['title'], 'owner_name': '授权业务',
                        'action_required': True, 'action_label': '查看并办理'})
            continue
        actual = 'social_resource' if kind == 'application' else kind
        if actual not in MODELS:
            continue
        try:
            obj = readable(db, actor, actual, raw['id'])
            if obj:
                row = waiting_condition(db, actor, obj, describe(db, actor, actual, obj, raw, entered_times))
                if actual == 'social_project' and obj.state == 'DRAFT':
                    row.update(action_required=False, action_hint='项目草稿尚未提交，请从原单核对资料后提交', action_label='查看并完善')
                out.append(row)
        except HTTPException as error:
            if error.status_code not in (403, 404):
                raise
    return out


def records(db, actor, tab):
    # Only the actor's business events are candidates; current read permission is checked again below.
    # shortcut: 复用原单授权逐条过滤后分页；单人已办超过1000条时改为授权联查分页。
    query = select(WorkflowEvent.object_type, WorkflowEvent.object_id, WorkflowEvent.action,
        WorkflowEvent.created_at, WorkflowEvent.before['state'].as_string().label('before_state'),
        WorkflowEvent.after['state'].as_string().label('after_state')).where(
        WorkflowEvent.actor_id == actor.id, WorkflowEvent.object_type.in_(MODELS))
    if tab == 'mine':
        query = query.where(WorkflowEvent.action.in_(CREATED_ACTIONS))
    # 同秒事件按业务版本排序；历史事件缺少版本时仍按时间和事件编号稳定回退。
    candidates = db.execute(query.order_by(WorkflowEvent.created_at.desc(),
        WorkflowEvent.after['version'].as_integer().desc(), WorkflowEvent.id.desc())).all()
    chosen = {}
    for event in candidates:
        key = (event.object_type, event.object_id)
        if key in chosen:
            continue
        handled = bool(re.search('审核|审批|核验|认定|复核|确认|归档|备案|退回|裁定|通过', event.action)) or event.before_state != event.after_state
        # 培训基地通过后沿用 DRAFT 存储状态，不能误当成重新保存草稿。
        base_approved = (event.object_type == 'social_resource' and event.before_state == 'SCHOOL'
            and event.action == ap.LEVEL_LABEL['school'] + '通过' + ap.FLOWS['base']['label'])
        if tab == 'handled' and (not handled or event.before_state in {'DRAFT', 'RETURNED', None} or (event.after_state=='DRAFT' and not base_approved)
                or event.action.startswith(('提交', '重新提交', '发起', '提出', '新建', '建立', '生成', '计算', '补正', '上传'))):
            continue
        chosen[key] = event
    out = []
    for (kind, ident), event in chosen.items():
        try:
            obj = readable(db, actor, kind, ident)
            if obj is None:
                continue
            row = waiting_condition(db, actor, obj, describe(db, actor, kind, obj))
            action = event.action.replace('Excel', '表格')
            if action.startswith(('积分认定：', '积分更正：')):
                action = {'DEAN':'院长初审通过', 'COORDINATOR':'归口复审通过', 'APPROVED':'分管审批通过',
                          'ARCHIVED':'归档入账', 'RETURNED':'退回补正'}.get(event.after_state, action)
            elif action.startswith('项目办理：'):
                action = {('COLLEGE','SUBMITTED'):'学院审批通过', ('SUBMITTED','FILED'):'完成学校备案',
                          ('CLOSE_COLLEGE','CLOSE_REVIEW'):'学院结项核验通过', ('CLOSE_REVIEW','CLOSED'):'学校核验结项'}.get((event.before_state,event.after_state), action)
            row.update(my_action=action, handled_at=serial(event.created_at), action_label='查看记录')
            out.append(row)
        except HTTPException as error:
            if error.status_code not in (403, 404):
                raise
    return out


def load(db, actor, filters, page, size, source):
    if actor.role.kind not in {'dept', 'college', 'school'}:
        raise HTTPException(403, '审批中心仅供管理身份使用；本人待办请进入待办中心')
    tab = filters.get('tab') or 'handle'
    if tab not in {'handle', 'handled', 'mine'}:
        raise HTTPException(422, '审批分区无效')
    rows = pending(db, actor, source) if tab == 'handle' else records(db, actor, tab)
    if filters.get('org_id'):
        from .read_queries import authorized_org_descendants
        orgs = authorized_org_descendants(db, actor, filters['org_id'])
        rows = [x for x in rows if x.get('org_id') in orgs]
    counts = {}
    for row in rows:
        if tab == 'handle' and not row.get('action_required', True):
            continue
        counts[row['type']] = counts.get(row['type'], 0) + 1
    stages = sorted({x['state'] for x in rows if tab!='handle' or x.get('action_required', True)})
    if filters.get('type'):
        rows = [x for x in rows if x['type'] == filters['type']]
    if filters.get('state'):
        rows = [x for x in rows if x['state'] == filters['state']]
    if filters.get('period_id'):
        rows = [x for x in rows if x.get('period_id') == filters['period_id']]
    if filters.get('stage') == 'archive':
        rows = [x for x in rows if x['state'] in {'待教学秘书归档', '待归档', 'READY', 'SCHOOL_APPROVED'}]
    elif filters.get('stage'):
        raise HTTPException(422, '审批环节无效')
    if filters.get('q'):
        word = filters['q'].casefold()
        rows = [x for x in rows if word in ' '.join(str(x.get(k) or '') for k in
            ('title', 'business_name', 'business_code', 'owner_name', 'staff_no', 'org_name', 'period_name', 'my_action')).casefold()]
    waiting_items = [x for x in rows if not x.get('action_required', True)]
    waiting = len(waiting_items)
    if tab == 'handle':
        rows = [x for x in rows if x.get('action_required', True)]
    rows.sort(key=lambda x: x.get('handled_at' if tab != 'handle' else 'entered_at') or '', reverse=tab != 'handle')
    return {'items': rows[(page-1)*size:page*size], 'total': len(rows), 'page': page, 'size': size,
            'counts': counts, 'stages': stages, 'waiting': waiting, 'waiting_items': waiting_items[:20] if tab=='handle' else [], 'tab': tab,
            'can_archive': actor.role.kind == 'school' and ('assessment.archive' in actor.permissions or
                actor.id in st.assignments(db).get('secretary', []))}
