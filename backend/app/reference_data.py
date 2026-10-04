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
from .integrations import apply_mappings,configuration_hash,mask_raw

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
            except ValidationError as exc:
                # Report only known contract fields; validation messages/inputs may
                # contain upstream personal data or untrusted extra-field names.
                labels={'external_key':'来源业务编号','event_date':'业务日期',
                    'project_code':'项目编码','project':'项目名称','course_code':'课程编码',
                    'course':'课程名称','class_code':'班级编码','class_name':'班级名称',
                    'hours':'学时','income':'培训收入','participants':'课程人次'}
                errors=[]
                for issue in exc.errors(include_input=False,include_context=False,include_url=False):
                    field=issue['loc'][0] if issue['loc'] else None
                    if field in labels:
                        detail='缺失' if issue['type']=='missing' else '格式或取值不符合台账规范'
                        message=f'{labels[field]}（{field}）{detail}'
                    else:message='包含未支持的字段，请核对生效字段映射'
                    if message not in errors:errors.append(message)
                return {},errors+['请提供完整业务记录（含学时、收入与人次），禁止把缺失值猜为零']
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
        db.add(InboundRow(batch_id=batch.id,row_no=i,business_key=key,raw=serial(mask_raw(connection,raw,data_type)),mapped=normalized,errors=errors))
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
        snap={}  # 4.4: per-row before/after kept in the receipt so the batch can be rolled back
        if batch.data_type in {'training_income','course_participants'}:
            from .schemas import RecordIn
            from .services import insert_record
            obj=db.scalar(select(TrainingRecord).where(TrainingRecord.external_key==normalized['external_key']).with_for_update())
            if obj:
                written.append({'row_no':row.row_no,'business_key':row.business_key,'object_id':obj.id,'unchanged':True});continue
            user=db.scalar(select(User).where(User.staff_no==normalized['staff_no']))
            values={k:v for k,v in normalized.items() if k!='staff_no'}
            obj=insert_record(db,actor,RecordIn(**values,teacher_id=user.id,reason=reason,basis=basis),batch_id=batch.id,channel='middle')
            ensure_reference_from_training_record(db,obj,source='学校数据中台')
            snap={'model':'training_record','created':True,'before':{},'after':serial(obj)}
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
            user_before=_user_state(user)
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
            snap={'model':'teacher_hr','created':not before,'before':before,'after':serial(obj),'user_id':user.id if user else None,'user_before':user_before,'user_after':_user_state(user)}
        elif batch.data_type=='training_project':
            obj=db.scalar(select(TrainingProjectMaster).where(TrainingProjectMaster.code==normalized['code']));before=serial(obj) if obj else {}
            values=dict(normalized);values['start_date']=date.fromisoformat(values['start_date']) if values['start_date'] else None;values['end_date']=date.fromisoformat(values['end_date']) if values['end_date'] else None
            if obj:
                for k,v in values.items():setattr(obj,k,v)
                obj.version+=1
            else:obj=TrainingProjectMaster(**values);db.add(obj);db.flush()
            audit(db,actor,'training_project',obj.id,'确认数据中台项目主数据入库',before=before,after=serial(obj),reason=reason)
            snap={'model':'training_project','created':not before,'before':before,'after':serial(obj)}
        elif batch.data_type=='course':
            if normalized['project_code'] and not db.scalar(select(TrainingProjectMaster.id).where(TrainingProjectMaster.code==normalized['project_code'])):
                raise HTTPException(409,{'row':row.row_no,'errors':['课程所属项目编码尚未入库']})
            obj=db.scalar(select(TrainingCourseMaster).where(TrainingCourseMaster.code==normalized['code']));before=serial(obj) if obj else {}
            if obj:
                for k,v in normalized.items():setattr(obj,k,v)
                obj.version+=1
            else:obj=TrainingCourseMaster(**normalized);db.add(obj);db.flush()
            audit(db,actor,'course',obj.id,'确认数据中台课程主数据入库',before=before,after=serial(obj),reason=reason)
            snap={'model':'course','created':not before,'before':before,'after':serial(obj)}
        written.append({'row_no':row.row_no,'business_key':row.business_key,'object_id':obj.id,**snap})
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


