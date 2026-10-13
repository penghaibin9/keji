"""Formal integration configuration and task substrate.

Only current REAL handshake evidence can activate a deployment-installed adapter.
The browser cannot register adapters, forge proof, or enable a test-only connection.
"""
from __future__ import annotations
import re, json
from urllib.parse import urlsplit
from fastapi import APIRouter,Request,HTTPException
from sqlalchemy import select
from ..core import *
from ..schemas import (ConnectionUpdate,MappingValidate,SyncEnqueue,LedgerSync,TaskRetry,VersionedReason,InboundPreview,
    InboundPullRequest,IntegrationScheduleIn,IntegrationScheduleUpdate,IntegrationProfileApply)
from ..integrations import (DATA_CATALOG,catalog_for,normalize_mappings,apply_mappings,enqueue_sync,
                            SyncItem,SyncCallLog,ADAPTERS,ConnectionCheck,probe_connection,activate_connection,pause_schedules,live_connection,task_sync_items)
from ..reference_data import InboundBatch,InboundRow,preview_inbound,confirm_inbound,rollback_inbound
from ..inbound_sync import IntegrationSchedule,create_pull_task
from ..integration_status import latest_task_status,latest_task_ids
router=APIRouter(prefix='/api',tags=['接口同步'])


def _connection(db,ident):
    obj=db.get(Connection,ident)
    if not obj:raise HTTPException(404,'接口配置不存在')
    return obj


def _clean_config(config):
    if not isinstance(config,dict):raise HTTPException(422,'接口配置无效')
    allowed={'endpoint','owner','retry_count','secret_env','frequency_minutes','auth_mode','adapter'}
    if set(config)-allowed:raise HTTPException(422,'接口配置包含未允许字段')
    endpoint=str(config.get('endpoint','')).strip();owner=str(config.get('owner','')).strip();secret_env=str(config.get('secret_env','')).strip()
    if endpoint:
        u=urlsplit(endpoint)
        if u.scheme!='https' or not u.hostname or u.username or u.password or u.query or u.fragment:raise HTTPException(422,'正式接口地址必须是明确的HTTPS地址')
    if secret_env and not re.fullmatch(r'[A-Z][A-Z0-9_]{2,100}',secret_env):raise HTTPException(422,'密钥只登记环境变量名称')
    try:
        from ..integrations import convert
        retry=convert(config.get('retry_count',3),'int');frequency=convert(config.get('frequency_minutes',30),'int')
        if type(retry) is not int or type(frequency) is not int:raise ValueError('integer required')
    except Exception:raise HTTPException(422,'重试次数或同步频率无效') from None
    if not 3<=retry<=10 or not 1<=frequency<=10080:raise HTTPException(422,'重试次数或同步频率超出范围')
    auth=str(config.get('auth_mode','')).strip()
    if auth and auth not in {'token','signature','oauth2','oidc','cas','school_sso','custom'}:raise HTTPException(422,'鉴权模式无效')
    adapter=config.get('adapter') or {}
    try:
        from ..adapters.common import validate_adapter_config
        validate_adapter_config(adapter)
    except Exception as exc:
        code=getattr(exc,'code','ADAPTER_CONFIG_INVALID')
        raise HTTPException(422,'接口适配参数无效：请核对参数结构，敏感凭据只能填写服务器环境变量引用') from None
    if not isinstance(adapter,dict):raise HTTPException(422,'接口适配参数必须为对象')
    return {'endpoint':endpoint,'owner':owner,'retry_count':retry,'secret_env':secret_env,'frequency_minutes':frequency,'auth_mode':auth,'adapter':adapter}


