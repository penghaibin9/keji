"""学院台账报送、口径体检、核定与首页指标；合成数据，按学校 2025/2026 两版统计表格式构造。"""
from io import BytesIO
import uuid
from decimal import Decimal
import openpyxl
import pytest
from app import ledger_check as lc
from conftest import auth, post


def sheet(template='2026', rows=None, college='测试学院一', year=2026):
    wb = openpyxl.Workbook(); ws = wb.active
    ws.append([f'{college}{year}年1-8月开展社会培训情况统计表'])
    ws.append([f'学院/部门名称： {college}   部门负责人：张三   经办人：李四   日期：{year}年8月'])
    if template == '2025':
        ws.append(['序号', '培训名称', '培训人数', '培训课时', '当量系数', '计算人次数', '培训人次分配情况', '资料情况', '备注'])
    else:
        ws.append(['序号', '培训项目名称', '培训人数', '培训课时', '培训人次数', '培训人次分配情况', '资料情况', '备注'])
    for r in rows or []: ws.append(r)
    ws.append(['总结'])
    ws.append(['资料要求：社会培训项目完成后，需提交资料'])
    out = BytesIO(); wb.save(out); return out.getvalue()


def checked(data):
    return lc.check(lc.parse(data, 'ledger.xlsx'))


def codes(row):
    return {i['code'] for i in row['issues']}


def test_long_allocation_names_are_preserved_for_exact_identity_binding():
    assert lc.parse_allocations('测试教师一：15、共同授课测试教师：15') == [
        ('测试教师一', Decimal('15')), ('共同授课测试教师', Decimal('15'))]
    result=checked(sheet(rows=[[1,'隔离长姓名项目',30,8,30,'测试教师一：15、共同授课测试教师：15','2,3,4','']]))
    assert [item['name'] for item in result['rows'][0]['allocations']] == ['测试教师一','共同授课测试教师']


def test_2025_missing_divide_by_eight_and_online_views():
    data = sheet('2025', [[1, '职业启蒙进校园', 342, 8, 1, 2736, '样例教师乙600、样例教师丙600、样例教师丁1200、样例教师戊336', '2，4', ''],
                          [2, '会客厅直播', 415500, 1, 1, 51937, '人工智能学院100%', '2，3,4', ''],
                          [3, '技能培训', 45, 10, 1, '=(C6*D6*E6)/8', '样例教师己56', '2,3', '']], college='测试学院一', year=2025)
    r = checked(data)
    assert r['template'] == '2025' and r['meta']['college'] == '测试学院一' and r['meta']['year'] == 2025
    first, online, formula = r['rows']
    assert 'MISSING_DIV8' in codes(first) and first['recommended'] == '342'
    assert 'ONLINE_VIEWS' not in codes(online) and 'LARGE_COUNT' in codes(online)
    assert online['recommended'] == online['claimed'] == '51937'
    assert formula['claimed'] == '56.25' and not {'MISSING_DIV8', 'FORMULA_MISMATCH'} & codes(formula)


def test_2026_modes_allocation_and_never_above_claimed():
    r = checked(sheet('2026', [[1, '人天式脱产班', 116, 80, '1160人天', '软件学院', '合同、签到', ''],
                               [2, '公益课', 1053, 2, 2106, '样例教师甲：2106', '活动照片', ''],
                               [3, '模块课', 102, 96, '204人次', '模块一/102 模块二/102', '花名册', ''],
                               [4, '对不上', 100, 2, 300, '样例教师甲：200', '名单', ''],
                               [5, '分配超额', 1000, 1, 1000, '样例教师甲：1500', '名单', ''],
                               [6, '7天线上公益课', '在线浏览19000左右', 1, 19000, '样例教师甲：19000', '截图', '']]))
    days, lecture, modules, unclear, over, online = r['rows']
    assert days['mode'] == '人天式' and days['recommended'] == '1160' and not days['issues']
    assert 'PEOPLE_X_HOURS' in codes(lecture) and 'NO_ROSTER' in codes(lecture)
    assert lecture['recommended'] == lecture['claimed'] == '2106' and lecture['needs_mode_confirmation']
    assert lecture['trial_candidates'] and not any('把课时数当成了模块数' in x['text'] for x in lecture['issues'])
    assert modules['mode'] == '模块式（2个模块）'
    assert 'MODE_UNCLEAR' in codes(unclear) and unclear['recommended'] == unclear['claimed'] and unclear['needs_mode_confirmation']
    assert 'ALLOC_OVER' in codes(over) and over['recommended'] == over['claimed']
    assert 'ONLINE_VIEWS' in codes(online) and online['recommended'] == '0'
    assert r['summary']['serious'] == 1


