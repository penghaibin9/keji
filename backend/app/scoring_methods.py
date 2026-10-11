"""10.1 / 9.1 extended scoring methods: 分档、扣分、加分、封顶/保底.

Legacy components (no ``method`` key) are never routed here.  Teacher rules keep
the AST-pinned ``services.evaluate`` and organization rules keep their original
ratio formula, so existing rules and archived results compute exactly as before.

Every extended method returns its explicit calculation steps, which are stored in
the existing calculation detail (formula / steps / tier_hit / bounds) and are
therefore versioned, trial-run and archived together with the rule version.

kind: ``points`` (teacher points), ``assessment`` (teacher assessment) or ``org``
(organization assessment).  Weighted kinds (assessment/org) never exceed the
component weight, so a rule's total stays within 0-100.
"""
from __future__ import annotations
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP, InvalidOperation

METHODS = {'ratio':'达标比例 × 权重','linear':'原始值 × 系数','tier':'分档','deduct':'扣分','bonus':'加分'}
TIER_MODES = {'score':'命中档直接得分','multiplier':'命中档系数'}
# ``cap`` already exists on legacy teacher components; it is not an extension key.
EXTENDED_KEYS = ('method','tiers','tier_mode','base','unit','per_unit','floor')
WEIGHTED = {'assessment','org'}
LIMIT = Decimal('1000000000000')


def _num(value, label, *, minimum=None, positive=False):
    try:
        n = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f'{label}必须是数字') from None
    if not n.is_finite() or abs(n) > LIMIT:
        raise ValueError(f'{label}超出允许范围')
    if positive and n <= 0:
        raise ValueError(f'{label}必须大于0')
    if minimum is not None and n < minimum:
        raise ValueError(f'{label}不能小于{minimum}')
    return n


def text(value):
    """Stable plain decimal text (no exponent), used for stored config and steps."""
    d = Decimal(str(value))
    s = format(d.normalize(), 'f') if d != 0 else '0'
    return s


def is_extended(component):
    return bool(component.get('method'))


def normalize_method(item, kind):
    """Validate an extended component and return its canonical extension fields.

    Returns ``{}`` for a legacy component (and rejects stray extension values),
    otherwise a dict of strings ready to be stored in the rule config.
    Raises ValueError with a Chinese message.
    """
    method = item.get('method')
    if method in (None, ''):
        if any(item.get(k) not in (None, '', []) for k in EXTENDED_KEYS if k != 'method'):
            raise ValueError('未选择评分方式时不能填写分档、扣分/加分或保底参数')
        return {}
    if method not in METHODS:
        raise ValueError('评分方式无效')
    out = {'method': method}
    weight = _num(item.get('weight', 0) or 0, '权重', minimum=Decimal(0))
    allowed = {'ratio':{'floor'},'linear':{'floor'},'tier':{'tiers','tier_mode','floor'},
               'deduct':{'base','unit','per_unit','floor'},'bonus':{'base','unit','per_unit','floor'}}[method]
    stray = [k for k in EXTENDED_KEYS if k != 'method' and k not in allowed and item.get(k) not in (None, '', [])]
    if stray:
        raise ValueError(f'评分方式“{METHODS[method]}”不使用以下参数：' + '、'.join(stray))
    if method == 'ratio':
        _num(item.get('target', 1), '达标值', positive=True)
        if kind == 'points':
            raise ValueError('积分规则不使用“达标比例 × 权重”，请选择原始值 × 系数、分档或加分/扣分')
    if method == 'linear':
        _num(item.get('factor', 1), '系数', minimum=Decimal(0))
    if method == 'tier':
        tiers = item.get('tiers')
        if not isinstance(tiers, list) or not 1 <= len(tiers) <= 20:
            raise ValueError('分档须填写1～20档')
        normalized, previous = [], None
        for i, t in enumerate(tiers, 1):
            if not isinstance(t, dict) or set(t) - {'min', 'value'} or not {'min', 'value'} <= set(t):
                raise ValueError(f'第{i}档须同时填写门槛与分值/系数')
            low = _num(t['min'], f'第{i}档门槛')
            val = _num(t['value'], f'第{i}档分值/系数', minimum=Decimal(0))
            if previous is not None and low <= previous:
                raise ValueError('分档门槛必须从低到高严格递增')
            previous = low
            normalized.append({'min': text(low), 'value': text(val)})
        mode = item.get('tier_mode') or 'score'
        if mode not in TIER_MODES:
            raise ValueError('分档计分方式无效')
        if kind in WEIGHTED and mode == 'score' and any(Decimal(t['value']) > weight for t in normalized):
            raise ValueError('分档得分不能超过该指标权重')
        out.update(tiers=normalized, tier_mode=mode)
    if method in {'deduct', 'bonus'}:
        if item.get('per_unit') in (None, ''):
            raise ValueError('扣分/加分须填写每单位分值')
        out['per_unit'] = text(_num(item['per_unit'], '每单位分值', positive=True))
        out['unit'] = text(_num(item.get('unit') if item.get('unit') not in (None, '') else 1, '计数单位', positive=True))
        default_base = weight if (method == 'deduct' and kind in WEIGHTED) else Decimal(0)
        base = _num(item['base'], '起始分') if item.get('base') not in (None, '') else default_base
        if kind in WEIGHTED and not Decimal(0) <= base <= weight:
            raise ValueError('起始分须在0与该指标权重之间')
        out['base'] = text(base)
    cap = item.get('cap')
    cap = _num(cap, '封顶值', minimum=Decimal(0)) if cap not in (None, '') else None
    floor = item.get('floor')
    floor = _num(floor, '保底值') if floor not in (None, '') else None
    if kind in WEIGHTED:
        if cap is not None and cap > weight:
            raise ValueError('封顶值不能超过该指标权重')
        if floor is not None and floor < 0:
            raise ValueError('保底值不能为负数')
    if cap is not None and floor is not None and floor > cap:
        raise ValueError('保底值不能高于封顶值')
    if floor is not None:
        out['floor'] = text(floor)
    if cap is not None and kind == 'org':
        out['cap'] = text(cap)
    return out