@router.get('/connections/coordination.xlsx')
def coordination_template(request:Request):
    from pathlib import Path
    from urllib.parse import quote
    from fastapi.responses import Response
    with request.app.state.sessions.begin() as db:
        a,session=current_actor(db,request);a.require('sync.manage')
        path=Path(__file__).resolve().parents[1]/'resources/integration-coordination.xlsx'
        if not path.is_file():raise HTTPException(503,'对接沟通清单模板缺失，请联系部署人员')
        data=path.read_bytes()
        audit(db,a,'connections','coordination-template','下载对接沟通清单',reason='协调三类接口资料；不是接通或验收证明')
    return Response(data,media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote('明天去学校_三大接口资料收集与剩余工作表.xlsx'),'X-Content-Type-Options':'nosniff'})

@router.get('/connections/profile-template.json')
def connection_profile_template(request:Request):
    from fastapi.responses import JSONResponse
    from ..integration_profile_templates import templates,merge_template
    with request.app.state.sessions.begin() as db:
        a,session=current_actor(db,request);a.require_admin();a.require('sync.manage')
        base=templates(DATA_CATALOG);items={};secret_defaults={'sso':'ND_SSO_SECRET','middle':'ND_MIDDLE_SECRET','province':'ND_PROVINCE_SECRET'}
        auth_defaults={'sso':'school_sso','middle':'token','province':'custom'}
        for code in ('sso','middle','province'):
            obj=db.scalar(select(Connection).where(Connection.code==code))
            if not obj:raise HTTPException(503,'三大接口初始化记录不完整')
            config=dict(obj.config or {})
            if not config.get('secret_env'):config['secret_env']=secret_defaults[code]
            if not config.get('auth_mode'):config['auth_mode']=auth_defaults[code]
            config['adapter']=merge_template(base[code],config.get('adapter') or {})
            items[code]={'expected_version':obj.version,'config':config,'mappings':obj.mappings or []}
        payload={'format':'YUEKE_R11_THREE_INTEGRATIONS_V2','connections':items,
            'reason':'学校接口资料整理后导入','basis':'以学校/省平台正式接口资料为依据；密钥只放服务器环境变量'}
        audit(db,a,'connections','three-integration-profile','下载三大接口参数模板',reason='模板不含Secret，只用于整理学校正式资料')
    return JSONResponse(payload,headers={'Content-Disposition':'attachment; filename="yueke-r11-three-integrations-profile.json"','X-Content-Type-Options':'nosniff'})


@router.post('/connections/profile-apply')
def connection_profile_apply(data:IntegrationProfileApply,request:Request):
    def apply(db,a,s):
        a.require_admin();a.require('sync.manage')
        if set(data.connections)!={'sso','middle','province'}:raise HTTPException(422,'参数文件必须同时包含 sso / middle / province 三项')
        staged=[]
        for code in ('sso','middle','province'):
            item=data.connections[code];obj=db.scalar(select(Connection).where(Connection.code==code).with_for_update())
            if not obj:raise HTTPException(503,'三大接口初始化记录不完整')
            check_version(obj,item.expected_version)
            mappings=normalize_mappings(item.mappings);allowed={x[0] for x in DATA_CATALOG.get(code,[])}
            invalid=sorted({m.get('data_type') for m in mappings if m.get('data_type') and m.get('data_type') not in allowed})
            if invalid:raise HTTPException(422,code+' 字段映射数据类型不属于采购目录: '+','.join(invalid))
            config=_clean_config(item.config)
            staged.append((obj,config,mappings,serial(obj)))
        for obj,config,mappings,before in staged:
            obj.config=config;obj.mappings=mappings;obj.state='NOT_CONNECTED';obj.version+=1
            pause_schedules(db,obj,'三大接口参数文件已更新，需重新真实验证并审批计划')
            audit(db,a,'connections',obj.id,'导入三大接口参数文件',before,serial(obj),data.reason)
        return {'applied':True,'connections':{obj.code:{'id':obj.id,'version':obj.version,'state':'NOT_CONNECTED'} for obj,_,_,_ in staged},
                'note':'参数已保存但未启用；必须逐项真实probe并明确激活后才能联网'}
    return command(request,data.model_dump(),'sync.manage',apply)


