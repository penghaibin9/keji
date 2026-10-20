"""历史来源只补真实事实；不创建项目，不重放审批，测试均为隔离合成资料。"""
from copy import deepcopy
import uuid
import pytest
from sqlalchemy import select
from app.models import Org, Role, Attachment
from app.social_models import SocialResource, SocialProject
from conftest import auth
from test_ledgers import upload, sheet
from test_school_cockpit import source
from test_social_images import png


@pytest.fixture
def history_sources(tmp_path, client2, app2):
    with app2.state.sessions.begin() as db:
        db.get(Org, 'college1').name = '合成历史学院'
    root = tmp_path / 'history'
    path = source(root, '合成历史学院', 2025, [[1, '原报零值项目', 0, 8, 1, 0], [None, None, 5, 8, 1, 5], [2, '另一历史项目', 2, 8, 1, 2]])
    app2.state.settings.school_reports_dir = root
    auth(client2, 'schooladmin')
    saved = upload(client2, '/api/social/ledgers', path.read_bytes(), org_id='college1', year='2025', reason='隔离历史原件报送').json()
    return saved


def empty_facts():
    return {'owner': {'name': None, 'role': None, 'evidence': None, 'account_id': None}, 'date_facts': [],
            'date_prefill': None, 'confirmed_start': None, 'confirmed_end': None, 'conflicts': [], 'pending_notes': [], 'attachment_ids': []}


def save(client, ledger, row, history, *, key=None, version=None):
    return client.put(f'/api/social/history-projects/{ledger["id"]}/{row}/facts', headers={'Idempotency-Key': key or str(uuid.uuid4())},
                      json={'expected_version': version or ledger['version'], 'reason': '隔离材料逐项核对', 'history': history})


def test_projection_keeps_zero_and_continuations_without_creating_projects(history_sources, client2, app2):
    listing = client2.get('/api/social/history-projects').json()
    assert listing['total'] == 2 and listing['counts'] == {'all': 2, 'missing': 2, 'conflict': 0}
    first = listing['items'][0]
    assert first['source_rows'] == [4, 5] and first['history'] == empty_facts()
    detail = client2.get(f'/api/social/history-projects/{history_sources["id"]}/4').json()
    assert [r['claimed'] for r in detail['rows']] == ['0', '5']
    assert client2.get(f'/api/social/history-projects/{history_sources["id"]}/5').status_code == 404
    newer = upload(client2, '/api/social/ledgers', sheet(rows=[[1, '无关新版本', 10, 8, 10]]), org_id='college1', year='2025', reason='隔离无关新版本').json()
    assert client2.get('/api/social/history-projects').json()['items'][0]['ledger_id'] == history_sources['id']
    assert client2.get(f'/api/social/history-projects/{newer["id"]}/4').status_code == 404
    with app2.state.sessions.begin() as db:
        assert db.scalars(select(SocialProject)).all() == []


def test_null_facts_idempotency_and_version_are_real(history_sources, client2, app2):
    key = str(uuid.uuid4())
    h = empty_facts(); h['pending_notes'] = ['隔离原表第4行列有完成人，不能认定为项目负责人']
    first = save(client2, history_sources, 4, h, key=key)
    assert first.status_code == 200, first.text
    repeated = save(client2, history_sources, 4, h, key=key)
    assert repeated.status_code == 200 and repeated.json() == first.json()
    assert first.json()['history']['confirmed_start'] is None and first.json()['history']['owner']['account_id'] is None
    assert save(client2, history_sources, 4, h).status_code == 409
    with app2.state.sessions.begin() as db:
        obj = db.get(SocialResource, history_sources['id'])
        assert obj.version == history_sources['version'] + 1 and obj.data['rows'][0]['claimed'] == '0'
        assert obj.data['rows'][0]['approved'] is None and 'history' not in obj.data['rows'][1]


