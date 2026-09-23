"""Reference/master data and inbound school data-hub staging.

These tables close an internal procurement gap without pretending to know the
school's external protocol.  External network/authentication remains handled by
an adapter.  This module provides deterministic mapping -> preview -> explicit
confirm -> local authoritative reference data.
"""
from __future__ import annotations
from datetime import date, datetime, timezone
from decimal import Decimal
from sqlalchemy import String,Integer,DateTime,Date,Boolean,JSON,Text,ForeignKey,UniqueConstraint,Index,CheckConstraint,Numeric,select
from sqlalchemy.orm import Mapped,mapped_column
from fastapi import HTTPException
from .models import Base,Entity,User,Role,Org,Connection,TrainingRecord,utcnow
from .core import serial,audit,workflow,check_version,digest,org_scope
from .integrations import apply_mappings,configuration_hash

class TeacherHrProfile(Entity,Base):
    __tablename__='teacher_hr_profiles'
    staff_no: Mapped[str]=mapped_column(String(64),unique=True,index=True)
    user_id: Mapped[str|None]=mapped_column(ForeignKey('users.id'),nullable=True,index=True)
    name: Mapped[str]=mapped_column(String(100))
    title: Mapped[str]=mapped_column(String(80),default='')
    org_code: Mapped[str]=mapped_column(String(64),index=True)
    active: Mapped[bool]=mapped_column(Boolean,default=True)
    source: Mapped[str]=mapped_column(String(100),default='学校数据中台')
    extra: Mapped[dict]=mapped_column(JSON,default=dict)
    source_updated_at: Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
    version: Mapped[int]=mapped_column(Integer,default=1)

class TrainingProjectMaster(Entity,Base):
    __tablename__='training_projects'
    code: Mapped[str]=mapped_column(String(64),unique=True,index=True)
    name: Mapped[str]=mapped_column(String(160))
    external_key: Mapped[str|None]=mapped_column(String(128),nullable=True,index=True)
    start_date: Mapped[date|None]=mapped_column(Date,nullable=True)
    end_date: Mapped[date|None]=mapped_column(Date,nullable=True)
    active: Mapped[bool]=mapped_column(Boolean,default=True,index=True)
    source: Mapped[str]=mapped_column(String(100),default='学校数据中台')
    version: Mapped[int]=mapped_column(Integer,default=1)

class TrainingCourseMaster(Entity,Base):
    __tablename__='training_courses'
    code: Mapped[str]=mapped_column(String(64),unique=True,index=True)
    name: Mapped[str]=mapped_column(String(160))
    project_code: Mapped[str|None]=mapped_column(String(64),nullable=True,index=True)
    external_key: Mapped[str|None]=mapped_column(String(128),nullable=True,index=True)
    active: Mapped[bool]=mapped_column(Boolean,default=True,index=True)
    source: Mapped[str]=mapped_column(String(100),default='学校数据中台')
    version: Mapped[int]=mapped_column(Integer,default=1)

class TrainingClassMaster(Entity,Base):
    __tablename__='training_classes'
    code: Mapped[str]=mapped_column(String(64),unique=True,index=True)
    name: Mapped[str]=mapped_column(String(160))
    project_code: Mapped[str]=mapped_column(String(64),index=True)
    course_code: Mapped[str]=mapped_column(String(64),index=True)
    start_date: Mapped[date|None]=mapped_column(Date,nullable=True)
    end_date: Mapped[date|None]=mapped_column(Date,nullable=True)
    active: Mapped[bool]=mapped_column(Boolean,default=True,index=True)
    source: Mapped[str]=mapped_column(String(100),default='学校数据中台')
    version: Mapped[int]=mapped_column(Integer,default=1)

class TeacherParticipation(Entity,Base):
    __tablename__='teacher_participations'
    external_key: Mapped[str]=mapped_column(String(128),unique=True)
    teacher_id: Mapped[str]=mapped_column(ForeignKey('users.id'),index=True)
    event_date: Mapped[date]=mapped_column(Date,index=True)
    project_code: Mapped[str]=mapped_column(String(64),index=True)
    project: Mapped[str]=mapped_column(String(160))
    course_code: Mapped[str]=mapped_column(String(64),index=True)
    course: Mapped[str]=mapped_column(String(160))
    hours: Mapped[float]=mapped_column(Numeric(12,2),nullable=False)
    source: Mapped[str]=mapped_column(String(100),default='经核对人工录入')
    batch_id: Mapped[str|None]=mapped_column(String(36),nullable=True,index=True)
    state: Mapped[str]=mapped_column(String(20),default='VALID',index=True)
    version: Mapped[int]=mapped_column(Integer,default=1)
    __table_args__=(CheckConstraint('hours >= 0'),Index('ix_teacher_participation_teacher_date','teacher_id','event_date'))

