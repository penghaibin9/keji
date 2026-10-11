"""Synthetic contract checks only; no school credentials or external calls."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select, func

from app.models import Audit, Connection, Org, TrainingRecord
from app.reference_data import InboundRow, confirm_inbound, preview_inbound, validate_inbound


def sample():
    return dict(staff_no='t1', external_key='mock-contract-1', event_date='2026-09-01',
                project_code='P1', project='模拟项目', course_code='C1', course='模拟课程',
                class_code='CL1', class_name='模拟班级', hours='2.00', income='100.00', participants=10)


@pytest.mark.parametrize('data_type', ['training_income', 'course_participants'])
def test_missing_fields_are_locatable_without_guessing_zero(data_type):
    payload=sample(); del payload['income']; del payload['participants']
    normalized, errors=validate_inbound(data_type, payload)
    assert normalized == {}
    assert '培训收入（income）缺失' in errors
    assert '课程人次（participants）缺失' in errors
    assert any('禁止把缺失值猜为零' in error for error in errors)


@pytest.mark.parametrize('field,label,value', [
    ('income', '培训收入', 'SYNTHETIC_PRIVATE_VALUE'),
    ('participants', '课程人次', 1.5),
    ('hours', '学时', 'NaN'),
    ('event_date', '业务日期', 'invalid-date'),
])
def test_invalid_field_is_named_without_echoing_payload(field,label,value):
    payload=sample(); payload[field]=value
    normalized,errors=validate_inbound('training_income',payload)
    assert normalized == {}
    assert f'{label}（{field}）格式或取值不符合台账规范' in errors
    assert 'SYNTHETIC_PRIVATE_VALUE' not in str(errors)


def test_unknown_field_name_and_value_are_not_echoed():
    payload=sample(); payload['SYNTHETIC_PRIVATE_FIELD']='SYNTHETIC_PRIVATE_VALUE'
    _,errors=validate_inbound('training_income',payload)
    assert '包含未支持的字段，请核对生效字段映射' in errors
    assert 'SYNTHETIC_PRIVATE' not in str(errors)


def test_valid_full_record_retains_trusted_source():
    payload=sample(); payload.update(source='人工伪装来源',teacher_id='t3')
    normalized,errors=validate_inbound('training_income',payload)
    assert errors == []
    assert normalized['source']=='学校数据中台'
    assert normalized['staff_no']=='t1' and 'teacher_id' not in normalized
    assert normalized['income']=='100.00' and normalized['participants']==10


def test_failed_mock_preview_is_audited_and_cannot_write_formal_records(db):
    payload=sample(); del payload['income']
    connection=Connection(code='middle',name='隔离模拟中台', mappings=[
        dict(source=key,target=key,transform='text',required=False)
        for key in payload
    ])
    db.add(connection); db.flush()
    actor=SimpleNamespace(id='admin',name='隔离管理员',org=db.get(Org,'school'),
                          request_id='mock-contract-test',require_admin=lambda:None)
    before=db.scalar(select(func.count()).select_from(TrainingRecord))
    batch=preview_inbound(db,actor,connection,'training_income',[payload],source_label='隔离模拟报文，非学校联调')
    row=db.scalar(select(InboundRow).where(InboundRow.batch_id==batch.id))
    assert '培训收入（income）缺失' in row.errors
    assert batch.errors==1 and batch.state=='PREVIEW'
    audit=db.scalar(select(Audit).where(Audit.object_id==batch.id))
    assert audit.after['errors']==1 and audit.after['rows']==1
    with pytest.raises(HTTPException) as blocked:
        confirm_inbound(db,actor,batch,batch.version,'隔离模拟确认')
    assert blocked.value.status_code==409
    assert db.scalar(select(func.count()).select_from(TrainingRecord))==before
