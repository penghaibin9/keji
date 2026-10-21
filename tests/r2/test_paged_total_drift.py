"""A source total that moves while a long FULL pull runs is drift, not a failed run; reconcile withdraws nothing."""
import pytest
from sqlalchemy import select, func

from app.models import Connection, Task
from app.inbound_sync import process_pull_task_once
from app.reference_data import TrainingProjectMaster, SchoolCourse, InboundBatch, InboundRow, confirm_inbound
from app.paged_inbound import lock_pending_task, resume_confirmed_task, _reconcile
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
@pytest.mark.parametrize('changed_total', [1510, 1490, 100])
def test_total_changing_mid_pull_completes_without_reconcile(app2, automatic, changed_total):
    hub = GrowingHub(1500, changed_total)
    registry, ident = prepare_run(app2, hub, automatic)
    state, result, error = drain(app2, ident, registry, automatic)
    assert state == 'DONE', error
    assert result['total_drift'] is True
    # A shrinking source cannot undo the 250 rows already confirmed on the first page.
    expected = max(250, changed_total)
    assert result['committed_records'] == expected
    assert 'skipped' in result['reconcile']
    with app2.state.sessions.begin() as db:
        assert db.scalar(select(func.count()).select_from(TrainingProjectMaster)) == expected


def test_stable_total_still_reconciles(app2):
    registry, ident = prepare_run(app2, SyntheticHub(1500), True)
    state, result, error = drain(app2, ident, registry, True)
    assert state == 'DONE', error
    assert not result.get('total_drift')
    assert 'skipped' not in (result.get('reconcile') or {})


@pytest.mark.parametrize('drift', [True, False])
def test_only_complete_stable_pull_can_deactivate_missing_course(app2, drift):
    with app2.state.sessions.begin() as db:
        connection = db.scalar(select(Connection).where(Connection.code == 'middle'))
        batch = InboundBatch(connection_id=connection.id, data_type='school_course',
                             owner_id='schooladmin', state='COMMITTED', total=3, errors=0)
        db.add(batch)
        db.flush()
        for i in range(4):
            db.add(SchoolCourse(external_key=f'K{i}', code=f'K{i}', name=f'合成课程{i}'))
            if i < 3:
                db.add(InboundRow(batch_id=batch.id, row_no=i, business_key=f'K{i}',
                                  raw={}, mapped={}, errors=[]))
        db.flush()
        task = Task(state='DONE', payload={'mode': 'FULL', 'data_type': 'school_course'},
                    result={'committed': True, 'source_total': 3, 'committed_records': 3,
                            'total_drift': drift, 'chunks': [{'batch_id': batch.id}]})
        _reconcile(db, task, actor(db))
        db.flush()
        missing = db.scalar(select(SchoolCourse).where(SchoolCourse.external_key == 'K3'))
        assert missing.active is drift
        if drift:
            assert 'skipped' in task.result['reconcile']
        else:
            assert task.result['reconcile']['deactivated'] == 1
