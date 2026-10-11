"""Reference/master data and inbound school data-hub staging.

These tables close an internal procurement gap without pretending to know the
school's external protocol.  External network/authentication remains handled by
an adapter.  This module provides deterministic mapping -> preview -> explicit
confirm -> local authoritative reference data.
"""
from __future__ import annotations
from datetime import date, datetime, timezone
from decimal import Decimal
import re
from sqlalchemy import String,Integer,DateTime,Date,Boolean,JSON,Text,ForeignKey,UniqueConstraint,Index,CheckConstraint,Numeric,select
from sqlalchemy.orm import Mapped,mapped_column
from fastapi import HTTPException
from .models import Base,Entity,User,Role,Org,Connection,TrainingRecord,utcnow
from .core import serial,audit,workflow,check_version,digest,org_scope
from .integrations import apply_mappings,configuration_hash,mask_raw
from .code_tables import tables as code_tables,derive_hr_active

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

class TeacherCourseTerm(Entity,Base):
    """One teacher teaching one course in one school term, as reported by a school system.

    origin separates the 教务 schedule (JW) from the 超星 online course library (CX);
    both describe the same teachers and are kept side by side for term scoring.
    """
    __tablename__='teacher_course_terms'
    external_key: Mapped[str]=mapped_column(String(200),unique=True)
    origin: Mapped[str]=mapped_column(String(8),index=True)
    staff_no: Mapped[str]=mapped_column(String(64),index=True)
    user_id: Mapped[str|None]=mapped_column(ForeignKey('users.id'),nullable=True,index=True)
    teacher_name: Mapped[str]=mapped_column(String(100),default='')
    course_code: Mapped[str]=mapped_column(String(64),index=True)
    course_name: Mapped[str]=mapped_column(String(300))
    term_name: Mapped[str]=mapped_column(String(64),index=True)
    credit: Mapped[float|None]=mapped_column(Numeric(8,2),nullable=True)
    hours: Mapped[float|None]=mapped_column(Numeric(10,2),nullable=True)
    extra: Mapped[dict]=mapped_column(JSON,default=dict)
    source_stamp: Mapped[str]=mapped_column(String(64),default='')
    active: Mapped[bool]=mapped_column(Boolean,default=True,index=True)
    source: Mapped[str]=mapped_column(String(100),default='学校数据中台')
    version: Mapped[int]=mapped_column(Integer,default=1)
    __table_args__=(Index('ix_teacher_course_term_staff_term','staff_no','term_name'),)

class SchoolCourse(Entity,Base):
    """教务课程总库 row: the course's official credit and hours, looked up by course code.

    The 教务 teaching table carries no credit, so teacher credits come from here.
    Kept apart from training_courses so school catalogue courses never show up
    as non-degree training courses.
    """
    __tablename__='school_courses'
    external_key: Mapped[str]=mapped_column(String(128),unique=True)
    code: Mapped[str]=mapped_column(String(100),index=True)
    name: Mapped[str]=mapped_column(String(300))
    credit: Mapped[float|None]=mapped_column(Numeric(8,2),nullable=True)
    hours: Mapped[float|None]=mapped_column(Numeric(10,2),nullable=True)
    weekly_hours: Mapped[float|None]=mapped_column(Numeric(8,2),nullable=True)
    dept: Mapped[str]=mapped_column(String(300),default='')
    course_version: Mapped[str]=mapped_column(String(32),default='')
    extra: Mapped[dict]=mapped_column(JSON,default=dict)
    active: Mapped[bool]=mapped_column(Boolean,default=True,index=True)
    source: Mapped[str]=mapped_column(String(100),default='学校数据中台')
    version: Mapped[int]=mapped_column(Integer,default=1)

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

SUPPORTED_INBOUND={'teacher_hr','training_project','course','training_income','course_participants','teacher_course','online_course','school_course'}
TEACHING_TYPES={'teacher_course':'JW','online_course':'CX'}
# Data types whose business key is the external_key field.
KEYED_TYPES={'training_income','course_participants','school_course',*TEACHING_TYPES}
# School-system feeds repeat identical rows (weekly slots, course versions); identical rows collapse.
COLLAPSE_TYPES={'school_course',*TEACHING_TYPES}

def business_key(data_type,normalized):
    return str(normalized.get('external_key') if data_type in KEYED_TYPES else normalized.get('staff_no') or normalized.get('code') or '').strip()

def _txt(v,label,max_len=160,required=True):
    s=str(v if v is not None else '').strip()
    if required and not s: raise ValueError(label+'必填')
    if len(s)>max_len:raise ValueError(label+'过长')
    return s

