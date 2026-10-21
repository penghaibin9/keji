"""只读原表、版本选择、计量单位、筛选同源和学校角色边界。"""
from hashlib import sha256
import openpyxl
import pytest
from fastapi import HTTPException
from app.school_cockpit import load_reports, summarize
from conftest import auth, post


def source(root, college, year, rows, *, name='社会培训人次统计表.xlsx', total=None):
    directory = root / f'{year}年社会培训资料' / college
    directory.mkdir(parents=True, exist_ok=True)
    w = openpyxl.Workbook(); s = w.active
    s.append([f'{college}{year}年'+('1-8月' if year == 2026 else '')+'开展社会培训情况统计表'])
    s.append([f'学院/部门名称：{college} 部门负责人：合成人员 经办人：合成人员'])
    s.append(['序号','培训项目名称','培训人数','培训课时',*(['当量系数'] if year == 2025 else []),'培训人次数','培训人次分配情况','资料情况','备注'])
    for row in rows: s.append(row)
    total_row = ['总结'] + [None] * (5 if year == 2025 else 4)
    total_row[-1] = total; s.append(total_row)
    p = directory / name; w.save(p); w.close(); return p


@pytest.fixture
def reports(tmp_path):
    root = tmp_path / 'school'
    source(root,'合成甲学院',2025,[[1,'旧项目',10,8,1,10],[None,None,5,8,1,5],[2,'另一项目',0,8,1,0]])
    source(root,'合成甲学院',2026,[[1,'过期版本',999,8,999]], total=999)
    source(root,'合成甲学院',2026,[[1,'模块项目',102,16,'204人次'],[2,'零记录',0,8,0]],name='更新版社会培训人次统计表.xlsx',total=0)
    source(root,'合成乙学院',2026,[[1,'人天项目',10,16,'20人天']],total=0)
    return root


def test_units_versions_zero_continuations_and_readonly(reports):
    before={str(p):sha256(p.read_bytes()).hexdigest() for p in reports.rglob('*.xlsx')}
    catalog=load_reports(reports); d=summarize(catalog)
    assert d['totals']=={'person_times':'204','person_days':'20','raw_conversions':None,'records':3,'colleges':2,'person_times_colleges':1}
    assert len(d['excluded'])==1 and '过期版本' not in str(d['details'])
    assert len(d['warnings'])==2 and '原表合计为0' in d['warnings'][0]['text']
    assert d['comparison'][0]['records']==2
    old=summarize(catalog,year=2025)
    assert old['totals']['records']==2 and len(old['details'])==3 and old['totals']['raw_conversions']=='15'
    project=old['projects'][0]['id']
    selected=summarize(catalog,year=2025,project=project)
    assert selected['totals']['records']==1 and len(selected['details'])==2 and selected['totals']['raw_conversions']=='15'
    assert sum(x['value'] for x in d['composition'])==d['totals']['records']
    assert sum(int(x['value']) for x in d['rank'])==int(d['totals']['person_times'])
    zero=summarize(catalog,project=next(x['id'] for x in d['projects'] if x['name']=='零记录'))
    assert zero['totals']['person_times']=='0' and zero['totals']['records']==1
    missing=summarize(catalog,year=2025,college='合成乙学院')
    assert missing['totals']['person_times'] is None and missing['table'][0]['selected_records'] is None
    assert all(not any(k in row for k in ['allocation','participants_raw','teacher_id','approved']) for row in d['details'])
    assert before=={str(p):sha256(p.read_bytes()).hexdigest() for p in reports.rglob('*.xlsx')}
    assert load_reports(reports) is catalog


def test_filter_validation_and_ambiguous_sources(reports):
    catalog=load_reports(reports)
    for filters in ({'year':2024},{'college':'越权来源'},{'project':'unknown'}):
        with pytest.raises(HTTPException) as exc:summarize(catalog,**filters)
        assert exc.value.status_code==422
    source(reports,'合成乙学院',2026,[[1,'冲突版本',10,8,10]],name='另一份人次统计表.xlsx')
    with pytest.raises(HTTPException) as exc:load_reports(reports)
    assert exc.value.status_code==503
    assert summarize(None)['available'] is False