@router.get('/connections/catalog')
def connection_catalog(request:Request):
    def load(db,a,s):
        out=[]
        for connection in db.scalars(select(Connection).order_by(Connection.code)):
            from ..integration_center import MATERIALS,stored,source_record_map,source_record_complete
            _,source_map=source_record_map(db,connection.id)
            data_types=[]
            for d in catalog_for(connection):
                record=source_map.get(d['data_type']) or {}
                data_types.append({**d,'connection_state':'CONNECTED' if live_connection(db,connection) else 'NOT_CONNECTED',
                    'source_confirmed':source_record_complete(record),
                    'source_system':record.get('source_system',''),'source_reference':record.get('reference','')})
            out.append({'connection':{**serial(connection),'state':'CONNECTED' if live_connection(db,connection) else 'NOT_CONNECTED'},'data_types':data_types})
            material_row=stored(db,'materials',connection.id)
            out[-1]['material_records']={'required':list(MATERIALS),'items':(material_row.value or {}).get('items',[]) if material_row else []}
        return {'items':out}
    return read_operation(request,'sync.manage',load)


@router.get('/connections/summary')
def connection_summary(request:Request):
    filters,_,_=filters_from(request,{'connection_id','data_type'})
    def load(db,a,s):
        if a.role.kind!='school':raise HTTPException(403,'仅学校管理角色查看全校接口运行状态')
        query=select(Connection).order_by(Connection.code)
        if filters.get('connection_id'):
            _connection(db,filters['connection_id']);query=query.where(Connection.id==filters['connection_id'])
        data_type=filters.get('data_type')
        if data_type and data_type not in {d[0] for rows in DATA_CATALOG.values() for d in rows}:
            raise HTTPException(422,'数据类型不在接口目录')
        connections=[c for c in db.scalars(query) if not data_type or data_type in {d[0] for d in DATA_CATALOG.get(c.code,[])}]
        latest=latest_task_ids(db,[c.id for c in connections],data_type)
        items=[]
        for connection in connections:
            items.append({'code':connection.code,'name':connection.name,
                'connection_state':'CONNECTED' if live_connection(db,connection) else 'NOT_CONNECTED',
                'latest_task':latest_task_status(db,connection,data_type,latest.get(connection.id))})
        return {'items':items,'all_connected':bool(items) and all(x['connection_state']=='CONNECTED' for x in items)}
    return read_operation(request,'portal.read',load)

@router.put('/connections/{ident}')
def update_connection(ident:str,data:ConnectionUpdate,request:Request):
    def apply(db,a,s):
        a.require_admin();obj=_connection(db,ident);check_version(obj,data.expected_version);before=serial(obj)
        mappings=normalize_mappings(data.mappings);allowed={x[0] for x in DATA_CATALOG.get(obj.code,[])}
        invalid=sorted({m.get('data_type') for m in mappings if m.get('data_type') and m.get('data_type') not in allowed})
        if invalid:raise HTTPException(422,'字段映射数据类型不属于当前接口采购目录: '+','.join(invalid))
        obj.mappings=mappings;obj.config=_clean_config(data.config)
        # Editing preparation data can never silently imply a live connection.
        obj.state='NOT_CONNECTED';obj.version+=1
        pause_schedules(db,obj,'接口配置已变更，需重新验证并审批计划')
        audit(db,a,'connections',obj.id,'修改接口参数与字段映射',before,serial(obj),data.reason);return obj
    return command(request,data.model_dump(),'sync.manage',apply)