def _bool(v,label='启用状态'):
    if v in (True,1,'1','true','TRUE','是','启用','active','ACTIVE'):return True
    if v in (False,0,'0','false','FALSE','否','停用','inactive','INACTIVE'):return False
    raise ValueError(label+'必须是布尔值')

def _num(v,label):
    if v in (None,''):return None
    try:d=Decimal(str(v).strip())
    except Exception:raise ValueError(label+'必须是数字') from None
    if not d.is_finite() or d<0 or d>=Decimal('100000'):raise ValueError(label+'超出范围')
    return str(d.quantize(Decimal('0.01')))

def _term(mapped):
    term=_txt(mapped.get('term_name',''),'学期',64,False)
    if term:return term
    year=_txt(mapped.get('school_year',''),'学年',16,False);no=_txt(mapped.get('term_no',''),'学期序号',8,False)
    if year and no:return f'{year}-{no}'
    raise ValueError('学期必填（学期名称，或学年+学期序号）')

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
        if data_type in TEACHING_TYPES:
            known={'staff_no','teacher_name','course_code','course_name','term_name','school_year','term_no','credit','hours','source_stamp','extra'}
            x={'origin':TEACHING_TYPES[data_type],'staff_no':_txt(mapped.get('staff_no'),'教师工号',64),
               'teacher_name':_txt(mapped.get('teacher_name',''),'教师姓名',100,False),
               'course_code':_txt(mapped.get('course_code'),'课程编码',64),'course_name':_txt(mapped.get('course_name'),'课程名称',300),
               'term_name':_term(mapped),'credit':_num(mapped.get('credit'),'学分'),'hours':_num(mapped.get('hours'),'学时'),
               'source_stamp':_txt(mapped.get('source_stamp',''),'来源时间戳',64,False)}
            x['extra']={**(mapped.get('extra') if isinstance(mapped.get('extra'),dict) else {}),**{k:v for k,v in mapped.items() if k not in known}}
            x['external_key']='|'.join((x['origin'],x['staff_no'],x['course_code'],x['term_name']))
            if len(x['external_key'])>200:raise ValueError('教师-课程-学期组合过长')
            return x,[]
        if data_type=='school_course':
            known={'external_key','code','name','credit','hours','weekly_hours','dept','course_version','active','deleted','extra'}
            code=_txt(mapped.get('code'),'课程编码',100)
            active=_bool(mapped.get('active',True))
            if mapped.get('deleted') not in (None,'') and _bool(mapped.get('deleted'),'删除标记'):active=False
            x={'external_key':_txt(mapped.get('external_key',''),'外部主键',128,False) or code,'code':code,
               'name':_txt(mapped.get('name'),'课程名称',300),'credit':_num(mapped.get('credit'),'学分'),
               'hours':_num(mapped.get('hours'),'总学时'),'weekly_hours':_num(mapped.get('weekly_hours'),'周学时'),
               'dept':_txt(mapped.get('dept',''),'开课单位',300,False),'course_version':_txt(mapped.get('course_version',''),'课程版本',32,False),
               'active':active}
            x['extra']={**(mapped.get('extra') if isinstance(mapped.get('extra'),dict) else {}),**{k:v for k,v in mapped.items() if k not in known}}
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

_SPAN_YEAR=re.compile(r'(\d{4})\s*[-－—~至到]\s*(\d{4})')
_START_YEAR_TERM=re.compile(r'^\s*(\d{4})\s*[-－_ ]\s*([1-4])\s*$')
UNKNOWN_YEAR='未识别学年'

def school_year_of(term_name):
    """'2025-2026学年第一学期' / '2025-2026-1' -> '2025-2026'; 超星 '2025-1' (start year + term) -> '2025-2026'."""
    text=str(term_name or '')
    m=_SPAN_YEAR.search(text)
    if m and int(m.group(2))==int(m.group(1))+1:return f'{m.group(1)}-{m.group(2)}'
    m=_START_YEAR_TERM.match(text)
    if m:return f'{m.group(1)}-{int(m.group(1))+1}'
    return None

_TERM_WORD=re.compile(r'第\s*([一二12])\s*学期|(?:上|下)学期|[-－_ ]\s*([12])\s*$')

def term_no_of(term_name):
    """'…第一学期' / '…-1' / '2025-1' -> 1; second term -> 2; otherwise None."""
    text=str(term_name or '').strip();m=_TERM_WORD.search(text)
    if not m:return None
    if m.group(0).endswith('学期') and m.group(0)[0] in '上下':return 1 if m.group(0)[0]=='上' else 2
    v=m.group(1) or m.group(2);return 1 if v in ('一','1') else 2

