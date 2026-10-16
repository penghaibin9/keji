"""Deterministic school calculations and scoped workflows; no policy inferred from missing data."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP, ROUND_FLOOR
from calendar import monthrange
from fastapi import HTTPException
from sqlalchemy import select, func, cast, String, or_
from .core import serial, digest, workflow, check_version, require_open_period, archive_exists, school_today
from .models import User, Org, Role, Setting, Attachment, WorkflowEvent, PointEntry, PointBalance, Period
from .reference_data import TrainingProjectMaster, TrainingCourseMaster
from .social_models import SocialProject, SocialUnit, SocialPolicy, SocialClaim, SocialAnnual, SocialResource

D = Decimal
STATES = {'DRAFT':'草稿', 'SUBMITTED':'待院长初审', 'DEAN':'待归口复审', 'COORDINATOR':'待分管副校长审批',
          'APPROVED':'待教学秘书归档', 'ARCHIVED':'已归档', 'FILED':'已备案', 'CLOSE_REVIEW':'待结项核验',
          'CLOSED':'已结项', 'RETURNED':'退回补正', 'REVIEW':'待职能部门核验', 'COMMITTEE':'待委员会评分',
          'PUBLIC':'公示中', 'ACTIVE':'已确认启用', 'VOID':'已作废',
          'DEPT':'待教研室审核', 'COLLEGE':'待学院审批', 'SCHOOL':'待学校审批', 'CLOSE_COLLEGE':'待学院结项核验', 'WITHDRAWN':'已撤回'}
REVIEW_STATES = {'DRAFT':'待发送教师','TEACHER':'待教师回应','COLLEGE':'待学院裁定','CLOSED':'已办结'}
DUTIES = {'dean':'二级学院院长','coordinator':'归口学院复审','vice_president':'分管副校长','secretary':'教学秘书',
          'finance':'财务核验','academic':'成果核验','discipline':'纪检核验','committee':'委员会评审'}
KINDS = {'social_project':SocialProject, 'social_claim':SocialClaim, 'social_annual':SocialAnnual,
         'social_policy':SocialPolicy, 'social_resource':SocialResource}
DECISIONS = {'cap_mode':'单次基数封顶', 'person_day_unit':'人天式核算单元', 'precision':'单元积分及汇总小数位',
             'rounding':'积分舍入方式', 'step_mode':'不足计分步长的处理', 'annual_model':'学院两套考核的关系',
             'bonus_pool':'加分合并方式', 'total_cap':'年度总分上限', 'grade_mode':'正式等级',
             'satisfaction_inclusive':'恰好95%满意度', 'achievement_dedup':'成果去重',
             'auxiliary_overlap':'辅助工作是否重复计分', 'title_scope':'职称折算积分范围',
             'title_precision':'职称折算小数位','title_rounding':'职称折算舍入','resubmission_mode':'退回补正期限口径',
             'organization_basis':'学院年度人次口径','effective_date':'适用开始日期','date_basis':'跨年归属日期'}
# 推荐口径仅用于生成待确认草稿；interpretation_reference 留空，学校书面确认前不能启用。
RECOMMENDED_POLICY = {'cap_mode':'ratio_cap', 'person_day_unit':'daily', 'precision':2, 'rounding':'half_up', 'step_mode':'full_steps',
                      'annual_model':'four_indicators', 'bonus_pool':'all_bonus_shared_ten', 'total_cap':110, 'grade_mode':'four',
                      'satisfaction_inclusive':False, 'achievement_dedup':'highest_per_reference', 'auxiliary_overlap':'exclusive',
                      'title_scope':'all', 'title_precision':2, 'title_rounding':'half_up', 'resubmission_mode':'original_submission',
                      'organization_basis':'project_units', 'effective_date':'2026-08-01', 'date_basis':'closeout',
                      'calendar_start':None, 'calendar_end':None, 'holidays':[], 'workdays':[], 'calendar_reference':'', 'interpretation_reference':''}


def today():
    return school_today()


def state_label(obj):
    if isinstance(obj,SocialResource) and obj.kind in ('course_apply','base') and (obj.data or {}).get('application'):
        from .applications import state_label as application_label
        return application_label(obj)
    if isinstance(obj,SocialResource) and obj.kind=='point_report' and obj.state=='VOID':return '已被新公示替代'
    if isinstance(obj,SocialResource) and obj.kind in {'base','achievement','course_resource'} and obj.state=='DRAFT':return '待补认定日期' if obj.kind=='achievement' and not obj.data.get('confirmed_on') else '已登记'
    if isinstance(obj,SocialPolicy) and obj.state=='DRAFT':return '执行口径待确认'
    if isinstance(obj,SocialResource) and obj.kind=='point_review':return REVIEW_STATES.get(obj.state,'待核验')
    if obj.state=='SUBMITTED':
        if isinstance(obj,SocialProject):return '待审核备案'
        if isinstance(obj,SocialResource) and obj.kind=='point_report':return '待归口复核'
    return STATES.get(obj.state,'待核验')


def number(value):
    return str(D(str(value)).quantize(D('0.01'), rounding=ROUND_HALF_UP))


def assignments(db):
    setting = db.get(Setting, 'social_training_duties')
    return setting.value if setting else {}


CONFLICTS_KEY = 'social_conflicts'


def conflicts(db):
    setting = db.get(Setting, CONFLICTS_KEY)
    return [x for x in (setting.value if setting else []) if x.get('active', True)]


def duty(db, actor, code, owner=None, org=None):
    actor.require('assessment.review')
    if actor.id not in assignments(db).get(code, []): raise HTTPException(403, '尚未获授'+DUTIES[code]+'职责')
    check_conflicts(db,actor,owner,org)


def check_conflicts(db, actor, owner=None, org=None):
    if owner == actor.id: raise HTTPException(403, '须回避本人申报事项')
    # 管理办法第二十八条：本人申报过利益冲突的老师或学院，须回避，由其他人员办理。
    for x in conflicts(db):
        if x['user_id'] == actor.id and ((x['target_kind'] == 'teacher' and owner and x['target_id'] == owner) or (x['target_kind'] == 'org' and org and x['target_id'] == org)):
            raise HTTPException(403, '你已申报与“'+x['target_name']+'”存在利益冲突，须回避，请由其他人员办理')


def check_report_conflicts(db, actor, rows):
    for row in rows:
        claim=db.get(SocialClaim,row['claim_id']);project=db.get(SocialProject,claim.project_id) if claim else None
        if not project:raise HTTPException(409,'汇总来源已缺失，请重新核验')
        check_conflicts(db,actor,claim.teacher_id,project.org_id)
        check_project_conflicts(db,actor,project)


def check_project_conflicts(db, actor, project):
    check_conflicts(db,actor,project.owner_id,project.org_id)
    teachers={t['teacher_id'] for unit in units(db,project.id) for t in unit.data['teachers'] if t.get('staff_type')=='internal'}
    for teacher_id in teachers:
        if db.get(User,teacher_id):check_conflicts(db,actor,teacher_id,project.org_id)


def review_staff_blockers(db,obj):
    """发送前按实际授权及回避规则确认后续每个环节有人可办。"""
    project=db.get(SocialProject,db.get(SocialClaim,obj.data['claim_id']).project_id)
    blocked=[]
    for code in ('dean','coordinator','vice_president','secretary'):
        available=False
        for ident in assignments(db).get(code,[]):
            if ident in {obj.data['created_by'],obj.data['teacher_id']}:continue
            user=db.get(User,ident)
            for actor in active_identities(db,user):
                try:
                    actor.require('points.read');actor.check_teacher(db,obj.data['teacher_id'])
                    duty(db,actor,code,obj.data['teacher_id'],obj.org_id);check_project_conflicts(db,actor,project)
                except HTTPException:continue
                available=True;break
            if available:break
        if not available:blocked.append(DUTIES[code]+'环节没有具备权限且无需回避的办理人，请学校管理员在社会培训职责设置中配置替代人员')
    return blocked


def active_identities(db,user):
    from .identities import extras_for, identity_actor
    if not user:return
    for ident in ['',*[x['id'] for x in extras_for(db,user.id)]]:
        try:
            actor=identity_actor(db,user,ident)
            if actor.org.active:yield actor
        except HTTPException:continue


def duty_eligible(db,user,admin,code):
    school=code in {'vice_president','coordinator','committee','finance','academic','discipline'}
    return any(a.org.id in admin.org_ids and 'assessment.review' in a.permissions
               and (not school or a.role.kind=='school') for a in active_identities(db,user))


def annual_achievements(db,org_id,period):
    rows=db.scalars(select(SocialResource).where(SocialResource.kind=='achievement',SocialResource.org_id==org_id).order_by(SocialResource.code))
    result=[]
    for r in rows:
        confirmed=achievement_date(db,r)
        if r.data.get('source')=='satisfaction' or not confirmed or not period.start_date<=confirmed<=period.end_date:continue
        result.append({'reference':r.code,'name':r.name,'level':r.data['level'],'confirmed_on':confirmed.isoformat(),'recognition_reference':r.data.get('recognition','')})
    return result


def check_annual_conflicts(db, actor, annual):
    period=db.get(Period,annual.period_id)
    for project in confirmed_projects(db,annual.org_id,period.start_date,period.end_date):check_project_conflicts(db,actor,project)


def scoped(db, actor, kind, ident, write=False, allow_participant=False):
    model = KINDS.get(kind)
    if not model: raise HTTPException(422, '业务类型不支持')
    obj = db.get(model, ident)
    if not obj: raise HTTPException(404, '业务记录不存在')
    if kind=='social_resource' and obj.kind in ('course_apply','base') and (obj.data or {}).get('application'):
        # 老师发起的申请：申请人、本级办理人和组织范围内的学院、学校可看；申请人在审批中或待补正时可补传附件。
        from .applications import read_check, PENDING_STATES
        read_check(db, actor, obj)
        if write and not (actor.id in {obj.data.get('teacher_id'), obj.data.get('created_by')} and obj.state in ('RETURNED','WITHDRAWN',*PENDING_STATES)):
            raise HTTPException(409, '申请已办结或不由你补正，不能修改')
        return obj
    if kind=='social_resource' and obj.kind not in {'base','achievement','course_resource','ledger','correction','point_review','point_report'}:
        raise HTTPException(403,'资源类型尚未配置授权，拒绝读取')
    if kind=='social_resource' and obj.kind=='course_resource' and not db.scalar(select(SocialResource.id).where(SocialResource.id==ident,course_resource_scope(db,actor))):
        raise HTTPException(403,'课程资源超出本人或本教研室授权范围')
    if kind=='social_annual':actor.require('assessment.read')
    if kind=='social_resource' and obj.kind=='point_report':actor.require('points.read')
    # 学院台账含全院教师人次分配，只给学院和学校看（与台账专用接口 require_ledger_role 一致），详情、附件下载都经过这里
    if kind=='social_resource' and obj.kind=='ledger' and actor.role.kind not in ('college','school'):raise HTTPException(403,'学院台账由学院报送、学校核定；教师请在“个人培训”查看分给本人的人次')
    if kind == 'social_policy':
        if write: actor.require('rules.manage')
    elif kind == 'social_claim':
        actor.require('points.read')
        actor.check_teacher(db, obj.teacher_id)
    else:
        org_id = obj.org_id
        if kind == 'social_resource' and obj.kind in ('correction', 'point_review'):
            actor.require('points.read')
            actor.check_teacher(db,obj.data['teacher_id'])
            if obj.kind=='point_review' and obj.state=='DRAFT' and actor.id!=obj.data.get('created_by') and actor.role.kind=='teacher':raise HTTPException(404,'业务记录不存在')
        elif kind == 'social_resource' and not write and actor.role.kind=='teacher':
            parent=actor.org.parent_id;college=db.get(Org,parent)
            allowed={parent}
            if obj.kind=='point_report' and obj.state in {'PUBLIC','ARCHIVED'} and college:allowed.add(college.parent_id)
            if org_id not in allowed:raise HTTPException(403,'资源超出授权范围')
            if obj.kind=='point_report' and obj.state not in {'PUBLIC','ARCHIVED'}:raise HTTPException(403,'积分汇总尚未发布')
        elif actor.role.kind == 'teacher':
            if kind=='social_annual' and not write and obj.state in {'PUBLIC','ARCHIVED'} and obj.org_id==actor.org.parent_id:pass
            elif kind=='social_project' and not write and allow_participant and obj.org_id==actor.org.parent_id and any(t['teacher_id']==actor.id for u in units(db,obj.id) for t in u.data['teachers']):pass
            elif kind != 'social_project' or obj.owner_id != actor.id: raise HTTPException(403, '业务超出本人范围')
        elif actor.role.kind == 'dept' and not write and org_id == actor.org.parent_id and (
                (kind == 'social_project' and allow_participant and obj.id in dept_project_ids(db, actor))
                or (kind == 'social_resource' and obj.kind in DEPT_READABLE_RESOURCES)):pass
        elif org_id not in actor.org_ids: raise HTTPException(403, '业务超出组织授权范围')
    if write:
        if obj.state in {'ARCHIVED', 'ACTIVE', 'CLOSED', 'VOID'}: raise HTTPException(409, '已生效、已归档或已作废依据不可覆盖')
        if kind not in {'social_claim', 'social_policy'} and not (kind=='social_resource' and obj.kind in ('correction','point_review')):
            actor.require('records.write')
    return obj


def attachments(db, kind, ident):
    return db.scalars(select(Attachment).where(Attachment.object_type == kind, Attachment.object_id == ident).order_by(Attachment.id)).all()


def evidence(db, kind, ident):
    return [{'id':x.id, 'name':x.name, 'sha256':x.sha256, 'size':x.size, 'mime':x.mime} for x in attachments(db,kind,ident)]


def require_evidence(db, kind, ident):
    files = evidence(db, kind, ident)
    if not files: raise HTTPException(409, '请先上传当前业务的正式佐证附件')
    return files


def dept_project_ids(db, actor):
    """教研室负责人只读：所属学院项目中，负责人或核算单元里的授课教师属于本教研室的项目（招标第6项：教研室查看本教研室教师培训数据）。"""
    teachers = set(actor.teacher_ids)
    if actor.role.kind != 'dept' or not teachers or not actor.org.parent_id: return set()
    cache = db.info.setdefault('dept_project_ids', {})
    if actor.id in cache: return cache[actor.id]
    projects = dict(db.execute(select(SocialProject.id, SocialProject.owner_id).where(SocialProject.org_id == actor.org.parent_id)).all())
    ids = {pid for pid, owner in projects.items() if owner in teachers}
    for pid, data in db.execute(select(SocialUnit.project_id, SocialUnit.data).where(SocialUnit.project_id.in_(list(projects)))).all() if projects else []:
        if pid not in ids and any(t.get('teacher_id') in teachers for t in (data or {}).get('teachers', [])): ids.add(pid)
    cache[actor.id] = ids
    return ids


DEPT_READABLE_RESOURCES = {'base', 'achievement', 'course_resource'}


def unit_membership(db,teacher_id):
    if db.bind.dialect.name=='mysql':
        member=func.json_contains(SocialUnit.data,func.json_object('teacher_id',teacher_id),'$.teachers')==1
    elif db.bind.dialect.name=='sqlite':
        teachers=func.json_each(SocialUnit.data,'$.teachers').table_valued('value',joins_implicitly=True)
        member=select(1).select_from(teachers).where(func.json_extract(teachers.c.value,'$.teacher_id')==teacher_id).exists()
    else:raise HTTPException(503,'当前数据库尚不支持参训项目检索')
    return member


def visible_projects(db,a):
    query=select(SocialProject)
    if a.role.kind=='teacher':
        member=unit_membership(db,a.id)
        participation=select(SocialUnit.id).where(SocialUnit.project_id==SocialProject.id,member).exists()
        query=query.where(SocialProject.org_id==a.org.parent_id,or_(SocialProject.owner_id==a.id,participation))
    elif a.role.kind=='dept':query=query.where(SocialProject.id.in_(dept_project_ids(db,a) or {''}))
    else:query=query.where(SocialProject.org_id.in_(a.org_ids))
    return query.order_by(SocialProject.created_at.desc(),SocialProject.id)


def visible_courses(db,a):
    query=select(TrainingCourseMaster).where(TrainingCourseMaster.active==True)
    if a.role.kind in ('teacher','dept'):
        codes=visible_projects(db,a).order_by(None).with_only_columns(SocialProject.data['code'].as_string())
        own=select(SocialResource.data['course_code'].as_string()).where(SocialResource.kind=='course_resource',SocialResource.org_id==a.org.parent_id,SocialResource.data['teacher_id'].as_string().in_(a.teacher_ids))
        query=query.where(or_(TrainingCourseMaster.project_code.in_(codes),TrainingCourseMaster.code.in_(own)))
    return query


def course_resource_scope(db,a):
    orgs=[a.org.parent_id] if a.role.kind in ('teacher','dept') else a.org_ids
    scope=SocialResource.org_id.in_(orgs)
    if a.role.kind in ('teacher','dept'):
        teacher=SocialResource.data['teacher_id'].as_string()
        scope=scope & SocialResource.data['course_code'].as_string().in_(visible_courses(db,a).with_only_columns(TrainingCourseMaster.code)) & or_(teacher.in_(a.teacher_ids),teacher.is_(None),teacher=='')
    return scope


def participated_project_ids(db, teacher_id):
    """本人在核算单元中担任授课或辅助的项目（积分只能就本人参与的项目申报）。"""
    rows = db.execute(select(SocialUnit.project_id, SocialUnit.data).where(cast(SocialUnit.data, String).contains(teacher_id, autoescape=True))).all()
    return {pid for pid, data in rows if any(t.get('teacher_id') == teacher_id for t in (data or {}).get('teachers', []))}


def units(db, project_id):
    return db.scalars(select(SocialUnit).where(SocialUnit.project_id==project_id).order_by(SocialUnit.external_key)).all()


def confirmed_projects(db, org_id, start_date, end_date):
    lower,upper=str(start_date),str(end_date)
    return [p for p in db.scalars(select(SocialProject).where(SocialProject.org_id==org_id,SocialProject.state=='CLOSED').order_by(SocialProject.id))
            if lower<=p.closeout.get('closed_on','')<=upper and p.closeout.get('finance_reference','').strip()]


def confirmed_project_income(db, org_id, start_date, end_date, date_basis='closeout'):
    if date_basis!='closeout':raise HTTPException(409,'收入归属口径尚未确认')
    return sum((D(str(p.closeout['actual_income'])) for p in confirmed_projects(db,org_id,start_date,end_date)),D(0))


def achievement_year(db, resource):
    confirmed=achievement_date(db,resource)
    return confirmed.year if confirmed else None


def achievement_date(db, resource):
    data=resource.data
    if data.get('project_id'):
        project=db.get(SocialProject,data['project_id'])
        if not project or project.state!='CLOSED' or project.org_id!=resource.org_id:return None
        value=project.closeout.get('closed_on')
    else:value=data.get('confirmed_on')
    try:return date.fromisoformat(value) if value else None
    except (ValueError,TypeError):return None


def resource_video_count(data):
    if data.get('resource_type')!='video':return 0
    count=data.get('video_count')
    return 1 if count is None else int(count)


def resolve_teacher(db, org_id, name, teacher_id=None):
    orgs={org_id};pending={org_id}
    while pending:
        pending=set(db.scalars(select(Org.id).where(Org.parent_id.in_(pending),Org.active==True)))-orgs
        orgs.update(pending)
    query=select(User).join(Role,Role.id==User.role_id).where(User.active==True,User.authorization_pending.is_(False),Role.active==True,Role.kind.in_(['teacher','dept','college','school']),User.staff_no.is_not(None),User.org_id.in_(orgs))
    if teacher_id:query=query.where(User.id==teacher_id)
    if name.strip():query=query.where(User.name==name.strip())
    elif not teacher_id:return None
    matches=db.scalars(query.limit(2)).all()
    return matches[0] if len(matches)==1 else None


def project_rule_blockers(data):
    expected={'enterprise':'city','community':'school','rural':'school'}.get(data['category'])
    if data['category']=='enterprise' and data['level']=='school':
        return ['企业定制培训应采用市级／企业专项层级，不能按校级权重备案或认定']
    if expected and data['level']!=expected and not data.get('level_basis','').strip():
        return ['项目层级与培训类别的通常口径不一致，请补充专项层级认定依据后重新审核备案']
    return []


def require_project_confirmed(project):
    if issues:=project_rule_blockers(project.data):raise HTTPException(409,'；'.join(issues))
    source=project.data.get('source',{})
    if source.get('dates_pending') or source.get('date_pending'):raise HTTPException(409,'实际培训日期尚待补充确认，不能正式提交或备案')
    if source.get('policy_pending',['level','scene'] if source.get('ledger_id') else []):raise HTTPException(409,'项目层级或培训场景尚待确认，不能正式提交或备案')
    if source.get('mode_pending'):raise HTTPException(409,'培训核算方式尚待确认，不能正式提交或备案')


def require_closeout_distribution(closeout):
    from .social_schemas import Closeout
    from pydantic import ValidationError
    try:values=Closeout.model_validate(closeout)
    except ValidationError as exc:raise HTTPException(422,'结项资料不完整或收入分配不符合规则：'+'；'.join(e['msg'] for e in exc.errors())) from None
    if not values.finance_reference.strip():raise HTTPException(422,'结项须填写有效的财务到账核验依据')
    if values.actual_income>0:
        if not values.funding_source:raise HTTPException(422,'非零收入须由财务明确资金来源')
        if values.funding_source=='other_training' and (values.retained is None or values.personnel is None):raise HTTPException(422,'其他培训收入须完整填写学校留存及人员支出')
        if values.funding_source=='government_special' and not values.funding_basis.strip():raise HTTPException(422,'政府专项资金须填写主管部门适用规定及核验依据')


def eligible(learner):
    return (not learner['full_time_student'] or learner['graduate_exception']) and all(learner[k] for k in ('signed','hours_met','full_attendance','passed')) and not learner['exclusion_reason'].strip()


def unit_counts(unit):
    valid = [r for r in unit['learners'] if eligible(r)]
    return {'effective':len(valid), 'excluded':len(unit['learners'])-len(valid), 'priority':sum(r['priority_group'] for r in valid)}


def person_day_blockers(rows):
    seen=set()
    for row in rows:
        if row['mode']!='person_day':continue
        for learner in row['learners']:
            if not eligible(learner):continue
            key=(row['event_date'],learner['reference'].strip())
            if key in seen:return ['人天式同一期同一学员同一天不能跨班重复计数，请核对学员编号并合并实际参训记录']
            seen.add(key)
    return []


def project_facts(db, project):
    rows = units(db, project.id)
    followups=project_followups(db,project.id);invalidated=any(x.get('invalidate_cohort') for x in followups)
    issues=person_day_blockers([u.data for u in rows])
    return {'project':serial(project), 'units':serial(rows), 'evidence':evidence(db,'social_project',project.id),
            'followups':followups,'invalidated':invalidated,**({'blockers':issues} if issues else {}),
            'effective':0 if invalidated else sum(unit_counts(u.data)['effective'] for u in rows),
            'priority':0 if invalidated else sum(unit_counts(u.data)['priority'] for u in rows),
            'excluded':sum(len(u.data['learners']) if invalidated else unit_counts(u.data)['excluded'] for u in rows)}


def project_followups(db,ident):
    latest={}
    for event in db.scalars(select(WorkflowEvent).where(WorkflowEvent.object_type=='social_project',WorkflowEvent.object_id==ident,WorkflowEvent.action=='投诉与项目跟踪').order_by(WorkflowEvent.created_at,WorkflowEvent.id)):
        latest[event.after['case_reference']]=event.after
    return list(latest.values())


def add_workdays(start, count, config):
    if not all(config.get(k) for k in ('calendar_start','calendar_end','calendar_reference')):
        raise HTTPException(409, '学校工作日历尚未确认')
    lower, upper = date.fromisoformat(config['calendar_start']), date.fromisoformat(config['calendar_end'])
    if not lower <= start <= upper: raise HTTPException(409, '学校工作日历未覆盖起算日期')
    holidays, workdays = set(config['holidays']), set(config['workdays'])
    current = start
    while count:
        current += timedelta(days=1)
        if current > upper: raise HTTPException(409, '学校工作日历未覆盖办理期限')
        if current.isoformat() in workdays or (current.weekday()<5 and current.isoformat() not in holidays): count -= 1
    return current


def calendar_block(config, start, count):
    try: return add_workdays(start, count, config), []
    except HTTPException as exc: return None, [exc.detail]


def missing(config, keys):
    return [DECISIONS[k]+'尚待学校书面确认' for k in keys if config.get(k) is None]


def duplicate_claim(db, project_id, teacher_id, ident=None):
    query=select(SocialClaim.id).where(SocialClaim.project_id==project_id,SocialClaim.teacher_id==teacher_id,
        SocialClaim.state.in_(['SUBMITTED','DEAN','COORDINATOR','APPROVED','ARCHIVED']))
    if ident:query=query.where(SocialClaim.id!=ident)
    return db.scalar(query.limit(1)) is not None


def point_trial(db, claim):
    project = db.get(SocialProject, claim.project_id)
    policy = db.get(SocialPolicy, claim.policy_id)
    cfg, p = policy.data, project.data
    facts = project_facts(db,project)
    invalidated=facts['invalidated']
    blockers = missing(cfg,['cap_mode','precision','rounding','effective_date','date_basis'])+project_rule_blockers(p)+facts.get('blockers',[])
    if duplicate_claim(db,project.id,claim.teacher_id,claim.id):blockers.append('同一项目已有本人审批中或已归档的积分申报，不能换考核周期重复认定；请办理原申报或追加更正')
    if p['mode']=='person_day': blockers += missing(cfg,['person_day_unit'])
    if claim.state=='RETURNED':blockers+=missing(cfg,['resubmission_mode'])
    if policy.state != 'ACTIVE': blockers.append('制度执行口径尚未正式启用')
    if not claim.data.get('recognition_form_reference'):blockers.append('学校制式积分认定表及其附件对应说明尚未提供')
    if project.state != 'CLOSED': blockers.append('项目尚未正常结项')
    if invalidated:blockers.append('正式处理决定已作废本期培训人次；已归档积分须另走更正流程')
    close = project.closeout
    deadline = None
    if close.get('closed_on'):
        closed = date.fromisoformat(close['closed_on'])
        period = db.get(Period,claim.period_id)
        if not period.start_date <= closed <= period.end_date: blockers.append('结项日期不属于申报周期；跨年处理须确认')
        if cfg.get('effective_date') and p['start_date'] < cfg['effective_date']: blockers.append('项目开始早于本规则生效日期，须单独核定')
        deadline, errors = calendar_block(cfg,closed,15);blockers += errors
        submitted_on = claim.data.get('submitted_on')
        if deadline and date.fromisoformat(submitted_on or today().isoformat()) > deadline: blockers.append('超过结项后15个工作日申报期限')
    if not facts['evidence']: blockers.append('项目佐证材料尚未上传')
    legacy=db.scalar(select(func.coalesce(func.sum(PointEntry.amount),0)).where(PointEntry.teacher_id==claim.teacher_id,PointEntry.period_id==claim.period_id,PointEntry.kind.in_(['BASE','RECALC'])))
    if legacy:blockers.append('本周期存在旧规则积分，存量衔接口径须核定后才能认定')
    if p['category']=='subsidy' and not (close.get('province_receipt') and close.get('special_evidence')): blockers.append('补贴项目报送凭证或专项材料不足')
    standard = D(30 if p['class_type']=='technical' else 50)
    level = D({'province':'1.2','city':'1.1','school':'1.0'}[p['level']])
    scene = D({'dispatched':'1.3','full_day':'1.1','ordinary':'1.0'}[p['scene']])
    details, teaching, managerial = [], D(0), D(0)
    work = []
    for u in facts['units']:
        for t in u['data']['teachers']:
            if t['teacher_id']==claim.teacher_id:
                if t['staff_type']=='external': blockers.append('外聘人员不适用本办法积分认定');continue
                work.append((u,t,0 if invalidated else unit_counts(u['data'])['effective']))
    if not work: blockers.append('缺少本人的合规工作明细')
    if p['mode']=='person_day' and cfg.get('person_day_unit')=='whole_project' and work:
        roles={t['role'] for _,t,_ in work}
        if len(roles)>1: blockers.append('整期人天核算存在岗位变化，需要学校核定')
        else: work=[(work[0][0],work[0][1],sum(n for _,_,n in work))]
    for u,t,count in work:
        ratio=D(count)/standard
        candidates={'ratio_cap':min(ratio,D(2)), 'over_standard_two':D(2) if count>standard else ratio}
        base=candidates.get(cfg.get('cap_mode'))
        role=D({'lecturer':'1','instructor':'0.8','manager':'0.6'}[t['role']])
        score=None if base is None else D(number(base*level*scene*role))
        if t['role']=='manager':
            blockers += missing(cfg,['auxiliary_overlap'])
            managerial += score or D(0)
        else: teaching += score or D(0)
        details.append({'unit':u['external_key'],'date':u['data']['event_date'],'participants':count,'standard':str(standard),
                        'level':str(level),'scene':str(scene),'role':str(role),'base_candidates':serial(candidates),'score':None if score is None else str(score),
                        'formula':f'基数 {number(base) if base is not None else "待确认：按比例最高2为"+number(candidates["ratio_cap"])+"，超标准按2为"+number(candidates["over_standard_two"])} × 层级 {level} × 场景 {scene} × 岗位 {role}（有效{count}人次，标准{standard}人）'})
    auxiliary=sum((D(x['amount']) for x in claim.data.get('auxiliary',[])),D(0))
    if auxiliary or managerial:
        blockers += missing(cfg,['auxiliary_overlap'])
        if not p.get('auxiliary_standard') or p.get('auxiliary_daily_cap') is None: blockers.append('辅助积分细则及个人每日限额尚未随项目备案')
        if managerial and auxiliary: blockers.append('管理岗位与辅助工作积分不能重复申报')
        daily={}
        for x in claim.data.get('auxiliary',[]):
            if not p['start_date']<=x['work_date']<=p['end_date']: blockers.append('辅助工作日期超出项目期间')
            daily[x['work_date']]=daily.get(x['work_date'],D(0))+D(x['amount'])
        for line in details:
            if line['role']=='0.6': daily[line['date']]=daily.get(line['date'],D(0))+D(line['score'] or 0)
        other_work=db.scalars(select(SocialClaim).where(SocialClaim.teacher_id==claim.teacher_id,SocialClaim.id!=claim.id,SocialClaim.state.in_(['SUBMITTED','DEAN','COORDINATOR','APPROVED','ARCHIVED']))).all()
        for previous in other_work:
            for row in previous.data.get('auxiliary',[]):
                if row['work_date'] in daily:daily[row['work_date']]+=D(row['amount'])
            for row in previous.snapshot.get('trial',{}).get('details',[]):
                if row['role']=='0.6' and row['date'] in daily:daily[row['date']]+=D(row['score'] or 0)
        if p.get('auxiliary_daily_cap') is not None and any(v>D(p['auxiliary_daily_cap']) for v in daily.values()): blockers.append('辅助积分超过个人每日限额')
    auxiliary += managerial
    other = db.scalars(select(SocialClaim).where(SocialClaim.project_id==project.id,SocialClaim.id!=claim.id,SocialClaim.state.in_(['SUBMITTED','DEAN','COORDINATOR','APPROVED','ARCHIVED']))).all()
    reserved=sum((D((c.snapshot.get('trial') or {}).get('auxiliary','0')) for c in other),D(0))
    if auxiliary+reserved>facts['effective']: blockers.append('全项目辅助积分超过有效培训总人次')
    computed=cfg.get('cap_mode') is not None and cfg.get('precision') is not None and cfg.get('rounding') is not None and (p['mode']!='person_day' or cfg.get('person_day_unit') is not None)
    return {'teaching':number(teaching) if computed else None,'auxiliary':number(auxiliary) if computed else None,'total':number(teaching+auxiliary) if computed else None,
            'details':details,'blockers':list(dict.fromkeys(blockers)),'deadline':serial(deadline),
            'basis':{'facts':facts,'policy':serial(policy),'claim_data':claim.data},'formal':False}


def require_unblocked(trial):
    if trial['blockers']: raise HTTPException(409, '；'.join(trial['blockers']))


def project_funding(db, projects, step_mode='full_steps'):
    out={'late':0,'overdue':0,'penalty':D(0),'details':[],'veto':[],'blockers':[]}
    for project in projects:
        close=project.closeout;follow=project_followups(db,project.id);name=project.data['name']
        closed=date.fromisoformat(close['closed_on']);month=closed.month+6
        year=closed.year+(month-1)//12;month=(month-1)%12+1
        due=date(year,month,min(closed.day,monthrange(year,month)[1]))
        settled=[x['completed_on'] for x in follow if x['kind']=='settlement' and x.get('completed_on')]
        settlement=max(settled) if settled else close.get('settlement_on')
        if (settlement and date.fromisoformat(settlement)>due) or (not settlement and today()>due):
            out['overdue']+=1
            reviews=[x for x in follow if x['kind']=='settlement' and x.get('completed_on')==settlement and x.get('settlement_result') and x.get('basis','').strip()]
            results={x['settlement_result'] for x in reviews}
            if len(results)!=1:
                out['blockers'].append(name+'：逾期结算须由财务在项目跟踪中确认不合规或批准例外；结算日期变化或结论冲突须重新核验')
            elif 'noncompliant' in results:
                out['late']+=1;out['details'].append(name+'：财务确认逾期结算不合规，扣5分；依据：'+'；'.join(x['basis'] for x in reviews))
            else:out['details'].append(name+'：财务已确认例外，本次不扣结算分；依据：'+'；'.join(x['basis'] for x in reviews))
        income=D(str(close['actual_income']));hidden=D(str(close['implicit_cost']))
        if close['location']=='onsite' and hidden>0:
            if income==0:out['blockers'].append(name+'：零收入项目存在隐性成本，扣分口径须核定')
            else:
                steps=max(D(0),hidden/income*100-20)/10
                if step_mode=='full_steps':steps=steps.to_integral_value(rounding=ROUND_FLOOR)
                penalty=steps*2;out['penalty']+=penalty
                if penalty:out['details'].append(name+'：隐性成本超额，扣'+number(penalty)+'分')
        out['veto'] += [x.get('basis') or '纪检确认违纪违规' for x in follow if x.get('annual_veto')]
    out['details']+=out['blockers']
    return out


def funding_cost(funding, other_failures, scope=None):
    blockers=list(funding.get('blockers',[]))
    if other_failures and funding.get('overdue') and scope!='other_only':
        blockers.append('原不合规次数可能已包含项目结算事项，请核对其他不合规次数（不含项目结算核验）后重新保存，避免重复扣分')
    return max(D(0),D(10)-(funding['late']+other_failures)*5-funding['penalty']),blockers


def annual_trial(db, annual):
    period=db.get(Period,annual.period_id);policy=db.get(SocialPolicy,annual.policy_id);cfg=policy.data;data=annual.data
    blockers=missing(cfg,['annual_model','bonus_pool','total_cap','grade_mode','step_mode','satisfaction_inclusive','achievement_dedup','organization_basis','precision','rounding','date_basis'])
    if policy.state!='ACTIVE':blockers.append('年度规则尚未正式启用')
    if not data.get('target_reference'):blockers.append('年度任务下达依据尚未提供')
    projects=confirmed_projects(db,annual.org_id,period.start_date,period.end_date)
    facts=[project_facts(db,p) for p in projects]
    blockers += [issue for fact in facts for issue in fact.get('blockers',[])]
    formal_veto=[x for fact in facts for x in fact['followups'] if x.get('annual_veto')]
    if formal_veto:data={**data,'confirmed_veto':True,'discipline_reference':'；'.join(x['basis'] for x in formal_veto)}
    income=confirmed_project_income(db,annual.org_id,period.start_date,period.end_date)
    participants=sum(p['effective'] for p in facts);priority=sum(p['priority'] for p in facts)
    def steps(value,unit):
        n=value/D(unit)
        return n.to_integral_value(rounding=ROUND_FLOOR) if cfg.get('step_mode')=='full_steps' else n
    metrics=[];bonus=D(0)
    for label,actual,target,base,loss_unit,loss,extra_cap in [('收入',income,data.get('income_target'),40,1,1,10),('培训人次',D(participants),data.get('participants_target'),20,10,2,5),('重点群体',D(priority),data.get('priority_target'),10,10,1,5)]:
        if target is None or D(str(target))<=0:
            blockers.append(label+'年度目标未有效下达，不能按零分或满分处理');metrics.append({'label':label,'actual':str(actual),'target':target,'base':None,'bonus':None});continue
        percent=actual/D(str(target))*100
        score=max(D(0),D(base)-steps(max(D(0),100-percent),loss_unit)*loss)
        extra=min(D(extra_cap),steps(max(D(0),percent-100),10))
        metrics.append({'label':label,'actual':str(actual),'target':str(target),'completion':number(percent),'base':number(score),'bonus':number(extra)})
        bonus+=extra
    achievements={}
    # 满意度自动成果已由项目满意度加2分体现，不再按校级成果重复计分。
    resources={x.code:x for x in db.scalars(select(SocialResource).where(SocialResource.kind=='achievement',SocialResource.org_id==annual.org_id))}
    for item in data['achievements']:
        resource=resources.get(item['reference'])
        if resource and resource.data.get('source')=='satisfaction':continue
        confirmed=achievement_date(db,resource) if resource else date.fromisoformat(item['confirmed_on']) if item.get('confirmed_on') else None
        if not confirmed or not period.start_date<=confirmed<=period.end_date:
            blockers.append('成果“'+item['name']+'”未确认属于本考核周期，不计入本次试算');continue
        if not resource and not item.get('recognition_reference','').strip():
            blockers.append('人工成果“'+item['name']+'”缺少正式认定依据，不计入本次试算');continue
        if resource and item['level']!=resource.data.get('level'):
            blockers.append('成果“'+item['name']+'”等级与已登记依据不一致');continue
        achievements[item['reference']]=max(achievements.get(item['reference'],D(0)),D({'national':10,'province':5,'school':2}[item['level']]))
    recognized=sum(achievements.values(),D(0));satisfaction=D(0)
    outcome_details=[{'label':reference,'value':number(score)+' 分，同一依据取最高等级'} for reference,score in achievements.items()]
    for p in projects:
        value=D(p.closeout['satisfaction'])
        if value>95 or (value==95 and cfg.get('satisfaction_inclusive') is True):
            satisfaction+=2;outcome_details.append({'label':p.data['name'],'value':'满意度 '+str(value)+'%，成果基础加2分'})
    # Satisfaction cannot overflow into the additional-award pool.
    results=min(D(10),recognized+satisfaction);bonus+=max(D(0),recognized-10)
    funding=project_funding(db,projects,cfg.get('step_mode'))
    cost,funding_blockers=funding_cost(funding,data['compliance_failures'],data.get('compliance_scope'));blockers+=funding_blockers
    cost_details=[{'label':'其他已确认不合规（不含项目结算核验）','value':number(D(data['compliance_failures'])*5)+' 分'}]
    cost_details += [{'label':'项目资金核验','value':value} for value in funding['details']]
    if data['confirmed_veto'] and not data['discipline_reference']:blockers.append('一票否决缺少正式处理或处分依据')
    if D(data['other_bonus']) > 0 and not data['other_bonus_basis']:blockers.append('其他加分缺少正式依据')
    cost=max(D(0),cost)
    base=sum((D(x['base']) for x in metrics if x['base'] is not None),D(0))+results+cost
    awarded=min(D(10),bonus+D(data['other_bonus']))
    total=base+awarded
    if cfg.get('total_cap') is not None:total=min(total,D(cfg['total_cap']))
    grade=None
    if cfg.get('grade_mode')=='four':grade='优秀' if total>=90 else '良好' if total>=80 else '合格' if total>=60 else '不合格'
    elif cfg.get('grade_mode')=='three':
        if cfg.get('excellent_from') is None or cfg.get('qualified_from') is None:blockers.append('三等评级门槛尚未确认')
        else:grade='优秀' if total>=D(cfg['excellent_from']) else '合格' if total>=D(cfg['qualified_from']) else '不合格'
    if data['confirmed_veto']:grade='不合格（一票否决）'
    recognized_claims=db.scalars(select(SocialClaim).join(SocialProject,SocialProject.id==SocialClaim.project_id).where(SocialProject.org_id==annual.org_id,SocialClaim.period_id==annual.period_id,SocialClaim.state=='ARCHIVED')).all()
    point_sources=[{'claim_id':c.id,'totals':serial(correction_totals(db,c))} for c in sorted(recognized_claims,key=lambda x:x.id)]
    points_total=sum((sum(D(v) for v in c['totals'].values()) for c in point_sources),D(0))
    computed=not funding_blockers and all(x['base'] is not None for x in metrics) and all(cfg.get(k) is not None for k in ('annual_model','bonus_pool','total_cap','step_mode','satisfaction_inclusive','achievement_dedup','precision','rounding'))
    return {'metrics':metrics,'achievement_base':number(results),'cost_base':None if funding_blockers else number(cost),'base':None if funding_blockers else number(base),
            'bonus_raw':number(bonus+D(data['other_bonus'])),'bonus_awarded':number(awarded) if computed else None,'total':number(total) if computed else None,
            'total_before_cap':number(base+awarded) if computed else None,'total_cap':cfg.get('total_cap'),'cost_details':cost_details,'outcome_details':outcome_details,
            'veto':data['confirmed_veto'],'veto_basis':data['discipline_reference'],'grade':grade if computed else None,'points_total':number(points_total),
            'points_average':number(points_total/data['staff_denominator']) if data.get('staff_denominator') and data.get('staff_basis') else None,'blockers':list(dict.fromkeys(blockers)),
            'basis':{'projects':facts,'policy':serial(policy),'annual_data':data,'recognized_points':point_sources},'formal':False}


def freeze(trial):
    return {'trial':trial,'sha256':digest(trial),'frozen_on':today().isoformat()}


def current_trial(db,obj):
    return point_trial(db,obj) if isinstance(obj,SocialClaim) else annual_trial(db,obj)


def require_fresh(db,obj):
    current=current_trial(db,obj)
    frozen=obj.snapshot.get('trial')
    if not frozen or obj.snapshot.get('sha256')!=digest(frozen) or digest(current['basis'])!=digest(frozen['basis']): raise HTTPException(409,'审批依据已变化，请退回后重新试算提交')
    require_unblocked(current)
    return current


def book_claim(db,actor,claim):
    if duplicate_claim(db,claim.project_id,claim.teacher_id,claim.id):raise HTTPException(409,'同一项目已有本人审批中或已归档申报，不能跨周期重复入账')
    if archive_exists(db,claim.teacher_id,claim.period_id):raise HTTPException(409,'考核周期已归档，应办理更正周期')
    old=db.scalar(select(func.coalesce(func.sum(PointEntry.amount),0)).where(PointEntry.teacher_id==claim.teacher_id,PointEntry.period_id==claim.period_id,PointEntry.kind.in_(['BASE','RECALC'])))
    if old:raise HTTPException(409,'本周期已有旧规则积分，须先核定存量衔接口径，不能重复认定')
    balance=db.scalar(select(PointBalance).where(PointBalance.teacher_id==claim.teacher_id,PointBalance.period_id==claim.period_id))
    if balance and balance.confirmed:raise HTTPException(409,'个人积分已确认，须先授权留痕解锁')
    if not balance:balance=PointBalance(teacher_id=claim.teacher_id,period_id=claim.period_id);db.add(balance);db.flush()
    for category in ('teaching','auxiliary'):
        value=D(claim.snapshot['trial'][category])
        db.add(PointEntry(teacher_id=claim.teacher_id,period_id=claim.period_id,item_key='social_'+category+'_'+claim.id,
                         kind='SOCIAL',amount=value,raw_value=str(value),formula='社会培训项目逐项认定；详见已归档积分申报',
                         source_snapshot={'social_claim':claim.id,'rule':{'name':'学校社会培训制度'},'recognition':claim.snapshot},
                         actor_id=actor.id,reason='教学秘书归档入账',basis='已完成学校社会培训审批流程'))
    balance.version+=1


def project_read_item(actor, project):
    item=serial(project)
    if actor.role.kind=='dept' or (actor.role.kind=='teacher' and project.owner_id!=actor.id):
        item['data']={k:v for k,v in project.data.items() if k in {'code','name','cohort','org_id','category','start_date','end_date','mode','class_type','level','scene'}};item['closeout']={}
    elif project.state=='CLOSED' and D(str(project.closeout.get('actual_income',0)))>0:
        close=project.closeout;pending=[]
        if not close.get('funding_source'):pending.append('历史结项资金来源待补核验')
        if close.get('funding_source')=='other_training' and (close.get('retained') is None or close.get('personnel') is None):pending.append('历史结项收入分配资料待补核验')
        if close.get('funding_source')=='government_special' and not close.get('funding_basis','').strip():pending.append('历史政府专项资金适用依据待补核验')
        item['closeout_pending']=pending
    return item


def claim_read_item(db, actor, claim):
    item=serial(claim)
    if (actor.role.kind=='dept' or (actor.role.kind=='teacher' and db.get(SocialProject,claim.project_id).owner_id!=actor.id)) and item.get('snapshot',{}).get('trial'):
        item['snapshot']={k:v for k,v in item['snapshot'].items() if k in {'sha256','frozen_on'}}
        item['snapshot']['trial']=personal_claim_trial(claim.snapshot['trial'],claim.teacher_id)
    return item


def point_entry_read_item(db, actor, item):
    result=serial(item);source=result.get('source_snapshot') or {}
    if not source.get('social_claim'):return result
    claim=db.get(SocialClaim,source['social_claim']);project=db.get(SocialProject,claim.project_id) if claim else None
    if 'records.read' in actor.permissions and actor.role.kind!='dept' and (actor.role.kind!='teacher' or (project and project.owner_id==actor.id)):return result
    recognition=source.get('recognition')
    if recognition and recognition.get('trial'):
        source['recognition']={k:v for k,v in recognition.items() if k in {'sha256','frozen_on'}}
        source['recognition']['trial']=personal_claim_trial(recognition['trial'],result['teacher_id'])
    return result


def annual_public_trial(trial):
    return {k:v for k,v in serial(trial).items() if k not in {'basis','points_total','points_average','cost_details','veto_basis'}}


def annual_read_item(actor, annual):
    item=serial(annual)
    if actor.role.kind=='teacher':
        item['data']={}
        item['snapshot']={k:v for k,v in item.get('snapshot',{}).items() if k in {'trial','sha256','frozen_on','public_start','public_end'}}
        if item['snapshot'].get('trial'):item['snapshot']['trial']=annual_public_trial(item['snapshot']['trial'])
    return item


def detail(db,actor,kind,obj):
    if isinstance(obj,SocialProject) and (actor.role.kind=='dept' or (actor.role.kind=='teacher' and obj.owner_id!=actor.id)):
        item=project_read_item(actor,obj)
        rows=[]
        names=dict(db.execute(select(User.id,User.name).where(User.id.in_(actor.teacher_ids))).all())
        for unit in units(db,obj.id):
            own=[{**t,'teacher_name':names.get(t['teacher_id'],'授权教师')} for t in unit.data['teachers'] if t['teacher_id'] in actor.teacher_ids]
            if own:rows.append({'id':unit.id,'external_key':unit.external_key,'data':{**{k:unit.data[k] for k in ('course_code','class_code','module','event_date','mode')},'teachers':own,'learners':[]}})
        org=db.get(Org,obj.org_id)
        return {'item':item,'org_name':org.name if org else '','state_label':state_label(obj),'readonly':True,'view_only':True,'readonly_reason':'仅展示本教研室教师参与摘要，项目原始资料由学院管理' if actor.role.kind=='dept' else '仅展示本人参与摘要，项目资料由负责人管理','attachments':[],'events':[],
                'facts':{'project':item,'units':rows,'evidence':[],'followups':[],'invalidated':False,'effective':None,'priority':None,'excluded':None}}
    result={'item':serial(obj),'state_label':state_label(obj),'attachments':evidence(db,kind,obj.id),
            'events':serial(db.scalars(select(WorkflowEvent).where(WorkflowEvent.object_type==kind,WorkflowEvent.object_id==obj.id).order_by(WorkflowEvent.created_at,WorkflowEvent.id)).all())}
    if isinstance(obj,SocialResource) and obj.kind=='point_report':
        for row in result['events']:
            if row['action']=='积分汇总：待院长初审' and row['after'].get('state')=='SUBMITTED':row['action']='积分汇总：待归口复核'
    if isinstance(obj,SocialProject):result['item']=project_read_item(actor,obj);result['facts']=project_facts(db,obj)
    if isinstance(obj,(SocialProject,SocialResource)):
        org=db.get(Org,obj.org_id);result['org_name']=org.name if org else ''  # 教师、教研室的组织列表不含所属学院，名称由服务端给出
    if isinstance(obj,SocialResource) and obj.kind in ('correction','point_review'):
        review_id=obj.data.get('review_id') if obj.kind=='correction' else None
        if review_id:result['attachments']=list(result['attachments'])+list(evidence(db,kind,review_id))  # 由核对单转来的更正，审批人可直接看到核对材料
        claim=db.get(SocialClaim,obj.data['claim_id']);project=db.get(SocialProject,claim.project_id) if claim else None
        teacher=db.get(User,obj.data['teacher_id']);creator=db.get(User,obj.data.get('created_by'))
        trial=(claim.snapshot or {}).get('trial',{}) if claim else {}
        result['review_context']={'teacher_name':teacher.name if teacher else '','creator_name':creator.name if creator else '','project':project.data['name'] if project else '',
                                  'claim_id':claim.id if claim else None,'teaching':trial.get('teaching'),'auxiliary':trial.get('auxiliary')}
        if obj.kind=='point_review' and obj.data.get('correction_id'):
            correction=db.get(SocialResource,obj.data['correction_id'])
            result['review_context']['correction_state']=correction.state if correction else None
        if obj.kind=='point_review' and obj.state=='DRAFT':result['workflow_blockers']=review_staff_blockers(db,obj)
    if actor.role.kind=='dept' and isinstance(obj,(SocialProject,SocialResource)) and obj.org_id not in actor.org_ids and not (isinstance(obj,SocialResource) and obj.kind in ('correction','point_review')):
        result.update(view_only=True,view_only_reason='教研室负责人可查看本教研室教师负责或参与的项目及学院资源；申报、备案、结项和资源登记由学院和学校办理。')
    if isinstance(obj,(SocialClaim,SocialAnnual)):
        result['trial']=obj.snapshot.get('trial') if obj.state=='ARCHIVED' else current_trial(db,obj)
        if obj.state=='ARCHIVED' and obj.snapshot.get('sha256')!=digest(result['trial']):raise HTTPException(409,'归档依据校验失败')
    if isinstance(obj,SocialClaim) and obj.state=='ARCHIVED':result['busy_reason']=claim_busy_reason(db,obj.id)
    if isinstance(obj,SocialClaim) and (actor.role.kind=='dept' or (actor.role.kind=='teacher' and db.get(SocialProject,obj.project_id).owner_id!=actor.id)):
        result['trial']=personal_claim_trial(result['trial'],obj.teacher_id)
        result['item']=claim_read_item(db,actor,obj)
        result['events']=[{k:v for k,v in row.items() if k in {'id','actor_name','action','created_at','reason','basis'}} for row in result['events']]
    if isinstance(obj,SocialAnnual) and actor.role.kind=='teacher':
        result.update(item=annual_read_item(actor,obj),trial=annual_public_trial(result['trial']),attachments=[],events=[],public_summary=True)
    return result


def personal_claim_trial(trial, teacher_id):
    result=serial(trial);facts=result.get('basis',{}).get('facts')
    if not facts:return result
    project=facts['project'];project['data']={k:v for k,v in project['data'].items() if k in {'code','name','cohort','org_id','category','start_date','end_date','mode','class_type','level','scene'}}
    project['closeout']={k:v for k,v in project.get('closeout',{}).items() if k=='closed_on'}
    rows=[]
    for unit in facts.get('units',[]):
        own=[t for t in unit['data']['teachers'] if t['teacher_id']==teacher_id]
        if not own:continue
        counts=unit_counts(unit['data']);reasons={}
        for learner in unit['data']['learners']:
            if not eligible(learner):
                reason='人工核验剔除' if learner.get('exclusion_reason','').strip() else '在校生且不符合毕业生例外' if learner['full_time_student'] and not learner['graduate_exception'] else '未满足签到、学时、参训或结业条件'
                reasons[reason]=reasons.get(reason,0)+1
        unit['data']={**{k:unit['data'][k] for k in ('course_code','class_code','module','event_date','mode')},'teachers':own,'learners':[],'counts':counts,'exclusion_summary':reasons}
        rows.append(unit)
    result['basis']['facts']={'project':project,'units':rows,'invalidated':facts.get('invalidated',False)}
    return result


def correction_totals(db,claim):
    totals={'teaching':D(claim.snapshot['trial']['teaching']),'auxiliary':D(claim.snapshot['trial']['auxiliary'])}
    for entry in db.scalars(select(PointEntry).where(PointEntry.teacher_id==claim.teacher_id,PointEntry.kind=='SOCIAL')):
        source=entry.source_snapshot
        if source.get('social_claim')==claim.id and source.get('correction_id'):
            totals[source['category']]+=D(entry.amount)
    return totals


def report_rows(db,a,org_id,year,start_month,end_month):
    org=db.get(Org,org_id)
    if not org or org_id not in a.org_ids:raise HTTPException(403,'汇总组织超出授权范围')
    colleges=[org_id] if org.kind=='college' else db.scalars(select(Org.id).where(Org.parent_id==org_id,Org.kind=='college')).all()
    claims=db.scalars(select(SocialClaim).join(SocialProject,SocialProject.id==SocialClaim.project_id).where(SocialProject.org_id.in_(colleges),SocialClaim.state=='ARCHIVED').order_by(SocialClaim.id)).all()
    rows=[]
    for claim in claims:
        trial=claim.snapshot['trial'];closed=date.fromisoformat(trial['basis']['facts']['project']['closeout']['closed_on'])
        if closed.year!=year or not start_month<=closed.month<=end_month:continue
        user=db.get(User,claim.teacher_id);project=db.get(SocialProject,claim.project_id);totals=correction_totals(db,claim)
        if any(x.get('invalidate_cohort') for x in project_followups(db,project.id)) and sum(totals.values())>0:raise HTTPException(409,'已作废项目尚有归档积分待更正，不能发布未处理的汇总')
        rows.append({'claim_id':claim.id,'teacher_id':user.id,'teacher_name':user.name,'org_name':db.get(Org,project.org_id).name,'project':project.data['name'],
                     'teaching':number(totals['teaching']),'auxiliary':number(totals['auxiliary']),'total':number(sum(totals.values())),
                     'original_sha256':claim.snapshot['sha256']})
    return rows


def book_correction(db,actor,obj):
    data=obj.data;claim=db.get(SocialClaim,data['claim_id']);require_open_period(db,data['period_id'])
    if claim.snapshot['sha256']!=data['original_sha256'] or digest(claim.snapshot['trial'])!=claim.snapshot['sha256']:raise HTTPException(409,'原认定快照校验失败')
    if archive_exists(db,claim.teacher_id,data['period_id']):raise HTTPException(409,'入账周期已归档，请使用更正周期')
    totals=correction_totals(db,claim)
    if any(totals[k]+D(data[k])<0 for k in totals):raise HTTPException(409,'更正后授课或辅助积分不能为负数')
    balance=db.scalar(select(PointBalance).where(PointBalance.teacher_id==claim.teacher_id,PointBalance.period_id==data['period_id']))
    if balance and balance.confirmed:raise HTTPException(409,'积分台账已确认，须先授权留痕解锁')
    if not balance:balance=PointBalance(teacher_id=claim.teacher_id,period_id=data['period_id']);db.add(balance);db.flush()
    for category in ('teaching','auxiliary'):
        value=D(data[category])
        db.add(PointEntry(teacher_id=claim.teacher_id,period_id=data['period_id'],item_key='social_fix_'+category+'_'+obj.id,
            kind='SOCIAL',amount=value,raw_value=str(value),formula='学校正式更正决定；原认定快照保留',
            source_snapshot={'social_claim':claim.id,'correction_id':obj.id,'category':category,'rule':{'name':'社会培训更正'},'decision':serial(obj)},
            actor_id=actor.id,reason=data['reason'],basis=data['decision_reference']))
    balance.version+=1


def claim_busy_reason(db, claim_id, reviews=True):
    """同一条积分同一时间只能有一件核对或更正在办，避免差额重复入账。"""
    if reviews and any(x.data.get('claim_id')==claim_id for x in db.scalars(select(SocialResource).where(SocialResource.kind=='point_review',SocialResource.state!='CLOSED'))):
        return '这条积分已有未办结的核对单，请先办结核对'
    if any(x.data.get('claim_id')==claim_id for x in db.scalars(select(SocialResource).where(SocialResource.kind=='correction',SocialResource.state.notin_(['ARCHIVED','VOID'])))):
        return '这条积分已有更正单在办理中，请等更正归档后再办理'
    return None


def open_point_reviews(db, teacher_id):
    """已发给教师、尚未办结的积分核对，以及由核对生成、尚未归档入账的更正；办结前不能确认该教师的考核。"""
    reviews = select(SocialResource).where(SocialResource.kind=='point_review',SocialResource.state.in_(['TEACHER','COLLEGE']))
    fixes = select(SocialResource).where(SocialResource.kind=='correction',SocialResource.state.notin_(['ARCHIVED','VOID']))
    return [x for x in db.scalars(reviews) if x.data.get('teacher_id')==teacher_id]+[x for x in db.scalars(fixes) if x.data.get('teacher_id')==teacher_id and x.data.get('review_id')]


def todo_items(db,a):
    items=[];duties={k for k,v in assignments(db).items() if a.id in v}
    def add(kind,obj,title,state=None,teacher_id=None,due=None):
        items.append({'type':kind,'id':obj.id,'title':title,'state':state or state_label(obj),'teacher_id':teacher_id,
                      'target_id':None if teacher_id else getattr(obj,'org_id',None),'deadline':serial(due)})
    if 'records.read' not in a.permissions:return items
    projects=db.scalars(select(SocialProject).where(SocialProject.org_id.in_(a.org_ids) if a.role.kind!='teacher' else SocialProject.owner_id==a.id)).all()
    for p in projects:
        if p.state in {'DRAFT','RETURNED'} and 'records.write' in a.permissions:add('social_project',p,'补充项目申报：'+p.data['name'])
        elif p.state in {'SUBMITTED','CLOSE_REVIEW'} and 'coordinator' in duties and p.owner_id!=a.id:add('social_project',p,'项目审核：'+p.data['name'])
        elif p.state=='FILED' and today().isoformat()>p.data['end_date']:add('social_project',p,'培训已结束，请办理结项：'+p.data['name'],'待结项')
        followups=project_followups(db,p.id)
        if any(x.get('invalidate_cohort') for x in followups) and 'secretary' in duties:
            for claim in db.scalars(select(SocialClaim).where(SocialClaim.project_id==p.id,SocialClaim.state=='ARCHIVED')):
                if sum(correction_totals(db,claim).values())>0:add('social_claim',claim,'正式处理后待追加积分更正',teacher_id=claim.teacher_id)
        if p.state=='CLOSED' and not p.closeout.get('settlement_on') and not any(x['kind']=='settlement' and x.get('completed_on') for x in followups):
            closed=date.fromisoformat(p.closeout['closed_on']);month=closed.month+6;year=closed.year+(month-1)//12;month=(month-1)%12+1
            due=date(year,month,min(closed.day,monthrange(year,month)[1]));add('social_project',p,'项目结算期限：'+due.isoformat()+' · '+p.data['name'],'结算跟踪',due=due)
        if p.state=='CLOSED' and p.closeout.get('rectification_due') and not any(x['kind']=='rectification' and x.get('completed_on') for x in followups):
            add('social_project',p,'满意度整改跟踪：'+p.closeout['rectification_due']+' · '+p.data['name'],'整改跟踪',due=p.closeout['rectification_due'])
        for case in followups:
            if not case.get('completed_on'):
                deadlines='、'.join(k+' '+v for k,v in case.get('deadlines',{}).items())
                add('social_project',p,'待办跟踪：'+p.data['name']+' · '+deadlines,'待办结')
    stages={'SUBMITTED':'dean','DEAN':'coordinator','COORDINATOR':'vice_president','APPROVED':'secretary'}
    for claim in db.scalars(select(SocialClaim).where(a.scope(SocialClaim.teacher_id))):
        if claim.state in {'DRAFT','RETURNED'} and claim.teacher_id==a.id:
            trial=point_trial(db,claim);add('social_claim',claim,'本人积分申报'+(' · 截至'+trial['deadline'] if trial['deadline'] else ' · 校历待确认'),teacher_id=claim.teacher_id)
        elif stages.get(claim.state) in duties and claim.teacher_id!=a.id:add('social_claim',claim,'社会培训积分认定',teacher_id=claim.teacher_id)
    for obj in db.scalars(select(SocialResource).where(SocialResource.kind=='correction')):
        if obj.data['teacher_id'] not in a.teacher_ids:continue
        if obj.state in {'DRAFT','RETURNED'} and obj.data['created_by']==a.id:add('social_resource',obj,'补充积分更正依据',teacher_id=obj.data['teacher_id'])
        elif stages.get(obj.state) in duties and a.id not in {obj.data['created_by'],obj.data['teacher_id']}:add('social_resource',obj,'社会培训积分更正审核',teacher_id=obj.data['teacher_id'])
    for obj in db.scalars(select(SocialResource).where(SocialResource.kind=='point_review',SocialResource.state!='CLOSED')):
        if obj.data['teacher_id'] not in a.teacher_ids:continue
        if obj.state=='DRAFT' and obj.data['created_by']==a.id:add('social_resource',obj,'上传核对材料并发给教师',teacher_id=obj.data['teacher_id'])
        elif obj.state=='TEACHER' and obj.data['teacher_id']==a.id:add('social_resource',obj,'教研室请你核对一条积分，请回应',teacher_id=a.id)
        elif obj.state=='COLLEGE' and 'dean' in duties and a.id not in {obj.data['created_by'],obj.data['teacher_id']}:add('social_resource',obj,'积分核对待学院裁定',teacher_id=obj.data['teacher_id'])
    for report in db.scalars(select(SocialResource).where(SocialResource.kind=='point_report',SocialResource.org_id.in_(a.org_ids),SocialResource.state.notin_(['ARCHIVED','VOID']))):
        if report.data['created_by']==a.id or duties&{'coordinator','secretary'}:add('social_resource',report,'积分双月报送或年度公示')
    if 'secretary' in duties and today().month%2==0:
        from types import SimpleNamespace
        add('social_report',SimpleNamespace(id='bimonth',state='DRAFT',org_id=a.org.id),'本双月积分汇总与报送','待汇总')
    if 'assessment.review' in a.permissions:
        for annual in db.scalars(select(SocialAnnual).where(SocialAnnual.org_id.in_(a.org_ids),SocialAnnual.state!='ARCHIVED')):
            if annual.owner_id==a.id and annual.state not in {'DRAFT','RETURNED'}:continue
            pending={'coordinator','finance','academic','discipline'}-annual.snapshot.get('checks',{}).keys()
            if (annual.owner_id==a.id and annual.state in {'DRAFT','RETURNED'}) or (annual.state=='REVIEW' and duties&pending) or (annual.state=='COMMITTEE' and 'committee' in duties) or (annual.state=='PUBLIC' and duties&{'coordinator','secretary'}):add('social_annual',annual,'学院年度考核办理')
    return items


def ledger_summary(db,a,year):
    rows=db.scalars(select(SocialClaim).where(a.scope(SocialClaim.teacher_id),SocialClaim.state=='ARCHIVED')).all()
    teachers={}
    for claim in rows:
        trial=claim.snapshot['trial'];closed=trial['basis']['facts']['project']['closeout']['closed_on'];claim_year=int(closed[:4])
        record=teachers.setdefault(claim.teacher_id,{'teacher_id':claim.teacher_id,'teaching':D(0),'auxiliary':D(0),'five_year_total':D(0),'years':{}})
        totals=correction_totals(db,claim);total=sum(totals.values())
        record['teaching']+=totals['teaching'];record['auxiliary']+=totals['auxiliary']
        if year-4<=claim_year<=year:record['five_year_total']+=total
        y=record['years'].setdefault(str(claim_year),{'teaching':D(0),'auxiliary':D(0),'title_score':D(0),'title_pending':False})
        y['teaching']+=totals['teaching'];y['auxiliary']+=totals['auxiliary']
        cfg=trial['basis']['policy']['data'];scope=cfg.get('title_scope');title_config=(cfg.get('title_precision'),cfg.get('title_rounding'))
        if '_title_config' in y and y['_title_config']!=title_config:y['title_pending']=True
        y['_title_config']=title_config
        if scope is None or None in title_config:y['title_pending']=True
        else:y['title_score']+=(total if scope=='all' else totals['teaching'])/100
    for teacher in teachers.values():
        for y in teacher['years'].values():
            precision,_=y.pop('_title_config')
            y['title_score']=None if y['title_pending'] else str(y['title_score'].quantize(D(1).scaleb(-precision),rounding=ROUND_HALF_UP))
    return {'items':serial(list(teachers.values())),'promotion_gate_enabled':False,'note':'仅汇总本模块已归档认定积分；历史汇总记录须补齐依据后另行核定。近五年340分条件尚不用于拦截职称申报。'}
