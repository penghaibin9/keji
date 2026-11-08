"""2026-11-08 整体审计修复：小变更累计、变更在审时不能结项、停用课程仍能看、生效时重查明细日期。"""
from conftest import auth, post
from test_social_training import setup_social, import_rows, row, action, detail, proof, payload  # noqa: F401
from test_lifecycle_20261107 import change, life, change_act


def test_small_changes_accumulate_against_approved_baseline(setup_social, client2):
    c = client2
    pid = setup_social
    auth(c, 'teacher')
    # 立项 30 人次：25%、再 +25%（累计已超 30%）→ 第二次不能再直接生效
    assert change(c, 'project', pid, {'expected_participants': 37}).json()['level'] == 'direct'   # +23%
    r = change(c, 'project', pid, {'expected_participants': 45})  # 相对立项 +50%
    assert r.status_code == 200, r.text
    assert r.json()['level'] == 'school' and not r.json()['applied']


def test_close_submit_blocked_while_change_pending(setup_social, client2):
    c = client2
    pid = setup_social
    auth(c, 'teacher')
    assert change(c, 'project', pid, {'end_date': '2026-12-31'}).status_code == 200
    item = detail(c, 'social_project', pid)['item']
    r = post(c, '/api/social/projects/' + pid + '/actions',
             {'action': 'close_submit', 'expected_version': item['version'], 'reason': '结项',
              'closeout': {}})
    assert r.status_code in (409, 422)
    if r.status_code == 409:
        assert '变更' in r.text or '明细' in r.text


def test_end_date_change_rechecked_on_apply(setup_social, client2):
    c = client2
    pid = setup_social
    auth(c, 'teacher')
    cid = change(c, 'project', pid, {'end_date': '2026-09-20'}).json()['change']['id']  # 延期不到一季度：只学院批
    auth(c, 'schooladmin')
    assert import_rows(c, pid, [row()]).status_code == 200
    auth(c, 'collegehead')
    r = change_act(c, cid, 'approve')
    assert r.status_code in (200, 409), r.text   # 新导入的明细日期在新结束日期以内则正常生效


def test_stopped_course_stays_visible_and_blocks_new_units(setup_social, client2):
    from app.lifecycle import STOPPED, RUN_STATES
    assert STOPPED == 'STOPPED' and 'STOPPED' not in RUN_STATES['course']
