"""Local load driver (asyncio + httpx): 3000 real logins, session verification, 100-user sustained mixed workload.
Passwords/cookies are never written to output. Usage: load_driver.py BASE_URL USERS_CSV OUT_DIR [duration_s] [vus]
"""
from __future__ import annotations
import asyncio, csv, json, math, random, sys, time
from collections import defaultdict
from pathlib import Path
import httpx, ssl
CTX = ssl.create_default_context()

BASE = sys.argv[1].rstrip('/'); USERS = Path(sys.argv[2]); OUT = Path(sys.argv[3]); OUT.mkdir(parents=True, exist_ok=True)
DURATION = float(sys.argv[4]) if len(sys.argv) > 4 else 360; VUS = int(sys.argv[5]) if len(sys.argv) > 5 else 100
import os; ONLINE_TARGET = int(os.environ.get('ONLINE_TARGET', '3000')); LOGIN_CONC = 20; TIMEOUT = 30.0; COOKIE = 'nd_test_session'
ORD, CPX = 3.0, 5.0
THINK = (float(os.environ.get('THINK_MIN', '0')), float(os.environ.get('THINK_MAX', '0')))
random.seed(7)

def pct(xs, p):
    if not xs: return None
    xs = sorted(xs); k = (len(xs) - 1) * p / 100; lo, hi = math.floor(k), math.ceil(k)
    return xs[lo] if lo == hi else xs[lo] * (hi - k) + xs[hi] * (k - lo)

def summ(samples, wall=None):
    t = [s[2] for s in samples]; err = [s for s in samples if not s[3]]
    d = {'requests': len(samples), 'errors': len(err), 'error_rate': round(len(err) / len(samples), 6) if samples else None,
         'p50_s': round(pct(t, 50), 4) if t else None, 'p95_s': round(pct(t, 95), 4) if t else None,
         'p99_s': round(pct(t, 99), 4) if t else None, 'max_s': round(max(t), 4) if t else None,
         'mean_s': round(sum(t) / len(t), 4) if t else None,
         'status_counts': {str(k): sum(1 for s in samples if s[1] == k) for k in sorted({s[1] for s in samples})}}
    if wall: d['throughput_rps'] = round(len(samples) / wall, 2)
    return d

async def req(client, method, path, token=None, **kw):
    h = {'Accept': 'application/json'}
    if token: h['Cookie'] = f'{COOKIE}={token}'
    h.update(kw.pop('headers', {}))
    t0 = time.perf_counter()
    try:
        r = await client.request(method, BASE + path, headers=h, timeout=TIMEOUT, **kw)
        body = r.content; el = time.perf_counter() - t0
        ok = r.status_code == 200
        if ok and body: json.loads(body)
        return r, r.status_code, el, ok
    except Exception as e:
        return None, 0, time.perf_counter() - t0, False

async def phase_login(creds):
    sem = asyncio.Semaphore(LOGIN_CONC); samples = []; tokens = {}
    async def one(c):
        async with sem:
            async with httpx.AsyncClient(verify=CTX) as cl:
                r, st, el, ok = await req(cl, 'POST', '/api/auth/login', json={'username': c['username'], 'password': c['password']},
                                          headers={'Origin': BASE, 'Sec-Fetch-Site': 'same-origin'})
                samples.append(('auth/login', st, el, ok, time.time()))
                if ok and r is not None and r.cookies.get(COOKIE): tokens[c['username']] = r.cookies.get(COOKIE)
    t0 = time.time(); await asyncio.gather(*(one(c) for c in creds)); return samples, tokens, time.time() - t0

async def phase_verify(tokens, label):
    sem = asyncio.Semaphore(100); samples = []; ok_users = 0
    lim = httpx.Limits(max_connections=100, max_keepalive_connections=100)
    async with httpx.AsyncClient(limits=lim, verify=CTX) as cl:
        async def one(u, tok):
            nonlocal ok_users
            async with sem:
                r, st, el, ok = await req(cl, 'GET', '/api/auth/me', tok)
                if ok and r.json()['user']['username'] != u: ok = False
                ok_users += ok; samples.append((label, st, el, ok, time.time()))
        t0 = time.time(); await asyncio.gather(*(one(u, t) for u, t in tokens.items()))
    return samples, ok_users, time.time() - t0

def endpoints_for(role, period_id):
    e = [('portal_workbench', '/api/portal/workbench', 'ordinary'), ('records_list', '/api/records?page=1&size=20', 'ordinary'),
         ('qualifications_list', '/api/qualifications?page=1&size=20', 'ordinary'), ('todos', '/api/todos?page=1&size=20', 'ordinary'),
         ('qualification_summary', '/api/qualification-summary', 'ordinary'),
         ('statistics_dashboard', '/api/statistics', 'complex'), ('assessments_list', '/api/assessments?page=1&size=20', 'complex')]
    if role != 'teacher':
        e += [('organization_workbench', '/api/organization-workbench', 'complex'), ('organization_assessments', '/api/organization-assessments?page=1&size=20', 'complex')]
    if role == 'school':
        e += [('statistics_comparison', f'/api/statistics/comparison?period_id={period_id}', 'complex'),
              ('assessments_list_2025_archived', '/api/assessments?page=1&size=20&state=ARCHIVED', 'complex')]
    return e

async def phase_business(vus, period_id):
    samples = []; stop = time.time() + DURATION; kinds = {}
    async def vu(i, role, tok):
        eps = endpoints_for(role, period_id)
        async with httpx.AsyncClient(limits=httpx.Limits(max_connections=1), verify=CTX) as cl:  # one browser-like connection per user
            await asyncio.sleep(random.random() * 2)  # stagger start
            while time.time() < stop:
                random.shuffle(eps)
                for label, path, kind in eps:
                    if time.time() >= stop: break
                    kinds[label] = kind
                    _, st, el, ok = await req(cl, 'GET', path, tok)
                    samples.append((label, st, el, ok, time.time(), role))
                    if THINK[1] > 0: await asyncio.sleep(random.uniform(*THINK))
    t0 = time.time(); await asyncio.gather(*(vu(i, r, t) for i, (r, t) in enumerate(vus))); return samples, kinds, time.time() - t0

