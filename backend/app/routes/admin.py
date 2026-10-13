"""R2 organization/account/role/configuration implementations for existing UI."""
from fastapi import APIRouter,Request,HTTPException
from sqlalchemy import select,func,delete
from ..core import *
from ..schemas import *
from ..passwords import hash_password
from ..permissions import ALLOWED,validate_permissions
from ..org_assessment import OrganizationAssessment
from ..readiness import _setting_ok
from ..settings_catalog import business_dictionary,import_policy,configurable_key,is_custom_key,MAX_CUSTOM_SETTINGS
router=APIRouter(prefix='/api',tags=['组织与配置'])

def need_admin(a): a.require_admin()
def account_shape(db,org_id,role_id,staff_no):
    org,role=db.get(Org,org_id),db.get(Role,role_id)
    if not org or not role or not role.active or not validate_permissions(role.kind,role.permissions):
        raise HTTPException(422,'组织或角色配置无效')
    org_scope(db,org,role.kind)
    if role.kind=='teacher' and not staff_no: raise HTTPException(422,'普通教师必须填写工号')
    return org,role

def admin_survives(db):
    db.flush()
    admins=db.scalars(select(User).where(User.active.is_(True),User.authorization_pending.is_(False),User.is_admin.is_(True))).all()
    for u in admins:
        r=db.get(Role,u.role_id);o=db.get(Org,u.org_id)
        if r and o and r.active and r.kind=='school' and o.active and o.kind=='school' and ALLOWED['school']<=set(r.permissions): return
    raise HTTPException(409,'不能停用或移除最后一位可用学校管理员')

@router.get('/organizations')
def organizations(request:Request):
    # Required by every preserved portal boot, including teachers.
    def load(db,a,s):
        visible=Org.id.in_(a.org_ids)
        if a.user.is_admin and a.role.kind=='school' and 'organization.manage' in a.permissions:
            # Recovery metadata only; Actor keeps inactive organizations out of business scope.
            visible=visible | (Org.active.is_(False) & Org.parent_id.in_(a.org_ids))
        items=serial(db.scalars(select(Org).where(visible).order_by(Org.code)).all())
        if a.user.is_admin and a.role.kind=='school':
            # 组织页显示每个学院、教研室的负责人；没有可用负责人的由上一级代办
            from ..identities import org_heads
            heads=org_heads(db)
            for x in items:
                if x['kind'] in ('dept','college'):x['heads']=heads.get(x['id'],[])
        return {'items':items}
    return read_operation(request,'portal.read',load)

def head_role(db,org):
    kind={'dept':'dept','college':'college'}.get(org.kind)
    if not kind:raise HTTPException(422,'只有二级学院和教研室可以设置负责人')
    for role in db.scalars(select(Role).where(Role.kind==kind,Role.active.is_(True)).order_by(Role.code)):
        if validate_permissions(role.kind,role.permissions) and 'assessment.review' in role.permissions:return role
    raise HTTPException(409,'没有可用的'+('教研室' if kind=='dept' else '学院')+'负责人角色，请先在角色权限里启用')

def org_members(db,org):
    return select(User).where(User.org_id.in_(org_scope(db,org,org.kind)),User.staff_no.is_not(None),User.active.is_(True))

@router.get('/organizations/{ident}/head-candidates')
def head_candidates(ident:str,request:Request):
    f,_,_=filters_from(request,{'q'})
    def load(db,a,s):
        need_admin(a);org=db.get(Org,ident)
        if not org or ident not in a.org_ids or org.kind not in ('dept','college'):raise HTTPException(404,'组织不存在')
        q=org_members(db,org)
        if f.get('q'):q=q.where(User.name.contains(f['q'],autoescape=True)|User.staff_no.contains(f['q'],autoescape=True))
        names={o.id:o.name for o in db.scalars(select(Org))}
        return {'items':[{'id':u.id,'name':u.name,'staff_no':u.staff_no,'title':u.title,'org_name':names.get(u.org_id,''),
            'authorization_pending':u.authorization_pending} for u in db.scalars(q.order_by(User.staff_no).limit(30))]}
    return read_operation(request,'users.manage',load)

