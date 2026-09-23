#!/usr/bin/env python3
"""Read-only source assembly gate. It is not a procurement acceptance shortcut."""
from __future__ import annotations
import argparse
import ast
import json
import hashlib
from pathlib import Path

REQUIRED = [
 'backend/app/__init__.py','backend/app/config.py','backend/app/core.py','backend/app/schemas.py',
 'backend/app/main.py','backend/app/models.py','backend/app/services.py','backend/app/assessment_evidence.py','backend/app/read_queries.py',
 'backend/app/import_access.py','backend/app/org_evidence.py','backend/app/readiness.py','backend/app/access_logging.py','backend/app/excel_io.py','backend/app/integrations.py','backend/app/integration_status.py',
 'backend/app/org_assessment.py','backend/app/reference_data.py','backend/app/inbound_sync.py','backend/app/delivery.py',
 *['backend/app/routes/'+x+'.py' for x in ('auth','admin','business','calculations','files','tasks','integrations','reference','delivery')],
 'backend/app/database_snapshot.py','backend/app/installation.py','backend/canonical_release.json','backend/canonical_schema.json','backend/alembic_legacy_unverified/MANIFEST.json',
 'backend/app/worker.py','backend/app/healthcheck.py','backend/app/releasecheck.py',
 'backend/app/integration_center.py','backend/app/integration_diagnostics.py','backend/app/sso_identity.py',
 'backend/app/paged_inbound.py','backend/app/adapters/paged_datahub.py','backend/app/routes/integration_center.py','backend/app/routes/sso_trial.py',
 'frontend/integration-workspace.js','frontend/integration-drafts.js',
 'backend/app/cli.py','backend/app/grants.py','backend/app/maintenance.py',
 'backend/requirements.txt','backend/app/resources/integration-coordination.xlsx','frontend/index.html','frontend/icons.js','frontend/app.js','frontend/scope.js','frontend/styles.css','frontend/integration.css','frontend/portal.css','frontend/portal-ui.js',
 'deploy/Dockerfile.api','deploy/Dockerfile.frontend','deploy/compose.yml','deploy/nginx.conf','deploy/mysql-init/01-users.sh',
]


def inspect_assembly(root):
    root=Path(root)
    missing=[name for name in REQUIRED if not (root/name).is_file() or not (root/name).stat().st_size]
    python_errors=[]
    for p in (root/'backend').rglob('*.py'):
        try:ast.parse(p.read_text(encoding='utf-8'))
        except (SyntaxError,UnicodeError):python_errors.append(str(p.relative_to(root)))
    revisions=[]
    for p in (root/'backend/alembic/versions').glob('*.py'):
        if p.name=='__init__.py':continue
        try:
            tree=ast.parse(p.read_text(encoding='utf-8'));values={}
            for n in tree.body:
                if isinstance(n,ast.Assign):
                    for t in n.targets:
                        if isinstance(t,ast.Name) and t.id in {'revision','down_revision'}:values[t.id]=ast.literal_eval(n.value)
                if isinstance(n,ast.AnnAssign) and isinstance(n.target,ast.Name) and n.target.id in {'revision','down_revision'}:
                    values[n.target.id]=ast.literal_eval(n.value)
            if 'revision' in values:revisions.append(values)
        except (SyntaxError,ValueError,TypeError):python_errors.append(str(p.relative_to(root)))
    revision_ids={v['revision'] for v in revisions}
    parents=set()
    for v in revisions:
        parent=v.get('down_revision')
        parents.update(parent if isinstance(parent,(list,tuple)) else [parent] if parent else [])
    heads=sorted(revision_ids-parents)
    migration_ok=len(revisions)==1 and revision_ids=={'20260918_0001'} and revisions[0].get('down_revision') is None and heads==['20260918_0001']
    alembic_config=any((root/p).is_file() for p in ('backend/alembic.ini','alembic.ini'))
    migration_env=any((root/'backend').rglob('env.py'))
    integrity_ok=False
    try:
        lock=json.loads((root/'backend/canonical_release.json').read_text())
        allowed={'backend/canonical_schema.json','backend/alembic/versions/20260918_0001_canonical_fresh_school.py','backend/alembic_legacy_unverified/20260917_0002_org_assessment_and_sync.py'}
        integrity_ok=(set(lock['sha256'])==allowed and lock['baseline_revision']=='20260918_0001'
            and lock['installation_scope']=='fresh_school_only'
            and all(not (root/name).is_symlink() and hashlib.sha256((root/name).read_bytes()).hexdigest()==sha for name,sha in lock['sha256'].items()))
    except (OSError,ValueError,KeyError,TypeError):pass
    ok=integrity_ok and not missing and not python_errors and migration_ok and alembic_config and migration_env
    return {'status':'PASS' if ok else 'BLOCKED','kind':'SOURCE_ASSEMBLY_ONLY','missing':missing,
            'python_errors':python_errors,'observed_alembic_heads':heads,
            'application_expected_heads':['20260918_0001'],'installation_scope':'fresh_school_only','legacy_upgrade_allowed':False,
            'historical_graph_verified':False,'unverified_historical_parent':'20260917_0001',
            'canonical_files_hash_verified':integrity_ok,'legacy_evidence_preserved':integrity_ok,'migration_graph_verified':migration_ok,'alembic_config_present':alembic_config,
            'migration_env_present':migration_env,
            'procurement_acceptance':False,'deployment_allowed_by_this_check_alone':False}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);p.add_argument('--strict',action='store_true');p.add_argument('--output',type=Path);a=p.parse_args()
    result=inspect_assembly(a.root);payload=json.dumps(result,ensure_ascii=False,indent=2)
    if a.output:a.output.write_text(payload+'\n',encoding='utf-8')
    print(payload)
    raise SystemExit(2 if a.strict and result['status']!='PASS' else 0)
