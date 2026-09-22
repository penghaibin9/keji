"""R2 stored-byte attachment processing; permission checked on every download."""
from __future__ import annotations
from fastapi import APIRouter,Request,UploadFile,File,Form,HTTPException
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool
from urllib.parse import quote
from pathlib import Path
from hashlib import sha256
import os,io,re,stat,secrets,warnings
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
    raise HTTPException(422,'只接收PDF、PNG、JPG附件')

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
    if kind not in {'qualification','dispute'}:raise HTTPException(422,'该附件业务类型尚不支持')
    if len(reason.strip())<2 or len(reason)>2000:raise HTTPException(422,'请填写有效上传依据')
    def authorize_before_parse():
        with request.app.state.sessions.begin() as db:
            a,s=current_actor(db,request,write=True);a.require('file.write')
            model,perm=(Qualification,'qualification.write') if kind=='qualification' else (Dispute,'dispute.write')
            owned_object(db,a,model,ident,perm,own=True)
    await run_in_threadpool(authorize_before_parse)
    data=await file.read(request.app.state.settings.upload_limit_mb*1024*1024+1)
    await file.close()
    if len(data)>request.app.state.settings.upload_limit_mb*1024*1024:raise HTTPException(413,'附件超过大小限制')
    name=file.filename or '';mime=await run_in_threadpool(inspect_upload,name,data)
    payload={'kind':kind,'id':ident,'name':name,'sha256':sha256(data).hexdigest(),'expected_version':expected_version,'reason':reason}
    written=[]
    def execute():
        def apply(db,a,s):
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