@router.post('/organizations/{ident}/heads')
def add_org_head(ident:str,data:OrgHeadIn,request:Request):
    """设置负责人：给本组织的一位老师加一个负责人兼任身份，原来的教师身份不变。"""
    def apply(db,a,s):
        from ..identities import all_extras,save_extras,org_heads,MAX_EXTRA_PER_USER
        import uuid
        need_admin(a);org=db.get(Org,ident)
        if not org or ident not in a.org_ids or not org.active:raise HTTPException(404,'组织不存在或已停用')
        role=head_role(db,org);user=db.scalar(org_members(db,org).where(User.id==data.user_id).with_for_update())
        if user is None:raise HTTPException(422,'只能从本组织在职、有工号的老师里选负责人')
        if not set(role.permissions)<=a.permissions:raise HTTPException(403,'不能分配超出本人授权的角色')
        if any(h['user_id']==user.id for h in org_heads(db).get(org.id,[])):raise HTTPException(409,user.name+' 已经是本组织负责人')
        items=all_extras(db,lock=True)
        if sum(1 for x in items if x['user_id']==user.id)>=MAX_EXTRA_PER_USER:raise HTTPException(409,'该老师的兼任身份已达上限')
        extra={'id':str(uuid.uuid4()),'user_id':user.id,'role_id':role.id,'org_id':org.id,'granted_by':a.id,
               'granted_at':utcnow().isoformat(timespec='seconds'),'reason':data.reason[:200]}
        save_extras(db,items+[extra]);user.version+=1
        after={'user_id':user.id,'name':user.name,'staff_no':user.staff_no,'role':role.name,'org':org.name}
        audit(db,a,'organization',org.id,'设置负责人',after=after,reason=data.reason)
        return {'added':True,**after}
    return command(request,data.model_dump(),'users.manage',apply)

@router.post('/organizations/{ident}/heads/remove')
def remove_org_head(ident:str,data:OrgHeadIn,request:Request):
    def apply(db,a,s):
        from ..identities import all_extras,save_extras
        need_admin(a);org=db.get(Org,ident)
        if not org or ident not in a.org_ids:raise HTTPException(404,'组织不存在')
        user=db.scalar(select(User).where(User.id==data.user_id).with_for_update())
        if user is None:raise HTTPException(404,'账号不存在')
        roles={r.id:r for r in db.scalars(select(Role))}
        if user.org_id==org.id and roles.get(user.role_id) and roles[user.role_id].kind==org.kind:
            raise HTTPException(409,'这是该账号的主身份，请到“账号管理”里调整角色')
        items=all_extras(db,lock=True)
        mine=[x for x in items if x['user_id']==user.id and x['org_id']==org.id and roles.get(x['role_id']) and roles[x['role_id']].kind==org.kind]
        if not mine:raise HTTPException(404,user.name+' 不是本组织负责人')
        save_extras(db,[x for x in items if x not in mine])
        # 正在用这个身份的会话随之失效，避免继续以负责人身份办理
        user.version+=1;user.auth_version+=1;db.execute(delete(AuthSession).where(AuthSession.user_id==user.id))
        after={'user_id':user.id,'name':user.name,'staff_no':user.staff_no,'org':org.name}
        audit(db,a,'organization',org.id,'移除负责人',before={'role':roles[mine[0]['role_id']].name},after=after,reason=data.reason)
        return {'removed':True,**after}
    return command(request,data.model_dump(),'users.manage',apply)

@router.post('/organizations')
def create_org(data:OrgIn,request:Request):
    def apply(db,a,s):
        need_admin(a);parent=db.get(Org,data.parent_id)
        if not parent or not parent.active or parent.id not in a.org_ids or (parent.kind,data.kind) not in {('school','college'),('college','dept')}:
            raise HTTPException(422,'上级组织与新增层级不匹配')
        obj=Org(**data.model_dump(exclude={'reason','basis'}));db.add(obj);db.flush()
        audit(db,a,'organization',obj.id,'新增组织',after=serial(obj),reason=data.reason);return obj
    return command(request,data.model_dump(),'organization.manage',apply)