def test_api_requires_school_role_and_permissions(client2,app2,reports):
    app2.state.settings.school_reports_dir=reports
    assert client2.get('/api/social/cockpit').status_code==401
    for user in ['teacher','depthead','collegehead']:
        auth(client2,user)
        assert client2.get('/api/social/cockpit').status_code==403
    auth(client2,'schooladmin')
    response=client2.get('/api/social/cockpit')
    assert response.status_code==200
    assert response.json()['totals']['person_times']=='204'
    d=response.json(); p=next(x for x in d['projects'] if x['college']=='合成乙学院')
    picked=client2.get('/api/social/cockpit',params={'college':'合成乙学院','project':p['id']}).json()
    assert picked['totals']['person_days']=='20' and picked['totals']['records']==1
    assert picked['totals']['person_times'] is None
    assert str(reports) not in response.text and '合成人员' not in response.text
    app2.state.settings.school_reports_dir=None
    assert client2.get('/api/social/cockpit').json()['available'] is False


def test_import_links_require_college_year_and_identical_original(client2, app2, tmp_path):
    from io import BytesIO
    from test_ledgers import upload
    from app.models import Org
    with app2.state.sessions.begin() as db:
        db.get(Org, 'college1').name = '测试一学院'
        db.get(Org, 'college2').name = '测试二学院'
    root = tmp_path / 'matched-reports'
    path = source(root, '测试一学院', 2026, [[1, '原表人天项目', 10, 16, '20人天']])
    raw = path.read_bytes()
    app2.state.settings.school_reports_dir = root
    auth(client2, 'schooladmin')
    initial = client2.get('/api/social/cockpit')
    assert initial.status_code == 200, initial.text
    before = initial.json()
    assert before['table'][0]['ledger'] is None
    for org, year in [('college2', 2026), ('college1', 2025)]:
        response = upload(client2, '/api/social/ledgers', raw, org_id=org, year=str(year), reason='隔离测试错误对应')
        assert response.status_code == 200, response.text
    assert client2.get('/api/social/cockpit').json()['table'][0]['ledger'] is None
    saved = upload(client2, '/api/social/ledgers', raw, org_id='college1', year='2026', reason='隔离测试正确对应').json()
    response = client2.get('/api/social/cockpit').json()
    link = response['table'][0]['ledger']
    assert link == {'id': saved['id'], 'year': 2026, 'version_no': 1, 'review_state': '待核定', 'is_latest': True}
    assert response['details'][0]['ledger'] == link
    assert saved['reported_quantities'] == [{'unit': '人天', 'value': '20'}]
    reviewed = post(client2, f'/api/social/ledgers/{saved["id"]}/review', {
        'expected_version': saved['version'], 'rows': [{'row_no': 4, 'approved': '7', 'reason': '隔离测试核定'}], 'reason': '隔离测试核定'})
    assert reviewed.status_code == 200, reviewed.text
    response = client2.get('/api/social/cockpit').json()
    assert response['table'][0]['ledger']['review_state'] == '已核定'
    assert response['totals'] == before['totals'] and response['details'][0]['value'] == '20'
    workbook = openpyxl.load_workbook(BytesIO(raw)); workbook.active['E4'] = '30人天'
    revised = BytesIO(); workbook.save(revised); workbook.close()
    assert upload(client2, '/api/social/ledgers', revised.getvalue(), org_id='college1', year='2026', reason='隔离测试新版台账').status_code == 200
    response = client2.get('/api/social/cockpit').json()
    assert response['table'][0]['ledger']['is_latest'] is False
    assert response['totals'] == before['totals'] and path.read_bytes() == raw


def test_reported_quantities_preserve_units_missing_values_and_zero():
    from app.routes.ledgers import reported_quantities
    assert reported_quantities([
        ('2025', [{'claimed': '100', 'claimed_raw': '100'}]),
        ('2026', [{'claimed': '0', 'claimed_raw': '0人次'}, {'claimed': '20', 'claimed_raw': '20人天'}])
    ]) == [{'unit': '原表折算量', 'value': '100'}, {'unit': '人次', 'value': '0'}, {'unit': '人天', 'value': '20'}]
    assert reported_quantities([('2026', [{'claimed': None, 'claimed_raw': ''}, {'claimed': '0', 'claimed_raw': '0'}])]) == [{'unit': '人次', 'value': None}]


