"""R2 stored-byte attachment processing; permission checked on every download."""
from __future__ import annotations
from fastapi import APIRouter,Request,UploadFile,File,Form,HTTPException
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool
from urllib.parse import quote
from pathlib import Path
from hashlib import sha256
import os,io,re,stat,secrets,warnings,zipfile
from PIL import Image
from ..core import *
from ..schemas import VersionedReason
from ..services import qualification_revision
from ..safe_files import open_nofollow
from .business import owned_object
router=APIRouter(prefix='/api',tags=['业务附件'])

def inspect_upload(name,data):
    if not name or len(name)>200 or '/' in name or '\\' in name or any(ord(c)<32 for c in name):raise HTTPException(422,'附件文件名无效')
    ext=Path(name).suffix.lower()
    if ext in {'.png','.jpg','.jpeg'}:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error',Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(data)) as image:
                    if image.width*image.height>20000000:raise ValueError('image too large')
                    fmt=image.format;image.verify()
            if (fmt=='PNG' and ext!='.png') or (fmt=='JPEG' and ext not in {'.jpg','.jpeg'}) or fmt not in {'PNG','JPEG'}:raise ValueError('mismatch')
        except Exception:raise HTTPException(422,'图片格式损坏、过大或与扩展名不符') from None
        return 'image/png' if fmt=='PNG' else 'image/jpeg'
    if ext=='.pdf':
        try:
            from pypdf import PdfReader
            if not data.startswith(b'%PDF-'):raise ValueError('pdf signature')
            # Inspect structure only; never execute actions or extract embedded bytes.
            with PdfReader(io.BytesIO(data),strict=True) as doc:
                if doc.is_encrypted or not 1<=len(doc.pages)<=2000:raise ValueError('pdf structure')
        except Exception:raise HTTPException(422,'PDF损坏、加密或超过页数上限') from None
        return 'application/pdf'
    if ext in {'.docx','.xlsx'}:
        part,mime=('word/document.xml','application/vnd.openxmlformats-officedocument.wordprocessingml.document') if ext=='.docx' else ('xl/workbook.xml','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                infos=archive.infolist();names={x.filename for x in infos}
                if len(infos)>2000 or sum(x.file_size for x in infos)>200*1024*1024:raise ValueError('zip bomb')
                if not {'[Content_Types].xml',part}<=names:raise ValueError('office structure')
                if any(x.flag_bits&1 or x.filename.replace('\\','/').rsplit('/',1)[-1].lower()=='vbaproject.bin' for x in infos):raise ValueError('encrypted or macro')
                if archive.testzip() is not None:raise ValueError('zip checksum')
        except Exception:raise HTTPException(422,'文档或表格损坏、加密、包含宏或超过解压限制') from None
        return mime
    raise HTTPException(422,'只接收 .pdf、.png、.jpg、.jpeg、.docx、.xlsx 附件；iPhone（苹果手机）照片请在相机设置里选“兼容性最佳”或截图后上传')

def verify_file(root,item):
    root=Path(root)
    if root.is_symlink() or not root.is_dir() or not re.fullmatch(r'[a-f0-9]{64}',item.storage_key):raise HTTPException(503,'附件存储配置异常')
    path=root/item.storage_key
    try:
        fd=open_nofollow(path,os.O_RDONLY)
        with os.fdopen(fd,'rb') as f:
            meta=os.fstat(f.fileno())
            if not stat.S_ISREG(meta.st_mode) or meta.st_size!=item.size or meta.st_size>100*1024*1024:raise ValueError('size')
            data=f.read(item.size+1)
        if len(data)!=item.size or sha256(data).hexdigest()!=item.sha256:raise ValueError('hash')
    except (OSError,ValueError):raise HTTPException(503,'附件字节校验未通过，请联系管理员') from None
    return data

# 12.5: evidence bound to teacher assessments, organisation assessments and sync tasks.
BOUND_KINDS={'assessment','org_assessment','sync_task','social_project','social_claim','social_policy','social_annual','social_resource'}

def bound_object(db,a,kind,ident,*,write=False):
    """Same layered checks as qualification files: permission, live scope, then object state."""
    from ..org_assessment import OrganizationAssessment
    if kind.startswith('social_'):
        from ..social_training import scoped
        a.require('records.read')
        obj=scoped(db,a,kind,ident,write=write)
        if kind=='social_annual' and a.role.kind=='teacher':raise HTTPException(403,'年度公示仅开放评分摘要，原始材料由授权核验人员查看')
        if write and kind=='social_claim' and (obj.teacher_id!=a.id or obj.state not in {'DRAFT','RETURNED'}):raise HTTPException(403,'仅本人可为待补正积分上传材料')
        if write and kind=='social_resource' and obj.kind=='correction' and (obj.data['created_by']!=a.id or obj.state not in {'DRAFT','RETURNED'}):raise HTTPException(403,'仅更正申请人可在草稿或退回时补充依据')
        if write and kind=='social_resource' and obj.kind=='point_review' and not ((obj.data['created_by']==a.id and obj.state=='DRAFT') or (obj.data['teacher_id']==a.id and obj.state=='TEACHER')):raise HTTPException(403,'核对材料由发起人在发送前、或被核对教师在回应时上传')
        return obj,getattr(obj,'teacher_id',None)
    if kind=='assessment':
        obj=owned_object(db,a,Assessment,ident,'assessment.read')
        if write:
            if obj.state=='ARCHIVED':raise HTTPException(409,'已归档考核不能追加材料')
            if obj.teacher_id==a.id:a.require('assessment.confirm')
            elif a.role.kind=='teacher':raise HTTPException(403,'只能为本人考核上传材料')
            else:a.require('assessment.review')
        return obj,obj.teacher_id
    if kind=='org_assessment':
        a.require('assessment.read')
        if a.role.kind=='teacher':raise HTTPException(403,'普通教师不访问组织考核')
        obj=db.get(OrganizationAssessment,ident)
        if not obj:raise HTTPException(404,'组织考核不存在')
        if a.role.kind!='school' and (obj.target_id!=a.org.id or obj.target_kind!=a.role.kind):raise HTTPException(403,'组织考核超出授权范围')
        if obj.target_id not in a.org_ids:raise HTTPException(403,'组织考核超出授权范围')
        if write:
            if obj.state=='ARCHIVED':raise HTTPException(409,'已归档组织考核不能追加材料')
            if not ({'assessment.review','assessment.calculate'}&a.permissions):raise HTTPException(403,'无权上传组织考核材料')
        return obj,None
    if kind=='sync_task':
        a.require_admin();a.require('sync.manage');obj=db.get(Task,ident)
        if not obj or obj.kind not in {'sync','inbound_pull'}:raise HTTPException(404,'同步任务不存在')
        return obj,None
    raise HTTPException(422,'该附件业务类型尚不支持')

def public_attachment(item):
    return {k:v for k,v in serial(item).items() if k!='storage_key'}

@router.get('/attachments')
def attachment_list(request:Request):
    f,_,_=filters_from(request,{'object_type','object_id'})
    if f.get('object_type') not in BOUND_KINDS or not f.get('object_id'):raise HTTPException(422,'请指定考核、组织考核或同步任务')
    def load(db,a,s):
        a.require('file.read');obj,teacher=bound_object(db,a,f['object_type'],f['object_id'])
        q=select(Attachment).where(Attachment.object_type==f['object_type'],Attachment.object_id==obj.id)
        if teacher:q=q.where(Attachment.teacher_id==teacher)
        return {'items':[public_attachment(x) for x in db.scalars(q.order_by(Attachment.created_at,Attachment.id))]}
    return read_operation(request,'file.read',load)

@router.post('/attachments/{ident}/detach')
def detach(ident:str,data:VersionedReason,request:Request):
    def apply(db,a,s):
        item=db.get(Attachment,ident)
        if not item or item.object_type!='qualification':raise HTTPException(404,'资质附件不存在')
        obj=owned_object(db,a,Qualification,item.object_id,'qualification.write',own=True);check_version(obj,data.expected_version)
        if obj.state not in {'DRAFT','RETURNED'} or ident not in obj.attachment_ids:raise HTTPException(409,'不能修改当前材料关联')
        before=serial(obj);obj.attachment_ids=[x for x in obj.attachment_ids if x!=ident];obj.version+=1
        qualification_revision(db,a,obj,data.reason)
        workflow(db,a,'qualification',obj.id,'移除当前附件关联',before,serial(obj),data.reason,data.basis)
        return obj
    return command(request,data.model_dump(),'file.write',apply)


@router.post('/attachments/{kind}/{ident}')
async def upload(kind:str,ident:str,request:Request,file:UploadFile=File(...),expected_version:int=Form(...),reason:str=Form(...)):
    if kind not in {'qualification','dispute'}|BOUND_KINDS:raise HTTPException(422,'该附件业务类型尚不支持')
    if len(reason.strip())<2 or len(reason)>2000:raise HTTPException(422,'请填写有效上传依据')
    def authorize_before_parse():
        with request.app.state.sessions.begin() as db:
            a,s=current_actor(db,request,write=True);a.require('file.write')
            if kind in BOUND_KINDS:bound_object(db,a,kind,ident,write=True);return
            model,perm=(Qualification,'qualification.write') if kind=='qualification' else (Dispute,'dispute.write')
            owned_object(db,a,model,ident,perm,own=True)
    await run_in_threadpool(authorize_before_parse)
    data=await file.read(request.app.state.settings.upload_limit_mb*1024*1024+1)
    await file.close()
    if len(data)>request.app.state.settings.upload_limit_mb*1024*1024:raise HTTPException(413,'附件超过大小限制')
    name=file.filename or '';mime=await run_in_threadpool(inspect_upload,name,data)
    payload={'kind':kind,'id':ident,'name':name,'sha256':sha256(data).hexdigest(),'expected_version':expected_version,'reason':reason}
    written=[]
    def store():
        root=request.app.state.settings.storage_dir
        if root.is_symlink() or not root.is_dir():raise HTTPException(503,'附件目录未就绪')
        key=secrets.token_hex(32);path=root/key
        fd=open_nofollow(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);written.append(path)
        with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
        return key
    def bound_upload(db,a):
        obj,teacher=bound_object(db,a,kind,ident,write=True);check_version(obj,expected_version)
        count=db.scalar(select(func.count()).select_from(Attachment).where(Attachment.object_type==kind,Attachment.object_id==ident))
        if count>=50:raise HTTPException(422,'单个业务对象最多50个附件')
        # teacher_id is the owning teacher for a teacher assessment; organisation/sync evidence
        # has no teacher owner, so the (non-null) column records the uploading account.
        item=Attachment(object_type=kind,object_id=ident,teacher_id=teacher or a.id,uploaded_by=a.id,name=name,storage_key=store(),
              sha256=payload['sha256'],size=len(data),mime=mime)
        db.add(item);db.flush()
        label={'assessment':'考核','org_assessment':'组织考核','sync_task':'同步任务'}.get(kind,'社会培训')
        after={'attachment_id':item.id,'name':name,'sha256':item.sha256,'size':item.size}
        if kind.startswith('social_'):
            obj.version+=1
            workflow(db,a,kind,ident,'上传社会培训佐证材料',{},after,reason,'附件校验值:'+item.sha256)
        elif kind=='sync_task':audit(db,a,'sync',ident,'上传同步佐证材料',after=after,reason=reason)
        else:workflow(db,a,'assessment' if kind=='assessment' else 'organization_assessment',ident,'上传'+label+'佐证材料',{},after,reason,'附件SHA256:'+item.sha256)
        return public_attachment(item)
    def execute():
        def apply(db,a,s):
            if kind in BOUND_KINDS:return bound_upload(db,a)
            model,perm=(Qualification,'qualification.write') if kind=='qualification' else (Dispute,'dispute.write')
            obj=owned_object(db,a,model,ident,perm,own=True);check_version(obj,expected_version)
            if (kind=='qualification' and obj.state not in {'DRAFT','RETURNED'}) or (kind=='dispute' and obj.state!='OPEN'):
                raise HTTPException(409,'当前业务状态不允许上传附件')
            root=request.app.state.settings.storage_dir
            if root.is_symlink() or not root.is_dir():raise HTTPException(503,'附件目录未就绪')
            if kind=='qualification' and len(obj.attachment_ids or [])>=20:raise HTTPException(422,'单份资质最多20个附件')
            key=secrets.token_hex(32);path=root/key
            fd=open_nofollow(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);written.append(path)
            with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
            item=Attachment(object_type=kind,object_id=ident,teacher_id=obj.teacher_id,uploaded_by=a.id,name=name,storage_key=key,
                  sha256=payload['sha256'],size=len(data),mime=mime)
            db.add(item);db.flush();before=serial(obj);obj.version+=1
            if kind=='qualification':
                obj.attachment_ids=[*(obj.attachment_ids or []),item.id];qualification_revision(db,a,obj,reason)
            workflow(db,a,kind,ident,'上传业务佐证',before,serial(obj),reason,'附件SHA256:'+item.sha256)
            return {k:v for k,v in serial(item).items() if k!='storage_key'}
        try:return command(request,payload,'file.write',apply)
        except Exception:
            for path in written:
                try:path.unlink()
                except OSError:pass # Metadata rolled back; orphan is not publicly served.
            raise
    return await run_in_threadpool(execute)

@router.get('/attachments/{ident}/download')
def download(ident:str,request:Request):
    with request.app.state.sessions.begin() as db:
        a,s=current_actor(db,request);a.require('file.read');item=db.get(Attachment,ident)
        if not item:raise HTTPException(404,'附件不存在')
        if item.object_type in BOUND_KINDS:
            obj,teacher=bound_object(db,a,item.object_type,item.object_id)
            if teacher and teacher!=item.teacher_id:raise HTTPException(403,'附件归属不一致')
            data=verify_file(request.app.state.settings.storage_dir,item)
            audit(db,a,'attachments',item.id,'下载业务附件',after={'sha256':item.sha256,'size':item.size,'object_type':item.object_type,'object_id':item.object_id},reason='授权访问业务佐证')
            filename=item.name;mime=item.mime
            return Response(data,media_type=mime,headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(filename),'X-Content-Type-Options':'nosniff'})
        a.check_teacher(db,item.teacher_id)
        model,perm={ 'qualification':(Qualification,'qualification.read'),'dispute':(Dispute,'dispute.write') }.get(item.object_type,(None,None))
        if not model:raise HTTPException(403,'附件业务归属无法确认')
        obj=owned_object(db,a,model,item.object_id,perm)
        if obj.teacher_id!=item.teacher_id:raise HTTPException(403,'附件归属不一致')
        data=verify_file(request.app.state.settings.storage_dir,item)
        audit(db,a,'attachments',item.id,'下载业务附件',after={'sha256':item.sha256,'size':item.size},reason='授权访问业务佐证')
        filename=item.name;mime=item.mime
    # Bytes have already passed permission/hash check. No public URL / reopen.
    return Response(data,media_type=mime,headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(filename),'X-Content-Type-Options':'nosniff'})