class InboundBatch(Entity,Base):
    __tablename__='inbound_batches'
    connection_id: Mapped[str]=mapped_column(ForeignKey('connections.id'),index=True)
    data_type: Mapped[str]=mapped_column(String(64),index=True)
    owner_id: Mapped[str]=mapped_column(ForeignKey('users.id'),index=True)
    source_label: Mapped[str]=mapped_column(String(160),default='手工脱敏联调样本')
    state: Mapped[str]=mapped_column(String(20),default='PREVIEW',index=True)
    total: Mapped[int]=mapped_column(Integer)
    errors: Mapped[int]=mapped_column(Integer)
    configuration_hash: Mapped[str]=mapped_column(String(64),default='')
    content_hash: Mapped[str]=mapped_column(String(64),default='')
    receipt: Mapped[dict]=mapped_column(JSON,default=dict)
    version: Mapped[int]=mapped_column(Integer,default=1)

class InboundRow(Entity,Base):
    __tablename__='inbound_rows'
    batch_id: Mapped[str]=mapped_column(ForeignKey('inbound_batches.id'),index=True)
    row_no: Mapped[int]=mapped_column(Integer)
    business_key: Mapped[str]=mapped_column(String(160),index=True)
    raw: Mapped[dict]=mapped_column(JSON)
    mapped: Mapped[dict]=mapped_column(JSON)
    errors: Mapped[list]=mapped_column(JSON,default=list)
    __table_args__=(UniqueConstraint('batch_id','row_no'),)

SUPPORTED_INBOUND={'teacher_hr','training_project','course','training_income','course_participants'}

def _txt(v,label,max_len=160,required=True):
    s=str(v if v is not None else '').strip()
    if required and not s: raise ValueError(label+'必填')
    if len(s)>max_len:raise ValueError(label+'过长')
    return s

def _bool(v,label='启用状态'):
    if v in (True,1,'1','true','TRUE','是','启用','active','ACTIVE'):return True
    if v in (False,0,'0','false','FALSE','否','停用','inactive','INACTIVE'):return False
    raise ValueError(label+'必须是布尔值')

def _day(v,label,required=False):
    if v in (None,''):
        if required:raise ValueError(label+'必填')
        return None
    if isinstance(v,date):return v.isoformat()
    try:return date.fromisoformat(str(v)).isoformat()
    except ValueError:raise ValueError(label+'格式应为 YYYY-MM-DD') from None

def validate_inbound(data_type,mapped):
    try:
        if data_type in {'training_income','course_participants'}:
            from .schemas import RecordIn
            from pydantic import ValidationError
            staff_no=_txt(mapped.get('staff_no'),'教师工号',64)
            fields={k:v for k,v in mapped.items() if k not in {'staff_no','teacher_id','source','reason','basis'}}
            try:record=RecordIn(**fields,teacher_id='pending',source='学校数据中台',reason='数据中台入站校验')
            except ValidationError:return {},['培训流水字段不完整或不符合台账规范，请提供完整业务记录（含学时、收入与人次），禁止把缺失值猜为零']
            return {**serial(record.model_dump(exclude={'teacher_id','reason','basis'})),'staff_no':staff_no},[]
        if data_type=='teacher_hr':
            known={'staff_no','name','title','org_code','active','source_updated_at','extra'}
            x={'staff_no':_txt(mapped.get('staff_no'),'教师工号',64),'name':_txt(mapped.get('name'),'姓名',100),
               'title':_txt(mapped.get('title',''),'职称/岗位',80,False),'org_code':_txt(mapped.get('org_code'),'组织编码',64),
               'active':_bool(mapped.get('active',True)),'source_updated_at':mapped.get('source_updated_at')}
            x['extra']={**(mapped.get('extra') if isinstance(mapped.get('extra'),dict) else {}),**{k:v for k,v in mapped.items() if k not in known}}
            if x['source_updated_at']:
                stamp=datetime.fromisoformat(str(x['source_updated_at']).replace('Z','+00:00'))
                if stamp.tzinfo is None:raise ValueError('来源更新时间必须含时区，不能猜测学校时区')
                x['source_updated_at']=stamp.astimezone(timezone.utc).isoformat()
            return x,[]
        if data_type=='training_project':
            start=_day(mapped.get('start_date'),'项目开始日期');end=_day(mapped.get('end_date'),'项目结束日期')
            if start and end and end<start:raise ValueError('项目结束日期不能早于开始日期')
            return {'code':_txt(mapped.get('code'),'项目编码',64),'name':_txt(mapped.get('name'),'项目名称',160),
              'external_key':_txt(mapped.get('external_key',''),'外部主键',128,False) or None,'start_date':start,'end_date':end,
              'active':_bool(mapped.get('active',True))},[]
        if data_type=='course':
            return {'code':_txt(mapped.get('code'),'课程编码',64),'name':_txt(mapped.get('name'),'课程名称',160),
              'project_code':_txt(mapped.get('project_code',''),'项目编码',64,False) or None,
              'external_key':_txt(mapped.get('external_key',''),'外部主键',128,False) or None,'active':_bool(mapped.get('active',True))},[]
    except ValueError as exc:return {},[str(exc)]
    return {},['当前数据类型尚无正式入站落库契约']

