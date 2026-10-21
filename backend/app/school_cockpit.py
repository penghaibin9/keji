"""学校报送资料只读视图；与授课流水、推荐值和学校核定值分别保存口径。"""
from __future__ import annotations
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from threading import Lock
import re
from fastapi import HTTPException
from . import ledger_check as lc

_cache = {}
_lock = Lock()


def _period(title, year):
    compact = re.sub(r'\s+', '', title)
    months = re.search(r'年(\d{1,2})[—–－\-至](\d{1,2})月', compact)
    first, last = (int(x) for x in months.groups()) if months else (1, 12)
    if not 1 <= first <= last <= 12:
        raise HTTPException(503, '学校原表的资料期间无法确认')
    from calendar import monthrange
    return {'year': year, 'start': date(year, first, 1).isoformat(),
            'end': date(year, last, monthrange(year, last)[1]).isoformat(),
            'label': f'{year}年全年' if (first, last) == (1, 12) else f'{year}年{first}—{last}月'}


def _read_report(path, root):
    raw = path.read_bytes()
    parsed = lc.parse(raw, path.name)
    year = parsed['meta']['year']
    if not year:
        raise HTTPException(503, '学校原表缺少明确年度')
    # 目录保留学校正式学院名称，避免原表抬头空格及“学院学院”导致拆成多个学院。
    college = next((re.sub(r'（.*$', '', part) for part in reversed(path.relative_to(root).parts[:-1])
                    if re.fullmatch(r'.+学院(?:（.*）)?', part)), '')
    if not college:
        raise HTTPException(503, '学校原始资料缺少可确认的学院名称')
    digest = sha256(raw).hexdigest()
    report = {'id': digest, 'college': college, 'file': path.name, 'period': _period(parsed['meta']['title'], year),
              'sheet_total': None if parsed['sheet_total'] is None else lc.q2(parsed['sheet_total']),
              'updated': path.name.startswith('更新版'), 'rows': [], 'warnings': []}
    project = None
    for item in parsed['items']:
        sequence = item['source_sequence']
        if re.fullmatch(r'\d+', sequence):
            project = f'{digest[:20]}-{item["row_no"]}'
        elif project is None:
            raise HTTPException(503, '原表续行缺少所属项目，请先核对来源表')
        report['rows'].append({'id': f'{digest[:20]}-{item["row_no"]}', 'project_id': project,
            'numbered': bool(re.fullmatch(r'\d+', sequence)), 'name': item['name'],
            'source_row': item['row_no'], 'source_sequence': sequence, 'source_cell': ('F' if parsed['template'] == '2025' else 'E') + str(item['row_no']),
            'value': None if item['claimed'] is None else lc.q2(item['claimed']),
            'unit': '原表折算量' if parsed['template'] == '2025' else ('人天' if '人天' in item['claimed_raw'] else '人次')})
    claimed = sum((Decimal(r['value']) for r in report['rows'] if r['value'] is not None), Decimal(0))
    if parsed['sheet_total'] is not None and parsed['sheet_total'] != claimed:
        report['warnings'].append(f'原表合计为{lc.q2(parsed["sheet_total"])}，明细汇总为{lc.q2(claimed)}；展示明细汇总，待学校核对。')
    if any(r['value'] is None for r in report['rows']):
        report['warnings'].append('部分来源行缺少可读取的报送值，未按零补齐。')
    return report


def load_reports(directory):
    if directory is None:
        return None
    root = Path(directory)
    if not root.is_dir() or root.is_symlink():
        raise HTTPException(503, '学校原始资料目录不可用，请由实施人员核对')
    root = root.resolve()
    paths = sorted(p for p in root.rglob('*人次统计表*') if p.suffix.lower() in {'.xls', '.xlsx'}
                   and not any(part.startswith(('__MACOSX', '._', '~$')) for part in p.relative_to(root).parts))
    if not paths or len(paths) > 200:
        raise HTTPException(503, '学校原始统计表缺失或数量异常')
    for path in paths:
        if any(p.is_symlink() for p in (path, *path.parents) if p != root.parent) or not path.resolve().is_relative_to(root):
            raise HTTPException(503, '学校原始资料路径不符合只读范围')
        if path.stat().st_size > lc.MAX_BYTES:
            raise HTTPException(503, '学校原始统计表超过读取上限')
    stamp = tuple((str(p.relative_to(root)), p.stat().st_size, p.stat().st_mtime_ns) for p in paths)
    with _lock:
        previous = _cache.get(str(root))
        if previous and previous[0] == stamp:
            return previous[1]
        groups = defaultdict(list)
        for path in paths:
            try:
                report = _read_report(path, root)
            except HTTPException:
                raise
            except Exception:
                raise HTTPException(503, '学校原始统计表读取失败，请核对文件格式与内容') from None
            key = (report['college'], report['period']['year'])
            if not any(r['id'] == report['id'] for r in groups[key]):
                groups[key].append(report)
        adopted, excluded = [], []
        for candidates in groups.values():
            updated = [r for r in candidates if r['updated']]
            if len(candidates) > 1 and len(updated) != 1:
                raise HTTPException(503, '同学院同年度存在未确认的多份原表，请先确认采用版本')
            chosen = updated[0] if updated else candidates[0]
            adopted.append(chosen)
            excluded.extend({'college': r['college'], 'file': r['file'], 'reason': '已有更新版，本表不重复累计'}
                            for r in candidates if r is not chosen)
        school_names = {name for path in paths for name in re.findall(r'([一-龥]{2,16}职业(?:技术)?学院)', path.name)}
        result = {'reports': adopted, 'excluded': excluded, 'school_name': next(iter(school_names)) if len(school_names) == 1 else '',
                  'read_at': datetime.now(timezone.utc).isoformat(),
                  'version': sha256(''.join(sorted(r['id'] for r in adopted)).encode()).hexdigest()}
        _cache.clear()
        _cache[str(root)] = (stamp, result)
        return result


