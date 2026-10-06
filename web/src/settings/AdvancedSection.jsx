import { useState } from "react";
import { api } from "../api";
import { REQUIRED_FIELDS } from "../theme";

export default function AdvancedSection({ onFactoryReset }) {
  const [type, setType] = useState("sales");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(null);
  const [picked, setPicked] = useState({
    arr: true,
    sales: true,
    items: true,
    payments: true,
    receipt: true,
    credit_note: true,
    stock: true,
  });

  const CLEANUP_OPTS = [
    { id: "arr", label: "Outstanding" },
    { id: "sales", label: "Sales" },
    { id: "items", label: "Item-wise sales" },
    { id: "payments", label: "Payments" },
    { id: "receipt", label: "Receipts" },
    { id: "credit_note", label: "Credit notes" },
    { id: "stock", label: "Stock quantities" },
  ];

  async function rebuild() {
    setErr("");
    setMsg("");
    try {
      await api.rebuildUk(type);
      setMsg("Unique keys rebuilt for " + type + ".");
    } catch (e) {
      setErr(e.message);
    }
  }

  function openCleanup() {
    const selected = CLEANUP_OPTS.filter((o) => picked[o.id]);
    if (!selected.length) {
      setErr("Select at least one data type.");
      return;
    }
    setErr("");
    setConfirm({ kind: "cleanup", selected });
  }

  function openFactory() {
    setErr("");
    setConfirm({ kind: "factory" });
  }

  async function runCleanup(selected) {
    setBusy(true);
    setMsg("");
    setErr("");
    try {
      const out = await api.cleanupData({ types: selected.map((o) => o.id) });
      const bits = Object.entries(out.removed || {}).map(([name, n]) => `${n} ${name.toLowerCase()}`);
      setMsg(`Removed ${out.total || 0} rows` + (bits.length ? ": " + bits.join(", ") : ".") + (out.balances_cleared ? `. Cleared ${out.balances_cleared} party/customer balances.` : "."));
      setConfirm(null);
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function runFactory() {
    setBusy(true);
    setMsg("");
    setErr("");
    try {
      const out = await api.factoryReset();
      setMsg(`Factory reset complete. Removed ${out.total || 0} imported rows and ${out.runs_deleted || 0} report runs.`);
      setConfirm(null);
      if (onFactoryReset) onFactoryReset();
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="card">
        <h2>Clear imported data</h2>
        <p className="muted">Removes selected outstanding, sales, item-wise sales, payments, and receipts. Stock items stay; quantities go to zero. Parties and customers stay. Reports already created stay, including 360 snapshots.</p>
        <div className="chips">
          {CLEANUP_OPTS.map((o) => (
            <button
              type="button"
              key={o.id}
              className={picked[o.id] ? "" : "secondary"}
              onClick={() => setPicked((prev) => ({ ...prev, [o.id]: !prev[o.id] }))}
            >{o.label}</button>
          ))}
          <button type="button" className="ghost" onClick={() => setPicked({ arr: true, sales: true, items: true, payments: true, receipt: true, stock: true })}>Select all</button>
        </div>
        <button className="danger" disabled={busy} onClick={openCleanup}>{busy && confirm?.kind === "cleanup" ? "Removing…" : "Remove this data"}</button>
      </div>
      <div className="card">
        <h2>Factory data reset</h2>
        <p className="muted">Clears imported operational data and every report run with its snapshots. Stock item names stay; quantities reset to zero. Master tags, activities, discontinued marks, users, and settings stay.</p>
        <button className="danger" disabled={busy} onClick={openFactory}>{busy && confirm?.kind === "factory" ? "Resetting…" : "Factory data reset"}</button>
      </div>
      <div className="card">
        <h2>Rebuild duplicate keys</h2>
        <p className="muted">Use after changing how duplicates are detected in Import. This rewrites stored keys for that type only.</p>
        <label>Type</label>
        <select value={type} onChange={(e) => setType(e.target.value)}>
          {Object.keys(REQUIRED_FIELDS).map((t) => <option key={t}>{t}</option>)}
        </select>
        <button onClick={rebuild}>Rebuild</button>
      </div>
      {msg ? <p className="ok">{msg}</p> : null}
      {err && !confirm ? <p className="err">{err}</p> : null}

      {confirm?.kind === "cleanup" ? (
        <div className="modal-backdrop" onClick={() => { if (!busy) setConfirm(null); }}>
          <div className="modal confirm-modal" onClick={(e) => e.stopPropagation()}>
            <h3>Remove imported data?</h3>
            <p className="muted">These types will be cleared so you can import again. This cannot be undone.</p>
            <ul className="confirm-list">
              {confirm.selected.map((o) => <li key={o.id}>{o.label}{o.id === "stock" ? " (items stay, qty → 0)" : ""}</li>)}
            </ul>
            <p className="muted">Parties, customers, stock item names, and generated reports stay.</p>
            {err ? <p className="err">{err}</p> : null}
            <div className="modal-actions">
              <button type="button" className="ghost" disabled={busy} onClick={() => setConfirm(null)}>Cancel</button>
              <button type="button" className="danger" disabled={busy} onClick={() => runCleanup(confirm.selected)}>
                {busy ? "Removing…" : "Remove data"}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {confirm?.kind === "factory" ? (
        <div className="modal-backdrop" onClick={() => { if (!busy) setConfirm(null); }}>
          <div className="modal confirm-modal" onClick={(e) => e.stopPropagation()}>
            <h3>Factory data reset?</h3>
            <p className="muted">This returns the app to a clean slate for import and Create.</p>
            <ul className="confirm-list">
              <li>All imported outstanding, sales, item-wise sales, payments, and receipts</li>
              <li>Stock quantities reset to zero (item names stay)</li>
              <li>Every generated report run and its snapshots</li>
            </ul>
            <p className="muted">Kept: stock items, parties, customers, party types, discontinued marks, logged activities, users, and settings.</p>
            {err ? <p className="err">{err}</p> : null}
            <div className="modal-actions">
              <button type="button" className="ghost" disabled={busy} onClick={() => setConfirm(null)}>Cancel</button>
              <button type="button" className="danger" disabled={busy} onClick={runFactory}>
                {busy ? "Resetting…" : "Reset everything"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
