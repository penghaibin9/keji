"""External-integration internal substrate.

No production adapter is registered by default. A Connection remains
NOT_CONNECTED until a real school/third-party protocol, credential and network
path are supplied and accepted outside this module.
"""
from __future__ import annotations
from datetime import datetime, timedelta, date
from decimal import Decimal
from hashlib import sha256
import json
import os, re, importlib
from sqlalchemy import String, Integer, DateTime, JSON, Text, Boolean, ForeignKey, UniqueConstraint, Index, select, func
from sqlalchemy.orm import Mapped, mapped_column
from fastapi import HTTPException
from .models import Base, Entity, Connection, Task, TaskAttempt, utcnow
from .core import serial, digest


class SyncItem(Entity, Base):
    __tablename__='sync_items'
    task_id: Mapped[str] = mapped_column(ForeignKey('tasks.id'),index=True)
    connection_id: Mapped[str] = mapped_column(ForeignKey('connections.id'),index=True)
    data_type: Mapped[str] = mapped_column(String(64),index=True)
    business_key: Mapped[str] = mapped_column(String(160),index=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    idempotency_key: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String(20),default='PENDING',index=True)
    attempts: Mapped[int] = mapped_column(Integer,default=0)
    next_at: Mapped[datetime] = mapped_column(DateTime,default=utcnow,index=True)
    result: Mapped[dict] = mapped_column(JSON,default=dict)
    error: Mapped[str] = mapped_column(Text,default='')
    version: Mapped[int] = mapped_column(Integer,default=1)
    __table_args__=(UniqueConstraint('connection_id','data_type','idempotency_key'),Index('ix_sync_item_task_state','task_id','state'))


class SyncCallLog(Entity, Base):
    __tablename__='sync_call_logs'
    item_id: Mapped[str] = mapped_column(ForeignKey('sync_items.id'),index=True)
    attempt: Mapped[int] = mapped_column(Integer)
    request_digest: Mapped[str] = mapped_column(String(64))
    response_digest: Mapped[str] = mapped_column(String(64), default='')
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    response_code: Mapped[str] = mapped_column(String(40),default='')
    result: Mapped[str] = mapped_column(String(20))
    message: Mapped[str] = mapped_column(Text,default='')
    __table_args__=(UniqueConstraint('item_id','attempt'),)


# Procurement item/data coverage registry. "local_status" reports only the
# current platform's local source coverage, never external connectivity.
DATA_CATALOG={
 'sso':[
  ('identity','统一认证身份字段与角色/组织映射','WAITING_PROTOCOL')],
 'middle':[
  ('teacher_hr','教师人事信息','AVAILABLE'),('training_income','培训收入','AVAILABLE'),('course_participants','课程人次','AVAILABLE'),
  ('training_project','培训项目基础信息','AVAILABLE'),('course','课程基础信息','AVAILABLE')],
 'province':[
  ('training_project','培训项目','AVAILABLE'),('course','课程','AVAILABLE'),('plan','培训计划','WAITING_SOURCE'),('class','班级','AVAILABLE'),
  ('teaching','教师授课','AVAILABLE'),('participants','人次','AVAILABLE'),('learning_process','学习过程','WAITING_SOURCE'),
  ('training_record','培训记录','AVAILABLE'),('assessment_result','考核结果','AVAILABLE'),('completion_result','结业结果','WAITING_SOURCE'),
  ('certificate','证书信息','WAITING_SOURCE')]
}

ALLOWED_TRANSFORMS={'text','int','decimal','date','bool'}

# Deployment modules must implement the real wire operation required by each
# procurement integration before they can even be registered as production
# adapters.  This catches half-built adapters before a connection can be probed.
REQUIRED_ADAPTER_METHODS={
 'sso':('probe','build_login_url','complete_login'),
 'middle':('probe','pull'),
 'province':('probe','send'),
}