def summarize(catalog, *, year=None, college='', project='', imported_ledgers=None):
    if catalog is None:
        return {'available': False, 'note': '尚未配置学校原始统计资料，以下授课流水统计继续保留。'}
    reports = catalog['reports']
    imported_ledgers = imported_ledgers or {}
    years = sorted({r['period']['year'] for r in reports})
    year = years[-1] if year is None else year
    if year not in years:
        raise HTTPException(422, '所选年度没有学校原始资料')
    colleges = sorted({r['college'] for r in reports})
    if college and college not in colleges:
        raise HTTPException(422, '学院不在学校原始资料范围')
    current = [r for r in reports if r['period']['year'] == year and (not college or r['college'] == college)]
    options = [{'id': row['project_id'], 'name': row['name'], 'college': r['college']}
               for r in current for row in r['rows'] if row['numbered']]
    if project and project not in {x['id'] for x in options}:
        raise HTTPException(422, '项目不在当前学院和资料期间')
    # 本期指标、学院图表与来源明细共用筛选后的来源行；续行随所属编号项目一起筛选。
    selected = [(r, row) for r in current for row in r['rows'] if not project or row['project_id'] == project]
    units = {}
    for unit in ('人次', '人天', '原表折算量'):
        rows = [row for _, row in selected if row['unit'] == unit]
        units[unit] = None if not rows or any(row['value'] is None for row in rows) else lc.q2(sum((Decimal(row['value']) for row in rows), Decimal(0)))
    selected_colleges = {r['college'] for r, _ in selected}
    record_count = len({row['project_id'] for _, row in selected})
    rank, composition = [], []
    for name in sorted(selected_colleges):
        rows = [row for r, row in selected if r['college'] == name]
        people = [row for row in rows if row['unit'] == '人次']
        if people:
            rank.append({'name': name, 'value': None if any(x['value'] is None for x in people) else lc.q2(sum((Decimal(x['value']) for x in people), Decimal(0)))})
        composition.append({'name': name, 'value': len({row['project_id'] for row in rows})})
    rank.sort(key=lambda r: Decimal(r['value']) if r['value'] is not None else Decimal(-1), reverse=True)
    composition.sort(key=lambda r: (-r['value'], r['name']))
    periods = []
    for y in years:
        ps = {tuple(sorted(r['period'].items())) for r in reports if r['period']['year'] == y}
        if len(ps) != 1:
            raise HTTPException(503, '同年度学院资料期间不一致，请先核对')
        periods.append(dict(next(iter(ps))))
    comparison = []
    for period in periods:
        group = [r for r in reports if r['period']['year'] == period['year'] and (not college or r['college'] == college)]
        comparison.append({**period, 'records': sum(sum(row['numbered'] for row in r['rows']) for r in group) if group else None, 'colleges': len(group)})
    table = []
    for name in ([college] if college else colleges):
        group = [r for r in reports if r['college'] == name]
        now = next((r for r in group if r['period']['year'] == year), None)
        rows = [row for r, row in selected if r['college'] == name]
        if project and not rows:
            continue
        quantities = []
        for unit in ('人次', '人天', '原表折算量'):
            same = [row for row in rows if row['unit'] == unit]
            if same:
                quantities.append({'unit': unit, 'value': None if any(row['value'] is None for row in same) else lc.q2(sum((Decimal(row['value']) for row in same), Decimal(0)))})
        table.append({'college': name, 'records': {str(y): next((sum(row['numbered'] for row in r['rows']) for r in group if r['period']['year'] == y), None) for y in years},
                      'quantities': quantities, 'selected_records': len({row['project_id'] for row in rows}) if now else None,
                      'status': '待补资料' if now is None else '合计待核' if now['warnings'] else '采用更新版' if now['updated'] else '待核定',
                      'ledger': imported_ledgers.get((name, year, now['id'])) if now else None})
    table.sort(key=lambda r: (-(r['records'][str(years[0])] or 0), r['college']))
    details = [{'college': r['college'], 'file': r['file'], 'period': r['period']['label'],
                'name': row['name'], 'row': row['source_row'], 'cell': row['source_cell'],
                'value': row['value'], 'unit': row['unit'], 'numbered': row['numbered'], 'status': '原表报送值',
                'ledger': imported_ledgers.get((r['college'], year, r['id']))}
               for r, row in selected]
    selected_period = next(p for p in periods if p['year'] == year)
    return {'available': True, 'school_name': catalog.get('school_name', ''), 'period': selected_period, 'periods': periods, 'college': college, 'project': project,
            'colleges': colleges, 'projects': options, 'totals': {'person_times': units['人次'], 'person_days': units['人天'],
                'raw_conversions': units['原表折算量'], 'records': record_count, 'colleges': len(selected_colleges),
                'person_times_colleges': len({r['college'] for r, row in selected if row['unit'] == '人次'})},
            'rank': rank, 'composition': composition, 'comparison': comparison, 'table': table, 'details': details,
            'warnings': [{'college': r['college'], 'text': warning} for r in current for warning in r['warnings']],
            'excluded': catalog['excluded'], 'version': catalog['version'], 'read_at': catalog['read_at'],
            'note': '学院原表报送值，待学校核定；人次、人天、原表折算量分别统计。编号项目记录不等于去重项目数或授课流水条数。',
            'comparison_note': '非同期资料对照，不计算同比；年度对照保留所选学院的原表完整期间，不随单条项目筛选改变。'}
