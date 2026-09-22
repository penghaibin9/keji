"""Best-effort access logging. This must never handle critical business auditing.

Critical business audit/receipt writes remain in the original business session
and must propagate exceptions. This separate access sink never changes a response
which a business transaction has already produced.
"""
from __future__ import annotations
from .models import Audit


def record_access_best_effort(sessions, logger, event):
    try:
        with sessions.begin() as db:
            db.add(Audit(**event))
        return True
    except Exception as exc:
        try:
            # Exception class is safe; repr/traceback can contain SQL and secrets.
            logger.error('access_log_write_failed request_id=%s error_class=%s',
                         event['request_id'], type(exc).__name__)
        except Exception:
            # A broken fallback handler must not turn a committed 2xx into 5xx.
            pass
        return False
