"""培训业务展示图片：项目、课程、基地、成果封面，培训师头像，基地场地照片。

图片与证明材料分开存放（附件 object_type 为 display_*），不计入“须上传佐证”的检查；
更换或移除只改当前展示引用并留痕，原图保留，不改变审批状态。
"""
from __future__ import annotations
import os,secrets
from hashlib import sha256
from fastapi import APIRouter,Request,UploadFile,File,Form,HTTPException
from fastapi.responses import Response
from pydantic import Field
from typing import Literal
from sqlalchemy import select,func
from starlette.concurrency import run_in_threadpool
from ..core import command,current_actor,serial,workflow,check_version
from ..models import Attachment
from ..schemas import Input
from ..safe_files import open_nofollow
from ..social_models import SocialProject,SocialResource
from .. import social_training as st
from .files import inspect_upload,verify_file

router=APIRouter(prefix='/api/social/images',tags=['培训业务展示图片'])

TARGETS={'project':(SocialProject,'social_project','display_project'),'resource':(SocialResource,'social_resource','display_resource')}
OBJECT_TYPES={v[2]:k for k,v in TARGETS.items()}
# 可维护展示图片的资源类型；course_apply 是课程资料记录，封面即课程封面，trainer 的封面即培训师头像。
RESOURCE_KINDS={'base','achievement','trainer','course_apply'}
MAX_PHOTOS=6
MAX_IMAGE_MB=5
LABELS={'project':'培训项目','base':'培训基地','achievement':'培训成果','trainer':'培训师','course_apply':'培训课程'}


def _target(db,target,ident,*,lock=False):
    if target not in TARGETS:raise HTTPException(422,'图片所属业务类型无效')
    model=TARGETS[target][0]
    obj=db.get(model,ident,with_for_update=lock)
    if not obj:raise HTTPException(404,'业务记录不存在')
    if target=='resource' and obj.kind not in RESOURCE_KINDS:raise HTTPException(422,'该类资料不维护展示图片')
    return obj


def can_view(db,a,target,obj):
    """能在列表里看到这条记录的人可以看展示图片；证明材料仍按原附件权限下载。"""
    if a.role.kind=='school':return True
    if target=='project':
        try:st.scoped(db,a,'social_project',obj.id,allow_participant=True);return True
        except HTTPException as error:
            if error.status_code not in (403,404):raise
            return False
    data=obj.data or {}
    if a.id in {data.get('teacher_id'),data.get('created_by')}:return True
    if obj.kind=='trainer':
        # 与师资库同口径：学院看本院，教研室看所属学院；教师只看本人。
        scope={a.org.parent_id} if a.role.kind=='dept' else set(a.org_ids) if a.role.kind=='college' else set()
        return obj.org_id in scope
    college=a.org.parent_id if a.role.kind in ('teacher','dept') else None
    return obj.org_id in a.org_ids or (college is not None and obj.org_id==college)


def can_maintain(db,a,target,obj):
    data=getattr(obj,'data',None) or {}
    if target=='project' and obj.owner_id==a.id:return True
    if target=='resource' and a.id in {data.get('teacher_id'),data.get('created_by')}:return True
    if a.role.kind in ('school','college') and 'records.write' in a.permissions and obj.org_id in a.org_ids:return True
    raise HTTPException(403,'只有记录负责人、申请人或所属学院、学校可维护展示图片')


def image_refs(obj):
    data=obj.data or {}
    return {'cover_id':data.get('cover_id'),'photo_ids':list(data.get('photo_ids') or [])}


def _bump(target,obj):
    obj.version=(obj.version or 0)+1