def catalog_for(connection:Connection):
    mappings=normalize_mappings(connection.mappings or [])
    out=[]
    for code,name,status in DATA_CATALOG.get(connection.code,[]):
        typed=[m for m in mappings if m.get('data_type')==code]
        legacy=[m for m in mappings if not m.get('data_type')]
        out.append({'data_type':code,'name':name,'local_status':status,'connection_state':connection.state,'mapping_count':len(typed or legacy)})
    return out


def normalize_mapping(mapping):
    if not isinstance(mapping,dict):raise HTTPException(422,'字段映射项无效')
    allowed={'data_type','source','target','transform','required','default'}
    if set(mapping)-allowed:raise HTTPException(422,'字段映射包含未知配置')
    data_type=str(mapping.get('data_type','')).strip();source=str(mapping.get('source','')).strip();target=str(mapping.get('target','')).strip();transform=str(mapping.get('transform','text')).strip()
    if data_type and (len(data_type)>64 or not all(c.isalnum() or c in '_-' for c in data_type)):raise HTTPException(422,'字段映射数据类型无效')
    if not source or not target or len(source)>120 or len(target)>120 or transform not in ALLOWED_TRANSFORMS:raise HTTPException(422,'字段映射定义无效')
    required=mapping.get('required',False)
    if type(required) is not bool:raise HTTPException(422,'字段映射 required 必须是真正的布尔值')
    out={'source':source,'target':target,'transform':transform,'required':required,'default':mapping.get('default')}
    if data_type:out['data_type']=data_type
    return out


def normalize_mappings(mappings):
    if not isinstance(mappings,list) or len(mappings)>300:raise HTTPException(422,'字段映射列表无效')
    out=[normalize_mapping(x) for x in mappings]
    if len({(x.get('data_type',''),x['target']) for x in out})!=len(out):raise HTTPException(422,'同一数据类型的目标字段不能重复映射')
    return out


def convert(value,kind):
    if value in (None,''):return value
    try:
        if kind=='text':return str(value).strip()
        if kind in {'int','decimal'}:
            if isinstance(value,bool) or len(str(value))>128:raise ValueError('number')
            number=Decimal(str(value))
            if not number.is_finite() or abs(number.adjusted())>100:raise ValueError('finite number')
            if kind=='int':
                if number!=number.to_integral_value() or not -(2**63)<=number<2**63:raise ValueError('integer')
                return int(number)
            return str(number)
        if kind=='date':return date.fromisoformat(str(value)).isoformat()
        if kind=='bool':
            if value in (True,1,'1','true','TRUE','是'):return True
            if value in (False,0,'0','false','FALSE','否'):return False
            raise ValueError('bool')
    except Exception:raise ValueError('转换失败') from None
    raise ValueError('未知转换')


def apply_mappings(connection:Connection,record:dict,data_type=None):
    if not isinstance(record,dict):raise HTTPException(422,'报文记录必须为对象')
    mapped={};errors=[]
    mappings=normalize_mappings(connection.mappings or [])
    typed=[m for m in mappings if m.get('data_type')==data_type] if data_type else []
    selected=typed or [m for m in mappings if not m.get('data_type')]
    for m in selected:
        if m['source'] in record:value=record[m['source']]
        else:
            from .adapters.common import path_get
            value=path_get(record,m['source'],m['default'])
        if value in (None,'') and m['required']:
            errors.append(f"{m['source']} 缺失");continue
        try:mapped[m['target']]=convert(value,m['transform'])
        except ValueError:errors.append(f"{m['source']} 转换失败")
    return mapped,errors


def business_idempotency(connection_id,data_type,business_key,payload):
    return digest({'connection_id':connection_id,'data_type':data_type,'business_key':business_key,'payload':payload})


