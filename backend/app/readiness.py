"""Read-only, initialization-aware startup probe. Never creates or seeds tables."""
from __future__ import annotations
from collections.abc import Mapping
import os
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from . import installation  # register immutable installation provenance
from .models import Org, Role, Setting, Guard
from .settings_catalog import setting_ok as _setting_ok
from .release_contract import EXPECTED_MIGRATION_HEADS
from .maintenance_guard import configured_maintenance


def _enabled_or_ambiguous(value):
    # Unknown values are not assumed safe in production.
    if value is None or value is False:
        return False
    return not (isinstance(value, str) and value.strip().lower() in {'false','0','no','off',''})


def _production_policy(cfg, maintenance):
    if cfg.env != 'production':
        return True
    for attr, env in (('seed_enabled','ND_SEED_ENABLED'),
                      ('auto_create_tables','ND_AUTO_CREATE_TABLES'),
                      ('auto_create_schema','ND_AUTO_CREATE_SCHEMA')):
        if _enabled_or_ambiguous(getattr(cfg, attr, None)) or _enabled_or_ambiguous(os.environ.get(env)):
            return False
    return maintenance['status'] in {'OPEN','ACTIVE'}


def collect_readiness(engine, cfg, release, *, expected_heads=EXPECTED_MIGRATION_HEADS):
    """Return stable public codes only; never expose SQL, URLs, passwords or errors.

    status describes DB/schema/initialization readiness for deployment probes.
    accepting_requests additionally reflects the durable maintenance latch.
    During an upgrade /api/health remains inspectable but business requests 503.
    """
    maintenance = configured_maintenance(cfg)
    report = {'status':'not_ready','release':release,
              'database':{'status':'unchecked'},
              'migration':{'status':'unchecked'},
              'initialization':{'status':'unchecked'},
              'maintenance':maintenance['status'], 'accepting_requests':False}
    if not _production_policy(cfg, maintenance):
        report['initialization'] = {'status':'invalid','reason':'PRODUCTION_POLICY'}
        return report
    try:
        with engine.connect() as conn:
            if conn.execute(text('SELECT 1')).scalar_one() != 1:
                report['database'] = {'status':'unavailable'}
                return report
            vendor = conn.dialect.name
            report['database'] = {'status':'ok','engine':vendor}
            if cfg.env == 'production':
                if vendor != 'mysql':
                    report['database']['status'] = 'unsupported'
                    return report
                version = conn.execute(text('SELECT VERSION()')).scalar_one()
                if not isinstance(version,str) or not version.startswith('8.4.') or 'mariadb' in version.lower():
                    report['database']['status'] = 'unsupported'
                    return report
            heads = frozenset(conn.execute(text('SELECT version_num FROM alembic_version')).scalars())
            if not expected_heads or heads != frozenset(expected_heads):
                report['migration'] = {'status':'mismatch'}
                return report
            report['migration'] = {'status':'ok'}
            if cfg.env == 'production':
                try: installation.require_canonical(conn, require_mysql=True)
                except installation.InstallationRejected:
                    report['migration'] = {'status':'invalid','reason':'CANONICAL_INSTALLATION_REQUIRED'}
                    return report
            guard = conn.execute(select(Guard.version).where(Guard.key=='calculations')).scalar_one_or_none()
            values = dict(conn.execute(select(Setting.key,Setting.value).where(Setting.key.in_(['branding','metrics','qualification','business_dictionary','import_policy']))).all())
            roots = conn.execute(select(Org.id).where(Org.kind=='school',Org.parent_id.is_(None),Org.active.is_(True))).scalars().all()
            roles = conn.execute(select(Role.kind,Role.permissions).where(Role.active.is_(True))).all()
            kinds = {kind for kind,perms in roles if isinstance(perms,list) and all(isinstance(p,str) for p in perms)}
            checks = {'calculations_guard': type(guard) is int and guard >= 1,
                      'settings': all(_setting_ok(key,values.get(key)) for key in ('branding','metrics','qualification','business_dictionary','import_policy')),
                      'school_root':len(roots)==1,
                      'core_roles':{'teacher','dept','college','school'} <= kinds}
            report['initialization'] = {'status':'ok' if all(checks.values()) else 'incomplete', 'checks':checks}
    except SQLAlchemyError:
        # Do not echo driver exceptions, SQL parameters or connection strings.
        if report['database']['status'] == 'unchecked':
            report['database'] = {'status':'unavailable'}
        elif report['migration']['status'] == 'unchecked':
            report['migration'] = {'status':'unavailable'}
        else:
            report['initialization'] = {'status':'unavailable'}
        return report
    if all(report[key]['status']=='ok' for key in ('database','migration','initialization')):
        report['status'] = 'ok'
        report['accepting_requests'] = not maintenance['blocked']
    return report