# Feeds the school sends in full: after a complete FULL pull, rows the school no longer
# sends were withdrawn at the source (a cancelled course) and stop counting here.
RECONCILE_TYPES={'teacher_course','online_course','school_course'}
RECONCILE_MAX_SHARE=Decimal('0.3')

def reconcile_full_pull(db,actor,data_type,batch_ids,source_total):
    """Deactivate active rows missing from one complete FULL pull; refuse suspicious wipes."""
    if data_type not in RECONCILE_TYPES:return None
    seen=set()
    for i in range(0,len(batch_ids),200):
        seen.update(db.scalars(select(InboundRow.business_key).where(InboundRow.batch_id.in_(batch_ids[i:i+200]))))
    if data_type=='school_course':model,q=SchoolCourse,select(SchoolCourse).where(SchoolCourse.active.is_(True))
    else:model,q=TeacherCourseTerm,select(TeacherCourseTerm).where(TeacherCourseTerm.active.is_(True),TeacherCourseTerm.origin==TEACHING_TYPES[data_type])
    active=db.scalars(q.with_for_update()).all()
    missing=[x for x in active if x.external_key not in seen]
    result={'data_type':data_type,'received_keys':len(seen),'active_before':len(active),'missing':len(missing),'deactivated':0}
    if not seen or not source_total:
        return {**result,'blocked':'本次全量没有收到数据，不停用任何记录'}
    if active and Decimal(len(missing))/Decimal(len(active))>RECONCILE_MAX_SHARE:
        return {**result,'blocked':'缺失比例超过 30%，疑似源端异常，未自动停用；请核对后再全量拉取','sample':[x.external_key for x in missing[:20]]}
    for x in missing:
        before=serial(x);x.active=False;x.version+=1
        audit(db,actor,data_type if data_type=='school_course' else 'teacher_course',x.id,'全量同步后源端已无此记录，停用',before=before,after=serial(x),reason='数据中台全量同步对账')
    db.flush()
    return {**result,'deactivated':len(missing),'sample':[x.external_key for x in missing[:20]]}

def _catalogue(db,codes):
    """Course code -> enabled 课程总库 row; with several versions the newest version wins."""
    best={}
    if not codes:return best
    codes=sorted(codes)
    for i in range(0,len(codes),500):
      for c in db.scalars(select(SchoolCourse).where(SchoolCourse.active.is_(True),SchoolCourse.code.in_(codes[i:i+500]))):
        if c.code not in best or (c.course_version,c.external_key)>(best[c.code].course_version,best[c.code].external_key):best[c.code]=c
    return best

