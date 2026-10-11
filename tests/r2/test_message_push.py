"""待办推送到学校移动门户：默认关闭；配置应用 ID 后，积分核对发给教师时按工号推一条。"""
from app import message_push
from conftest import auth
from test_social_training import setup_social, recognized, detail, action, proof  # noqa: F401
from test_point_review import sent_review


class _Inline:
    def __init__(self, target, args, daemon): self.target, self.args = target, args
    def start(self): self.target(*self.args)


def _capture(monkeypatch):
    sent = []
    monkeypatch.setattr(message_push, '_send_all', lambda endpoint, bodies: sent.append((endpoint, bodies)))
    monkeypatch.setattr(message_push.threading, 'Thread', _Inline)
    return sent


def test_push_is_off_without_app_id(recognized, client2, monkeypatch):
    sent = _capture(monkeypatch)
    claim_id, _ = recognized
    sent_review(client2, claim_id)
    assert sent == []


def test_review_sent_to_teacher_pushes_by_staff_no(recognized, client2, app2, monkeypatch):
    sent = _capture(monkeypatch)
    monkeypatch.setattr(app2.state.settings, 'message_push_yyid', 'APP-TEST')
    claim_id, _ = recognized
    sent_review(client2, claim_id)
    bodies = [b for _, batch in sent for b in batch]
    assert len(bodies) == 1, bodies
    body = bodies[0]
    assert body['yyid'] == 'APP-TEST' and body['jsrid'] == 'J001' and '核对' in body['title']
    assert sent[0][0].startswith('https://')
    # 测试环境来源是 http，不能作为门户跳转地址
    assert body['url'] == ''


def test_failed_write_pushes_nothing(recognized, client2, app2, monkeypatch):
    sent = _capture(monkeypatch)
    monkeypatch.setattr(app2.state.settings, 'message_push_yyid', 'APP-TEST')
    claim_id, _ = recognized
    ident = sent_review(client2, claim_id)
    sent.clear()
    auth(client2, 'teacher')
    assert action(client2, 'point-reviews', 'social_resource', ident, 'send').status_code == 403
    assert sent == []


def test_recalculating_assessment_only_notifies_new_or_changed_scores(client2, app2, monkeypatch):
    from conftest import post
    from test_api import rule, activate, REASON
    sent = _capture(monkeypatch)
    monkeypatch.setattr(app2.state.settings, 'message_push_yyid', 'APP-TEST')
    auth(client2, 'schooladmin'); x = rule(client2); assert activate(client2, x).status_code == 200
    calc = lambda: post(client2, '/api/assessments/calculate', {'period_id': 'period2026', 'teacher_ids': ['teacher'], **REASON})
    assert calc().status_code == 200
    first = [b for _, batch in sent for b in batch]
    assert len(first) == 1 and first[0]['jsrid'] == 'J001' and '考核' in first[0]['title']
    sent.clear()
    # 学校反复试算、得分没变：不再重复打扰老师
    assert calc().status_code == 200
    assert sent == []


def test_many_recipients_are_split_into_batches(app2, monkeypatch):
    from app.models import User
    token = message_push.begin()
    try:
        with app2.state.sessions() as db:
            users = [SimpleUser(f'T{i:04d}') for i in range(230)]
            monkeypatch.setattr(db, 'get', lambda model, ident: users[int(ident)] if model is User else None)
            message_push.queue(db, [str(i) for i in range(230)], '标题', '说明')
        box = message_push._pending.get()
    finally:
        message_push._pending.reset(token)
    assert [x['jsrid'].count(',') + 1 for x in box] == [100, 100, 30]
    assert len({s for x in box for s in x['jsrid'].split(',')}) == 230


class SimpleUser:
    def __init__(self, staff_no): self.staff_no = staff_no