@router.put('/organizations/{ident}')
def update_org(ident:str,data:OrgUpdate,request:Request):
    def apply(db,a,s):
        need_admin(a);obj=db.get(Org,ident)
        if not obj or ident not in a.org_ids: raise HTTPException(404,'组织不存在')
        check_version(obj,data.expected_version);before=serial(obj)
        parent=db.get(Org,data.parent_id) if data.parent_id else None
        if obj.kind=='school':
            if data.parent_id: raise HTTPException(422,'学校根组织不能设置上级')
        elif not parent or parent.id not in a.org_ids or not parent.active or (parent.kind,obj.kind) not in {('school','college'),('college','dept')}:
            raise HTTPException(422,'上级组织不正确')
        obj.name=data.name;obj.parent_id=data.parent_id;obj.version+=1
        audit(db,a,'organization',ident,'调整组织',before,serial(obj),data.reason)
        return obj
    return command(request,data.model_dump(),'organization.manage',apply)

@router.post('/organizations/{ident}/state')
def org_action(ident:str,data:Action,request:Request):
    def apply(db,a,s):
        need_admin(a);obj=db.get(Org,ident)
        if not obj or obj.kind=='school': raise HTTPException(409,'学校根组织不能停用')
        check_version(obj,data.expected_version)
        if data.action not in {'enable','disable'}: raise HTTPException(422,'组织操作无效')
        parent=db.get(Org,obj.parent_id)
        if not parent or parent.id not in a.org_ids: raise HTTPException(403,'组织不在授权范围')
        before=serial(obj);obj.active=data.action=='enable';obj.version+=1
        audit(db,a,'organization',ident,'组织启停',before,serial(obj),data.reason);return obj
    return command(request,data.model_dump(),'organization.manage',apply)

@router.get('/teachers')
def teachers(request:Request):
    f,p,z=filters_from(request,{'q'})
    def load(db,a,s):
        q=select(User).where(a.scope(User.id),User.staff_no.is_not(None))
        if f.get('q'):q=q.where(User.name.contains(f['q'],autoescape=True)|User.staff_no.contains(f['q'],autoescape=True))
        return page_result(db,q.order_by(User.staff_no),p,z)
    return read_operation(request,'portal.read',load)

@router.get('/users')
def users(request:Request):
    f,p,z=filters_from(request,{'q','hr_state'})
    if f.get('hr_state') not in (None,'active','inactive','missing','none'):raise HTTPException(422,'人事状态筛选无效')
    def load(db,a,s):
        from ..reference_data import TeacherHrProfile
        need_admin(a);q=select(User).where(User.org_id.in_(a.org_ids))
        if f.get('q'): q=q.where(User.name.contains(f['q'],autoescape=True)|User.username.contains(f['q'],autoescape=True))
        # 人事状态: active/inactive in the school's 教职工 table, missing = staff number not there,
        # none = management account without a staff number.
        in_hr=select(TeacherHrProfile.staff_no)
        state=f.get('hr_state')
        if state=='none':q=q.where(User.staff_no.is_(None))
        elif state=='missing':q=q.where(User.staff_no.is_not(None),User.staff_no.not_in(in_hr))
        elif state:q=q.where(User.staff_no.in_(in_hr.where(TeacherHrProfile.active.is_(state=='active'))))
        out=page_result(db,q.order_by(User.username),p,z)
        from ..identities import all_extras,describe
        extras={}
        for x in all_extras(db):extras.setdefault(x['user_id'],[]).append({'id':x['id'],**describe(db,x['role_id'],x['org_id'])})
        locked={u.id for u in db.scalars(select(User).where(User.id.in_([x['id'] for x in out['items']] or ['']),User.locked_until>utcnow()))}
        for x in out['items']:x['extra_identities']=extras.get(x['id'],[]);x['locked']=x['id'] in locked
        numbers=[x['staff_no'] for x in out['items'] if x.get('staff_no')]
        hr=dict(db.execute(select(TeacherHrProfile.staff_no,TeacherHrProfile.active).where(TeacherHrProfile.staff_no.in_(numbers))).all()) if numbers else {}
        for x in out['items']:
            n=x.get('staff_no');x['hr_state']='none' if not n else ('missing' if n not in hr else ('active' if hr[n] else 'inactive'))
        out['hr_synced']=db.scalar(select(func.count()).select_from(TeacherHrProfile))>0
        out['hr_unmatched']=db.scalar(select(func.count()).select_from(TeacherHrProfile).where(TeacherHrProfile.user_id.is_(None))) or 0
        return out
    return read_operation(request,'users.manage',load)