# ---- 4.4 rollback of a confirmed inbound batch ---------------------------------
USER_FIELDS=('name','title','org_id','active','version')
MASTER_MODELS={'teacher_hr':TeacherHrProfile,'training_project':TrainingProjectMaster,'course':TrainingCourseMaster}
RESTORE_FIELDS={'teacher_hr':('user_id','name','title','org_code','active','extra','source_updated_at'),
    'training_project':('name','external_key','start_date','end_date','active'),'course':('name','project_code','external_key','active')}
CONFIRM_ACTIONS={'teacher_hr':'确认数据中台教师人事入库','training_project':'确认数据中台项目主数据入库','course':'确认数据中台课程主数据入库'}

def _user_state(user):
    return {k:getattr(user,k) for k in USER_FIELDS} if user else None

def _restore_value(key,value):
    if value in (None,''):return None if key in {'source_updated_at','start_date','end_date','external_key','project_code','user_id'} else value
    if key=='source_updated_at':return datetime.fromisoformat(str(value)).replace(tzinfo=None)
    if key in {'start_date','end_date'}:return date.fromisoformat(str(value))
    return value

def _legacy_snapshot(db,batch,entry):
    """Batches confirmed before per-row snapshots existed: reuse the row audit of the same confirm request."""
    from .models import Audit
    model=batch.data_type
    if model not in CONFIRM_ACTIONS:return None
    confirm=db.scalar(select(Audit).where(Audit.module=='inbound',Audit.object_id==batch.id,Audit.action=='确认数据中台入站整批入库').order_by(Audit.created_at.desc()).limit(1))
    if not confirm or not confirm.request_id:return None
    row=db.scalar(select(Audit).where(Audit.module==model,Audit.object_id==entry['object_id'],Audit.action==CONFIRM_ACTIONS[model],Audit.request_id==confirm.request_id).limit(1))
    if not row:return None
    if model=='teacher_hr' and ((row.before or {}).get('user_id') or (row.after or {}).get('user_id')):return None  # account before-values were not recorded
    return {'model':model,'created':not row.before,'before':row.before,'after':row.after}

def rollback_conflicts(db,batch,entries):
    """Objects changed after this batch (later batches or local edits) are reported, never clobbered."""
    from .core import archive_exists
    from .models import Period
    issues=[];ids={e['object_id'] for e in entries}
    mine=(batch.receipt or {}).get('committed_at','')
    later=db.scalars(select(InboundBatch).where(InboundBatch.state=='COMMITTED',InboundBatch.id!=batch.id,InboundBatch.data_type==batch.data_type)).all()
    for other in later:
        if (other.receipt or {}).get('committed_at','')<=mine:continue
        for r in (other.receipt or {}).get('rows',[]):
            if r.get('object_id') in ids and not r.get('unchanged'):issues.append(f"{r.get('business_key')}：已被后续批次 {other.id[:8]} 修改")
    for e in entries:
        key=e.get('business_key');model=e['model']
        if model=='training_record':
            obj=db.get(TrainingRecord,e['object_id'])
            if not obj or obj.batch_id!=batch.id:issues.append(f'{key}：台账记录不属于本批次');continue
            if obj.state!='VALID' or obj.version!=int((e.get('after') or {}).get('version',1)):issues.append(f'{key}：台账记录入库后已被更正或作废');continue
            for period in db.scalars(select(Period).where(Period.start_date<=obj.event_date,Period.end_date>=obj.event_date)):
                if archive_exists(db,obj.teacher_id,period.id):issues.append(f'{key}：所属教师考核已归档，不能撤销其依据');break
            continue
        # Content (not version) comparison: a later batch that was itself rolled back restores
        # exactly these values, so batches can be undone newest-first.
        obj=db.get(MASTER_MODELS[model],e['object_id']);after=e.get('after') or {};current=serial(obj) if obj else {}
        if not obj or any(current.get(k)!=after.get(k) for k in RESTORE_FIELDS[model] if k in after):issues.append(f'{key}：主数据入库后已被修改');continue
        if model=='teacher_hr' and e.get('user_id'):
            user=db.get(User,e['user_id']);expected=e.get('user_after') or {}
            if not user or not expected or any(getattr(user,k)!=expected.get(k) for k in USER_FIELDS if k!='version'):issues.append(f'{key}：对应账号入库后已被调整')
    return list(dict.fromkeys(issues))