class AdapterRegistry:
    """Only deployment-installed modules can register production adapters.

    The endpoint is pinned by deployment, not by an administrator's web input.
    Test adapters can never be returned while production mode is enabled.
    """
    def __init__(self):
        self._items={}; self._test_codes=set(); self._endpoints={}; self._credential_envs={}; self.production=False
    def register_for_test(self,code,adapter):
        if self.production: raise RuntimeError('TEST_ADAPTER_FORBIDDEN_IN_PRODUCTION')
        self._items[code]=adapter; self._test_codes.add(code)
    def register_production(self,code,adapter,*,endpoint,credential_env):
        from urllib.parse import urlsplit
        u=urlsplit(endpoint)
        required=REQUIRED_ADAPTER_METHODS.get(code,())
        if (not isinstance(credential_env,str) or not re.fullmatch(r'[A-Z][A-Z0-9_]{2,100}',credential_env) or code not in DATA_CATALOG or u.scheme!='https' or not u.hostname or u.username or u.password
            or u.query or u.fragment or any(not callable(getattr(adapter,name,None)) for name in required)
            or not re.fullmatch(r'[A-Za-z0-9_.:-]{3,128}',str(getattr(adapter,'adapter_id','')))):
            raise ValueError('INVALID_PRODUCTION_ADAPTER_CONTRACT')
        self._items[code]=adapter; self._test_codes.discard(code); self._endpoints[code]=endpoint; self._credential_envs[code]=credential_env
    def configure(self,production,modules=()):
        self.production=production
        for name in modules:
            if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*',name):
                raise RuntimeError('INVALID_ADAPTER_MODULE')
            importlib.import_module(name).register(self)
    def clear(self):
        self._items.clear(); self._test_codes.clear(); self._endpoints.clear(); self._credential_envs.clear()
    def get(self,code):
        if self.production and code in self._test_codes:return None
        return self._items.get(code)
    def is_real(self,code):return code in self._items and code not in self._test_codes
    def endpoint_matches(self,connection):
        return self._endpoints.get(connection.code)==(connection.config or {}).get('endpoint')

    def credential_matches(self,connection):
        return self._credential_envs.get(connection.code)==(connection.config or {}).get('secret_env')

ADAPTERS=AdapterRegistry()

class ConnectionCheck(Entity, Base):
    __tablename__='connection_checks'
    connection_id: Mapped[str] = mapped_column(ForeignKey('connections.id'),index=True)
    configuration_hash: Mapped[str] = mapped_column(String(64))
    adapter_id: Mapped[str] = mapped_column(String(128),default='')
    mode: Mapped[str] = mapped_column(String(20))
    passed: Mapped[bool] = mapped_column(Boolean,default=False)
    reason_code: Mapped[str] = mapped_column(String(64))
    receipt: Mapped[dict] = mapped_column(JSON,default=dict)
    actor_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    expires_at: Mapped[datetime] = mapped_column(DateTime)

def configuration_hash(connection):
    return digest({'id':connection.id,'config':connection.config or {},'mappings':connection.mappings or []})

def current_connection_check(db, connection, *, activated=False):
    """Bind proof to a locked logical revision, never wall-clock/UUID ordering.

    Activation increments Connection.version once. Pre-R9 proof has no revision
    and must be reverified, not amended retroactively. Ambiguous proof fails shut.
    """
    revision=connection.version-(1 if activated else 0)
    rows=db.scalars(select(ConnectionCheck).where(
        ConnectionCheck.connection_id==connection.id,
        ConnectionCheck.receipt['_connection_revision'].as_integer()==revision
    ).limit(2).execution_options(populate_existing=True)).all()
    if len(rows)!=1:return None
    check=rows[0]
    if type((check.receipt or {}).get('_connection_revision')) is not int:return None
    return check


def live_connection(db,connection,registry=ADAPTERS):
    if not connection or connection.state!='CONNECTED':return False
    if not registry.production:return True  # Isolated development fixtures only; production startup sets True.
    adapter=registry.get(connection.code)
    if adapter is None or not registry.is_real(connection.code) or not registry.endpoint_matches(connection) or not registry.credential_matches(connection):return False
    check=current_connection_check(db,connection,activated=True)
    return bool(check and check.mode=='REAL' and check.passed and check.expires_at>utcnow()
                and check.configuration_hash==configuration_hash(connection)
                and check.adapter_id==getattr(adapter,'adapter_id',None)
                and check.receipt.get('_credential_sha256')==credential_fingerprint(connection))

