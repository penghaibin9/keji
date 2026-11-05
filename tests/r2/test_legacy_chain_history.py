"""旧申请转新流程：历史上已通过的节点（旧链的教研室、学校）不在新链里时，进度计算不能报错。

触发条件：退回的那一级还在新链里，但它之前已通过的节点被新链去掉了。
例：旧课程“教研室通过 → 学院退回 → 重提 → 撤回 → 再提交”，再提交记了新链（学院 → 学校），历史里还有教研室的“通过”。
"""
from datetime import datetime, timedelta
from types import SimpleNamespace
import pytest
from app import approvals as ap


def ev(i, decision, level=None, flow='course'):
    h = {'flow': flow, 'decision': decision}
    if level:
        h['level'] = level
    return SimpleNamespace(after={'handling': h}, created_at=datetime(2026, 11, 1) + timedelta(hours=i), actor_name='某人', reason='补材料')


@pytest.fixture
def fake(monkeypatch):
    box = {}
    monkeypatch.setattr(ap, 'events', lambda db, t, i: box['evs'])
    monkeypatch.setattr(ap, 'handler_names', lambda db, a, level: (['办理人'], ap.LEVEL_LABEL[level], None))
    monkeypatch.setattr(ap, 'duty_gap', lambda db, a, level: None)
    return box


@pytest.mark.parametrize('flow,state,removed', [('course', 'COLLEGE', 'dept'), ('teaching_course', 'COLLEGE', 'dept'), ('trainer', 'COLLEGE', 'dept')])
def test_resubmitted_old_application_enters_new_chain(fake, flow, state, removed):
    fake['evs'] = [ev(0, 'submit', flow=flow), ev(1, 'approve', removed, flow), ev(2, 'return', 'college', flow), ev(3, 'submit', flow=flow),
                   ev(4, 'withdraw', flow=flow), ev(5, 'submit', flow=flow)]
    obj = SimpleNamespace(id='x', state=state, data=ap.mark_new_chain(flow, {}))
    assert ap.chain_of(flow, obj) == ap.FLOWS[flow]['chain'] and removed not in ap.chain_of(flow, obj)
    p = ap.progress(None, flow, obj, SimpleNamespace(id='t', name='老师'))
    assert [n['key'] for n in p['nodes']] == ['submit', *ap.FLOWS[flow]['chain'], 'done']
    assert p['nodes'][1]['state'] == 'current' and p['tone'] == 'blue'


def test_old_chain_and_new_chain_return_unchanged(fake):
    # 旧申请继续按旧链：教研室通过、学院退回后补正，进度仍显示教研室已通过、从学院接着审。
    fake['evs'] = [ev(0, 'submit'), ev(1, 'approve', 'dept'), ev(2, 'return', 'college'), ev(3, 'submit')]
    old = SimpleNamespace(id='x', state='COLLEGE', data={})
    p = ap.progress(None, 'course', old, SimpleNamespace(id='t', name='老师'))
    assert [(n['key'], n['state']) for n in p['nodes']][:3] == [('submit', 'done'), ('dept', 'done'), ('college', 'current')]
    # 新申请学校退回：学院的通过保留，补正后从学校接着审。
    fake['evs'] = [ev(0, 'submit'), ev(1, 'approve', 'college'), ev(2, 'return', 'school'), ev(3, 'submit')]
    new = SimpleNamespace(id='y', state='SCHOOL', data=ap.mark_new_chain('course', {}))
    p = ap.progress(None, 'course', new, SimpleNamespace(id='t', name='老师'))
    assert [(n['key'], n['state']) for n in p['nodes']][:3] == [('submit', 'done'), ('college', 'done'), ('school', 'current')]
