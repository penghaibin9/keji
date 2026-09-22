"""Container health probes."""
from __future__ import annotations
import sys
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from .config import Settings
from .core import make_engine
from .models import RuntimeState,utcnow


def worker_health(cfg=None):
    cfg=cfg or Settings();engine=make_engine(cfg.database_url)
    try:
        with sessionmaker(bind=engine)() as db:
            obj=db.get(RuntimeState,'worker')
            return bool(obj and obj.value.get('healthy') is True and (utcnow()-obj.updated_at).total_seconds()<90)
    finally:engine.dispose()


def main():
    mode=sys.argv[1] if len(sys.argv)>1 else ''
    if mode=='worker':raise SystemExit(0 if worker_health() else 1)
    raise SystemExit(2)

if __name__=='__main__':main()