def pause_schedules(db,connection,reason):
    from .inbound_sync import IntegrationSchedule
    for schedule in db.scalars(select(IntegrationSchedule).where(IntegrationSchedule.connection_id==connection.id,IntegrationSchedule.active.is_(True))):
        schedule.active=False;schedule.last_error=reason;schedule.version+=1
        from .sync_policy import invalidate_schedule_tasks
        invalidate_schedule_tasks(db,schedule.id,reason)

def probe_connection(db,actor,connection,registry=ADAPTERS,*,production=False):
    actor.require_admin()
    connection=db.scalar(select(Connection).where(Connection.id==connection.id)
        .with_for_update().execution_options(populate_existing=True))
    if not connection:raise HTTPException(404,'接口配置不存在')
    adapter=registry.get(connection.code)
    mode='REAL' if production and registry.is_real(connection.code) else 'TEST_ONLY'
    code='ADAPTER_NOT_REGISTERED';passed=False;receipt={}
    if adapter is not None:
        if mode=='REAL' and (not registry.endpoint_matches(connection) or not registry.credential_matches(connection)):code='CONNECTION_CONTEXT_NOT_PINNED'
        elif not callable(getattr(adapter,'probe',None)):code='PROBE_NOT_IMPLEMENTED'
        else:
            secret_name=(connection.config or {}).get('secret_env','');credential=os.environ.get(secret_name,'')
            if not credential:code='CREDENTIAL_MISSING'
            else:
                try:
                    # The adapter is responsible for TLS verification, pinned DNS/redirect policy,
                    # transport timeouts and the actual school-specific authentication handshake.
                    response=adapter.probe(config=dict(connection.config or {}),credential=credential,timeout_seconds=10)
                    passed=(isinstance(response,dict) and all(response.get(k) is True for k in
                            ('authenticated','tls_verified','protocol_verified')))
                    code='VERIFIED' if passed else 'PROBE_REJECTED'
                    if isinstance(response,dict):
                        receipt={'response_digest':digest(serial(response)),
                            'authenticated':response.get('authenticated') is True,
                            'tls_verified':response.get('tls_verified') is True,
                            'protocol_verified':response.get('protocol_verified') is True,'_credential_sha256':credential_fingerprint(connection)}
                except Exception:code='PROBE_FAILED'  # No exception text/URL/credential is persisted.
    receipt={**receipt,'_connection_revision':connection.version+1}
    check=ConnectionCheck(connection_id=connection.id,configuration_hash=configuration_hash(connection),
        adapter_id=str(getattr(adapter,'adapter_id',''))[:128],mode=mode,passed=passed,reason_code=code,
        receipt=receipt,actor_id=actor.id,expires_at=utcnow()+timedelta(hours=24))
    db.add(check)
    # A failed recheck must stop writes immediately, not leave a stale green state.
    connection.state='NOT_CONNECTED';connection.version+=1
    pause_schedules(db,connection,'连接复核后需要重新确认启用')
    db.flush();return check

def activate_connection(db,actor,connection,check_id,registry=ADAPTERS):
    actor.require_admin()
    connection=db.scalar(select(Connection).where(Connection.id==connection.id).with_for_update().execution_options(populate_existing=True))
    if not connection:raise HTTPException(404,'接口配置不存在')
    check=db.get(ConnectionCheck,check_id);adapter=registry.get(connection.code)
    latest=current_connection_check(db,connection)
    if (not check or not latest or latest.id!=check.id or check.connection_id!=connection.id or not check.passed
        or check.mode!='REAL' or check.expires_at<=utcnow() or check.configuration_hash!=configuration_hash(connection)
        or adapter is None or not registry.is_real(connection.code) or not registry.endpoint_matches(connection)
        or not registry.credential_matches(connection)
        or check.adapter_id!=getattr(adapter,'adapter_id',None)
        or check.receipt.get('_credential_sha256')!=credential_fingerprint(connection)):
        raise HTTPException(409,'缺少当前配置的有效真实连接验证，不能启用；本地测试不算真实接通')
    connection.state='CONNECTED';connection.version+=1
    # Schedules stay disabled until an administrator explicitly approves them again.
    return connection

