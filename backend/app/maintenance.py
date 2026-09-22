"""Post-restore sanitation; never overwrites an existing live school."""
from __future__ import annotations
import argparse
from pathlib import Path
from sqlalchemy import delete,select
from sqlalchemy.orm import sessionmaker
from .config import Settings
from .core import make_engine
from .models import User,AuthSession,Throttle,Connection,Task,TaskAttempt,utcnow
from .integrations import ConnectionCheck
from .inbound_sync import IntegrationSchedule
from .passwords import hash_password


def sanitize_restore(cfg,username,password_file):
    p=Path(password_file)
    if p.is_symlink() or not p.is_file():raise RuntimeError('administrator password secret missing')
    password=p.read_text().rstrip('\r\n')
    if len(password)<12:raise RuntimeError('administrator password secret too short')
    engine=make_engine(cfg.database_url)
    try:
        if cfg.env == "production":
            from .installation import require_canonical
            with engine.connect() as connection: require_canonical(connection, require_mysql=True)
        with sessionmaker(bind=engine).begin() as db:
            admin=db.scalar(select(User).where(User.username==username).with_for_update())
            if not admin or not admin.is_admin:raise RuntimeError('restored administrator not found')
            db.execute(delete(AuthSession));db.execute(delete(Throttle))
            for user in db.scalars(select(User).with_for_update()):user.auth_version+=1
            # A restored snapshot must never replay external writes automatically.
            now=utcnow()
            for connection in db.scalars(select(Connection).with_for_update()):
                connection.state='NOT_CONNECTED';connection.version+=1
            for proof in db.scalars(select(ConnectionCheck).with_for_update()):
                proof.expires_at=min(proof.expires_at,now)
            for schedule in db.scalars(select(IntegrationSchedule).with_for_update()):
                schedule.active=False;schedule.auto_commit=False;schedule.last_error='RESTORE_REAPPROVAL_REQUIRED';schedule.version+=1
            for task in db.scalars(select(Task).where(Task.kind.in_(['sync','inbound_pull']),Task.state.in_(['PENDING','RETRY','RUNNING'])).with_for_update()):
                task.state='BLOCKED';task.error='RESTORE_REVALIDATION_REQUIRED';task.lease_token=None;task.lease_until=None;task.version+=1
                db.add(TaskAttempt(task_id=task.id,attempt=task.attempts,result='BLOCKED',message='RESTORE_REVALIDATION_REQUIRED'))
            admin.password_hash=hash_password(password);admin.must_change_password=True;admin.active=True;admin.failures=0;admin.locked_until=None;admin.version+=1
    finally:engine.dispose()


def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='cmd',required=True)
    s=sub.add_parser('sanitize-restore');s.add_argument('--username',default='admin');s.add_argument('--password-file',required=True)
    a=p.parse_args();cfg=Settings()
    try:sanitize_restore(cfg,a.username,a.password_file)
    except RuntimeError as exc:print('BLOCK:',str(exc));raise SystemExit(2)
    print('RESTORE_SANITIZED')

if __name__=='__main__':main()
