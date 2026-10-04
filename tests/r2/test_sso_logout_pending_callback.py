"""A logout must also cancel that browser's outstanding SSO request."""
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations import ADAPTERS
from app.models import Audit, AuthSession, Setting
from conftest import post
from test_r11_three_adapter_layer import _enable_sso


@pytest.mark.parametrize('logout_path', ['/api/auth/logout', '/api/auth/sso/logout'])
def test_logout_revokes_pending_callback_even_if_old_cookie_is_replayed(app2,logout_path):
    _enable_sso(app2)
    try:
        with TestClient(app2,raise_server_exceptions=False) as client:
            def start():
                response=client.get('/api/auth/sso/start',follow_redirects=False)
                assert response.status_code==302
                return parse_qs(urlsplit(response.headers['location']).query)['state'][0]
            initial=start()
            assert client.get('/api/auth/sso/callback',params={'state':initial,'code':'mock'},follow_redirects=False).status_code==303
            me=client.get('/api/auth/me').json()
            client.headers.update({'origin':'http://testserver','x-csrf-token':me['csrf']})
            pending=start()
            response=post(client,logout_path)
            assert response.status_code==200,response.text
            assert client.get('/api/auth/me').status_code==401
            # Replay the pre-logout browser cookie; deleting cookies alone is
            # insufficient because the server must revoke the pending state.
            client.cookies.set('nd_test_sso_state',pending)
            callback=client.get('/api/auth/sso/callback',params={'state':pending,'code':'mock'},follow_redirects=False)
            assert callback.status_code==401
            assert client.get('/api/auth/me').status_code==401
            with Session(app2.state.engine) as db:
                assert db.scalar(select(AuthSession)) is None
                assert db.scalar(select(Setting).where(Setting.key.like('ssostate:%'))) is None
                rejection=db.scalar(select(Audit).where(Audit.action=='统一认证登录拒绝'))
                assert rejection is not None and rejection.result=='DENIED'
    finally:
        ADAPTERS.clear()


def test_implementation_callback_rejects_non_ascii_state_without_server_error(client2,app2,monkeypatch):
    from test_integration_workspace import setup_trial
    setup_trial(client2,app2,monkeypatch)
    original_cookie=client2.cookies.get(app2.state.settings.cookie_name)
    response=client2.get('/api/auth/sso/implementation-callback',
        params={'state':'非法模拟状态','ticket':'ST-synthetic'},follow_redirects=False)
    assert response.status_code==401
    assert response.json()['session_created'] is False
    assert client2.cookies.get(app2.state.settings.cookie_name)==original_cookie
    assert client2.get('/api/auth/me').json()['user']['id']=='schooladmin'
    with app2.state.sessions() as db:
        assert db.scalar(select(Setting).where(Setting.key.like('integration.sso_trial:%'))) is None
        assert db.scalar(select(Setting).where(Setting.key.like('ssoid:%'))) is None


def test_logout_does_not_cancel_another_browsers_pending_login(app2):
    _enable_sso(app2)
    try:
        with TestClient(app2,raise_server_exceptions=False) as first, TestClient(app2,raise_server_exceptions=False) as other:
            def start(client):
                response=client.get('/api/auth/sso/start',follow_redirects=False)
                return parse_qs(urlsplit(response.headers['location']).query)['state'][0]
            initial=start(first)
            assert first.get('/api/auth/sso/callback',params={'state':initial,'code':'mock'},follow_redirects=False).status_code==303
            first.headers.update({'origin':'http://testserver','x-csrf-token':first.get('/api/auth/me').json()['csrf']})
            start(first)
            other_state=start(other)
            assert post(first,'/api/auth/sso/logout').status_code==200
            callback=other.get('/api/auth/sso/callback',params={'state':other_state,'code':'mock'},follow_redirects=False)
            assert callback.status_code==303
            assert other.get('/api/auth/me').status_code==200
    finally:
        ADAPTERS.clear()


def test_non_ascii_callback_state_is_rejected_and_audited(app2):
    _enable_sso(app2)
    try:
        with TestClient(app2,raise_server_exceptions=False) as client:
            assert client.get('/api/auth/sso/start',follow_redirects=False).status_code==302
            callback=client.get('/api/auth/sso/callback',params={'state':'非法模拟状态','code':'mock'},follow_redirects=False)
            assert callback.status_code==401
            assert client.get('/api/auth/me').status_code==401
            with Session(app2.state.engine) as db:
                row=db.scalar(select(Audit).where(Audit.action=='统一认证登录拒绝'))
                assert row is not None and row.result=='DENIED'
    finally:
        ADAPTERS.clear()
