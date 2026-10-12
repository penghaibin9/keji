"""Delivery regeneration must preserve explanations and refuse an existing DB."""
import pytest
from generate_delivery_catalog import generate, old_labels
from generate_api_catalog import render as render_api_catalog
from pathlib import Path


def test_labels_survive_both_old_and_regenerated_dictionary(tmp_path):
    source = tmp_path / 'dictionary.md'
    source.write_text('### 1. `users` 用户账号\n| `name` | VARCHAR | 否 | 普通 | 姓名 |\n', encoding='utf-8')
    assert old_labels(source) == ({'users': '用户账号'}, {('users', 'name'): '姓名'})
    source.write_text('## `users` 用户账号\n| `name` | VARCHAR | 否 | 否 | — | — | 否 | 姓名 |\n', encoding='utf-8')
    assert old_labels(source) == ({'users': '用户账号'}, {('users', 'name'): '姓名'})


def test_catalog_refuses_existing_database_before_running_migrations(tmp_path, monkeypatch):
    database = tmp_path / 'existing.sqlite'
    database.write_bytes(b'existing protected data')
    def forbidden(*args, **kwargs):
        raise AssertionError('must not run migration or inspect existing data')
    monkeypatch.setattr('generate_delivery_catalog.subprocess.run', forbidden)
    with pytest.raises(ValueError, match='新的隔离空库'):
        generate(database, tmp_path / 'unused.md', tmp_path / 'output.json')
    assert database.read_bytes() == b'existing protected data'
    assert not (tmp_path / 'output.json').exists()


@pytest.mark.parametrize('filename', ['preview.sqlite', 'renamed.json'])
def test_catalog_output_cannot_overwrite_database(tmp_path, monkeypatch, filename):
    output = tmp_path / filename
    content = b'SQLite format 3\x00protected data'
    output.write_bytes(content)
    def forbidden(*args, **kwargs):
        raise AssertionError('invalid output must be rejected before migration')
    monkeypatch.setattr('generate_delivery_catalog.subprocess.run', forbidden)
    with pytest.raises(ValueError, match='输出'):
        generate(tmp_path / 'new.sqlite', tmp_path / 'labels.md', output)
    assert output.read_bytes() == content
    assert not (tmp_path / 'new.sqlite').exists()


def test_api_catalog_includes_health_outside_business_security_gate():
    text, result = render_api_catalog(Path(__file__).resolve().parents[2])
    assert result['route_count'] == result['business_route_count'] + result['health_route_count']
    assert result['health_route_count'] == 1
    assert sum(row['path'] == '/api/health' for row in result['routes']) == 1
    assert 'GET /api/todos?stage=archive' in text
    assert '/api/imports/{ident}/discard' in text
