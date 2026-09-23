"""HTTP regression tests for the implementation center; synthetic identities only."""
import io
import json
import zipfile
from datetime import timedelta
from urllib.parse import urlsplit, parse_qs
import pytest
from sqlalchemy import select, func
from app.models import Connection, Setting, AuthSession, User, utcnow
from app.integrations import ADAPTERS, ConnectionCheck
from app.inbound_sync import IntegrationSchedule
from app.adapters.contracts import AdapterContractError
from conftest import auth, post, put

REASON = {'reason': '独立合成实施验收', 'basis': '接口收口专项'}


def connection_id(client, code='sso'):
    return next(x['connection']['id'] for x in client.get('/api/connections/catalog').json()['items']
                if x['connection']['code'] == code)


def sso_config():
    return {'endpoint': 'https://synthetic.invalid', 'owner': '合成学校接口负责人',
        'secret_env': 'ND_CLOSEOUT_TRIAL', 'adapter': {'protocol': 'cas', 'login_path': '/login',
            'validate_path': '/serviceValidate', 'identity_fields': {'account': 'account',
            'name': 'name', 'active': 'active', 'org_code': 'org', 'stable_id': 'id'}}}


def make_draft(client, ident, config=None):
    active = client.get('/api/connections/'+ident+'/draft').json()
    response = put(client, '/api/connections/'+ident+'/draft', {
        **REASON, 'expected_version': active['active_version'], 'expected_draft_version': active['draft_version'],
        'config': config or sso_config(), 'mappings': []})
    assert response.status_code == 200, response.text
    return {'expected_version': active['active_version'], 'draft_version': response.json()['draft_version'], **REASON}


def test_draft_save_preserves_live_connection_and_schedules(client2, app2):
    auth(client2, 'schooladmin')
    ident = connection_id(client2, 'middle')
    with app2.state.sessions.begin() as db:
        obj = db.get(Connection, ident)
        obj.state = 'CONNECTED'
        db.add(IntegrationSchedule(connection_id=ident, data_type='training_project',
            frequency_minutes=30, auto_commit=True, active=True, approved_by='schooladmin'))
    action = make_draft(client2, ident, {'endpoint': 'https://synthetic.invalid', 'owner': '学校资料'})
    with app2.state.sessions() as db:
        assert db.get(Connection, ident).state == 'CONNECTED'
        assert db.get(Connection, ident).config == {}
        assert db.scalar(select(IntegrationSchedule)).active
        assert db.get(Connection, ident).version == action['expected_version']
    conflict = put(client2, '/api/connections/'+ident+'/draft', {**REASON,
        'expected_version': action['expected_version'], 'expected_draft_version': 0, 'config': {}, 'mappings': []})
    assert conflict.status_code == 409


class TrialAdapter:
    adapter_id = 'synthetic.trial.adapter'
    def probe(self, **kwargs):
        return {'authenticated': True, 'tls_verified': True, 'protocol_verified': True}
    def build_login_url(self, *, state, **kwargs):
        return {'redirect_url': 'https://synthetic.invalid/login?state='+state}
    def complete_login(self, **kwargs):
        return {'stable_id': 'synthetic-subject', 'account': 'teacher', 'staff_no': 'J001',
                'name': '合成教师', 'org_code': 'dept1', 'external_roles': ['external_admin'], 'active': True}


def setup_trial(client, app, monkeypatch):
    monkeypatch.setenv('ND_CLOSEOUT_TRIAL', 'synthetic-test-credential-only')
    monkeypatch.setattr(ADAPTERS, '_items', {'sso': TrialAdapter()})
    monkeypatch.setattr(ADAPTERS, '_test_codes', {'sso'})
    monkeypatch.setattr(ADAPTERS, 'production', False)
    auth(client, 'schooladmin')
    ident = connection_id(client)
    action = make_draft(client, ident)
    response = post(client, '/api/connections/'+ident+'/draft/login-test', action)
    assert response.status_code == 200, response.text
    state = parse_qs(urlsplit(response.json()['redirect_url']).query)['state'][0]
    return ident, action, state


