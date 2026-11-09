"""2026-11-07 立项后的运行过程：运行记录、申请变更（原档案照常运行，通过后版本号 +1）、年度确认、停用与恢复、立项简化。"""
from conftest import auth, post, put
from test_social_training import setup_social, import_rows, row, action, detail, proof, payload  # noqa: F401
from test_applications import setup as app_setup, apply_course, act


def life(c, kind, ident):
    r = c.get('/api/social/lifecycle/' + kind + '/' + ident)
    assert r.status_code == 200, r.text
    return r.json()


def change(c, kind, ident, values, reason='培训延期两周，学员单位调整'):
    return post(c, '/api/social/lifecycle/' + kind + '/' + ident + '/changes', {'values': values, 'reason': reason})


def change_act(c, ident, action_, reason='同意变更', basis=''):
    item = c.get('/api/social/lifecycle/changes/' + ident).json()['item']
    return post(c, '/api/social/lifecycle/changes/' + ident + '/actions', {'action': action_, 'expected_version': item['version'], 'reason': reason, 'basis': basis})


def test_running_note_is_append_only_and_shows_in_timeline(setup_social, client2):
    c = client2
    pid = setup_social
    auth(c, 'teacher')
    v0 = detail(c, 'social_project', pid)['item']['version']
    r = post(c, '/api/social/lifecycle/project/' + pid + '/notes', {'tag': 'start', 'text': '第一期今天开班，到 28 人'})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d['running'] and d['timeline'][0]['what'] == '第一期今天开班，到 28 人' and d['timeline'][0]['source'] == 'self'
    assert detail(c, 'social_project', pid)['item']['version'] == v0  # 记一笔不动乐观锁版本
    assert post(c, '/api/social/lifecycle/project/' + pid + '/notes', {'tag': 'nope', 'text': 'x'}).status_code == 422
    auth(c, 'otherteacher')
    assert post(c, '/api/social/lifecycle/project/' + pid + '/notes', {'tag': 'other', 'text': '别人的项目'}).status_code == 403
    assert c.get('/api/social/lifecycle/project/' + pid).status_code == 403


def test_small_change_applies_directly_and_bumps_version(setup_social, client2):
    c = client2
    pid = setup_social
    auth(c, 'teacher')
    assert life(c, 'project', pid)['biz_version'] == 1
    r = change(c, 'project', pid, {'expected_participants': 36})  # 30 → 36，变动 20%
    assert r.status_code == 200, r.text
    d = r.json()
    assert d['applied'] and d['level'] == 'direct'
    assert d['archive']['biz_version'] == 2 and d['archive']['versions'][0]['v'] == 2
    assert detail(c, 'social_project', pid)['item']['data']['expected_participants'] == 36
    assert change(c, 'project', pid, {'expected_participants': 36}).status_code == 422  # 没有改动


def test_big_change_goes_college_then_school_while_project_keeps_running(setup_social, client2):
    c = client2
    pid = setup_social
    auth(c, 'teacher')
    r = change(c, 'project', pid, {'end_date': '2026-12-31'})  # 延期超过一个季度：学院 → 学校
    assert r.status_code == 200, r.text
    d = r.json()
    assert not d['applied'] and d['level'] == 'school'
    cid = d['change']['id']
    assert d['change']['state'] == 'COLLEGE'
    assert d['archive']['pending_change']['id'] == cid and not d['archive']['can']['change']
    assert change(c, 'project', pid, {'expected_outcomes': '再改一项'}).status_code == 409  # 一次只办一份变更
    # 审批期间原档案照常运行：还能导入明细
    auth(c, 'schooladmin')
    assert import_rows(c, pid, [row()]).status_code == 200
    auth(c, 'teacher')
    assert detail(c, 'social_project', pid)['item']['data']['end_date'] == '2026-09-02'
    assert change_act(c, cid, 'approve').status_code == 403  # 本人不能批
    auth(c, 'collegehead')
    todos = c.get('/api/todos').json()['items']
    assert any(x['type'] == 'life_change' and x['id'] == cid for x in todos)
    r = change_act(c, cid, 'approve')
    assert r.status_code == 200, r.text
    assert r.json()['item']['state'] == 'SCHOOL'
    auth(c, 'reviewer')
    r = change_act(c, cid, 'approve', '同意延期')
    assert r.status_code == 200, r.text
    assert r.json()['item']['state'] == 'ACTIVE'
    item = detail(c, 'social_project', pid)['item']
    assert item['state'] == 'FILED' and item['data']['end_date'] == '2026-12-31' and item['data']['biz_version'] == 2
    auth(c, 'teacher')
    v = life(c, 'project', pid)
    assert v['pending_change'] is None and [x['v'] for x in v['versions']] == [2, 1]
    assert '结束日期' in v['versions'][0]['summary']


