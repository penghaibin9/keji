"""4.3 field-mapping transform "mask" applies during inbound preview and is what gets stored."""
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.integrations import convert,normalize_mapping
from app.reference_data import TeacherHrProfile,InboundRow
from conftest import auth,post
from test_r4_internal_closeout import configure_middle

REASON={'reason':'入站脱敏测试','basis':'合成隔离数据'}
ID_CARD='430102199001011234'


def test_mask_transform_contract():
    assert convert('13812345678','mask:3:4')=='138****5678'
    assert convert(ID_CARD,'mask:3:4')=='430***********1234'
    masked=convert('ABCDEFGH','mask');assert masked=='AB****GH'
    assert convert('','mask')=='' and convert(None,'mask') is None
    assert normalize_mapping({'source':'a','target':'b','transform':'mask:2:2'})['transform']=='mask:2:2'
    for bad in ('mask:9:9','mask:1','masked','mask:a:b'):
        with pytest.raises(HTTPException):normalize_mapping({'source':'a','target':'b','transform':bad})


def test_masked_field_is_masked_in_preview_and_storage(client2,app2):
    c=client2;auth(c,'schooladmin')
    conn=configure_middle(c,[
      {'source':'staff','target':'staff_no','transform':'text','required':True,'default':None},
      {'source':'name','target':'name','transform':'text','required':True,'default':None},
      {'source':'org','target':'org_code','transform':'text','required':True,'default':None},
      {'source':'idCard','target':'id_card','transform':'mask:3:4','required':False,'default':None},
      {'source':'phone','target':'phone','transform':'mask','required':False,'default':None},
    ])
    p=post(c,'/api/connections/'+conn['id']+'/inbound/preview',{'data_type':'teacher_hr','records':[{'staff':'J001','name':'测试教师一','org':'dept1','idCard':ID_CARD,'phone':'13812345678'}],'source_label':'脱敏样本',**REASON})
    assert p.status_code==200,p.text;batch=p.json();assert batch['errors']==0,batch
    detail=c.get('/api/inbound-batches/'+batch['id']).json()
    mapped=detail['rows']['items'][0]['mapped']
    assert mapped['extra']['id_card']=='430***********1234' and ID_CARD not in str(mapped)
    assert mapped['extra']['phone']!='13812345678' and '*' in mapped['extra']['phone']
    raw=detail['rows']['items'][0]['raw'];assert raw['idCard']=='430***********1234' and raw['staff']=='J001'
    r=post(c,'/api/inbound-batches/'+batch['id']+'/confirm',{'expected_version':batch['version'],**REASON});assert r.status_code==200,r.text
    with Session(app2.state.engine) as db:
        profile=db.scalar(select(TeacherHrProfile).where(TeacherHrProfile.staff_no=='J001'))
        assert profile.extra['id_card']=='430***********1234'
        assert ID_CARD not in str(db.execute(select(InboundRow.mapped,InboundRow.raw).where(InboundRow.batch_id==batch['id'])).all())
