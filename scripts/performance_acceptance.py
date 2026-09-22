#!/usr/bin/env python3
"""PDF 13.7/13.8 performance acceptance runner.

Runs against a staging/school HTTPS deployment. It never creates users or mutates
business data. Input CSV columns: username,password. Passwords are never printed or
written to the result JSON.

Gates:
- real login gate (default 20 concurrent logins),
- optional online-session capacity gate (default target 3000 unique credentials),
- 100 concurrent authenticated users executing a mixed read workload,
- ordinary endpoint p95 <= 3s, complex/statistics endpoint p95 <= 5s,
- zero HTTP failures for the acceptance workload.

This tool is evidence-producing, not a production load generator. Use a dedicated
pre-production dataset and accounts.
"""
from __future__ import annotations

import argparse, csv, json, math, os, ssl, statistics, sys, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import build_opener, HTTPCookieProcessor, Request, HTTPSHandler
from urllib.error import HTTPError, URLError

ORDINARY_LIMIT_S = 3.0
COMPLEX_LIMIT_S = 5.0
DEFAULT_PATHS = [
    ("records", "/api/records?page=1&size=20", "ordinary"),
    ("todos", "/api/todos", "ordinary"),
    ("assessments", "/api/assessments?page=1&size=20", "ordinary"),
    ("statistics", "/api/statistics", "complex"),
]

@dataclass
class Sample:
    phase: str
    label: str
    status: int
    elapsed_s: float
    ok: bool
    error: str = ""

@dataclass
class SessionCtx:
    username: str
    opener: object
    csrf: str


def percentile(values, pct):
    if not values:
        return None
    xs=sorted(values)
    if len(xs)==1:
        return xs[0]
    k=(len(xs)-1)*(pct/100)
    lo=math.floor(k); hi=math.ceil(k)
    if lo==hi:return xs[lo]
    return xs[lo]*(hi-k)+xs[hi]*(k-lo)


def summary(samples):
    times=[x.elapsed_s for x in samples]
    errors=[x for x in samples if not x.ok]
    return {
        "requests":len(samples),
        "errors":len(errors),
        "error_rate":round(len(errors)/len(samples),6) if samples else None,
        "p50_s":round(percentile(times,50),4) if times else None,
        "p95_s":round(percentile(times,95),4) if times else None,
        "p99_s":round(percentile(times,99),4) if times else None,
        "max_s":round(max(times),4) if times else None,
        "status_counts":{str(s):sum(1 for x in samples if x.status==s) for s in sorted({x.status for x in samples})},
    }


def load_users(path):
    p=Path(path)
    st=p.stat()
    if os.name!='nt' and st.st_mode & 0o077:
        raise SystemExit(f"凭据文件权限过宽：{p}；请 chmod 600")
    rows=[];seen=set()
    with p.open(newline='',encoding='utf-8-sig') as f:
        for i,r in enumerate(csv.DictReader(f),2):
            u=(r.get('username') or '').strip(); pw=r.get('password') or ''
            if not u or not pw: raise SystemExit(f"凭据CSV第{i}行缺 username/password")
            if u in seen: raise SystemExit(f"凭据CSV包含重复账号：{u}")
            seen.add(u); rows.append((u,pw))
    if not rows: raise SystemExit('凭据CSV为空')
    return rows


def ssl_context(args):
    if args.allow_http_lab:
        return None
    if args.ca_file:
        return ssl.create_default_context(cafile=args.ca_file)
    return ssl.create_default_context()


def make_opener(args):
    jar=CookieJar()
    handlers=[HTTPCookieProcessor(jar)]
    ctx=ssl_context(args)
    if ctx is not None: handlers.append(HTTPSHandler(context=ctx))
    return build_opener(*handlers)


def http(opener, base, path, *, method='GET', body=None, headers=None, timeout=15):
    url=urljoin(base.rstrip('/')+'/',path.lstrip('/'))
    data=None
    h={'Accept':'application/json','User-Agent':'Yueke-NonDegree-Acceptance/1.0'}
    if headers:h.update(headers)
    if body is not None:
        data=json.dumps(body,ensure_ascii=False).encode('utf-8')
        h['Content-Type']='application/json'
    req=Request(url,data=data,headers=h,method=method)
    started=time.perf_counter()
    try:
        with opener.open(req,timeout=timeout) as resp:
            raw=resp.read(); status=resp.status
        elapsed=time.perf_counter()-started
        parsed=json.loads(raw.decode('utf-8')) if raw else {}
        return status,elapsed,parsed,''
    except HTTPError as e:
        elapsed=time.perf_counter()-started
        try: detail=e.read().decode('utf-8')[:300]
        except Exception: detail=''
        return e.code,elapsed,{},f'HTTP {e.code}: {detail}'
    except (URLError,TimeoutError,OSError) as e:
        return 0,time.perf_counter()-started,{},type(e).__name__