def test_returned_change_leaves_archive_untouched_and_withdraw(setup_social, client2):
    c = client2
    pid = setup_social
    auth(c, 'teacher')
    cid = change(c, 'project', pid, {'expected_outcomes': '增加一项职业技能等级证书'}).json()['change']['id']
    auth(c, 'collegehead')
    assert change_act(c, cid, 'return', '').status_code == 422
    r = change_act(c, cid, 'return', '证书名称写具体')
    assert r.status_code == 200 and r.json()['item']['state'] == 'RETURNED'
    assert detail(c, 'social_project', pid)['item']['data']['expected_outcomes'] == '完成技能培训'
    auth(c, 'teacher')
    cid2 = change(c, 'project', pid, {'expected_outcomes': '增加茶艺师四级证书'}).json()['change']['id']
    r = change_act(c, cid2, 'withdraw', '先不改了')
    assert r.status_code == 200 and r.json()['item']['state'] == 'WITHDRAWN'
    assert life(c, 'project', pid)['pending_change'] is None


def test_change_conflicts_with_later_edit_is_refused(setup_social, client2, app2):
    from app.social_models import SocialProject
    c = client2
    pid = setup_social
    auth(c, 'teacher')
    cid = change(c, 'project', pid, {'expected_outcomes': '新的成果'}).json()['change']['id']
    with app2.state.sessions.begin() as db:
        p = db.get(SocialProject, pid)
        p.data = {**p.data, 'expected_outcomes': '别处改过'}
    auth(c, 'collegehead')
    r = change_act(c, cid, 'approve')
    assert r.status_code == 409 and '已被改过' in r.text


def test_college_raised_college_level_change_applies_directly(setup_social, client2):
    c = client2
    pid = setup_social
    auth(c, 'collegehead')
    r = change(c, 'project', pid, {'expected_outcomes': '学院调整预期成果'})
    assert r.status_code == 200, r.text
    assert r.json()['applied'] and r.json()['archive']['biz_version'] == 2


def test_change_only_while_running(setup_social, client2):
    c = client2
    pid = setup_social
    auth(c, 'schooladmin')
    assert import_rows(c, pid, [row()]).status_code == 200
    auth(c, 'teacher')
    closeout = {'closed_on': '2026-09-02', 'outcome_report': '结项报告', 'satisfaction': '96', 'actual_income': '0', 'finance_reference': '零收入', 'location': 'onsite'}
    assert action(c, 'projects', 'social_project', pid, 'close_submit', closeout=closeout).status_code == 200
    r = change(c, 'project', pid, {'expected_outcomes': '结项后再改'})
    assert r.status_code == 409 and '结项' in r.text
    assert life(c, 'project', pid)['can']['note'] is False


def test_teacher_project_submit_no_longer_blocked_by_report_info_but_close_is(app2, client2):
    from test_project_apply import setup as project_setup, teacher_project
    c = client2
    project_setup(app2)
    auth(c, 'teacher')
    p = teacher_project(c)
    proof(c, 'social_project', p['id'], p['version'])
    r = action(c, 'projects', 'social_project', p['id'], 'submit')
    assert r.status_code == 200 and r.json()['item']['data']['report_pending'] is True
    auth(c, 'collegehead')
    assert action(c, 'projects', 'social_project', p['id'], 'approve').status_code == 200
    auth(c, 'reviewer')
    assert action(c, 'projects', 'social_project', p['id'], 'file').status_code == 200
    auth(c, 'teacher')
    assert any('上报信息' in x for x in life(c, 'project', p['id'])['reminders'])
    closeout = {'closed_on': '2026-09-02', 'outcome_report': '结项报告', 'satisfaction': '96', 'actual_income': '0', 'finance_reference': '零收入', 'location': 'onsite'}
    r = action(c, 'projects', 'social_project', p['id'], 'close_submit', closeout=closeout)
    assert r.status_code == 409  # 先拦明细（尚无参训核算明细），上报信息在后面一并检查
    item = detail(c, 'social_project', p['id'])['item']
    r = put(c, '/api/social/projects/' + p['id'] + '/report-info', {'expected_version': item['version'], 'total_hours': '16', 'audiences': ['企业职工'],
            'service_types': ['national'], 'teaching_methods': ['classroom'], 'reason': '结项前补齐'})
    assert r.status_code == 200, r.text
    assert r.json()['item']['data']['report_pending'] is False


