"""R2 new shared authorization / transaction implementation for recovered services.

No mocked users, no seed path, no inferred historical migrations. All successful
commands and their critical audit/receipt commit together, before HTTP returns.
"""
from __future__ import annotations
from datetime import date, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlsplit
import hmac, json, re
from sqlalchemy import create_engine, select, func, event, inspect as sa_inspect, delete
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, Request
from .models import *
from .permissions import ALLOWED, validate_permissions

SECRET_COLUMNS = {'_credential_sha256','password_hash','token_hash','csrf','failures','locked_until','auth_version','storage_key',
 'password','new_password','old_password','token','access_token','refresh_token','secret','client_secret','authorization'}

def serial(value):
    if value is None or isinstance(value,(str,int,bool,float)): return value
    if isinstance(value,Decimal): return str(value)
    if isinstance(value,(datetime,date)): return value.isoformat()
    if isinstance(value,dict): return {str(k):serial(v) for k,v in value.items() if str(k).lower() not in SECRET_COLUMNS}
    if isinstance(value,(list,tuple,set)): return [serial(v) for v in value]
    if isinstance(value,Base):
        return {c.key:serial(getattr(value,c.key)) for c in sa_inspect(type(value)).columns if c.key not in SECRET_COLUMNS}
    raise TypeError('无法序列化该业务对象')