def hr_freshness_errors(profile, normalized):
    if profile is None or profile.source_updated_at is None:return []
    if not normalized.get('source_updated_at'):
        return ['已有来源更新时间，缺少时间戳的数据不能覆盖正式人事信息']
    incoming=datetime.fromisoformat(normalized['source_updated_at']).astimezone(timezone.utc).replace(tzinfo=None)
    if incoming<profile.source_updated_at:return ['来源数据旧于已入库版本，拒绝倒退覆盖']
    if incoming==profile.source_updated_at and any(getattr(profile,k)!=normalized[k] for k in ('name','title','org_code','active','extra')):
        return ['相同来源更新时间对应不同内容，请联系数据责任方核对']
    return []


def validate_inbound_relations(db,data_type,normalized,*,lock=False):
    """The same association gate runs in preview and immediately before commit."""
    def one(q):return db.scalar(q.with_for_update() if lock else q)
    errors=[]
    if data_type in {'training_income','course_participants'}:
        user=one(select(User).where(User.staff_no==normalized['staff_no']))
        if not user or not user.active:errors.append('教师工号未对应启用的本地账号')
        else:
            role=db.get(Role,user.role_id);org=db.get(Org,user.org_id)
            try:
                if not role or not role.active or role.kind!='teacher':raise HTTPException(403,'教师角色不可用')
                org_scope(db,org,'teacher')
            except (HTTPException,AttributeError):errors.append('教师组织或角色不可用')
        errors.extend(record_reference_errors(db,normalized))
        existing=one(select(TrainingRecord).where(TrainingRecord.external_key==normalized['external_key']))
        if existing:
            expected={k:v for k,v in normalized.items() if k!='staff_no'}
            expected['teacher_id']=user.id if user else ''
            actual=serial(existing)
            if existing.state!='VALID' or any((Decimal(str(actual.get(k,0)))!=Decimal(str(v))) if k in {'hours','income'} else str(actual.get(k,''))!=str(v) for k,v in expected.items()):
                errors.append('该来源业务编号已有不同台账记录；为保留本地修改，请先在培训台账核对并留痕更正')
        return errors
    if data_type=='teacher_hr':
        org=one(select(Org).where(Org.code==normalized['org_code']))
        if not org or not org.active or org.kind!='dept':errors.append('组织编码必须对应启用教研室')
        elif org:
            try:org_scope(db,org,'teacher')
            except HTTPException:errors.append('教研室所属学院或学校已停用或层级异常')
        profile=one(select(TeacherHrProfile).where(TeacherHrProfile.staff_no==normalized['staff_no']))
        errors.extend(hr_freshness_errors(profile,normalized))
        user=one(select(User).where(User.staff_no==normalized['staff_no']))
        if user:
            role=one(select(Role).where(Role.id==user.role_id))
            if not role or role.kind!='teacher':errors.append('工号已绑定非教师账号')
    elif data_type=='course' and normalized.get('project_code'):
        project=one(select(TrainingProjectMaster).where(TrainingProjectMaster.code==normalized['project_code']))
        if not project:errors.append('课程所属项目编码尚未入库')
        elif not project.active:errors.append('课程所属项目已停用')
    if data_type=='course' and normalized.get('project_code'):
        code,project=normalized['code'],normalized['project_code']
        conflict=(one(select(TrainingRecord.id).where(TrainingRecord.course_code==code,TrainingRecord.project_code!=project).limit(1))
            or one(select(TeacherParticipation.id).where(TeacherParticipation.course_code==code,TeacherParticipation.project_code!=project).limit(1))
            or one(select(TrainingClassMaster.id).where(TrainingClassMaster.course_code==code,TrainingClassMaster.project_code!=project).limit(1)))
        if conflict:errors.append('课程项目归属与已存在业务或班级关联冲突')
    return errors

