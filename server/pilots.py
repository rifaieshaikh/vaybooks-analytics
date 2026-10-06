"""Pilot workbook intake. Real exports are required before a gate can pass.

Numeric baselines are not invented from Vay. A pilot stays blocked until its
sample folder contains a data row and the manifest no longer says BLOCKER.
"""

from __future__ import annotations

from pathlib import Path

PILOTS = ("edge_point", "plymax", "eff_yes_traders")


def samples_root():
    return Path(__file__).resolve().parents[1] / "docs" / "phase0" / "samples"


def _manifest_blocked(text):
    return "BLOCKER" in (text or "")


def _has_data_row(folder: Path):
    if not folder.is_dir():
        return False
    for path in folder.glob("*.csv"):
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if len(lines) > 1:
            return True
    return False


def pilot_status(samples_root):
    root = Path(samples_root)
    out = []
    for pilot in PILOTS:
        folder = root / pilot
        manifest = folder / "MANIFEST.md"
        text = manifest.read_text(encoding="utf-8") if manifest.is_file() else ""
        blocked = _manifest_blocked(text) or not _has_data_row(folder)
        out.append({
            "pilot": pilot,
            "blocked": blocked,
            "reason": "workbook not yet received" if blocked else "",
        })
    return out


def baselines_ready(samples_root):
    """True only when every external pilot has a received workbook."""
    rows = pilot_status(samples_root)
    return bool(rows) and all(not row["blocked"] for row in rows)


def presets_for_received_pilots(samples_root):
    """Header presets shipped beside a received workbook. Blocked pilots add none."""
    root = Path(samples_root)
    presets = []
    for row in pilot_status(root):
        if row["blocked"]:
            continue
        path = root / row["pilot"] / "preset.json"
        if not path.is_file():
            continue
        import json
        preset = json.loads(path.read_text(encoding="utf-8"))
        if preset.get("id") and preset.get("column_map"):
            presets.append(preset)
    return presets