@router.post('/connections/validate')
def validate_mapping(data:MappingValidate,request:Request):
    def apply(db,a,s):
        obj=_connection(db,data.connection_id)
        allowed={x[0] for x in DATA_CATALOG.get(obj.code,[])}
        if data.data_type not in allowed:raise HTTPException(422,'数据类型不在采购接口目录')
        normalized=normalize_mappings(obj.mappings or [])
        typed=[m for m in normalized if m.get('data_type')==data.data_type];legacy=[m for m in normalized if not m.get('data_type')]
        if obj.code!='sso' and not (typed or legacy):raise HTTPException(409,'当前数据类型尚未配置字段映射，不能把空映射校验当成通过')
        rows=[];errors=0
        for idx,record in enumerate(data.records,1):
            if obj.code=='sso' and data.data_type=='identity':
                a.require_admin()
                from ..sso_identity import preview_identity
                result=preview_identity(db,obj.config,record)
                rows.append({'row':idx,**result});errors+=bool(result['errors'])
            else:
                mapped,row_errors=apply_mappings(obj,record,data.data_type);errors+=bool(row_errors)
                rows.append({'row':idx,'mapped':mapped,'errors':row_errors})
        audit(db,a,'connections',obj.id,'本地字段映射校验',after={'data_type':data.data_type,'rows':len(rows),'error_rows':errors,'external_called':False},reason=data.reason)
        return {'connection_state':obj.state,'external_called':False,'items':rows,'error_rows':errors}
    return command(request,data.model_dump(),'sync.manage',apply)


@router.post('/connections/{ident}/sync')
def manual_sync(ident:str,data:SyncEnqueue,request:Request):
    def apply(db,a,s):
        a.require_admin();obj=_connection(db,ident)
        task,created=enqueue_sync(db,a,obj,data.data_type,data.records,data.reason,return_created=True)
        if created and not live_connection(db,obj):
            task.state='BLOCKED';task.error='外部接口未真实连接';task.version+=1
            for item in db.scalars(select(SyncItem).where(SyncItem.task_id==task.id)):
                item.state='BLOCKED';item.error='NOT_CONNECTED';item.version+=1
            task.attempts+=1
            db.add(TaskAttempt(task_id=task.id,attempt=task.attempts,result='BLOCKED',message='NOT_CONNECTED'))
        audit(db,a,'sync',task.id,'创建人工同步/补传任务',after={'connection':obj.code,'data_type':data.data_type,'records':len(data.records),'state':task.state},reason=data.reason)
        return task
    return command(request,data.model_dump(),'sync.manage',apply)


def _province(db,ident):
    obj=_connection(db,ident)
    if obj.code!='province':raise HTTPException(422,'只有湘培直通车支持从台账组装上报数据')
    return obj


def _ledger_filters(source):
    return {k:source.get(k) for k in ('start','end','period_id','org_id') if source.get(k)}


@router.get('/connections/{ident}/ledger-sync/catalog')
def ledger_sync_catalog(ident:str,request:Request):
    """11.3 which province types can be assembled locally, canonical fields, and why 4 types wait."""
    def load(db,a,s):
        obj=_province(db,ident)
        from ..province_payload import ledger_catalog
        mappings=normalize_mappings(obj.mappings or [])
        items=[{**x,'mapping_count':len([m for m in mappings if m.get('data_type')==x['data_type']] or [m for m in mappings if not m.get('data_type')])} for x in ledger_catalog()]
        return {'items':items,'note':'本平台按内部标准字段组装；省平台正式字段由“字段对应”按省级规范转换，不在此处臆造省级字段名。'}
    return read_operation(request,'sync.manage',load)


@router.get('/connections/{ident}/ledger-sync/preview')
def ledger_sync_preview(ident:str,request:Request):
    f,_,_=filters_from(request,{'data_type','start','end','period_id','org_id'})
    def load(db,a,s):
        a.require_admin();obj=_province(db,ident)
        from ..province_payload import build_ledger_records,chunks,CANONICAL_FIELDS
        if not f.get('data_type'):raise HTTPException(422,'请选择数据类型')
        records=build_ledger_records(db,a,f['data_type'],_ledger_filters(f))
        mappings=normalize_mappings(obj.mappings or [])
        mapped=any(not m.get('data_type') or m.get('data_type')==f['data_type'] for m in mappings)
        sample=records[:5]
        return {'data_type':f['data_type'],'count':len(records),'task_count':len(chunks(records)),'sample':sample,
            'mapped_sample':[apply_mappings(obj,x,f['data_type'])[0] for x in sample] if mapped else [],
            'fields':[{'key':k,'label':v} for k,v in CANONICAL_FIELDS[f['data_type']]],'mapping_ready':mapped,
            'connection_live':live_connection(db,obj),'external_called':False}
    return read_operation(request,'sync.manage',load)


