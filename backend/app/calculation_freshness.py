"""Compare only used business dependencies; timestamps and unrelated fields are not evidence changes."""
from decimal import Decimal
from sqlalchemy import select, or_, and_
from fastapi import HTTPException
from .models import Dispute, TrainingRecord
from .core import digest

SOURCE_NAMES={'hours':'授课学时','participants':'课程人次','income':'归属培训收入','qualifications':'有效资质','points':'本期积分','assessment_score':'归档考核分','teachers':'参与教师','projects':'培训项目','courses':'课程'}
RECORD_FIELDS={'hours':'hours','participants':'participants','income':'income','teachers':'teacher_id','projects':'project_code','courses':'course_code'}

def source_basis(snapshot, source):
    if 'basis_digests' in snapshot:return snapshot['basis_digests'].get(source)
    if source in RECORD_FIELDS:
        field=RECORD_FIELDS[source]
        return {r['id']:{k:r.get(k) for k in {'teacher_id','event_date','external_key','source','batch_id',field}}
                for r in snapshot.get('training_records',[])}
    if source=='qualifications':return {q['id']:q for q in snapshot.get('qualifications',[])}
    if source=='points':return {p['id']:p for p in snapshot.get('point_entries',[])}
    if source=='assessment_score':return snapshot.get('assessment_references',snapshot.get('previous_archived_assessment'))
    raise HTTPException(409,'计算依据的数据来源无法识别，请先核实规则')

def source_changes(previous, current, components):
    items=[]
    for source in dict.fromkeys(c['source'] for c in components):
        before=source_basis(previous,source);after=source_basis(current,source)
        # Numeric serialization (10 vs 10.00) is stable for database snapshots.
        if digest(before)==digest(after) and all(previous.get('period',{}).get(k)==current.get('period',{}).get(k) for k in ('start_date','end_date')):
            continue
        details=[]
        if source in RECORD_FIELDS and isinstance(before,dict) and isinstance(after,dict):
            names={r['id']:f"{r['event_date']} · {r.get('course') or r.get('project') or '培训记录'}" for snap in (previous,current) for r in snap.get('training_records',[])}
            field=RECORD_FIELDS[source]
            for ident in sorted(before.keys()|after.keys()):
                if before.get(ident)!=after.get(ident):
                    details.append({'record_id':ident,'name':names.get(ident,'培训记录'),'before':str(before[ident].get(field)) if ident in before else '未纳入','after':str(after[ident].get(field)) if ident in after else '已移出'})
        items.append({'source':source,'label':SOURCE_NAMES[source],
            'before':format(Decimal(str(previous.get('values',{}).get(source,0))),'.2f'),
            'after':format(Decimal(str(current.get('values',{}).get(source,0))),'.2f'),
            'details':details[:20],'detail_count':len(details)})
    return {'changed':bool(items),'items':items}

def require_current_sources(changes):
    if changes['changed']:raise HTTPException(409,'计算依据已变化，请先退回或重新取数计算，再确认及归档')

def relevant_disputes(teacher_id,period,record_ids=()):
    records=select(TrainingRecord.id).where(TrainingRecord.teacher_id==teacher_id,
        or_(and_(TrainingRecord.event_date>=period.start_date,TrainingRecord.event_date<=period.end_date),TrainingRecord.id.in_(record_ids)))
    return select(Dispute).where(Dispute.teacher_id==teacher_id,Dispute.state=='OPEN',
        or_(Dispute.period_id==period.id,and_(Dispute.period_id.is_(None),Dispute.object_type=='record',Dispute.object_id.in_(records))))
