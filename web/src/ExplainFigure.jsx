import { useState } from "react";
import { createPortal } from "react-dom";

const LABEL = {
  source_confirmed: "Source-confirmed",
  inferred: "Inferred settlement",
  snapshot_cost: "Snapshot cost",
  cost_unavailable: "Cost unavailable",
};

function sourceLine(source) {
  const bits = [source.type];
  if (source.records) bits.push(source.records + " records");
  if (source.coverage_through) bits.push("through " + source.coverage_through);
  if (source.effective_date) bits.push("effective " + source.effective_date);
  if (source.uploaded_at) bits.push("uploaded " + String(source.uploaded_at).slice(0, 10));
  return bits.join(" · ");
}

export default function ExplainFigure({ explanation, label }) {
  const [open, setOpen] = useState(false);
  if (!explanation) return null;
  const window = explanation.window || {};
  const span = window.from && window.to ? window.from + " to " + window.to : (window.to || window.report_date || "");
  return (
    <>
      <button type="button" className="ghost" onClick={() => setOpen(true)}>{label || "Explain"}</button>
      {open ? createPortal(
        <div className="modal-backdrop" onClick={() => setOpen(false)}>
          <div className="modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
            <div className="card-head">
              <h3>{explanation.label || "Number"}</h3>
              <button type="button" className="ghost" onClick={() => setOpen(false)}>Close</button>
            </div>
            <p>{explanation.formula}</p>
            {span ? <p className="muted">Window {span}{window.report_date ? " · report " + window.report_date : ""}</p> : null}
            {explanation.status === "unavailable" ? <p className="warn">{explanation.reason || "Unavailable"}</p> : null}
            {explanation.label_kind ? <p className="muted">{LABEL[explanation.label_kind] || explanation.label_kind}</p> : null}
            {explanation.basis ? <p className="muted">{explanation.basis === "live" ? "Latest data" : "Saved with this report"}</p> : null}
            {explanation.mixed_coverage && explanation.coverage_note ? <p className="warn">{explanation.coverage_note}</p> : null}
            {(explanation.sources || []).length ? (
              <ul>
                {explanation.sources.map((source) => <li key={source.type}>{sourceLine(source)}</li>)}
              </ul>
            ) : null}
            {explanation.inputs?.length ? <p className="muted">Uses {explanation.inputs.join(" and ")}.</p> : null}
            {explanation.reconciliation?.status ? (
              <p className="muted">Reconciliation {explanation.reconciliation.status}{explanation.reconciliation.message ? " — " + explanation.reconciliation.message : ""}</p>
            ) : null}
          </div>
        </div>,
        document.body,
      ) : null}
    </>
  );
}