def link_school_rows(db,a,user):
    """A new account takes over the school rows already synced under its staff number,
    so the roster, scope and credits see it now instead of after the next data-hub pull."""
    from ..reference_data import TeacherHrProfile,TeacherCourseTerm
    profile=db.scalar(select(TeacherHrProfile).where(TeacherHrProfile.staff_no==user.staff_no,TeacherHrProfile.user_id.is_(None)))
    if profile is not None:
        before=serial(profile);profile.user_id=user.id;profile.version+=1
        audit(db,a,'teacher_hr',profile.id,'新账号对应人事记录',before,serial(profile),'按工号对应新建账号')
    terms=db.scalars(select(TeacherCourseTerm).where(TeacherCourseTerm.staff_no==user.staff_no,TeacherCourseTerm.user_id.is_(None))).all()
    for t in terms:t.user_id=user.id;t.version+=1
    if terms:audit(db,a,'teacher_course',user.id,'新账号对应授课记录',after={'staff_no':user.staff_no,'rows':len(terms)},reason='按工号对应新建账号')

@router.post('/users')
def create_user(data:UserIn,request:Request):
    def apply(db,a,s):
        need_admin(a);org,role=account_shape(db,data.org_id,data.role_id,data.staff_no)
        if org.id not in a.org_ids or not set(role.permissions)<=a.permissions: raise HTTPException(403,'不能创建超出本人授权的账号')
        values=data.model_dump(exclude={'reason','basis','password'})
        obj=User(**values,password_hash=hash_password(data.password),is_admin=False,must_change_password=True,active=True)
        db.add(obj);db.flush();audit(db,a,'users',obj.id,'新增账号',after=serial(obj),reason=data.reason)
        if obj.staff_no:link_school_rows(db,a,obj)
        return obj
    return command(request,data.model_dump(),'users.manage',apply)

@router.put('/users/{ident}')
def update_user(ident:str,data:UserUpdate,request:Request):
    def apply(db,a,s):
        need_admin(a);obj=db.get(User,ident)
        if not obj or obj.org_id not in a.org_ids: raise HTTPException(404,'账号不存在')
        check_version(obj,data.expected_version);org,role=account_shape(db,data.org_id,data.role_id,obj.staff_no)
        if org.id not in a.org_ids or not set(role.permissions)<=a.permissions: raise HTTPException(403,'不能分配超出本人授权的角色')
        if data.is_admin and role.kind!='school': raise HTTPException(422,'学校管理员必须绑定学校角色')
        before=serial(obj)
        obj.authorization_pending=False
        for key,value in data.model_dump(exclude={'reason','basis','expected_version','extra_identities'}).items():setattr(obj,key,value)
        after=serial(obj)
        if data.extra_identities is not None:
            from ..identities import replace_user_extras,describe
            old_extras,new_extras=replace_user_extras(db,a,obj,[x.model_dump() for x in data.extra_identities],data.reason)
            before['extra_identities']=[describe(db,x['role_id'],x['org_id']) for x in old_extras]
            after['extra_identities']=[describe(db,x['role_id'],x['org_id']) for x in new_extras]
        obj.version+=1;obj.auth_version+=1;db.execute(delete(AuthSession).where(AuthSession.user_id==ident))
        after['version']=obj.version
        admin_survives(db);audit(db,a,'users',ident,'调整账号权限',before,after,data.reason);return obj
    return command(request,data.model_dump(),'users.manage',apply)

@router.post('/users/{ident}/reset-password')
def reset_user(ident:str,data:ResetPassword,request:Request):
    def apply(db,a,s):
        need_admin(a);obj=db.get(User,ident)
        if not obj or obj.org_id not in a.org_ids: raise HTTPException(404,'账号不存在')
        check_version(obj,data.expected_version)
        obj.password_hash=hash_password(data.password);obj.must_change_password=True;obj.failures=0;obj.locked_until=None
        obj.version+=1;obj.auth_version+=1;db.execute(delete(AuthSession).where(AuthSession.user_id==ident))
        audit(db,a,'users',ident,'重置临时密码',after={'must_change_password':True,'sessions_revoked':True},reason=data.reason)
        return serial(obj)
    return command(request,data.model_dump(),'users.manage',apply)

