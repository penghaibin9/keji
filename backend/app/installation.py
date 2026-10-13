"""Read-only canonical-installation guard; not a defence against a malicious DBA.

The marker is written only by the fresh migration. Runtime gets SELECT only.
A version stamp alone, incomplete DDL or a legacy database must never pass.
"""
from __future__ import annotations
import argparse, hashlib, json, uuid, re
from pathlib import Path
from datetime import datetime
import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column
from .models import Base

BASELINE_REVISION = "20260918_0001"
# Additive revisions after the baseline, oldest first, with the schema contract each adds.
EXTENSION_REVISIONS = (("20261008_0002", "social_schema.json"), ("20261009_0003", "teaching_schema.json"), ("20261012_0004", "auth_session_schema.json"), ("20261013_0005", "audit_index_schema.json"))
CURRENT_REVISION = EXTENSION_REVISIONS[-1][0]
KNOWN_REVISIONS = (BASELINE_REVISION, *(r for r, _ in EXTENSION_REVISIONS))
SOURCE_KIND = "canonical_empty_school"
CONTRACT_PATH = Path(__file__).resolve().parents[1] / "canonical_schema.json"

class InstallationProvenance(Base):
    __tablename__ = "installation_provenance"
    singleton_id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=False)
    installation_id: Mapped[str] = mapped_column(sa.String(36), nullable=False, unique=True)
    baseline_revision: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    source_kind: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    contract_sha256: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    installed_at: Mapped[datetime] = mapped_column(sa.DateTime, nullable=False)
    __table_args__ = (sa.CheckConstraint("singleton_id = 1", name="ck_installation_singleton"),)

class InstallationRejected(RuntimeError):
    pass

def load_contract():
    raw = CONTRACT_PATH.read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()

def type_signature(t):
    if isinstance(t, (sa.Boolean, sa.Integer)):
        return {"family": "integer"}
    if isinstance(t, sa.Numeric):
        return {"family": "numeric", "precision": t.precision, "scale": t.scale}
    if isinstance(t, sa.JSON): return {"family": "json"}
    if isinstance(t, sa.DateTime): return {"family": "datetime"}
    if isinstance(t, sa.Date): return {"family": "date"}
    if isinstance(t, sa.Text): return {"family": "text"}
    if isinstance(t, sa.String): return {"family": "string", "length": t.length}
    raise InstallationRejected("UNSUPPORTED_SCHEMA_TYPE")

def normalize_check(expression):
    return re.sub(r'[\s`()]+','',expression).lower()

def verify_schema(connection, *, revision=CURRENT_REVISION):
    contract, _ = load_contract(); inspector = sa.inspect(connection)
    if revision not in KNOWN_REVISIONS: raise InstallationRejected("LEGACY_OR_UNKNOWN_REVISION")
    for rev, name in EXTENSION_REVISIONS[:KNOWN_REVISIONS.index(revision)]:
        contract['tables'].update(json.loads(CONTRACT_PATH.with_name(name).read_text(encoding='utf-8'))['tables'])
    tables = set(inspector.get_table_names()) - {"alembic_version"}
    if tables != set(contract["tables"]) or inspector.get_view_names():
        raise InstallationRejected("SCHEMA_TABLE_SET_MISMATCH")
    for name, expected in contract["tables"].items():
        cols = {c["name"]: {**type_signature(c["type"]), "nullable": c["nullable"]}
                for c in inspector.get_columns(name)}
        if cols != expected["columns"]:
            raise InstallationRejected("SCHEMA_COLUMNS_MISMATCH")
        if inspector.get_pk_constraint(name)["constrained_columns"] != expected["primary_key"]:
            raise InstallationRejected("SCHEMA_PRIMARY_KEY_MISMATCH")
        fks = {(tuple(x["constrained_columns"]), x["referred_table"], tuple(x["referred_columns"]))
               for x in inspector.get_foreign_keys(name)}
        required = {(tuple(x[0]), x[1], tuple(x[2])) for x in expected["foreign_keys"]}
        if fks != required: raise InstallationRejected("SCHEMA_FOREIGN_KEY_MISMATCH")
        checks={normalize_check(x['sqltext']) for x in inspector.get_check_constraints(name)}
        if checks!=set(expected.get('checks',[])):raise InstallationRejected('SCHEMA_CHECK_MISMATCH')
        indexes = inspector.get_indexes(name)
        unique = {tuple(x["column_names"]) for x in inspector.get_unique_constraints(name)}
        unique |= {tuple(x["column_names"]) for x in indexes if x.get("unique")}
        if {tuple(x) for x in expected["unique"]} != unique:
            raise InstallationRejected("SCHEMA_UNIQUE_MISMATCH")
        actual = {(x["name"], tuple(x["column_names"]), bool(x["unique"])) for x in indexes}
        if not {(x[0], tuple(x[1]), x[2]) for x in expected["indexes"]} <= actual:
            raise InstallationRejected("SCHEMA_INDEX_MISMATCH")
        if connection.dialect.name == "mysql":
            engine = inspector.get_table_options(name).get("mysql_engine", "")
            if engine.lower() != "innodb": raise InstallationRejected("SCHEMA_ENGINE_MISMATCH")
    return True

