"""Normalized receipt IDs must not be fabricated by truncating upstream data."""
import pytest
from sqlalchemy import select

from app.adapters.contracts import AdapterContractError
from app.adapters.province import ConfigurableProvinceAdapter
from app.integrations import AdapterRegistry, enqueue_sync, process_sync_task_once, task_sync_items, SyncCallLog
from app.models import Connection
from test_integration_closeout import actor


def config():
    return {'endpoint':'https://synthetic.invalid/api','retry_count':3,'adapter':{
        'data_types':{'training_project':{
            'request':{'method':'POST','path':'projects','body':'${payload}','auth':{'mode':'none'}},
            'response':{'accepted_path':'accepted','accepted_values':[True],'receipt_id_path':'receipt'}
        }}}}


class ReceiptAdapter(ConfigurableProvinceAdapter):
    def __init__(self,receipt):self.receipt=receipt
    def _request_json(self,**kwargs):return {'accepted':True,'receipt':self.receipt}


@pytest.mark.parametrize('receipt',['R'*129,{'id':'MOCK-1'},['MOCK-1'],True])
def test_invalid_receipt_is_rejected_without_truncation_or_stringification(receipt):
    with pytest.raises(AdapterContractError) as error:
        ReceiptAdapter(receipt).send(data_type='training_project',payload={'code':'MOCK'},
            idempotency_key='mock-idem',config=config(),credential='TEST_ONLY',timeout_seconds=10)
    assert error.value.code=='PROVINCE_RECEIPT_INVALID'


@pytest.mark.parametrize('receipt,expected',[('R'*128,'R'*128),(123,'123'),(0,'0'),(None,None),('',None)])
def test_valid_or_absent_optional_receipt_preserves_identity(receipt,expected):
    response=ReceiptAdapter(receipt).send(data_type='training_project',payload={'code':'MOCK'},
        idempotency_key='mock-idem',config=config(),credential='TEST_ONLY',timeout_seconds=10)
    assert response.get('receipt_id')==expected


def test_invalid_receipt_enters_retry_and_cannot_create_success_log(app2):
    cfg=config(); adapter=ReceiptAdapter('R'*129)
    class WorkerAdapter:
        def send(self,**kwargs):
            return adapter.send(**kwargs,config=cfg,credential='TEST_ONLY',timeout_seconds=10)
    registry=AdapterRegistry();registry.register_for_test('province',WorkerAdapter())
    with app2.state.sessions.begin() as db:
        connection=db.scalar(select(Connection).where(Connection.code=='province'))
        connection.state='CONNECTED';connection.config=cfg
        connection.mappings=[{'source':'code','target':'code','required':True,'transform':'text'}]
        task=enqueue_sync(db,actor(db),connection,'training_project',
            [{'business_key':'MOCK-1','code':'MOCK-1'}],'隔离模拟回执')
        process_sync_task_once(db,task,registry)
        item=task_sync_items(db,task)[0]
        log=db.scalar(select(SyncCallLog).where(SyncCallLog.item_id==item.id))
        assert task.state=='RETRY' and item.state=='RETRY'
        assert log.result=='ERROR' and not log.acknowledged
        assert log.message=='PROVINCE_RECEIPT_INVALID'
        assert 'receipt_id' not in item.result
        assert item.error=='PROVINCE_RECEIPT_INVALID'