@router.post('/users/{ident}/unlock')
def unlock_user(ident:str,data:VersionedReason,request:Request):
    """输错密码被锁定时解锁，不改密码。"""
    def apply(db,a,s):
        need_admin(a);obj=db.get(User,ident)
        if not obj or obj.org_id not in a.org_ids: raise HTTPException(404,'账号不存在')
        check_version(obj,data.expected_version)
        before={'failures':obj.failures,'locked':bool(obj.locked_until and obj.locked_until>utcnow())}
        obj.failures=0;obj.locked_until=None;obj.version+=1
        audit(db,a,'users',ident,'解除登录锁定',before=before,after={'locked':False},reason=data.reason)
        return serial(obj)
    return command(request,data.model_dump(),'users.manage',apply)

@router.get('/roles')
def roles(request:Request):
    def load(db,a,s):
        need_admin(a)
        return {'items':db.scalars(select(Role).order_by(Role.code)).all(),'available':{k:sorted(v & a.permissions) for k,v in ALLOWED.items()}}
    return read_operation(request,'users.manage',load)

@router.post('/roles')
def copy_role(data:RoleCopy,request:Request):
    def apply(db,a,s):
        need_admin(a);source=db.get(Role,data.copy_from)
        if not source or not validate_permissions(source.kind,source.permissions): raise HTTPException(422,'来源角色无效')
        if not set(source.permissions)<=a.permissions: raise HTTPException(403,'不能复制超授权角色')
        obj=Role(code=data.code,name=data.name,kind=source.kind,permissions=list(source.permissions),active=source.active)
        db.add(obj);db.flush();audit(db,a,'roles',obj.id,'复制角色',after=serial(obj),reason=data.reason);return obj
    return command(request,data.model_dump(),'roles.manage',apply)

@router.put('/roles/{ident}')
def update_role(ident:str,data:RoleUpdate,request:Request):
    def apply(db,a,s):
        need_admin(a);obj=db.get(Role,ident)
        if not obj:raise HTTPException(404,'角色不存在')
        check_version(obj,data.expected_version)
        if not validate_permissions(obj.kind,data.permissions) or not set(data.permissions)<=a.permissions: raise HTTPException(403,'包含超出角色层级或本人授权的权限')
        if not data.active and db.scalar(select(func.count()).select_from(Role).where(Role.kind==obj.kind,Role.active.is_(True)))<=1:
            raise HTTPException(409,'须保留各层级至少一个有效角色')
        before=serial(obj);obj.permissions=data.permissions;obj.active=data.active;obj.version+=1
        admin_survives(db);audit(db,a,'roles',ident,'调整角色授权',before,serial(obj),data.reason);return obj
    return command(request,data.model_dump(),'roles.manage',apply)

@router.get('/periods')
def periods(request:Request):
    return read_operation(request,'portal.read',lambda db,a,s:{'items':db.scalars(select(Period).order_by(Period.end_date.desc(),Period.id)).all()})

@router.post('/periods')
def create_period(data:PeriodIn,request:Request):
    def apply(db,a,s):
        need_admin(a);obj=Period(**data.model_dump(exclude={'reason','basis'}));db.add(obj);db.flush()
        audit(db,a,'periods',obj.id,'新增考核周期',after=serial(obj),reason=data.reason);return obj
    return command(request,data.model_dump(),'settings.manage',apply)

@router.post('/periods/{ident}/close')
def close_period(ident:str,data:VersionedReason,request:Request):
    def apply(db,a,s):
        need_admin(a);obj=require_open_period(db,ident);check_version(obj,data.expected_version)
        if (db.scalar(select(Assessment.id).where(Assessment.period_id==ident,Assessment.state!='ARCHIVED').limit(1))
            or db.scalar(select(OrganizationAssessment.id).where(OrganizationAssessment.period_id==ident,OrganizationAssessment.state!='ARCHIVED').limit(1))
            or db.scalar(select(Dispute.id).where(Dispute.period_id==ident,Dispute.state=='OPEN').limit(1))):
            raise HTTPException(409,'仍有未归档教师/组织考核或未解决核对申请')
        from ..social_models import SocialClaim,SocialAnnual,SocialResource
        pending=[]
        for model,label in ((SocialClaim,'社会培训积分申报'),(SocialAnnual,'学院社会培训年度考核')):
            count=db.scalar(select(func.count()).select_from(model).where(model.period_id==ident,model.state!='ARCHIVED'))
            if count:pending.append(label+str(count)+'项')
        for kind,finished,label in [('correction',['ARCHIVED','VOID'],'积分更正'),('point_review',['CLOSED'],'积分核对')]:
            count=db.scalar(select(func.count()).select_from(SocialResource).where(SocialResource.kind==kind,SocialResource.state.notin_(finished),SocialResource.data['period_id'].as_string()==ident))
            if count:pending.append(label+str(count)+'项')
        if pending:raise HTTPException(409,'仍有未办结社会培训事项：'+'、'.join(pending)+'；请先在对应业务中办结，再关闭周期')
        before=serial(obj);obj.state='CLOSED';obj.version+=1
        audit(db,a,'periods',ident,'关闭考核周期',before,serial(obj),data.reason);return obj
    return command(request,data.model_dump(),'settings.manage',apply)