def test_date_nature_cannot_turn_plans_or_news_into_actual(history_sources, client2):
    h = empty_facts(); h['date_facts'] = [{'kind': 'planned', 'text': '拟于六月培训', 'evidence': '隔离方案第2页', 'start_date': '2025-06-01', 'end_date': '2025-06-05'}]
    h['confirmed_start'], h['confirmed_end'] = '2025-06-01', '2025-06-05'
    assert save(client2, history_sources, 4, h).status_code == 422
    h['date_facts'][0]['kind'] = 'news'
    assert save(client2, history_sources, 4, h).status_code == 422
    h['date_facts'][0]['kind'] = 'actual'
    h['conflicts'] = ['隔离方案与实际签到期间不一致']
    assert save(client2, history_sources, 4, h).status_code == 422
    h['conflicts'] = []
    result = save(client2, history_sources, 4, h)
    assert result.status_code == 200, result.text
    assert result.json()['history']['confirmed_end'] == '2025-06-05'
    h['confirmed_start'] = h['confirmed_end'] = None
    h['conflicts'] = ['隔离方案与实际签到期间不一致']
    assert save(client2, history_sources, 6, h, version=result.json()['ledger_version']).status_code == 200
    assert client2.get('/api/social/history-projects?year=2025&issue=conflict').json()['total'] == 1
    assert client2.get('/api/social/history-projects?year=2026').status_code == 422


def test_history_permissions_do_not_open_whole_college_to_teachers(history_sources, client2):
    assert client2.get('/api/social/workspace?section=projects').json()['history_available'] is True
    auth(client2, 'collegehead')
    assert client2.get('/api/social/history-projects').json()['total'] == 2
    for username in ('teacher', 'depthead'):
        auth(client2, username)
        assert client2.get('/api/social/workspace?section=projects').json()['history_available'] is False
        assert client2.get('/api/social/history-projects').status_code == 403
        assert client2.get(f'/api/social/history-projects/{history_sources["id"]}/4').status_code == 403
        assert save(client2, history_sources, 4, empty_facts()).status_code == 403


def test_project_materials_must_belong_to_ledger_and_exclude_original(history_sources, client2, app2):
    h = empty_facts(); h['attachment_ids'] = [history_sources['data']['file']['id']]
    assert save(client2, history_sources, 4, h).status_code == 422
    other = upload(client2, '/api/social/ledgers', sheet(rows=[[1, '其他版本', 10, 8, 10]]), org_id='college1', year='2025', reason='隔离其他台账').json()
    h['attachment_ids'] = [other['data']['file']['id']]
    assert save(client2, history_sources, 4, h).status_code == 422
    response = client2.post('/api/attachments/social_resource/' + history_sources['id'],
        headers={'Idempotency-Key': str(uuid.uuid4())}, data={'expected_version': history_sources['version'], 'reason': '隔离本项目专属图片'}, files={'file': ('项目佐证.png', png(), 'image/png')})
    assert response.status_code == 200, response.text
    version = client2.get('/api/social/ledgers/' + history_sources['id']).json()['version']
    attachment = response.json()['id']
    h['attachment_ids'] = [attachment, attachment]
    assert save(client2, history_sources, 4, h, version=version).status_code == 422
    h['attachment_ids'] = [attachment]
    result = save(client2, history_sources, 4, h, version=version)
    assert result.status_code == 200 and result.json()['attachments'][0]['id'] == attachment
    with app2.state.sessions.begin() as db:
        role = db.get(Role, 'role-school'); role.permissions = [p for p in role.permissions if p != 'file.read']
    auth(client2, 'schooladmin')
    read = client2.get(f'/api/social/history-projects/{history_sources["id"]}/4').json()
    assert read['attachments'] == [] and read['can_read_files'] is False


def test_owner_account_requires_matching_evidence_and_person(history_sources, client2):
    h = empty_facts(); h['owner'] = {'name': '来源里的真实姓名', 'role': '项目负责人', 'evidence': '隔离负责人签字页', 'account_id': 'schooladmin'}
    assert save(client2, history_sources, 4, h).status_code == 422
    h['owner'] = {'name': '测试教师一', 'role': '完成人', 'evidence': '隔离完成人列表', 'account_id': 'teacher'}
    assert save(client2, history_sources, 4, h).status_code == 422


def test_discrete_actual_dates_cannot_be_joined_into_full_period(history_sources, client2):
    h = empty_facts()
    h['date_facts'] = [{'kind': 'actual', 'text': '首日活动', 'evidence': '隔离活动照片', 'start_date': '2025-06-01'},
                       {'kind': 'actual', 'text': '另一活动结束', 'evidence': '隔离报道', 'end_date': '2025-06-05'}]
    h['confirmed_start'], h['confirmed_end'] = '2025-06-01', '2025-06-05'
    assert save(client2, history_sources, 4, h).status_code == 422