def digest(value):
    return sha256(json.dumps(serial(value),sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def make_engine(url):
    if url.startswith('sqlite://'):
        engine=create_engine(url,connect_args={'check_same_thread':False,'timeout':10},hide_parameters=True)
        @event.listens_for(engine,'connect')
        def fk(conn,_): conn.execute('PRAGMA foreign_keys=ON')
        return engine
    return create_engine(url,pool_pre_ping=True,pool_size=10,max_overflow=10,pool_recycle=1200,
                         isolation_level='READ COMMITTED',hide_parameters=True,
                         connect_args={'connect_timeout':10})

def org_scope(db,org,kind):
    orgs={o.id:o for o in db.scalars(select(Org))}
    if org.id not in orgs or kind not in ALLOWED or not org.active:
        raise HTTPException(403,'组织或角色无效')
    expected={'teacher':'dept','dept':'dept','college':'college','school':'school'}[kind]
    if org.kind!=expected: raise HTTPException(403,'角色与组织层级不匹配')
    seen=set(); cursor=org
    while cursor is not None:
        if cursor.id in seen or not cursor.active: raise HTTPException(403,'组织关系无效')
        seen.add(cursor.id)
        if cursor.kind=='school':
            if cursor.parent_id is not None: raise HTTPException(403,'学校根组织关系无效')
            break
        parent=orgs.get(cursor.parent_id)
        if parent is None or (cursor.kind,parent.kind) not in {('dept','college'),('college','school')}:
            raise HTTPException(403,'组织层级不完整')
        cursor=parent
    if cursor is None: raise HTTPException(403,'学校归属不存在')
    ids={org.id}; frontier={org.id}
    while frontier:
        children={o.id for o in orgs.values() if o.active and o.parent_id in frontier}
        if children & ids or len(ids|children)>10000: raise HTTPException(503,'组织关系异常')
        for cid in children:
            child=orgs[cid]; parent=orgs[child.parent_id]
            if (parent.kind,child.kind) not in {('school','college'),('college','dept')}:
                raise HTTPException(503,'组织层级异常')
        ids |= children; frontier=children
    return sorted(ids)

class Actor:
    def __init__(self,db,user,role,org,request=None):
        if not user.active or not role.active or not validate_permissions(role.kind,role.permissions):
            raise HTTPException(403,'账号或角色已停用，或授权配置无效')
        self.user,self.role,self.org=user,role,org
        self.id,self.name=user.id,user.name
        self.org_ids=org_scope(db,org,role.kind)
        self.permissions=frozenset(role.permissions)
        self.request_id=getattr(getattr(request,'state',None),'request_id','')
        # Read paths use a database subquery through scope() and should not copy
        # every authorized teacher id into Python on every request.  A concrete
        # tuple is loaded lazily only for operations that must freeze or compare
        # an exact authorization snapshot (exports/imports/fingerprints).
        self._db=db
        self._teacher_ids=(user.id,) if role.kind=='teacher' else None
    def require(self,permission):
        if permission not in self.permissions: raise HTTPException(403,'无权执行此操作')
    def require_admin(self):
        if self.role.kind!='school' or not self.user.is_admin:
            raise HTTPException(403,'需要学校系统管理员授权')
    @property
    def teacher_ids(self):
        if self._teacher_ids is None:
            self._teacher_ids=tuple(self._db.scalars(select(User.id).where(
                User.org_id.in_(self.org_ids),User.staff_no.is_not(None))))
        return self._teacher_ids
    def scope(self,column):
        if self.role.kind=='teacher': return column==self.id
        return column.in_(select(User.id).where(
            User.org_id.in_(self.org_ids),User.staff_no.is_not(None)))
    def check_teacher(self,db,teacher_id,active=False):
        user=db.get(User,teacher_id)
        if (user is None or not user.staff_no or user.org_id not in self.org_ids
                or (self.role.kind=='teacher' and teacher_id!=self.id)
                or (active and not user.active)):
            raise HTTPException(403,'教师不在当前授权业务范围')
        return user
    def fingerprint(self):
        return digest({'actor':self.id,'version':self.user.auth_version,'role':self.role.id,'rv':self.role.version,
            'org':self.org.id,'orgs':self.org_ids,'teachers':sorted(self.teacher_ids),'permissions':sorted(self.permissions)})

def check_origin(request):
    cfg=request.app.state.settings
    if request.headers.get('sec-fetch-site') in {'cross-site','same-site'}:
        raise HTTPException(403,'跨站写请求已拒绝')
    source=request.headers.get('origin')
    if source is None:
        ref=request.headers.get('referer','')
        parsed=urlsplit(ref)
        source=f'{parsed.scheme}://{parsed.netloc}' if parsed.scheme and parsed.netloc else ''
    if source!=cfg.public_origin: raise HTTPException(403,'请求来源校验失败')

def current_actor(db,request,*,allow_password=False,write=False):
    cfg=request.app.state.settings
    raw=request.cookies.get(cfg.cookie_name,'')
    if not re.fullmatch(r'[A-Za-z0-9_-]{40,90}',raw): raise HTTPException(401,'登录已失效，请重新登录')
    session=db.get(AuthSession,sha256(raw.encode()).hexdigest())
    now=utcnow()
    if not session or session.expires_at<=now or session.last_seen<now-timedelta(minutes=cfg.session_idle_minutes):
        raise HTTPException(401,'登录已失效，请重新登录')
    user=db.scalar(select(User).where(User.id==session.user_id).with_for_update()) if write else db.get(User,session.user_id)
    if not user or not user.active or user.auth_version!=session.auth_version:
        raise HTTPException(401,'账号状态已变化，请重新登录')
    role,org=db.get(Role,user.role_id),db.get(Org,user.org_id)
    if not role or not org: raise HTTPException(403,'账号组织权限不完整')
    actor=Actor(db,user,role,org,request)
    from .demo_identity import resolve
    actor=resolve(db,request,actor,session,write=write)
    request.state.actor_id,request.state.actor_name,request.state.org_id=actor.id,actor.name,actor.org.id
    if user.must_change_password and not allow_password: raise HTTPException(403,'首次登录请先修改临时密码')
    if write:
        check_origin(request)
        supplied=request.headers.get('x-csrf-token','')
        if not supplied or not hmac.compare_digest(supplied,session.csrf): raise HTTPException(403,'请求校验已失效，请刷新后重试')
    if (now-session.last_seen).total_seconds() >= 60:
        session.last_seen=now
    return actor,session

def audit(db,actor,module,object_id,action,before=None,after=None,reason='',result='SUCCESS'):
    controller=getattr(actor,'demo_controller',None)
    if controller and controller.id!=actor.id:
        after=dict(after or {},demo_operator={'id':controller.id,'username':controller.user.username})
    obj=Audit(actor_id=actor.id,actor_name=actor.name,org_id=actor.org.id,module=module,
      object_id=str(object_id)[:128],action=action,before=serial(before or {}),after=serial(after or {}),
      reason=reason,result=result,request_id=actor.request_id)
    db.add(obj); db.flush() # Raise in the business transaction, never swallow.
    return obj

def workflow(db,actor,object_type,object_id,action,before,after,reason,basis=''):
    ev=WorkflowEvent(object_type=object_type,object_id=object_id,actor_id=actor.id,actor_name=actor.name,
        org_id=actor.org.id,action=action,before=serial(before),after=serial(after),reason=reason,basis=basis)
    db.add(ev); audit(db,actor,object_type,object_id,action,before,after,reason)
    return ev

def lock_guard(db,key):
    obj=db.scalar(select(Guard).where(Guard.key==key).with_for_update())
    if obj is None: raise HTTPException(503,'业务初始化未完成')
    # SQLite lacks FOR UPDATE; a real UPDATE also locks the test writer. MySQL
    # uses the same row lock. No parallel unguarded write command is introduced.
    obj.version+=1;db.flush()

def archive_exists(db,teacher_id,period_id):
    return db.scalar(select(Assessment.id).where(Assessment.teacher_id==teacher_id,Assessment.period_id==period_id,Assessment.state=='ARCHIVED')) is not None

def check_version(obj,expected):
    if obj.version!=expected: raise HTTPException(409,'数据已被其他操作更新，请刷新核对')

def require_open_period(db,period_id):
    p=db.get(Period,period_id)
    if not p: raise HTTPException(404,'考核周期不存在')
    if p.state!='OPEN': raise HTTPException(409,'本周期已关闭，不允许修改')
    return p

def read_operation(request,permission,fn,*,allow_password=False):
    with request.app.state.sessions.begin() as db:
        actor,session=current_actor(db,request,allow_password=allow_password)
        if permission: actor.require(permission)
        return serial(fn(db,actor,session))

def command(request,payload,permission,fn,*,allow_password=False):
    raw=request.headers.get('idempotency-key','')
    if not re.fullmatch(r'[A-Za-z0-9_-]{8,128}',raw): raise HTTPException(422,'写入必须提供有效幂等请求编号')
    with request.app.state.sessions.begin() as db:
        # Authorization-changing writes and business writes share a guard. This
        # favors correctness until per-object MySQL concurrency is measured.
        lock_guard(db,'calculations')
        actor,session=current_actor(db,request,allow_password=allow_password,write=True)
        if permission: actor.require(permission)
        key=sha256((actor.id+'\0'+raw).encode()).hexdigest()
        # Hash the complete input, including password changes, without storing
        # any input secret. Audit serialization is deliberately a separate path.
        try:
            raw_payload=json.dumps({'method':request.method,'path':request.url.path,'body':payload},
                sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False,
                default=lambda v:v.isoformat() if isinstance(v,(date,datetime)) else str(v) if isinstance(v,Decimal) else (_ for _ in ()).throw(TypeError('输入格式无效')))
        except (ValueError,TypeError):
            raise HTTPException(422,'请求包含非法数值或无法保存的数据格式') from None
        request_hash=sha256(raw_payload.encode()).hexdigest()
        receipt=db.get(Receipt,key)
        auth_fingerprint=actor.fingerprint()
        if receipt:
            if receipt.actor_id!=actor.id or receipt.request_hash!=request_hash: raise HTTPException(409,'同一幂等编号不能用于不同操作')
            if receipt.response.get('authorization')!=auth_fingerprint: raise HTTPException(409,'权限范围已变化，请重新核对业务结果')
            return receipt.response['data']
        result=serial(fn(db,actor,session))
        db.add(Receipt(key=key,actor_id=actor.id,request_hash=request_hash,response={'data':result,'authorization':auth_fingerprint}))
        db.flush()
    return result

def page_result(db,query,page=1,size=20):
    total=db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    return {'items':serial(db.scalars(query.offset((page-1)*size).limit(size)).all()),'total':total,'page':page,'size':size}

def filters_from(request,allowed):
    values=dict(request.query_params)
    for key in request.query_params:
        if len(request.query_params.getlist(key))>1: raise HTTPException(422,'不允许重复筛选参数')
    page,size=values.pop('page','1'),values.pop('size','20')
    if not page.isdigit() or not size.isdigit() or not (1<=int(page)<=100000 and 1<=int(size)<=200):
        raise HTTPException(422,'分页参数无效')
    if set(values)-set(allowed): raise HTTPException(422,'含不支持的筛选字段')
    return {k:v for k,v in values.items() if v!=''},int(page),int(size)
