"""organization assessment and per-item sync evidence

Revision ID: 20260917_0002
Revises: 20260917_0001
"""
from alembic import op
import sqlalchemy as sa
import uuid
from datetime import datetime, timezone
revision='20260917_0002'
down_revision='20260917_0001'
branch_labels=None
depends_on=None

def _new_id():
    return str(uuid.uuid4())

def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)

def _backfill_reference_data(bind):
    """Upgrade-safe, dialect-neutral backfill from the authoritative 0001 facts.

    Existing training records are teaching/business facts only. They seed project/course/class
    reference masters, but are deliberately NOT copied into teacher_participations because the
    old schema cannot prove that a teaching record was also a teacher-learning record.
    Existing staff accounts seed a local HR profile so a school upgrading from 0001 does not
    start with an empty teacher reference catalog. External HR sync may later supersede it.
    """
    now=_utcnow()
    organizations=sa.table('organizations',sa.column('id',sa.String(36)),sa.column('code',sa.String(64)))
    users=sa.table('users',sa.column('id',sa.String(36)),sa.column('staff_no',sa.String(64)),sa.column('name',sa.String(100)),
                   sa.column('title',sa.String(80)),sa.column('org_id',sa.String(36)),sa.column('active',sa.Boolean()))
    profiles=sa.table('teacher_hr_profiles',sa.column('staff_no',sa.String(64)),sa.column('user_id',sa.String(36)),sa.column('name',sa.String(100)),
                      sa.column('title',sa.String(80)),sa.column('org_code',sa.String(64)),sa.column('active',sa.Boolean()),
                      sa.column('source',sa.String(100)),sa.column('extra',sa.JSON()),sa.column('source_updated_at',sa.DateTime()),
                      sa.column('version',sa.Integer()),sa.column('id',sa.String(36)),sa.column('created_at',sa.DateTime()))
    staff_rows=bind.execute(sa.select(users.c.id,users.c.staff_no,users.c.name,users.c.title,users.c.active,organizations.c.code.label('org_code'))
        .select_from(users.join(organizations,users.c.org_id==organizations.c.id))
        .where(users.c.staff_no.is_not(None),users.c.staff_no!='')).mappings().all()
    if staff_rows:
        bind.execute(profiles.insert(),[{'id':_new_id(),'staff_no':r['staff_no'],'user_id':r['id'],'name':r['name'],
          'title':r['title'] or '','org_code':r['org_code'],'active':bool(r['active']),'source':'升级回填：本地账号',
          'extra':{'backfilled_from':'users','authoritative_external_hr':False},'source_updated_at':None,'version':1,'created_at':now} for r in staff_rows])

    records=sa.table('training_records',sa.column('id',sa.String(36)),sa.column('created_at',sa.DateTime()),
        sa.column('project_code',sa.String(64)),sa.column('project',sa.String(160)),sa.column('course_code',sa.String(64)),sa.column('course',sa.String(160)),
        sa.column('class_code',sa.String(64)),sa.column('class_name',sa.String(160)))
    projects=sa.table('training_projects',sa.column('code',sa.String(64)),sa.column('name',sa.String(160)),sa.column('external_key',sa.String(128)),
        sa.column('start_date',sa.Date()),sa.column('end_date',sa.Date()),sa.column('active',sa.Boolean()),sa.column('source',sa.String(100)),
        sa.column('version',sa.Integer()),sa.column('id',sa.String(36)),sa.column('created_at',sa.DateTime()))
    courses=sa.table('training_courses',sa.column('code',sa.String(64)),sa.column('name',sa.String(160)),sa.column('project_code',sa.String(64)),sa.column('external_key',sa.String(128)),
        sa.column('active',sa.Boolean()),sa.column('source',sa.String(100)),sa.column('version',sa.Integer()),sa.column('id',sa.String(36)),sa.column('created_at',sa.DateTime()))
    classes=sa.table('training_classes',sa.column('code',sa.String(64)),sa.column('name',sa.String(160)),sa.column('project_code',sa.String(64)),sa.column('course_code',sa.String(64)),
        sa.column('start_date',sa.Date()),sa.column('end_date',sa.Date()),sa.column('active',sa.Boolean()),sa.column('source',sa.String(100)),
        sa.column('version',sa.Integer()),sa.column('id',sa.String(36)),sa.column('created_at',sa.DateTime()))
    rows=bind.execute(sa.select(records).order_by(records.c.created_at,records.c.id)).mappings().all()
    pmap,cmap,clmap={},{},{}
    for r in rows:
        if r['project_code']:
            pmap[r['project_code']]={'id':_new_id(),'code':r['project_code'],'name':r['project'] or r['project_code'],'external_key':None,
              'start_date':None,'end_date':None,'active':True,'source':'升级回填：培训业务台账','version':1,'created_at':now}
        if r['course_code']:
            cmap[r['course_code']]={'id':_new_id(),'code':r['course_code'],'name':r['course'] or r['course_code'],'project_code':r['project_code'] or None,
              'external_key':None,'active':True,'source':'升级回填：培训业务台账','version':1,'created_at':now}
        if r['class_code']:
            clmap[r['class_code']]={'id':_new_id(),'code':r['class_code'],'name':r['class_name'] or r['class_code'],'project_code':r['project_code'] or '',
              'course_code':r['course_code'] or '','start_date':None,'end_date':None,'active':True,'source':'升级回填：培训业务台账','version':1,'created_at':now}
    if pmap:bind.execute(projects.insert(),list(pmap.values()))
    if cmap:bind.execute(courses.insert(),list(cmap.values()))
    if clmap:bind.execute(classes.insert(),list(clmap.values()))

