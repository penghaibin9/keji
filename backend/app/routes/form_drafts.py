"""Versioned private input drafts. Formal creation still uses the original APIs."""
import json
import re
from typing import Literal
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr, model_validator
from sqlalchemy import select,func
from ..core import audit, command, read_operation
from ..models import FormDraft, utcnow

router=APIRouter(prefix='/api/form-drafts',tags=['个人填写草稿'])
Kind=Literal['project','qualification','course','teaching_course','base','trainer','trainer_external','claim','annual']
FIELDS={
 'project':'code name cohort org_id owner_id owner_id_search category high_risk start_date end_date expected_income expected_participants expected_outcomes one_skill province_report province_basis target_groups total_hours video_minutes base_count venue_type venue_place venue_reason venue_ref mode class_type level scene level_basis auxiliary_standard auxiliary_daily_cap dates_confirmed level_confirmed scene_confirmed mode_confirmed audience_other',
 'qualification':'category name certificate_no issuer obtained expires _long_term',
 'course':'code name hours teaching_mode ideology intro project_code teacher_id teacher_id_search package one_skill target_groups cw_checked cw_reviewer cw_on cw_ref',
 'teaching_course':'hours teaching_mode ideology intro package one_skill target_groups cw_checked cw_reviewer cw_on cw_ref aud_other',
 'base':'code name manager_name usage_practice usage_ideology level onsite partner established_on recognized_on location recognition',
 'trainer':'name unit title specialty qualification_basis experience',
 'trainer_external':'name unit title specialty qualification_basis experience',
 'claim':'project_id period_id policy_id recognition_form_reference submit_now',
 'annual':'org_id period_id policy_id income_target participants_target priority_target staff_denominator target_reference staff_basis self_report other_bonus other_bonus_basis compliance_failures discipline_reference confirmed_veto',
}
FILE_FIELDS={'file','proof_files','cover_file'}


class DraftOwner(BaseModel):
    model_config=ConfigDict(extra='forbid',hide_input_in_errors=True)
    user_id:str=Field(min_length=1,max_length=64)
    role_id:str=Field(min_length=1,max_length=64)
    org_id:str=Field(min_length=1,max_length=64)


class DraftInput(BaseModel):
    model_config=ConfigDict(extra='forbid',hide_input_in_errors=True)
    owner:DraftOwner
    expected_version:int=Field(ge=0)
    title:str=Field(min_length=1,max_length=200)
    source_version:int|None=Field(default=None,ge=1)
    values:dict[str,StrictStr|StrictBool]=Field(default_factory=dict)
    files:dict[str,list[str]]=Field(default_factory=dict)
    auxiliary:list[dict[str,StrictStr]]=Field(default_factory=list,max_length=1000)

    @model_validator(mode='after')
    def bounded(self):
        if len(self.values)>200 or any(len(k)>80 or isinstance(v,str) and len(v)>20000 for k,v in self.values.items()):
            raise ValueError('草稿字段或内容过长，请分次整理')
        if len(json.dumps(self.model_dump(),ensure_ascii=False).encode())>128*1024:
            raise ValueError('草稿内容过大，请精简后再保存')
        if not set(self.files)<=FILE_FIELDS or any(len(names)>50 for names in self.files.values()):
            raise ValueError('草稿材料清单不合法')
        for names in self.files.values():
            if any(not isinstance(n,str) or not 1<=len(n)<=200 or re.search(r'[/\\\x00-\x1f]',n) for n in names):
                raise ValueError('只允许保存材料文件名，不能保存路径或文件内容')
        for row in self.auxiliary:
            if set(row)!={'work_date','amount','description'} or any(len(v)>2000 for v in row.values()):
                raise ValueError('辅助工作草稿格式不正确')
        return self


class DraftFinish(BaseModel):
    model_config=ConfigDict(extra='forbid',hide_input_in_errors=True)
    owner:DraftOwner
    expected_version:int=Field(ge=1)
    action:Literal['complete','discard']


def require_kind(actor,kind):
    if kind=='project' and not (actor.role.kind=='teacher' or actor.role.kind in ('college','school') and 'records.write' in actor.permissions):
        raise HTTPException(403,'当前身份不能保存项目填写草稿')
    if kind=='qualification':actor.require('qualification.write')
    if kind=='trainer_external' and actor.role.kind not in ('college','school'):
        raise HTTPException(403,'当前身份不能登记外聘培训师')
    if kind=='annual':
        actor.require('assessment.review')
        if actor.role.kind not in ('college','school'):raise HTTPException(403,'当前身份不能填写学院自评')
    if kind=='claim':actor.require('records.read')


def check_owner(owner,actor):
    if owner.model_dump()!={'user_id':actor.id,'role_id':actor.role.id,'org_id':actor.org.id}:
        raise HTTPException(409,'登录身份已变化，未把草稿保存或清理到其他身份，请刷新核对')