@router.post('/connections/{ident}/ledger-sync')
def ledger_sync_enqueue(ident:str,data:LedgerSync,request:Request):
    def apply(db,a,s):
        a.require_admin();obj=_province(db,ident)
        from ..province_payload import build_ledger_records,chunks
        records=build_ledger_records(db,a,data.data_type,_ledger_filters(data.model_dump()))
        if not records:raise HTTPException(422,'所选范围没有可上报的台账数据')
        if data.expected_count is not None and data.expected_count!=len(records):raise HTTPException(409,'台账数据在预览后已变化，请重新预览核对数量')
        tasks=[]
        for part in chunks(records):
            task,created=enqueue_sync(db,a,obj,data.data_type,part,data.reason,return_created=True)
            if created and not live_connection(db,obj):
                task.state='BLOCKED';task.error='外部接口未真实连接';task.version+=1
                for item in db.scalars(select(SyncItem).where(SyncItem.task_id==task.id)):
                    item.state='BLOCKED';item.error='NOT_CONNECTED';item.version+=1
                task.attempts+=1
                db.add(TaskAttempt(task_id=task.id,attempt=task.attempts,result='BLOCKED',message='NOT_CONNECTED'))
            task.payload={**task.payload,'origin':'ledger','ledger_filters':_ledger_filters(data.model_dump())}
            tasks.append({'id':task.id,'state':task.state,'created':created,'rows':len(part),'reused':len(task.payload.get('reused_item_ids') or [])})
        audit(db,a,'sync',obj.id,'从台账生成湘培直通车同步任务',after={'data_type':data.data_type,'records':len(records),'tasks':[t['id'] for t in tasks],
            'filters':_ledger_filters(data.model_dump())},reason=data.reason)
        return {'data_type':data.data_type,'records':len(records),'tasks':tasks}
    return command(request,data.model_dump(),'sync.manage',apply)


@router.get('/sync-items')
def sync_items(request:Request):
    f,p,z=filters_from(request,{'task_id','state','data_type','connection_id'})
    def load(db,a,s):
        q=select(SyncItem)
        if f.get('task_id'):
            task=db.get(Task,f['task_id'])
            if not task or task.kind!='sync':raise HTTPException(404,'同步任务不存在')
            q=q.where(SyncItem.id.in_([x.id for x in task_sync_items(db,task)]))
        for k in ('state','data_type','connection_id'):
            if f.get(k):q=q.where(getattr(SyncItem,k)==f[k])
        return page_result(db,q.order_by(SyncItem.created_at.desc(),SyncItem.id),p,z)
    return read_operation(request,'sync.manage',load)


@router.get('/sync-items/{ident}')
def sync_item_detail(ident:str,request:Request):
    def load(db,a,s):
        item=db.get(SyncItem,ident)
        if not item:raise HTTPException(404,'同步记录不存在')
        return {'item':item,'calls':db.scalars(select(SyncCallLog).where(SyncCallLog.item_id==ident).order_by(SyncCallLog.attempt)).all()}
    return read_operation(request,'sync.manage',load)


def _retry_item(db,a,item,reason,expected_version):
    from ..sync_policy import retry_sync_items
    task=db.get(Task,item.task_id)
    if not task:raise HTTPException(409,'同步任务已失效')
    return retry_sync_items(db,a,task,reason,item_ids={item.id},expected_item_versions={item.id:expected_version})


@router.post('/sync-items/{ident}/retry')
def retry_sync_item(ident:str,data:VersionedReason,request:Request):
    def apply(db,a,s):
        item=db.get(SyncItem,ident)
        if not item:raise HTTPException(404,'同步记录不存在')
        check_version(item,data.expected_version)
        return _retry_item(db,a,item,data.reason,data.expected_version)
    return command(request,data.model_dump(),'sync.manage',apply)


