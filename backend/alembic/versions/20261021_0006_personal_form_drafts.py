"""Private partial input drafts; no existing business rows are changed."""
from alembic import op
import sqlalchemy as sa

revision="20261021_0006"
down_revision="20261013_0005"
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('form_drafts',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('created_at',sa.DateTime(),nullable=False),
        sa.Column('user_id',sa.String(36),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('role_id',sa.String(36),sa.ForeignKey('roles.id'),nullable=False),
        sa.Column('org_id',sa.String(36),sa.ForeignKey('organizations.id'),nullable=False),
        sa.Column('kind',sa.String(32),nullable=False),
        sa.Column('context_key',sa.String(160),nullable=False),
        sa.Column('title',sa.String(200),nullable=False),
        sa.Column('payload',sa.JSON(),nullable=False),
        sa.Column('source_version',sa.Integer(),nullable=True),
        sa.Column('state',sa.String(16),nullable=False),
        sa.Column('version',sa.Integer(),nullable=False),
        sa.Column('updated_at',sa.DateTime(),nullable=False),
        sa.UniqueConstraint('user_id','role_id','org_id','kind','context_key',name='uq_form_draft_scope'),
        mysql_engine='InnoDB')


def downgrade():
    raise RuntimeError('Personal drafts must be preserved; automatic downgrade is not supported')