def annual_teaching_credits(db,rows):
    """Sum each teacher's course credits over the two terms of a school year.

    教务 (JW) rows take credit from 课程总库 by course code unless the row carries its own.
    超星 (CX) rows use their own credit. A CX course linked to a JW course
    (extra.jw_course_code) that the same teacher already has in that school year
    counts once, through JW.
    """
    rows=list(rows)
    def link(r):return str((r.extra or {}).get('jw_course_code') or '').strip()
    catalogue=_catalogue(db,{r.course_code for r in rows if r.origin=='JW'}|{link(r) for r in rows if r.origin=='CX' and link(r)})
    jw_taught={(r.staff_no,school_year_of(r.term_name),r.course_code) for r in rows if r.origin=='JW'}
    staff=set()
    numbers=sorted({r.staff_no for r in rows})
    for i in range(0,len(numbers),500):
        staff.update(db.scalars(select(TeacherHrProfile.staff_no).where(TeacherHrProfile.active.is_(True),TeacherHrProfile.staff_no.in_(numbers[i:i+500]))))
    groups={}
    for r in sorted(rows,key=lambda r:(r.staff_no,r.term_name,r.origin,r.course_code)):
        year=school_year_of(r.term_name)
        g=groups.setdefault((r.staff_no,year or UNKNOWN_YEAR),{'staff_no':r.staff_no,'teacher_name':r.teacher_name,'user_id':r.user_id,
            'school_year':year or UNKNOWN_YEAR,'terms':set(),'jw_credit':Decimal('0'),'cx_credit':Decimal('0'),'hours':Decimal('0'),
            'courses':0,'missing_credit':[],'duplicates_skipped':0,'details':[],'in_staff_table':r.staff_no in staff})
        if r.teacher_name and not g['teacher_name']:g['teacher_name']=r.teacher_name
        if r.user_id and not g['user_id']:g['user_id']=r.user_id
        g['terms'].add(r.term_name)
        detail={'term_name':r.term_name,'term_no':term_no_of(r.term_name),'origin':r.origin,'course_code':r.course_code,'course_name':r.course_name,'credit':None,'hours':None,'credit_from':None,'counted':True}
        g['details'].append(detail)
        if r.origin=='CX' and link(r) and (r.staff_no,year,link(r)) in jw_taught:
            g['duplicates_skipped']+=1;detail.update(counted=False,linked_course_code=link(r));continue
        ref=catalogue.get(r.course_code if r.origin=='JW' else link(r))
        credit=r.credit if r.credit is not None else (ref.credit if ref else None)
        hours=r.hours if r.hours is not None else (ref.hours if ref else None)
        detail.update(credit=None if credit is None else str(Decimal(str(credit)).quantize(Decimal('0.01'))),
            hours=None if hours is None else str(Decimal(str(hours)).quantize(Decimal('0.01'))),
            credit_from=None if credit is None else ('source' if r.credit is not None else 'catalogue'))
        g['courses']+=1
        if credit is None:g['missing_credit'].append(r.course_code)
        else:g['jw_credit' if r.origin=='JW' else 'cx_credit']+=Decimal(str(credit))
        if hours is not None:g['hours']+=Decimal(str(hours))
    out=[]
    for g in groups.values():
        g['terms']=sorted(g['terms']);g['total_credit']=g['jw_credit']+g['cx_credit']
        g['missing_credit']=sorted(set(g['missing_credit']))
        for k in ('jw_credit','cx_credit','total_credit','hours'):g[k]=str(g[k].quantize(Decimal('0.01')))
        out.append(g)
    out.sort(key=lambda g:g['staff_no'])
    out.sort(key=lambda g:(g['school_year']!=UNKNOWN_YEAR,g['school_year']),reverse=True)  # newest year first, unknown last
    return out

def term_anchor(school_year,term_no):
    """Date a term counts on: term 1 of '2025-2026' -> 2025-09-01, term 2 -> 2026-03-01.

    A school assessment period that runs September to August therefore takes both
    terms of one school year; a calendar-year period takes term 2 of one year and term 1 of the next.
    A term without a recognisable number counts on the school year's first day.
    """
    if not school_year or school_year==UNKNOWN_YEAR:return None
    start=int(school_year[:4])
    return date(start+1,3,1) if term_no==2 else date(start,9,1)

def teaching_credit_facts(db,teacher,period):
    """授课学分 for one teacher in one assessment period, with the per-course evidence."""
    if not teacher or not teacher.staff_no:return Decimal('0'),{'staff_no':None,'courses':[],'excluded':[]}
    rows=db.scalars(select(TeacherCourseTerm).where(TeacherCourseTerm.staff_no==teacher.staff_no,TeacherCourseTerm.active.is_(True))
        .order_by(TeacherCourseTerm.external_key)).all()
    total=Decimal('0');courses=[];excluded=[]
    if not db.scalar(select(TeacherHrProfile.id).where(TeacherHrProfile.staff_no==teacher.staff_no,TeacherHrProfile.active.is_(True))):
        # Only teachers in the school's 教职工 table earn teaching credit.
        return total,{'staff_no':teacher.staff_no,'courses':[],'excluded':[],'not_in_staff_table':True}
    for g in annual_teaching_credits(db,rows):
        for d in g['details']:
            anchor=term_anchor(g['school_year'],d['term_no'])
            item={'school_year':g['school_year'],'term_name':d['term_name'],'origin':d['origin'],'course_code':d['course_code'],
                  'credit':d['credit'],'credit_from':d['credit_from'],'counted':d['counted'],'counts_on':anchor.isoformat() if anchor else None}
            if anchor is None or not period.start_date<=anchor<=period.end_date:
                if anchor is None:excluded.append({**item,'reason':'学期名称识别不出学年'})
                continue
            courses.append(item)
            if d['counted'] and d['credit'] is not None:total+=Decimal(d['credit'])
    return total,{'staff_no':teacher.staff_no,'courses':courses,'excluded':excluded}

def hr_freshness_errors(profile, normalized):
    if profile is None or profile.source_updated_at is None:return []
    if not normalized.get('source_updated_at'):
        return ['已有来源更新时间，缺少时间戳的数据不能覆盖正式人事信息']
    incoming=datetime.fromisoformat(normalized['source_updated_at']).astimezone(timezone.utc).replace(tzinfo=None)
    if incoming<profile.source_updated_at:return ['来源数据旧于已入库版本，拒绝倒退覆盖']
    if incoming==profile.source_updated_at and any(getattr(profile,k)!=normalized[k] for k in ('name','title','org_code','active','extra')):
        return ['相同来源更新时间对应不同内容，请联系数据责任方核对']
    return []


