"""Index audit_events(result, created_at): the security summary reads the few DENIED rows of a large audit table."""
from alembic import op
import sqlalchemy as sa

revision = "20261013_0005"
down_revision = "20261012_0004"
branch_labels = None
depends_on = None

INDEX = "ix_audit_result_time"


def upgrade():
    # A school database may already carry this index (built by hand as an emergency fix); match by columns, not only by name.
    existing = sa.inspect(op.get_bind()).get_indexes("audit_events")
    if any(x["name"] == INDEX or list(x["column_names"]) == ["result", "created_at"] for x in existing):
        return
    op.create_index(INDEX, "audit_events", ["result", "created_at"])


def downgrade():
    raise RuntimeError("Automatic audit index downgrade is not supported")
