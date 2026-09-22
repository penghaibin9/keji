import importlib.util
import json
import sys
from pathlib import Path

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.core import Actor
from app.models import Audit, Org, Role, TrainingRecord, User
from conftest import auth

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "local_capacity_preflight", ROOT / "scripts/local_capacity_preflight.py"
)
PREFLIGHT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PREFLIGHT
SPEC.loader.exec_module(PREFLIGHT)


def test_teacher_actor_does_not_enumerate_every_teacher_in_the_department(app2):
    statements = []
    with Session(app2.state.engine) as db:
        user = db.get(User, "teacher")
        role = db.get(Role, user.role_id)
        org = db.get(Org, user.org_id)

        def capture(_conn, _cursor, statement, _parameters, _context, _many):
            statements.append(statement.lower())

        event.listen(app2.state.engine, "before_cursor_execute", capture)
        try:
            actor = Actor(db, user, role, org)
        finally:
            event.remove(app2.state.engine, "before_cursor_execute", capture)
    assert actor.teacher_ids == ("teacher",)
    assert not any("from users" in statement and "staff_no" in statement for statement in statements)


def test_management_read_scope_stays_in_sql_until_exact_snapshot_is_requested(app2):
    with Session(app2.state.engine) as db:
        user = db.get(User, "depthead")
        actor = Actor(db, user, db.get(Role, user.role_id), db.get(Org, user.org_id))
        assert actor._teacher_ids is None
        expression = actor.scope(TrainingRecord.teacher_id)
        assert "select" in str(expression).lower()
        assert actor._teacher_ids is None
        assert actor.teacher_ids == ("teacher",)


def test_read_access_audit_still_persists_after_response_background(client2, app2):
    auth(client2, "teacher")
    response = client2.get("/api/records?page=1&size=20")
    assert response.status_code == 200
    with Session(app2.state.engine) as db:
        row = db.scalar(select(Audit).where(
            Audit.module == "access", Audit.object_id == "/api/records", Audit.action == "GET"
        ).order_by(Audit.created_at.desc()))
        assert row is not None and row.result == "SUCCESS" and row.request_id


def test_local_capacity_preflight_is_scaled_and_never_claims_formal_acceptance(tmp_path):
    output = tmp_path / "capacity.json"
    report = PREFLIGHT.run_preflight(output, online_target=20, concurrency=8, cycles=1, timeout=10)
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert report["local_preflight_pass"] is True
    assert saved["session_capacity"]["stored_unique_sessions"] == 20
    assert saved["business_capacity"]["target_concurrency"] == 8
    assert saved["business_capacity"]["application_worker_topology"] == 2
    assert saved["business_capacity"]["total_requests"] == 32
    assert saved["formal_acceptance"] is False
    assert saved["overall_pass"] is False
    assert saved["tls_verified"] is False
    assert saved["production_touched"] is False
    assert "capacity-session" not in output.read_text(encoding="utf-8")


def test_capacity_preflight_input_bounds_are_fail_closed(tmp_path):
    for online, concurrency in [(0, 1), (10, 0), (10, 11), (10001, 1), (501, 501)]:
        try:
            PREFLIGHT.run_preflight(tmp_path / "bad.json", online, concurrency)
        except ValueError:
            pass
        else:
            raise AssertionError((online, concurrency))
    for workers in (0, 9):
        try:
            PREFLIGHT.run_preflight(tmp_path / "bad-workers.json", 10, 2, app_workers=workers)
        except ValueError:
            pass
        else:
            raise AssertionError(workers)
