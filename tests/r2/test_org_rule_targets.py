"""C-06: targets require school input; warnings never rewrite existing rules."""
from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session
from app.org_assessment import OrganizationAssessmentRule, evaluate_org_rule, org_rule_warnings
from conftest import auth, post


REASON = {'reason': '隔离考核目标回归', 'basis': '合成学校细则'}


def payload(target='100'):
    component = {'key': 'income', 'label': '归属培训收入', 'source': 'income', 'weight': '100'}
    if target != 'missing':
        component['target'] = target
    return {'target_kind': 'dept', 'name': '合成目标规则', 'period_id': 'period2026',
            'config': {'components': [component]}, **REASON}


@pytest.mark.parametrize('target', ['missing', None, '', ' ', '0', '-1'])
def test_new_org_rule_cannot_save_without_positive_target(client2, target):
    auth(client2, 'schooladmin')
    response = post(client2, '/api/organization-assessment-rules', payload(target))
    assert response.status_code == 422, response.text
    assert client2.get('/api/organization-assessment-rules').json()['items'] == []


@pytest.mark.parametrize('target', ['missing', None, '', ' '])
def test_old_draft_without_target_cannot_activate(client2, app2, target):
    auth(client2, 'schooladmin')
    created = post(client2, '/api/organization-assessment-rules', payload()).json()
    config = payload(target)['config']
    with Session(app2.state.engine) as db:
        db.get(OrganizationAssessmentRule, created['id']).config = deepcopy(config)
        db.commit()
    response = post(client2, f"/api/organization-assessment-rules/{created['id']}/actions",
                    {'action': 'activate', 'expected_version': created['version'], **REASON})
    assert response.status_code == 422, response.text
    assert '请按学校考核细则填写' in response.json()['detail']
    with Session(app2.state.engine) as db:
        stored = db.get(OrganizationAssessmentRule, created['id'])
        assert stored.state == 'DRAFT' and stored.config == config


@pytest.mark.parametrize('target,source,method,warning', [
    ('1', 'income', None, True), ('1.0000', 'income', 'ratio', True),
    ('100', 'income', None, False), ('1', 'hours', None, False),
    ('1', 'income', 'tier', False), ('invalid', 'income', None, False),
])
def test_income_target_warning_applies_only_to_ratio(target, source, method, warning):
    config = {'components': [{'source': source, 'target': target, 'method': method}]}
    original = deepcopy(config)
    messages = org_rule_warnings(config)
    assert bool(messages) is warning
    if warning:
        assert '来源未记录' in messages[0] and '系统默认' not in messages[0]
    assert config == original


def test_target_one_warning_reaches_list_trial_activation_and_calculation(client2, app2):
    auth(client2, 'schooladmin')
    created = post(client2, '/api/organization-assessment-rules', payload('1')).json()
    path = f"/api/organization-assessment-rules/{created['id']}"
    listed = client2.get('/api/organization-assessment-rules').json()['items'][0]
    assert listed['config']['components'][0]['target'] == '1'
    assert '来源未记录' in listed['warnings'][0]
    trial = post(client2, path + '/trial', {'target_ids': ['dept1']})
    assert trial.status_code == 200, trial.text
    assert trial.json()['warnings'] == listed['warnings']
    active = post(client2, path + '/actions', {'action': 'activate', 'expected_version': created['version'], **REASON})
    assert active.status_code == 200, active.text
    assert active.json()['warnings'] == listed['warnings']
    calculated = post(client2, '/api/organization-assessments/calculate',
                      {'target_kind': 'dept', 'period_id': 'period2026', 'target_ids': ['dept1'], **REASON})
    assert calculated.status_code == 200, calculated.text
    assert calculated.json()['warnings'] == listed['warnings']
    with Session(app2.state.engine) as db:
        stored = db.get(OrganizationAssessmentRule, created['id'])
        assert stored.config == created['config'] and stored.fingerprint == created['fingerprint']
    auth(client2, 'teacher')
    assert client2.get('/api/organization-assessment-rules').status_code == 403


def test_school_entered_target_keeps_proportional_score():
    rule = SimpleNamespace(id='synthetic', version_no=1, config=payload('100')['config'])
    detail = evaluate_org_rule(rule, {'income': Decimal('20')})
    assert detail[0]['score'] == '20.00'
    assert detail[0]['target'] == '100'
    assert org_rule_warnings(rule.config) == []
