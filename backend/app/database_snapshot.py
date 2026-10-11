"""Read-only, deterministic table digests for stopped-writer backup reconciliation.

Contains counts and SHA256 digests, never raw rows or database credentials. This
is a data-integrity comparison, not a signature against a privileged attacker.
"""
from __future__ import annotations
import base64
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
import re
import sqlalchemy as sa
from . import installation, org_assessment, integrations, reference_data, inbound_sync
from . import social_models
from .models import Base

ALGORITHM = 'sha256-primary-key-typed-json-v1'


def typed(value):
    if value is None or type(value) in (str, bool, int):
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError('NONFINITE_SNAPSHOT_VALUE')
        return {'$decimal': str(value)}
    if isinstance(value, datetime):
        return {'$datetime': value.isoformat(timespec='microseconds')}
    if isinstance(value, date):
        return {'$date': value.isoformat()}
    if isinstance(value, bytes):
        return {'$bytes': base64.b64encode(value).decode('ascii')}
    if isinstance(value, list):
        return {'$json_list': [typed(x) for x in value]}
    if isinstance(value, dict):
        if any(not isinstance(k, str) for k in value):
            raise ValueError('INVALID_JSON_SNAPSHOT_KEY')
        return {'$json_object': {k:typed(v) for k,v in value.items()}}
    if type(value) is float:
        # JSON fields may contain finite decimal-free floats, but never NaN/Inf.
        import math
        if not math.isfinite(value):raise ValueError('NONFINITE_SNAPSHOT_VALUE')
        return {'$float': value.hex()}
    raise ValueError('UNSUPPORTED_SNAPSHOT_TYPE')


def payload_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def take_snapshot(engine, *, require_mysql=True):
    options={'isolation_level':'REPEATABLE READ'} if engine.dialect.name=='mysql' else {}
    tables={name:table for name,table in Base.metadata.tables.items()}
    version=sa.Table('alembic_version',sa.MetaData(),sa.Column('version_num',sa.String(32),primary_key=True))
    tables[version.name]=version
    with engine.connect().execution_options(**options) as connection:
        with connection.begin():
            proof=installation.require_canonical(connection,require_mysql=require_mysql)
            records={}
            for name,table in sorted(tables.items()):
                primary=list(table.primary_key.columns)
                if not primary:raise ValueError('SNAPSHOT_PRIMARY_KEY_REQUIRED')
                columns=[col.name for col in table.columns]
                digest=hashlib.sha256();digest.update(payload_bytes({'table':name,'columns':columns})+b'\n')
                count=0
                with connection.execution_options(stream_results=True).execute(sa.select(table).order_by(*primary)) as result:
                    for row in result:
                        digest.update(payload_bytes([typed(v) for v in row])+b'\n');count+=1
                records[name]={'rows':count,'sha256':digest.hexdigest(),'columns':columns}
    output={'algorithm':ALGORITHM,'baseline_revision':proof['baseline_revision'],
            'installation_id':proof['installation_id'],'contract_sha256':proof['contract_sha256'], 'tables':records}
    output['snapshot_sha256']=hashlib.sha256(payload_bytes(output)).hexdigest()
    return output


def validate_snapshot(value):
    if not isinstance(value,dict) or set(value)!={'algorithm','baseline_revision','installation_id','contract_sha256','tables','snapshot_sha256'}:
        raise ValueError('DATABASE_RECONCILIATION_INVALID')
    if value['algorithm']!=ALGORITHM or value['baseline_revision']!=installation.BASELINE_REVISION:
        raise ValueError('DATABASE_RECONCILIATION_LINEAGE_MISMATCH')
    for checksum in ('snapshot_sha256','contract_sha256'):
        if not isinstance(value[checksum],str) or not re.fullmatch('[0-9a-f]{64}',value[checksum]):
            raise ValueError('DATABASE_RECONCILIATION_INVALID')
    if not isinstance(value['tables'],dict) or set(value['tables'])!=set(Base.metadata.tables)|{'alembic_version'}:
        raise ValueError('DATABASE_RECONCILIATION_TABLES_MISMATCH')
    for name,entry in value['tables'].items():
        if not isinstance(entry,dict) or set(entry)!={'rows','sha256','columns'}:
            raise ValueError('DATABASE_RECONCILIATION_INVALID')
        if type(entry['rows']) is not int or entry['rows']<0 or not isinstance(entry['sha256'],str) or not re.fullmatch('[0-9a-f]{64}',entry['sha256']):
            raise ValueError('DATABASE_RECONCILIATION_INVALID')
        expected=[c.name for c in Base.metadata.tables[name].columns] if name!='alembic_version' else ['version_num']
        if entry['columns']!=expected:raise ValueError('DATABASE_RECONCILIATION_COLUMNS_MISMATCH')
    signed={k:v for k,v in value.items() if k!='snapshot_sha256'}
    if value['snapshot_sha256']!=hashlib.sha256(payload_bytes(signed)).hexdigest():
        raise ValueError('DATABASE_RECONCILIATION_DIGEST_MISMATCH')
    return value


def compare_snapshots(expected, actual):
    validate_snapshot(expected);validate_snapshot(actual)
    if expected!=actual:raise ValueError('RESTORED_DATABASE_ROWS_DO_NOT_MATCH_BACKUP')
    return {'status':'MATCH','tables':len(actual['tables']),'rows':sum(x['rows'] for x in actual['tables'].values()),
            'snapshot_sha256':actual['snapshot_sha256']}


def main():
    from .config import Settings
    from .core import make_engine
    cfg=Settings();engine=make_engine(cfg.database_url)
    try:
        if cfg.env!='production':raise ValueError('PRODUCTION_MYSQL_REQUIRED')
        value=take_snapshot(engine,require_mysql=True);validate_snapshot(value)
        print(json.dumps(value,ensure_ascii=False,sort_keys=True))
    except (ValueError,RuntimeError,sa.exc.SQLAlchemyError):
        raise SystemExit('BLOCKED: database snapshot could not be verified') from None
    finally:engine.dispose()

if __name__=='__main__':main()