def login_one(args, cred, phase='login'):
    username,password=cred; opener=make_opener(args)
    status,t,data,err=http(opener,args.base_url,'/api/auth/login',method='POST',body={'username':username,'password':password},
                           headers={'Origin':args.base_url.rstrip('/'),'Sec-Fetch-Site':'same-origin'},timeout=args.timeout)
    sample=Sample(phase,'auth/login',status,t,status==200,err)
    if status!=200:return None,[sample]
    status2,t2,me,err2=http(opener,args.base_url,'/api/auth/me',timeout=args.timeout)
    sample2=Sample(phase,'auth/me',status2,t2,status2==200,err2)
    if status2!=200:return None,[sample,sample2]
    return SessionCtx(username,opener,str(me.get('csrf') or '')),[sample,sample2]


def run_login_gate(args, users):
    n=min(args.login_concurrency,len(users))
    selected=users[:n]
    samples=[]; sessions=[]
    with ThreadPoolExecutor(max_workers=n) as ex:
        futs=[ex.submit(login_one,args,c,'login_gate') for c in selected]
        for f in as_completed(futs):
            sess,ss=f.result();samples.extend(ss)
            if sess:sessions.append(sess)
    login_only=[s for s in samples if s.label=='auth/login']
    s=summary(login_only)
    gate=(len(login_only)==n and s['errors']==0 and (s['p95_s'] or 999)<=args.login_p95_limit)
    return {"target_concurrency":n,"threshold_p95_s":args.login_p95_limit,"summary":s,"pass":gate},sessions,samples


def build_sessions(args, users, target):
    if len(users)<target:
        return {"target":target,"available_unique_credentials":len(users),"pass":False,"status":"BLOCKED_INPUT"},[],[]
    samples=[]; sessions=[]; lock=threading.Lock()
    # Keep login preparation deliberately lower than business concurrency; this phase tests session capacity, not burst authentication.
    workers=min(args.session_prepare_concurrency,target)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs=[ex.submit(login_one,args,c,'online_session_gate') for c in users[:target]]
        for f in as_completed(futs):
            sess,ss=f.result();
            with lock:
                samples.extend(ss)
                if sess:sessions.append(sess)
    # Validate a deterministic sample of the created sessions after all are resident.
    verify_sessions=sessions[:min(args.online_verify_count,len(sessions))]
    verify=[]
    with ThreadPoolExecutor(max_workers=min(50,max(1,len(verify_sessions)))) as ex:
        futs=[]
        for sess in verify_sessions:
            futs.append(ex.submit(http,sess.opener,args.base_url,'/api/auth/me',timeout=args.timeout))
        for f in as_completed(futs):
            st,t,_,err=f.result();verify.append(Sample('online_session_gate','auth/me/verify',st,t,st==200,err))
    samples.extend(verify)
    gate=len(sessions)==target and all(x.ok for x in verify) and all(x.ok for x in samples if x.label=='auth/login')
    return {"target":target,"created":len(sessions),"verify_count":len(verify),"pass":gate,
            "status":"PASS" if gate else "FAIL","login_summary":summary([x for x in samples if x.label=='auth/login']),
            "verify_summary":summary(verify)},sessions,samples


def run_business_gate(args, sessions):
    target=args.business_concurrency
    if len(sessions)<target:
        return {"target_concurrency":target,"available_sessions":len(sessions),"pass":False,"status":"BLOCKED_INPUT"},[]
    chosen=sessions[:target]
    all_samples=[]; lock=threading.Lock()
    paths=DEFAULT_PATHS
    def worker(i,sess):
        local=[]
        # Model normal mixed browsing instead of an artificial thundering herd
        # where every user opens the same endpoint at the same instant.
        offset=i%len(paths);ordered=paths[offset:]+paths[:offset]
        for cycle in range(args.business_cycles):
            for label,path,kind in ordered:
                st,t,_,err=http(sess.opener,args.base_url,path,timeout=args.timeout)
                local.append(Sample('business_gate',label,st,t,st==200,err))
        return local
    with ThreadPoolExecutor(max_workers=target) as ex:
        futs=[ex.submit(worker,i,s) for i,s in enumerate(chosen)]
        for f in as_completed(futs): all_samples.extend(f.result())
    per={}
    endpoint_kinds={label:kind for label,_,kind in paths}
    pass_all=True
    for label,_,kind in paths:
        xs=[x for x in all_samples if x.label==label]; sm=summary(xs)
        threshold=COMPLEX_LIMIT_S if kind=='complex' else ORDINARY_LIMIT_S
        passed=sm['errors']==0 and (sm['p95_s'] or 999)<=threshold
        per[label]={"kind":kind,"threshold_p95_s":threshold,"summary":sm,"pass":passed}
        pass_all=pass_all and passed
    return {"target_concurrency":target,"cycles_per_user":args.business_cycles,"total_requests":len(all_samples),
            "endpoints":per,"pass":pass_all,"status":"PASS" if pass_all else "FAIL"},all_samples


