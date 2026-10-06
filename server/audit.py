"""Append-only audit events. There is no delete API."""

from __future__ import annotations


def record(store, action, actor, detail=""):
    if store is None or not hasattr(store, "append_audit"):
        return None
    return store.append_audit({
        "action": str(action or ""),
        "actor": str(actor or ""),
        "detail": str(detail or ""),
    })


def list_events(store, limit=50, offset=0):
    if not hasattr(store, "list_audit"):
        return [], 0
    return store.list_audit(limit=limit, offset=offset)