@router.get('/settings')
def settings(request:Request):
    return read_operation(request,'settings.manage',lambda db,a,s:{'items':db.scalars(select(Setting).where(~Setting.key.like('ssoid:%'),~Setting.key.like('ssostate:%'),Setting.key!='code_tables',Setting.key!='account_identities').order_by(Setting.key)).all()})

@router.get('/settings/{key}/history')
def setting_history(key:str,request:Request):
    def load(db,a,s):
        need_admin(a)
        if not configurable_key(key):
            raise HTTPException(404,'配置项不存在')
        rows=db.scalars(select(Audit).where(Audit.module=='settings',Audit.object_id==key)
            .order_by(Audit.created_at.desc(),Audit.id.desc()).limit(100)).all()
        return {'key':key,'items':rows}
    return read_operation(request,'settings.manage',load)

@router.put('/settings/{key}')
def update_setting(key:str,data:SettingUpdate,request:Request):
    def apply(db,a,s):
        need_admin(a);obj=db.get(Setting,key)
        if not configurable_key(key) or not obj: raise HTTPException(404,'配置项不存在')
        check_version(obj,data.expected_version)
        if not _setting_ok(key,data.value):raise HTTPException(422,'配置值不符合该项目规范')
        if len(str(data.value))>12000:raise HTTPException(422,'配置值过长')
        before=serial(obj);obj.value=data.value;obj.version+=1
        audit(db,a,'settings',key,'修改基础配置',before,serial(obj),data.reason);return obj
    return command(request,data.model_dump(),'settings.manage',apply)

@router.post('/settings')
def create_setting(data:SettingCreate,request:Request):
    """3.1: add a custom dictionary category (dict:code) or system parameter (param:code)."""
    def apply(db,a,s):
        need_admin(a)
        if not is_custom_key(data.key):raise HTTPException(422,'只能新增自定义字典类别（dict:编码）或系统参数（param:编码）')
        if db.get(Setting,data.key):raise HTTPException(409,'该配置编码已存在，请在原配置上修改')
        count=db.scalar(select(func.count()).select_from(Setting).where(Setting.key.like('dict:%')|Setting.key.like('param:%')))
        if count>=MAX_CUSTOM_SETTINGS:raise HTTPException(422,'自定义配置项数量已达上限')
        if not _setting_ok(data.key,data.value):raise HTTPException(422,'配置值不符合该项目规范')
        if len(str(data.value))>12000:raise HTTPException(422,'配置值过长')
        obj=Setting(key=data.key,value=data.value,version=1);db.add(obj);db.flush()
        audit(db,a,'settings',data.key,'新增学校自定义配置',{},serial(obj),data.reason);return obj
    return command(request,data.model_dump(),'settings.manage',apply)

@router.get('/dictionaries')
def dictionaries(request:Request):
    def load(db,a,s):
        values=business_dictionary(db)
        policy=import_policy(db)
        custom={'categories':{},'parameters':{}}
        for item in db.scalars(select(Setting).where(Setting.key.like('dict:%')|Setting.key.like('param:%')).order_by(Setting.key)):
            if not _setting_ok(item.key,item.value):continue  # fail closed: a damaged custom item is not published
            code=item.key.split(':',1)[1]
            if item.key.startswith('dict:'):custom['categories'][code]={'name':item.value['name'],'items':item.value['items']}
            else:custom['parameters'][code]={'name':item.value['name'],'type':item.value['type'],'value':item.value['value']}
        return {'notice_categories':values['notice_categories'],'record_sources':values['record_sources'],
                'status_labels':values['status_labels'],'import_max_rows':policy['max_rows'],**custom}
    return read_operation(request,'portal.read',load)