@router.post('/sync-tasks/{ident}/retry-failed')
def retry_sync_failed(ident:str,data:TaskRetry,request:Request):
    def apply(db,a,s):
        task=db.get(Task,ident)
        if not task or task.kind!='sync':raise HTTPException(404,'同步任务不存在')
        check_version(task,data.expected_version)
        from ..sync_policy import retry_sync_items
        return retry_sync_items(db,a,task,data.reason,expected_task_version=data.expected_version)
    return command(request,data.model_dump(),'sync.manage',apply)


@router.post('/connections/{ident}/inbound/preview')
def inbound_preview(ident:str,data:InboundPreview,request:Request):
    def apply(db,a,s):
        a.require_admin();obj=_connection(db,ident)
        batch=preview_inbound(db,a,obj,data.data_type,data.records,data.source_label)
        return batch
    return command(request,data.model_dump(),'sync.manage',apply)

@router.get('/inbound-batches')
def inbound_batches(request:Request):
    """Paged metadata for the integration portal; raw rows remain behind detail access."""
    f,p,z=filters_from(request,{'connection_id','data_type','state'})
    def load(db,a,s):
        a.require_admin();q=select(InboundBatch)
        if f.get('connection_id'):
            _connection(db,f['connection_id']);q=q.where(InboundBatch.connection_id==f['connection_id'])
        if f.get('data_type'):
            from ..reference_data import SUPPORTED_INBOUND
            if f['data_type'] not in SUPPORTED_INBOUND:raise HTTPException(422,'当前入站数据类型不支持')
            q=q.where(InboundBatch.data_type==f['data_type'])
        if f.get('state'):
            if f['state'] not in {'PREVIEW','COMMITTED','FAILED','BLOCKED','VOID'}:raise HTTPException(422,'入站状态筛选无效')
            q=q.where(InboundBatch.state==f['state'])
        total=db.scalar(select(func.count()).select_from(q.subquery()))
        # Summary does not disclose mapped/raw HR, access hashes or internal receipt payloads.
        # 只取摘要列：receipt 平均约 200KB，整行读出会把大字段从盘上读一遍。
        fields=('id','connection_id','data_type','state','total','errors','created_at','version')
        cols=[getattr(InboundBatch,k) for k in fields]
        rows=db.execute(q.with_only_columns(*cols,maintain_column_froms=True).order_by(InboundBatch.created_at.desc(),InboundBatch.id).offset((p-1)*z).limit(z)).all()
        return {'items':[{k:serial(v) for k,v in zip(fields,r)} for r in rows],'total':total,'page':p,'size':z}
    return read_operation(request,'sync.manage',load)

@router.get('/inbound-batches/{ident}')
def inbound_detail(ident:str,request:Request):
    f,p,z=filters_from(request,set())
    def load(db,a,s):
        a.require_admin();batch=db.get(InboundBatch,ident)
        if not batch:raise HTTPException(404,'入站批次不存在')
        q=select(InboundRow).where(InboundRow.batch_id==ident).order_by(InboundRow.row_no)
        return {'batch':batch,'rows':page_result(db,q,p,z)}
    return read_operation(request,'sync.manage',load)

@router.post('/inbound-batches/{ident}/confirm')
def inbound_confirm(ident:str,data:VersionedReason,request:Request):
    def apply(db,a,s):
        batch=db.get(InboundBatch,ident)
        if not batch:raise HTTPException(404,'入站批次不存在')
        if not batch:raise HTTPException(404,'入站批次不存在')
        from ..paged_inbound import lock_pending_task,resume_confirmed_task
        task=lock_pending_task(db,batch)
        result=confirm_inbound(db,a,batch,data.expected_version,data.reason,data.basis)
        resume_confirmed_task(db,task,result)
        return result
    return command(request,data.model_dump(),'sync.manage',apply)

