"""立项（申报）通过以后的运行过程：一份档案，三种运行中的动作（2026-11-07）。

依据管理办法第四条（全生命周期管理）、第十二条（四）（核心事项变更重新备案）。
不做整份版本化，不改数据库结构：

- 运行记录：负责人或学院随手记一笔（开班、加课、检查、整改……），只追加、不审批，写进现有办理记录（workflow_events）。
- 申请变更：只审改动的那几项。审批期间原档案照常运行（项目照样导明细、传材料），通过后才改档案，业务版本号 +1，
  改前改后的快照就是那条办理记录的 before/after。变更单本身是一条 social_resources（kind='change'），走 approvals 里的审批链。
  小变更（人次、收入变动不超过 30%，联系人、简介之类）直接生效，只留痕迹。
- 年度运行确认：培训基地、培训师资每年确认一次是否还在运行。
- 结束：项目走原来的结项；课程、基地、师资“停用”（停用不是作废，历史数据都在，可以恢复）。

原来的“申请重新备案”（refile）把项目打回补正、重审期间明细导不进去；新办的变更走这里，在途的重新备案按原路办完。
"""
from __future__ import annotations
from datetime import date
from decimal import Decimal, InvalidOperation
from fastapi import HTTPException
from sqlalchemy import select
from .core import serial, workflow, school_today
from .models import User, Org, WorkflowEvent
from .social_models import SocialProject, SocialResource, SocialUnit
from . import approvals as ap

TYPES = {'project': '培训项目', 'course': '培训课程', 'base': '培训基地', 'trainer': '培训师资'}
RESOURCE_KIND = {'course': 'course_apply', 'base': 'base', 'trainer': 'trainer'}
OBJECT_TYPE = {'project': 'social_project', 'course': 'social_resource', 'base': 'social_resource', 'trainer': 'social_resource'}
# 档案“在运行”的业务状态：项目已备案；课程、师资已入库；基地生效后的状态沿用原来的 DRAFT（显示“已生效”）。
RUN_STATES = {'project': ('FILED',), 'course': ('ACTIVE',), 'base': ('DRAFT', 'ACTIVE'), 'trainer': ('ACTIVE',)}
STOPPED = 'STOPPED'
CHANGE_PENDING = ('COLLEGE', 'SCHOOL', 'HR', 'JWC')
CHANGE_LEVEL_LABEL = {'direct': '直接更新（留痕）', 'college': '学院审批', 'school': '学院审批 → 学校备案',
                      'hr': '学院审批 → 组织人事部认定', 'jwc': '教务处备案审核'}
CHANGE_FLOW = {'college': 'change_college', 'school': 'change', 'hr': 'change_hr', 'jwc': 'change_jwc'}
LEVEL_ORDER = ('direct', 'college', 'school', 'hr', 'jwc')

NOTE_TAGS = {'start': '开班', 'teach': '授课/加课', 'check': '检查督导', 'material': '材料归档', 'issue': '问题整改',
             'use': '使用情况', 'other': '其他'}

CATEGORY = {'subsidy': '补贴性培训', 'enterprise': '企业定制培训', 'community': '社区公益培训', 'rural': '乡村帮扶培训', 'other': '其他非学历培训'}
TEACHING_MODE = {'lecture': '讲授', 'practice': '实训实操', 'case': '案例研讨', 'onsite': '现场教学', 'online': '线上自学'}
BASE_USAGE = {'practice': '实践教学基地', 'ideology': '思政实践教学基地'}
BASE_LEVEL = {'school': '校级', 'city': '市级', 'province': '省级及以上'}
VENUE_TYPE = {'base': '校内基地', 'campus': '其他校内场所', 'offsite': '校外（一事一议）'}
DIRECTIONS = {'subsidy': '补贴性培训', 'enterprise': '企业定制培训', 'community': '社区公益培训', 'rural': '乡村帮扶培训',
              'other': '其他非学历培训', 'one_skill': '“一人一技”专项'}

# 可以申请变更的核心字段：(标签, 类型, 选项)。类型：text / textarea / number / money / date / choice / multi / user / venue
FIELDS = {
    'project': {
        'end_date': ('结束日期（延期或提前）', 'date', None),
        'expected_participants': ('预估培训人次', 'number', None),
        'expected_income': ('预计收入（元）', 'money', None),
        'venue': ('培训场地', 'venue', VENUE_TYPE),
        'owner_id': ('项目负责人', 'user', None),
        'category': ('培训类别', 'choice', CATEGORY),
        'expected_outcomes': ('预期成果', 'textarea', None),
        'total_hours': ('总学时', 'number', None),
    },
    'course': {
        'hours': ('学时', 'number', None),
        'teaching_mode': ('教学方式', 'choice', TEACHING_MODE),
        'audience': ('面向对象', 'textarea', None),
        'intro': ('课程简介', 'textarea', None),
    },
    'base': {
        'location': ('具体地点', 'text', None),
        'usages': ('基地用途', 'multi', BASE_USAGE),
        'level': ('基地级别', 'choice', BASE_LEVEL),
        'partner': ('共建单位', 'text', None),
        'manager_name': ('基地负责人', 'text', None),
    },
    'trainer': {
        'directions': ('培训业务类别', 'multi', DIRECTIONS),
        'title': ('职称或岗位', 'text', None),
        'unit': ('工作单位', 'text', None),
        'specialty': ('专业特长', 'text', None),
    },
}


def label_of(kind, value, options=None):
    if value in (None, '', []):
        return '（空）'
    if kind == 'venue' and isinstance(value, dict):
        return VENUE_TYPE.get(value.get('type'), '') + '：' + str(value.get('place') or '')
    if kind == 'multi' and isinstance(value, list):
        return '、'.join((options or {}).get(v, v) for v in value)
    if kind == 'choice':
        return (options or {}).get(value, str(value))
    return str(value)


