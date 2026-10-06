import { useEffect, useState } from "react";
import AgeBar, { ageParts } from "./AgeBar";
import { ageLabel, hashSet, inSelectedPeriod, money } from "./format";

function sharePct(value, total) {
  const base = Number(total) || 0;
  if (base <= 0) return "0%";
  const pct = ((Number(value) || 0) / base) * 100;
  return pct.toLocaleString(undefined, { maximumFractionDigits: 1, minimumFractionDigits: 0 }) + "%";
}

function moneyShare(value, total) {
  return money(value) + " (" + sharePct(value, total) + ")";
}

function linesForPeriod(period, overall, view, monthKey, fyKey) {
  const own = Array.isArray(period?.lines) ? period.lines : [];
  const all = Array.isArray(overall?.lines) ? overall.lines : [];
  const source = own.length ? own : all;
  return source.filter((row) => inSelectedPeriod(row.date_iso, view, monthKey, fyKey));
}

function invoiceLabel(row) {
  if (row?.kind === "opening" || !(row?.invoice || row?.invoice_id)) return "Opening balance";
  return row.invoice || "Sale";
}

export default function SettlementsPanel({ detail, showParty }) {
  const settlements = detail.settlements || {};
  const overall = settlements.overall || {
    total: Object.values(detail.collection_buckets || {}).reduce((s, v) => s + (Number(v) || 0), 0),
    buckets: detail.collection_buckets || {},
  };
  const byFy = settlements.by_fy || [];
  const months = settlements.months || [];
  const [monthKey, setMonthKey] = useState(settlements.default_month || (months[0] && months[0].key) || "");
  const [fyKey, setFyKey] = useState((byFy[0] && byFy[0].key) || "");
  const [view, setView] = useState("overall");
  const [bucketKey, setBucketKey] = useState("");

  useEffect(() => {
    setMonthKey(settlements.default_month || (months[0] && months[0].key) || "");
    setFyKey((byFy[0] && byFy[0].key) || "");
    setView("overall");
    setBucketKey("");
  }, [detail.uk, settlements.default_month]);

  const selectedMonth = months.find((m) => m.key === monthKey) || months[0] || null;
  const selectedFy = byFy.find((y) => y.key === fyKey) || byFy[0] || null;
  const bands = detail.aging_bands;

  let period = overall;
  let periodLabel = "Overall — by age of settled invoice";
  if (view === "fy" && selectedFy) {
    period = selectedFy;
    periodLabel = selectedFy.label + " — settled by age";
  } else if (view === "month" && selectedMonth) {
    period = selectedMonth;
    periodLabel = selectedMonth.label + " — settled by age";
  }

  return (
    <div className="card">
      <h3>Settlements</h3>
      <p className="muted">Receipts applied to invoices — aged by how old the settled invoice was on the payment date.</p>

      <div className="buy-tiles" style={{ marginTop: 12 }}>
        <div className="card buy-tile">
          <span className="muted">Overall settled</span>
          <strong>{moneyShare(overall.total || 0, overall.total || 0)}</strong>
        </div>
        {overall.credit ? (
          <div className="card buy-tile">
            <span className="muted">Advance / excess</span>
            <strong>{money(overall.credit)}</strong>
          </div>
        ) : null}
        {selectedMonth ? (
          <div className="card buy-tile">
            <span className="muted">{selectedMonth.label}</span>
            <strong>{moneyShare(selectedMonth.total || 0, overall.total || 0)}</strong>
          </div>
        ) : null}
        {selectedFy ? (
          <div className="card buy-tile">
            <span className="muted">{selectedFy.label}</span>
            <strong>{moneyShare(selectedFy.total || 0, overall.total || 0)}</strong>
          </div>
        ) : null}
      </div>

      <div className="chips" style={{ marginTop: 16 }}>
        <button type="button" className={view === "overall" ? "" : "secondary"} onClick={() => { setView("overall"); setBucketKey(""); }}>Overall</button>
        <button type="button" className={view === "fy" ? "" : "secondary"} onClick={() => { setView("fy"); setBucketKey(""); }} disabled={!byFy.length}>Fiscal year</button>
        <button type="button" className={view === "month" ? "" : "secondary"} onClick={() => { setView("month"); setBucketKey(""); }}>Month</button>
      </div>

      {view === "fy" && byFy.length ? (
        <div className="card-head" style={{ alignItems: "center", gap: 12, flexWrap: "wrap", marginTop: 12 }}>
          <h4 className="quiet" style={{ margin: 0 }}>Per fiscal year</h4>
          <select
            value={selectedFy ? selectedFy.key : ""}
            onChange={(e) => { setFyKey(e.target.value); setBucketKey(""); }}
            aria-label="Fiscal year"
          >
            {byFy.map((y) => (
              <option key={y.key} value={y.key}>{y.label} · {moneyShare(y.total, overall.total || 0)}</option>
            ))}
          </select>
        </div>
      ) : null}

      {view === "month" ? (
        <div className="card-head" style={{ alignItems: "center", gap: 12, flexWrap: "wrap", marginTop: 12 }}>
          <h4 className="quiet" style={{ margin: 0 }}>By month</h4>
          {months.length ? (
            <select
              value={selectedMonth ? selectedMonth.key : ""}
              onChange={(e) => { setMonthKey(e.target.value); setBucketKey(""); }}
              aria-label="Settlement month"
            >
              {months.map((m) => (
                <option key={m.key} value={m.key}>{m.label} · {moneyShare(m.total, overall.total || 0)}</option>
              ))}
            </select>
          ) : (
            <span className="muted">No settlements yet</span>
          )}
        </div>
      ) : null}

      <div style={{ marginTop: 16 }}>
        {view === "month" && !selectedMonth ? (
          <p className="muted">No receipts in this period.</p>
        ) : (
          <AgeBar
            parts={ageParts(period.buckets, bands)}
            title={periodLabel}
            selected={bucketKey}
            onSelect={setBucketKey}
          />
        )}
      </div>
      {view === "month" && !selectedMonth ? null : (
        <SettlementLines
          lines={linesForPeriod(period, overall, view, monthKey, fyKey)}
          bucketKey={bucketKey}
          bands={bands}
          showParty={showParty}
        />
      )}
    </div>
  );
}