@router.post('/inbound-batches/{ident}/rollback')
def inbound_rollback(ident:str,data:VersionedReason,request:Request):
    """4.4 撤销本批入库: restore prior master values; refuse on later changes; audit is never deleted."""
    def apply(db,a,s):
        batch=db.get(InboundBatch,ident)
        if not batch:raise HTTPException(404,'入站批次不存在')
        return rollback_inbound(db,a,batch,data.expected_version,data.reason,data.basis)
    return command(request,data.model_dump(),'sync.manage',apply)

@router.post('/connections/{ident}/inbound/pull')
def inbound_pull(ident:str,data:InboundPullRequest,request:Request):
    def apply(db,a,s):
        a.require_admin();obj=_connection(db,ident)
        return create_pull_task(db,a,obj,data.data_type,data.mode,data.reason)
    return command(request,data.model_dump(),'sync.manage',apply)

@router.get('/integration-schedules')
def integration_schedules(request:Request):
    f,p,z=filters_from(request,{'connection_id','active','data_type'})
    def load(db,a,s):
        a.require_admin();q=select(IntegrationSchedule)
        if f.get('connection_id'):q=q.where(IntegrationSchedule.connection_id==f['connection_id'])
        if f.get('data_type'):q=q.where(IntegrationSchedule.data_type==f['data_type'])
        if f.get('active') in {'true','false'}:q=q.where(IntegrationSchedule.active.is_(f['active']=='true'))
        return page_result(db,q.order_by(IntegrationSchedule.created_at.desc(),IntegrationSchedule.id),p,z)
    return read_operation(request,'sync.manage',load)

@router.post('/integration-schedules')
def create_integration_schedule(data:IntegrationScheduleIn,request:Request):
    def apply(db,a,s):
        a.require_admin();connection=_connection(db,data.connection_id)
        if connection.code!='middle':raise HTTPException(422,'只有学校数据中台支持入站定时计划')
        if data.active and (not live_connection(db,connection) or not data.auto_commit):raise HTTPException(409,'启用定时计划必须先完成真实连接并明确批准自动确认入库')
        if data.active and (ADAPTERS.get(connection.code) is None or not callable(getattr(ADAPTERS.get(connection.code),'pull',None))):raise HTTPException(409,'启用定时计划前必须注册真实数据中台拉取适配器')
        if db.scalar(select(IntegrationSchedule.id).where(IntegrationSchedule.connection_id==connection.id,IntegrationSchedule.data_type==data.data_type)):raise HTTPException(409,'该数据类型已存在同步计划')
        obj=IntegrationSchedule(connection_id=connection.id,data_type=data.data_type,frequency_minutes=data.frequency_minutes,auto_commit=data.auto_commit,active=data.active,approved_by=a.id,next_at=utcnow())
        db.add(obj);db.flush();audit(db,a,'sync_schedule',obj.id,'创建数据中台定时同步计划',after=serial(obj),reason=data.reason);return obj
    return command(request,data.model_dump(),'sync.manage',apply)

@router.put('/integration-schedules/{ident}')
def update_integration_schedule(ident:str,data:IntegrationScheduleUpdate,request:Request):
    def apply(db,a,s):
        a.require_admin();obj=db.get(IntegrationSchedule,ident)
        if not obj:raise HTTPException(404,'同步计划不存在')
        check_version(obj,data.expected_version);connection=_connection(db,obj.connection_id);before=serial(obj)
        if data.active and (not live_connection(db,connection) or not data.auto_commit):raise HTTPException(409,'启用定时计划必须先完成真实连接并明确批准自动确认入库')
        if data.active and (ADAPTERS.get(connection.code) is None or not callable(getattr(ADAPTERS.get(connection.code),'pull',None))):raise HTTPException(409,'启用定时计划前必须注册真实数据中台拉取适配器')
        from ..sync_policy import invalidate_schedule_tasks
        invalidate_schedule_tasks(db,obj.id,'计划配置或自动入库批准已变更，原排队任务作废')
        obj.frequency_minutes=data.frequency_minutes;obj.auto_commit=data.auto_commit;obj.active=data.active;obj.approved_by=a.id;obj.next_at=utcnow();obj.last_error='';obj.version+=1
        audit(db,a,'sync_schedule',obj.id,'修改数据中台定时同步计划',before,serial(obj),data.reason);return obj
    return command(request,data.model_dump(),'sync.manage',apply)


