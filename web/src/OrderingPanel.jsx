import { useEffect, useState } from "react";
import { api } from "./api";
import { ageKeysFrom, ageLabel, money, round2, rowBucket } from "./format";

function pct(flagged, sales) {
  const s = Number(sales) || 0;
  if (!s) return "—";
  return ((100 * (Number(flagged) || 0)) / s).toFixed(0) + "%";
}

function csvEscape(value) {
  const s = value == null ? "" : String(value);
  if (/[",\n\r]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

function toCsv(headers, rows) {
  const lines = [headers.map(csvEscape).join(",")];
  for (const row of rows) {
    lines.push(headers.map((h) => csvEscape(row[h])).join(","));
  }
  return "\uFEFF" + lines.join("\r\n");
}

function downloadText(filename, text, mime = "text/csv;charset=utf-8") {
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function safeFilenamePart(value) {
  return String(value || "export")
    .replace(/[^\w.-]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 80) || "export";
}

function dueBucketKeys(detail, customers) {
  const sample = (customers || []).find((c) => c && (c.owe_buckets || c.d0_15 != null)) || {};
  return ageKeysFrom(sample.owe_buckets || sample, detail.aging_bands);
}

function dueBucketHeader(key, bands) {
  return "Due " + ageLabel(key, bands);
}

/** Unique customers from flagged ordering events, enriched from member list when present. */
function followUpRowsFromEvents(events, customers, bucketKeys, bands) {
  const byUk = new Map();
  const byName = new Map();
  for (const c of customers || []) {
    if (c.uk) byUk.set(String(c.uk).toLowerCase(), c);
    if (c.name) byName.set(String(c.name).toLowerCase(), c);
  }
  const map = new Map();
  for (const ev of events || []) {
    const uk = String(ev.customer_uk || "").trim();
    const party = String(ev.party || "").trim();
    const key = (uk || party).toLowerCase();
    if (!key) continue;
    let row = map.get(key);
    if (!row) {
      const member = (uk && byUk.get(uk.toLowerCase())) || (party && byName.get(party.toLowerCase())) || {};
      row = {
        Customer: party || member.name || "",
        UK: uk || member.uk || "",
        "Flagged orders": 0,
        "Flagged sale value": 0,
        "Max oldest age": 0,
        "Overdue at flag": 0,
        "Latest flagged date": "",
        Invoices: [],
        Balance: member.due != null ? round2(member.due) : "",
        Status: member.status_label || member.status || "",
        Salesperson: member.salesperson || "",
        Group: member.group || "",
      };
      for (const bk of bucketKeys) {
        row[dueBucketHeader(bk, bands)] = round2(rowBucket(member, bk));
      }
      map.set(key, row);
    }
    row["Flagged orders"] += 1;
    row["Flagged sale value"] = round2(row["Flagged sale value"] + (Number(ev.amount) || 0));
    row["Overdue at flag"] = round2(row["Overdue at flag"] + (Number(ev.overdue_amount) || 0));
    if ((ev.oldest_age || 0) > row["Max oldest age"]) row["Max oldest age"] = ev.oldest_age || 0;
    if ((ev.date_iso || "") > row["Latest flagged date"]) row["Latest flagged date"] = ev.date_iso || "";
    if (ev.invoice) row.Invoices.push(ev.invoice);
  }
  return [...map.values()]
    .map((row) => ({
      ...row,
      Invoices: [...new Set(row.Invoices)].join("; "),
    }))
    .sort((a, b) => String(a.Customer).localeCompare(String(b.Customer), undefined, { sensitivity: "base" }));
}

function followUpCsvHeaders(bucketKeys, bands) {
  return [
    "Customer",
    "UK",
    "Flagged orders",
    "Flagged sale value",
    "Max oldest age",
    "Overdue at flag",
    "Latest flagged date",
    "Invoices",
    "Balance",
    ...bucketKeys.map((k) => dueBucketHeader(k, bands)),
    "Status",
    "Salesperson",
    "Group",
  ];
}

function downloadCollectionFollowUp(detail, period, view, selectedFy, selectedMonth) {
  const customers = detail.customers || [];
  const bands = detail.aging_bands;
  const bucketKeys = dueBucketKeys(detail, customers);
  const rows = followUpRowsFromEvents(period.events || [], customers, bucketKeys, bands);
  if (!rows.length) return;
  let periodKey = "overall";
  if (view === "fy" && selectedFy) periodKey = selectedFy.key || selectedFy.label || "fy";
  if (view === "month" && selectedMonth) periodKey = selectedMonth.key || "month";
  const name = safeFilenamePart(detail.name || detail.uk);
  const file = `collection_followup_${name}_${safeFilenamePart(periodKey)}.csv`;
  downloadText(file, toCsv(followUpCsvHeaders(bucketKeys, bands), rows));
}

function FlaggedTable({ rows, showParty }) {
  if (!rows.length) {
    return <p className="muted" style={{ marginTop: 12 }}>No orders while overdue in this period.</p>;
  }
  return (
    <div className="table-wrap" style={{ marginTop: 12 }}>
      <table className="data">
        <thead>
          <tr>
            <th>Date</th>
            {showParty ? <th>Customer</th> : null}
            <th>Invoice</th>
            <th className="num">Sale</th>
            <th className="num">Oldest age</th>
            <th className="num">Overdue</th>
            <th>Due days</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((e, i) => (
            <tr key={(e.invoice_id || e.invoice || "") + "-" + (e.date_iso || "") + "-" + i}>
              <td>{e.date_label || e.date_iso || "—"}</td>
              {showParty ? <td className="clip" title={e.party || ""}>{e.party || "—"}</td> : null}
              <td className="clip">{e.invoice || "—"}</td>
              <td className="num">{money(e.amount)}</td>
              <td className="num">{e.oldest_age != null ? e.oldest_age + "d" : "—"}</td>
              <td className="num">{money(e.overdue_amount)}</td>
              <td>{e.due_days != null ? e.due_days + " · " + (e.due_days_source || "") : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function OrderingPanel({ detail, showParty, entity, canEditDueDays, onDueDaysSaved }) {
  const ordering = detail.ordering || {};
  const overall = ordering.overall || {};
  const byFy = ordering.by_fy || [];
  const months = ordering.months || [];
  const [monthKey, setMonthKey] = useState(ordering.default_month || (months[0] && months[0].key) || "");
  const [fyKey, setFyKey] = useState((byFy[0] && byFy[0].key) || "");
  const [view, setView] = useState("overall");

  useEffect(() => {
    setMonthKey(ordering.default_month || (months[0] && months[0].key) || "");
    setFyKey((byFy[0] && byFy[0].key) || "");
    setView("overall");
  }, [detail.uk, ordering.default_month]);

  const selectedMonth = months.find((m) => m.key === monthKey) || months[0] || null;
  const selectedFy = byFy.find((y) => y.key === fyKey) || byFy[0] || null;

  let period = overall;
  if (view === "fy" && selectedFy) period = selectedFy;
  if (view === "month" && selectedMonth) period = selectedMonth;

  const sourceLabel = {
    customer: "customer",
    group: "group",
    rep: "sales rep",
    default: "default",
  }[detail.due_days_source || ordering.due_days_source || "default"] || "default";

  const editEntity = entity || (!showParty ? "customer" : null);

  return (
    <div className="card">
      <h3>Ordering</h3>
      <p className="muted">
        Sales placed while outstanding was older than due days (as of the sale date).
        Using <strong>{detail.due_days != null ? detail.due_days : ordering.due_days || 30}</strong> days
        {" "}· from {sourceLabel}.
      </p>
      {editEntity && detail.uk ? (
        <DueDaysEditor
          entity={editEntity}
          uk={detail.uk}
          detail={detail}
          canEdit={!!canEditDueDays}
          onSaved={onDueDaysSaved}
        />
      ) : null}

      <div className="buy-tiles" style={{ marginTop: 12 }}>
        <div className="card buy-tile">
          <span className="muted">Overall sales</span>
          <strong>{money(overall.sales_value || 0)}</strong>
          <span className="muted">{overall.sales_count || 0} orders</span>
        </div>
        <div className="card buy-tile">
          <span className="muted">Flagged overall</span>
          <strong>{money(overall.flagged_value || 0)}</strong>
          <span className="muted">{overall.flagged_count || 0} · {pct(overall.flagged_value, overall.sales_value)}</span>
        </div>
        {selectedMonth ? (
          <div className="card buy-tile">
            <span className="muted">{selectedMonth.label}</span>
            <strong>{money(selectedMonth.flagged_value || 0)}</strong>
            <span className="muted">{selectedMonth.flagged_count || 0} flagged</span>
          </div>
        ) : null}
        {selectedFy ? (
          <div className="card buy-tile">
            <span className="muted">{selectedFy.label}</span>
            <strong>{money(selectedFy.flagged_value || 0)}</strong>
            <span className="muted">{selectedFy.flagged_count || 0} flagged</span>
          </div>
        ) : null}
      </div>

      <div className="chips" style={{ marginTop: 16 }}>
        <button type="button" className={view === "overall" ? "" : "secondary"} onClick={() => setView("overall")}>Overall</button>
        <button type="button" className={view === "fy" ? "" : "secondary"} onClick={() => setView("fy")} disabled={!byFy.length}>Fiscal year</button>
        <button type="button" className={view === "month" ? "" : "secondary"} onClick={() => setView("month")}>Month</button>
      </div>

      {view === "fy" && byFy.length ? (
        <div className="card-head" style={{ alignItems: "center", gap: 12, flexWrap: "wrap", marginTop: 12 }}>
          <h4 className="quiet" style={{ margin: 0 }}>Per fiscal year</h4>
          <select value={selectedFy ? selectedFy.key : ""} onChange={(e) => setFyKey(e.target.value)} aria-label="Fiscal year">
            {byFy.map((y) => (
              <option key={y.key} value={y.key}>{y.label} · {y.flagged_count || 0} flagged</option>
            ))}
          </select>
        </div>
      ) : null}

      {view === "month" ? (
        <div className="card-head" style={{ alignItems: "center", gap: 12, flexWrap: "wrap", marginTop: 12 }}>
          <h4 className="quiet" style={{ margin: 0 }}>By month</h4>
          {months.length ? (
            <select value={selectedMonth ? selectedMonth.key : ""} onChange={(e) => setMonthKey(e.target.value)} aria-label="Order month">
              {months.map((m) => (
                <option key={m.key} value={m.key}>{m.label} · {m.flagged_count || 0} flagged</option>
              ))}
            </select>
          ) : null}
        </div>
      ) : null}

      <div style={{ marginTop: 12 }}>
        <div className="card-head" style={{ alignItems: "center", gap: 12, flexWrap: "wrap", marginBottom: 0 }}>
          <p className="muted" style={{ margin: 0 }}>
            {period.flagged_count || 0} of {period.sales_count || 0} orders flagged
            {" · "}{money(period.flagged_value || 0)} of {money(period.sales_value || 0)}
            {" · "}{pct(period.flagged_value, period.sales_value)} of value
          </p>
          {showParty ? (
            <button
              type="button"
              className="secondary"
              disabled={!(period.events || []).length}
              title="Download unique customers with flagged orders in this view"
              onClick={() => downloadCollectionFollowUp(detail, period, view, selectedFy, selectedMonth)}
            >
              Download collection follow-up
            </button>
          ) : null}
        </div>
        <FlaggedTable rows={period.events || []} showParty={showParty} />
      </div>
    </div>
  );
}

export function DueDaysEditor({ entity, uk, detail, onSaved, canEdit }) {
  const [value, setValue] = useState(detail.due_days != null ? String(detail.due_days) : "30");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const own = !!detail.due_days_own;
  const source = detail.due_days_source || "default";

  useEffect(() => {
    setValue(detail.due_days != null ? String(detail.due_days) : "30");
    setErr("");
  }, [detail.uk, detail.due_days]);

  if (!canEdit) {
    return (
      <p className="muted" style={{ margin: "8px 0 0" }}>
        Due days: <strong>{detail.due_days != null ? detail.due_days : 30}</strong>
        {" "}· from {source}{own ? " (own)" : ""}
      </p>
    );
  }

  async function save(next) {
    setBusy(true);
    setErr("");
    try {
      let out;
      if (entity === "customer") out = await api.setCustomerDueDays(uk, next);
      else if (entity === "group") out = await api.setGroupDueDays(uk, next);
      else out = await api.setRepDueDays(uk, next);
      if (onSaved) onSaved(out);
    } catch (e) {
      setErr(e.message || "Could not save");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ marginTop: 8, display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
      <label className="muted" style={{ display: "flex", gap: 6, alignItems: "center" }}>
        Due days
        <input
          type="number"
          min={0}
          style={{ width: 72 }}
          value={value}
          disabled={busy}
          onChange={(e) => setValue(e.target.value)}
        />
      </label>
      <button type="button" className="btn" disabled={busy} onClick={() => save(Number(value))}>
        Save
      </button>
      {own ? (
        <button type="button" className="btn ghost" disabled={busy} onClick={() => save(null)}>
          Clear override
        </button>
      ) : null}
      <span className="muted">from {source}{own ? " (own)" : ""}</span>
      {err ? <span className="err">{err}</span> : null}
    </div>
  );
}

export function orderingHeroLine(detail) {
  const ordering = detail.ordering?.months ? detail.ordering : (detail.ordering_brief || detail.ordering || {});
  const badge = ordering.badge || {};
  const months = ordering.months || [];
  const byFy = ordering.by_fy || [];
  const currentKey = ordering.default_month;
  const month = months.find((m) => m.key === currentKey);
  if (badge.current_month && month && month.flagged_count) {
    return `${month.flagged_count} orders while overdue this month · ${money(month.flagged_value)}`;
  }
  if (badge.current_fy) {
    const asOf = detail.as_of || "";
    let fy = null;
    if (asOf) {
      const [yy, mm] = asOf.split("-").map(Number);
      const fyStartYear = mm >= 4 ? yy : yy - 1;
      const fyKey = `${fyStartYear}-04-01`;
      fy = byFy.find((y) => y.key === fyKey);
    }
    if (!fy) fy = byFy.find((y) => (y.flagged_count || 0) > 0) || byFy[0];
    if (fy && fy.flagged_count) {
      return `${fy.flagged_count} orders while overdue ${fy.label} · ${money(fy.flagged_value)}`;
    }
  }
  return "";
}