@router.post('/{target}/{ident}')
async def upload_image(target:str,ident:str,request:Request,file:UploadFile=File(...),purpose:str=Form('cover'),expected_version:int=Form(...)):
    if purpose not in ('cover','photo'):raise HTTPException(422,'图片用途无效')
    def authorize():
        with request.app.state.sessions.begin() as db:
            a,_=current_actor(db,request,write=True);a.require('file.write')
            obj=_target(db,target,ident)
            if not can_view(db,a,target,obj):raise HTTPException(403,'记录超出你的查看范围')
            can_maintain(db,a,target,obj)
            if purpose=='photo' and (target!='resource' or obj.kind!='base'):raise HTTPException(422,'只有培训基地可以维护场地照片')
    await run_in_threadpool(authorize)
    limit=min(request.app.state.settings.upload_limit_mb,MAX_IMAGE_MB)*1024*1024
    data=await file.read(limit+1);await file.close()
    if len(data)>limit:raise HTTPException(413,f'图片不能超过 {min(request.app.state.settings.upload_limit_mb,MAX_IMAGE_MB)}MB')
    name=file.filename or ''
    mime=await run_in_threadpool(inspect_upload,name,data)
    if not mime.startswith('image/'):raise HTTPException(422,'展示图片只接收 PNG、JPG 格式；证明材料请在“材料”里上传')
    digest=sha256(data).hexdigest();written=[]
    payload={'target':target,'id':ident,'purpose':purpose,'name':name,'sha256':digest,'expected_version':expected_version}
    def apply(db,a,s):
        a.require('file.write')
        obj=_target(db,target,ident,lock=True);check_version(obj,expected_version)
        if not can_view(db,a,target,obj):raise HTTPException(403,'记录超出你的查看范围')
        can_maintain(db,a,target,obj)
        refs=image_refs(obj)
        if purpose=='photo':
            if obj.kind!='base':raise HTTPException(422,'只有培训基地可以维护场地照片')
            if len(refs['photo_ids'])>=MAX_PHOTOS:raise HTTPException(422,f'场地照片最多 {MAX_PHOTOS} 张，请先移除不用的照片')
        object_type=TARGETS[target][2]
        if db.scalar(select(func.count()).select_from(Attachment).where(Attachment.object_type==object_type,Attachment.object_id==ident))>=50:
            raise HTTPException(422,'该记录的展示图片历史已达上限，请联系管理员')
        root=request.app.state.settings.storage_dir
        if root.is_symlink() or not root.is_dir():raise HTTPException(503,'附件目录未就绪')
        key=secrets.token_hex(32);path=root/key
        fd=open_nofollow(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);written.append(path)
        with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
        item=Attachment(object_type=object_type,object_id=ident,teacher_id=a.id,uploaded_by=a.id,name=name,storage_key=key,sha256=digest,size=len(data),mime=mime)
        db.add(item);db.flush()
        before=refs
        if purpose=='cover':obj.data={**obj.data,'cover_id':item.id}
        else:obj.data={**obj.data,'photo_ids':[*refs['photo_ids'],item.id]}
        _bump(target,obj)
        label=LABELS['project' if target=='project' else obj.kind]
        action=('更换'+('头像' if getattr(obj,'kind','')=='trainer' else '封面') if purpose=='cover' else '添加场地照片')
        workflow(db,a,TARGETS[target][1],ident,label+'：'+action,before,{**image_refs(obj),'name':name,'sha256':digest},'维护展示图片','仅更新展示引用，不改变审批状态')
        return {'image':{'id':item.id,'name':name},'refs':image_refs(obj),'version':obj.version}
    def execute():
        try:return command(request,payload,'records.read',apply)
        except Exception:
            for path in written:
                try:path.unlink()
                except OSError:pass
            raise
    return await run_in_threadpool(execute)


class ImageRemoveIn(Input):
    expected_version:int=Field(ge=1)
    purpose:Literal['cover','photo']
    image_id:str=Field(min_length=1,max_length=36)


@router.post('/{target}/{ident}/remove')
def remove_image(target:str,ident:str,data:ImageRemoveIn,request:Request):
    def apply(db,a,s):
        obj=_target(db,target,ident,lock=True);check_version(obj,data.expected_version)
        if not can_view(db,a,target,obj):raise HTTPException(403,'记录超出你的查看范围')
        can_maintain(db,a,target,obj)
        refs=image_refs(obj)
        if data.purpose=='cover':
            if refs['cover_id']!=data.image_id:raise HTTPException(409,'封面已被更换，请刷新后再试')
            obj.data={**obj.data,'cover_id':None}
        else:
            if data.image_id not in refs['photo_ids']:raise HTTPException(409,'照片已被移除，请刷新后再试')
            obj.data={**obj.data,'photo_ids':[x for x in refs['photo_ids'] if x!=data.image_id]}
        _bump(target,obj)
        label=LABELS['project' if target=='project' else obj.kind]
        workflow(db,a,TARGETS[target][1],ident,label+'：'+('移除展示封面' if data.purpose=='cover' else '移除场地照片'),refs,image_refs(obj),'维护展示图片','原图保留在历史中，不删除')
        return {'refs':image_refs(obj),'version':obj.version}
    return command(request,data.model_dump(),'records.read',apply)


@router.get('/{image_id}')
def show_image(image_id:str,request:Request):
    with request.app.state.sessions.begin() as db:
        a,_=current_actor(db,request)
        item=db.get(Attachment,image_id)
        if not item or item.object_type not in OBJECT_TYPES:raise HTTPException(404,'图片不存在')
        target=OBJECT_TYPES[item.object_type]
        obj=_target(db,target,item.object_id)
        if not can_view(db,a,target,obj):raise HTTPException(403,'图片超出你的查看范围')
        data=verify_file(request.app.state.settings.storage_dir,item)
        mime=item.mime
    return Response(data,media_type=mime,headers={'Cache-Control':'private, max-age=600','X-Content-Type-Options':'nosniff','Content-Disposition':'inline'})
