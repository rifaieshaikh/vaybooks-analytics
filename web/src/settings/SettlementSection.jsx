import { useEffect, useState } from "react";
import { api } from "../api";

export default function SettlementSection() {
  const DEFAULT_BANDS = [
    { key: "d0_15", label: "0–15", max_days: 15 },
    { key: "d15_30", label: "15–30", max_days: 30 },
    { key: "d30_45", label: "30–45", max_days: 45 },
    { key: "d45_60", label: "45–60", max_days: 60 },
    { key: "d60_90", label: "60–90", max_days: 90 },
    { key: "d90", label: "90+", max_days: null },
  ];
  const [mode, setMode] = useState("oldest");
  const [bands, setBands] = useState(DEFAULT_BANDS);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    api.settlement()
      .then((d) => {
        setMode(d.mode || "oldest");
        if (Array.isArray(d.aging_bands) && d.aging_bands.length) {
          setBands(d.aging_bands.map((b) => ({
            key: b.key,
            label: b.label,
            max_days: b.max_days == null ? null : Number(b.max_days),
          })));
        }
      })
      .catch((e) => setErr(e.message))
      .finally(() => setLoaded(true));
  }, []);

  async function persist(nextMode, nextBands) {
    setErr("");
    setMsg("");
    setBusy(true);
    try {
      const payload = {
        mode: nextMode,
        aging_bands: nextBands.map((b, i) => ({
          key: b.key || ("d" + i),
          label: b.label || b.key || ("Band " + (i + 1)),
          max_days: i === nextBands.length - 1 ? null : Number(b.max_days),
        })),
        setup_complete: true,
      };
      const out = await api.setSettlement(payload);
      setMode(out.mode || nextMode);
      if (Array.isArray(out.aging_bands)) setBands(out.aging_bands);
      setMsg("Saved.");
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  function selectMode(next) {
    if (next === mode || busy) return;
    persist(next, bands);
  }

  function updateBand(i, patch) {
    setBands((prev) => prev.map((b, idx) => (idx === i ? { ...b, ...patch } : b)));
  }

  function addBand() {
    setBands((prev) => {
      const copy = prev.map((b) => ({ ...b }));
      const last = copy[copy.length - 1];
      const prevMax = copy.length > 1 ? Number(copy[copy.length - 2].max_days) || 0 : 0;
      const mid = prevMax + 15;
      if (last) {
        last.max_days = mid;
        last.label = last.label && last.label.includes("+") ? String(prevMax) + "–" + mid : last.label;
        if (!last.key || last.key === "d90") last.key = "d" + prevMax + "_" + mid;
      }
      copy.push({ key: "d" + mid + "_plus", label: mid + "+", max_days: null });
      return copy;
    });
  }

  function removeBand(i) {
    setBands((prev) => {
      if (prev.length <= 1) return prev;
      const next = prev.filter((_, idx) => idx !== i);
      if (next.length) next[next.length - 1] = { ...next[next.length - 1], max_days: null };
      return next;
    });
  }

  const options = [
    {
      id: "oldest",
      label: "Oldest to latest",
      help: "Clears opening balance first, then invoices from oldest to newest. Excess becomes advance.",
      steps: ["Opening balance", "Oldest → newest invoices", "Advance if anything left"],
    },
    {
      id: "specific",
      label: "Specific",
      help: "Applies to the matching Invoice No first. Any remainder (or no match) uses Oldest to latest.",
      steps: ["Matching invoice", "Opening then oldest → newest on remainder"],
    },
  ];

  return (
    <div className="card">
      <h2>Collection settlement</h2>
      <p className="muted">
        How receipts clear balances for settlement aging. Outstanding due is always attributed newest→oldest
        on invoices still open after settlement.
      </p>
      {!loaded ? <p className="muted">Loading…</p> : null}
      <div className="settlement-options" role="radiogroup" aria-label="Settlement mode">
        {options.map((opt) => {
          const on = mode === opt.id;
          return (
            <button
              type="button"
              key={opt.id}
              className={"settlement-option" + (on ? " on" : "")}
              role="radio"
              aria-checked={on}
              disabled={busy || !loaded}
              onClick={() => selectMode(opt.id)}
            >
              <span className="settlement-option-radio" aria-hidden />
              <span className="settlement-option-body">
                <strong>{opt.label}</strong>
                <span className="muted">{opt.help}</span>
                <span className="settlement-steps">
                  {opt.steps.map((step, i) => (
                    <span key={step} className="settlement-step">
                      <span className="settlement-step-n">{i + 1}</span>
                      {step}
                    </span>
                  ))}
                </span>
              </span>
            </button>
          );
        })}
      </div>

      <h3 className="settlement-bands-title">Aging bands</h3>
      <p className="muted">
        Shared day cutoffs for due, settlement, and sales aging. The last band is open-ended (e.g. 90+).
      </p>
      <div className="aging-bands-editor">
        {bands.map((b, i) => {
          const isLast = i === bands.length - 1;
          return (
            <div key={b.key + "-" + i} className="aging-band-row">
              <label>
                Label
                <input
                  value={b.label || ""}
                  disabled={busy || !loaded}
                  onChange={(e) => updateBand(i, { label: e.target.value })}
                />
              </label>
              <label>
                Max days
                <input
                  type="number"
                  min="0"
                  value={isLast ? "" : (b.max_days ?? "")}
                  placeholder={isLast ? "∞" : ""}
                  disabled={busy || !loaded || isLast}
                  onChange={(e) => updateBand(i, { max_days: e.target.value === "" ? null : Number(e.target.value) })}
                />
              </label>
              <button
                type="button"
                className="ghost"
                disabled={busy || !loaded || bands.length <= 1}
                onClick={() => removeBand(i)}
              >
                Remove
              </button>
            </div>
          );
        })}
        <div className="row gap">
          <button type="button" className="ghost" disabled={busy || !loaded} onClick={addBand}>
            Add band
          </button>
          <button
            type="button"
            className="ghost"
            disabled={busy || !loaded}
            onClick={() => setBands(DEFAULT_BANDS.map((b) => ({ ...b })))}
          >
            Reset to default
          </button>
          <button type="button" disabled={busy || !loaded} onClick={() => persist(mode, bands)}>
            Save bands
          </button>
        </div>
      </div>
      {msg ? <p className="ok">{msg}</p> : null}
      {err ? <p className="err">{err}</p> : null}
    </div>
  );
}
