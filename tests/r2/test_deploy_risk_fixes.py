"""Fixes from the 2026-10-11 deployment-risk review; synthetic fixture only."""
import secrets
from datetime import timedelta
from hashlib import sha256
from sqlalchemy.orm import Session
from app.models import AuthSession, User, utcnow
from app.social_models import SocialResource
from conftest import auth, post
from test_procurement_inbound_rollback import REASON, inbound
from test_r4_internal_closeout import configure_middle
from test_teacher_course_inbound import typed


def test_teacher_and_dept_cannot_open_college_ledger(client2, app2):
    with Session(app2.state.engine) as db:
        db.add(SocialResource(id='ledger-x', kind='ledger', code='LEDGER-X', org_id='college1', name='学院台账', state='SUBMITTED', data={}))
        db.commit()
    for user in ('teacher', 'depthead'):
        auth(client2, user)
        r = client2.get('/api/social/objects/social_resource/ledger-x')
        assert r.status_code == 403 and '学院台账' in r.json()['detail'], (user, r.text)
    auth(client2, 'collegehead')
    assert client2.get('/api/social/objects/social_resource/ledger-x').status_code == 200


def sso_login(client, app, user_id):
    """Trusted server-side session, as created only after the SSO callback."""
    cfg = app.state.settings
    token = secrets.token_urlsafe(32)
    with Session(app.state.engine) as db:
        user = db.get(User, user_id)
        db.add(AuthSession(token_hash=sha256(token.encode()).hexdigest(), csrf=secrets.token_urlsafe(32), user_id=user_id,
            auth_version=user.auth_version, auth_method='sso', expires_at=utcnow() + timedelta(hours=1), last_seen=utcnow()))
        db.commit()
    client.cookies.clear()
    client.cookies.set(cfg.cookie_name, token)
    return token


def test_sso_session_is_not_blocked_by_temporary_password(client2, app2):
    with Session(app2.state.engine) as db:
        db.get(User, 'teacher').must_change_password = True
        db.commit()
    cfg = app2.state.settings
    token = sso_login(client2, app2, 'teacher')
    assert client2.get('/api/records').status_code == 200
    client2.cookies.set('nd_sso_session', sha256(('sso:' + token).encode()).hexdigest())
    assert client2.get('/api/records').status_code == 200
    me = client2.get('/api/auth/me').json()
    assert me['sso_session'] is True and me['user']['must_change_password'] is False
    # Client markers do not change the trusted server-side provenance.
    client2.cookies.set('nd_sso_session', 'x' * 64)
    assert client2.get('/api/records').status_code == 200
    assert cfg.cookie_name in client2.cookies


def test_missing_course_credit_blocks_formal_calculation(client2, app2):
    from test_api import activate
    from app.reference_data import TeacherHrProfile
    c = client2; auth(c, 'schooladmin')
    maps = (typed('school_course', {'KCH': 'code', 'KCMC': 'name', 'XF': 'credit'}, {'code', 'name'})
            + typed('teacher_course', {'ZGH': 'staff_no', 'XM': 'teacher_name', 'KCH': 'course_code', 'KCMC': 'course_name', 'XQMC': 'term_name'},
                    {'staff_no', 'course_code', 'course_name', 'term_name'}))
    conn = configure_middle(c, maps)
    inbound(c, conn, 'school_course', [{'KCH': 'K1', 'KCMC': '高等数学', 'XF': '4'}])
    # K9 is taught but missing from the course catalogue, so it has no credit.
    inbound(c, conn, 'teacher_course', [
        {'ZGH': 'J001', 'XM': '测试教师一', 'KCH': 'K1', 'KCMC': '高等数学', 'XQMC': '2025-2026学年第二学期'},
        {'ZGH': 'J001', 'XM': '测试教师一', 'KCH': 'K9', 'KCMC': '缺学分课', 'XQMC': '2025-2026学年第二学期'}])
    with Session(app2.state.engine) as db:
        db.add(TeacherHrProfile(staff_no='J001', user_id='teacher', name='测试教师一', org_code='dept1')); db.commit()
    r = post(c, '/api/rules', {'kind': 'points', 'name': '学分积分', 'period_id': 'period2026', 'config': {'components': [
        {'key': 'credits', 'label': '授课学分', 'source': 'credits', 'factor': '2', 'weight': '0', 'target': '1', 'cap': None}]}, **REASON})
    assert r.status_code == 200, r.text
    assert activate(c, r.json()).status_code == 200
    r = post(c, '/api/points/calculate', {'period_id': 'period2026', 'teacher_ids': ['teacher'], **REASON})
    assert r.status_code == 409 and 'K9' in r.json()['detail'], r.text
    assert c.get('/api/points?teacher_id=teacher').json()['sum'] in ('0', '0.00')