@router.get('/qualification-categories')
def categories(request:Request):
    def load(db,a,s):
        obj=db.get(Setting,'qualification')
        if not obj or not _setting_ok('qualification',obj.value):raise HTTPException(503,'资质字典未配置')
        return {'categories':obj.value['categories']}
    return read_operation(request,'qualification.read',load)

# Notifications posted to a parent are visible downwards, not to siblings.
def notice_scope(db,a):
    ids=set(a.org_ids);o=a.org
    while o and o.parent_id:
        ids.add(o.parent_id);o=db.get(Org,o.parent_id)
    return ids

@router.get('/notices')
def notices(request:Request):
    f,p,z=filters_from(request,{'q'})
    def load(db,a,s):
        q=select(Notice).where(Notice.org_id.in_(notice_scope(db,a)))
        if 'notice.manage' not in a.permissions:q=q.where(Notice.published.is_(True))
        else:q=q.where(Notice.published.is_(True)|Notice.org_id.in_(a.org_ids))
        if f.get('q'):q=q.where(Notice.title.contains(f['q'],autoescape=True)|Notice.body.contains(f['q'],autoescape=True))
        result=page_result(db,q.order_by(Notice.created_at.desc(),Notice.id),p,z)
        names=dict(db.execute(select(Org.id,Org.name).where(Org.id.in_({x['org_id'] for x in result['items']}))).all())
        for item in result['items']:item['org_name']=names.get(item['org_id'],'')
        return result
    return read_operation(request,'notice.read',load)

@router.post('/notices')
def create_notice(data:NoticeIn,request:Request):
    def apply(db,a,s):
        if data.org_id not in a.org_ids:raise HTTPException(403,'发布范围超出授权')
        if data.category not in business_dictionary(db)['notice_categories']:raise HTTPException(422,'请选择学校业务字典中的通知分类')
        obj=Notice(**data.model_dump(exclude={'reason','basis'}),author_id=a.id);db.add(obj);db.flush()
        audit(db,a,'notices',obj.id,'发布通知',after=serial(obj),reason=data.reason);return obj
    return command(request,data.model_dump(),'notice.manage',apply)

@router.get('/notices/{ident}')
def notice_detail(ident:str,request:Request):
    def load(db,a,s):
        obj=db.get(Notice,ident)
        if not obj or obj.org_id not in notice_scope(db,a) or (not obj.published and ('notice.manage' not in a.permissions or obj.org_id not in a.org_ids)):
            raise HTTPException(404,'通知不存在或未发布')
        return obj
    return read_operation(request,'notice.read',load)

@router.put('/notices/{ident}')
def update_notice(ident:str,data:NoticeUpdate,request:Request):
    def apply(db,a,s):
        obj=db.get(Notice,ident)
        if not obj or obj.org_id not in a.org_ids or data.org_id not in a.org_ids:raise HTTPException(404,'通知不存在')
        if data.category not in business_dictionary(db)['notice_categories']:raise HTTPException(422,'请选择学校业务字典中的通知分类')
        check_version(obj,data.expected_version);before=serial(obj)
        for k,v in data.model_dump(exclude={'reason','basis','expected_version'}).items():setattr(obj,k,v)
        obj.version+=1;audit(db,a,'notices',ident,'更新通知',before,serial(obj),data.reason);return obj
    return command(request,data.model_dump(),'notice.manage',apply)

@router.get('/audit/security-alerts')
def security_alerts(request:Request):
    """12.3 安全提示: denied accesses by user, login refusals/lockouts, key changes, interface failures."""
    f,_,_=filters_from(request,{'days'})
    days=f.get('days','7')
    if not days.isdigit() or not 1<=int(days)<=90:raise HTTPException(422,'统计天数应为 1～90')
    def load(db,a,s):
        from ..security_alerts import security_summary
        return security_summary(db,a,int(days))
    return read_operation(request,'audit.read',load)

@router.get('/audit')
def audit_list(request:Request):
    from ..read_queries import AUDIT_FILTERS
    f,p,z=filters_from(request,AUDIT_FILTERS)
    def load(db,a,s):
        from ..read_queries import audit_query
        q=audit_query(db,a,f)
        return page_result(db,q.order_by(Audit.created_at.desc(),Audit.id),p,z)
    return read_operation(request,'audit.read',load)