def resolve_hr_org(db,code,name=None):
    """Local organisation for a 教职工 所在单位: same code first, else one active org with the same name."""
    org=db.scalar(select(Org).where(Org.code==code,Org.active.is_(True))) if code else None
    if org is None and name:
        hits=db.scalars(select(Org).where(Org.name==str(name).strip(),Org.active.is_(True))).all()
        org=hits[0] if len(hits)==1 else None
    return org

def school_year_now(today=None):
    """'2025-2026' from September 2025 to August 2026."""
    d=today or date.today();y=d.year if d.month>=9 else d.year-1
    return f'{y}-{y+1}'

# 教职工 fields kept in TeacherHrProfile.extra (mapping targets in the data-hub connection).
HR_EXTRA_KEYS=('org_name','staff_type','post_name','post_type','duty','hr_status_code')
HR_PRIVATE_KEYS=('gender','edu','degree')
ROSTER_PROBLEMS={'no_account':'工号未对应本系统账号','unit_mismatch':'人事单位与本系统组织对不上',
                 'inactive_teaching':'不在职但有授课','missing_credit':'有课程缺学分'}

def _year_terms(db,numbers,school_year):
    """Active teaching rows of one school year for the given staff numbers (term names start or contain the year)."""
    if not numbers:return []
    y=school_year[:4];rows=[]
    numbers=sorted(set(numbers))
    for i in range(0,len(numbers),500):
        rows+=db.scalars(select(TeacherCourseTerm).where(TeacherCourseTerm.active.is_(True),TeacherCourseTerm.staff_no.in_(numbers[i:i+500]),
            TeacherCourseTerm.term_name.contains(school_year,autoescape=True)|TeacherCourseTerm.term_name.startswith(y+'-',autoescape=True))).all()
    return [r for r in rows if school_year_of(r.term_name)==school_year]

def staff_roster(db,profiles,*,school_year,private):
    """One row per 教职工: school fields, the local account it maps to, this year's credits and problems.

    private=False drops gender, education and degree (managers see them only when the school allows it).
    """
    profiles=list(profiles)
    orgs={o.id:o for o in db.scalars(select(Org))}
    def ancestors(org_id):
        seen=[]
        while org_id and org_id in orgs and org_id not in seen:seen.append(org_id);org_id=orgs[org_id].parent_id
        return seen
    user_ids=[p.user_id for p in profiles if p.user_id]
    users={u.id:u for u in db.scalars(select(User).where(User.id.in_(user_ids)))} if user_ids else {}
    credits={g['staff_no']:g for g in annual_teaching_credits(db,_year_terms(db,[p.staff_no for p in profiles],school_year))}
    out=[]
    for p in profiles:
        extra=p.extra or {}
        user=users.get(p.user_id)
        chain=ancestors(user.org_id) if user else []
        dept=orgs.get(chain[0]) if chain else None
        college=next((orgs[i] for i in chain if orgs[i].kind=='college'),None)
        hr_org=resolve_hr_org(db,p.org_code,extra.get('org_name'))
        c=credits.get(p.staff_no)
        problems=[]
        if not user:problems.append('no_account')
        if user and hr_org is not None and hr_org.id not in chain:problems.append('unit_mismatch')
        if not p.active and c and (c['courses'] or c['duplicates_skipped']):problems.append('inactive_teaching')
        if c and c['missing_credit']:problems.append('missing_credit')
        row={'staff_no':p.staff_no,'name':p.name,'title':p.title,'active':p.active,'user_id':p.user_id,
             'hr_org_code':p.org_code,'hr_org_name':extra.get('org_name') or (hr_org.name if hr_org else ''),
             **{k:extra.get(k) or '' for k in HR_EXTRA_KEYS if k!='org_name'},
             'org_id':dept.id if dept else None,'org_name':dept.name if dept else '','college_name':college.name if college else '',
             'school_year':school_year,'jw_credit':c['jw_credit'] if c else '0.00','cx_credit':c['cx_credit'] if c else '0.00',
             'total_credit':c['total_credit'] if c else '0.00','missing_credit':c['missing_credit'] if c else [],
             'problems':problems,'hr_updated_at':p.source_updated_at.isoformat() if p.source_updated_at else None,
             'synced_at':p.created_at.isoformat() if p.created_at else None}
        if private:row.update({k:extra.get(k) or '' for k in HR_PRIVATE_KEYS})
        out.append(row)
    return out