function SettlementLines({ lines, bucketKey, bands, showParty }) {
  const shown = (lines || []).filter((row) => !bucketKey || row.bucket === bucketKey);
  const band = ageParts({}, bands).find((part) => part.key === bucketKey);
  const label = band?.label || (bucketKey ? ageLabel(bucketKey, bands) + " days" : "");
  return (
    <div className="table-wrap" style={{ marginTop: 8 }}>
      <table className="dense list-table compact">
        <thead>
          <tr>
            <th>Date</th>
            {showParty ? <th>Customer</th> : null}
            <th>Invoice</th>
            <th className="num">Age</th>
            <th className="num">Amount</th>
          </tr>
        </thead>
        <tbody>
          {shown.length ? shown.map((row, index) => (
            <tr key={(row.date_iso || "") + "-" + (row.invoice_id || row.invoice || index)}>
              <td>{row.date_label || "—"}</td>
              {showParty ? (
                <td>
                  {row.customer_uk ? (
                    <button type="button" className="linkish" onClick={() => hashSet("customer/" + encodeURIComponent(row.customer_uk))}>
                      {row.party || "Customer"}
                    </button>
                  ) : (row.party || "—")}
                </td>
              ) : null}
              <td>
                {row.invoice_id && row.kind !== "opening" ? (
                  <button type="button" className="linkish" onClick={() => hashSet("invoice/" + encodeURIComponent(row.invoice_id))}>
                    {invoiceLabel(row)}
                  </button>
                ) : invoiceLabel(row)}
              </td>
              <td className="num">{row.age_days == null ? "—" : row.age_days + " days"}</td>
              <td className="num">{money(row.amount || 0)}</td>
            </tr>
          )) : (
            <tr>
              <td colSpan={showParty ? 5 : 4} className="muted">
                {bucketKey ? "No invoices in " + label + "." : "No settlements in this period."}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