def inbound_content_hash(rows):
    return digest([{'row_no':r.row_no,'business_key':r.business_key,'raw':r.raw,'mapped':r.mapped,'errors':r.errors} for r in rows])

def preview_inbound(db,actor,connection:Connection,data_type,records,source_label='手工脱敏联调样本'):
    if connection.code!='middle':raise HTTPException(422,'只有学校数据中台使用本入站预览链')
    if data_type not in SUPPORTED_INBOUND:raise HTTPException(422,'该数据类型尚未建立正式入站落库契约')
    if not isinstance(records,list) or not 1<=len(records)<=1000:raise HTTPException(422,'入站记录数量无效')
    batch=InboundBatch(connection_id=connection.id,data_type=data_type,owner_id=actor.id,source_label=source_label,total=len(records),errors=0,receipt={},configuration_hash=configuration_hash(connection))
    db.add(batch);db.flush();seen=set()
    for i,raw in enumerate(records,1):
        mapped,mapping_errors=apply_mappings(connection,raw,data_type)
        normalized,validation_errors=validate_inbound(data_type,mapped)
        errors=list(mapping_errors)+list(validation_errors)
        if not validation_errors:errors+=validate_inbound_relations(db,data_type,normalized)
        key=str(normalized.get('external_key') if data_type in {'training_income','course_participants'} else normalized.get('staff_no') or normalized.get('code') or '').strip()
        if key in seen:errors.append('同批业务唯一键重复')
        if key:seen.add(key)
        else:errors.append('无法确定业务唯一键')
        db.add(InboundRow(batch_id=batch.id,row_no=i,business_key=key,raw=serial(raw),mapped=normalized,errors=errors))
        if errors:batch.errors+=1
    db.flush()
    batch.content_hash=inbound_content_hash(db.scalars(select(InboundRow).where(InboundRow.batch_id==batch.id).order_by(InboundRow.row_no)).all())
    audit(db,actor,'inbound',batch.id,'生成数据中台入站预览',after={'data_type':data_type,'rows':batch.total,'errors':batch.errors},reason='仅预览，未写正式主数据')
    return batch

def confirm_inbound(db,actor,batch:InboundBatch,expected_version,reason,basis=''):
    # Keep PREVIEW/staging evidence while rolling back every formal write if a worker
    # catches a later exception and commits its outer task/attempt transaction.
    with db.begin_nested():
        return _confirm_inbound(db,actor,batch,expected_version,reason,basis)

