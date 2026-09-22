#!/usr/bin/env python3
"""Run a disposable 3000-session / 100-concurrent local capacity preflight.

This is deliberately not procurement acceptance.  It creates a temporary
SQLite database containing synthetic users and sessions, starts the real ASGI
application on loopback, runs read-only HTTP requests, writes a redacted JSON
report, and removes the temporary database afterwards.  It never opens or
modifies the configured project/production database.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import socket
import statistics
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from hashlib import sha256
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session
import uvicorn

from app.config import Settings
from app.main import create_app
from app.models import AuthSession, Base, Org, Period, Role, Setting, TrainingRecord, User, utcnow
from app.permissions import ALLOWED

ORDINARY_LIMIT_S = 3.0
COMPLEX_LIMIT_S = 5.0
PATHS = (
    ("training_records", "/api/records?page=1&size=20", "ordinary"),
    ("todos", "/api/todos?page=1&size=20", "ordinary"),
    ("assessments", "/api/assessments?page=1&size=20", "ordinary"),
    ("statistics", "/api/statistics", "complex"),
)


@dataclass
class Sample:
    phase: str
    label: str
    status: int
    elapsed_s: float
    ok: bool
    error: str = ""


def percentile(values, pct):
    if not values:
        return None
    values = sorted(values)
    if len(values) == 1:
        return values[0]
    pos = (len(values) - 1) * pct / 100
    low, high = math.floor(pos), math.ceil(pos)
    if low == high:
        return values[low]
    return values[low] * (high - pos) + values[high] * (pos - low)


def summarize(samples):
    durations = [item.elapsed_s for item in samples]
    errors = [item for item in samples if not item.ok]
    return {
        "requests": len(samples),
        "errors": len(errors),
        "error_rate": round(len(errors) / len(samples), 6) if samples else None,
        "p50_s": round(percentile(durations, 50), 4) if durations else None,
        "p95_s": round(percentile(durations, 95), 4) if durations else None,
        "p99_s": round(percentile(durations, 99), 4) if durations else None,
        "max_s": round(max(durations), 4) if durations else None,
        "status_counts": {
            str(status): sum(item.status == status for item in samples)
            for status in sorted({item.status for item in samples})
        },
    }


def role_for(index):
    # 70% teachers, 15% department, 10% college, 5% school management.
    point = index % 20
    return "teacher" if point < 14 else "dept" if point < 17 else "college" if point < 19 else "school"


def seed_lab(database_url, online_target):
    """Create synthetic data only in a new disposable database."""
    settings = Settings(
        env="test",
        database_url=database_url,
        secure_cookie=False,
        allowed_hosts="127.0.0.1,localhost",
        public_origin="http://127.0.0.1",
        storage_dir=Path(database_url.removeprefix("sqlite:///")).parent / "files",
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    now = utcnow()
    raw_tokens = []
    with Session(app.state.engine) as db:
        db.add_all([
            Org(id="school", code="school", name="容量预检学校", kind="school", parent_id=None),
            Org(id="college", code="college", name="容量预检学院", kind="college", parent_id="school"),
            Org(id="dept", code="dept", name="容量预检教研室", kind="dept", parent_id="college"),
        ])
        db.flush()
        for kind, permissions in ALLOWED.items():
            db.add(Role(id="role-" + kind, code=kind, name={
                "teacher": "普通教师", "dept": "教研室负责人",
                "college": "学院负责人", "school": "学校管理人员",
            }[kind], kind=kind, permissions=sorted(permissions)))
        db.add_all([
            Setting(key="branding", value={"school_name": "容量预检学校"}),
            Setting(key="metrics", value={"income_note": "隔离容量预检", "participants_note": "隔离容量预检"}),
            Setting(key="qualification", value={"expiry_days": 30, "categories": ["教学资质"]}),
            Period(id="capacity-period", name="容量预检周期", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31)),
        ])
        db.flush()
        users, sessions, records = [], [], []
        for index in range(online_target):
            kind = role_for(index)
            ident = f"capacity-user-{index:05d}"
            token = sha256(f"capacity-session-{index:05d}".encode()).hexdigest()
            raw_tokens.append(token)
            org_id = "dept" if kind in {"teacher", "dept"} else "college" if kind == "college" else "school"
            users.append({
                "id": ident, "created_at": now, "username": ident, "name": f"容量预检用户{index:05d}",
                "staff_no": f"CAP-{index:05d}" if kind == "teacher" else None, "title": "容量预检",
                "org_id": org_id, "role_id": "role-" + kind, "password_hash": "LOCAL_CAPACITY_LOGIN_DISABLED",
                "active": True, "is_admin": False, "must_change_password": False, "auth_version": 1,
                "version": 1, "failures": 0, "locked_until": None,
            })
            sessions.append({
                "token_hash": sha256(token.encode()).hexdigest(), "csrf": sha256((token + "csrf").encode()).hexdigest(),
                "user_id": ident, "auth_version": 1, "expires_at": now + timedelta(hours=2), "last_seen": now,
            })
            if kind == "teacher":
                records.append({
                    "id": f"capacity-record-{index:05d}", "created_at": now,
                    "external_key": f"CAPACITY-{index:05d}", "teacher_id": ident,
                    "event_date": date(2026, 9, 1), "project_code": "CAP-PROJECT", "project": "容量预检项目",
                    "course_code": "CAP-COURSE", "course": "容量预检课程", "class_code": "CAP-CLASS",
                    "class_name": "容量预检班级", "hours": 1, "participants": 1, "income": 1,
                    "source": "隔离容量预检", "batch_id": None, "state": "VALID", "version": 1,
                })
        db.execute(insert(User), users)
        db.execute(insert(AuthSession), sessions)
        if records:
            db.execute(insert(TrainingRecord), records)
        db.commit()
    return app, raw_tokens


def request(base_url, token, path, phase, label, timeout):
    started = time.perf_counter()
    req = Request(base_url + path, headers={
        "Accept": "application/json",
        "Cookie": "nd_test_session=" + token,
        "User-Agent": "Yueke-Local-Capacity-Preflight/1.0",
    })
    try:
        with urlopen(req, timeout=timeout) as response:
            body = response.read()
            status = response.status
        if body:
            json.loads(body.decode("utf-8"))
        return Sample(phase, label, status, time.perf_counter() - started, status == 200)
    except HTTPError as exc:
        return Sample(phase, label, exc.code, time.perf_counter() - started, False, f"HTTP {exc.code}")
    except (URLError, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return Sample(phase, label, 0, time.perf_counter() - started, False, type(exc).__name__)


def start_server(app):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(2048)
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="critical", access_log=False))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.time() + 20
    while not server.started and thread.is_alive() and time.time() < deadline:
        time.sleep(0.05)
    if not server.started:
        server.should_exit = True
        thread.join(timeout=5)
        sock.close()
        raise RuntimeError("隔离容量预检服务未能启动")
    return server, thread, sock, f"http://127.0.0.1:{port}"


def run_preflight(output, online_target=3000, concurrency=100, cycles=1, timeout=15, app_workers=2):
    if not 1 <= online_target <= 10000:
        raise ValueError("在线会话预检数量须为1至10000")
    if not 1 <= concurrency <= min(500, online_target):
        raise ValueError("并发数须为1至500，且不能超过在线会话数")
    if not 1 <= cycles <= 10:
        raise ValueError("每用户循环次数须为1至10")
    if not 1 <= app_workers <= 8:
        raise ValueError("本地应用进程模拟数须为1至8")
    logging.getLogger("nondegree").setLevel(logging.CRITICAL)
    started = time.time()
    with tempfile.TemporaryDirectory(prefix="nd-capacity-lab-") as lab:
        lab_path = Path(lab).resolve()
        if not lab_path.name.startswith("nd-capacity-lab-"):
            raise RuntimeError("容量预检必须使用专用临时目录")
        database = lab_path / "capacity.sqlite"
        app, tokens = seed_lab("sqlite:///" + str(database), online_target)
        with Session(app.state.engine) as db:
            stored_sessions = db.scalar(select(func.count()).select_from(AuthSession))
            stored_users = db.scalar(select(func.count()).select_from(User))
        apps = [app] + [create_app(app.state.settings) for _ in range(app_workers - 1)]
        runtimes = [start_server(item) for item in apps]
        base_urls = [item[3] for item in runtimes]
        try:
            verify_count = min(100, online_target)
            with ThreadPoolExecutor(max_workers=min(concurrency, verify_count)) as pool:
                verify = list(pool.map(lambda pair: request(
                    base_urls[pair[0] % len(base_urls)], pair[1], "/api/auth/me",
                    "session_sample", "authenticated_session", timeout,
                ), enumerate(tokens[:verify_count])))
            samples = []
            def workload(index):
                result = []
                token = tokens[index]
                base_url = base_urls[index % len(base_urls)]
                offset = index % len(PATHS)
                paths = PATHS[offset:] + PATHS[:offset]
                for _ in range(cycles):
                    for label, path, _ in paths:
                        result.append(request(base_url, token, path, "business", label, timeout))
                return result
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                futures = [pool.submit(workload, index) for index in range(concurrency)]
                for future in as_completed(futures):
                    samples.extend(future.result())
        finally:
            for server, _, _, _ in runtimes:
                server.should_exit = True
            for _, thread, sock, _ in runtimes:
                thread.join(timeout=20)
                sock.close()
            for item in apps:
                item.state.engine.dispose()
        endpoints = {}
        business_pass = True
        for label, _, kind in PATHS:
            group = [item for item in samples if item.label == label]
            data = summarize(group)
            threshold = COMPLEX_LIMIT_S if kind == "complex" else ORDINARY_LIMIT_S
            passed = data["errors"] == 0 and data["p95_s"] is not None and data["p95_s"] <= threshold
            endpoints[label] = {"kind": kind, "threshold_p95_s": threshold, "summary": data, "pass": passed}
            business_pass = business_pass and passed
        session_summary = summarize(verify)
        session_pass = stored_sessions == online_target and stored_users == online_target and session_summary["errors"] == 0
        local_pass = session_pass and business_pass
        report = {
            "evidence_kind": "LOCAL_ISOLATED_CAPACITY_PREFLIGHT",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "synthetic": True,
            "temporary_database_removed": True,
            "production_touched": False,
            "tls_verified": False,
            "formal_acceptance": False,
            "requirements_reference": {
                "online_sessions": 3000, "business_concurrency": 100,
                "ordinary_p95_s": ORDINARY_LIMIT_S, "complex_p95_s": COMPLEX_LIMIT_S,
            },
            "session_capacity": {
                "target": online_target, "stored_unique_users": stored_users,
                "stored_unique_sessions": stored_sessions, "http_sample_size": len(verify),
                "http_sample_summary": session_summary, "pass": session_pass,
            },
            "business_capacity": {
                "target_concurrency": concurrency, "cycles_per_user": cycles,
                "application_worker_topology": app_workers,
                "workload_model": "staggered mixed read-only business pages",
                "role_mix": "70% teacher, 15% department, 10% college, 5% school management",
                "total_requests": len(samples), "endpoints": endpoints, "pass": business_pass,
            },
            "local_preflight_pass": local_pass,
            "overall_pass": False,
            "duration_s": round(time.time() - started, 3),
            "notes": [
                "本报告只证明隔离本机、合成数据和本次负载模型的施工预检结果。",
                "临时数据库、会话值和测试用户已随临时目录删除，不进入交付包。",
                "未使用学校服务器、MySQL、HTTPS、真实数据规模和正式账号，不构成采购性能验收。",
                "正式验收仍须在双方确认的学校目标环境执行。",
            ],
        }
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, target)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="本地隔离容量施工预检（不等于学校正式验收）")
    parser.add_argument("--output", required=True)
    parser.add_argument("--online-target", type=int, default=3000)
    parser.add_argument("--concurrency", type=int, default=100)
    parser.add_argument("--cycles", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=15)
    parser.add_argument("--app-workers", type=int, default=2,
                        help="模拟当前交付配置中的应用进程数，默认2")
    args = parser.parse_args(argv)
    report = run_preflight(args.output, args.online_target, args.concurrency, args.cycles, args.timeout, args.app_workers)
    print(json.dumps({
        "local_preflight_pass": report["local_preflight_pass"],
        "formal_acceptance": False,
        "online_sessions": report["session_capacity"]["stored_unique_sessions"],
        "business_concurrency": report["business_capacity"]["target_concurrency"],
        "output": str(Path(args.output)),
    }, ensure_ascii=False))
    return 0 if report["local_preflight_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