@router.get('/connections/{ident}/checks')
def connection_checks(ident:str,request:Request):
    def load(db,a,s):
        a.require_admin();_connection(db,ident)
        return {'items':db.scalars(select(ConnectionCheck).where(ConnectionCheck.connection_id==ident)
            .order_by(ConnectionCheck.receipt['_connection_revision'].as_integer().desc(),ConnectionCheck.created_at.desc(),ConnectionCheck.id.desc()).limit(50)).all()}
    return read_operation(request,'sync.manage',load)

@router.post('/connections/{ident}/probe')
def connection_probe(ident:str,data:VersionedReason,request:Request):
    def apply(db,a,s):
        a.require_admin();obj=_connection(db,ident);check_version(obj,data.expected_version)
        check=probe_connection(db,a,obj,production=request.app.state.settings.env=='production')
        audit(db,a,'connections',obj.id,'连接协议与鉴权验证',after={'check_id':check.id,'mode':check.mode,
            'passed':check.passed,'reason_code':check.reason_code},reason=data.reason)
        return {'check':check,'connection':obj}
    return command(request,data.model_dump(),'sync.manage',apply)

@router.post('/connections/{ident}/activate/{check_id}')
def connection_activate(ident:str,check_id:str,data:VersionedReason,request:Request):
    def apply(db,a,s):
        a.require_admin();obj=_connection(db,ident);check_version(obj,data.expected_version);before=serial(obj)
        activate_connection(db,a,obj,check_id)
        audit(db,a,'connections',ident,'确认启用真实连接',before,serial(obj),data.reason)
        return obj
    return command(request,data.model_dump(),'sync.manage',apply)

@router.post('/connections/{ident}/disconnect')
def connection_disconnect(ident:str,data:VersionedReason,request:Request):
    def apply(db,a,s):
        a.require_admin();obj=_connection(db,ident);check_version(obj,data.expected_version);before=serial(obj)
        obj.state='NOT_CONNECTED';obj.version+=1;pause_schedules(db,obj,'学校管理员主动断开连接')
        # Explicit disconnect invalidates old checks, so activation needs a new handshake.
        for check in db.scalars(select(ConnectionCheck).where(ConnectionCheck.connection_id==ident)):
            check.expires_at=utcnow()
        audit(db,a,'connections',ident,'断开连接并停用同步计划',before,serial(obj),data.reason)
        return obj
    return command(request,data.model_dump(),'sync.manage',apply)

@router.get('/sync-tasks/{ident}/evidence')
def sync_evidence(ident:str,request:Request):
    def load(db,a,s):
        a.require_admin();task=db.get(Task,ident)
        if not task or task.kind not in {'sync','inbound_pull'}:raise HTTPException(404,'同步任务不存在')
        rows=task_sync_items(db,task) if task.kind=='sync' else []
        logs=db.scalars(select(SyncCallLog).where(SyncCallLog.item_id.in_([x.id for x in rows]))
            .order_by(SyncCallLog.created_at,SyncCallLog.id)).all() if rows else []
        items=[{'id':x.id,'data_type':x.data_type,'state':x.state,'attempts':x.attempts,
                'payload_hash':x.payload_hash,'idempotency_key':x.idempotency_key,'receipt':x.result,
                'reused':x.task_id!=task.id} for x in rows]
        proof={'task_id':task.id,'kind':task.kind,'state':task.state,'created_at':task.created_at,
            'connection_id':task.payload.get('connection_id'),'configuration_hash':task.payload.get('configuration_hash'),
            'summary':task.result,'items':items,'calls':serial(logs),
            'external_acceptance':False,'note':'本地调用与回执证据，不替代学校外部接口验收签认'}
        proof=serial(proof);return {'evidence':proof,'sha256':digest(proof)}
    return read_operation(request,'sync.manage',load)
