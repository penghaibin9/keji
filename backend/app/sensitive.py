"""Role-based masking of sensitive identifiers at the response/export boundary (12.6).

Stored data, audit before/after, digests and frozen archives keep full values; only
what leaves the server for a viewer is masked.  A viewer sees a full value when it is
their own record, or when they hold the review/manage permission for it AND the owner
is inside their live organisation scope.  Everyone else receives a partial value.
"""
from __future__ import annotations
from sqlalchemy import select
from .models import User

REVIEW_STAFF = frozenset({'users.manage','qualification.review','assessment.review'})
# key -> permissions any one of which unlocks the full value (owner always sees full)
SENSITIVE_FIELDS = {
    'certificate_no': frozenset({'qualification.review'}),
    'staff_no': REVIEW_STAFF, 'teacher_staff_no': REVIEW_STAFF, 'staff_no_snapshot': REVIEW_STAFF,
    'phone': frozenset({'users.manage'}), 'mobile': frozenset({'users.manage'}), 'telephone': frozenset({'users.manage'}),
    'id_card': frozenset({'users.manage'}), 'id_no': frozenset({'users.manage'}), 'id_number': frozenset({'users.manage'}),
}
MASK_CHAR = '*'


def mask_text(value, head=None, tail=None):
    """Keep a few leading/trailing characters, e.g. J001 -> J**1, 430102199001011234 -> 4301**********1234."""
    if value is None or value == '':return value
    s = str(value); n = len(s)
    if n <= 2:return s[0] + MASK_CHAR * (n - 1)
    keep = max(1, n // 4)
    head = keep if head is None else max(0, int(head)); tail = keep if tail is None else max(0, int(tail))
    if head + tail >= n:head, tail = (1, 1) if n > 2 else (1, 0)
    return s[:head] + MASK_CHAR * (n - head - tail) + (s[n - tail:] if tail else '')


def _owner(d):
    for key in ('teacher_id', 'user_id'):
        if key in d:return d[key]
    if 'username' in d or 'staff_no' in d:return d.get('id')
    return None


def _walk(value, visit):
    if isinstance(value, dict):
        if any(k in SENSITIVE_FIELDS for k in value):visit(value)
        for item in value.values():_walk(item, visit)
    elif isinstance(value, list):
        for item in value:_walk(item, visit)


class MaskPolicy:
    """Decide per owner; caches the owner -> org lookup for one response."""
    def __init__(self, db, actor):
        self.db, self.actor, self._orgs = db, actor, {}
        self.masked = 0

    def _in_scope(self, owner):
        if owner is None:return True  # rows already limited by the query scope (e.g. admin-only staging)
        if owner not in self._orgs:
            self._orgs[owner] = self.db.scalar(select(User.org_id).where(User.id == owner,True if self.actor.role.kind=='school' else User.authorization_pending.is_(False)))
        return self._orgs[owner] in set(self.actor.org_ids) and self.actor.role.kind != 'teacher'

    def full(self, key, owner):
        if owner is not None and owner == self.actor.id:return True
        return bool(SENSITIVE_FIELDS[key] & self.actor.permissions) and self._in_scope(owner)

    def value(self, key, value, owner):
        if value in (None, '') or self.full(key, owner):return value
        self.masked += 1
        return mask_text(value)

    def apply(self, data):
        def visit(d):
            owner = _owner(d)
            for key in [k for k in d if k in SENSITIVE_FIELDS]:
                if isinstance(d[key], (str, int)) and not isinstance(d[key], bool):d[key] = self.value(key, d[key], owner)
        _walk(data, visit)
        return data


def mask_response(db, actor, data):
    """In-place on an already serialised (JSON-ready) response and returns it."""
    if actor is None or not isinstance(data, (dict, list)):return data
    return MaskPolicy(db, actor).apply(data)
