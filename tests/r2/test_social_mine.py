"""个人培训页：只显示本人的项目、积分申报进度、台账人次、资质和提醒。"""
from app.routes.ledgers import claim_deadline
from datetime import date
from conftest import auth, post
from test_social_training import setup_social, row, import_rows, close_project
from test_social_additions import recommended


def test_mine_lists_own_project_deadline_then_claim_steps(setup_social,client2,app2):
    pid=setup_social;assert import_rows(client2,pid,[row()]).status_code==200;close_project(client2,pid)
    auth(client2,'teacher');m=client2.get('/api/social/mine?year=2026');assert m.status_code==200,m.text;m=m.json()
    p=next(x for x in m['projects'] if x['id']==pid)
    assert p['state']=='CLOSED' and p['roles']==['项目负责人','主讲（1 次）'] and p['claim'] is None
    assert p['deadline']['date']=='2026-09-23' and p['deadline']['estimated'] is True
    assert any('截止日期暂估为 2026-09-23' in r['text'] and r['action']=='social-detail' for r in m['reminders'])
    pol=recommended(client2).json()['item']['id']
    auth(client2,'teacher');r=post(client2,'/api/social/claims',{'project_id':pid,'period_id':'period2026','policy_id':pol,'recognition_form_reference':'学校制式认定表','reason':'申报'});assert r.status_code==200,r.text
    m=client2.get('/api/social/mine?year=2026').json()
    c=m['claims'][0];assert c['state']=='DRAFT' and c['total']=='1.56' and c['steps'][0]['current'] and not any(s['done'] for s in c['steps'])
    assert next(x for x in m['projects'] if x['id']==pid)['claim']['state']=='DRAFT'
    assert any('等学校正式启用积分口径后再提交' in r['text'] for r in m['reminders']) and not any('前申报积分' in r['text'] for r in m['reminders'])
    auth(client2,'otherteacher');other=client2.get('/api/social/mine?year=2026').json()
    assert other['projects']==[] and other['claims']==[]


def test_weekday_estimate_skips_weekends(app2):
    with app2.state.sessions() as db:
        due,estimated=claim_deadline(db,date(2026,9,4))
    assert due==date(2026,9,25) and estimated


def test_estimated_deadline_never_declares_expiry_and_confirmed_deadline_routes_correctly(setup_social, client2, app2, monkeypatch):
    from app import social_training as st
    from app.social_models import SocialPolicy
    pid = setup_social
    assert import_rows(client2, pid, [row()]).status_code == 200
    close_project(client2, pid)
    monkeypatch.setattr(st, 'today', lambda: date(2026, 9, 24))
    auth(client2, 'teacher')
    reminder = next(r for r in client2.get('/api/social/mine?year=2026').json()['reminders'] if '截止日期' in r['text'])
    assert '不据此认定逾期' in reminder['text'] and '已过期' not in reminder['text']
    assert reminder['action'] == 'social-detail' and reminder['id'] == 'social_project|' + pid
    with app2.state.sessions.begin() as db:
        db.add(SocialPolicy(period_id='period2026', name='合成已确认校历', state='ACTIVE', created_by='schooladmin',
                            data={'calendar_start':'2026-01-01','calendar_end':'2026-12-31','calendar_reference':'合成书面校历','holidays':[],'workdays':[]}))
    reminder = next(r for r in client2.get('/api/social/mine?year=2026').json()['reminders'] if '截止日期' in r['text'])
    assert '已超过学校校历确定' in reminder['text'] and reminder['action'] == 'social-detail'
    monkeypatch.setattr(st, 'today', lambda: date(2026, 9, 23))
    reminder = next(r for r in client2.get('/api/social/mine?year=2026').json()['reminders'] if '前申报积分' in r['text'])
    assert reminder['action'] == 'social-claim-new' and reminder['action_label'] == '去申报'


def test_bimonth_report_keeps_organization_in_both_todo_views(setup_social, client2, monkeypatch):
    from app import social_training as st
    monkeypatch.setattr(st, 'today', lambda: date(2026, 10, 11))
    auth(client2, 'depthead')
    todo = next(x for x in client2.get('/api/todos').json()['items'] if x['type'] == 'social_report')
    home = next(x for x in client2.get('/api/portal/workbench').json()['tasks']['items'] if x['type'] == 'social_report')
    assert todo['target_id'] == home['target_id'] == 'dept1'
    assert home['owner_name'] == '测试教研室一'
