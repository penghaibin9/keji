"""Retention for the raw rows of old inbound batches.

inbound_rows grows by about 250k rows per weekly full sync, almost all of it the raw and mapped JSON of rows
that were confirmed long ago. Compacting keeps the row (row_no, business_key, errors) so batch totals, the
duplicate-key check and the full-pull reconcile keep working; only the bulky raw/mapped payloads are emptied.

Run from the backend directory:
    python -m app.inbound_retention --older-than-days 90 --keep-latest 2            # dry run, changes nothing
    python -m app.inbound_retention --older-than-days 90 --keep-latest 2 --apply    # compacts
After a large compaction MySQL only gives the disk space back after `OPTIMIZE TABLE inbound_rows` (a maintenance window job).
"""
from __future__ import annotations
import argparse
from datetime import timedelta
from sqlalchemy import select, func, update
from .core import utcnow
from .reference_data import InboundBatch, InboundRow

# Only batches whose outcome is settled. PREVIEW batches still wait for a human decision.
SETTLED = ('COMMITTED', 'VOID')
MARK = {'_compacted': True}


def candidates(db, older_than_days, keep_latest=2, now=None):
    """Batch ids whose rows may be compacted: settled, old, and not one of the newest `keep_latest` per feed."""
    cutoff = (now or utcnow()) - timedelta(days=older_than_days)
    rows = db.execute(select(InboundBatch.id, InboundBatch.connection_id, InboundBatch.data_type, InboundBatch.created_at, InboundBatch.state)
                      .where(InboundBatch.state.in_(SETTLED)).order_by(InboundBatch.created_at.desc(), InboundBatch.id)).all()
    seen, picked = {}, []
    for ident, connection_id, data_type, created_at, _ in rows:
        key = (connection_id, data_type)
        seen[key] = seen.get(key, 0) + 1
        if seen[key] > keep_latest and created_at < cutoff:
            picked.append(ident)
    return picked


def compact(db, older_than_days, keep_latest=2, apply=False, now=None):
    ids = candidates(db, older_than_days, keep_latest, now)
    todo = 0
    for i in range(0, len(ids), 50):
        part = ids[i:i + 50]
        pending = select(func.count()).select_from(InboundRow).where(InboundRow.batch_id.in_(part), InboundRow.raw['_compacted'].as_string().is_(None))
        todo += db.scalar(pending) or 0
        if apply:
            db.execute(update(InboundRow).where(InboundRow.batch_id.in_(part), InboundRow.raw['_compacted'].as_string().is_(None))
                       .values(raw=MARK, mapped={}).execution_options(synchronize_session=False))
    return {'batches': len(ids), 'rows': todo, 'applied': bool(apply)}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--older-than-days', type=int, required=True)
    p.add_argument('--keep-latest', type=int, default=2)
    p.add_argument('--apply', action='store_true')
    a = p.parse_args(argv)
    if a.older_than_days < 30 or a.keep_latest < 1:
        raise SystemExit('BLOCK: --older-than-days must be at least 30 and --keep-latest at least 1')
    from sqlalchemy.orm import sessionmaker
    from .config import Settings
    from .core import make_engine
    engine = make_engine(Settings().database_url)
    try:
        with sessionmaker(bind=engine, expire_on_commit=False).begin() as db:
            result = compact(db, a.older_than_days, a.keep_latest, a.apply)
    finally:
        engine.dispose()
    print(('已压缩' if a.apply else '预演（未改动数据）') + f"：{result['batches']} 个批次，{result['rows']} 行原始内容")


if __name__ == '__main__':
    main()
