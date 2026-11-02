"""Pure normalized-contract regression; no database, network or credentials."""
import pytest

from app.integrations import safe_acknowledgement


@pytest.mark.parametrize('value',[None,True,False,1.25,{'id':'mock'},['mock']])
def test_non_identifier_receipt_is_not_fabricated(value):
    result=safe_acknowledgement({'accepted':True,'receipt_id':value})
    assert 'receipt_id' not in result
    assert result['accepted'] is True


@pytest.mark.parametrize('value,expected',[('MOCK-123','MOCK-123'),(0,'0'),(123,'123'),('None','None')])
def test_string_or_integer_receipt_is_preserved(value,expected):
    assert safe_acknowledgement({'accepted':True,'receipt_id':value})['receipt_id']==expected


@pytest.mark.parametrize('value',['R'*129,'','not an identifier'])
def test_existing_length_and_character_filter_remains(value):
    assert 'receipt_id' not in safe_acknowledgement({'accepted':True,'receipt_id':value})


@pytest.mark.parametrize('accepted',[False,'true',1,None])
def test_receipt_does_not_substitute_for_positive_ack(accepted):
    with pytest.raises(RuntimeError,match='UPSTREAM_NOT_ACKNOWLEDGED'):
        safe_acknowledgement({'accepted':accepted,'receipt_id':'MOCK-123'})