def _college_of(orgs,org_id):
    seen=set()
    while org_id and org_id in orgs and org_id not in seen:
        seen.add(org_id)
        if orgs[org_id].kind=='college':return orgs[org_id]
        org_id=orgs[org_id].parent_id
    return None

def credit_summary(db,profiles,*,school_year):
    """人均授课学分 of one school year over the given 教职工 (active ones only), overall and per college.

    The denominator is every active 教职工 in scope, teaching or not; teaching_staff and
    avg_teaching show the average over staff that taught at least one counted course.
    A college comes from the teacher's local account, or from the 人事单位 when no account matches.
    """
    profiles=[p for p in profiles if p.active]
    orgs={o.id:o for o in db.scalars(select(Org))}
    user_ids=[p.user_id for p in profiles if p.user_id]
    users={u.id:u for u in db.scalars(select(User).where(User.id.in_(user_ids)))} if user_ids else {}
    credits={g['staff_no']:Decimal(g['total_credit']) for g in annual_teaching_credits(db,_year_terms(db,[p.staff_no for p in profiles],school_year))}
    def bucket():return {'staff':0,'teaching_staff':0,'total_credit':Decimal('0')}
    overall=bucket();colleges={}
    for p in profiles:
        user=users.get(p.user_id)
        college=_college_of(orgs,user.org_id) if user else None
        if college is None and not user:
            hr_org=resolve_hr_org(db,p.org_code,(p.extra or {}).get('org_name'))
            college=_college_of(orgs,hr_org.id) if hr_org else None
        credit=credits.get(p.staff_no,Decimal('0'))
        targets=[overall]+([colleges.setdefault(college.id,{'id':college.id,'name':college.name,**bucket()})] if college else [])
        for t in targets:
            t['staff']+=1;t['total_credit']+=credit
            if credit>0:t['teaching_staff']+=1
    def done(t):
        q=Decimal('0.01')
        return {**t,'total_credit':str(t['total_credit'].quantize(q)),
                'avg_credit':str((t['total_credit']/t['staff']).quantize(q)) if t['staff'] else None,
                'avg_teaching':str((t['total_credit']/t['teaching_staff']).quantize(q)) if t['teaching_staff'] else None}
    return {'school_year':school_year,**done(overall),
            'colleges':sorted((done(c) for c in colleges.values()),key=lambda c:c['name'])}

# Problems the 对接与同步 page counts per data-hub table, with where the page sends the admin to fix them.
SOURCE_TABLES=('teacher_hr','school_course','teacher_course','online_course')

