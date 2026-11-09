"""2026-11-09 社会培训项目积分：结项通过后系统自动生成申报，走 教研室 → 学院 → 学校 三级。"""
from datetime import date
from decimal import Decimal
from sqlalchemy import select
from app.models import PointEntry
from app.social_models import SocialClaim
from app import social_training as st
from conftest import auth
from test_social_training import HASH, setup_social, import_rows, row, action, detail, policy, close_project  # noqa: F401


def auto_claim(app2, pid):
    with app2.state.sessions() as db:
        return db.scalars(select(SocialClaim).where(SocialClaim.project_id == pid)).all()


def test_close_generates_claim_and_three_levels_book_points(setup_social, client2, app2, monkeypatch):
    monkeypatch.setattr(st, 'today', lambda: date(2026, 9, 3))
    pid = setup_social
    policy(client2, True)  # 学校已启用积分口径
    assert import_rows(client2, pid, [row()]).status_code == 200
    close_project(client2, pid)
    claims = auto_claim(app2, pid)
    assert len(claims) == 1 and claims[0].teacher_id == 'teacher' and claims[0].state == 'DEPT'
    assert claims[0].data['auto'] is True and claims[0].data['chain'] == 3
    ident = claims[0].id
    auth(client2, 'collegehead')
    assert action(client2, 'claims', 'social_claim', ident, 'approve').status_code == 403  # 不能越过教研室
    auth(client2, 'teacher')
    assert action(client2, 'claims', 'social_claim', ident, 'approve').status_code in (403, 409)
    for user, after in (('depthead', 'COLLEGE'), ('collegehead', 'SCHOOL'), ('reviewer', 'ARCHIVED')):
        auth(client2, user)
        r = action(client2, 'claims', 'social_claim', ident, 'approve')
        assert r.status_code == 200 and r.json()['item']['state'] == after, r.text
    with app2.state.sessions() as db:
        assert sum(db.scalars(select(PointEntry.amount).where(PointEntry.kind == 'SOCIAL'))) == Decimal('1.56')


def test_no_active_policy_means_no_auto_claim(setup_social, client2, app2, monkeypatch):
    monkeypatch.setattr(st, 'today', lambda: date(2026, 9, 3))
    pid = setup_social
    assert import_rows(client2, pid, [row()]).status_code == 200
    close_project(client2, pid)
    assert auto_claim(app2, pid) == []
