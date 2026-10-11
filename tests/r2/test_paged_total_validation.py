"""Reject a source-total contradiction before preview or formal page writes."""
import pytest
from sqlalchemy import select, func

from app.models import Task, TaskAttempt
from app.inbound_sync import process_pull_task_once
from app.reference_data import TrainingProjectMaster, InboundBatch, confirm_inbound
from app.paged_inbound import lock_pending_task, resume_confirmed_task
from test_integration_closeout import SyntheticHub, prepare_run, actor


class ContradictoryTotalHub(SyntheticHub):
    def __init__(self,total):
        super().__init__(750)
        self.declared_total=total
    def _request_json(self,**kwargs):
        response=super()._request_json(**kwargs)
        response['total']=self.declared_total
        return response


@pytest.mark.parametrize('automatic',[True,False])
@pytest.mark.parametrize('declared_total,prior_rows',[(100,0),(300,250)])
def test_intermediate_page_exceeding_total_is_not_staged_or_written(app2,automatic,declared_total,prior_rows):
    registry,ident=prepare_run(app2,ContradictoryTotalHub(declared_total),automatic)
    if prior_rows:
        with app2.state.sessions.begin() as db:
            task=db.get(Task,ident)
            process_pull_task_once(db,task,registry)
            if not automatic:
                batch=db.get(InboundBatch,task.result['pending']['batch_id'])
                pending=lock_pending_task(db,batch)
                confirm_inbound(db,actor(db),batch,batch.version,'隔离第一页确认')
                resume_confirmed_task(db,pending,batch)
            assert task.state=='PENDING'
            assert task.result['committed_records']==250
    with app2.state.sessions.begin() as db:
        task=db.get(Task,ident)
        process_pull_task_once(db,task,registry)
        assert task.state=='RETRY'
        assert task.error=='PULL_RESPONSE_TOTAL_MISMATCH'
        assert task.result.get('committed_records',0)==prior_rows
        assert db.scalar(select(func.count()).select_from(TrainingProjectMaster))==prior_rows
        assert db.scalar(select(func.count()).select_from(InboundBatch))==(1 if prior_rows else 0)
        attempt=db.scalar(select(TaskAttempt).where(TaskAttempt.task_id==ident).order_by(TaskAttempt.attempt.desc()))
        assert attempt.message=='PULL_RESPONSE_TOTAL_MISMATCH'
