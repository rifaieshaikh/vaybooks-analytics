"""One weekly report while this process is open. Missed weeks are not backfilled."""

from __future__ import annotations

from vay.dates import today_ist
from vay.phase3 import due_weekly_date

_checked_on = ""


def ensure_weekly_run(store, start=True):
    """Create at most one automatic report for the current week."""
    from server.jobs import enqueue_run
    from server.org_policy import get_org_policy, save_org_policy
    from server.settings import sync_jobs

    policy = get_org_policy(store)
    if not policy.get("weekly_run"):
        return None
    today = today_ist(policy.get("timezone")).strftime("%Y-%m-%d")
    due = due_weekly_date(today, policy.get("last_weekly_report_date") or "", True)
    if not due:
        return None
    run_id, err = enqueue_run(store, {"core": True, "fiscal": False, "items": True, "profit": False}, due)
    if err or not run_id:
        return None
    store.update_run(run_id, {"weekly": True})
    save_org_policy(store, {"last_weekly_report_date": due, "weekly_run": True})
    if not start:
        return run_id
    if sync_jobs():
        from server.jobs import run_job
        run_job(store, run_id)
    else:
        from server.route_helpers import start_job
        start_job(run_id)
    return run_id


def ensure_weekly_run_once(store):
    """Skip repeat checks on the same calendar day inside this process."""
    global _checked_on
    from server.org_policy import get_org_policy
    policy = get_org_policy(store)
    today = today_ist(policy.get("timezone")).strftime("%Y-%m-%d")
    if _checked_on == today:
        return None
    _checked_on = today
    return ensure_weekly_run(store, start=True)