def test_date_prefill_is_shared_by_ledger_and_history_without_confirmation(history_sources, client2):
    h = empty_facts()
    h['conflicts'] = ['原表活动日明确，候选材料归属仍待核对']
    h['date_prefill'] = {'kind': 'source', 'text': '按原表本条单日服务预填，待学校复核', 'evidence': '合成原表第4行',
                         'start_date': '2025-06-15', 'end_date': '2025-06-15'}
    saved = save(client2, history_sources, 4, h)
    assert saved.status_code == 200, saved.text
    item = saved.json()
    assert item['history']['confirmed_start'] is None and item['history']['confirmed_end'] is None
    assert item['status'] == '有冲突待核对' and '历史预填日期待学校复核' in item['missing']
    ledger = client2.get(f'/api/social/ledgers/{history_sources["id"]}').json()
    assert ledger['data']['rows'][0]['history'] == item['history']
    assert ledger['data']['rows'][0]['claimed'] == '0' and ledger['data']['rows'][0]['approved'] is None
    assert 'history' not in ledger['data']['rows'][1]
    listing = client2.get('/api/social/history-projects?issue=prefill').json()
    assert listing['date_prefill_count'] == listing['total'] == 1
    assert listing['items'][0]['history']['date_prefill'] == h['date_prefill']
    auth(client2, 'teacher')
    assert client2.get('/api/social/history-projects?issue=prefill').status_code == 403


@pytest.mark.parametrize('change', [
    {'end_date': None}, {'start_date': '2025-06-16'}, {'evidence': ' '}, {'kind': 'planned'}, {'status': 'confirmed'},
])
def test_date_prefill_rejects_missing_endpoints_evidence_and_confirmation_flag(history_sources, client2, change):
    h = empty_facts()
    h['date_prefill'] = {'kind': 'source', 'text': '合成单日服务日期预填', 'evidence': '合成原表第4行',
                         'start_date': '2025-06-15', 'end_date': '2025-06-15', **change}
    assert save(client2, history_sources, 4, h).status_code == 422


def test_date_prefill_alone_never_supports_confirmed_period(history_sources, client2):
    h = empty_facts()
    h['date_prefill'] = {'kind': 'actual', 'text': '合成证明日期建议', 'evidence': '合成证明第2页',
                         'start_date': '2025-06-01', 'end_date': '2025-06-05'}
    h['confirmed_start'], h['confirmed_end'] = '2025-06-01', '2025-06-05'
    assert save(client2, history_sources, 4, h).status_code == 422


def test_legacy_sequences_are_read_from_matching_original_without_overwriting(history_sources, client2, app2):
    with app2.state.sessions.begin() as db:
        ledger = db.get(SocialResource, history_sources['id'])
        data = deepcopy(ledger.data)
        for row in data['rows']:
            row.pop('source_sequence', None)
        data['rows'][0]['approved'] = '3'
        data['rows'][0]['project_code'] = 'preserved-code'
        data['rows'][0]['history'] = empty_facts()
        data['rows'][0]['history']['pending_notes'] = ['保留原有待核依据']
        ledger.data = data
        before = deepcopy(data)
    listing = client2.get('/api/social/history-projects')
    assert listing.status_code == 200, listing.text
    assert listing.json()['total'] == 2
    item = listing.json()['items'][0]
    assert item['sequence'] == '1' and item['source_rows'] == [4, 5]
    detail = client2.get(f'/api/social/history-projects/{history_sources["id"]}/4')
    assert detail.status_code == 200
    assert detail.json()['project_code'] == 'preserved-code'
    with app2.state.sessions.begin() as db:
        assert db.get(SocialResource, history_sources['id']).data == before
    updated = save(client2, history_sources, 4, item['history'])
    assert updated.status_code == 200, updated.text
    with app2.state.sessions.begin() as db:
        after = db.get(SocialResource, history_sources['id']).data
        assert after == before
        assert db.scalars(select(SocialProject)).all() == []


def test_legacy_sequence_recovery_rejects_changed_row_identity(history_sources, client2, app2):
    with app2.state.sessions.begin() as db:
        ledger = db.get(SocialResource, history_sources['id'])
        data = deepcopy(ledger.data)
        data['rows'][0].pop('source_sequence')
        data['rows'][0]['name'] = '与原件不一致'
        ledger.data = data
    assert client2.get('/api/social/history-projects').status_code == 503