def credential_fingerprint(connection):
    from hashlib import sha256
    value=os.environ.get((connection.config or {}).get('secret_env',''),'')
    return sha256(value.encode()).hexdigest() if value else None

def transport_kwargs(connection,registry):
    """Explicit per-call context for deployment adapters; test doubles remain isolated."""
    if not registry.production:return {}
    if not registry.credential_matches(connection):raise RuntimeError('CREDENTIAL_REFERENCE_NOT_PINNED')
    secret=os.environ.get((connection.config or {}).get('secret_env',''),'')
    if not secret:raise RuntimeError('CREDENTIAL_MISSING')
    if not registry.endpoint_matches(connection):raise RuntimeError('ENDPOINT_NOT_PINNED')
    return {'config':dict(connection.config or {}),'credential':secret,'timeout_seconds':10}

def safe_acknowledgement(response):
    if not isinstance(response,dict) or response.get('accepted') is not True:
        raise RuntimeError('UPSTREAM_NOT_ACKNOWLEDGED')
    code=str(response.get('code','ACK'))
    if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,40}',code):code='ACK'
    safe={'accepted':True,'code':code,'response_digest':digest(serial(response))}
    receipt_id=str(response.get('receipt_id',''))
    if re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}',receipt_id):safe['receipt_id']=receipt_id
    return safe


def enqueue_sync(db,actor,connection,data_type,records,reason='', *, return_created=False):
    if data_type not in {x[0] for x in DATA_CATALOG.get(connection.code,[])}:raise HTTPException(422,'数据类型不在采购接口目录')
    if not isinstance(records,list) or not 1<=len(records)<=1000:raise HTTPException(422,'单次同步记录数量无效')
    seen=set()
    for i,source in enumerate(records):
        if not isinstance(source,dict):raise HTTPException(422,{'row':i+1,'errors':['记录必须为对象']})
        business_key=str(source.get('business_key') or source.get('id') or source.get('external_key') or '').strip()
        if not business_key or len(business_key)>160 or business_key in seen:raise HTTPException(422,{'row':i+1,'errors':['业务唯一键为空、超过160字符或同批重复']})
        seen.add(business_key)
    key='sync-'+digest({'connection':connection.id,'type':data_type,'records':records,'configuration_hash':configuration_hash(connection)})[:64]
    existing=db.scalar(select(Task).where(Task.key==key))
    if existing:return (existing,False) if return_created else existing
    task=Task(kind='sync',owner_id=actor.id,key=key,payload={'connection_id':connection.id,'connection_code':connection.code,'data_type':data_type,'reason':reason,'configuration_hash':configuration_hash(connection),'requested_rows':len(records),'reused_item_ids':[]},state='PENDING')
    db.add(task);db.flush(); reused=[]
    for i,source in enumerate(records):
        mappings=normalize_mappings(connection.mappings or [])
        if not any(not m.get('data_type') or m.get('data_type')==data_type for m in mappings):
            raise HTTPException(409,'当前同步类型缺少字段映射，禁止发送空报文')
        mapped,errors=apply_mappings(connection,source,data_type)
        if errors:raise HTTPException(422,{'row':i+1,'errors':errors})
        business_key=str(source.get('business_key') or source.get('id') or source.get('external_key') or '').strip()
        if not business_key:raise HTTPException(422,{'row':i+1,'errors':['缺少业务唯一键 business_key/id/external_key']})
        idem=business_idempotency(connection.id,data_type,business_key,{'configuration_hash':configuration_hash(connection),'mapped':mapped})
        old=db.scalar(select(SyncItem).where(SyncItem.connection_id==connection.id,SyncItem.data_type==data_type,SyncItem.idempotency_key==idem))
        if old:
            reused.append(old.id)
            continue
        db.add(SyncItem(task_id=task.id,connection_id=connection.id,data_type=data_type,business_key=business_key,payload_hash=digest(mapped),idempotency_key=idem,payload=mapped,state='PENDING'))
    task.payload={**task.payload,'reused_item_ids':reused}
    db.flush();return (task,True) if return_created else task


