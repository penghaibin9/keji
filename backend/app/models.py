"""Relational business model. UUID strings avoid JavaScript integer truncation.
Financial / scoring values use DECIMAL. Evidence and ledger rows are append-only
at the API layer. Production grants also deny UPDATE/DELETE on immutable tables.
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from sqlalchemy import (String, Integer, DateTime, Date, Numeric, Boolean, JSON, Text,
                        ForeignKey, UniqueConstraint, Index, CheckConstraint)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

def uid() -> str:
    return str(uuid.uuid4())

def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)

class Base(DeclarativeBase):
    pass

class Entity:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class Org(Entity, Base):
    __tablename__ = "organizations"
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(20))
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id"), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)

class Role(Entity, Base):
    __tablename__ = "roles"
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(20))
    permissions: Mapped[list] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)

class User(Entity, Base):
    __tablename__ = "users"
    username: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    staff_no: Mapped[str | None] = mapped_column(String(64), unique=True)
    title: Mapped[str] = mapped_column(String(80), default="")
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    role_id: Mapped[str] = mapped_column(ForeignKey("roles.id"), index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    authorization_pending: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True)
    auth_version: Mapped[int] = mapped_column(Integer, default=1)
    version: Mapped[int] = mapped_column(Integer, default=1)
    failures: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime)

class AuthSession(Base):
    __tablename__ = "auth_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    csrf: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    auth_version: Mapped[int] = mapped_column(Integer)
    auth_method: Mapped[str] = mapped_column(String(10), nullable=False, default="local", server_default="local")
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    last_seen: Mapped[datetime] = mapped_column(DateTime)

class Throttle(Base):
    __tablename__ = "login_throttles"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    window_start: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class Guard(Base):
    __tablename__ = "mutation_guards"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=1)

class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(Integer, default=1)

class Notice(Entity, Base):
    __tablename__ = "notices"
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(40), default="业务通知")
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    published: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)

class Period(Entity, Base):
    __tablename__ = "periods"
    name: Mapped[str] = mapped_column(String(100), unique=True)
    start_date: Mapped[datetime] = mapped_column(Date)
    end_date: Mapped[datetime] = mapped_column(Date)
    state: Mapped[str] = mapped_column(String(20), default="OPEN")
    version: Mapped[int] = mapped_column(Integer, default=1)

class TrainingRecord(Entity, Base):
    __tablename__ = "training_records"
    external_key: Mapped[str] = mapped_column(String(128), unique=True)
    teacher_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    event_date: Mapped[datetime] = mapped_column(Date, index=True)
    project_code: Mapped[str] = mapped_column(String(64), index=True)
    project: Mapped[str] = mapped_column(String(160))
    course_code: Mapped[str] = mapped_column(String(64), index=True)
    course: Mapped[str] = mapped_column(String(160))
    class_code: Mapped[str] = mapped_column(String(64))
    class_name: Mapped[str] = mapped_column(String(160))
    hours: Mapped[float] = mapped_column(Numeric(12, 2))
    participants: Mapped[int] = mapped_column(Integer)
    income: Mapped[float] = mapped_column(Numeric(18, 2))
    source: Mapped[str] = mapped_column(String(100), default="经核对人工录入")
    batch_id: Mapped[str | None] = mapped_column(String(36), index=True)
    state: Mapped[str] = mapped_column(String(20), default="VALID")
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (CheckConstraint("hours >= 0"), CheckConstraint("participants >= 0"),
                     Index("ix_records_teacher_date", "teacher_id", "event_date"))

class RecordRevision(Entity, Base):
    __tablename__ = "record_revisions"
    record_id: Mapped[str] = mapped_column(ForeignKey("training_records.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    data: Mapped[dict] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(Text)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    __table_args__ = (UniqueConstraint("record_id", "version"),)

class Qualification(Entity, Base):
    __tablename__ = "qualifications"
    teacher_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    category: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(160))
    certificate_no: Mapped[str] = mapped_column(String(128))
    issuer: Mapped[str] = mapped_column(String(160))
    obtained: Mapped[datetime] = mapped_column(Date)
    expires: Mapped[datetime | None] = mapped_column(Date, index=True)
    state: Mapped[str] = mapped_column(String(20), default="DRAFT", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    current_revision_id: Mapped[str | None] = mapped_column(String(36))
    attachment_ids: Mapped[list] = mapped_column(JSON, default=list)
    __table_args__ = (UniqueConstraint("teacher_id", "certificate_no"),)

class QualificationRevision(Entity, Base):
    __tablename__ = "qualification_revisions"
    qualification_id: Mapped[str] = mapped_column(ForeignKey("qualifications.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    data: Mapped[dict] = mapped_column(JSON)
    attachment_ids: Mapped[list] = mapped_column(JSON)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("qualification_id", "version"),)

class Attachment(Entity, Base):
    __tablename__ = "attachments"
    object_type: Mapped[str] = mapped_column(String(30))
    object_id: Mapped[str] = mapped_column(String(36), index=True)
    teacher_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    uploaded_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(200))
    storage_key: Mapped[str] = mapped_column(String(80), unique=True)
    sha256: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(Integer)
    mime: Mapped[str] = mapped_column(String(80))

class Rule(Entity, Base):
    __tablename__ = "rules"
    kind: Mapped[str] = mapped_column(String(20), index=True)
    name: Mapped[str] = mapped_column(String(100))
    version_no: Mapped[int] = mapped_column(Integer)
    period_id: Mapped[str] = mapped_column(ForeignKey("periods.id"), index=True)
    config: Mapped[dict] = mapped_column(JSON)
    fingerprint: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(20), default="DRAFT")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (UniqueConstraint("kind", "period_id", "version_no"),)

class RuleTrial(Entity, Base):
    __tablename__ = "rule_trials"
    rule_id: Mapped[str] = mapped_column(ForeignKey("rules.id"), index=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    result: Mapped[list] = mapped_column(JSON)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))

class CalculationBatch(Entity, Base):
    __tablename__ = "calculation_batches"
    kind: Mapped[str] = mapped_column(String(20))
    period_id: Mapped[str] = mapped_column(ForeignKey("periods.id"))
    rule_id: Mapped[str] = mapped_column(ForeignKey("rules.id"))
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    reason: Mapped[str] = mapped_column(Text)

class PointBalance(Entity, Base):
    __tablename__ = "point_balances"
    teacher_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    period_id: Mapped[str] = mapped_column(ForeignKey("periods.id"), index=True)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (UniqueConstraint("teacher_id", "period_id"),)

class PointEntry(Entity, Base):
    __tablename__ = "point_entries"
    teacher_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    period_id: Mapped[str] = mapped_column(ForeignKey("periods.id"), index=True)
    item_key: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(20))
    amount: Mapped[float] = mapped_column(Numeric(18, 2))
    raw_value: Mapped[str] = mapped_column(String(80))
    formula: Mapped[str] = mapped_column(String(500))
    rule_id: Mapped[str | None] = mapped_column(ForeignKey("rules.id"))
    batch_id: Mapped[str | None] = mapped_column(ForeignKey("calculation_batches.id"), index=True)
    source_snapshot: Mapped[dict] = mapped_column(JSON)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(Text)
    basis: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = (Index("ix_points_teacher_period", "teacher_id", "period_id"),)

class Assessment(Entity, Base):
    __tablename__ = "assessments"
    teacher_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    period_id: Mapped[str] = mapped_column(ForeignKey("periods.id"), index=True)
    rule_id: Mapped[str] = mapped_column(ForeignKey("rules.id"))
    score: Mapped[float] = mapped_column(Numeric(8, 2))
    detail: Mapped[list] = mapped_column(JSON)
    source_snapshot: Mapped[dict] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String(20), default="TEACHER", index=True)
    returned: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    archive: Mapped[dict | None] = mapped_column(JSON)
    archive_sha256: Mapped[str | None] = mapped_column(String(64))
    __table_args__ = (UniqueConstraint("teacher_id", "period_id"),)

class WorkflowEvent(Entity, Base):
    __tablename__ = "workflow_events"
    object_type: Mapped[str] = mapped_column(String(30))
    object_id: Mapped[str] = mapped_column(String(36), index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    actor_name: Mapped[str] = mapped_column(String(100))
    org_id: Mapped[str] = mapped_column(String(36))
    action: Mapped[str] = mapped_column(String(50))
    before: Mapped[dict] = mapped_column(JSON)
    after: Mapped[dict] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(Text)
    basis: Mapped[str] = mapped_column(Text, default="")

class Dispute(Entity, Base):
    __tablename__ = "disputes"
    teacher_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    object_type: Mapped[str] = mapped_column(String(30))
    object_id: Mapped[str] = mapped_column(String(36), index=True)
    period_id: Mapped[str | None] = mapped_column(ForeignKey("periods.id"))
    reason: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(20), default="OPEN")
    resolution: Mapped[str] = mapped_column(Text, default="")
    resolved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    version: Mapped[int] = mapped_column(Integer, default=1)

class ImportJob(Entity, Base):
    __tablename__ = "import_jobs"
    kind: Mapped[str] = mapped_column(String(30))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    filename: Mapped[str] = mapped_column(String(200))
    sha256: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(20), default="PREVIEW")
    total: Mapped[int] = mapped_column(Integer)
    errors: Mapped[int] = mapped_column(Integer)
    receipt: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)

class ImportRow(Entity, Base):
    __tablename__ = "import_rows"
    job_id: Mapped[str] = mapped_column(ForeignKey("import_jobs.id"), index=True)
    row_no: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)
    errors: Mapped[list] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint("job_id", "row_no"),)

class Connection(Entity, Base):
    __tablename__ = "connections"
    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    state: Mapped[str] = mapped_column(String(30), default="NOT_CONNECTED")
    mappings: Mapped[list] = mapped_column(JSON, default=list)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)

class Task(Entity, Base):
    __tablename__ = "tasks"
    kind: Mapped[str] = mapped_column(String(30))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    key: Mapped[str] = mapped_column(String(100), unique=True)
    payload: Mapped[dict] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String(20), default="PENDING", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    lease_token: Mapped[str | None] = mapped_column(String(64))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)

class TaskAttempt(Entity, Base):
    __tablename__ = "task_attempts"
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), index=True)
    attempt: Mapped[int] = mapped_column(Integer)
    result: Mapped[str] = mapped_column(String(20))
    message: Mapped[str] = mapped_column(Text)

class Receipt(Base):
    __tablename__ = "command_receipts"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    request_hash: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class Audit(Entity, Base):
    __tablename__ = "audit_events"
    actor_id: Mapped[str | None] = mapped_column(String(36), index=True)
    actor_name: Mapped[str] = mapped_column(String(100))
    org_id: Mapped[str | None] = mapped_column(String(36), index=True)
    module: Mapped[str] = mapped_column(String(50), index=True)
    object_id: Mapped[str] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(120))
    before: Mapped[dict] = mapped_column(JSON)
    after: Mapped[dict] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(Text)
    result: Mapped[str] = mapped_column(String(30))
    request_id: Mapped[str] = mapped_column(String(36))
    __table_args__ = (Index("ix_audit_time", "created_at"), Index("ix_audit_result_time", "result", "created_at"))

class RuntimeState(Base):
    __tablename__ = "runtime_state"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class FormDraft(Entity, Base):
    """Personal unfinished input, never a business record or an approval."""
    __tablename__ = "form_drafts"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    role_id: Mapped[str] = mapped_column(ForeignKey("roles.id"))
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    kind: Mapped[str] = mapped_column(String(32))
    context_key: Mapped[str] = mapped_column(String(160))
    title: Mapped[str] = mapped_column(String(200))
    payload: Mapped[dict] = mapped_column(JSON)
    source_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    state: Mapped[str] = mapped_column(String(16), default="ACTIVE")
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint("user_id","role_id","org_id","kind","context_key",name="uq_form_draft_scope"),)