def main(argv=None):
    ap=argparse.ArgumentParser(description='跃科非学历教育 PDF 13.7/13.8 性能验收')
    ap.add_argument('--base-url',required=True)
    ap.add_argument('--users-csv',required=True)
    ap.add_argument('--output',required=True)
    ap.add_argument('--ca-file')
    ap.add_argument('--allow-http-lab',action='store_true',help='仅实验室HTTP；结果不得作为学校TLS验收')
    ap.add_argument('--timeout',type=float,default=15)
    ap.add_argument('--login-concurrency',type=int,default=20)
    ap.add_argument('--login-p95-limit',type=float,default=3.0)
    ap.add_argument('--online-target',type=int,default=3000)
    ap.add_argument('--online-verify-count',type=int,default=100)
    ap.add_argument('--session-prepare-concurrency',type=int,default=20)
    ap.add_argument('--business-concurrency',type=int,default=100)
    ap.add_argument('--business-cycles',type=int,default=2)
    args=ap.parse_args(argv)
    parsed=urlparse(args.base_url)
    if parsed.scheme!='https' and not args.allow_http_lab:raise SystemExit('正式验收必须使用 HTTPS；实验室HTTP需显式 --allow-http-lab')
    if parsed.scheme not in {'http','https'} or not parsed.netloc:raise SystemExit('base-url 无效')
    if min(args.login_concurrency,args.online_target,args.business_concurrency,args.business_cycles)<1:raise SystemExit('并发/目标参数必须大于0')
    users=load_users(args.users_csv)
    started=time.time()
    login_gate,login_sessions,login_samples=run_login_gate(args,users)
    online_gate,online_sessions,online_samples=build_sessions(args,users,args.online_target)
    # Business gate can still execute with login-gate sessions when online session target is blocked by missing credentials,
    # provided enough unique authenticated users exist for the requested business concurrency.
    business_pool=online_sessions if len(online_sessions)>=args.business_concurrency else []
    if not business_pool and len(users)>=args.business_concurrency:
        # Build only the business concurrency sessions if the 3000-user input set is incomplete.
        _,business_pool,_=build_sessions(args,users,args.business_concurrency)
    business_gate,business_samples=run_business_gate(args,business_pool)
    tls_verified=(parsed.scheme=='https' and not args.allow_http_lab)
    overall=bool(login_gate['pass'] and online_gate['pass'] and business_gate['pass'] and tls_verified)
    result={
      "tool":"Yueke NonDegree PDF 13.7/13.8 acceptance",
      "generated_at":time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
      "base_url":f'{parsed.scheme}://{parsed.netloc}',
      "tls_verified":tls_verified,
      "requirements":{"ordinary_p95_s":ORDINARY_LIMIT_S,"complex_p95_s":COMPLEX_LIMIT_S,
                      "online_sessions":args.online_target,"business_concurrency":args.business_concurrency},
      "login_gate":login_gate,"online_session_gate":online_gate,"business_gate":business_gate,
      "overall_pass":overall,
      "duration_s":round(time.time()-started,3),
      "notes":[
        "凭据与Cookie不会写入结果文件。",
        "online_session_gate需要唯一测试账号；凭据不足时为BLOCKED_INPUT，不等于系统性能失败。",
        "仅HTTPS且证书校验成功的结果可以进入学校环境验收证据。",
        "结果只证明本次数据集、服务器、网络与负载模型，不可外推到不同硬件。",
      ],
    }
    out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
    tmp=out.with_suffix(out.suffix+'.tmp');tmp.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(tmp,out)
    print(json.dumps({"overall_pass":overall,"login":login_gate['pass'],"online":online_gate['pass'],"business":business_gate['pass'],"output":str(out)},ensure_ascii=False))
    return 0 if overall else 2

if __name__=='__main__':raise SystemExit(main())