def test_school_and_other_ledger_scopes_preserve_all_api_and_adopted_versions(client2, app2, reports):
    from app.models import Org
    from test_ledgers import upload, sheet
    with app2.state.sessions.begin() as db:
        db.get(Org, 'college1').name = '合成甲学院'
        db.get(Org, 'college2').name = '合成乙学院'
        db.add(Org(id='arts-source', code='ARTS-SOURCE', name='合成艺术学院', kind='college', parent_id='school'))
        db.add(Org(id='test-only', code='TEST-ONLY', name='测试学院一', kind='college', parent_id='school'))
    source(reports, '合成艺术学院', 2025, [[1, '仅2025年资料', 10, 8, 1, 10]])
    app2.state.settings.school_reports_dir = reports
    auth(client2, 'schooladmin')
    catalog = load_reports(reports)
    saved = {}
    for college, org in [('合成甲学院', 'college1'), ('合成乙学院', 'college2')]:
        report = next(r for r in catalog['reports'] if r['college'] == college and r['period']['year'] == 2026)
        path = next(p for p in reports.rglob(report['file']) if sha256(p.read_bytes()).hexdigest() == report['id'])
        result = upload(client2, '/api/social/ledgers', path.read_bytes(), org_id=org, year='2026', reason='隔离采用原表导入')
        assert result.status_code == 200, result.text
        saved[org] = result.json()['id']
    newer = upload(client2, '/api/social/ledgers', sheet(rows=[[1, '其他新版', 999, 8, '999人次']], college='合成甲学院'), org_id='college1', year='2026', reason='隔离其他版本').json()
    test_ledger = upload(client2, '/api/social/ledgers', sheet(rows=[[1, '隔离线上样本', '在线浏览160左右', 8, '160人次']], college='测试学院一'), org_id='test-only', year='2026', reason='隔离原有测试台账').json()
    school = client2.get('/api/social/ledgers?source=school').json()
    assert school['source'] == 'school' and school['source_catalog_available'] is True and school['year'] == 2026
    assert [p['year'] for p in school['source_periods']] == [2025, 2026]
    assert '2026年1—8月' in school['source_note']
    assert {r['id'] for r in school['items']} == set(saved.values())
    assert {q['unit']: q['value'] for q in school['reported_quantities']} == {'人次': '204', '人天': '20'}
    assert school['missing'] == [{'org_id': 'arts-source', 'org_name': '合成艺术学院', 'source_status': '原表未提供，待补资料'}]
    assert school['online'] == {'views': '0', 'projects': 0}
    assert all(len(r['versions']) == 1 for r in school['items'])
    other = client2.get('/api/social/ledgers?year=2026&source=other').json()
    assert {r['id'] for r in other['items']} == {newer['id'], test_ledger['id']}
    assert other['reported_quantities'] == [{'unit': '人次', 'value': '1159'}]
    assert other['online'] == {'views': '160', 'projects': 1} and other['missing'] == []
    unscoped = client2.get('/api/social/ledgers?year=2026').json()
    assert unscoped['source'] == 'all' and len(unscoped['items']) == 3
    versions = next(r['versions'] for r in unscoped['items'] if r['org_id'] == 'college1')
    assert {r['id'] for r in versions} == {saved['college1'], newer['id']}
    assert client2.get('/api/social/ledgers?year=2027&source=school').status_code == 422
    assert client2.get('/api/social/ledgers?year=2027&source=other').json()['items'] == []
    assert client2.get('/api/social/ledgers?source=invalid').status_code == 422
    app2.state.settings.school_reports_dir = reports / 'missing'
    assert client2.get('/api/social/ledgers?year=2026&source=school').status_code == 503
    assert client2.get('/api/social/ledgers?year=2026').status_code == 200
    app2.state.settings.school_reports_dir = None
    fallback = client2.get('/api/social/ledgers?year=2026&source=school').json()
    assert fallback['source'] == 'all' and fallback['source_catalog_available'] is False and len(fallback['items']) == 3
    auth(client2, 'collegehead')
    app2.state.settings.school_reports_dir = reports
    scoped = client2.get('/api/social/ledgers?year=2026&source=school').json()
    assert [r['id'] for r in scoped['items']] == [saved['college1']] and scoped['missing'] == []
