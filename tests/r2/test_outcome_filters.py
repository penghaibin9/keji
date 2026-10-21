from app.social_models import SocialResource
from conftest import auth


def test_outcome_filters_apply_before_count_and_paging(app2, client2):
    with app2.state.sessions.begin() as db:
        for i in range(201):
            db.add(SocialResource(kind='achievement', org_id='college1', code=f'FILTER-A-{i:03}',
                                  name=f'合成校级成果{i}', data={'level': 'school'}))
        db.add(SocialResource(kind='achievement', org_id='college1', code='FILTER-Z-ONE',
                              name='跨页合成国家级成果', data={'level': 'national'}))
        db.add(SocialResource(kind='achievement', org_id='college2', code='FILTER-Z-TWO',
                              name='另一学院国家级成果', data={'level': 'national'}))
    auth(client2, 'schooladmin')
    result = client2.get('/api/social/workspace?section=outcomes&level=national').json()
    assert result['pagination']['total'] == 2
    assert {r['code'] for r in result['resources']} == {'FILTER-Z-ONE', 'FILTER-Z-TWO'}
    result = client2.get('/api/social/workspace?section=outcomes&level=national&org_id=college1&q=跨页').json()
    assert result['pagination']['total'] == 1
    assert [r['code'] for r in result['resources']] == ['FILTER-Z-ONE']
    assert {o['id'] for o in result['outcome_orgs']} >= {'college1', 'college2'}
    empty = client2.get('/api/social/workspace?section=outcomes&level=province').json()
    assert empty['pagination']['total'] == 0 and empty['resources'] == []
    assert client2.get('/api/social/workspace?section=outcomes&level=invalid').status_code == 422
    auth(client2, 'teacher')
    own = client2.get('/api/social/workspace?section=outcomes&level=national').json()
    assert own['pagination']['total'] == 1
    assert [r['code'] for r in own['resources']] == ['FILTER-Z-ONE']
    assert client2.get('/api/social/workspace?section=outcomes&org_id=college2').status_code == 403