def test_browser_trial_does_not_switch_session_or_bind_account(client2, app2, monkeypatch):
    ident, action, state = setup_trial(client2, app2, monkeypatch)
    before = client2.cookies.get(app2.state.settings.cookie_name)
    response = client2.get('/api/auth/sso/implementation-callback', params={'state': state, 'ticket': 'ST-synthetic'}, follow_redirects=False)
    assert response.status_code == 303, response.text
    assert client2.cookies.get(app2.state.settings.cookie_name) == before
    assert client2.get('/api/auth/me').json()['user']['id'] == 'schooladmin'
    with app2.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(AuthSession)) == 1
        assert not db.scalar(select(Setting).where(Setting.key.like('ssoid:%')))
        row = db.get(Setting, 'integration.draft:'+ident)
        proof = db.get(ConnectionCheck, row.value['check_id'])
        assert proof.passed and proof.mode == 'TEST_ONLY'
        assert proof.receipt['preview']['binding']['role_kind'] == 'teacher'
    published = post(client2, '/api/connections/'+ident+'/draft/publish', {**action, 'confirm_schedule_pause': True})
    assert published.status_code == 409
    replay = client2.get('/api/auth/sso/implementation-callback', params={'state': state, 'ticket': 'ST-synthetic'})
    assert replay.status_code == 401


@pytest.mark.parametrize('change_kind', ['state', 'draft', 'credential', 'revoked'])
def test_trial_rejects_changed_context(client2, app2, monkeypatch, change_kind):
    ident, action, state = setup_trial(client2, app2, monkeypatch)
    if change_kind == 'state':
        state = 'unmatched-state'
    elif change_kind == 'draft':
        make_draft(client2, ident)
    elif change_kind == 'credential':
        monkeypatch.setenv('ND_CLOSEOUT_TRIAL', 'different-synthetic-credential')
    else:
        with app2.state.sessions.begin() as db:
            db.get(User, 'schooladmin').is_admin = False
    response = client2.get('/api/auth/sso/implementation-callback', params={'state': state, 'ticket': 'ST-synthetic'}, follow_redirects=False)
    assert response.status_code in {401, 403, 409}
    with app2.state.sessions() as db:
        assert not db.scalar(select(Setting).where(Setting.key.like('ssoid:%')))
        assert db.scalar(select(func.count()).select_from(AuthSession)) == 1


def test_official_callbacks_are_server_generated_and_health_is_non_destructive(client2, app2):
    auth(client2, 'schooladmin')
    ident = connection_id(client2)
    action = make_draft(client2, ident)
    w = client2.get('/api/connections/'+ident+'/implementation').json()
    assert w['callbacks']['login'] == 'http://testserver/api/auth/sso/callback'
    assert w['callbacks']['test_login'] == 'http://testserver/api/auth/sso/implementation-callback'
    assert w['statuses']['acceptance'] == '待学校签认'
    response = post(client2, '/api/connections/'+ident+'/health', {**REASON, 'expected_version': action['expected_version']})
    assert response.status_code == 200, response.text
    assert response.json()['active_unchanged']
    assert response.json()['connection_version'] == action['expected_version']
    with app2.state.sessions() as db:
        assert db.get(Connection, ident).version == action['expected_version']


def test_materials_and_handover_do_not_imply_acceptance(client2, app2):
    auth(client2, 'schooladmin')
    ident = connection_id(client2)
    make_draft(client2, ident)
    w = client2.get('/api/connections/'+ident+'/implementation').json()
    items = [{'name': name, 'owner': '合成责任人', 'reference': 'SYNTHETIC-DOC-001',
              'confirmed_on': '2026-09-23'} for name in w['materials']['required']]
    r = put(client2, '/api/connections/'+ident+'/materials', {**REASON, 'expected_version': 0, 'items': items})
    assert r.status_code == 200, r.text
    w = client2.get('/api/connections/'+ident+'/implementation').json()
    assert w['statuses']['materials'] == '资料登记齐全'
    assert w['statuses']['acceptance'] == '待学校签认'
    archive = client2.get('/api/connections/'+ident+'/handover.zip')
    assert archive.status_code == 200
    data = zipfile.ZipFile(io.BytesIO(archive.content)).read('implementation.json').decode()
    assert '_credential_sha256' not in data and 'token_hash' not in data
    assert json.loads(data)['school_acceptance'] == 'PENDING_SCHOOL_CONFIRMATION'


@pytest.mark.parametrize('username', ['teacher', 'depthead', 'collegehead'])
def test_non_admin_cannot_access_implementation_or_drafts(client2, app2, username):
    with app2.state.sessions() as db:
        ident = db.scalar(select(Connection.id).where(Connection.code == 'sso'))
    auth(client2, username)
    for endpoint in ('implementation', 'draft', 'handover.zip'):
        assert client2.get('/api/connections/'+ident+'/'+endpoint).status_code == 403
    r = post(client2, '/api/connections/'+ident+'/health', {**REASON, 'expected_version': 1})
    assert r.status_code == 403
