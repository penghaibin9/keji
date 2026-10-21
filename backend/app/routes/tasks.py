"""Excel import/export, task views and runtime operations."""
from __future__ import annotations
import shutil,uuid
from hashlib import sha256
from pathlib import Path
from urllib.parse import quote
from fastapi import APIRouter,Request,HTTPException,UploadFile,File
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool
from sqlalchemy import select
from ..core import *
from ..schemas import VersionedReason,ExportRequest,TaskRetry
from ..excel_io import inspect_xlsx,template_bytes,validate_rows,commit_import,error_xlsx,read_export_file,import_preview_digest,import_error_text,TEMPLATE_NAMES,EXPORT_FORMAT_VERSION
from ..settings_catalog import import_row_limit
from ..import_access import require_import_permission, make_import_proof, require_import_access, public_import, import_summary
from ..read_queries import RECORD_FILTERS,ASSESSMENT_FILTERS,AUDIT_FILTERS
router=APIRouter(prefix='/api',tags=['Excel、任务与运行状态'])


def _public_task(obj):
    data=serial(obj);payload=dict(data.get('payload') or {});payload.pop('authorization',None);data['payload']=payload
    result=dict(data.get('result') or {});result.pop('storage_name',None);data['result']=result
    if obj.kind=='export':data['historical_report']=obj.state=='DONE' and result.get('report_version')!=EXPORT_FORMAT_VERSION
    return data


def _owned_import(db,a,ident):
    obj=db.get(ImportJob,ident)
    if not obj or obj.owner_id!=a.id:raise HTTPException(404,'导入任务不存在')
    require_import_access(db,a,obj)
    return obj

@router.get('/connections')
def connections(request:Request):
    return read_operation(request,'sync.manage',lambda db,a,s:{'items':db.scalars(select(Connection).order_by(Connection.code)).all()})

@router.get('/imports/templates/{kind}')
def import_template(kind:str,request:Request):
    with request.app.state.sessions.begin() as db:
        a,s=current_actor(db,request);require_import_permission(a,kind)
        data=template_bytes(kind);audit(db,a,'imports',kind,'下载Excel导入模板',after={'kind':kind},reason='下载标准空模板')
    return Response(data,media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(TEMPLATE_NAMES[kind]+'模板.xlsx'),'X-Content-Type-Options':'nosniff'})

@router.post('/imports/{kind}/preview')
async def import_preview(kind:str,request:Request,file:UploadFile=File(...)):
    if kind not in {'records','participations','qualifications','teachers'}:raise HTTPException(422,'导入类型无效')
    def authorize():
        with request.app.state.sessions.begin() as db:
            a,s=current_actor(db,request,write=True);require_import_permission(a,kind)
            return import_row_limit(db)
    max_rows=await run_in_threadpool(authorize)
    limit=min(request.app.state.settings.upload_limit_mb*1024*1024,10*1024*1024)
    data=await file.read(limit+1);await file.close()
    if len(data)>limit:raise HTTPException(413,'Excel文件超过大小限制')
    filename=file.filename or '';parsed=await run_in_threadpool(lambda:inspect_xlsx(data,filename,kind,max_rows=max_rows));file_sha=sha256(data).hexdigest()
    payload={'kind':kind,'filename':filename,'sha256':file_sha,'rows':len(parsed)}
    def execute():
        def apply(db,a,s):
            require_import_permission(a,kind)
            checked=validate_rows(db,a,kind,parsed)
            errors=sum(bool(x['errors']) for x in checked)
            job=ImportJob(kind=kind,owner_id=a.id,filename=filename,sha256=file_sha,state='INVALID' if errors else 'PREVIEW',total=len(checked),errors=errors,receipt={'preview_rows_sha256':import_preview_digest(checked),'access_proof':make_import_proof(a,kind,checked)})
            db.add(job);db.flush()
            for x in checked:db.add(ImportRow(job_id=job.id,row_no=x['row_no'],payload={'raw':x['raw'],'normalized':x['normalized']},errors=x['errors']))
            audit(db,a,'imports',job.id,'生成Excel导入预览',after={'kind':kind,'rows':job.total,'errors':job.errors,'sha256':file_sha},reason='上传标准Excel，仅预览未入库')
            return public_import(job)
        return command(request,payload,'import',apply)
    return await run_in_threadpool(execute)

