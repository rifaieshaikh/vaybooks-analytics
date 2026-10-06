"""Current organization for a request or background job.

Desktop installs use one organization, ``default``. A missing org id on an
older document belongs to that organization. ``None`` means unscoped and is
only for startup housekeeping that must see every organization.
"""

from __future__ import annotations

from contextlib import contextmanager
import contextvars

DEFAULT_ORG = "default"

_org = contextvars.ContextVar("vay_org_id", default=DEFAULT_ORG)


def current_org_id():
    return _org.get()


def set_org(org_id):
    return _org.set(DEFAULT_ORG if org_id is None else org_id)


def reset_org(token):
    _org.reset(token)


def doc_org(doc):
    return ((doc or {}).get("org_id") or DEFAULT_ORG)


def in_org(doc):
    want = current_org_id()
    if want is None:
        return True
    return doc_org(doc) == want


def stamp_org(doc):
    """Force a new document into the current organization."""
    out = dict(doc or {})
    cur = current_org_id()
    if cur is None:
        out["org_id"] = out.get("org_id") or DEFAULT_ORG
    else:
        out["org_id"] = cur
    return out


@contextmanager
def bind_org(org_id):
    token = set_org(org_id or DEFAULT_ORG)
    try:
        yield
    finally:
        reset_org(token)


@contextmanager
def unscoped():
    token = _org.set(None)
    try:
        yield
    finally:
        _org.reset(token)
