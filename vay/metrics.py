"""Versioned metric catalog.

Bump an integer when that metric's formula, date basis, or exclusion rules change.
Dashboard, reports, and Create manifests pin these versions on each run.
"""

from __future__ import annotations

from vay.domain import METRIC_IDS

# Starting version for every Phase 0 metric. Do not reset a version; only increment.
METRIC_VERSIONS = {metric_id: 1 for metric_id in METRIC_IDS}


def metric_versions():
    """Copy of {metric_id: version} for run manifests."""
    return dict(METRIC_VERSIONS)