def test_rejects_unknown_layout():
    wb = openpyxl.Workbook(); wb.active.append(['随便', '一张表']); out = BytesIO(); wb.save(out)
    with pytest.raises(Exception) as exc: lc.parse(out.getvalue(), 'x.xlsx')
    assert '表头' in str(exc.value.detail)


def upload(client, path, data, **form):
    return client.post(path, headers={'Idempotency-Key': str(uuid.uuid4())}, data=form,
                       files={'file': ('台账.xlsx', data, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})


def test_submit_review_and_overview_scope(client2):
    data = sheet('2026', [[1, '人天式脱产班', 16, 16, 32, '测试教师一：32', '签到表', ''],
                          [2, '公益课', 200, 2, 400, '测试教师一：400', '照片', '']])
    auth(client2, 'collegehead')
    preview = upload(client2, '/api/social/ledgers/preview', data)
    assert preview.status_code == 200, preview.text
    assert preview.json()['suggested_org_id'] == 'college1'
    r = upload(client2, '/api/social/ledgers', data, org_id='college1', year='2026', reason='学院报送 1-8 月台账')
    assert r.status_code == 200, r.text
    ledger = r.json()
    assert ledger['totals'] == {'claimed_total': '432', 'recommended_total': '432', 'approved_rows': 0, 'pending_rows': 2, 'final_total': '432', 'state': '待核定'}
    again = upload(client2, '/api/social/ledgers', data, org_id='college1', year='2026', reason='重复报送')
    assert again.status_code == 409
    other = upload(client2, '/api/social/ledgers', data, org_id='college2', year='2026', reason='越权报送')
    assert other.status_code == 403
    review = post(client2, f'/api/social/ledgers/{ledger["id"]}/review', {'expected_version': ledger['version'], 'rows': [{'row_no': 4, 'approved': '32'}], 'reason': '学院不能核定'})
    assert review.status_code == 403

    auth(client2, 'schooladmin')
    bad = post(client2, f'/api/social/ledgers/{ledger["id"]}/review', {'expected_version': ledger['version'], 'rows': [{'row_no': 5, 'approved': '100'}], 'reason': '核定'})
    assert bad.status_code == 422 and '理由' in bad.text
    ok = post(client2, f'/api/social/ledgers/{ledger["id"]}/review', {'expected_version': ledger['version'], 'rows': [{'row_no': 4, 'approved': '32'}, {'row_no': 5, 'approved': '100', 'reason': '财务证明到场 100 人'}], 'reason': '继教学院核定'})
    assert ok.status_code == 200, ok.text
    assert ok.json()['totals']['state'] == '已核定' and ok.json()['totals']['final_total'] == '132' and ok.json()['state'] == 'ACTIVE'
    listing = client2.get('/api/social/ledgers?year=2026').json()
    assert [x['org_name'] for x in listing['items']] == ['测试学院一'] and listing['missing'] == [{'org_id': 'college2', 'org_name': '测试学院二'}]
    school = client2.get('/api/social/overview?year=2026').json()
    assert school['scope'] == '全校' and school['participants']['final'] == '132' and school['participants']['claimed'] == '432'
    assert school['participants']['pending_ledgers'] == 0 and school['can_review'] is True and school['points'] is None

    auth(client2, 'teacher')
    mine = client2.get('/api/social/overview?year=2026').json()
    assert mine['scope'] == '本人' and mine['participants']['mine'] == {'value': '432', 'projects': 2}
    assert mine['points'] == {'year': '0', 'five_years': '0', 'five_year_target': '340', 'title_points': '0', 'trial': None, 'trial_claims': 0} and mine['dual']['mine'] is None and mine['can_review'] is False
    # 招标第2项：教师仅本人数据。整院台账含全院教师人次分配，教师和教研室均不可读，本人分配在 /social/mine 查看。
    assert client2.get(f'/api/social/ledgers/{ledger["id"]}').status_code == 403
    assert client2.get('/api/social/ledgers?year=2026').status_code == 403
    assert upload(client2, '/api/social/ledgers/preview', data).status_code == 403
    auth(client2, 'depthead')
    assert client2.get(f'/api/social/ledgers/{ledger["id"]}').status_code == 403
    assert client2.get('/api/social/targets?year=2026').status_code == 403
    assert client2.get('/api/social/departments?year=2026').status_code == 200
    auth(client2, 'otherteacher')
    assert client2.get(f'/api/social/ledgers/{ledger["id"]}').status_code == 403
    assert client2.get('/api/social/overview?year=2026').json()['participants']['final'] == '0'


def put_json(client, path, payload):
    return client.put(path, json=payload, headers={'Idempotency-Key': str(uuid.uuid4())})


def test_drafts_online_figure_targets_and_estimate(client2):
    data = sheet('2026', [[1, '2026.3.14线下公益课', 40, 2, 40, '测试教师一：40', '签到表', ''],
                          [2, '人天式脱产班', 16, 16, 32, '外校老师：32', '签到表', ''],
                          [3, '7天线上公益课', '在线浏览19000左右', 1, 19000, '测试教师一：19000', '截图', '']])
    auth(client2, 'collegehead')
    ledger = upload(client2, '/api/social/ledgers', data, org_id='college1', year='2026', reason='学院报送').json()
    assert ledger['online'] == {'views': '19000', 'projects': 1}
    bound=post(client2,f'/api/social/ledgers/{ledger["id"]}/rows/5/project-link',{'expected_version':ledger['version'],'action':'owner','owner_id':'collegehead','reason':'外校授课人员不能推测负责人，明确本院承办负责人'})
    assert bound.status_code==200,bound.text
    ledger=bound.json()
    made = post(client2, f'/api/social/ledgers/{ledger["id"]}/projects', {'expected_version': ledger['version'], 'reason': '台账生成项目草稿'})
    assert made.status_code == 200, made.text
    body = made.json()
    assert [m['row_no'] for m in body['made']] == [4, 5] and body['skipped'][0]['row_no'] == 6 and body['drafts'] == 2
    assert body['made'][0]['owner'] == '测试教师一' and body['made'][1]['owner'] == '测试学院负责人'
    again = post(client2, f'/api/social/ledgers/{ledger["id"]}/projects', {'expected_version': body['version'], 'rows': [4, 5], 'reason': '重复生成'})
    assert again.status_code == 409
    projects = client2.get('/api/social/workspace?section=projects').json()['projects']
    first = next(p for p in projects if p['id'] == body['made'][0]['project_id'])
    assert first['state'] == 'DRAFT' and first['data']['start_date'] == '2026-03-14' and first['data']['class_type'] == 'lecture' and first['data']['category'] == 'community'
    assert put_json(client2, '/api/social/targets', {'year': 2026, 'items': [{'org_id': 'college1', 'participants': '100'}], 'reason': '学院不能下达'}).status_code == 403
    assert post(client2, f'/api/social/ledgers/{ledger["id"]}/school-figure', {'expected_version': body['version'], 'value': '60', 'reason': '学院不能登记'}).status_code == 403

    auth(client2, 'schooladmin')
    fig = post(client2, f'/api/social/ledgers/{ledger["id"]}/school-figure', {'expected_version': body['version'], 'value': '60', 'reason': '学校人工核定 60 人次'})
    assert fig.status_code == 200, fig.text
    assert fig.json()['school_figure']['value'] == '60' and fig.json()['school_figure']['diff'] == '12'
    saved = put_json(client2, '/api/social/targets', {'year': 2026, 'items': [{'org_id': 'college1', 'income': '100', 'participants': '72'}], 'reason': '下达年度目标'})
    assert saved.status_code == 200, saved.text
    t = client2.get('/api/social/targets?year=2026').json()
    row = next(x for x in t['items'] if x['org_id'] == 'college1')
    assert row['actual']['participants'] == '72' and row['actual']['income'] == '0'
    assert row['estimate']['metrics'][0]['completion'] == '0' and row['estimate']['metrics'][1]['score'] == '20'
    assert row['estimate']['total'] is None and '重点群体目标' in row['estimate']['missing']
    put_json(client2, '/api/social/targets', {'year': 2026, 'items': [{'org_id': 'college1', 'income': '100', 'participants': '72', 'priority': '10'}], 'reason': '补下达重点群体目标'})
    row = next(x for x in client2.get('/api/social/targets?year=2026').json()['items'] if x['org_id'] == 'college1')
    assert row['estimate']['total'] is None and row['estimate']['missing'] == ['重点群体实际数']
    put_json(client2, '/api/social/targets', {'year': 2026, 'items': [{'org_id': 'college1', 'income': '100', 'participants': '72', 'priority': '10', 'priority_actual': '8'}], 'reason': '登记重点群体实际人次'})
    est = next(x for x in client2.get('/api/social/targets?year=2026').json()['items'] if x['org_id'] == 'college1')['estimate']
    # 项目尚无财务到账：收入 0 + 人次 20 + 重点群体 8 + 成果 0 + 资金 10 = 38。
    assert est['total'] == '38' and est['grade'] == '不合格' and est['missing'] == []
    over = client2.get('/api/social/overview?year=2026').json()
    assert over['participants']['completion'] == '100' and over['online']['views'] == '19000'
