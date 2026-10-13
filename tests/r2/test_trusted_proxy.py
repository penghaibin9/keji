"""学校反向代理把所有用户转发成同一个地址：默认不信转发头；配置了可信代理才采用代理传来的客户端链。"""
import pytest
from fastapi.testclient import TestClient
from app.client_ip import client_ip, parse_networks
from app.config import Settings
from app.main import create_app
from conftest import FIXTURE_PASSWORD, _database_url
from support import populate

PROXY = '10.255.1.34'


class _Request:
    def __init__(self, peer, chain, trusted):
        from types import SimpleNamespace
        self.client = SimpleNamespace(host=peer) if peer else None
        self.headers = {'x-client-chain': chain} if chain is not None else {}
        self.app = SimpleNamespace(state=SimpleNamespace(settings=SimpleNamespace(trusted_proxy_networks=parse_networks(trusted))))


def test_default_off_ignores_the_forwarded_chain():
    assert client_ip(_Request(PROXY, '1.2.3.4', '')) == PROXY
    assert client_ip(_Request(None, '1.2.3.4', PROXY)) == 'unknown'


def test_trusted_proxy_uses_the_right_most_address_that_is_not_a_trusted_proxy():
    assert client_ip(_Request(PROXY, '172.16.8.9', PROXY)) == '172.16.8.9'
    # 客户端自己写的最左边内容不被采用；采用最右边第一个不是可信代理的地址
    assert client_ip(_Request(PROXY, '6.6.6.6, 172.16.8.9', PROXY)) == '172.16.8.9'
    assert client_ip(_Request(PROXY, '172.16.8.9, 10.0.0.7', '10.255.1.34, 10.0.0.0/24')) == '172.16.8.9'
    assert client_ip(_Request('10.255.1.34', '2001:db8::5', '10.255.1.0/24')) == '2001:db8::5'


def test_untrusted_peer_cannot_set_the_address_even_when_a_proxy_is_configured():
    assert client_ip(_Request('203.0.113.9', '6.6.6.6', PROXY)) == '203.0.113.9'


def test_missing_or_malformed_chain_falls_back_to_the_direct_peer():
    assert client_ip(_Request(PROXY, None, PROXY)) == PROXY
    assert client_ip(_Request(PROXY, '', PROXY)) == PROXY
    assert client_ip(_Request(PROXY, '172.16.8.9, unknown', PROXY)) == PROXY
    assert client_ip(_Request(PROXY, '10.255.1.34', PROXY)) == PROXY      # 链里全是代理自己


def test_malformed_setting_is_rejected_at_startup(tmp_path):
    with pytest.raises(ValueError):
        Settings(env='test', database_url='sqlite:///' + str(tmp_path / 'x.sqlite'), secure_cookie=False, public_origin='http://testserver',
                 allowed_hosts='testserver', storage_dir=tmp_path / 'files', trusted_proxies='not-an-address')


def _client(tmp_path, trusted, peer=PROXY):
    tmp_path.mkdir(parents=True, exist_ok=True)
    cfg = Settings(env='test', database_url='sqlite:///' + str(tmp_path / 'proxy.sqlite'), secure_cookie=False, public_origin='http://testserver',
                   allowed_hosts='testserver', storage_dir=tmp_path / 'files', trusted_proxies=trusted)
    app = create_app(cfg); populate(app.state.engine)
    client = TestClient(app, raise_server_exceptions=False, client=(peer, 50000)); client.headers['origin'] = 'http://testserver'
    return client


def _bad_login(client, ip, user):
    return client.post('/api/auth/login', json={'username': user, 'password': 'wrong-password'}, headers={'x-client-chain': ip})


def test_school_proxy_users_are_throttled_per_real_address_only_when_configured(tmp_path):
    # 没配置：全校用户在同一个来源地址下共享计数，一个人刷满，别人的登录也被限流（旧行为，作对照）
    shared = _client(tmp_path / 'off', '')
    for _ in range(100):
        if _bad_login(shared, '172.16.8.9', 'nobody').status_code == 429:break
    assert shared.post('/api/auth/login', json={'username': 'teacher', 'password': FIXTURE_PASSWORD}, headers={'x-client-chain': '172.16.8.10'}).status_code == 429
    # 配置了可信代理：另一位用户的真实地址不同，不受影响
    split = _client(tmp_path / 'on', PROXY)
    for _ in range(100):
        if _bad_login(split, '172.16.8.9', 'nobody').status_code == 429:break
    ok = split.post('/api/auth/login', json={'username': 'teacher', 'password': FIXTURE_PASSWORD}, headers={'x-client-chain': '172.16.8.10'})
    assert ok.status_code == 200, ok.text
