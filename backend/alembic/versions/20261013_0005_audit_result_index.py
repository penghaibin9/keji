"""Indexes for the security summary and the two big list screens (audit log, inbound batches).

- audit_events(result, created_at): the security summary reads the few DENIED rows of a large audit table.
- audit_events(created_at DESC, id ASC) and inbound_batches(created_at DESC, id ASC): the lists sort newest first
  with the id as tie-breaker; mixed directions cannot use a plain ascending index, so every page open sorted the whole table.

A school database may already carry the same index built by hand under another name. The installation contract checks
index names, so such an index is renamed to the contract name instead of being skipped.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261013_0005"
down_revision = "20261012_0004"
branch_labels = None
depends_on = None

# (name, table, columns, descending columns)
INDEXES = (
    ("ix_audit_result_time", "audit_events", ("result", "created_at"), ()),
    ("ix_audit_created_desc_id", "audit_events", ("created_at", "id"), ("created_at",)),
    ("ix_inbound_batches_created_desc_id", "inbound_batches", ("created_at", "id"), ("created_at",)),
)


def _descending(index):
    sorting = index.get("column_sorting") or {}
    return tuple(sorted(c for c, s in sorting.items() if "desc" in s))


def _same_shape(index, columns, desc):
    if index.get("unique") or list(index["column_names"]) != list(columns):
        return False
    # SQLite does not report the sort direction; MySQL does. Compare only when it is reported.
    return "column_sorting" not in index or _descending(index) == tuple(sorted(desc))


def _ensure(bind, name, table, columns, desc):
    existing = sa.inspect(bind).get_indexes(table)
    if any(x["name"] == name for x in existing):
        return
    twin = next((x for x in existing if _same_shape(x, columns, desc)), None)
    if twin is not None and bind.dialect.name == "mysql":
        op.execute(sa.text(f"ALTER TABLE `{table}` RENAME INDEX `{twin['name']}` TO `{name}`"))
        return
    if twin is not None:
        op.drop_index(twin["name"], table_name=table)
    op.create_index(name, table, [sa.text(f"{c} DESC") if c in desc else c for c in columns])


def upgrade():
    bind = op.get_bind()
    for name, table, columns, desc in INDEXES:
        _ensure(bind, name, table, columns, desc)


def downgrade():
    raise RuntimeError("Automatic index downgrade is not supported")
