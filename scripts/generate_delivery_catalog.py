"""Generate delivery structure evidence from an isolated, migrated empty database."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from sqlalchemy import create_engine, inspect, text
from app import models, org_assessment, integrations, reference_data, inbound_sync, installation, social_models
from app.delivery import SECRETISH
from app.release_contract import EXPECTED_MIGRATION_HEADS
from generate_api_catalog import render as render_api_catalog


def old_labels(path):
    tables, fields, current = {}, {}, None
    for line in path.read_text(encoding='utf-8').splitlines():
        heading = re.match(r'^#{2,3} (?:\d+\. )?`([^`]+)` (.+)', line)
        if heading:
            current = heading[1]
            tables[current] = heading[2]
        elif current and line.startswith('| `'):
            cells = [part.strip() for part in line.strip('|').split('|')]
            if len(cells) == 5:
                fields[(current, cells[0].strip('`'))] = cells[4]
            elif len(cells) == 8:
                fields[(current, cells[0].strip('`'))] = cells[7]
    return tables, fields


def generate(database, labels, output):
    database = database.resolve()
    labels, output = labels.resolve(), output.resolve()
    if output.suffix.lower() != '.json' or output in {database, labels}:
        raise ValueError('结构证据输出必须是独立 JSON 文件，不能指向数据库或说明来源')
    if output.exists():
        with output.open('rb') as stream:
            if stream.read(16) == b'SQLite format 3\x00':
                raise ValueError('结构证据输出不能覆盖已有数据库')
    if database.exists():
        raise ValueError('生成目标必须是新的隔离空库，不能复用现有数据库')
    database.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, ND_ENV='test', ND_DATABASE_URL='sqlite:///' + database.as_posix(),
               ND_SECURE_COOKIE='false', ND_PUBLIC_ORIGIN='http://testserver',
               ND_STORAGE_DIR=str(database.parent / 'unused-files'), ND_RELEASE_GUARD='true')
    env.pop('ND_DATABASE_URL_FILE', None)
    subprocess.run([sys.executable, '-m', 'alembic', '-c', str(ROOT / 'backend/alembic.ini'),
                    'upgrade', 'head'], cwd=ROOT, env=env, check=True)
    engine = create_engine(env['ND_DATABASE_URL'])
    inspector = inspect(engine)
    with engine.connect() as connection:
        heads = sorted(connection.execute(text('SELECT version_num FROM alembic_version')).scalars())
    assert set(heads) == set(EXPECTED_MIGRATION_HEADS), 'migration head differs'
    names = sorted(name for name in inspector.get_table_names() if name != 'alembic_version')
    assert set(names) == set(models.Base.metadata.tables), 'migrated table inventory differs from models'
    table_labels, field_labels = old_labels(labels)
    table_labels.update({'school_courses': '学校课程总库', 'teacher_course_terms': '教师课程学期',
                         'social_projects': '社会培训项目', 'social_claims': '社会培训积分申报',
                         'form_drafts': '个人未完成填写暂存'})
    field_labels.update({('form_drafts', key): meaning for key, meaning in {
        'user_id': '暂存所属用户', 'role_id': '暂存所属身份', 'org_id': '暂存所属组织',
        'kind': '允许暂存的业务类型', 'context_key': '新建填写或原业务的隔离标识',
        'title': '本人辨认暂存的标题', 'payload': '白名单表单内容及附件名称；不保存附件文件',
        'source_version': '原业务版本，用于恢复前检查变更', 'state': '有效、已完成或已放弃',
        'updated_at': '最后暂存时间',
    }.items()})
    rows = []
    for name in names:
        primary = set(inspector.get_pk_constraint(name)['constrained_columns'])
        foreign = {column: fk['referred_table'] + '.' + fk['referred_columns'][index]
                   for fk in inspector.get_foreign_keys(name)
                   for index, column in enumerate(fk['constrained_columns'])}
        model_columns = models.Base.metadata.tables[name].columns
        columns = inspector.get_columns(name)
        assert {column['name'] for column in columns} == set(model_columns.keys()), name
        for column in columns:
            field = column['name']
            model = model_columns[field]
            meaning = field_labels.get((name, field)) or model.comment or {
                'id': '主键', 'version': '并发校验版本', 'created_at': '创建时间',
                'auth_method': '登录方式：本地密码或学校统一认证',
            }.get(field, '字段业务含义以对应模型和服务校验为准')
            rows.append({'table': name, 'table_label': table_labels.get(name, '业务扩展表'),
                         'column': field, 'type': str(column['type']), 'nullable': column['nullable'],
                         'primary_key': field in primary, 'foreign_key': foreign.get(field, ''),
                         'default': str(column['default'] or ''), 'sensitive': field in SECRETISH,
                         'meaning': meaning})
    _, routes = render_api_catalog(ROOT)
    digest_inputs = sorted(set(r['file'] for r in routes['routes']))
    result = {'migration_heads': heads, 'table_count': len(names), 'column_count': len(rows),
              'api_route_count': routes['route_count'], 'static_route_status': routes['status'],
              'business_api_route_count': routes['business_route_count'], 'health_api_route_count': routes['health_route_count'],
              'schema_source': 'isolated_sqlite_migrations_not_school_database', 'fields': rows,
              'routes': routes['routes'], 'source_sha256': {
                  name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in digest_inputs}}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    lines = ['# 数据字典（交付候选，字段级）', '',
             '迁移头：`' + ', '.join(heads) + '`。独立空库执行全部迁移后读取实际结构，',
             '逐表、逐字段与当前模型比对；不是读取学校数据库，也不是 MySQL（生产数据库）验收。', '',
             f'业务表 {len(names)} 张，字段 {len(rows)} 个。迁移版本表另计 1 张。', '',
             f"接口共 {routes['route_count']} 项，其中业务路由 {routes['business_route_count']} 项、健康检查 {routes['health_route_count']} 项。", '',
             '生成入口：`scripts/generate_delivery_catalog.py`。结构证据见 `docs/交付结构清单.json`。', '',
             '密码、令牌、附件存储键等敏感字段只列结构，不列数据。中文含义缺失处明确标注，禁止据名称猜测业务口径。', '']
    for name in names:
        lines += [f'## `{name}` {table_labels.get(name, "业务扩展表")}', '',
                  '| 字段 | 类型 | 可空 | 主键 | 外键 | 数据库默认 | 敏感 | 业务含义 |',
                  '|---|---|---|---|---|---|---|---|']
        for row in (row for row in rows if row['table'] == name):
            lines.append('| ' + ' | '.join([f"`{row['column']}`", row['type'],
                         '是' if row['nullable'] else '否', '是' if row['primary_key'] else '否',
                         row['foreign_key'] or '—', row['default'] or '—',
                         '是' if row['sensitive'] else '否', row['meaning'].replace('|', '／')]) + ' |')
        lines.append('')
    (ROOT / 'docs/数据字典.md').write_text('\n'.join(lines), encoding='utf-8', newline='\n')
    engine.dispose()
    return {key: result[key] for key in ('migration_heads', 'table_count', 'column_count', 'api_route_count')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--schema-database', type=Path, required=True)
    parser.add_argument('--labels', type=Path, default=ROOT / 'docs/数据字典.md')
    parser.add_argument('--output', type=Path, default=ROOT / 'docs/交付结构清单.json')
    args = parser.parse_args()
    print(json.dumps(generate(args.schema_database, args.labels, args.output), ensure_ascii=False))