def source_status(db,*,school_year):
    """Per data-hub table: rows held here (active / stopped) and rows needing follow-up."""
    from sqlalchemy import func,exists,true
    def counts(model,*where):
        rows=dict(db.execute(select(model.active,func.count()).where(*where).group_by(model.active)).all())
        return {'active':rows.get(True,0),'inactive':rows.get(False,0)}
    out={}
    hr=db.scalars(select(TeacherHrProfile)).all()
    roster=staff_roster(db,hr,school_year=school_year,private=False) if hr else []
    by_problem={k:sum(k in r['problems'] for r in roster) for k in ROSTER_PROBLEMS}
    out['teacher_hr']={**counts(TeacherHrProfile),'problems':sum(bool(r['problems']) for r in roster),
        'problem_detail':by_problem,'problem_note':'没对上账号、单位对不上、不在职但有授课、缺学分（'+school_year+' 学年）'}
    out['school_course']={**counts(SchoolCourse),
        'problems':(n:=db.scalar(select(func.count()).select_from(SchoolCourse).where(SchoolCourse.active.is_(True),SchoolCourse.credit.is_(None))) or 0),
        'problem_detail':{'missing_credit':n},'problem_note':'课程总库里没有学分的课程'}
    catalogued=exists().where(SchoolCourse.active.is_(True),SchoolCourse.code==TeacherCourseTerm.course_code,SchoolCourse.credit.is_not(None))
    for data_type,origin in TEACHING_TYPES.items():
        base=(TeacherCourseTerm.origin==origin,)
        no_credit=db.scalar(select(func.count()).select_from(TeacherCourseTerm).where(*base,TeacherCourseTerm.active.is_(True),TeacherCourseTerm.credit.is_(None),
            (~catalogued) if origin=='JW' else true())) or 0
        terms=db.execute(select(TeacherCourseTerm.term_name,func.count()).where(*base,TeacherCourseTerm.active.is_(True)).group_by(TeacherCourseTerm.term_name)).all()
        unknown_year=sum(n for t,n in terms if school_year_of(t) is None)
        not_in_hr=db.scalar(select(func.count()).select_from(TeacherCourseTerm).where(*base,TeacherCourseTerm.active.is_(True),
            ~exists().where(TeacherHrProfile.staff_no==TeacherCourseTerm.staff_no,TeacherHrProfile.active.is_(True)))) or 0
        out[data_type]={**counts(TeacherCourseTerm,*base),'problems':no_credit+unknown_year+not_in_hr,
            'problem_detail':{'missing_credit':no_credit,'unknown_year':unknown_year,'not_in_staff_table':not_in_hr},
            'problem_note':'缺学分、学期名称认不出学年、工号不在在职教职工表（一条记录可能同时算多项）'}
    return out

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
        # The school's 所在单位 is usually a college or office, not a 教研室.  A unit that
        # resolves to a local 教研室 still moves the account there; any other unit is kept
        # on the profile only, so the whole staff table can come in before units are mapped.
        org=resolve_hr_org(db,normalized['org_code'],(normalized.get('extra') or {}).get('org_name'))
        if org and org.kind=='dept':
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
    db.add(batch);db.flush();seen={}
    codes=code_tables(db) if data_type=='teacher_hr' else None
    for i,raw in enumerate(records,1):
        mapped,mapping_errors=apply_mappings(connection,raw,data_type)
        status_error=derive_hr_active(db,mapped,codes) if data_type=='teacher_hr' else None
        normalized,validation_errors=validate_inbound(data_type,mapped)
        if status_error:validation_errors=[status_error,*validation_errors]
        errors=list(mapping_errors)+list(validation_errors)
        if not validation_errors:errors+=validate_inbound_relations(db,data_type,normalized)
        key=business_key(data_type,normalized)
        # Schedule rows repeat per week/class; identical teacher-course-term rows collapse.
        if key in seen and not (data_type in COLLAPSE_TYPES and seen[key]==normalized):errors.append('同批业务唯一键重复')
        if key:seen.setdefault(key,normalized)
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
    seen={}
    for row in rows:
        normalized,errors=validate_inbound(batch.data_type,row.mapped)
        if not errors:errors+=validate_inbound_relations(db,batch.data_type,normalized,lock=True)
        key=business_key(batch.data_type,normalized)
        duplicate=key in seen and batch.data_type in COLLAPSE_TYPES and seen[key]==normalized
        if not key or key!=row.business_key or (key in seen and not duplicate):errors.append('预览业务唯一键异常')
        seen.setdefault(key,normalized)
        if row.errors or errors:raise HTTPException(409,{'row':row.row_no,'errors':row.errors+errors})
    written=[];unmapped_accounts=0;revoked_sessions=0;done=set()
    for row in rows:
        normalized,errors=validate_inbound(batch.data_type,row.mapped)
        if errors:raise HTTPException(409,{'row':row.row_no,'errors':errors})
        if batch.data_type in COLLAPSE_TYPES and row.business_key in done:
            written.append({'row_no':row.row_no,'business_key':row.business_key,'duplicate':True,'unchanged':True});continue
        done.add(row.business_key)
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
            org=resolve_hr_org(db,normalized['org_code'],(normalized.get('extra') or {}).get('org_name'))
            dept=org if org and org.kind=='dept' else None
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
                auth_changed=((dept is not None and user.org_id!=dept.id) or user.active!=normalized['active'])
                user.name=normalized['name'];user.title=normalized['title'];user.active=normalized['active'];user.version+=1
                if dept is not None:user.org_id=dept.id
                if auth_changed:user.auth_version+=1;revoked_sessions+=1
            else:unmapped_accounts+=1
            if obj:
                obj.user_id=user.id if user else None;obj.name=normalized['name'];obj.title=normalized['title'];obj.org_code=normalized['org_code'];obj.active=normalized['active'];obj.extra=normalized['extra'];obj.source_updated_at=datetime.fromisoformat(normalized['source_updated_at']).replace(tzinfo=None) if normalized.get('source_updated_at') else None;obj.version+=1
            else:
                obj=TeacherHrProfile(staff_no=normalized['staff_no'],user_id=user.id if user else None,name=normalized['name'],title=normalized['title'],org_code=normalized['org_code'],active=normalized['active'],extra=normalized['extra'],source_updated_at=datetime.fromisoformat(normalized['source_updated_at']).replace(tzinfo=None) if normalized.get('source_updated_at') else None)
                db.add(obj);db.flush()
            audit(db,actor,'teacher_hr',obj.id,'确认数据中台教师人事入库',before=before,after=serial(obj),reason=reason)
            snap={'model':'teacher_hr','created':not before,'before':before,'after':serial(obj),'user_id':user.id if user else None,'user_before':user_before,'user_after':_user_state(user)}
        elif batch.data_type in TEACHING_TYPES:
            obj=db.scalar(select(TeacherCourseTerm).where(TeacherCourseTerm.external_key==normalized['external_key']).with_for_update())
            user=db.scalar(select(User).where(User.staff_no==normalized['staff_no']))
            values={k:v for k,v in normalized.items() if k not in {'external_key','origin','staff_no','course_code','term_name'}}
            values['credit']=Decimal(values['credit']) if values['credit'] is not None else None
            values['hours']=Decimal(values['hours']) if values['hours'] is not None else None
            values['user_id']=user.id if user else None;values['active']=True
            if not user:unmapped_accounts+=1
            before=serial(obj) if obj else {}
            if obj and all((Decimal(str(getattr(obj,k))) if getattr(obj,k) is not None else None)==v if k in {'credit','hours'} else getattr(obj,k)==v for k,v in values.items()):
                written.append({'row_no':row.row_no,'business_key':row.business_key,'object_id':obj.id,'unchanged':True});continue
            if obj:
                for k,v in values.items():setattr(obj,k,v)
                obj.version+=1
            else:
                obj=TeacherCourseTerm(external_key=normalized['external_key'],origin=normalized['origin'],staff_no=normalized['staff_no'],
                    course_code=normalized['course_code'],term_name=normalized['term_name'],source='学校数据中台',**values)
                db.add(obj);db.flush()
            audit(db,actor,'teacher_course',obj.id,CONFIRM_ACTIONS['teacher_course'],before=before,after=serial(obj),reason=reason)
            snap={'model':'teacher_course','created':not before,'before':before,'after':serial(obj)}
        elif batch.data_type=='school_course':
            obj=db.scalar(select(SchoolCourse).where(SchoolCourse.external_key==normalized['external_key']).with_for_update())
            values={k:v for k,v in normalized.items() if k!='external_key'}
            for k in DECIMAL_FIELDS & values.keys():values[k]=Decimal(values[k]) if values[k] is not None else None
            before=serial(obj) if obj else {}
            if obj and all(getattr(obj,k)==v for k,v in values.items()):
                written.append({'row_no':row.row_no,'business_key':row.business_key,'object_id':obj.id,'unchanged':True});continue
            if obj:
                for k,v in values.items():setattr(obj,k,v)
                obj.version+=1
            else:
                obj=SchoolCourse(external_key=normalized['external_key'],source='学校数据中台',**values);db.add(obj);db.flush()
            audit(db,actor,'school_course',obj.id,CONFIRM_ACTIONS['school_course'],before=before,after=serial(obj),reason=reason)
            snap={'model':'school_course','created':not before,'before':before,'after':serial(obj)}
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
DECIMAL_FIELDS={'credit','hours','weekly_hours'}
MASTER_MODELS={'teacher_hr':TeacherHrProfile,'training_project':TrainingProjectMaster,'course':TrainingCourseMaster,'teacher_course':TeacherCourseTerm,'school_course':SchoolCourse}
RESTORE_FIELDS={'teacher_hr':('user_id','name','title','org_code','active','extra','source_updated_at'),
    'training_project':('name','external_key','start_date','end_date','active'),'course':('name','project_code','external_key','active'),
    'teacher_course':('user_id','teacher_name','course_name','credit','hours','extra','source_stamp','active'),
    'school_course':('code','name','credit','hours','weekly_hours','dept','course_version','extra','active')}
CONFIRM_ACTIONS={'teacher_hr':'确认数据中台教师人事入库','training_project':'确认数据中台项目主数据入库','course':'确认数据中台课程主数据入库','teacher_course':'确认数据中台教师学期授课入库','school_course':'确认数据中台课程总库入库'}

def _user_state(user):
    return {k:getattr(user,k) for k in USER_FIELDS} if user else None

def _restore_value(key,value):
    if value in (None,''):return None if key in {'source_updated_at','start_date','end_date','external_key','project_code','user_id'} else value
    if key=='source_updated_at':return datetime.fromisoformat(str(value)).replace(tzinfo=None)
    if key in {'start_date','end_date'}:return date.fromisoformat(str(value))
    if key in DECIMAL_FIELDS:return Decimal(str(value))
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
