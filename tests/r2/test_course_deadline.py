"""培训课程申报期限：每学年一个截止日（默认学年结束后的 9 月 30 日），到期前 7 天提醒，截止后学院可为本院开放补报。"""
from datetime import date
import pytest
from conftest import auth, put
from test_applications import setup, apply_course
from app import applications as apps


def today_is(monkeypatch, day):
    monkeypatch.setattr(apps, 'school_today', lambda: day)


def overview(c):
    r = c.get('/api/applications/deadlines')
    assert r.status_code == 200, r.text
    return r.json()


def test_default_deadline_reminder_and_block_after_deadline(app2, client2, monkeypatch):
    c = client2
    ids = setup(app2, open_years=False)
    auth(c, 'teacher')
    # 2024-2025 学年的课（X2），默认截止 2025-09-30；到期前 7 天提醒。
    today_is(monkeypatch, date(2025, 9, 25))
    d = c.get('/api/applications/teaching-courses').json()
    x2 = next(x for x in d['courses'] if x['course_code'] == 'X2')
    assert x2['window']['deadline'] == '2025-09-30' and x2['window']['days_left'] == 5 and x2['window']['state'] == 'open'
    assert [w['school_year'] for w in d['deadline_reminders']] == ['2024-2025']
    today_is(monkeypatch, date(2025, 10, 1))
    r = apply_course(c, ids['X2'])
    assert r.status_code == 409 and '2025-09-30 截止' in r.text and '开放补报' in r.text
    assert c.get('/api/applications/deadlines').status_code == 403
    # 学院开放补报后本院老师可以申报。
    auth(c, 'collegehead')
    o = overview(c)
    assert o['can_reopen'] and not o['can_set']
    item = next(x for x in o['items'] if x['school_year'] == '2024-2025')
    assert item['state'] == 'closed'
    body = {'school_year': '2024-2025', 'until': '2025-10-20', 'reason': '老师出差补报', 'expected_version': o['version']}
    assert put(c, '/api/applications/deadlines/reopen', {**body, 'until': '2026-03-01'}).status_code == 422  # 最多 90 天
    assert put(c, '/api/applications/deadlines/reopen', {**body, 'school_year': '2025-2026'}).status_code == 409  # 还没截止
    r = put(c, '/api/applications/deadlines/reopen', body)
    assert r.status_code == 200, r.text
    assert next(x for x in r.json()['items'] if x['school_year'] == '2024-2025')['state'] == 'reopened'
    auth(c, 'teacher')
    assert apply_course(c, ids['X2']).status_code == 200
    # 补报结束后又截止；另一学院不受本院补报影响。
    auth(c, 'otherdept')
    assert c.get('/api/applications/deadlines').status_code == 403
    today_is(monkeypatch, date(2025, 10, 21))
    auth(c, 'teacher')
    assert c.get('/api/applications/teaching-courses').json()['windows']['2024-2025']['state'] == 'closed'


def test_school_sets_deadline_with_version_check(app2, client2, monkeypatch):
    c = client2
    ids = setup(app2, open_years=False)
    today_is(monkeypatch, date(2025, 10, 5))
    auth(c, 'collegehead')
    assert put(c, '/api/applications/deadlines', {'school_year': '2024-2025', 'deadline': '2025-10-31', 'reason': '学校发文延期', 'expected_version': 0}).status_code == 403
    auth(c, 'schooladmin')
    o = overview(c)
    assert o['can_set']
    bad = {'school_year': '2024-2025', 'deadline': '2024-08-01', 'reason': '学校发文延期', 'expected_version': o['version']}
    assert put(c, '/api/applications/deadlines', bad).status_code == 422
    assert put(c, '/api/applications/deadlines', {**bad, 'school_year': '2024-2026'}).status_code == 422
    r = put(c, '/api/applications/deadlines', {**bad, 'deadline': '2025-10-31'})
    assert r.status_code == 200, r.text
    item = next(x for x in r.json()['items'] if x['school_year'] == '2024-2025')
    assert item['deadline'] == '2025-10-31' and item['custom'] and item['state'] == 'open'
    assert put(c, '/api/applications/deadlines', {**bad, 'deadline': '2025-11-30'}).status_code == 409  # 旧版本号
    auth(c, 'teacher')
    assert apply_course(c, ids['X2']).status_code == 200


@pytest.mark.parametrize('year,expected', [('2025-2026', date(2026, 9, 30)), ('2020-2021', date(2021, 9, 30))])
def test_default_deadline_is_september_30_after_the_year(year, expected):
    assert apps.default_deadline(year) == expected


def test_approved_course_books_no_points_and_rebook_is_gone(app2, client2):
    """管理办法第十六条是课程遴选：通过后进培训课程库，不给老师记积分（积分办法只按项目授课人次计）。"""
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from app.models import Setting, PointEntry
    from conftest import post
    from test_applications import act
    c = client2
    ids = setup(app2)
    with app2.state.sessions.begin() as db:
        db.add(Setting(key='param:social_course_points', value={'name': '每门社会培训课积分', 'type': 'decimal', 'value': '3'}))
    auth(c, 'teacher')
    ident = apply_course(c, ids['K1']).json()['item']['id']
    for user in ('depthead', 'collegehead', 'reviewer'):
        auth(c, user)
        assert act(c, ident, 'approve').status_code == 200
    assert 'points' not in c.get('/api/applications/' + ident).json()['item']['data']
    auth(c, 'schooladmin')
    assert 'pending_points' not in overview(c)
    assert post(c, '/api/applications/points/rebook', {'reason': '补记'}).status_code in (404, 405)
    with Session(app2.state.engine) as db:
        assert db.scalars(select(PointEntry).where(PointEntry.teacher_id == 'teacher')).all() == []
