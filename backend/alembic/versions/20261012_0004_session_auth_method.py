"""Record authentication provenance on the server; old sessions remain local."""
from alembic import op
import sqlalchemy as sa

revision = "20261012_0004"
down_revision = "20261009_0003"
branch_labels = None
depends_on = None


def upgrade():
    pending=_existing_mismatches()
    op.add_column('users', sa.Column('authorization_pending', sa.Boolean(), nullable=False, server_default=sa.false()))
    for ident in pending:
        op.get_bind().execute(sa.text('UPDATE users SET authorization_pending=:pending,auth_version=auth_version+1,version=version+1 WHERE id=:id'),{'pending':True,'id':ident})
    op.add_column('auth_sessions', sa.Column('auth_method', sa.String(10), nullable=False, server_default='local'))


def downgrade():
    raise RuntimeError("Automatic authentication provenance downgrade is not supported")


def _existing_mismatches():
    # Preserve staff facts; the school must confirm authorization for unresolved moves.
    import json
    connection=op.get_bind()
    orgs={row['id']:row for row in connection.execute(sa.text('SELECT id,code,name,parent_id,active FROM organizations')).mappings()}
    def ancestors(ident):
        result=set()
        while ident in orgs and ident not in result:
            result.add(ident);ident=orgs[ident]['parent_id']
        return result
    rows=connection.execute(sa.text('SELECT u.id,u.org_id,h.org_code,h.extra FROM users u JOIN teacher_hr_profiles h ON u.staff_no=h.staff_no')).mappings().all()
    pending=[]
    for row in rows:
        extra=row['extra'] if isinstance(row['extra'],dict) else json.loads(row['extra'] or '{}')
        matches=[org for org in orgs.values() if org['active'] and org['code']==row['org_code']]
        if not matches and extra.get('org_name'):
            matches=[org for org in orgs.values() if org['active'] and org['name']==extra['org_name']]
        source=matches[0] if len(matches)==1 else None
        if source and (source['id'] in ancestors(row['org_id']) or row['org_id'] in ancestors(source['id'])):continue
        pending.append(row['id'])
    required=['assessment.archive', 'assessment.calculate', 'assessment.confirm', 'assessment.read', 'assessment.review', 'audit.read', 'data.export', 'dispute.resolve', 'dispute.write', 'export', 'file.read', 'file.write', 'import', 'notice.manage', 'notice.read', 'operations.read', 'organization.manage', 'organization.read', 'points.adjust', 'points.calculate', 'points.read', 'portal.read', 'qualification.read', 'qualification.review', 'qualification.write', 'records.read', 'records.write', 'roles.manage', 'rules.manage', 'settings.manage', 'sync.manage', 'users.manage']
    candidates=connection.execute(sa.text("SELECT u.id,r.permissions FROM users u JOIN roles r ON r.id=u.role_id JOIN organizations o ON o.id=u.org_id WHERE u.active=1 AND u.is_admin=1 AND r.active=1 AND r.kind='school' AND o.active=1 AND o.kind='school'")).mappings()
    admins=set()
    for row in candidates:
        permissions=row['permissions'] if isinstance(row['permissions'],list) else json.loads(row['permissions'])
        if isinstance(permissions,list) and len(permissions)==len(set(permissions)) and set(permissions)==set(required):admins.add(row['id'])
    if admins and not admins-set(pending):
        raise RuntimeError('迁移会使最后一位学校管理员失去授权，请先核对人事单位并设置备用管理员')
    return pending