def _confirm_inbound(db,actor,batch:InboundBatch,expected_version,reason,basis=''):
    actor.require_admin()
    batch=db.scalar(select(InboundBatch).where(InboundBatch.id==batch.id).with_for_update().execution_options(populate_existing=True))
    check_version(batch,expected_version)
    if batch.owner_id!=actor.id:raise HTTPException(403,'只能确认本人生成的入站预览')
    if batch.state!='PREVIEW':raise HTTPException(409,'该入站批次已处理')
    if batch.errors:raise HTTPException(409,'预览仍有错误行，不能确认入库')
    rows=db.scalars(select(InboundRow).where(InboundRow.batch_id==batch.id).order_by(InboundRow.row_no)).all()
    connection=db.scalar(select(Connection).where(Connection.id==batch.connection_id).with_for_update())
    if not connection or batch.configuration_hash!=configuration_hash(connection):
        raise HTTPException(409,'接口配置或字段映射已变化，请重新生成预览')
    if len(rows)!=batch.total or not rows or batch.content_hash!=inbound_content_hash(rows):
        raise HTTPException(409,'预览行数量或内容校验不一致，禁止确认')
    seen=set()
    for row in rows:
        normalized,errors=validate_inbound(batch.data_type,row.mapped)
        if not errors:errors+=validate_inbound_relations(db,batch.data_type,normalized,lock=True)
        key=str(normalized.get('external_key') if batch.data_type in {'training_income','course_participants'} else normalized.get('staff_no') or normalized.get('code') or '')
        if not key or key!=row.business_key or key in seen:errors.append('预览业务唯一键异常')
        seen.add(key)
        if row.errors or errors:raise HTTPException(409,{'row':row.row_no,'errors':row.errors+errors})
    written=[];unmapped_accounts=0;revoked_sessions=0
    for row in rows:
        normalized,errors=validate_inbound(batch.data_type,row.mapped)
        if errors:raise HTTPException(409,{'row':row.row_no,'errors':errors})
        if batch.data_type in {'training_income','course_participants'}:
            from .schemas import RecordIn
            from .services import insert_record
            obj=db.scalar(select(TrainingRecord).where(TrainingRecord.external_key==normalized['external_key']).with_for_update())
            if obj:
                written.append({'row_no':row.row_no,'business_key':row.business_key,'object_id':obj.id,'unchanged':True});continue
            user=db.scalar(select(User).where(User.staff_no==normalized['staff_no']))
            values={k:v for k,v in normalized.items() if k!='staff_no'}
            obj=insert_record(db,actor,RecordIn(**values,teacher_id=user.id,reason=reason,basis=basis),batch_id=batch.id)
            ensure_reference_from_training_record(db,obj,source='学校数据中台')
        elif batch.data_type=='teacher_hr':
            org=db.scalar(select(Org).where(Org.code==normalized['org_code'],Org.active.is_(True)))
            if not org or org.kind!='dept':raise HTTPException(409,{'row':row.row_no,'errors':['组织编码必须对应启用教研室']})
            obj=db.scalar(select(TeacherHrProfile).where(TeacherHrProfile.staff_no==normalized['staff_no']))
            before=serial(obj) if obj else {}
            stamp=datetime.fromisoformat(normalized['source_updated_at']).replace(tzinfo=None) if normalized.get('source_updated_at') else None
            if obj and stamp is not None and obj.source_updated_at==stamp:
                # Identical source replay must not reapply stale authorization to a
                # user who was subsequently edited locally. The batch is still audited.
                written.append({'row_no':row.row_no,'business_key':row.business_key,'object_id':obj.id,'unchanged':True})
                continue
            user=db.scalar(select(User).where(User.staff_no==normalized['staff_no']))
            if user:
                role=db.get(Role,user.role_id)
                if not role or role.kind!='teacher':raise HTTPException(409,{'row':row.row_no,'errors':['工号已绑定非教师账号']})
                auth_changed=(user.org_id!=org.id or user.active!=normalized['active'])
                user.name=normalized['name'];user.title=normalized['title'];user.org_id=org.id;user.active=normalized['active'];user.version+=1
                if auth_changed:user.auth_version+=1;revoked_sessions+=1
            else:unmapped_accounts+=1
            if obj:
                obj.user_id=user.id if user else None;obj.name=normalized['name'];obj.title=normalized['title'];obj.org_code=normalized['org_code'];obj.active=normalized['active'];obj.extra=normalized['extra'];obj.source_updated_at=datetime.fromisoformat(normalized['source_updated_at']).replace(tzinfo=None) if normalized.get('source_updated_at') else None;obj.version+=1
            else:
                obj=TeacherHrProfile(staff_no=normalized['staff_no'],user_id=user.id if user else None,name=normalized['name'],title=normalized['title'],org_code=normalized['org_code'],active=normalized['active'],extra=normalized['extra'],source_updated_at=datetime.fromisoformat(normalized['source_updated_at']).replace(tzinfo=None) if normalized.get('source_updated_at') else None)
                db.add(obj);db.flush()
            audit(db,actor,'teacher_hr',obj.id,'确认数据中台教师人事入库',before=before,after=serial(obj),reason=reason)
        elif batch.data_type=='training_project':
            obj=db.scalar(select(TrainingProjectMaster).where(TrainingProjectMaster.code==normalized['code']));before=serial(obj) if obj else {}
            values=dict(normalized);values['start_date']=date.fromisoformat(values['start_date']) if values['start_date'] else None;values['end_date']=date.fromisoformat(values['end_date']) if values['end_date'] else None
            if obj:
                for k,v in values.items():setattr(obj,k,v)
                obj.version+=1
            else:obj=TrainingProjectMaster(**values);db.add(obj);db.flush()
            audit(db,actor,'training_project',obj.id,'确认数据中台项目主数据入库',before=before,after=serial(obj),reason=reason)
        elif batch.data_type=='course':
            if normalized['project_code'] and not db.scalar(select(TrainingProjectMaster.id).where(TrainingProjectMaster.code==normalized['project_code'])):
                raise HTTPException(409,{'row':row.row_no,'errors':['课程所属项目编码尚未入库']})
            obj=db.scalar(select(TrainingCourseMaster).where(TrainingCourseMaster.code==normalized['code']));before=serial(obj) if obj else {}
            if obj:
                for k,v in normalized.items():setattr(obj,k,v)
                obj.version+=1
            else:obj=TrainingCourseMaster(**normalized);db.add(obj);db.flush()
            audit(db,actor,'course',obj.id,'确认数据中台课程主数据入库',before=before,after=serial(obj),reason=reason)
        written.append({'row_no':row.row_no,'business_key':row.business_key,'object_id':obj.id})
    batch.state='COMMITTED';batch.version+=1;batch.receipt={**(batch.receipt or {}),'written':len(written),'rows':written,'unmapped_teacher_accounts':unmapped_accounts,'authorization_changes':revoked_sessions,'committed_at':utcnow().isoformat(),'configuration_hash':batch.configuration_hash,'content_hash':batch.content_hash}
    audit(db,actor,'inbound',batch.id,'确认数据中台入站整批入库',after=batch.receipt,reason=reason)
    return batch