def _bounds(c, kind):
    weight = Decimal(str(c.get('weight', 0) or 0))
    cap = Decimal(str(c['cap'])) if c.get('cap') not in (None, '') else (weight if kind in WEIGHTED else None)
    floor = Decimal(str(c['floor'])) if c.get('floor') not in (None, '') else (
        Decimal(0) if (kind in WEIGHTED or c['method'] == 'deduct') else None)
    return floor, cap


def score_component(c, value, kind):
    """Evaluate one extended component. Returns (score, formula, explanation)."""
    value = Decimal(str(value)); method = c['method']; weight = Decimal(str(c.get('weight', 0) or 0))
    steps = [f'评分方式：{METHODS[method]}']; hit = None
    if method == 'ratio':
        target = Decimal(str(c['target']))
        ratio = max(Decimal(0), min(Decimal(1), value / target))
        result = ratio * weight
        steps.append(f'达标比例 = max(0, min({text(value)} ÷ {text(target)}, 1)) = {text(ratio.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))}')
        steps.append(f'× 权重 {text(weight)} = {text(result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))}')
    elif method == 'linear':
        factor = Decimal(str(c.get('factor', 1)))
        result = value * factor
        steps.append(f'{text(value)} × 系数 {text(factor)} = {text(result)}')
    elif method == 'tier':
        tiers = sorted(c['tiers'], key=lambda t: Decimal(str(t['min'])))
        index = None
        for i, t in enumerate(tiers):
            if value >= Decimal(str(t['min'])):
                index = i
        if index is None:
            result = Decimal(0)
            steps.append(f'原始值 {text(value)} 低于最低档门槛 {text(tiers[0]["min"])}，未命中分档，本项计 0')
        else:
            t = tiers[index]; amount = Decimal(str(t['value']))
            hit = {'index': index + 1, 'min': text(t['min']), 'value': text(amount), 'mode': c.get('tier_mode', 'score')}
            upper = f'，< {text(tiers[index + 1]["min"])}' if index + 1 < len(tiers) else ''
            steps.append(f'原始值 {text(value)} 命中第 {index + 1} 档（≥ {text(t["min"])}{upper}）')
            if c.get('tier_mode', 'score') == 'score':
                result = amount
                steps.append(f'命中档得分 {text(amount)}')
            else:
                base = weight if kind in WEIGHTED else value
                result = base * amount
                steps.append(f'命中档系数 {text(amount)} × {"权重" if kind in WEIGHTED else "原始值"} {text(base)} = {text(result)}')
    else:
        unit = Decimal(str(c.get('unit', 1))); per = Decimal(str(c['per_unit'])); base = Decimal(str(c.get('base', 0)))
        count = max(Decimal(0), (value / unit).to_integral_value(rounding=ROUND_FLOOR))
        sign = '−' if method == 'deduct' else '+'
        result = base - count * per if method == 'deduct' else base + count * per
        steps.append(f'计数 = 向下取整({text(value)} ÷ {text(unit)}) = {text(count)}')
        steps.append(f'起始分 {text(base)} {sign} {text(count)} × {text(per)} = {text(result)}')
    floor, cap = _bounds(c, kind); applied = ''
    if cap is not None and result > cap:
        steps.append(f'超过封顶 {text(cap)}，按封顶计'); result = cap; applied = 'cap'
    if floor is not None and result < floor:
        steps.append(f'低于保底 {text(floor)}，按保底计'); result = floor; applied = 'floor'
    score = Decimal(str(result)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    steps.append(f'本项得分 {score}')
    explanation = {'method': method, 'method_label': METHODS[method], 'steps': steps, 'tier_hit': hit,
                   'bounds': {'floor': text(floor) if floor is not None else None,
                              'cap': text(cap) if cap is not None else None, 'applied': applied}}
    return score, '；'.join(steps), explanation


def clean_teacher_config(config, kind):
    """Stored teacher rule config: legacy components keep their historic shape
    (no extension keys); extended components store canonical method fields."""
    out = []
    for c in config['components']:
        c = {k: v for k, v in c.items() if not (k in EXTENDED_KEYS and v in (None, '', []))}
        if is_extended(c):
            try:
                c.update(normalize_method(c, kind))
            except ValueError as exc:
                from fastapi import HTTPException
                raise HTTPException(422, str(exc)) from None
        out.append(c)
    return {**config, 'components': out}
