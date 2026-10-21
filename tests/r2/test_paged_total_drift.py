"""A source total that moves while a long FULL pull runs is drift, not a failed run; reconcile withdraws nothing."""
import pytest
from sqlalchemy import select, func

from app.models import Task
from app.inbound_sync import process_pull_task_once
from app.reference_data import TrainingProjectMaster, InboundBatch, confirm_inbound
from app.paged_inbound import lock_pending_task, resume_confirmed_task
from test_integration_closeout import SyntheticHub, prepare_run, actor


class GrowingHub(SyntheticHub):
    """The school adds rows after the first page was read: later pages report a larger total."""
    def __init__(self, start, grown):
        super().__init__(start)
        self.grown = grown
        self.pages = 0
    def _request_json(self, **kwargs):
        self.pages += 1
        if self.pages == 2:
            self.total = self.grown
        return super()._request_json(**kwargs)


def drain(app, ident, registry, automatic):
    for _ in range(60):
        with app.state.sessions.begin() as db:
            task = db.get(Task, ident)
            if task.state in ('DONE', 'FAILED', 'BLOCKED'):
                return task.state, dict(task.result or {}), task.error
            process_pull_task_once(db, task, registry)
            if not automatic and task.state == 'WAITING_CONFIRMATION':
                batch = db.get(InboundBatch, task.result['pending']['batch_id'])
                pending = lock_pending_task(db, batch)
                confirm_inbound(db, actor(db), batch, batch.version, '隔离分页确认')
                resume_confirmed_task(db, pending, batch)
    raise AssertionError('run did not finish')


@pytest.mark.parametrize('automatic', [True, False])
def test_total_growing_mid_pull_completes_without_reconcile(app2, automatic):
    hub = GrowingHub(1500, 1510)
    registry, ident = prepare_run(app2, hub, automatic)
    state, result, error = drain(app2, ident, registry, automatic)
    assert state == 'DONE', error
    assert result['total_drift'] is True
    assert result['committed_records'] == 1510
    assert 'skipped' in result['reconcile']
    with app2.state.sessions.begin() as db:
        assert db.scalar(select(func.count()).select_from(TrainingProjectMaster)) == 1510


def test_stable_total_still_reconciles(app2):
    registry, ident = prepare_run(app2, SyntheticHub(1500), True)
    state, result, error = drain(app2, ident, registry, True)
    assert state == 'DONE', error
    assert not result.get('total_drift')
    assert 'skipped' not in (result.get('reconcile') or {})
