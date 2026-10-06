import { useEffect, useMemo, useState } from "react";
import SectionTabs from "./SectionTabs";
import { createPortal } from "react-dom";

function prettyTime(value) {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

function runLabel(row) {
  if (!row) return "";
  const date = row.report_date || "Report";
  const time = prettyTime(row.created_at);
  const when = time ? date + ", " + time : date;
  return row.fy_label ? when + " · " + row.fy_label : when;
}

function prettyDate(value) {
  if (!value) return "Unknown date";
  const d = new Date(value + (String(value).includes("T") ? "" : "T12:00:00"));
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function packNames(packs) {
  const on = Object.keys(packs || {}).filter((k) => packs[k]);
  return on.length ? on : ["core"];
}

function SnapshotPicker({ runs, currentId, onSelect, busy }) {
  const [open, setOpen] = useState(false);
  const [date, setDate] = useState("");
  const [picked, setPicked] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");

  const current = useMemo(() => (runs || []).find((r) => r.id === currentId) || null, [runs, currentId]);
  const dates = useMemo(() => {
    const seen = new Set();
    const out = [];
    (runs || []).forEach((row) => {
      const d = row.report_date || "";
      if (d && !seen.has(d)) {
        seen.add(d);
        out.push(d);
      }
    });
    return out;
  }, [runs]);

  const filtered = useMemo(() => {
    const rows = runs || [];
    if (!date) return rows;
    return rows.filter((row) => row.report_date === date);
  }, [runs, date]);

  useEffect(() => {
    if (!open) return undefined;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    function onKey(e) {
      if (e.key === "Escape" && !saving) setOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener("keydown", onKey);
    };
  }, [open, saving]);

  function openModal() {
    setDate("");
    setPicked(currentId || "");
    setErr("");
    setOpen(true);
  }

  async function apply(id) {
    const next = id || picked;
    if (!next || next === currentId) {
      setOpen(false);
      return;
    }
    setSaving(true);
    setErr("");
    try {
      await onSelect(next);
      setOpen(false);
    } catch (e) {
      setErr(e.message || "Could not load that snapshot.");
    } finally {
      setSaving(false);
    }
  }

  if (busy || !(runs || []).length) return null;

  const dialog = open ? (
    <div className="modal-backdrop snapshot-backdrop" onClick={() => { if (!saving) setOpen(false); }}>
      <div
        className="modal snapshot-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="snapshot-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="snapshot-head">
          <div>
            <h3 id="snapshot-title">Choose snapshot</h3>
            <p className="muted">Official numbers and 360 views follow the Create run you pick.</p>
          </div>
          <button type="button" className="ghost snapshot-close" disabled={saving} onClick={() => setOpen(false)} aria-label="Close">×</button>
        </div>

        <div className="snapshot-body">
          <div className="snapshot-toolbar">
            <SectionTabs
              className="snapshot-tabs"
              label="Report dates"
              fill
              value={date || "all"}
              onChange={(id) => setDate(id === "all" ? "" : id)}
              tabs={[
                { id: "all", label: "All", count: (runs || []).length, disabled: saving },
                ...dates.map((d) => ({
                  id: d,
                  label: prettyDate(d),
                  count: (runs || []).filter((r) => r.report_date === d).length,
                  disabled: saving,
                })),
              ]}
            />
            <label className="snapshot-date">
              <span className="sr-only">Custom report date</span>
              <input
                type="date"
                value={/^\d{4}-\d{2}-\d{2}$/.test(date) ? date : ""}
                onChange={(e) => setDate(e.target.value)}
                disabled={saving}
                title="Filter by date"
              />
            </label>
          </div>

          <div className="snapshot-list" role="listbox" aria-label="Snapshots">
            {filtered.length ? filtered.map((row) => {
              const selected = picked === row.id;
              const isCurrent = row.id === currentId;
              return (
                <button
                  key={row.id}
                  type="button"
                  role="option"
                  aria-selected={selected}
                  className={"snapshot-card" + (selected ? " on" : "") + (isCurrent ? " current" : "")}
                  disabled={saving}
                  onClick={() => setPicked(row.id)}
                  onDoubleClick={() => apply(row.id)}
                >
                  <span className="snapshot-card-main">
                    <span className="snapshot-card-date">{prettyDate(row.report_date)}{prettyTime(row.created_at) ? ", " + prettyTime(row.created_at) : ""}</span>
                    {row.fy_label ? <span className="snapshot-card-fy">{row.fy_label}</span> : null}
                    <span className="snapshot-card-meta">
                      {packNames(row.packs).map((name) => (
                        <span key={name} className="snapshot-pack">{name}</span>
                      ))}
                      {row.report_count ? (
                        <span className="muted">{row.report_count} reports</span>
                      ) : null}
                    </span>
                  </span>
                  <span className="snapshot-card-side">
                    {isCurrent ? <span className="pill ok">Current</span> : null}
                    <span className={"snapshot-check" + (selected ? " on" : "")} aria-hidden="true" />
                  </span>
                </button>
              );
            }) : (
              <div className="snapshot-empty">
                <strong>No snapshots for that date</strong>
                <p className="muted">Clear the date filter or Create reports for another day.</p>
              </div>
            )}
          </div>
        </div>

        {err ? <p className="err snapshot-err">{err}</p> : null}

        <div className="modal-actions snapshot-actions">
          <button type="button" className="ghost" disabled={saving} onClick={() => setOpen(false)}>Cancel</button>
          <button type="button" disabled={saving || !picked} onClick={() => apply()}>
            {saving ? "Loading…" : picked && picked !== currentId ? "View snapshot" : "Done"}
          </button>
        </div>
      </div>
    </div>
  ) : null;

  return (
    <>
      <button type="button" className="secondary snapshot-trigger" onClick={openModal}>
        <span className="snapshot-trigger-label">Snapshot</span>
        <strong>{current ? runLabel(current) : "Choose…"}</strong>
        <span className="snapshot-trigger-caret" aria-hidden="true" />
      </button>
      {dialog && typeof document !== "undefined" ? createPortal(dialog, document.body) : null}
    </>
  );
}

export { runLabel };
export default SnapshotPicker;
