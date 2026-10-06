import { useEffect, useState } from "react";
import AgeBar from "./AgeBar";
import { ageColor, hashSet, inSelectedPeriod, money } from "./format";

function bucketTitle(bucket) {
  if (!bucket) return "";
  if (bucket.key === "first") return bucket.label || "First order";
  return (bucket.label || bucket.key) + " days";
}

export default function SalesGapsPanel({ detail, showParty }) {
  const gaps = (detail?.ordering || {}).sales_gaps || detail?.sales_gaps;
  const years = gaps?.by_fy || [];
  const months = gaps?.months || [];
  const yearSig = years.map((row) => row.key).join("|");
  const monthSig = months.map((row) => row.key).join("|");
  const [view, setView] = useState("overall");
  const [fyKey, setFyKey] = useState(years[0]?.key || "");
  const [monthKey, setMonthKey] = useState(months[0]?.key || "");
  const [bucketKey, setBucketKey] = useState("");

  useEffect(() => {
    setView("overall");
    setFyKey(yearSig.split("|")[0] || "");
    setMonthKey(monthSig.split("|")[0] || "");
    setBucketKey("");
  }, [detail?.uk, yearSig, monthSig]);

  if (!gaps) {
    return (
      <div className="card">
        <h3>Sales</h3>
        <p className="muted">Create the report again. Order gaps are saved with that report.</p>
      </div>
    );
  }

  const selectedYear = years.find((row) => row.key === fyKey) || years[0] || gaps.fy;
  const selectedMonth = months.find((row) => row.key === monthKey) || months[0] || gaps.month;
  const period = view === "fy"
    ? (selectedYear || { buckets: [], lines: [], orders: 0, value: 0 })
    : view === "month"
      ? (selectedMonth || { buckets: [], lines: [], orders: 0, value: 0 })
      : (gaps.overall || { buckets: [], lines: [], orders: 0, value: 0 });
  const buckets = period.buckets || [];
  const periodLines = (period.lines || []).filter((row) => inSelectedPeriod(row.date_iso, view, monthKey, fyKey));
  const fallbackLines = periodLines.length ? periodLines : (gaps.overall?.lines || []).filter((row) => inSelectedPeriod(row.date_iso, view, monthKey, fyKey));
  const lines = fallbackLines.filter((row) => !bucketKey || row.bucket === bucketKey);
  const selected = buckets.find((row) => row.key === bucketKey);

  return (
    <div className="card">
      <h3>Sales</h3>
      <p className="muted">
        Days from one order to the next, for each customer. Invoices on the same day count as one order.
      </p>
      <div className="chips" style={{ marginTop: 12 }}>
        <button type="button" className={view === "overall" ? "" : "secondary"} onClick={() => { setView("overall"); setBucketKey(""); }}>Overall</button>
        <button type="button" className={view === "fy" ? "" : "secondary"} onClick={() => { setView("fy"); setBucketKey(""); }} disabled={!years.length && !gaps.fy}>Fiscal year</button>
        <button type="button" className={view === "month" ? "" : "secondary"} onClick={() => { setView("month"); setBucketKey(""); }} disabled={!months.length && !gaps.month}>Month</button>
      </div>
      {view === "fy" && years.length ? (
        <div className="card-head" style={{ alignItems: "center", gap: 12, flexWrap: "wrap", marginTop: 12 }}>
          <h4 className="quiet" style={{ margin: 0 }}>Fiscal year</h4>
          <select value={selectedYear?.key || ""} onChange={(e) => { setFyKey(e.target.value); setBucketKey(""); }} aria-label="Fiscal year">
            {years.map((row) => (
              <option key={row.key} value={row.key}>{row.label} · {row.orders || 0} orders</option>
            ))}
          </select>
        </div>
      ) : null}
      {view === "month" && months.length ? (
        <div className="card-head" style={{ alignItems: "center", gap: 12, flexWrap: "wrap", marginTop: 12 }}>
          <h4 className="quiet" style={{ margin: 0 }}>Month</h4>
          <select value={selectedMonth?.key || ""} onChange={(e) => { setMonthKey(e.target.value); setBucketKey(""); }} aria-label="Month">
            {months.map((row) => (
              <option key={row.key} value={row.key}>{row.label} · {row.orders || 0} orders</option>
            ))}
          </select>
        </div>
      ) : null}
      <div style={{ marginTop: 16 }}>
        <AgeBar
          parts={buckets.map((bucket, index) => ({
            key: bucket.key,
            label: bucketTitle(bucket),
            value: Number(bucket.value) || 0,
            color: bucket.key === "first" ? "#44403c" : ageColor(bucket.key, index),
          }))}
          selected={bucketKey}
          onSelect={setBucketKey}
        />
      </div>
      <div className="table-wrap" style={{ marginTop: 8 }}>
        <table className="dense list-table compact">
          <thead>
            <tr>
              <th>Date</th>
              {showParty ? <th>Customer</th> : null}
              <th>Invoice</th>
              <th className="num">Days since previous</th>
              <th className="num">Amount</th>
            </tr>
          </thead>
          <tbody>
            {lines.length ? lines.map((row, index) => (
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
                  {row.invoice_id ? (
                    <button type="button" className="linkish" onClick={() => hashSet("invoice/" + encodeURIComponent(row.invoice_id))}>
                      {row.invoice || "Sale"}
                    </button>
                  ) : (row.invoice || "—")}
                </td>
                <td className="num">{row.gap_days == null ? "First order" : row.gap_days}</td>
                <td className="num">{money(row.amount || 0)}</td>
              </tr>
            )) : (
              <tr>
                <td colSpan={showParty ? 5 : 4} className="muted">
                  {selected ? "No orders in " + bucketTitle(selected) + "." : "No orders in this period."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {period.orders ? (
        <p className="muted" style={{ marginTop: 8 }}>
          {period.orders} {period.orders === 1 ? "order" : "orders"} · {money(period.value || 0)}
          {selected ? " · showing " + bucketTitle(selected) : ""}
        </p>
      ) : null}
    </div>
  );
}