def record_reference_errors(db, record, *, pending=None):
    """Validate identities without changing school-wide master data from a ledger.

    A course with project_code=None is explicitly global. A bound course and a
    class cannot be silently moved to another project by a departmental operator.
    The same pending identity map catches conflicts between rows of one import.
    """
    get=record.get if isinstance(record,dict) else lambda name:getattr(record,name,None)
    project,course,klass=get('project_code'),get('course_code'),get('class_code')
    errors=[]
    c=db.scalar(select(TrainingCourseMaster).where(TrainingCourseMaster.code==course))
    k=db.scalar(select(TrainingClassMaster).where(TrainingClassMaster.code==klass)) if klass else None
    if c and c.project_code is not None and c.project_code!=project:
        errors.append('课程编码已绑定其他项目，请核对项目/课程编码')
    if k and (k.project_code!=project or k.course_code!=course):
        errors.append('班级编码已绑定其他项目或课程，请核对班级编码')
    if pending is not None:
        pc=pending.setdefault('courses',{});pk=pending.setdefault('classes',{})
        if not c or c.project_code is not None:
            if course in pc and pc[course]!=project:errors.append('同批课程编码出现不同项目归属')
            pc.setdefault(course,project)
        if klass:
            pair=(project,course)
            if klass in pk and pk[klass]!=pair:errors.append('同批班级编码出现不同项目或课程归属')
            pk.setdefault(klass,pair)
    return errors


def ensure_reference_from_training_record(db,record,source='培训业务台账派生'):
    """Create missing identities only; never rename/reparent an existing master.

    Historical display names stay on each ledger row. Authoritative master changes
    belong to validated school-admin inbound configuration, not financial edits.
    """
    errors=record_reference_errors(db,record)
    if errors:raise HTTPException(409,'；'.join(errors))
    if not db.scalar(select(TrainingProjectMaster.id).where(TrainingProjectMaster.code==record.project_code)):
        db.add(TrainingProjectMaster(code=record.project_code,name=record.project,source=source,active=True));db.flush()
    if not db.scalar(select(TrainingCourseMaster.id).where(TrainingCourseMaster.code==record.course_code)):
        db.add(TrainingCourseMaster(code=record.course_code,name=record.course,project_code=record.project_code,source=source,active=True));db.flush()
    if not db.scalar(select(TrainingClassMaster.id).where(TrainingClassMaster.code==record.class_code)):
        db.add(TrainingClassMaster(code=record.class_code,name=record.class_name,project_code=record.project_code,course_code=record.course_code,source=source,active=True));db.flush()