def upgrade():
    op.create_table('organization_assessment_rules',
      sa.Column('target_kind',sa.String(20),nullable=False),sa.Column('name',sa.String(100),nullable=False),
      sa.Column('version_no',sa.Integer(),nullable=False),sa.Column('period_id',sa.String(36),sa.ForeignKey('periods.id'),nullable=False),
      sa.Column('config',sa.JSON(),nullable=False),sa.Column('fingerprint',sa.String(64),nullable=False),sa.Column('state',sa.String(20),nullable=False),
      sa.Column('created_by',sa.String(36),sa.ForeignKey('users.id'),nullable=False),sa.Column('reason',sa.Text(),nullable=False),
      sa.Column('version',sa.Integer(),nullable=False),sa.Column('id',sa.String(36),primary_key=True),sa.Column('created_at',sa.DateTime(),nullable=False),
      sa.UniqueConstraint('target_kind','period_id','version_no',name='uq_org_assessment_rule_version'))
    op.create_index('ix_org_assessment_rules_target_kind','organization_assessment_rules',['target_kind'])
    op.create_index('ix_org_assessment_rules_period_id','organization_assessment_rules',['period_id'])
    op.create_index('ix_org_assessment_rules_state','organization_assessment_rules',['state'])
    op.create_table('organization_rule_trials',
      sa.Column('rule_id',sa.String(36),sa.ForeignKey('organization_assessment_rules.id'),nullable=False),sa.Column('fingerprint',sa.String(64),nullable=False),
      sa.Column('target_ids',sa.JSON(),nullable=False),sa.Column('result',sa.JSON(),nullable=False),sa.Column('actor_id',sa.String(36),sa.ForeignKey('users.id'),nullable=False),
      sa.Column('id',sa.String(36),primary_key=True),sa.Column('created_at',sa.DateTime(),nullable=False))
    op.create_index('ix_organization_rule_trials_rule_id','organization_rule_trials',['rule_id'])
    op.create_table('organization_assessments',
      sa.Column('target_kind',sa.String(20),nullable=False),sa.Column('target_id',sa.String(36),sa.ForeignKey('organizations.id'),nullable=False),
      sa.Column('period_id',sa.String(36),sa.ForeignKey('periods.id'),nullable=False),sa.Column('rule_id',sa.String(36),sa.ForeignKey('organization_assessment_rules.id'),nullable=False),
      sa.Column('score',sa.Numeric(8,2),nullable=False),sa.Column('detail',sa.JSON(),nullable=False),sa.Column('source_snapshot',sa.JSON(),nullable=False),
      sa.Column('state',sa.String(24),nullable=False),sa.Column('version',sa.Integer(),nullable=False),sa.Column('generated_by',sa.String(36),sa.ForeignKey('users.id'),nullable=False),
      sa.Column('reviewed_by',sa.String(36),sa.ForeignKey('users.id'),nullable=True),sa.Column('school_audited_by',sa.String(36),sa.ForeignKey('users.id'),nullable=True),
      sa.Column('archive',sa.JSON(),nullable=True),sa.Column('archive_sha256',sa.String(64),nullable=True),sa.Column('id',sa.String(36),primary_key=True),sa.Column('created_at',sa.DateTime(),nullable=False),
      sa.UniqueConstraint('target_kind','target_id','period_id',name='uq_org_assessment_target_period'))
    op.create_index('ix_organization_assessments_target_kind','organization_assessments',['target_kind'])
    op.create_index('ix_organization_assessments_target_id','organization_assessments',['target_id'])
    op.create_index('ix_organization_assessments_period_id','organization_assessments',['period_id'])
    op.create_index('ix_organization_assessments_state','organization_assessments',['state'])
    op.create_index('ix_org_assessment_period_state','organization_assessments',['period_id','state'])
    op.create_table('organization_assessment_metric_evidence',
      sa.Column('assessment_id',sa.String(36),sa.ForeignKey('organization_assessments.id'),nullable=False),sa.Column('metric_code',sa.String(64),nullable=False),
      sa.Column('metric_name',sa.String(100),nullable=False),sa.Column('raw_value',sa.String(100),nullable=False),sa.Column('data_source',sa.String(200),nullable=False),
      sa.Column('scope_snapshot',sa.JSON(),nullable=False),sa.Column('formula',sa.String(500),nullable=False),sa.Column('target_value',sa.String(100),nullable=False),
      sa.Column('weight',sa.Numeric(7,2),nullable=False),sa.Column('rule_version',sa.Integer(),nullable=False),sa.Column('calculated_score',sa.Numeric(8,2),nullable=False),
      sa.Column('measured_at',sa.DateTime(),nullable=False),sa.Column('id',sa.String(36),primary_key=True),sa.Column('created_at',sa.DateTime(),nullable=False),
      sa.UniqueConstraint('assessment_id','metric_code',name='uq_org_assessment_metric'))
    op.create_index('ix_org_metric_evidence_assessment_id','organization_assessment_metric_evidence',['assessment_id'])
    op.create_table('sync_items',
      sa.Column('task_id',sa.String(36),sa.ForeignKey('tasks.id'),nullable=False),sa.Column('connection_id',sa.String(36),sa.ForeignKey('connections.id'),nullable=False),
      sa.Column('data_type',sa.String(64),nullable=False),sa.Column('business_key',sa.String(160),nullable=False),sa.Column('payload_hash',sa.String(64),nullable=False),
      sa.Column('idempotency_key',sa.String(64),nullable=False),sa.Column('payload',sa.JSON(),nullable=False),sa.Column('state',sa.String(20),nullable=False),
      sa.Column('attempts',sa.Integer(),nullable=False),sa.Column('next_at',sa.DateTime(),nullable=False),sa.Column('result',sa.JSON(),nullable=False),sa.Column('error',sa.Text(),nullable=False),
      sa.Column('version',sa.Integer(),nullable=False),sa.Column('id',sa.String(36),primary_key=True),sa.Column('created_at',sa.DateTime(),nullable=False),
      sa.UniqueConstraint('connection_id','data_type','idempotency_key',name='uq_sync_item_idempotency'))
    for name,col in [('ix_sync_items_task_id','task_id'),('ix_sync_items_connection_id','connection_id'),('ix_sync_items_data_type','data_type'),('ix_sync_items_business_key','business_key'),('ix_sync_items_state','state'),('ix_sync_items_next_at','next_at')]:op.create_index(name,'sync_items',[col])
    op.create_index('ix_sync_item_task_state','sync_items',['task_id','state'])
    op.create_table('sync_call_logs',
      sa.Column('item_id',sa.String(36),sa.ForeignKey('sync_items.id'),nullable=False),sa.Column('attempt',sa.Integer(),nullable=False),
      sa.Column('request_digest',sa.String(64),nullable=False),sa.Column('response_code',sa.String(40),nullable=False),sa.Column('result',sa.String(20),nullable=False),
      sa.Column('message',sa.Text(),nullable=False),sa.Column('id',sa.String(36),primary_key=True),sa.Column('created_at',sa.DateTime(),nullable=False),
      sa.UniqueConstraint('item_id','attempt',name='uq_sync_call_attempt'))
    op.create_index('ix_sync_call_logs_item_id','sync_call_logs',['item_id'])

    op.create_table('teacher_hr_profiles',
      sa.Column('staff_no',sa.String(64),nullable=False),sa.Column('user_id',sa.String(36),sa.ForeignKey('users.id'),nullable=True),
      sa.Column('name',sa.String(100),nullable=False),sa.Column('title',sa.String(80),nullable=False),sa.Column('org_code',sa.String(64),nullable=False),
      sa.Column('active',sa.Boolean(),nullable=False),sa.Column('source',sa.String(100),nullable=False),sa.Column('extra',sa.JSON(),nullable=False),
      sa.Column('source_updated_at',sa.DateTime(),nullable=True),sa.Column('version',sa.Integer(),nullable=False),sa.Column('id',sa.String(36),primary_key=True),sa.Column('created_at',sa.DateTime(),nullable=False),
      sa.UniqueConstraint('staff_no',name='uq_teacher_hr_profiles_staff_no'))
    for name,col in [('ix_teacher_hr_profiles_staff_no','staff_no'),('ix_teacher_hr_profiles_user_id','user_id'),('ix_teacher_hr_profiles_org_code','org_code')]:op.create_index(name,'teacher_hr_profiles',[col])
    op.create_table('training_projects',
      sa.Column('code',sa.String(64),nullable=False),sa.Column('name',sa.String(160),nullable=False),sa.Column('external_key',sa.String(128),nullable=True),
      sa.Column('start_date',sa.Date(),nullable=True),sa.Column('end_date',sa.Date(),nullable=True),sa.Column('active',sa.Boolean(),nullable=False),sa.Column('source',sa.String(100),nullable=False),
      sa.Column('version',sa.Integer(),nullable=False),sa.Column('id',sa.String(36),primary_key=True),sa.Column('created_at',sa.DateTime(),nullable=False),sa.UniqueConstraint('code',name='uq_training_projects_code'))
    for name,col in [('ix_training_projects_code','code'),('ix_training_projects_external_key','external_key'),('ix_training_projects_active','active')]:op.create_index(name,'training_projects',[col])
    op.create_table('training_courses',
      sa.Column('code',sa.String(64),nullable=False),sa.Column('name',sa.String(160),nullable=False),sa.Column('project_code',sa.String(64),nullable=True),
      sa.Column('external_key',sa.String(128),nullable=True),sa.Column('active',sa.Boolean(),nullable=False),sa.Column('source',sa.String(100),nullable=False),sa.Column('version',sa.Integer(),nullable=False),
      sa.Column('id',sa.String(36),primary_key=True),sa.Column('created_at',sa.DateTime(),nullable=False),sa.UniqueConstraint('code',name='uq_training_courses_code'))
    for name,col in [('ix_training_courses_code','code'),('ix_training_courses_project_code','project_code'),('ix_training_courses_external_key','external_key'),('ix_training_courses_active','active')]:op.create_index(name,'training_courses',[col])
    op.create_table('training_classes',
      sa.Column('code',sa.String(64),nullable=False),sa.Column('name',sa.String(160),nullable=False),sa.Column('project_code',sa.String(64),nullable=False),sa.Column('course_code',sa.String(64),nullable=False),
      sa.Column('start_date',sa.Date(),nullable=True),sa.Column('end_date',sa.Date(),nullable=True),sa.Column('active',sa.Boolean(),nullable=False),sa.Column('source',sa.String(100),nullable=False),sa.Column('version',sa.Integer(),nullable=False),
      sa.Column('id',sa.String(36),primary_key=True),sa.Column('created_at',sa.DateTime(),nullable=False),sa.UniqueConstraint('code',name='uq_training_classes_code'))
    for name,col in [('ix_training_classes_code','code'),('ix_training_classes_project_code','project_code'),('ix_training_classes_course_code','course_code'),('ix_training_classes_active','active')]:op.create_index(name,'training_classes',[col])
    op.create_table('teacher_participations',
      sa.Column('external_key',sa.String(128),nullable=False),sa.Column('teacher_id',sa.String(36),sa.ForeignKey('users.id'),nullable=False),sa.Column('event_date',sa.Date(),nullable=False),
      sa.Column('project_code',sa.String(64),nullable=False),sa.Column('project',sa.String(160),nullable=False),sa.Column('course_code',sa.String(64),nullable=False),sa.Column('course',sa.String(160),nullable=False),
      sa.Column('hours',sa.Numeric(12,2),nullable=False),sa.Column('source',sa.String(100),nullable=False),sa.Column('batch_id',sa.String(36),nullable=True),sa.Column('state',sa.String(20),nullable=False),sa.Column('version',sa.Integer(),nullable=False),
      sa.Column('id',sa.String(36),primary_key=True),sa.Column('created_at',sa.DateTime(),nullable=False),sa.CheckConstraint('hours >= 0',name='ck_teacher_participations_hours_nonnegative'),sa.UniqueConstraint('external_key',name='uq_teacher_participations_external_key'))
    for name,col in [('ix_teacher_participations_teacher_id','teacher_id'),('ix_teacher_participations_event_date','event_date'),('ix_teacher_participations_project_code','project_code'),('ix_teacher_participations_course_code','course_code'),('ix_teacher_participations_batch_id','batch_id'),('ix_teacher_participations_state','state')]:op.create_index(name,'teacher_participations',[col])
    op.create_index('ix_teacher_participation_teacher_date','teacher_participations',['teacher_id','event_date'])
    op.create_table('inbound_batches',
      sa.Column('connection_id',sa.String(36),sa.ForeignKey('connections.id'),nullable=False),sa.Column('data_type',sa.String(64),nullable=False),sa.Column('owner_id',sa.String(36),sa.ForeignKey('users.id'),nullable=False),
      sa.Column('source_label',sa.String(160),nullable=False),sa.Column('state',sa.String(20),nullable=False),sa.Column('total',sa.Integer(),nullable=False),sa.Column('errors',sa.Integer(),nullable=False),sa.Column('receipt',sa.JSON(),nullable=False),sa.Column('version',sa.Integer(),nullable=False),
      sa.Column('id',sa.String(36),primary_key=True),sa.Column('created_at',sa.DateTime(),nullable=False))
    for name,col in [('ix_inbound_batches_connection_id','connection_id'),('ix_inbound_batches_data_type','data_type'),('ix_inbound_batches_owner_id','owner_id'),('ix_inbound_batches_state','state')]:op.create_index(name,'inbound_batches',[col])
    op.create_table('inbound_rows',
      sa.Column('batch_id',sa.String(36),sa.ForeignKey('inbound_batches.id'),nullable=False),sa.Column('row_no',sa.Integer(),nullable=False),sa.Column('business_key',sa.String(160),nullable=False),
      sa.Column('raw',sa.JSON(),nullable=False),sa.Column('mapped',sa.JSON(),nullable=False),sa.Column('errors',sa.JSON(),nullable=False),sa.Column('id',sa.String(36),primary_key=True),sa.Column('created_at',sa.DateTime(),nullable=False),
      sa.UniqueConstraint('batch_id','row_no',name='uq_inbound_rows_batch_row'))
    op.create_index('ix_inbound_rows_batch_id','inbound_rows',['batch_id']);op.create_index('ix_inbound_rows_business_key','inbound_rows',['business_key'])
    op.create_table('integration_schedules',
      sa.Column('connection_id',sa.String(36),sa.ForeignKey('connections.id'),nullable=False),sa.Column('data_type',sa.String(64),nullable=False),
      sa.Column('frequency_minutes',sa.Integer(),nullable=False),sa.Column('auto_commit',sa.Boolean(),nullable=False),sa.Column('active',sa.Boolean(),nullable=False),
      sa.Column('approved_by',sa.String(36),sa.ForeignKey('users.id'),nullable=False),sa.Column('next_at',sa.DateTime(),nullable=False),sa.Column('last_run_at',sa.DateTime(),nullable=True),
      sa.Column('last_cursor',sa.String(500),nullable=True),sa.Column('last_error',sa.String(500),nullable=False),sa.Column('version',sa.Integer(),nullable=False),
      sa.Column('id',sa.String(36),primary_key=True),sa.Column('created_at',sa.DateTime(),nullable=False),
      sa.UniqueConstraint('connection_id','data_type',name='uq_integration_schedule_connection_type'))
    for name,col in [('ix_integration_schedules_connection_id','connection_id'),('ix_integration_schedules_data_type','data_type'),('ix_integration_schedules_active','active'),('ix_integration_schedules_approved_by','approved_by'),('ix_integration_schedules_next_at','next_at')]:op.create_index(name,'integration_schedules',[col])
    op.create_index('ix_integration_schedule_due','integration_schedules',['active','next_at'])

    # Preserve existing 0001 business facts when this migration is applied to an upgraded school.
    _backfill_reference_data(op.get_bind())

    settings=sa.table('settings',sa.column('key',sa.String(100)),sa.column('value',sa.JSON()),sa.column('version',sa.Integer()))
    bind=op.get_bind()
    existing=set(bind.execute(sa.select(settings.c.key).where(settings.c.key.in_(['business_dictionary','import_policy']))).scalars())
    rows=[]
    if 'business_dictionary' not in existing:
        rows.append({'key':'business_dictionary','value':{
          'notice_categories':['业务通知','政策通知','操作通知'],
          'record_sources':['经核对人工录入','Excel导入','学校数据中台'],
          'status_labels':{
            'DRAFT':'草稿','SUBMITTED':'待资质审核','APPROVED':'审核通过','RETURNED':'退回补充','TEACHER':'教师确认','DEPARTMENT':'教研室确认','COLLEGE':'学院确认','SCHOOL':'学校审核','READY':'待归档','ARCHIVED':'已归档','GENERATED':'待组织复核','REVIEWED':'待学校审核','SCHOOL_APPROVED':'待归档','OPEN':'进行中','CLOSED':'已关闭','RESOLVED':'已解决','ACTIVE':'已启用','INACTIVE':'已停用','VALID':'有效记录','PENDING':'排队中','RUNNING':'处理中','RETRY':'等待重试','FAILED':'处理失败','BLOCKED':'未接通 / 已阻断','DONE':'已完成','PREVIEW':'待确认导入','COMMITTED':'已入库','NOT_CONNECTED':'未对接','VALIDATED':'仅本地校验','EXPIRING':'有效期核对','BASE':'初始积分','RECALC':'重算差额','MANUAL':'人工调整','SUCCESS':'成功','DENIED':'已拦截','ERROR':'异常','VOID':'已作废'},
        },'version':1})
    if 'import_policy' not in existing:rows.append({'key':'import_policy','value':{'max_rows':5000},'version':1})
    if rows:op.bulk_insert(settings,rows)

def downgrade():
    op.execute(sa.text("DELETE FROM settings WHERE `key` IN ('business_dictionary','import_policy')"))
    for name in ('integration_schedules','inbound_rows','inbound_batches','teacher_participations','training_classes','training_courses','training_projects','teacher_hr_profiles','sync_call_logs','sync_items','organization_assessment_metric_evidence','organization_assessments','organization_rule_trials','organization_assessment_rules'):
        op.drop_table(name)
