"""Indexes for the security summary and the two big list screens (audit log, inbound batches).

- audit_events(result, created_at): the security summary reads the few DENIED rows of a large audit table.
- audit_events(created_at DESC, id ASC) and inbound_batches(created_at DESC, id ASC): the lists sort newest first
  with the id as tie-breaker; mixed directions cannot use a plain ascending index, so every page open sorted the whole table.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261013_0005"
down_revision = "20261012_0004"
branch_labels = None
depends_on = None

INDEX = "ix_audit_result_time"
NEWEST_FIRST = (("ix_audit_created_desc_id", "audit_events"), ("ix_inbound_batches_created_desc_id", "inbound_batches"))


def upgrade():
    inspector = sa.inspect(op.get_bind())
    # A school database may already carry these indexes (built by hand as an emergency fix, under another name):
    # the plain one is matched by columns, the descending ones by name.
    existing = inspector.get_indexes("audit_events")
    if not any(x["name"] == INDEX or list(x["column_names"]) == ["result", "created_at"] for x in existing):
        op.create_index(INDEX, "audit_events", ["result", "created_at"])
    for name, table in NEWEST_FIRST:
        if name not in {x["name"] for x in inspector.get_indexes(table)}:
            op.create_index(name, table, [sa.text("created_at DESC"), sa.text("id ASC")])


def downgrade():
    raise RuntimeError("Automatic index downgrade is not supported")