def process_sync_task_once(db,task:Task,registry=ADAPTERS):
    if task.kind!='sync':raise ValueError('not sync task')
    if task.state not in {'PENDING','RETRY'}:return task
    from .sync_policy import sync_actor, block_task, retry_exhausted
    try:actor=sync_actor(db,task)
    except HTTPException:
        return block_task(db,task,'同步发起人账号或同步操作权限已失效','EXECUTION_AUTHORIZATION_REVOKED')
    if not isinstance(task.payload,dict):return block_task(db,task,'同步任务内容不完整，请核对后重新建批','SYNC_BATCH_INTEGRITY_FAILED')
    connection=db.get(Connection,task.payload.get('connection_id'))
    if not connection:
        task.state='FAILED';task.error='连接配置不存在';task.version+=1;return task
    if not live_connection(db,connection,registry):
        task.state='BLOCKED';task.error='外部接口未真实连接';task.version+=1
        db.add(TaskAttempt(task_id=task.id,attempt=task.attempts+1,result='BLOCKED',message='NOT_CONNECTED'))
        task.attempts+=1;return task
    adapter=registry.get(connection.code)
    if adapter is None:
        task.state='BLOCKED';task.error='当前发布未注册真实外部适配器';task.version+=1
        db.add(TaskAttempt(task_id=task.id,attempt=task.attempts+1,result='BLOCKED',message='ADAPTER_NOT_REGISTERED'))
        task.attempts+=1;return task
    if task.payload.get('configuration_hash') and task.payload['configuration_hash']!=configuration_hash(connection):
        task.state='BLOCKED';task.error='接口配置已变更，请核对并创建新同步任务';task.version+=1;return task
    if not sync_batch_consistent(db,task,connection):
        return block_task(db,task,'同步任务明细或内容摘要不一致，禁止发送，请核对原批次','SYNC_BATCH_INTEGRITY_FAILED')
    from .sync_policy import retry_budget
    retry_budget(connection)
    items=db.scalars(select(SyncItem).where(SyncItem.task_id==task.id,SyncItem.state.in_(['PENDING','RETRY']),SyncItem.next_at<=utcnow()).order_by(SyncItem.created_at,SyncItem.id)).all()
    if not items:
        return finalize_sync_task(db,task)
    task.state='RUNNING';task.attempts+=1
    for item in items:
        item.attempts+=1;request_digest=digest(item.payload)
        try:
            response=adapter.send(data_type=item.data_type,payload=serial(item.payload),idempotency_key=item.idempotency_key,**transport_kwargs(connection,registry))
            receipt=safe_acknowledgement(response)
            item.state='DONE';item.result=receipt;item.error='';code=receipt['code']
            db.add(SyncCallLog(item_id=item.id,attempt=item.attempts,request_digest=request_digest,response_code=code,response_digest=receipt['response_digest'],acknowledged=True,result='SUCCESS',message=''))
        except Exception as exc:
            message=type(exc).__name__
            from .adapters.contracts import AdapterContractError
            upstream_code=getattr(exc,'upstream_code','') if isinstance(exc,AdapterContractError) else ''
            if not isinstance(upstream_code,str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,40}',upstream_code):upstream_code=''
            item.error=message
            if retry_exhausted(item.attempts,(item.result or {}).get('retry_base_attempt',0),connection):item.state='FAILED'
            else:
                item.state='RETRY';item.next_at=utcnow()+timedelta(seconds=min(300,2**item.attempts))
            db.add(SyncCallLog(item_id=item.id,attempt=item.attempts,request_digest=request_digest,response_code=upstream_code,result='ERROR',message=message))
        item.version+=1
    db.flush()
    finalize_sync_task(db,task)
    db.add(TaskAttempt(task_id=task.id,attempt=task.attempts,result=task.state,message=task.error or 'sync pass'))
    return task