def _num(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _ratio(old, new):
    old, new = _num(old), _num(new)
    if old is None or new is None:
        return None
    if old == 0:
        return Decimal('1') if new != 0 else Decimal('0')
    return abs(new - old) / abs(old)


# ---- 档案读取与权限 ----

def load(db, a, kind, ident, *, write=False):
    if kind not in TYPES:
        raise HTTPException(422, '档案类型不支持')
    if kind == 'project':
        obj = db.get(SocialProject, ident)
        if obj is None or obj.state == 'DELETED':
            raise HTTPException(404, '项目不存在')
    else:
        obj = db.get(SocialResource, ident)
        if obj is None or obj.kind != RESOURCE_KIND[kind] or obj.state == 'DELETED':
            raise HTTPException(404, TYPES[kind] + '不存在')
    check_access(db, a, kind, obj, write=write)
    return obj


def owner_ids(kind, obj):
    if kind == 'project':
        return {obj.owner_id}
    d = obj.data or {}
    return {i for i in (d.get('teacher_id'), d.get('created_by')) if i}


def applicant(db, kind, obj, fallback=None):
    """审批规则里的“申请人”：项目负责人；课程、师资的申请人；外聘培训师和学院直接登记的资源是登记人。"""
    if kind == 'project':
        return db.get(User, obj.owner_id)
    d = obj.data or {}
    for ident in (d.get('teacher_id'), d.get('created_by')):
        if ident and (user := db.get(User, ident)) is not None:
            return user
    return fallback


def is_manager(a, obj):
    return a.role.kind in ('college', 'school') and obj.org_id in a.org_ids


def check_access(db, a, kind, obj, *, write=False):
    mine = a.id in owner_ids(kind, obj)
    if write:
        if mine:
            return
        if is_manager(a, obj) and 'records.write' in a.permissions:
            return
        raise HTTPException(403, '只有负责人（申请人）或所属学院、学校可以办理')
    if mine or is_manager(a, obj):
        return
    if kind == 'project' and a.role.kind == 'teacher' and is_member(db, a, obj):
        return
    if a.role.kind == 'dept':
        who = applicant(db, kind, obj)
        if (who and who.org_id in a.org_ids) or obj.org_id in a.org_ids:
            return
    raise HTTPException(403, '超出你的查看范围')


def is_member(db, a, obj):
    """参与授课（在参训明细里有本人）但不是负责人的老师：能看档案、上传运行材料，不能变更、结项。"""
    from . import social_training as st
    return any(t.get('teacher_id') == a.id for u in st.units(db, obj.id) for t in (u.data or {}).get('teachers') or [])


def running(kind, obj):
    return obj.state in RUN_STATES[kind]


def require_running(kind, obj, what='办理'):
    if not running(kind, obj):
        if obj.state == STOPPED:
            raise HTTPException(409, '已停用，不能' + what + '；需要时请先恢复运行')
        if kind == 'project' and obj.state in ('CLOSE_COLLEGE', 'CLOSE_REVIEW', 'CLOSED'):
            raise HTTPException(409, '项目已进入结项，不能再' + what)
        raise HTTPException(409, ('项目备案' if kind == 'project' else '审批通过') + '后才进入运行，才能' + what)


def name_of(kind, obj):
    return obj.data['name'] if kind == 'project' else obj.name


def events(db, kind, obj):
    return ap.events(db, OBJECT_TYPE[kind], obj.id)


def biz_version(obj):
    return int((obj.data or {}).get('biz_version') or 1)


# ---- 运行记录 ----

def add_note(db, a, kind, obj, tag, text, happened_on, reason):
    require_running(kind, obj, '记运行过程')
    if tag not in NOTE_TAGS:
        raise HTTPException(422, '记录类型无效')
    if happened_on and happened_on > school_today():
        raise HTTPException(422, '发生日期不能晚于今天')
    note = {'tag': tag, 'tag_label': NOTE_TAGS[tag], 'text': text, 'happened_on': (happened_on or school_today()).isoformat()}
    # 只追加：不改档案本身，也不动乐观锁版本，记一笔不会和别人同时在办的事冲突。
    workflow(db, a, OBJECT_TYPE[kind], obj.id, '运行记录：' + NOTE_TAGS[tag], {}, {'run_note': note}, reason or text[:200])
    return note


# ---- 申请变更 ----

def current_value(kind, obj, key):
    if kind == 'project' and key == 'owner_id':
        return obj.owner_id
    return (obj.data or {}).get(key)


def normalize(db, a, kind, obj, key, value):
    """把表单里的新值整理成档案里存的样子，同时做这一项自己的校验。"""
    label, typ, options = FIELDS[kind][key]
    if typ in ('text', 'textarea'):
        value = str(value or '').strip()
        if typ == 'text' and len(value) > 500 or len(value) > 2000:
            raise HTTPException(422, label + '太长')
        if key == 'expected_outcomes' and not value:
            raise HTTPException(422, '预期成果不能为空')
        return value
    if typ in ('number', 'money'):
        n = _num(value)
        if n is None or n < 0 or n > Decimal('1000000000000'):
            raise HTTPException(422, label + '请填写不小于 0 的数字')
        if key == 'expected_participants':
            if n != n.to_integral_value():
                raise HTTPException(422, '人次须为整数')
            return int(n)
        return format(n.normalize(), 'f') if typ == 'money' or key in ('hours', 'total_hours') else str(n)
    if typ == 'date':
        try:
            d = date.fromisoformat(str(value))
        except ValueError:
            raise HTTPException(422, label + '格式无效')
        if kind == 'project' and key == 'end_date':
            if d.isoformat() < obj.data['start_date']:
                raise HTTPException(422, '结束日期不能早于开始日期')
            from . import social_training as st
            outside = [u.external_key for u in st.units(db, obj.id) if u.data['event_date'] > d.isoformat()]
            if outside:
                raise HTTPException(409, '已有参训明细晚于新的结束日期：' + '、'.join(outside[:10]))
        return d.isoformat()
    if typ == 'choice':
        if value not in options:
            raise HTTPException(422, label + '选项无效')
        if kind == 'project' and key == 'category' and value == 'subsidy' and not str(obj.data.get('target_groups') or '').strip():
            raise HTTPException(422, '改为补贴性培训须先说明重点群体和行动对接内容，请在项目资料里补充后再申请')
        return value
    if typ == 'multi':
        items = list(dict.fromkeys(value or []))
        if not items or any(v not in options for v in items):
            raise HTTPException(422, label + '至少选一项')
        return items
    if typ == 'user':
        user = db.get(User, str(value or ''))
        org = db.get(Org, user.org_id) if user else None
        if not user or not user.active or user.authorization_pending or not org or (org.id != obj.org_id and org.parent_id != obj.org_id):
            raise HTTPException(422, '项目负责人须为承办学院的有效人员')
        return user.id
    if typ == 'venue':
        from .social_schemas import ProjectVenue
        try:
            return ProjectVenue.model_validate(value or {}).model_dump()
        except Exception as error:  # pydantic ValidationError：给出能看懂的一句
            msg = str(getattr(error, 'errors', lambda: [{}])()[0].get('msg', '')) if hasattr(error, 'errors') else ''
            raise HTTPException(422, '培训场地填写不完整' + ('：' + msg.replace('Value error, ', '') if msg else ''))
    raise HTTPException(422, '字段不支持')


def field_level(kind, obj, key, old, new):
    """每一项改动要谁批。项目：负责人、类别、延期超过一个季度、改到校外、人次或收入变动超过 30% 要学校备案；
    人次、收入变动不超过 30% 直接生效；其余学院批。课程学时变动超过 50% 要学校；基地地点、级别要学校；师资业务类别要人事认定。"""
    if kind == 'project':
        if key in ('owner_id', 'category'):
            return 'school'
        if key == 'end_date':
            return 'school' if (date.fromisoformat(new) - date.fromisoformat(old or new)).days > 92 else 'college'
        if key == 'venue':
            return 'school' if (new or {}).get('type') == 'offsite' and (old or {}).get('type') != 'offsite' else 'college'
        if key in ('expected_participants', 'expected_income'):
            # 对比“上次经审批（或立项）时的值”，不是上一次的值：小变更连着改也累计，超过 30% 就要学校备案。
            r = _ratio(((obj.data or {}).get('baseline') or {}).get(key, old), new)
            return 'direct' if r is not None and r <= Decimal('0.3') else 'school'
        return 'college'
    if kind == 'course':
        if key == 'hours':
            r = _ratio(old, new)
            return 'school' if r is None or r > Decimal('0.5') else 'college'
        return 'direct' if key in ('audience', 'intro') else 'college'
    if kind == 'base':
        if key in ('location', 'level'):
            return 'school'
        return 'direct' if key == 'manager_name' else 'college'
    if key == 'directions':
        return 'jwc' if (obj.data or {}).get('source') == 'external' else 'hr'
    return 'direct'


def pending_change(db, kind, obj):
    rows = db.scalars(select(SocialResource).where(SocialResource.kind == 'change', SocialResource.state.in_(CHANGE_PENDING),
                                                   SocialResource.data['target_id'].as_string() == obj.id)).all()
    return rows[0] if rows else None


def changes_of(db, obj):
    return db.scalars(select(SocialResource).where(SocialResource.kind == 'change', SocialResource.data['target_id'].as_string() == obj.id)
                      .order_by(SocialResource.created_at)).all()


def plan_change(db, a, kind, obj, values):
    if not values:
        raise HTTPException(422, '请至少改一项')
    rows, level = [], 'direct'
    for key, raw in values.items():
        if key not in FIELDS[kind]:
            raise HTTPException(422, '“' + key + '”不能在这里变更')
        label, typ, options = FIELDS[kind][key]
        old = current_value(kind, obj, key)
        new = normalize(db, a, kind, obj, key, raw)
        if serial(old) == serial(new) or (typ in ('number', 'money') and _num(old) is not None and _num(old) == _num(new)):
            continue
        lv = field_level(kind, obj, key, old, new)
        level = max(level, lv, key=LEVEL_ORDER.index)
        rows.append({'key': key, 'label': label, 'type': typ, 'from': serial(old), 'to': serial(new),
                     'from_text': label_of(typ, old, options), 'to_text': label_of(typ, new, options), 'level': lv})
    if not rows:
        raise HTTPException(422, '填写的内容和现在一样，没有需要变更的')
    return rows, level


def submit_change(db, a, kind, obj, values, reason, basis=''):
    require_running(kind, obj, '申请变更')
    if pending_change(db, kind, obj) is not None:
        raise HTTPException(409, '已有一份变更在审批中，请等它办完，或先撤回再重新申请')
    rows, level = plan_change(db, a, kind, obj, values)
    who = applicant(db, kind, obj, fallback=a.user)
    summary = '；'.join(r['label'] + '：' + r['from_text'] + ' → ' + r['to_text'] for r in rows)
    if level == 'direct':
        apply_change(db, a, kind, obj, rows, reason, basis, how='直接更新（小变更，留痕）')
        return {'applied': True, 'level': level, 'summary': summary, 'change': None}
    flow = CHANGE_FLOW[level]
    chain = ap.FLOWS[flow]['chain']
    state, confirmed = ap.FLOWS[flow]['states'][chain[0]], None
    # 学院、学校账号替负责人提出的变更，学院这一级视为提出时已确认（和项目代登记一样）。
    if chain[0] == 'college' and a.role.kind in ('college', 'school') and a.id != (who.id if who else None):
        confirmed = '学院、学校提出时已确认'
        if len(chain) == 1:
            apply_change(db, a, kind, obj, rows, reason, basis, how='学院确认变更')
            return {'applied': True, 'level': level, 'summary': summary, 'change': None}
        state = ap.FLOWS[flow]['states'][chain[1]]
    seq = len(changes_of(db, obj)) + 1
    code = ('CHG-' + obj.id[:40] + '-' + str(seq))[:64]
    while db.scalar(select(SocialResource.id).where(SocialResource.code == code)):
        seq += 1
        code = ('CHG-' + obj.id[:40] + '-' + str(seq))[:64]
    data = {'target_type': kind, 'target_id': obj.id, 'target_name': name_of(kind, obj), 'object_type': OBJECT_TYPE[kind],
            'rows': rows, 'level': level, 'flow': flow, 'summary': summary, 'from_version': biz_version(obj),
            'teacher_id': who.id if who else None, 'created_by': a.id, 'reason': reason}
    change = SocialResource(kind='change', org_id=obj.org_id, code=code, name=('变更：' + name_of(kind, obj))[:160], state=state, data=serial(data))
    db.add(change)
    db.flush()
    record_change(db, a, change, '提交变更申请', {}, reason, {'flow': flow, 'decision': 'submit', 'college_by_registrant': confirmed}, basis)
    # 档案上也记一笔，时间线里能看到“申请了什么变更”。
    workflow(db, a, OBJECT_TYPE[kind], obj.id, '申请变更：' + CHANGE_LEVEL_LABEL[level], {}, {'change_id': change.id, 'summary': summary}, reason, basis)
    return {'applied': False, 'level': level, 'summary': summary, 'change': serial(change)}


def record_change(db, a, change, action, before, reason, handling, basis=''):
    change.version += 1
    db.flush()
    workflow(db, a, 'social_resource', change.id, action, before, ap.handling_after(serial(change), handling), reason, basis)


def target_of(db, change):
    d = change.data
    obj = db.get(SocialProject, d['target_id']) if d['target_type'] == 'project' else db.get(SocialResource, d['target_id'])
    if obj is None:
        raise HTTPException(409, '变更的档案已不存在')
    return d['target_type'], obj


def apply_change(db, a, kind, obj, rows, reason, basis, *, how, change=None):
    require_running(kind, obj, '变更')
    for r in rows:
        if serial(current_value(kind, obj, r['key'])) != r['from']:
            raise HTTPException(409, '“' + r['label'] + '”在申请之后已被改过，这份变更不能直接生效；请退回，由申请人按现在的资料重新申请')
    if kind == 'project':
        for r in rows:
            if r['key'] == 'end_date':
                # 申请到生效之间可能又导入了明细：生效时再核对一次。
                from . import social_training as st
                outside = [u.external_key for u in st.units(db, obj.id) if u.data['event_date'] > r['to']]
                if outside:
                    raise HTTPException(409, '已有参训明细晚于新的结束日期：' + '、'.join(outside[:10]) + '；请退回，由申请人重新申请')
    before = serial(obj)
    values = dict(obj.data)
    baseline = dict(values.get('baseline') or {})
    for r in rows:
        if kind == 'project' and r['key'] == 'owner_id':
            obj.owner_id = r['to']
        values[r['key']] = r['to']
        if r['key'] in ('expected_participants', 'expected_income'):
            # 直接生效的小变更不移动基准；经审批的变更把基准移到新值。
            if r.get('level') == 'direct':
                baseline.setdefault(r['key'], r['from'])
            else:
                baseline[r['key']] = r['to']
    if baseline:
        values['baseline'] = baseline
    version = biz_version(obj) + 1
    values['biz_version'] = version
    obj.data = values
    obj.version += 1
    db.flush()
    summary = '；'.join(r['label'] + '：' + r['from_text'] + ' → ' + r['to_text'] for r in rows)
    handling = {'flow': 'change', 'decision': 'apply', 'how': how, 'version': version, 'summary': summary, 'change_id': change.id if change else None}
    workflow(db, a, OBJECT_TYPE[kind], obj.id, '变更生效：第' + str(version) + '版', before, ap.handling_after(serial(obj), handling), reason, basis)
    return version


def change_action(db, a, change, action, reason, basis=''):
    from . import message_push
    flow = change.data['flow']
    kind, obj = target_of(db, change)
    who = db.get(User, change.data.get('teacher_id')) if change.data.get('teacher_id') else db.get(User, change.data['created_by'])
    mine = a.id in {change.data.get('teacher_id'), change.data.get('created_by')}
    before = serial(change)
    if action == 'withdraw':
        if not mine or change.state not in CHANGE_PENDING:
            raise HTTPException(409, '只有申请人可以撤回审批中的变更')
        change.state = 'WITHDRAWN'
        record_change(db, a, change, '撤回变更申请', before, reason, {'flow': flow, 'decision': 'withdraw'}, basis)
        workflow(db, a, OBJECT_TYPE[kind], obj.id, '撤回变更申请', {}, {'change_id': change.id}, reason, basis)
        return change
    level = ap.level_of(flow, change.state)
    if not level:
        raise HTTPException(409, '变更不在审批中')
    if action == 'approve' and level in ('hr', 'jwc') and not (basis or '').strip():
        raise HTTPException(422, '请填写' + ('资格认定文号和日期' if level == 'hr' else '备案依据'))
    handling = ap.check_handler(db, a, who, level, change.org_id)
    handling.update(flow=flow, decision=action)
    if action == 'return':
        change.state = 'RETURNED'
        change.data = {**change.data, 'returned_level': level}
        record_change(db, a, change, ap.LEVEL_LABEL[level] + '退回变更申请', before, reason, handling, basis)
        workflow(db, a, OBJECT_TYPE[kind], obj.id, ap.LEVEL_LABEL[level] + '退回变更申请', {}, {'change_id': change.id}, reason, basis)
        message_push.queue(db, [change.data.get('teacher_id'), change.data.get('created_by')], '变更申请被退回',
                           change.data['target_name'] + '：' + reason + '。原档案照常运行，需要时可重新申请。')
        return change
    if action != 'approve':
        raise HTTPException(422, '操作无效')
    if ap.same_person(db, 'social_resource', change.id, a):
        handling['same_person'] = ap.SAME_PERSON
    change.state = ap.next_state(flow, level, change)
    if change.state == ap.FLOWS[flow]['done']:
        version = apply_change(db, a, kind, obj, change.data['rows'], reason, basis, how=ap.LEVEL_LABEL[level] + '批准变更', change=change)
        change.data = {**change.data, 'applied_version': version, 'applied_on': school_today().isoformat()}
        message_push.queue(db, [change.data.get('teacher_id'), change.data.get('created_by')], '变更已生效',
                           change.data['target_name'] + '：' + change.data['summary'])
    record_change(db, a, change, ap.LEVEL_LABEL[level] + '批准变更申请', before, reason, handling, basis)
    return change


def change_read(db, a, change):
    kind, obj = target_of(db, change)
    mine = a.id in {change.data.get('teacher_id'), change.data.get('created_by')}
    level = ap.level_of(change.data['flow'], change.state)
    who = db.get(User, change.data.get('teacher_id') or change.data['created_by'])
    handle = bool(level) and ap.can_handle(db, a, who, level, change.org_id)
    if not (mine or handle or is_manager(a, change)):
        raise HTTPException(403, '变更申请超出你的查看范围')
    return {'item': serial(change), 'target': {'type': kind, 'id': obj.id, 'name': name_of(kind, obj), 'version': biz_version(obj)},
            'level_label': CHANGE_LEVEL_LABEL[change.data['level']], 'state_label': change_state_label(change),
            'progress': ap.progress(db, change.data['flow'], change, who),
            'can': {'approve': handle, 'return': handle, 'withdraw': mine and change.state in CHANGE_PENDING},
            'events': [{'action': e.action, 'actor_name': e.actor_name, 'created_at': e.created_at, 'reason': e.reason}
                       for e in ap.events(db, 'social_resource', change.id)]}


def change_state_label(change):
    if change.state in ap.LEVEL_STATES:
        return ap.LEVEL_STATES[change.state]
    return {'ACTIVE': '已生效', 'RETURNED': '已退回', 'WITHDRAWN': '已撤回'}.get(change.state, change.state)


def change_todos(db, a, rows=None):
    items = []
    if rows is None:
        rows = db.scalars(select(SocialResource).where(SocialResource.kind == 'change', SocialResource.state.in_(CHANGE_PENDING))).all()
    for change in rows:
        level = ap.level_of(change.data['flow'], change.state)
        if not level or a.role.kind == 'teacher' and level not in ap.LEVEL_DUTY:
            continue
        who = db.get(User, change.data.get('teacher_id') or change.data['created_by'])
        try:
            handling = ap.check_handler(db, a, who, level, change.org_id)
        except HTTPException:
            continue
        hint = '（' + handling['acting_for'] + '）' if handling.get('acting_for') else ''
        items.append({'type': 'life_change', 'id': change.id, 'title': TYPES[change.data['target_type']] + '变更：' + change.data['target_name'] + hint,
                      'state': change_state_label(change), 'teacher_id': change.data.get('teacher_id'), 'target_id': None if change.data.get('teacher_id') else change.org_id,
                      'org_id': change.org_id, 'business_type_label': '运行中变更', 'business_name': change.data['target_name'], 'state_label': change_state_label(change)})
    return items


# ---- 年度运行确认、停用 ----

def started_year(obj):
    """基地、师资最早有据可查的年份（设立、认定或生效日期中最早的）；都没有时返回 None，不限制。"""
    years = []
    for key in ('established_on', 'recognized_on', 'effective_on'):
        value = str((obj.data or {}).get(key) or '')[:4]
        if value.isdigit():
            years.append(int(value))
    return min(years) if years else None


def annual_years(obj):
    """年度确认可选的年份：今年和上一年度，但不早于设立／认定／生效那一年。"""
    this_year = school_today().year
    first = started_year(obj)
    return [y for y in (this_year, this_year - 1) if first is None or y >= first]


def annual_confirm(db, a, kind, obj, year, still_running, text, reason):
    if kind not in ('base', 'trainer'):
        raise HTTPException(422, '年度运行确认只用于培训基地、培训师资')
    require_running(kind, obj, '做年度确认')
    this_year = school_today().year
    if year not in (this_year, this_year - 1):
        raise HTTPException(422, '只能确认今年或上一年度')
    if year not in annual_years(obj):
        raise HTTPException(422, str(year) + '年时还没有设立或认定（最早是' + str(started_year(obj)) + '年），不能确认这一年度')
    before = serial(obj)
    annual = dict((obj.data or {}).get('annual') or {})
    previous = annual.get(str(year))
    entry = {'running': still_running, 'text': text, 'on': school_today().isoformat(), 'by': a.id}
    if previous:
        # 同一年度再次确认视为更正：保留上一次的结论，办理记录写明“更正”和前后变化。
        entry['corrects'] = {k: previous.get(k) for k in ('running', 'text', 'on', 'by')}
    annual[str(year)] = entry
    obj.data = {**obj.data, 'annual': annual}
    obj.version += 1
    db.flush()
    state = '在运行' if still_running else '暂未运行'
    if previous:
        old = '在运行' if previous.get('running') else '暂未运行'
        title = '年度运行确认（更正）：' + str(year) + '年度' + (old + ' → ' + state if old != state else '仍为' + state)
    else:
        title = '年度运行确认：' + str(year) + '年度' + state
    workflow(db, a, OBJECT_TYPE[kind], obj.id, title, before, serial(obj), reason or text)


def stop(db, a, kind, obj, reason):
    if kind == 'project':
        raise HTTPException(422, '培训项目以结项结束，不用停用')
    require_running(kind, obj, '停用')
    if pending_change(db, kind, obj) is not None:
        raise HTTPException(409, '有变更在审批中，请先撤回变更再停用')
    before = serial(obj)
    obj.data = {**obj.data, 'stopped_from': obj.state, 'stopped_on': school_today().isoformat(), 'stopped_by': a.id}
    obj.state = STOPPED
    obj.version += 1
    db.flush()
    workflow(db, a, OBJECT_TYPE[kind], obj.id, '停用' + TYPES[kind], before, serial(obj), reason)


def resume(db, a, kind, obj, reason):
    if obj.state != STOPPED:
        raise HTTPException(409, '没有停用，不用恢复')
    before = serial(obj)
    back = obj.data.get('stopped_from') or RUN_STATES[kind][0]
    obj.state = back
    obj.data = {k: v for k, v in obj.data.items() if k not in ('stopped_from', 'stopped_on', 'stopped_by')}
    obj.version += 1
    db.flush()
    workflow(db, a, OBJECT_TYPE[kind], obj.id, '恢复运行', before, serial(obj), reason)


def stopped_course_codes(db, codes):
    """已停用课程的课程编号：停用后不再接受新的参训明细，历史明细不动。"""
    codes = set(codes)
    if not codes:
        return set()
    out = set()
    for r in db.scalars(select(SocialResource).where(SocialResource.kind == 'course_apply', SocialResource.state == STOPPED)):
        code = (r.data or {}).get('course_code') or (r.code[3:] if r.code.startswith(('CA-', 'CI-')) else None)
        if code in codes:
            out.add(code)
    return out


# ---- 档案视图：时间线、版本、汇总、提醒 ----

def _source(db, kind, obj, ev, roles):
    if ev.actor_id in owner_ids(kind, obj):
        return 'self'
    return roles.get(ev.actor_id, 'college')


def _classify(ev):
    a, h = ev.action, (ev.after or {}).get('handling') or {}
    if a.startswith('运行记录'):
        return 'note'
    if a.startswith('变更生效') or a.startswith('申请变更') or '变更申请' in a:
        return 'change'
    if a == '确认培训明细整批入库' or a == '上传社会培训佐证材料':
        return 'auto'
    if h.get('decision') == 'approve' and (ev.after or {}).get('state') in ('FILED', 'ACTIVE', 'CLOSED'):
        return 'end' if (ev.after or {}).get('state') == 'CLOSED' else 'start'
    if a.startswith('停用') or a.startswith('年度运行确认') or a == '恢复运行':
        return 'end' if a.startswith('停用') else 'note'
    return 'flow'


def _what(ev):
    after = ev.after or {}
    if after.get('run_note'):
        n = after['run_note']
        return n['text'], n.get('happened_on')
    if ev.action == '上传社会培训佐证材料':
        return '上传材料：' + str(after.get('name') or ''), None
    if ev.action == '确认培训明细整批入库':
        return '导入一批参训明细（系统核算人次）', None
    h = after.get('handling') or {}
    if h.get('summary'):
        return ev.action + '　' + h['summary'], None
    if after.get('summary'):
        return ev.action + '　' + after['summary'], None
    return ev.action, None


def view(db, a, kind, obj):
    from . import social_training as st
    evs = events(db, kind, obj)
    roles = dict(db.execute(select(User.id, Org.kind).join(Org, Org.id == User.org_id).where(User.id.in_({e.actor_id for e in evs} or {''}))).all())
    roles = {k: ('school' if v == 'school' else 'college') for k, v in roles.items()}
    timeline, versions = [], []
    started = False
    for ev in evs:
        k = _classify(ev)
        text, happened = _what(ev)
        after = ev.after or {}
        h = after.get('handling') or {}
        if not started and after.get('state') in RUN_STATES[kind] and ev.action not in ('运行记录',) and not after.get('run_note'):
            started = True
            versions.append({'v': 1, 'at': ev.created_at, 'who': ev.actor_name, 'summary': '立项（申报）通过，开始运行' if kind == 'project' else '审批通过，开始运行'})
        elif kind == 'project' and h.get('flow') == 'project' and h.get('decision') == 'approve' and h.get('level') == 'school' and versions:
            versions.append({'v': len(versions) + 1, 'at': ev.created_at, 'who': ev.actor_name, 'summary': '重新备案通过'})
        if h.get('flow') == 'change' and h.get('decision') == 'apply':
            versions.append({'v': h.get('version') or len(versions) + 1, 'at': ev.created_at, 'who': ev.actor_name, 'summary': h.get('summary', ''), 'how': h.get('how')})
        timeline.append({'at': ev.created_at, 'on': happened, 'who': ev.actor_name, 'what': text, 'kind': k,
                         'source': 'auto' if k == 'auto' and ev.action == '确认培训明细整批入库' else _source(db, kind, obj, ev, roles),
                         'reason': ev.reason if not after.get('run_note') else ''})
    pending = pending_change(db, kind, obj)
    today = school_today()
    reminders, stats = [], []
    mine = a.id in owner_ids(kind, obj)
    can_write = mine or (is_manager(a, obj) and 'records.write' in a.permissions)
    notes = sum(1 for t in timeline if t['kind'] == 'note')
    materials = len(st.attachments(db, OBJECT_TYPE[kind], obj.id))
    if kind == 'project':
        rows = st.units(db, obj.id)
        effective = sum(st.unit_counts(u.data)['effective'] for u in rows)
        # 2026-11-09 设计图 v2：已开期次、参训人次、到账收入、材料。
        income = (obj.closeout or {}).get('actual_income')
        stats = [['已开期次', str(len({u.data.get('class_code') for u in rows})) + ' 期'], ['参训人次', str(effective) + ' / 预估 ' + str(obj.data.get('expected_participants') or 0)],
                 ['到账收入', (str(income) + ' 元') if income not in (None, '') else '—'], ['材料', str(materials) + ' 份']]
        if obj.state == 'FILED':
            end = date.fromisoformat(obj.data['end_date'])
            start = date.fromisoformat(obj.data['start_date'])
            if today > end:
                reminders.append('培训已于 ' + obj.data['end_date'] + ' 结束（' + str((today - end).days) + ' 天前），材料齐了就可以点“项目结项”。')
            elif (end - today).days <= 30:
                reminders.append('还有 ' + str((end - today).days) + ' 天培训结束；需要延期请点“项目立项”里的“申请变更”。')
            if today >= start and not rows:
                reminders.append('还没有参训明细' + ('，请导入。' if 'records.write' in a.permissions else '，已在学院待办里提醒导入。'))
            if obj.data.get('report_pending'):
                from .social_schemas import application_blockers
                if issues := application_blockers(obj.data):
                    reminders.append('结项前要补齐上报信息：' + '、'.join(i.replace('请填写', '').replace('请选择', '') for i in issues) + '。')
    else:
        d = obj.data or {}
        if kind == 'course':
            code = d.get('course_code') or (obj.code[3:] if obj.code.startswith(('CA-', 'CI-')) else '')
            used = list(db.scalars(select(SocialUnit).where(SocialUnit.data['course_code'].as_string() == code))) if code else []
            stats = [['学时', str(d.get('hours') or '—')], ['开课次数', str(len({(u.data['class_code'], u.data['event_date']) for u in used})) + ' 次'],
                     ['参训人次', str(sum(st.unit_counts(u.data)['effective'] for u in used))], ['运行记录', str(notes) + ' 笔']]
        else:
            stats = [['运行记录', str(notes) + ' 笔'], ['材料', str(materials) + ' 份'],
                     ['最近年度确认', next((y + '年 · ' + ('在运行' if v.get('running') else '暂未运行') for y, v in sorted((d.get('annual') or {}).items(), reverse=True)), '还没有')]]
            if running(kind, obj) and today.month >= 9 and str(today.year) not in (d.get('annual') or {}):
                reminders.append('请做 ' + str(today.year) + ' 年度运行确认（今年是否还在运行），点“年度确认”两下就好。')
    if obj.state == STOPPED:
        reminders = ['已于 ' + str((obj.data or {}).get('stopped_on') or '') + ' 停用，历史记录都保留；需要时可以恢复运行。']
    is_run = running(kind, obj)
    d = obj.data or {}
    names = dict(db.execute(select(User.id, User.name).where(User.id.in_({obj.owner_id} if kind == 'project' else {d.get('teacher_id') or ''}))).all())
    org = db.get(Org, obj.org_id)
    if kind == 'project':
        facts = [['负责人', names.get(obj.owner_id, '')], ['承办学院', org.name if org else ''], ['培训类别', CATEGORY.get(d.get('category'), '')],
                 ['培训时间', d['start_date'] + ' 至 ' + d['end_date']], ['培训场地', label_of('venue', d.get('venue'))], ['期次', obj.cohort]]
    elif kind == 'course':
        facts = [['主讲教师', d.get('teacher_name') or names.get(d.get('teacher_id'), '')], ['所属学院', org.name if org else ''],
                 ['学时', str(d.get('hours') or '')], ['教学方式', TEACHING_MODE.get(d.get('teaching_mode'), '')], ['生效日期', d.get('effective_on') or '']]
    elif kind == 'base':
        facts = [['所属学院', org.name if org else ''], ['地点', d.get('location') or ''], ['类型', '校内基地' if d.get('onsite') is not False else '校外共建'],
                 ['用途', label_of('multi', d.get('usages'), BASE_USAGE)], ['生效日期', d.get('effective_on') or '']]
    else:
        facts = [['姓名', obj.name], ['所属学院', org.name if org else ''], ['来源', '外聘培训师' if d.get('source') == 'external' else '校内教师'],
                 ['业务类别', label_of('multi', d.get('directions'), DIRECTIONS)], ['认定或备案日期', d.get('effective_on') or '']]
    return {'facts': [f for f in facts if f[1]], 'application': bool(d.get('application')), 'code': getattr(obj, 'code', None) or d.get('code'),
            'course_code': d.get('course_code') if kind == 'course' else None,'type': kind, 'type_label': TYPES[kind], 'id': obj.id, 'name': name_of(kind, obj), 'state': obj.state,
            'state_label': '已停用' if obj.state == STOPPED else st.state_label(obj), 'running': is_run, 'version': obj.version,
            'biz_version': biz_version(obj), 'timeline': list(reversed(timeline)), 'versions': list(reversed(versions)),
            'stats': stats, 'reminders': reminders,
            'pending_change': {'id': pending.id, 'summary': pending.data['summary'], 'state_label': change_state_label(pending),
                               'level_label': CHANGE_LEVEL_LABEL[pending.data['level']]} if pending else None,
            'fields': [{'key': k, 'label': v[0], 'type': v[1], 'options': v[2], 'value': serial(current_value(kind, obj, k))} for k, v in FIELDS[kind].items()],
            'note_tags': NOTE_TAGS,
            'annual': {y: {'running': bool(v.get('running')), 'on': v.get('on')} for y, v in (d.get('annual') or {}).items()} if kind in ('base', 'trainer') else {},
            'annual_years': annual_years(obj) if kind in ('base', 'trainer') else [],
            'can': {'note': can_write and is_run, 'change': can_write and is_run and pending is None,
                    'annual': can_write and is_run and kind in ('base', 'trainer'),
                    'stop': can_write and is_run and kind != 'project' and pending is None,
                    'resume': can_write and obj.state == STOPPED,
                    'close': kind == 'project' and obj.state == 'FILED' and (mine or (is_manager(a, obj) and 'records.write' in a.permissions)),
                    # 师资的认定材料办结后保持原样（不追加），运行材料只给项目、课程、基地。
                    'upload': (can_write or (kind == 'project' and a.role.kind == 'teacher' and is_member(db, a, obj))) and is_run and (kind == 'project' or kind in ('course', 'base') and bool(d.get('application')))},
            'lead': can_write, 'points': points_view(db, a, obj) if kind == 'project' else None}


# ---- 运行卡片（2026-11-09，按设计稿：列表页的“X运行”卡片 + 学院“待我审批的变更”） ----

BOARD_STATES = {'project': ('FILED', 'CLOSE_COLLEGE', 'CLOSE_REVIEW'), 'course': ('ACTIVE', STOPPED),
                'base': ('DRAFT', 'ACTIVE', STOPPED), 'trainer': ('ACTIVE', STOPPED)}
BOARD_LIMIT = 24


def _board_rows(db, a, kind):
    if kind == 'project':
        q = select(SocialProject).where(SocialProject.state.in_(BOARD_STATES[kind]))
        if a.role.kind == 'teacher':
            q = q.where(SocialProject.owner_id == a.id)
        elif a.role.kind in ('college', 'school'):
            q = q.where(SocialProject.org_id.in_(a.org_ids or {''}))
        return db.scalars(q.order_by(SocialProject.created_at.desc())).all()
    q = select(SocialResource).where(SocialResource.kind == RESOURCE_KIND[kind], SocialResource.state.in_(BOARD_STATES[kind]))
    if a.role.kind in ('college', 'school'):
        q = q.where(SocialResource.org_id.in_(a.org_ids or {''}))
    rows = db.scalars(q.order_by(SocialResource.created_at.desc())).all()
    # 学院直接登记、还没提交的申请草稿不算运行中的档案。
    return [r for r in rows if not ((r.data or {}).get('application') and r.state == 'DRAFT')]


def _card(db, a, kind, obj):
    v = view(db, a, kind, obj)
    d = obj.data or {}
    if kind == 'project':
        sub = [CATEGORY.get(d.get('category'), ''), d['start_date'] + ' 至 ' + d['end_date']]
    elif kind == 'course':
        sub = [(str(d.get('hours')) + ' 学时') if d.get('hours') not in (None, '') else '', d.get('teacher_name') or '']
    elif kind == 'base':
        sub = [d.get('location') or '', label_of('multi', d.get('usages'), BASE_USAGE)]
    else:
        sub = [d.get('unit') or '', label_of('multi', d.get('directions'), DIRECTIONS)]
    pending = v['pending_change']
    return {'type': kind, 'id': obj.id, 'name': v['name'], 'state': obj.state, 'running': v['running'],
            'state_label': '变更审批中' if pending else v['state_label'], 'sub': ' · '.join(x for x in sub if x),
            'stats': v['stats'][:3], 'remind': (v['reminders'] or [''])[0],
            'pending': pending['summary'] + '（' + pending['state_label'] + '）' if pending else ''}


def board(db, a, kind):
    if kind not in TYPES:
        raise HTTPException(422, '档案类型不支持')
    cards = []
    total = 0
    for obj in _board_rows(db, a, kind):
        try:
            check_access(db, a, kind, obj)
        except HTTPException:
            continue
        total += 1
        if len(cards) < BOARD_LIMIT:
            cards.append(_card(db, a, kind, obj))
    # 要处理的排前面：在审变更、提醒，其余保持新的在前。
    cards.sort(key=lambda c: (not c['pending'] and not c['remind'], not c['running']))
    changes = []
    for todo in change_todos(db, a):
        change = db.get(SocialResource, todo['id'])
        if change is None or change.data.get('target_type') != kind:
            continue
        who = db.get(User, change.data.get('teacher_id') or change.data['created_by'])
        changes.append({'id': change.id, 'version': change.version, 'state': change.state, 'name': change.data['target_name'],
                        'target_id': change.data.get('target_id'), 'who': who.name if who else '', 'on': str(change.created_at)[:10],
                        'reason': change.data.get('reason') or '', 'level_label': CHANGE_LEVEL_LABEL[change.data['level']],
                        'state_label': change_state_label(change),
                        'rows': [{'label': r.get('label'), 'from_text': r.get('from_text'), 'to_text': r.get('to_text')} for r in change.data.get('rows') or []]})
    return {'type': kind, 'type_label': TYPES[kind], 'cards': cards, 'total': total, 'changes': changes}


# ---- 2026-11-09 设计图 v2：老师“我的X”三步列表、学院和学校“待我审批”、积分预估 ----
# 状态只用 6 个：草稿、审批中、运行中、变更中、结项中（课程/基地/师资叫“停用中”）、已结项（“已停用”）。

STATUS6 = {'draft': '草稿', 'review': '审批中', 'run': '运行中', 'change': '变更中', 'closing': '结项中', 'done': '已结项'}
STAGE_OF = {'draft': 'apply', 'review': 'apply', 'run': 'run', 'change': 'run', 'closing': 'close', 'done': 'close'}
REVIEW_STATES = ('COLLEGE', 'SUBMITTED', 'DEPT', 'SCHOOL', 'HR', 'JWC')


def status6(db, kind, obj):
    s = obj.state
    if kind == 'project':
        if s in ('DRAFT', 'RETURNED', 'WITHDRAWN'):
            return 'draft'
        if s in ('COLLEGE', 'SUBMITTED'):
            return 'review'
        if s in ('CLOSE_COLLEGE', 'CLOSE_REVIEW'):
            return 'closing'
        if s == 'CLOSED':
            return 'done'
        return 'change' if pending_change(db, kind, obj) is not None else 'run'
    if s in ('RETURNED', 'WITHDRAWN'):
        return 'draft'
    if s in REVIEW_STATES:
        return 'review'
    if s == STOPPED:
        return 'done'
    if running(kind, obj):
        return 'change' if pending_change(db, kind, obj) is not None else 'run'
    return 'draft'


def status_label(kind, code):
    if kind != 'project' and code in ('closing', 'done'):
        return '停用中' if code == 'closing' else '已停用'
    return STATUS6[code]


def last_return(db, kind, obj):
    """最近一次退回的原因和退回人（还处在退回后的状态时才有意义）。"""
    for ev in reversed(events(db, kind, obj)):
        h = (ev.after or {}).get('handling') or {}
        if h.get('decision') == 'return':
            return {'reason': ev.reason or '', 'by': ev.actor_name or '', 'on': str(ev.created_at)[:10], 'flow': h.get('flow')}
        if h.get('decision') in ('submit', 'approve', 'refile'):
            return None
    return None


def active_policy(db):
    """现行口径；学校办法没批、没有启用的口径时，用最新的草稿口径试行（和老师申报时的试行口径一致）。"""
    from .social_models import SocialPolicy
    for state in ('ACTIVE', 'DRAFT'):
        found = db.scalar(select(SocialPolicy).where(SocialPolicy.state == state).order_by(SocialPolicy.created_at.desc()).limit(1))
        if found is not None:
            return found
    return None


def points_estimate(db, project):
    """按学校现行社会培训积分口径（social_training.point_trial 的同一套公式）预估每位校内老师的积分。
    只用于显示“预计积分 / 将记积分”；正式积分仍以积分申报审批归档为准。口径未启用时返回 None。"""
    from . import social_training as st
    policy = active_policy(db)
    cfg = (policy.data if policy else None) or {}
    if not cfg.get('cap_mode'):
        return None
    p = project.data or {}
    D = st.D
    try:
        standard = D(30 if p.get('class_type') == 'technical' else 50)
        level = D({'province': '1.2', 'city': '1.1', 'school': '1.0'}[p.get('level') or 'school'])
        scene = D({'dispatched': '1.3', 'full_day': '1.1', 'ordinary': '1.0'}[p.get('scene') or 'ordinary'])
    except KeyError:
        return None
    out = {}
    for u in st.units(db, project.id):
        count = st.unit_counts(u.data)['effective']
        ratio = D(count) / standard
        base = min(ratio, D(2)) if cfg.get('cap_mode') == 'ratio_cap' else (D(2) if count > standard else ratio)
        for t in u.data.get('teachers') or []:
            if t.get('staff_type') == 'external' or not t.get('teacher_id'):
                continue
            role = D({'lecturer': '1', 'instructor': '0.8', 'manager': '0.6'}.get(t.get('role'), '1'))
            out[t['teacher_id']] = out.get(t['teacher_id'], D(0)) + base * level * scene * role
    return {k: st.number(v) for k, v in out.items()}


def points_booked(db, project):
    """已归档入账的社会培训积分（按老师）。"""
    from .social_models import SocialClaim
    out = {}
    from . import social_training as st
    for c in db.scalars(select(SocialClaim).where(SocialClaim.project_id == project.id, SocialClaim.state == 'ARCHIVED')):
        if ((c.snapshot or {}).get('trial') or {}).get('total') is not None:
            teaching, auxiliary = st.claim_points(c)  # 审批中改过的以最终认定为准
            out[c.teacher_id] = str(Decimal(str(out.get(c.teacher_id, 0))) + teaching + auxiliary)
    return out


def points_line(db, project):
    est = points_estimate(db, project)
    if not est:
        return ''
    names = dict(db.execute(select(User.id, User.name).where(User.id.in_(list(est)))).all())
    order = sorted(est, key=lambda k: (k != project.owner_id, names.get(k, '')))
    return '、'.join(names.get(k, k) + ('（负责人）' if k == project.owner_id else '') + ' ' + est[k] + ' 分' for k in order)


def close_gaps(db, project):
    """结项前查缺：按积分口径说明缺了会怎样。"""
    from . import social_training as st
    gaps = []
    d = project.data or {}
    if d.get('end_date') and d['end_date'] > school_today().isoformat():
        gaps.append('培训要到 ' + d['end_date'] + ' 才结束，结束后才能结项')
    if d.get('report_pending'):
        from .social_schemas import application_blockers
        if issues := application_blockers(d):
            gaps.append('还要补上报信息：' + '、'.join(i.replace('请填写', '').replace('请选择', '') for i in issues) + '，不补不能结项')
    # 2026-11-09（9e98fb3 起）：老师结项不再被参训明细拦，明细由学院在审核结项时导入，学院、学校通过前必须有。
    files = st.attachments(db, 'social_project', project.id)
    names = [str(getattr(f, 'name', '') or (f.get('name') if isinstance(f, dict) else '')) for f in files]
    if not any(('签到' in n or '名册' in n or '名单' in n) for n in names):
        gaps.append('缺签到表或学员名册，参训人次不能认定，不计积分')
    if not any(n.lower().endswith(('.jpg', '.jpeg', '.png', '.heic', '.webp')) for n in names):
        gaps.append('缺现场照片，过程材料不全')
    if (project.data or {}).get('category') == 'subsidy' and not any('报送' in n or '凭证' in n for n in names):
        gaps.append('缺报送凭证，补贴性培训不计积分')
    return gaps


def close_notes(db, project):
    """结项时只提示、不拦的事：参训明细由老师上传 Excel，学院、学校通过前必须有。"""
    from . import social_training as st
    return [] if st.units(db, project.id) else ['还没上传参训明细表']


def _date_line(kind, obj):
    d = obj.data or {}
    if kind == 'project':
        return (d.get('start_date') or '') + ' 至 ' + (d.get('end_date') or '')
    for key, label in (('effective_on', '生效 '), ('established_on', '设立 ')):
        if d.get(key):
            return label + str(d[key])
    return '提交 ' + str(obj.created_at)[:10]


def _todo(db, a, kind, obj, code, lead):
    ident = kind + '|' + obj.id
    if code == 'draft':
        back = last_return(db, kind, obj)
        act = 'social-detail' if kind == 'project' else 'app-edit'
        aid = 'social_project|' + obj.id if kind == 'project' else obj.id
        if back and back['reason']:
            return {'text': '被退回：' + back['reason'], 'act': act, 'id': aid, 'btn': '修改后重新提交', 'tone': 'warn', 'rejected': back}
        return {'text': '还没提交', 'act': act, 'id': aid, 'btn': '继续填写', 'tone': 'warn'}
    if code == 'review':
        return {'text': ap.LEVEL_STATES.get(obj.state) or ('待学校备案' if obj.state == 'SUBMITTED' else '审批中'), 'tone': 'info'}
    if code == 'closing':
        return {'text': {'CLOSE_COLLEGE': '待学院结项审核', 'CLOSE_REVIEW': '待学校结项核验'}.get(obj.state, '停用审批中'), 'tone': 'info'}
    if code == 'done':
        return None
    if kind == 'project' and lead and obj.state == 'FILED' and (obj.data or {}).get('end_date', '9999') < school_today().isoformat():
        back = last_return(db, kind, obj)
        if back and back.get('flow') == 'project_close':
            return {'text': '结项被退回：' + back['reason'], 'act': 'life-close', 'id': ident, 'btn': '重新结项', 'tone': 'warn'}
        return {'text': '培训已结束，去结项', 'act': 'life-close', 'id': ident, 'btn': '去结项', 'tone': 'warn'}
    if code == 'change':
        pc = pending_change(db, kind, obj)
        return {'text': '变更待审批：' + (pc.data.get('summary') if pc else ''), 'act': 'life-change-view', 'id': pc.id if pc else '', 'btn': '查看', 'tone': 'info'}
    if kind in ('base', 'trainer') and school_today().month >= 9 and str(school_today().year) not in ((obj.data or {}).get('annual') or {}):
        return {'text': '请做 ' + str(school_today().year) + ' 年度确认', 'act': 'life-annual', 'id': ident, 'btn': '年度确认', 'tone': 'warn'}
    return None


def my_items(db, a, kind):
    """老师“我的X”：本人负责（申请）的和本人参与授课的，按三步分好。"""
    from . import applications as apps
    from . import social_training as st
    if kind not in TYPES:
        raise HTTPException(422, '档案类型不支持')
    rows = []
    if kind == 'project':
        member_ids = st.participated_project_ids(db, a.id)
        q = select(SocialProject).where(SocialProject.state != 'DELETED')
        for obj in db.scalars(q.where((SocialProject.owner_id == a.id) | (SocialProject.id.in_(member_ids or {''})))):
            rows.append((obj, obj.owner_id == a.id))
    else:
        for obj in db.scalars(select(SocialResource).where(SocialResource.kind == RESOURCE_KIND[kind], SocialResource.state != 'DELETED')):
            d = obj.data or {}
            if a.id in {d.get('teacher_id'), d.get('created_by')} and (apps.is_application(obj) or running(kind, obj) or obj.state == STOPPED):
                rows.append((obj, True))
    items = []
    for obj, lead in rows:
        code = status6(db, kind, obj)
        todo = _todo(db, a, kind, obj, code, lead)
        items.append({'type': kind, 'id': obj.id, 'name': name_of(kind, obj), 'state': obj.state, 'status': code, 'status_label': status_label(kind, code),
                      'stage': STAGE_OF[code], 'dates': _date_line(kind, obj), 'lead': lead, 'todo': todo,
                      'again': kind == 'project' and lead and code == 'done', 'updated_at': str(apps.last_event_at(db, obj) or obj.created_at)})
    items.sort(key=lambda x: x['updated_at'], reverse=True)
    items.sort(key=lambda x: x['todo'] is None or x['todo'].get('tone') != 'warn')
    return {'type': kind, 'items': items}


def approval_queue(db, a, kind):
    """学院、学校“待我审批”：立项（申报/备案）、变更、结项。只列本人这一级能办的。"""
    from . import applications as apps
    from . import social_training as st
    if kind not in TYPES:
        raise HTTPException(422, '档案类型不支持')
    out = []
    names = {}

    def who_name(uid):
        if uid not in names:
            u = db.get(User, uid) if uid else None
            names[uid] = u.name if u else ''
        return names[uid]
    if kind == 'project':
        for p in db.scalars(select(SocialProject).where(SocialProject.state.in_(('COLLEGE', 'SUBMITTED', 'CLOSE_COLLEGE', 'CLOSE_REVIEW')))):
            owner = db.get(User, p.owner_id)
            if p.state in ('COLLEGE', 'CLOSE_COLLEGE'):
                if a.role.kind != 'college' or p.org_id not in a.org_ids:
                    continue
                try:
                    ap.check_handler(db, a, owner, 'college', p.org_id)
                except HTTPException:
                    continue
            elif not st.may_review(db, a, p):
                continue
            closing = p.state in ('CLOSE_COLLEGE', 'CLOSE_REVIEW')
            d = p.data or {}
            summary = CATEGORY.get(d.get('category'), '') + ' · ' + d.get('start_date', '') + ' 至 ' + d.get('end_date', '')
            if closing:
                summary = '满意度 ' + str((p.closeout or {}).get('satisfaction', '—')) + '% · 材料 ' + str(len(st.attachments(db, 'social_project', p.id))) + ' 份'
            action = {'COLLEGE': 'approve', 'CLOSE_COLLEGE': 'approve', 'SUBMITTED': 'file', 'CLOSE_REVIEW': 'close'}[p.state]
            unit_count = len(st.units(db, p.id)) if closing else None
            out.append({'kind': 'close' if closing else 'apply', 'label': ('结项核验' if p.state == 'CLOSE_REVIEW' else '结项') if closing else ('备案' if p.state == 'SUBMITTED' else '立项'),
                        'type': kind, 'id': p.id, 'name': d.get('name', ''), 'who': who_name(p.owner_id), 'on': str(apps.last_event_at(db, p) or p.created_at)[:10],
                        'summary': summary, 'action': action, 'version': p.version, 'state': p.state, 'units': unit_count,
                        'batch': (action == 'approve' and not (closing and not unit_count)) or (action == 'file' and not (d.get('category') == 'subsidy' or d.get('high_risk')))})
    else:
        for obj in db.scalars(select(SocialResource).where(SocialResource.kind == RESOURCE_KIND[kind], SocialResource.state.in_(apps.PENDING_STATES))):
            if not apps.is_application(obj):
                continue
            flow = apps.flow_of(obj)
            level = ap.level_of(flow, obj.state)
            if not level:
                continue
            applicant = apps.applicant_of(db, obj)
            try:
                ap.check_handler(db, a, applicant, level, obj.org_id)
            except HTTPException:
                continue
            out.append({'kind': 'apply', 'label': {'college': '申报', 'school': '入库' if kind == 'course' else '审批', 'hr': '认定', 'jwc': '备案', 'dept': '申报'}.get(level, '申报'),
                        'type': kind, 'id': obj.id, 'name': obj.name, 'who': applicant.name if applicant else '', 'on': str(obj.created_at)[:10],
                        'summary': ap.FLOWS[flow]['label'], 'action': 'approve', 'version': obj.version,
                        # 基地到学校认定时若申报没填认定依据，要审批人补，不进批量。
                        'needs_basis': kind == 'base' and level == 'school' and not str((obj.data or {}).get('recognition') or '').strip(),
                        'batch': level not in ('hr', 'jwc') and not (kind == 'base' and level == 'school' and not str((obj.data or {}).get('recognition') or '').strip())})
    for todo in change_todos(db, a):
        change = db.get(SocialResource, todo['id'])
        if change is None or change.data.get('target_type') != kind:
            continue
        lv = ap.level_of(change.data['flow'], change.state)
        out.append({'kind': 'change', 'label': '变更', 'type': kind, 'id': change.id, 'name': change.data['target_name'],
                    'who': who_name(change.data.get('teacher_id') or change.data.get('created_by')), 'on': str(change.created_at)[:10],
                    'summary': change.data.get('summary', ''), 'action': 'approve', 'version': change.version, 'batch': lv not in ('hr', 'jwc'),
                    'rows': [{'label': r.get('label'), 'from_text': r.get('from_text'), 'to_text': r.get('to_text')} for r in change.data.get('rows') or []],
                    'reason': change.data.get('reason') or ''})
    out.sort(key=lambda x: x['on'], reverse=True)
    return {'type': kind, 'items': out}


def require_close_view(a, project):
    """结项核验资料（到账收入、财务凭据、留存、人员支出，各位老师的预计积分）只给项目负责人和所属学院、学校看；
    参与授课的老师、教研室负责人不能通过运行档案接口绕过系统对他们的屏蔽。"""
    if a.id == project.owner_id or is_manager(a, project):
        return
    raise HTTPException(403, '结项核验资料只有项目负责人和所属学院、学校可以查看')


def close_review(db, a, project):
    """结项审批页：运行汇总、平铺材料、将记积分。"""
    require_close_view(a, project)
    from . import social_training as st
    v = view(db, a, 'project', project)
    files = st.evidence(db, 'social_project', project.id)
    return {'archive': v, 'files': files, 'points': points_line(db, project), 'closeout': serial(project.closeout or {}),
            'units': len(st.units(db, project.id)), 'expected_income': serial((project.data or {}).get('expected_income')), 'state': project.state}


def points_view(db, a, project):
    """详情页“运行汇总”里的积分：已结项且已归档的显示已记积分，否则按现行口径预估。"""
    booked = points_booked(db, project)
    if project.state == 'CLOSED' and booked:
        full = a.id == project.owner_id or is_manager(a, project)
        return {'label': '已记积分', 'value': booked.get(a.id, '0'), 'line': ('、'.join(booked.values()) and points_line(db, project)) if full else ''}
    est = points_estimate(db, project)
    if est is None:
        return {'label': '预计积分', 'value': '口径未启用', 'line': ''}
    full = a.id == project.owner_id or is_manager(a, project)  # 别人的预计积分只给负责人和学院、学校看
    return {'label': '预计积分', 'value': str(sum(Decimal(v) for v in est.values())) if is_manager(a, project) else est.get(a.id, '0'),
            'line': points_line(db, project) if full else ''}
