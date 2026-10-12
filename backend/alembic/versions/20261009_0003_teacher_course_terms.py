"""Add teacher_course_terms (教务排课 + 超星课程库 teacher-course-term rows) and school_courses (教务课程总库 credit/hours); additive only."""
from alembic import op
import sqlalchemy as sa
revision = "20261009_0003"
down_revision = "20261008_0002"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('teacher_course_terms',
    sa.Column('external_key', sa.String(length=200), nullable=False),
    sa.Column('origin', sa.String(length=8), nullable=False),
    sa.Column('staff_no', sa.String(length=64), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=True),
    sa.Column('teacher_name', sa.String(length=100), nullable=False),
    sa.Column('course_code', sa.String(length=64), nullable=False),
    sa.Column('course_name', sa.String(length=300), nullable=False),
    sa.Column('term_name', sa.String(length=64), nullable=False),
    sa.Column('credit', sa.Numeric(precision=8, scale=2), nullable=True),
    sa.Column('hours', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('extra', sa.JSON(), nullable=False),
    sa.Column('source_stamp', sa.String(length=64), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('source', sa.String(length=100), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('external_key'),
    mysql_charset='utf8mb4',
    mysql_collate='utf8mb4_0900_ai_ci',
    mysql_engine='InnoDB'
    )
    op.create_index(op.f('ix_teacher_course_terms_origin'), 'teacher_course_terms', ['origin'], unique=False)
    op.create_index(op.f('ix_teacher_course_terms_staff_no'), 'teacher_course_terms', ['staff_no'], unique=False)
    op.create_index(op.f('ix_teacher_course_terms_user_id'), 'teacher_course_terms', ['user_id'], unique=False)
    op.create_index(op.f('ix_teacher_course_terms_course_code'), 'teacher_course_terms', ['course_code'], unique=False)
    op.create_index(op.f('ix_teacher_course_terms_term_name'), 'teacher_course_terms', ['term_name'], unique=False)
    op.create_index(op.f('ix_teacher_course_terms_active'), 'teacher_course_terms', ['active'], unique=False)
    op.create_index('ix_teacher_course_term_staff_term', 'teacher_course_terms', ['staff_no', 'term_name'], unique=False)
    op.create_table('school_courses',
    sa.Column('external_key', sa.String(length=128), nullable=False),
    sa.Column('code', sa.String(length=100), nullable=False),
    sa.Column('name', sa.String(length=300), nullable=False),
    sa.Column('credit', sa.Numeric(precision=8, scale=2), nullable=True),
    sa.Column('hours', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('weekly_hours', sa.Numeric(precision=8, scale=2), nullable=True),
    sa.Column('dept', sa.String(length=300), nullable=False),
    sa.Column('course_version', sa.String(length=32), nullable=False),
    sa.Column('extra', sa.JSON(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('source', sa.String(length=100), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('external_key'),
    mysql_charset='utf8mb4',
    mysql_collate='utf8mb4_0900_ai_ci',
    mysql_engine='InnoDB'
    )
    op.create_index(op.f('ix_school_courses_code'), 'school_courses', ['code'], unique=False)
    op.create_index(op.f('ix_school_courses_active'), 'school_courses', ['active'], unique=False)

def downgrade():
    raise RuntimeError("Destructive teacher-course downgrade is not supported")