async def main():
    creds = list(csv.DictReader(USERS.open(encoding='utf-8')))
    byrole = defaultdict(list)
    for c in creds: byrole[c['role']].append(c)
    mix = {'teacher': 60, 'dept': 20, 'college': 12, 'school': 8}
    biz = [c for r, n in mix.items() for c in byrole[r][:n]]
    rest = [c for c in creds if c not in biz]; random.shuffle(rest)
    online = biz + rest[:ONLINE_TARGET - len(biz)]
    roles = {c['username']: c['role'] for c in online}
    result = {'tool': 'scratchpad load_driver.py (asyncio+httpx)', 'base_url': BASE, 'started_at': time.strftime('%Y-%m-%dT%H:%M:%S%z')}
    print('login phase...', flush=True)
    ls, tokens, wall = await phase_login(online)
    result['online_session_phase'] = {'target': ONLINE_TARGET, 'login_concurrency': LOGIN_CONC, 'created_sessions': len(tokens),
        'role_mix': {r: sum(1 for u in tokens if roles[u] == r) for r in mix}, 'login_summary': summ(ls, wall), 'wall_s': round(wall, 1)}
    print(json.dumps(result['online_session_phase'], ensure_ascii=False), flush=True)
    vs, okn, wall = await phase_verify(tokens, 'auth/me')
    result['online_session_phase'].update(verify_all_sessions={'checked': len(vs), 'valid': okn, 'concurrency': 100, 'summary': summ(vs, wall)},
        **{'pass': len(tokens) == ONLINE_TARGET and okn == ONLINE_TARGET})
    print('verify', okn, flush=True)
    async with httpx.AsyncClient(verify=CTX) as cl:
        r, *_ = await req(cl, 'GET', '/api/auth/me', tokens[biz[-1]['username']])
    # period id (2026) for comparison via assessments list of a school user
    async with httpx.AsyncClient(verify=CTX) as cl:
        r, *_ = await req(cl, 'GET', '/api/periods', tokens[biz[-1]['username']])
        periods = r.json() if r is not None and r.status_code == 200 else []
        items = periods['items'] if isinstance(periods, dict) else periods
        period_id = next((p['id'] for p in items if p['name'].startswith('2026')), '')
    vus = [(c['role'], tokens[c['username']]) for c in biz if c['username'] in tokens]
    print('business phase', len(vus), 'VUs for', DURATION, 's', flush=True)
    bs, kinds, wall = await phase_business(vus, period_id)
    t_start = min(s[4] for s in bs)
    per = {}
    for label in sorted(kinds):
        xs = [s for s in bs if s[0] == label]; kind = kinds[label]; thr = CPX if kind == 'complex' else ORD
        sm = summ(xs, wall); per[label] = {'kind': kind, 'threshold_p95_s': thr, 'summary': sm,
            'by_role': {r: summ([s for s in xs if s[5] == r]) for r in mix if any(s[5] == r for s in xs)},
            'pass': sm['errors'] == 0 and sm['p95_s'] <= thr}
    ordinary = [s for s in bs if kinds[s[0]] == 'ordinary']; complex_ = [s for s in bs if kinds[s[0]] == 'complex']
    windows = []
    for w in range(int(math.ceil(wall / 30))):
        xs = [s for s in bs if t_start + w * 30 <= s[4] < t_start + (w + 1) * 30]
        if xs: windows.append({'window': f'{w*30}-{w*30+30}s', 'requests': len(xs), 'rps': round(len(xs) / 30, 1), 'errors': sum(not s[3] for s in xs),
                               'ordinary_p95_s': round(pct([s[2] for s in xs if kinds[s[0]] == 'ordinary'], 95) or 0, 3),
                               'complex_p95_s': round(pct([s[2] for s in xs if kinds[s[0]] == 'complex'], 95) or 0, 3)})
    result['business_phase'] = {'virtual_users': len(vus), 'role_mix': mix, 'duration_s': round(wall, 1), 'model': f'closed loop, think time {THINK[0]}-{THINK[1]}s between requests, one keep-alive connection per user, shuffled endpoint order per cycle',
        'overall': summ(bs, wall), 'ordinary_all': summ(ordinary, wall), 'complex_all': summ(complex_, wall), 'endpoints': per, 'windows_30s': windows,
        'ordinary_pass': all(v['pass'] for v in per.values() if v['kind'] == 'ordinary'), 'complex_pass': all(v['pass'] for v in per.values() if v['kind'] == 'complex')}
    print(json.dumps({k: result['business_phase'][k] for k in ('overall', 'ordinary_pass', 'complex_pass')}, ensure_ascii=False), flush=True)
    vs2, okn2, wall2 = await phase_verify(tokens, 'auth/me/after')
    result['online_session_phase']['reverify_after_business'] = {'checked': len(vs2), 'valid': okn2, 'summary': summ(vs2, wall2)}
    result['finished_at'] = time.strftime('%Y-%m-%dT%H:%M:%S%z')
    (OUT / 'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf-8')
    with (OUT / 'business_samples.csv').open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f); w.writerow(['endpoint', 'status', 'elapsed_s', 'ok', 'epoch', 'role'])
        for s in bs: w.writerow([s[0], s[1], round(s[2], 5), int(s[3]), round(s[4], 3), s[5]])
    print('done', flush=True)

asyncio.run(main())
