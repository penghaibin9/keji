"""Synthetic upstream only: no school service, credentials or production data."""
from datetime import timedelta
import pytest
from sqlalchemy import select, func
from app.core import Actor
from app.models import Connection, User, Role, Org, Task, utcnow, AuthSession, Setting
from app.integrations import AdapterRegistry, probe_connection, activate_connection, live_connection
from app.inbound_sync import IntegrationSchedule, create_pull_task, process_pull_task_once
from app.reference_data import TrainingProjectMaster, InboundBatch, confirm_inbound
from app.paged_inbound import lock_pending_task, resume_confirmed_task
from app.adapters.datahub import ConfigurableDataHubAdapter
from app.adapters.contracts import AdapterContractError
from app.sso_identity import preview_identity


def actor(db):
    return Actor(db, db.get(User, 'schooladmin'), db.get(Role, 'role-school'), db.get(Org, 'school'))


def page_config(size=250):
    return {'adapter': {'data_types': {'training_project': {
        'request': {'method': 'GET', 'path': '/projects', 'auth': {'mode': 'none'}},
        'pagination': {'mode': 'page', 'page_size': size, 'max_pages': 100, 'start_page': 1},
        'response': {'records_path': 'items', 'has_more_path': 'more', 'total_path': 'total'},
    }}}}


class SyntheticHub(ConfigurableDataHubAdapter):
    def __init__(self, total, fail_page=None):
        self.total, self.fail_page = total, fail_page
        self.config = page_config()
        self.calls = []

    def _request_json(self, *, context, **kwargs):
        self.calls.append(context['page'])
        if self.fail_page == context['page']:
            self.fail_page = None
            raise AdapterContractError('UPSTREAM_TIMEOUT')
        start = context['offset']
        end = min(start + context['limit'], self.total)
        return {'items': [{'code': 'IMPORT-%06d' % n, 'name': '合成项目%d' % n}
                          for n in range(start, end)], 'more': end < self.total, 'total': self.total}

    def pull_chunk(self, **kwargs):
        return super().pull_chunk(config=self.config, credential='TEST_ONLY', timeout_seconds=10, **kwargs)


@pytest.mark.parametrize('total', [0, 999, 1000, 1001, 2500])
def test_all_pages_are_returned_without_truncation(total):
    hub = SyntheticHub(total)
    checkpoint, records = None, []
    for _ in range(20):
        result = hub.pull_chunk(data_type='training_project', mode='FULL', cursor=None,
                                limit=1000, checkpoint=checkpoint)
        records.extend(result['records'])
        if not result['has_more']:
            break
        checkpoint = result['checkpoint']
    assert len(records) == total
    assert len({row['code'] for row in records}) == total


def prepare_run(app, hub, automatic):
    registry = AdapterRegistry()
    registry.register_for_test('middle', hub)
    with app.state.sessions.begin() as db:
        connection = db.scalar(select(Connection).where(Connection.code == 'middle'))
        connection.config = hub.config
        connection.mappings = [{'data_type': 'training_project', 'source': key,
            'target': key, 'required': True, 'transform': 'text'} for key in ('code', 'name')]
        connection.state = 'CONNECTED'
        schedule = None
        if automatic:
            schedule = IntegrationSchedule(connection_id=connection.id, data_type='training_project',
                frequency_minutes=30, auto_commit=True, active=True, approved_by='schooladmin')
            db.add(schedule)
            db.flush()
        task = create_pull_task(db, actor(db), connection, 'training_project', 'FULL', '合成验收', schedule=schedule)
        return registry, task.id


def test_1001_rows_resume_after_interrupted_second_page(app2):
    hub = SyntheticHub(1001, fail_page=2)
    registry, ident = prepare_run(app2, hub, True)
    for iteration in range(12):
        with app2.state.sessions.begin() as db:
            task = db.get(Task, ident)
            process_pull_task_once(db, task, registry)
            if iteration == 1:
                assert task.state == 'RETRY'
                assert task.result['committed_records'] == 250
                assert task.result['checkpoint']['page'] == 2
            if task.state == 'DONE':
                break
    with app2.state.sessions() as db:
        task = db.get(Task, ident)
        assert task.state == 'DONE', task.error
        assert task.result['committed_records'] == 1001
        assert len(task.result['chunks']) == 5
        assert db.scalar(select(func.count()).select_from(TrainingProjectMaster)) == 1001
        assert hub.calls == [1, 2, 2, 3, 4, 5]
        from app.integration_status import latest_task_status
        summary=latest_task_status(db,db.get(Connection,task.payload['connection_id']))
        assert summary['success_count']==1001
        assert summary['display_state']=='COMMITTED'


def test_manual_confirmation_controls_each_page(app2):
    registry, ident = prepare_run(app2, SyntheticHub(251), False)
    for expected in (250, 251):
        with app2.state.sessions.begin() as db:
            task = db.get(Task, ident)
            process_pull_task_once(db, task, registry)
            assert task.state == 'WAITING_CONFIRMATION'
            before = db.scalar(select(func.count()).select_from(TrainingProjectMaster))
            assert before == (0 if expected == 250 else 250)
            batch = db.get(InboundBatch, task.result['pending']['batch_id'])
            locked = lock_pending_task(db, batch)
            confirm_inbound(db, actor(db), batch, batch.version, '人工确认合成批次')
            resume_confirmed_task(db, locked, batch)
            assert task.result['committed_records'] == expected
    with app2.state.sessions() as db:
        assert db.get(Task, ident).state == 'DONE'