def sync_batch_consistent(db,task,connection):
    """Check the ENTIRE queued batch before the first remote side effect.

    Digests detect accidental corruption/incomplete queue state, not an attacker
    who can rewrite all database evidence. The worker owns the task lock; reused
    rows are references and are never sent by this task.
    """
    payload=task.payload
    if not isinstance(payload,dict):return False
    kind=payload.get('data_type');stamp=payload.get('configuration_hash')
    reused=payload.get('reused_item_ids');count=payload.get('requested_rows')
    if (kind not in {x[0] for x in DATA_CATALOG.get(connection.code,[])}
        or payload.get('connection_id')!=connection.id
        or payload.get('connection_code')!=connection.code
        or stamp!=configuration_hash(connection)
        or type(count) is not int or not 1<=count<=1000
        or not isinstance(reused,list) or len(reused)>count
        or any(not isinstance(x,str) or not x for x in reused)
        or len(set(reused))!=len(reused)):return False
    rows=task_sync_items(db,task)
    if len(rows)!=count or not set(reused).issubset({x.id for x in rows}):return False
    owner_ids={x.task_id for x in rows}
    owners={x.id:x for x in db.scalars(select(Task).where(Task.id.in_(owner_ids)))}
    keys=set()
    for item in rows:
        owner=owners.get(item.task_id)
        if (item.connection_id!=connection.id or item.data_type!=kind
            or not isinstance(item.business_key,str) or not item.business_key
            or item.business_key in keys or item.state not in {'PENDING','RETRY','RUNNING','DONE','FAILED','BLOCKED'}
            or not isinstance(item.payload,dict) or not owner or owner.kind!='sync'
            or not isinstance(owner.payload,dict)
            or any(owner.payload.get(k)!=payload.get(k) for k in ('connection_id','connection_code','data_type','configuration_hash'))
            or ((item.id in reused)!=(item.task_id!=task.id))):return False
        keys.add(item.business_key)
        try:
            if item.payload_hash!=digest(item.payload):return False
            if item.idempotency_key!=business_idempotency(connection.id,kind,item.business_key,
                {'configuration_hash':stamp,'mapped':item.payload}):return False
        except (ValueError,TypeError,OverflowError):return False
    return True


def task_sync_items(db,task):
    reused=(task.payload or {}).get('reused_item_ids') or []
    return db.scalars(select(SyncItem).where((SyncItem.task_id==task.id)|(SyncItem.id.in_(reused))).order_by(SyncItem.created_at,SyncItem.id)).all()

def finalize_sync_task(db,task):
    rows=task_sync_items(db,task)
    success=sum(x.state=='DONE' for x in rows); failed=sum(x.state in {'FAILED','BLOCKED'} for x in rows)
    waiting=[x for x in rows if x.state in {'PENDING','RETRY','RUNNING'}]
    invalid=not rows or len(rows)!=task.payload.get('requested_rows',len(rows)) or success+failed+len(waiting)!=len(rows)
    task.state='FAILED' if invalid else 'RETRY' if waiting else 'FAILED' if failed else 'DONE'
    task.error='存在失败或缺失同步项' if failed or invalid else ''
    if waiting:task.next_at=max(utcnow()+timedelta(seconds=2),min(x.next_at for x in waiting))
    task.result={'total':len(rows),'success':success,'failed':failed,'waiting':len(waiting),
                 'reused':len((task.payload or {}).get('reused_item_ids') or []),'requested_rows':task.payload.get('requested_rows',len(rows))}
    task.version+=1
    return task
