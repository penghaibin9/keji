"""Generate least-privilege MySQL grants for runtime and migration accounts.

Passwords are never embedded here; users are provisioned by mysql-init from
private secret SQL. Runtime has no DDL; append-only evidence receives only
SELECT/INSERT and installation/version tables are SELECT-only. Migration has DDL/DML.
"""
from . import installation  # register immutable installation provenance
from .models import Base
# Register extension tables before reading metadata.
from . import org_assessment, integrations, reference_data, inbound_sync  # noqa: F401

APPEND_ONLY_TABLES = frozenset({'audit_events','workflow_events','record_revisions',
    'qualification_revisions','point_entries','rule_trials','organization_rule_trials',
    'task_attempts','sync_call_logs','attachments'})

def q(name):return '`'+name.replace('`','``')+'`'

def sql(schema='nondegree',runtime_user='nondegree_app',migration_user='nondegree_migration'):
    statements=[
      f"REVOKE ALL PRIVILEGES, GRANT OPTION FROM '{runtime_user}'@'%';",
      f"REVOKE ALL PRIVILEGES, GRANT OPTION FROM '{migration_user}'@'%';",
    ]
    for table in sorted(Base.metadata.tables):
        privileges = ("SELECT" if table == "installation_provenance" else
                      "SELECT, INSERT" if table in APPEND_ONLY_TABLES else "SELECT, INSERT, UPDATE, DELETE")
        statements.append(f"GRANT {privileges} ON {q(schema)}.{q(table)} TO '{runtime_user}'@'%';")
    statements.append(f"GRANT SELECT ON {q(schema)}.`alembic_version` TO '{runtime_user}'@'%';")
    statements.append(f"GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, DROP, REFERENCES, CREATE VIEW, SHOW VIEW, TRIGGER ON {q(schema)}.* TO '{migration_user}'@'%';")
    statements.append('FLUSH PRIVILEGES;')
    return '\n'.join(statements)