def test_identity_preview_uses_login_root_roles_and_active_rules(app2):
    config = {'endpoint': 'https://synthetic.invalid', 'adapter': {
        'identity_root': 'data', 'identity_fields': {'stable_id': 'id', 'account': 'account',
            'name': 'name', 'org_code': 'org', 'roles': 'roles', 'active': 'status'},
        'org_map': {'upstream-dept': 'dept1'}, 'roles_delimiter': ';',
        'active_true_values': ['ACTIVE'], 'active_false_values': ['DISABLED']}}
    payload = {'data': {'id': 'subject-1', 'account': 'teacher', 'name': '合成教师',
        'org': 'upstream-dept', 'roles': 'teacher;staff', 'status': 'ACTIVE'}}
    with app2.state.sessions.begin() as db:
        session_count = db.scalar(select(func.count()).select_from(AuthSession))
        result = preview_identity(db, config, payload)
        assert result['can_login'] is True, result
        assert result['mapped']['org_code'] == 'dept1'
        assert result['mapped']['external_roles'] == ['teacher', 'staff']
        assert result['binding']['scope'] == '仅本人'
        assert db.scalar(select(func.count()).select_from(AuthSession)) == session_count
        assert not db.scalar(select(Setting).where(Setting.key.like('ssoid:%')))
        payload['data']['status'] = 'DISABLED'
        assert preview_identity(db, config, payload)['can_login'] is False


class SyntheticProbe:
    adapter_id = 'synthetic.test.probe'
    def probe(self, **kwargs):
        return {'authenticated': True, 'tls_verified': True, 'protocol_verified': True}
    def pull(self, **kwargs):
        return {'records': []}


def test_published_authorization_survives_probe_ttl_but_not_key_rotation(app2, monkeypatch):
    registry = AdapterRegistry()
    registry.production = True
    monkeypatch.setenv('ND_CLOSEOUT_TEST_SECRET', 'synthetic-local-only')
    registry.register_production('middle', SyntheticProbe(), endpoint='https://synthetic.invalid',
                                 credential_env='ND_CLOSEOUT_TEST_SECRET')
    with app2.state.sessions.begin() as db:
        connection = db.scalar(select(Connection).where(Connection.code == 'middle'))
        connection.config = {'endpoint': 'https://synthetic.invalid', 'secret_env': 'ND_CLOSEOUT_TEST_SECRET'}
        check = probe_connection(db, actor(db), connection, registry, production=True)
        activate_connection(db, actor(db), connection, check.id, registry)
        check.expires_at = utcnow() - timedelta(days=2)
        assert live_connection(db, connection, registry)
        monkeypatch.setenv('ND_CLOSEOUT_TEST_SECRET', 'synthetic-rotated')
        assert not live_connection(db, connection, registry)


def test_missing_end_marker_is_not_silently_treated_as_complete():
    hub = SyntheticHub(1001)
    hub.config['adapter']['data_types']['training_project']['response'].pop('has_more_path')
    with pytest.raises(AdapterContractError) as error:
        hub.pull_chunk(data_type='training_project', mode='FULL', cursor=None, limit=1000)
    assert error.value.code == 'PULL_COMPLETENESS_RULE_REQUIRED'
    assert hub.calls == []


def test_repeated_page_preserves_prior_commit_and_blocks_new_scheduled_run(app2):
    from app.inbound_sync import enqueue_due_schedules
    class RepeatedHub(SyntheticHub):
        def _request_json(self, *, context, **kwargs):
            response = super()._request_json(context=context, **kwargs)
            if context['page'] == 2:
                response['items'][0]['code'] = 'IMPORT-000000'
            return response
    registry, ident = prepare_run(app2, RepeatedHub(251), True)
    for _ in range(2):
        with app2.state.sessions.begin() as db:
            process_pull_task_once(db, db.get(Task, ident), registry)
    with app2.state.sessions.begin() as db:
        task = db.get(Task, ident)
        assert task.state == 'FAILED'
        assert task.result['committed_records'] == 250
        assert db.scalar(select(func.count()).select_from(TrainingProjectMaster)) == 250
        schedule = db.scalar(select(IntegrationSchedule))
        schedule.next_at = utcnow()
        assert enqueue_due_schedules(db, registry=registry) == []
        assert db.scalar(select(func.count()).select_from(Task).where(Task.kind == 'inbound_pull')) == 1


def test_transport_diagnostics_classify_failures_without_raw_details():
    import socket
    import ssl
    from urllib.error import URLError
    from app.adapters.http_transport import _failure_code
    from app.integration_diagnostics import diagnostic
    for error, code in [(socket.gaierror('private-hostname'), 'UPSTREAM_DNS_FAILED'),
                        (TimeoutError('private-token'), 'UPSTREAM_TIMEOUT'),
                        (ssl.SSLCertVerificationError('private-certificate'), 'UPSTREAM_TLS_VERIFY_FAILED')]:
        assert _failure_code(URLError(error)) == code
        result = diagnostic(code)
        assert 'private-' not in str(result)
        assert result['remedy'] and result['trace_id']
