"""采购第3项：基础配置在相关业务中统一生效。"""
from datetime import date, timedelta

from app.models import Qualification
from conftest import auth, put


REASON = {'reason': '采购第3项专项核验', 'basis': '采购清单第3项第4至5条'}


def settings(client):
    return {item['key']: item for item in client.get('/api/settings').json()['items']}


def update(client, key, value, version):
    response = put(client, f'/api/settings/{key}', {
        'value': value,
        'expected_version': version,
        **REASON,
    })
    assert response.status_code == 200, response.text
    return response.json()


def test_brand_metrics_and_qualification_settings_reach_their_business_consumers(client2, app2):
    auth(client2, 'schooladmin')
    current = settings(client2)

    update(client2, 'branding', {'school_name': '采购配置核验学校'}, current['branding']['version'])
    assert client2.get('/api/auth/me').json()['school_name'] == '采购配置核验学校'

    metric_value = {
        'income_note': '采购核验收入统计口径',
        'participants_note': '采购核验课程人次统计口径',
    }
    update(client2, 'metrics', metric_value, current['metrics']['version'])
    statistics = client2.get('/api/statistics').json()
    assert statistics['metric_notes'] == metric_value

    with app2.state.sessions.begin() as db:
        db.add(Qualification(
            id='procurement-expiry-window',
            teacher_id='teacher',
            category='职业资格',
            name='采购配置核验资质',
            certificate_no='PROCUREMENT-SETTING-1',
            issuer='隔离测试机构',
            obtained=date.today() - timedelta(days=365),
            expires=date.today() + timedelta(days=10),
            state='APPROVED',
        ))

    auth(client2, 'teacher')
    before = client2.get('/api/todos?type=qualification&size=100').json()['items']
    assert any(item['id'] == 'procurement-expiry-window' for item in before)

    auth(client2, 'schooladmin')
    qualification = settings(client2)['qualification']
    update(client2, 'qualification', {
        'expiry_days': 5,
        'categories': ['职业资格', '学校专项资质'],
    }, qualification['version'])

    auth(client2, 'teacher')
    after = client2.get('/api/todos?type=qualification&size=100').json()['items']
    assert not any(item['id'] == 'procurement-expiry-window' for item in after)
    assert client2.get('/api/statistics').json()['qualification_warning_days'] == 5
    assert client2.get('/api/qualification-categories').json()['categories'] == ['职业资格', '学校专项资质']


def test_setting_history_contains_operator_time_before_after_and_reason(client2):
    auth(client2, 'schooladmin')
    current = settings(client2)['branding']
    update(client2, 'branding', {'school_name': '采购历史核验学校'}, current['version'])
    history = client2.get('/api/settings/branding/history').json()['items'][0]
    assert history['actor_name'] == '学校测试管理员'
    assert history['created_at']
    assert history['reason'] == REASON['reason']
    assert history['before']['value']['school_name'] == '隔离测试学校'
    assert history['after']['value']['school_name'] == '采购历史核验学校'