def test_course_hours_change_annual_and_stop(client2, app2):
    c = client2
    ids = app_setup(app2)
    auth(c, 'teacher')
    ident = apply_course(c, ids['K1'], hours='32').json()['item']['id']
    auth(c, 'collegehead')
    assert act(c, ident, 'approve').status_code == 200
    auth(c, 'reviewer')
    assert act(c, ident, 'approve').json()['item']['state'] == 'ACTIVE'
    auth(c, 'teacher')
    assert life(c, 'course', ident)['can']['annual'] is False  # 年度确认只给基地、师资
    r = change(c, 'course', ident, {'hours': '40'}, '增加 8 学时实操')  # 25%：学院批
    assert r.status_code == 200 and r.json()['level'] == 'college'
    cid = r.json()['change']['id']
    auth(c, 'collegehead')
    assert change_act(c, cid, 'approve').json()['item']['state'] == 'ACTIVE'
    auth(c, 'teacher')
    v = life(c, 'course', ident)
    assert v['biz_version'] == 2 and c.get('/api/applications/' + ident).json()['item']['data']['hours'] == '40'
    item = c.get('/api/applications/' + ident).json()['item']
    r = post(c, '/api/social/lifecycle/course/' + ident + '/stop', {'expected_version': item['version'], 'reason': '课程不再开设'})
    assert r.status_code == 200, r.text
    assert r.json()['state'] == 'STOPPED' and r.json()['can']['resume']
    assert post(c, '/api/social/lifecycle/course/' + ident + '/notes', {'tag': 'other', 'text': '停用后记一笔'}).status_code == 409
    item = c.get('/api/applications/' + ident).json()['item']
    r = post(c, '/api/social/lifecycle/course/' + ident + '/resume', {'expected_version': item['version'], 'reason': '重新开设'})
    assert r.status_code == 200 and r.json()['state'] == 'ACTIVE'


def test_base_annual_confirmation(setup_social, client2):
    c = client2
    auth(c, 'teacher')
    data = {'code': 'LIFE-B1', 'name': '茶园实践基地', 'location': '长沙县', 'onsite': False, 'partner': '某茶业公司', 'recognition': '共建协议',
            'usages': ['practice'], 'established_on': '2026-03-01'}
    r = post(c, '/api/applications/bases', {'data': data, 'reason': '申请基地'})
    assert r.status_code == 200, r.text
    ident = r.json()['item']['id']
    auth(c, 'collegehead')
    assert act(c, ident, 'approve').status_code == 200
    auth(c, 'reviewer')
    assert act(c, ident, 'approve').status_code == 200
    auth(c, 'teacher')
    v = life(c, 'base', ident)
    assert v['running'] and v['can']['annual']
    r = post(c, '/api/social/lifecycle/base/' + ident + '/annual', {'year': 2026, 'running': True, 'text': '今年接待 3 期'})
    assert r.status_code == 200, r.text
    assert not any('年度运行确认' in x for x in r.json()['reminders'])
    assert any(t['what'].startswith('年度运行确认') for t in r.json()['timeline'])
    r = change(c, 'base', ident, {'manager_name': '王老师'}, '负责人调整')
    assert r.status_code == 200 and r.json()['applied']
    r = change(c, 'base', ident, {'location': '浏阳市'}, '基地搬迁')
    assert r.status_code == 200 and r.json()['level'] == 'school'
    # 学院直接修改审批通过的基地资料会被拦，须走申请变更
    auth(c, 'collegehead')
    item = c.get('/api/applications/' + ident).json()['item']
    r = put(c, '/api/social/resources/' + ident, {'kind': 'base', 'org_id': item['org_id'], 'code': item['code'], 'name': '改名', 'expected_version': item['version'], 'reason': '直接改'})
    assert r.status_code in (409, 422)


def test_running_board_cards_and_changes(setup_social, client2):
    """列表上方的“X运行”卡片：老师看本人负责的，学院看本院的并带着待审批变更。"""
    c = client2
    pid = setup_social
    auth(c, 'teacher')
    cid = change(c, 'project', pid, {'end_date': '2026-12-31'}).json()['change']['id']
    body = c.get('/api/social/lifecycle/board/project')
    assert body.status_code == 200, body.text
    body = body.json()
    card = next(x for x in body['cards'] if x['id'] == pid)
    assert body['total'] >= 1 and card['running'] and card['state_label'] == '变更审批中' and card['pending']
    assert {'name', 'sub', 'stats', 'remind'} <= set(card)
    assert c.get('/api/social/lifecycle/board/nothing').status_code == 422
    auth(c, 'collegehead')
    college = c.get('/api/social/lifecycle/board/project').json()
    assert any(x['id'] == cid and x['rows'] and x['rows'][0]['to_text'] for x in college['changes'])
    auth(c, 'otherteacher')
    assert not c.get('/api/social/lifecycle/board/project').json()['cards']