def require_canonical(connection, *, check_schema=True, require_mysql=False, allow_baseline=False):
    if require_mysql:
        if connection.dialect.name != "mysql": raise InstallationRejected("MYSQL_84_REQUIRED")
        version = connection.execute(sa.text("SELECT VERSION()")).scalar_one()
        if not str(version).startswith("8.4.") or "mariadb" in str(version).lower():
            raise InstallationRejected("MYSQL_84_REQUIRED")
    tables = set(sa.inspect(connection).get_table_names())
    if not {"alembic_version", "installation_provenance"} <= tables:
        raise InstallationRejected("INSTALLATION_PROVENANCE_MISSING")
    heads = list(connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalars())
    # allow_baseline (migration preflight only): an older known revision may be upgraded in place.
    if heads != [CURRENT_REVISION] and not (allow_baseline and len(heads) == 1 and heads[0] in KNOWN_REVISIONS): raise InstallationRejected("LEGACY_OR_UNKNOWN_REVISION")
    records = connection.execute(sa.select(InstallationProvenance.__table__)).mappings().all()
    _, checksum = load_contract()
    if len(records) != 1: raise InstallationRejected("INSTALLATION_PROVENANCE_INVALID")
    r = dict(records[0])
    try:
        good_uuid = str(uuid.UUID(r["installation_id"])) == r["installation_id"]
    except (TypeError, ValueError, AttributeError): good_uuid = False
    if (r["singleton_id"] != 1 or not good_uuid or r["baseline_revision"] != BASELINE_REVISION
        or r["source_kind"] != SOURCE_KIND or r["contract_sha256"] != checksum
        or not isinstance(r["installed_at"], datetime)):
        raise InstallationRejected("INSTALLATION_PROVENANCE_INVALID")
    if check_schema: verify_schema(connection, revision=heads[0])
    return {"installation_id": r["installation_id"], "baseline_revision": BASELINE_REVISION,
            "source_kind": SOURCE_KIND, "contract_sha256": checksum,
            "installed_at": r["installed_at"].isoformat()}

def migration_preflight(connection):
    inspector = sa.inspect(connection); tables = set(inspector.get_table_names())
    if inspector.get_view_names(): raise InstallationRejected("NONEMPTY_DATABASE_REFUSED")
    if tables <= {"alembic_version"}:
        if "alembic_version" in tables and connection.execute(sa.text("SELECT COUNT(*) FROM alembic_version")).scalar_one():
            raise InstallationRejected("STAMP_WITHOUT_SCHEMA_REFUSED")
        return "EMPTY"
    require_canonical(connection, require_mysql=connection.dialect.name != "sqlite", allow_baseline=True)
    return "CANONICAL"

def main():
    from .config import Settings
    from .core import make_engine
    parser=argparse.ArgumentParser(); parser.add_argument("action", choices=["verify"]); parser.parse_args()
    cfg=Settings(); engine=make_engine(cfg.database_url)
    try:
        with engine.connect() as connection:
            result=require_canonical(connection, require_mysql=cfg.env == "production")
        print(json.dumps(result, ensure_ascii=False))
    except (InstallationRejected, sa.exc.SQLAlchemyError):
        raise SystemExit("BLOCKED: canonical installation verification failed") from None
    finally: engine.dispose()

if __name__ == "__main__": main()