def load(db,actor,kind,context_key):
    require_kind(actor,kind)
    if re.search(r'[\x00-\x1f]',context_key):raise HTTPException(422,'草稿标识无效')
    return db.scalar(select(FormDraft).where(FormDraft.user_id==actor.id,FormDraft.role_id==actor.role.id,
        FormDraft.org_id==actor.org.id,FormDraft.kind==kind,FormDraft.context_key==context_key))


def present(row,actor):
    owner={'user_id':actor.id,'role_id':actor.role.id,'org_id':actor.org.id}
    if row is None:return {'version':0,'draft':None,'owner':owner}
    if row.state!='ACTIVE':return {'version':row.version,'draft':None,'owner':owner}
    # Existing response masking recognizes this server-assigned owner, not a submitted identity.
    payload={**row.payload,'values':{**row.payload.get('values',{}),'user_id':actor.id}}
    return {'version':row.version,'owner':owner,'draft':{'title':row.title,'source_version':row.source_version,
        'updated_at':row.updated_at.isoformat()+'Z','payload':payload}}


@router.get('')
def list_drafts(request:Request,kind:Kind,prefix:str=Query('new:',min_length=1,max_length=120),
                page:int=Query(1,ge=1),size:int=Query(20,ge=1,le=50)):
    def read(db,a,s):
        require_kind(a,kind)
        query=select(FormDraft).where(FormDraft.user_id==a.id,FormDraft.role_id==a.role.id,
            FormDraft.org_id==a.org.id,FormDraft.kind==kind,FormDraft.state=='ACTIVE',
            FormDraft.context_key.startswith(prefix,autoescape=True))
        total=db.scalar(select(func.count()).select_from(query.subquery()))
        rows=db.scalars(query.order_by(FormDraft.updated_at.desc(),FormDraft.id).offset((page-1)*size).limit(size)).all()
        return {'items':[{'context_key':r.context_key,'title':r.title,'updated_at':r.updated_at.isoformat()+'Z'} for r in rows],
            'page':page,'size':size,'total':total,'owner':present(None,a)['owner']}
    return read_operation(request,'portal.read',read)


@router.get('/{kind}')
def get_draft(kind:Kind,request:Request,context_key:str=Query('new',min_length=1,max_length=160)):
    return read_operation(request,'portal.read',lambda db,a,s:present(load(db,a,kind,context_key),a))


@router.put('/{kind}')
def save_draft(kind:Kind,data:DraftInput,request:Request,context_key:str=Query('new',min_length=1,max_length=160)):
    allowed=set(FIELDS[kind].split())|{'reason','basis'}
    for key in data.values:
        if key not in allowed and not (
            kind in ('project','course','teaching_course') and re.fullmatch(r'aud_[0-9]{1,2}|aud_other|svc_(national|regional|industry|other)|tm_(classroom|case|onsite|field|seminar|lab|internship|peer|other)',key)
            or kind in ('trainer','trainer_external') and re.fullmatch(r'dir_(subsidy|enterprise|community|rural|other|one_skill)|qual_[A-Za-z0-9_-]{1,64}',key)
        ):
            raise HTTPException(422,'该字段不属于本类填写草稿')
    if data.auxiliary and kind!='claim':raise HTTPException(422,'此类草稿不能保存辅助工作行')
    def save(db,a,s):
        check_owner(data.owner,a)
        row=load(db,a,kind,context_key)
        if (row.version if row else 0)!=data.expected_version:
            raise HTTPException(409,'草稿已被其他窗口更新，当前文字已保留；请先查看最新草稿，不能直接覆盖')
        if row is None:
            row=FormDraft(user_id=a.id,role_id=a.role.id,org_id=a.org.id,kind=kind,context_key=context_key)
            db.add(row);before=0;row.version=1
        else:before=row.version;row.version+=1
        row.title=data.title;row.payload={'values':data.values,'files':data.files,'auxiliary':data.auxiliary}
        row.source_version=data.source_version;row.state='ACTIVE';row.updated_at=utcnow();db.flush()
        audit(db,a,'form_drafts',row.id,'暂存填写内容',{'version':before},{'version':row.version,'kind':kind},'本人主动暂存，未创建或提交业务')
        return present(row,a)
    return command(request,{'context_key':context_key,**data.model_dump()},'portal.read',save)


@router.post('/{kind}/finish')
def finish_draft(kind:Kind,data:DraftFinish,request:Request,context_key:str=Query('new',min_length=1,max_length=160)):
    def finish(db,a,s):
        check_owner(data.owner,a)
        row=load(db,a,kind,context_key)
        if not row or row.version!=data.expected_version:raise HTTPException(409,'草稿版本已变化，未清理其他窗口的新内容')
        row.state='COMPLETED' if data.action=='complete' else 'DISCARDED';row.version+=1;row.updated_at=utcnow()
        audit(db,a,'form_drafts',row.id,'填写草稿已完成' if data.action=='complete' else '本人放弃填写草稿',
            {},{'version':row.version,'state':row.state},'保留草稿记录，不改动正式业务')
        return present(row,a)
    return command(request,{'context_key':context_key,**data.model_dump()},'portal.read',finish)