@router.get('/imports')
def imports(request:Request):
    f,p,z=filters_from(request,{'kind'})
    def load(db,a,s):
        q=select(ImportJob).where(ImportJob.owner_id==a.id)
        if f.get('kind'):q=q.where(ImportJob.kind==f['kind'])
        total=db.scalar(select(func.count()).select_from(q.subquery()))
        jobs=db.scalars(q.order_by(ImportJob.created_at.desc(),ImportJob.id).offset((p-1)*z).limit(z)).all()
        return {'items':[import_summary(db,a,x) for x in jobs],'total':total,'page':p,'size':z}
    return read_operation(request,'import',load)

@router.get('/imports/{ident}')
def import_detail(ident:str,request:Request):
    f,p,z=filters_from(request,set())
    def load(db,a,s):
        job=_owned_import(db,a,ident);q=select(ImportRow).where(ImportRow.job_id==ident).order_by(ImportRow.row_no)
        rows=page_result(db,q,p,z)
        rows['items']=[{**row,'errors':[import_error_text(value) for value in row['errors']]} for row in rows['items']]
        return {'job':public_import(job),'rows':rows}
    return read_operation(request,'import',load)

@router.get('/imports/{ident}/errors')
def import_errors(ident:str,request:Request):
    with request.app.state.sessions.begin() as db:
        a,s=current_actor(db,request);a.require('import');job=_owned_import(db,a,ident)
        rows=db.scalars(select(ImportRow).where(ImportRow.job_id==ident).order_by(ImportRow.row_no)).all()
        if not job.errors:raise HTTPException(409,'当前导入没有错误行')
        data=error_xlsx(rows);audit(db,a,'imports',job.id,'下载Excel错误行',after={'errors':job.errors},reason='修正后重新上传原Excel')
    return Response(data,media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':"attachment; filename*=UTF-8''%E5%AF%BC%E5%85%A5%E9%94%99%E8%AF%AF%E8%A1%8C.xlsx",'X-Content-Type-Options':'nosniff'})

@router.post('/imports/{ident}/confirm')
def import_confirm(ident:str,data:VersionedReason,request:Request):
    def apply(db,a,s):
        job=_owned_import(db,a,ident);check_version(job,data.expected_version)
        if job.state=='INVALID' or (job.state=='PREVIEW' and job.errors):raise HTTPException(409,'批次有错误，请下载错误明细并放弃本批，修正后重新上传')
        if job.state!='PREVIEW':raise HTTPException(409,'该导入批次已处理')
        stored=db.scalars(select(ImportRow).where(ImportRow.job_id==ident).order_by(ImportRow.row_no)).all()
        rows=[{'row_no':x.row_no,'raw':(x.payload or {}).get('raw',{}),'normalized':(x.payload or {}).get('normalized',{}),'errors':list(x.errors or [])} for x in stored]
        return public_import(commit_import(db,a,job,rows,data.reason,data.basis))
    return command(request,data.model_dump(),'import',apply)

@router.post('/imports/{ident}/discard')
def import_discard(ident:str,data:VersionedReason,request:Request):
    def apply(db,a,s):
        job=_owned_import(db,a,ident);check_version(job,data.expected_version)
        if job.state not in {'PREVIEW','INVALID'} or not job.errors:raise HTTPException(409,'仅有错误且未入库的批次可以放弃')
        before={'state':job.state,'errors':job.errors,'version':job.version}
        job.state='VOID';job.version+=1
        job.receipt={**(job.receipt or {}),'written':0,'discarded_at':utcnow().isoformat(),'discarded_by':a.id,'discard_reason':data.reason,'discard_basis':data.basis}
        audit(db,a,'imports',job.id,'放弃Excel导入批次',before=before,after={'state':job.state,'errors':job.errors,'version':job.version,'written':0},reason=data.reason)
        return public_import(job)
    return command(request,data.model_dump(),'import',apply)

EXPORT_FILTERS={
 'records':set(RECORD_FILTERS),'participations':{'q','teacher_id','org_id','start','end','project_code','course_code'},'qualifications':{'q','state','teacher_id','org_id'},'points':{'teacher_id','period_id','org_id'},
 'assessments':set(ASSESSMENT_FILTERS),'organization_assessments':{'period_id','target_kind','target_id','state','progress'},'audit':set(AUDIT_FILTERS),'handover':set(),
}

@router.post('/exports')
def create_export(data:ExportRequest,request:Request):
    if set(data.filters)-EXPORT_FILTERS[data.kind]:raise HTTPException(422,'导出筛选字段无效')
    if data.kind=='handover' and (data.filters or not data.confirmed):raise HTTPException(422,'业务移交必须明确确认且不接收局部筛选')
    permission='data.export' if data.kind=='handover' else 'export'
    def apply(db,a,s):
        from ..excel_io import require_export_scope
        require_export_scope(a,data.kind)
        if data.kind=='audit':
            from ..read_queries import audit_query
            audit_query(db,a,data.filters)
        task=Task(kind='export',owner_id=a.id,key='export-'+uuid.uuid4().hex,payload={'kind':data.kind,'filters':data.filters,'authorization':a.fingerprint()},state='PENDING')
        db.add(task);db.flush();audit(db,a,'exports',task.id,'创建后台导出任务',after={'kind':data.kind,'filters':data.filters},reason='按当前授权范围后台生成')
        return _public_task(task)
    return command(request,data.model_dump(),permission,apply)

@router.get('/tasks')
def tasks(request:Request):
    f,p,z=filters_from(request,{'kind','connection_id','data_type','state'})
    def load(db,a,s):
        kind=f.get('kind','export')
        if kind not in {'export','sync','integration'}:raise HTTPException(422,'任务类型无效')
        integration_kinds={'sync','inbound_pull'}
        a.require('sync.manage' if kind in {'sync','integration'} else 'export')
        q=select(Task).where(Task.kind.in_(integration_kinds) if kind=='integration' else Task.kind==kind)
        if kind=='export':
            q=q.where(Task.owner_id==a.id)
            if f.get('connection_id') or f.get('data_type'):
                raise HTTPException(422,'导出任务不接受外部连接筛选')
        if f.get('state'):
            if f['state'] not in {'PENDING','RUNNING','RETRY','FAILED','BLOCKED','DONE','WAITING_CONFIRMATION'}:
                raise HTTPException(422,'任务状态筛选无效')
            q=q.where(Task.state==f['state'])
        if f.get('connection_id'):
            if not db.get(Connection,f['connection_id']):raise HTTPException(404,'接口配置不存在')
            q=q.where(Task.payload['connection_id'].as_string()==f['connection_id'])
        if f.get('data_type'):
            from ..integrations import DATA_CATALOG
            if f['data_type'] not in {row[0] for rows in DATA_CATALOG.values() for row in rows}:
                raise HTTPException(422,'数据类型不在接口目录')
            q=q.where(Task.payload['data_type'].as_string()==f['data_type'])
        total=db.scalar(select(func.count()).select_from(q.order_by(None).subquery()))
        items=db.scalars(q.order_by(Task.created_at.desc(),Task.id).offset((p-1)*z).limit(z)).all()
        return {'items':[_public_task(x) for x in items],'total':total,'page':p,'size':z}
    return read_operation(request,None,load)

@router.get('/tasks/{ident}')
def task_detail(ident:str,request:Request):
    def load(db,a,s):
        obj=db.get(Task,ident)
        if not obj:raise HTTPException(404,'任务不存在')
        integration_kinds={'sync','inbound_pull'}
        a.require('sync.manage' if obj.kind in integration_kinds else 'export')
        if obj.kind=='export' and obj.owner_id!=a.id:raise HTTPException(403,'只能访问本人导出任务')
        return {'task':_public_task(obj),'attempts':db.scalars(select(TaskAttempt).where(TaskAttempt.task_id==ident).order_by(TaskAttempt.attempt)).all()}
    return read_operation(request,None,load)

@router.post('/tasks/{ident}/retry')
def task_retry(ident:str,data:TaskRetry,request:Request):
    def apply(db,a,s):
        obj=db.scalar(select(Task).where(Task.id==ident).with_for_update())
        if not obj:raise HTTPException(404,'任务不存在')
        check_version(obj,data.expected_version)
        integration_kinds={'sync','inbound_pull'}
        a.require('sync.manage' if obj.kind in integration_kinds else 'export')
        if obj.kind=='export':
            if obj.owner_id!=a.id:raise HTTPException(403,'只能重试本人导出任务')
            if obj.payload.get('authorization')!=a.fingerprint():raise HTTPException(409,'权限范围已变化，请重新创建导出')
        if obj.state not in {'FAILED','BLOCKED'}:raise HTTPException(409,'当前任务无需重试')
        if obj.kind=='sync':
            from ..sync_policy import retry_sync_items
            return _public_task(retry_sync_items(db,a,obj,data.reason))
        if obj.kind=='inbound_pull':
            from ..sync_policy import retry_pull_task
            return _public_task(retry_pull_task(db,a,obj,data.reason))
        before=serial(obj);obj.state='PENDING';obj.error='';obj.next_at=utcnow();obj.lease_token=None;obj.lease_until=None;obj.version+=1
        audit(db,a,'tasks',obj.id,'重试后台任务',before,_public_task(obj),data.reason);return _public_task(obj)
    return command(request,data.model_dump(),None,apply)

@router.get('/tasks/{ident}/download')
def task_download(ident:str,request:Request):
    with request.app.state.sessions.begin() as db:
        a,s=current_actor(db,request);obj=db.get(Task,ident)
        if not obj or obj.kind!='export' or obj.owner_id!=a.id:raise HTTPException(404,'导出任务不存在')
        a.require('data.export' if obj.payload.get('kind')=='handover' else 'export')
        if obj.payload.get('kind')=='handover':a.require_admin()
        if obj.payload.get('authorization')!=a.fingerprint():raise HTTPException(409,'权限范围已变化，请重新导出')
        if obj.state!='DONE':raise HTTPException(409,'导出文件尚未生成完成')
        data=read_export_file(request.app.state.settings.storage_dir,obj);result=dict(obj.result);audit(db,a,'exports',obj.id,'下载后台导出',after={'kind':obj.payload.get('kind'),'sha256':result.get('sha256'),'size':result.get('size')},reason='下载时重新校验权限与文件SHA256')
    return Response(data,media_type=result['mime'],headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(result['filename']),'X-Content-Type-Options':'nosniff'})

@router.get('/operations')
def operations(request:Request):
    def load(db,a,s):
        a.require_admin();heartbeat=db.get(RuntimeState,'worker');backup=db.get(RuntimeState,'backup')
        healthy=bool(heartbeat and (utcnow()-heartbeat.updated_at).total_seconds()<90 and heartbeat.value.get('healthy') is True)
        return {'environment':request.app.state.settings.env,'database_engine':db.bind.dialect.name,'database_reachable':True,
          'worker':{'healthy':healthy,'last_heartbeat':heartbeat.updated_at.isoformat() if heartbeat else None},
          'free_gib':round(shutil.disk_usage(request.app.state.settings.storage_dir).free/1024**3,2),
          'backup':backup.value if backup else {},'notes':'内部Excel与同步任务底座已接回；真实学校接口、历史迁移基线、MySQL和机房验收未完成时不会显示为通过。'}
    return read_operation(request,'operations.read',load)
