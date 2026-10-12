"""数据中台令牌提前失效（20007/20009/20010）时清缓存、重新取令牌并只重试一次。"""
from app.adapters.rest import ConfigurableRestBase


class FakeTransport:
    calls = []
    script = []

    def __init__(self, endpoint):
        self.endpoint = endpoint

    def request_json(self, method, target, *, headers=None, payload=None, timeout_seconds=None):
        FakeTransport.calls.append((method, target, dict(payload or {})))
        if 'get_access_token' in target:
            n = sum(1 for c in FakeTransport.calls if 'get_access_token' in c[1])
            return {'code': 10000, 'result': {'access_token': f'tok{n}', 'expires_in': 7200}}
        return FakeTransport.script.pop(0)


class Adapter(ConfigurableRestBase):
    transport_cls = FakeTransport


SPEC = {'method': 'POST', 'path': '/open_api/customization/tgxjzgjbxx/full', 'body': {'page': 1},
        'auth': {'mode': 'datahub_access_token', 'token_in': 'body'}}
CREDS = {'app_key': 'k', 'app_secret': 's'}


def run(script):
    FakeTransport.calls = []; FakeTransport.script = list(script)
    a = Adapter()
    return a, a._request_json(endpoint='https://dh.example.edu.cn', spec=SPEC, context={}, credentials=CREDS, timeout_seconds=5)


def data_calls():
    return [c for c in FakeTransport.calls if 'get_access_token' not in c[1]]


def test_invalid_token_refreshes_and_retries_once():
    _, out = run([{'code': 20009, 'message': 'token error'}, {'code': 10000, 'result': {'data': [1]}}])
    assert out['code'] == 10000
    calls = data_calls()
    assert [c[2]['access_token'] for c in calls] == ['tok1', 'tok2']


def test_second_invalid_token_is_returned_not_looped():
    _, out = run([{'code': 20007}, {'code': 20010}])
    assert out['code'] == 20010 and len(data_calls()) == 2


def test_other_errors_do_not_retry():
    _, out = run([{'code': 50000}])
    assert out['code'] == 50000 and len(data_calls()) == 1


def test_cached_token_reused_when_valid():
    a, _ = run([{'code': 10000}, {'code': 10000}])
    a._request_json(endpoint='https://dh.example.edu.cn', spec=SPEC, context={}, credentials=CREDS, timeout_seconds=5)
    assert sum(1 for c in FakeTransport.calls if 'get_access_token' in c[1]) == 1
