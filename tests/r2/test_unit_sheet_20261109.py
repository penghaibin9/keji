"""2026-11-09 老师自己上传参训明细表（五列 Excel）；学校结项点“同意”即可。"""
import uuid
from datetime import date
from io import BytesIO
from openpyxl import Workbook, load_workbook
from sqlalchemy import select
from app.models import User
from app.social_models import SocialUnit, SocialProject
from app import social_training as st
from conftest import auth
from test_social_training import setup_social, detail, action, proof  # noqa: F401


def sheet(rows, head=('培训日期', '课程', '学员', '是否完成', '授课教师工号')):
    wb = Workbook(); ws = wb.active; ws.append(list(head))
    for r in rows: ws.append(list(r))
    out = BytesIO(); wb.save(out); return out.getvalue()


def upload(client, pid, data, name='参训明细.xlsx'):
    return client.post('/api/social/projects/' + pid + '/unit-sheet', headers={'Idempotency-Key': str(uuid.uuid4())},
                       files={'file': (name, data, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})


def units(app2, pid):
    with app2.state.sessions() as db:
        return db.scalars(select(SocialUnit).where(SocialUnit.project_id == pid)).all()


def test_template_has_five_columns(client2):
    auth(client2, 'teacher')
    r = client2.get('/api/social/units/template.xlsx')
    assert r.status_code == 200
    ws = load_workbook(BytesIO(r.content)).active
    assert [c.value for c in ws[1]] == ['培训日期', '课程', '学员', '是否完成', '授课教师工号']


def test_teacher_uploads_sheet_bad_rows_skipped_and_reupload_replaces(setup_social, client2, app2):
    pid = setup_social
    auth(client2, 'teacher')
    data = sheet([('2026-09-01', '', '张三', '', ''), ('2026/9/1', 'SOC-C1', '李四', '否', ''),
                  ('2026-10-01', '', '王五', '', ''), ('2026-09-02', '', '', '', ''),
                  ('2026-09-02', '', '赵六', '', 'NOPE'), ('2026-09-01', '', '张三', '', ''),
                  ('2026-09-02', '技能课程', '钱七', '是', '')])
    r = upload(client2, pid, data)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['imported'] == 3 and body['units'] == 2 and body['effective'] == 2 and body['excluded'] == 1
    assert [e['row'] for e in body['errors']] == [4, 5, 6, 7]
    assert '项目期间' in body['errors'][0]['reason'] and '工号 NOPE' in body['errors'][2]['reason'] and '重复' in body['errors'][3]['reason']
    got = units(app2, pid)
    assert len(got) == 2 and all(u.data['teachers'] == [{'teacher_id': 'teacher', 'staff_type': 'internal', 'role': 'lecturer'}] for u in got)
    r = upload(client2, pid, sheet([('2026-09-01', '', '孙八', '', '')]))
    assert r.status_code == 200, r.text
    got = units(app2, pid)
    assert len(got) == 1 and got[0].data['learners'][0]['reference'] == '孙八'


def test_no_usable_rows_or_wrong_format_is_422(setup_social, client2, app2):
    pid = setup_social
    auth(client2, 'teacher')
    r = upload(client2, pid, sheet([('2026-12-01', '', '张三', '', '')]))
    assert r.status_code == 422 and '第2行' in r.json()['detail']
    r = upload(client2, pid, b'not-xlsx', name='a.csv')
    assert r.status_code == 422


def test_school_close_one_click_defaults(setup_social, client2, app2, monkeypatch):
    monkeypatch.setattr(st, 'today', lambda: date(2026, 9, 3))
    pid = setup_social
    auth(client2, 'schooladmin')
    r = action(client2, 'projects', 'social_project', pid, 'close_submit', closeout={'closed_on': '2026-09-02', 'outcome_report': '结项报告'})
    assert r.status_code == 200, r.text
    auth(client2, 'reviewer')
    r = action(client2, 'projects', 'social_project', pid, 'close')
    assert r.status_code == 409 and r.json()['detail'] == '老师还没上传参训明细表'
    auth(client2, 'teacher')
    assert upload(client2, pid, sheet([('2026-09-01', '', '张三', '', '')])).status_code == 200
    auth(client2, 'reviewer')
    r = action(client2, 'projects', 'social_project', pid, 'close')
    assert r.status_code == 200, r.text
    with app2.state.sessions() as db:
        p = db.get(SocialProject, pid)
        assert p.state == 'CLOSED' and str(p.closeout['satisfaction']) == '85' and str(p.closeout['actual_income']) == '0'


def test_upload_needs_login(setup_social, client2):
    client2.cookies.clear()
    r = upload(client2, setup_social, sheet([('2026-09-01', '', '张三', '', '')]))
    assert r.status_code in (401, 403)