def rollback_inbound(db,actor,batch:InboundBatch,expected_version,reason,basis=''):
    actor.require_admin()
    batch=db.scalar(select(InboundBatch).where(InboundBatch.id==batch.id).with_for_update().execution_options(populate_existing=True))
    receipt=dict(batch.receipt or {})
    if batch.state=='VOID' and receipt.get('rollback'):return batch  # idempotent: already rolled back, nothing re-applied
    check_version(batch,expected_version)
    if batch.state!='COMMITTED':raise HTTPException(409,'只有已入库的批次可以撤销')
    entries=[]
    for e in receipt.get('rows',[]):
        if e.get('unchanged'):continue
        if 'after' not in e:
            legacy=_legacy_snapshot(db,batch,e)
            if legacy is None:raise HTTPException(409,'该批次入库时未记录可恢复的前值（早期批次），不能自动撤销；请按审计记录人工核对后更正')
            e={**e,**legacy}
        entries.append(e)
    conflicts=rollback_conflicts(db,batch,entries)
    if conflicts:raise HTTPException(409,'撤销被拒绝：以下数据在本批入库后已被修改，为避免覆盖请先人工核对：'+'；'.join(conflicts[:20])+(f' 等{len(conflicts)}项' if len(conflicts)>20 else ''))
    restored=[];revoked=0
    for e in entries:
        model=e['model']
        if model=='training_record':
            from .models import RecordRevision
            obj=db.get(TrainingRecord,e['object_id']);before=serial(obj)
            obj.state='VOID';obj.version+=1;db.flush()
            db.add(RecordRevision(record_id=obj.id,version=obj.version,data=serial(obj),reason=reason,actor_id=actor.id))
            workflow(db,actor,'record',obj.id,'撤销数据中台入站记录',before,serial(obj),reason,basis or '整批撤销：'+batch.id)
            restored.append({'business_key':e.get('business_key'),'object_id':obj.id,'action':'VOID'});continue
        obj=db.get(MASTER_MODELS[model],e['object_id']);before=serial(obj)
        if e.get('created'):
            obj.active=False;action='DEACTIVATED'  # created by this batch: deactivate, never physically delete
        else:
            for key in RESTORE_FIELDS[model]:
                if key in e['before']:setattr(obj,key,_restore_value(key,e['before'][key]))
            action='RESTORED'
        obj.version+=1;db.flush()
        if model=='teacher_hr' and e.get('user_id') and e.get('user_before'):
            user=db.get(User,e['user_id']);prior=e['user_before'];ub=_user_state(user)
            auth_changed=user.org_id!=prior['org_id'] or user.active!=prior['active']
            user.name=prior['name'];user.title=prior['title'];user.org_id=prior['org_id'];user.active=prior['active']
            if auth_changed:user.auth_version+=1;revoked+=1
            user.version+=1;db.flush()
            audit(db,actor,'users',user.id,'撤销数据中台人事入库：恢复账号信息',before=ub,after=_user_state(user),reason=reason)
        audit(db,actor,model,obj.id,'撤销数据中台入站：恢复主数据前值' if action=='RESTORED' else '撤销数据中台入站：停用本批新建主数据',before=before,after=serial(obj),reason=reason)
        restored.append({'business_key':e.get('business_key'),'object_id':obj.id,'action':action})
    before_state={'state':batch.state,'version':batch.version}
    batch.state='VOID';batch.version+=1
    batch.receipt={**receipt,'rollback':{'at':utcnow().isoformat(),'actor_id':actor.id,'actor_name':actor.name,'reason':reason,'basis':basis,'objects':restored,'authorization_changes':revoked}}
    audit(db,actor,'inbound',batch.id,'撤销数据中台入站批次',before=before_state,after={'state':'VOID','objects':restored},reason=reason)
    return batch
