import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "./api";
import { hashSet, money } from "./format";
import SalesCompare, { formatQty, resultLabel } from "./SalesCompare";
import { can } from "./theme";

function cellText(cell) {
  if (!cell || cell.value == null || cell.value === "") return cell?.reason || "—";
  return cell.value;
}

const PLAIN_METRICS = new Set(["collection_rate", "gross_margin", "dso", "stock_cover_days"]);

function showCell(row, cell) {
  if (PLAIN_METRICS.has(row.id)) return cellText(cell);
  return moneyCell(cell);
}

function moneyCell(cell) {
  if (!cell || cell.value == null || cell.value === "") return cell?.reason || "—";
  const n = Number(cell.value);
  if (!Number.isFinite(n)) return String(cell.value);
  return money(n);
}

const PAGE = {
  scorecard: ["Scorecard", "This period, the prior period, last year, and any target."],
  "sales-change": ["Sales change", "Customers and products that moved sales."],
  "customer-movement": ["Customer movement", "Who bought, who stopped, and who to recover."],
  collection: ["Collection worklist", "Outstanding balances to assign."],
  stock: ["Stock decisions", "Cover, slow stock, and what to reorder."],
  quality: ["Data quality", "Exceptions to correct in the source files."],
  review: ["Weekly review", "Suggested work for this report, and what is already assigned."],
  reorder: ["Reorder", "Quantities round up to pack size and stop at the budget. Snapshot cost is today's purchase price."],
  builder: ["Report builder", "Arrange the existing metrics. Saving a report does not change sales, outstanding, or stock."],
};

const FILTER_SECTIONS = new Set(["sales-change", "customer-movement", "collection", "stock", "quality"]);

const TYPE_LABEL = {
  collection: "Collection",
  recovery: "Recovery",
  purchase: "Purchase",
  data_fix: "Data fix",
};

function statusPill(status) {
  const label = status === "done" ? "Done" : status === "dropped" ? "Dropped" : "Open";
  const tone = status === "done" ? "credit" : status === "dropped" ? "stopped" : "warn";
  return <span className={"pill " + tone}>{label}</span>;
}

function drill(row) {
  const target = row?.drill;
  if (!target?.name) return;
  if (target.kind === "item") hashSet("item/" + encodeURIComponent(target.name));
  else hashSet("customer/" + encodeURIComponent(target.name));
}

export default function AnalyticsPage({ section, run, user }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [query, setQuery] = useState("");
  const [saved, setSaved] = useState("");
  const [draft, setDraft] = useState(null);
  const manage = can(user, "actions.manage");

  useEffect(() => {
    let cancelled = false;
    setErr("");
    setSaved("");
    if (section === "review" || section === "reorder" || section === "builder") {
      setData({});
      return undefined;
    }
    api.analytics(run?.id ? { run: run.id } : {})
      .then((payload) => { if (!cancelled) setData(payload); })
      .catch((e) => { if (!cancelled) setErr(e.message || "Could not load"); });
    api.savedViews()
      .then((payload) => {
        if (cancelled) return;
        const filters = (payload.views || {})[section] || {};
        setQuery(filters.query || "");
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [run?.id, section]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return null;
    return q;
  }, [query]);

  function matches(value) {
    if (!filtered) return true;
    return String(value || "").toLowerCase().includes(filtered);
  }

  async function saveFilters() {
    setSaved("");
    try {
      await api.saveView(section, { query });
      setSaved("Filters saved");
    } catch (e) {
      setErr(e.message || "Could not save filters");
    }
  }

  if (err) return <p className="err">{err}</p>;
  if (!data) return <p className="muted">Loading…</p>;

  const [title, blurb] = PAGE[section] || ["Reports", ""];
  const showFilter = FILTER_SECTIONS.has(section);

  return (
    <div className="workspace-page">
      <div className="page-head">
        <div className="page-head-copy">
          <h2>{title}</h2>
          <p className="muted">
            {blurb}
            {run?.report_date ? " · " + run.report_date : ""}
          </p>
        </div>
        {showFilter ? (
          <div className="page-head-tools">
            <input
              className="search-input"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Filter this list"
              aria-label="Filter"
            />
            <button type="button" className="secondary" onClick={saveFilters}>Save view</button>
          </div>
        ) : null}
      </div>
      {saved ? <p className="ok analytics-flash">{saved}</p> : null}
      {section === "scorecard" ? <Scorecard data={data.scorecard} reportDate={run?.report_date || data.report_date || ""} /> : null}
      {section === "sales-change" ? <SalesChange data={data.sales_change} matches={matches} /> : null}
      {section === "customer-movement" ? (
        <Movement data={data.customer_movement} matches={matches} onAssign={manage ? (row) => setDraft({
          action_type: "recovery",
          subject_kind: "customer",
          subject_name: row.name,
          proposal: "Recover " + row.name,
          was_inactive: row.movement === "inactive",
          report_date: run?.report_date || data.report_date || "",
        }) : null} />
      ) : null}
      {section === "collection" ? (
        <Collection data={data.collection} matches={matches} onAssign={manage ? (row) => setDraft({
          action_type: "collection",
          subject_kind: "customer",
          subject_name: row.name,
          proposal: "Collect from " + row.name,
          amount: row.balance,
          report_date: run?.report_date || data.report_date || "",
        }) : null} />
      ) : null}
      {section === "stock" ? (
        <StockDecisions data={data.stock} matches={matches} onAssign={manage ? (row) => setDraft({
          action_type: "purchase",
          subject_kind: "item",
          subject_name: row.name,
          proposal: "Reorder " + row.name,
          amount: row.on_hand,
          report_date: run?.report_date || data.report_date || "",
        }) : null} />
      ) : null}
      {section === "quality" ? (
        <Quality data={data.quality} matches={matches} onAssign={manage ? (row) => setDraft({
          action_type: "data_fix",
          subject_kind: "quality",
          subject_name: row.message,
          proposal: row.fix,
          quality_message: row.message,
          report_date: run?.report_date || data.report_date || "",
        }) : null} />
      ) : null}
      {section === "review" ? <WeeklyReview run={run} user={user} /> : null}
      {section === "reorder" ? <ReorderPage run={run} user={user} /> : null}
      {section === "builder" ? <ReportBuilder run={run} user={user} /> : null}
      {draft ? (
        <AssignDialog
          draft={draft}
          user={user}
          onClose={() => setDraft(null)}
          onSaved={() => { setDraft(null); setSaved("Action assigned"); }}
        />
      ) : null}
    </div>
  );
}

function Scorecard({ data, reportDate }) {
  const rows = data?.rows || [];
  const [forecast, setForecast] = useState(null);
  const [scenario, setScenario] = useState("");
  useEffect(() => {
    const params = new URLSearchParams();
    if (reportDate) params.set("report_date", reportDate);
    if (scenario) {
      params.set("scenario", "Sales factor");
      params.set("sales_factor", scenario);
    }
    const qs = params.toString() ? "?" + params.toString() : "";
    api.forecast(qs).then(setForecast).catch(() => setForecast(null));
  }, [reportDate, scenario]);
  if (!rows.length) return <p className="muted">Create a report to see the scorecard.</p>;
  return (
    <div className="stack">
    <div className="card table-card list-panel">
      <div className="table-wrap">
        <table className="dense list-table compact">
          <thead>
            <tr>
              <th>Metric</th>
              <th className="num">This period</th>
              <th className="num">Prior period</th>
              <th className="num">Prior year</th>
              <th className="num">Target</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td>{row.label}</td>
                <td className="num">{showCell(row, row.current)}</td>
                <td className="num">{showCell(row, row.prior)}</td>
                <td className="num">{showCell(row, row.prior_year)}</td>
                <td className="num">{moneyCell(row.target)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
    <label className="scenario-field">
      Scenario factor
      <input value={scenario} placeholder="1.1" onChange={(e) => setScenario(e.target.value)} />
    </label>
    {forecast ? <ForecastCard forecast={forecast} /> : null}
    </div>
  );
}

function ForecastCard({ forecast }) {
  return (
    <div className="card">
      <h3>Sales forecast · {forecast.window?.start} to {forecast.window?.end}</h3>
      <p className="muted">These figures are labelled estimates. They are not on the scorecard.</p>
      <div className="table-wrap">
        <table className="dense list-table compact">
          <thead>
            <tr><th>Method</th><th className="num">Sales</th></tr>
          </thead>
          <tbody>
            {(forecast.methods || []).map((row) => (
              <tr key={row.label}>
                <td>{row.label}</td>
                <td className="num">{row.value == null ? (row.reason || "—") : money(row.value)}</td>
              </tr>
            ))}
            <tr>
              <td>{forecast.uncertainty?.label || "Gap between methods"}</td>
              <td className="num">{forecast.uncertainty?.value == null ? (forecast.uncertainty?.reason || "—") : money(forecast.uncertainty.value)}</td>
            </tr>
          </tbody>
        </table>
      </div>
      {forecast.scenario ? (
        <p className="muted">{forecast.scenario.label}: {forecast.scenario.name}. {(forecast.scenario.methods || []).map((row) => row.label + " " + (row.value == null ? (row.reason || "—") : money(row.value))).join("; ")}</p>
      ) : null}
    </div>
  );
}

function signedMoney(n) {
  if (n == null || n === "") return "—";
  const v = Number(n);
  if (!Number.isFinite(v)) return "—";
  const body = money(Math.abs(v));
  if (v > 0) return "+" + body;
  if (v < 0) return "-" + body;
  return body;
}

function signedQty(n) {
  if (n == null || n === "") return "—";
  const v = Number(n);
  if (!Number.isFinite(v)) return "—";
  const body = formatQty(Math.abs(v));
  if (v > 0) return "+" + body;
  if (v < 0) return "-" + body;
  return body;
}

function SalesChange({ data, matches }) {
  if (!data) return <p className="muted">Sales change is not available for this login.</p>;
  const customers = (data.customers || []).filter((row) => matches(row.name));
  const products = (data.products || []).filter((row) => matches(row.name));
  const bridge = data.bridge || {};
  return (
    <div>
      <SalesCompare data={data.summary} />
      {bridge.status === "unavailable" ? (
        <p className="muted analytics-note">Price, volume, and mix: {bridge.reason}</p>
      ) : (
        <div className="analytics-bridge">
          <span>Price {money(bridge.price)}</span>
          <span>Volume {money(bridge.volume)}</span>
          <span>Mix {money(bridge.mix)}</span>
        </div>
      )}
      <SectionTable
        title="Customers"
        headers={["Customer", "This period", "Prior period", "Change", "Result"]}
        numFrom={1}
        rows={customers}
        cells={(row) => [row.name, row.current == null ? "—" : money(row.current), row.prior == null ? "—" : money(row.prior), signedMoney(row.change), resultLabel(row.change)]}
      />
      {products.length ? (
        <SectionTable
          title="Products"
          headers={["Product", "Qty this period", "Qty prior", "Qty change", "Amount this period", "Amount prior", "Amount change", "Qty", "Amount"]}
          numFrom={1}
          rows={products}
          cells={(row) => [
            row.name,
            row.qty_current == null ? "—" : formatQty(row.qty_current),
            row.qty_prior == null ? "—" : formatQty(row.qty_prior),
            signedQty(row.qty_change),
            row.current == null ? "—" : money(row.current),
            row.prior == null ? "—" : money(row.prior),
            signedMoney(row.change),
            resultLabel(row.qty_change),
            resultLabel(row.change),
          ]}
        />
      ) : <p className="muted">No item lines in these periods.</p>}
    </div>
  );
}

function Movement({ data, matches, onAssign }) {
  const rows = (data?.rows || []).filter((row) => matches(row.name) || matches(row.movement) || matches(row.status));
  return (
    <SectionTable
      title="Customers"
      headers={["Customer", "Movement", "Status", "This period", "Prior period", "Buying cycle"]}
      rows={rows}
      onAssign={onAssign}
      cells={(row) => [
        row.name,
        row.movement,
        row.status || "",
        row.current == null ? "—" : money(row.current),
        row.prior == null ? "—" : money(row.prior),
        row.buying_cycle || row.buying_cycle_reason || "—",
      ]}
    />
  );
}

function Collection({ data, matches, onAssign }) {
  if (data?.status === "unavailable") return <p className="muted">{data.reason}</p>;
  const rows = (data?.rows || []).filter((row) => matches(row.name) || matches(row.status));
  return (
    <SectionTable
      title="Who to collect from"
      headers={["Customer", "Status", "Balance", "Overdue 30+", "Invoices"]}
      rows={rows}
      onAssign={onAssign}
      cells={(row) => [
        row.name,
        row.status,
        money(row.balance),
        money(row.overdue_30),
        row.invoice_detail === "available" || row.invoice_detail === "estimated"
          ? (row.invoices || []).map((inv) => inv.invoice + " " + money(inv.remaining)).join(", ")
            + (row.invoice_detail === "estimated" ? " (estimated)" : "")
          : "Invoice detail unavailable",
      ]}
    />
  );
}

function StockDecisions({ data, matches, onAssign }) {
  if (data?.status === "unavailable") return <p className="muted">{data.reason}</p>;
  const rows = (data?.rows || []).filter((row) => matches(row.name));
  return (
    <div>
      <div className="analytics-bridge">
        <span>Cover {data?.cover_days != null ? data.cover_days + " days" : (data?.cover_label || "No recent demand")}</span>
        {data?.slow_value != null ? <span>Slow stock {money(data.slow_value)}</span> : null}
        {data?.uncosted ? <span>{data.uncosted} uncosted</span> : null}
      </div>
      <SectionTable
        title="Items"
        headers={["Item", "On hand", "Qty 30 days", "Cover", "Slow value"]}
        rows={rows}
        onAssign={onAssign}
        cells={(row) => [
          row.name,
          row.on_hand,
          row.qty_30,
          row.cover_days != null ? row.cover_days : (row.cover_label || "—"),
          row.slow_value == null ? (row.slow ? "Missing cost" : "—") : money(row.slow_value),
        ]}
      />
    </div>
  );
}

function Quality({ data, matches, onAssign }) {
  const rows = (data?.rows || []).filter((row) => matches(row.message) || matches(row.fix));
  if (!rows.length) return <p className="ok">No data-quality exceptions.</p>;
  return (
    <SectionTable
      title="Fixes"
      headers={["Severity", "What happened", "Fix"]}
      rows={rows}
      cells={(row) => [row.severity, row.message, row.fix]}
      drillable={false}
      onAssign={onAssign}
    />
  );
}

function SectionTable({ title, headers, rows, cells, drillable = true, onAssign, numFrom = null }) {
  const cols = headers.length + (onAssign ? 1 : 0);
  return (
    <div className="card table-card list-panel analytics-table">
      <div className="table-card-head"><h3>{title}</h3></div>
      <div className="table-wrap">
        <table className="dense list-table compact">
          <thead>
            <tr>{headers.map((h, idx) => <th key={h} className={numFrom != null && idx >= numFrom && h !== "Result" && h !== "Qty" && h !== "Amount" ? "num" : ""}>{h}</th>)}{onAssign ? <th className="num">Assign</th> : null}</tr>
          </thead>
          <tbody>
            {rows.length ? rows.map((row, i) => (
              <tr
                key={row.name || row.message || i}
                className={drillable ? "click-row" : undefined}
                onClick={drillable ? () => drill(row) : undefined}
              >
                {cells(row).map((value, idx) => <td key={idx} className={numFrom != null && idx >= numFrom && headers[idx] !== "Result" && headers[idx] !== "Qty" && headers[idx] !== "Amount" ? "num" : ""}>{value}</td>)}
                {onAssign ? (
                  <td className="num">
                    <button type="button" className="secondary analytics-assign" onClick={(e) => { e.stopPropagation(); onAssign(row); }}>Assign</button>
                  </td>
                ) : null}
              </tr>
            )) : (
              <tr><td className="muted" colSpan={cols}>Nothing in this filter.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function AssignDialog({ draft, user, onClose, onSaved }) {
  const [form, setForm] = useState({
    ...draft,
    owner: draft.owner || user?.username || "",
    due_date: draft.due_date || "",
  });
  const [owners, setOwners] = useState([]);
  const [err, setErr] = useState("");
  useEffect(() => {
    api.actions().then((payload) => setOwners(payload.owners || [])).catch(() => {});
  }, []);
  useEffect(() => {
    function onKey(e) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  async function save(e) {
    e.preventDefault();
    setErr("");
    try {
      await api.createAction(form);
      onSaved();
    } catch (errSave) {
      setErr(errSave.message || "Could not assign");
    }
  }
  return createPortal(
    <div className="modal-backdrop" onClick={onClose}>
      <form
        className="modal assign-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="assign-title"
        onClick={(ev) => ev.stopPropagation()}
        onSubmit={save}
      >
        <p className="analytics-kicker">{TYPE_LABEL[form.action_type] || "Action"}</p>
        <h3 id="assign-title">{form.subject_name || "Assign"}</h3>
        <div className="assign-form">
          <label className="span-2">
            Proposal
            <input value={form.proposal} onChange={(e) => setForm({ ...form, proposal: e.target.value })} />
          </label>
          <label>
            Owner
            <select value={form.owner} onChange={(e) => setForm({ ...form, owner: e.target.value })}>
              <option value="">Select</option>
              {owners.map((name) => <option key={name} value={name}>{name}</option>)}
            </select>
          </label>
          <label>
            Due date
            <input type="date" value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })} />
          </label>
        </div>
        {err ? <p className="err">{err}</p> : null}
        <div className="modal-actions">
          <button type="button" className="secondary" onClick={onClose}>Cancel</button>
          <button type="submit">Save action</button>
        </div>
      </form>
    </div>,
    document.body,
  );
}

function WeeklyReview({ run, user }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [draft, setDraft] = useState(null);
  const manage = can(user, "actions.manage");
  function load() {
    api.review(run?.id ? { run: run.id } : {})
      .then(setData)
      .catch((e) => setErr(e.message || "Could not load"));
  }
  useEffect(() => { load(); }, [run?.id]);
  if (err) return <p className="err">{err}</p>;
  if (!data) return <p className="muted">Loading…</p>;
  return (
    <div className="analytics-columns">
      <section>
        <h3>Suggested</h3>
        <div className="analytics-list">
          {(data.suggestions || []).map((row) => (
            <article className="analytics-item" key={row.reason + row.subject_name}>
              <div>
                <p className="analytics-kicker">{row.reason}</p>
                <p className="analytics-title">{row.proposal}</p>
              </div>
              {manage ? (
                <button type="button" onClick={() => setDraft({ ...row, due_date: data.default_due, report_date: data.report_date })}>Assign</button>
              ) : null}
            </article>
          ))}
          {!(data.suggestions || []).length ? <p className="muted">No suggestions for this report.</p> : null}
        </div>
      </section>
      <section>
        <h3>This week</h3>
        <div className="analytics-list">
          {(data.actions || []).map((row) => (
            <article className="analytics-item" key={row.id}>
              <div>
                <p className="analytics-kicker">{TYPE_LABEL[row.action_type] || "Action"}</p>
                <p className="analytics-title">{row.proposal}</p>
                <div className="analytics-meta">
                  {statusPill(row.status)}
                  <span>{row.owner}</span>
                  <span>Due {row.due_date}</span>
                  {row.outcome?.label ? <span>{row.outcome.label}</span> : null}
                </div>
              </div>
              {manage && row.status === "open" ? (
                <button type="button" className="secondary" onClick={() => api.setActionStatus(row.id, "done").then(load)}>Mark done</button>
              ) : null}
            </article>
          ))}
          {!(data.actions || []).length ? <p className="muted">Nothing assigned for this report yet.</p> : null}
        </div>
      </section>
      {draft ? <AssignDialog draft={draft} user={user} onClose={() => setDraft(null)} onSaved={() => { setDraft(null); load(); }} /> : null}
    </div>
  );
}

function ReorderPage({ run, user }) {
  const [data, setData] = useState(null);
  const [lines, setLines] = useState([]);
  const [budget, setBudget] = useState("");
  const [owner, setOwner] = useState(user?.username || "");
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const manage = can(user, "actions.manage");
  useEffect(() => {
    api.reorder(run?.id ? { run: run.id } : {})
      .then((payload) => {
        setData(payload);
        setLines(payload.lines || []);
        setBudget(payload.budget == null ? "" : String(payload.budget));
      })
      .catch((e) => setErr(e.message || "Could not load"));
  }, [run?.id]);
  function patch(index, key, value) {
    setLines((prev) => prev.map((row, i) => (i === index ? { ...row, [key]: value } : row)));
  }
  async function save(assign) {
    setErr("");
    setMsg("");
    try {
      const out = await api.saveReorder({
        budget: budget === "" ? null : Number(budget),
        assign,
        owner,
        report_date: data?.report_date || run?.report_date || "",
        lines: lines.map((row) => ({
          name: row.name,
          qty: Number(row.qty),
          pack_size: Number(row.pack_size || 0),
          minimum: Number(row.minimum || 0),
          lead_days: Number(row.lead_days || 0),
          supplier: row.supplier || "",
          unit_cost: row.unit_cost || 0,
        })),
      });
      setLines(out.lines || []);
      setData((prev) => ({ ...(prev || {}), spent: out.spent, stopped: out.stopped }));
      setMsg(assign ? "Reorder saved and assigned. This is not a purchase order." : "Reorder saved.");
    } catch (e) {
      setErr(e.message || "Could not save");
    }
  }
  if (err && !data) return <p className="err">{err}</p>;
  if (!data) return <p className="muted">Loading…</p>;
  if (data.status === "unavailable") return <p className="muted">{data.reason}</p>;
  const owners = data.owners?.length ? data.owners : (owner ? [owner] : []);
  return (
    <div>
      <div className="analytics-toolbar">
        <label>
          Budget
          <input type="number" value={budget} onChange={(e) => setBudget(e.target.value)} />
        </label>
        {manage ? (
          <label>
            Owner
            <select value={owner} onChange={(e) => setOwner(e.target.value)}>
              {owners.map((name) => <option key={name} value={name}>{name}</option>)}
            </select>
          </label>
        ) : null}
        {data.spent != null && budget !== "" ? (
          <span className="page-stat">Spent {money(data.spent)} of {money(Number(budget))}</span>
        ) : null}
      </div>
      <div className="card table-card list-panel">
        <div className="table-wrap">
          <table className="dense list-table compact analytics-edit">
            <thead>
              <tr>
                <th>Item</th><th className="num">Cover</th><th>Qty</th><th>Pack</th><th>Minimum</th><th>Lead days</th><th>Supplier</th><th className="num">Snapshot cost</th>
              </tr>
            </thead>
            <tbody>
              {lines.length ? lines.map((row, i) => (
                <tr key={row.name}>
                  <td>{row.name}</td>
                  <td className="num">{row.cover_days}</td>
                  <td><input type="number" value={row.qty} onChange={(e) => patch(i, "qty", e.target.value)} /></td>
                  <td><input type="number" value={row.pack_size || ""} onChange={(e) => patch(i, "pack_size", e.target.value)} /></td>
                  <td><input type="number" value={row.minimum || ""} onChange={(e) => patch(i, "minimum", e.target.value)} /></td>
                  <td><input type="number" value={row.lead_days || ""} onChange={(e) => patch(i, "lead_days", e.target.value)} /></td>
                  <td className="wide"><input value={row.supplier || ""} onChange={(e) => patch(i, "supplier", e.target.value)} /></td>
                  <td className="num">{row.unit_cost == null ? "—" : money(row.unit_cost)}</td>
                </tr>
              )) : (
                <tr><td className="muted" colSpan={8}>No short-cover items for this report.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
      {data.stopped ? <p className="muted">Later lines were left out because they would pass the budget.</p> : null}
      {err ? <p className="err">{err}</p> : null}
      {msg ? <p className="ok analytics-flash">{msg}</p> : null}
      {manage ? (
        <div className="analytics-foot">
          <p className="muted">Saving does not create a purchase order.</p>
          <div className="analytics-foot-actions">
            <button type="button" className="secondary" onClick={() => save(false)}>Save proposal</button>
            <button type="button" onClick={() => save(true)}>Save and assign</button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

const DIMENSION_LABEL = {
  customer: "Customer",
  product: "Product",
  sales_rep: "Salesperson",
  group: "Group",
  location: "Location",
};

const COMPARISON_LABEL = {
  current: "This period",
  prior: "Prior period",
  prior_year: "Prior year",
};

const MONEY_METRICS = new Set([
  "sales_mtd", "sales_ytd", "collections_mtd", "sales_change_drivers",
  "ar_balance", "ar_overdue_30", "slow_stock_value",
]);

function cellLabel(metricId, cell) {
  if (!cell || cell.value == null || cell.value === "") return cell?.reason || "—";
  const n = Number(cell.value);
  if (!Number.isFinite(n)) return String(cell.value);
  if (MONEY_METRICS.has(metricId)) return money(n);
  if (metricId === "collection_rate" || metricId === "gross_margin") return n.toLocaleString(undefined, { maximumFractionDigits: 1 }) + "%";
  return n.toLocaleString(undefined, { maximumFractionDigits: 1 });
}

function ReportBuilder({ run, user }) {
  const manage = can(user, "reports.manage");
  const [catalog, setCatalog] = useState(null);
  const [reports, setReports] = useState([]);
  const [name, setName] = useState("");
  const [dimension, setDimension] = useState("sales_rep");
  const [comparison, setComparison] = useState("current");
  const [metricIds, setMetricIds] = useState(["sales_mtd"]);
  const [filterValue, setFilterValue] = useState("");
  const [customColumn, setCustomColumn] = useState("");
  const [schedule, setSchedule] = useState(false);
  const [showPack, setShowPack] = useState(false);
  const [rowFilter, setRowFilter] = useState("");
  const [preview, setPreview] = useState(null);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState(null);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");

  function loadReports() {
    api.savedReports().then((payload) => setReports(payload.reports || [])).catch((e) => setErr(e.message || "Could not load"));
  }

  useEffect(() => {
    api.savedReportCatalog().then(setCatalog).catch((e) => setErr(e.message || "Could not load"));
    loadReports();
  }, []);

  const metrics = (catalog?.metrics || []).filter((row) => (row.dimensions || []).includes(dimension));

  function toggleMetric(id) {
    setMetricIds((prev) => (prev.includes(id) ? prev.filter((item) => item !== id) : prev.concat(id)));
  }

  function payload() {
    return {
      name: name || "Untitled report",
      metric_ids: metricIds,
      dimension,
      comparison,
      filters: filterValue.trim() ? [{ field: "name", value: filterValue.trim() }] : [],
      custom_column: customColumn,
      schedule,
      show_pack_size: dimension === "product" && showPack,
      row_filter: rowFilter,
      report_date: run?.report_date || "",
    };
  }

  async function previewReport() {
    setErr("");
    setMsg("");
    try {
      setPreview(await api.previewSavedReport(payload()));
    } catch (e) {
      setErr(e.message || "Could not preview");
    }
  }

  async function saveReport() {
    setErr("");
    setMsg("");
    try {
      await api.createSavedReport(payload());
      setMsg("Draft saved. It stays hidden until you approve it.");
      loadReports();
    } catch (e) {
      setErr(e.message || "Could not save");
    }
  }

  async function approve(id) {
    setErr("");
    try {
      await api.approveSavedReport(id);
      loadReports();
    } catch (e) {
      setErr(e.message || "Could not approve");
    }
  }

  async function adopt() {
    setErr("");
    try {
      await api.adoptPack();
      setMsg("Wholesale templates added as drafts.");
      loadReports();
    } catch (e) {
      setErr(e.message || "Could not turn on the pack");
    }
  }

  async function adoptRetail() {
    setErr("");
    try {
      await api.adoptRetailPack();
      setMsg("Retail templates added as drafts.");
      loadReports();
    } catch (e) {
      setErr(e.message || "Could not turn on the retail pack");
    }
  }

  async function ask() {
    setErr("");
    setAnswer(null);
    try {
      setAnswer(await api.askReport({ text: question, report_date: run?.report_date || "" }));
    } catch (e) {
      setErr(e.message || "Could not answer");
    }
  }

  function applyTemplate(template) {
    setName(template.name || "");
    setDimension(template.dimension || "customer");
    setComparison(template.comparison || "current");
    setMetricIds(template.metric_ids || []);
    setShowPack(Boolean(template.show_pack_size));
    setRowFilter(template.row_filter || "");
    setFilterValue("");
    setSchedule(false);
    setPreview(null);
  }

  if (!catalog) return err ? <p className="err">{err}</p> : <p className="muted">Loading…</p>;

  return (
    <div>
      {manage ? (
        <div className="card builder-form">
          <div className="builder-section">
            <h3>Start from a template</h3>
            <div className="metric-picks">
              {(catalog.templates || []).map((template) => (
                <button type="button" key={template.id} className="metric-pick" onClick={() => applyTemplate(template)}>
                  {template.name}
                </button>
              ))}
              <button type="button" className="secondary" onClick={adopt}>Add wholesale templates</button>
            </div>
          </div>
          <div className="builder-section">
            <h3>Retail pack</h3>
            <div className="metric-picks">
              {(catalog.retail_templates || []).map((template) => (
                <button type="button" key={template.id} className="metric-pick" onClick={() => applyTemplate(template)}>
                  {template.name}
                </button>
              ))}
              <button type="button" className="secondary" onClick={adoptRetail}>Add retail templates</button>
            </div>
          </div>
          <div className="builder-section">
            <h3>Ask an approved figure</h3>
            <div className="analytics-toolbar">
              <label>
                Question
                <input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Sales" />
              </label>
              <button type="button" className="secondary" onClick={ask}>Answer</button>
            </div>
            {answer ? (
              <p className={answer.answered ? "" : "muted"}>
                {answer.answered
                  ? (answer.name || answer.metric_id) + ": " + (answer.value == null ? (answer.reason || "—") : answer.value) + (answer.metric_versions ? " · version " + Object.values(answer.metric_versions).join(", ") : "")
                  : (answer.message || "Cannot answer that.")}
              </p>
            ) : null}
          </div>
          <div className="analytics-toolbar">
            <label>
              Name
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Sales by salesperson" />
            </label>
            <label>
              Group by
              <select value={dimension} onChange={(e) => {
                const next = e.target.value;
                setDimension(next);
                setMetricIds((prev) => prev.filter((id) => (catalog.metrics || []).some((row) => row.id === id && (row.dimensions || []).includes(next))));
              }}>
                {Object.entries(DIMENSION_LABEL).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
              </select>
            </label>
            <label>
              Comparison
              <select value={comparison} onChange={(e) => setComparison(e.target.value)}>
                {Object.entries(COMPARISON_LABEL).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
              </select>
            </label>
            <label>
              Only this name
              <input value={filterValue} onChange={(e) => setFilterValue(e.target.value)} placeholder="Optional" />
            </label>
            <label>
              Extra column
              <select value={customColumn} onChange={(e) => setCustomColumn(e.target.value)}>
                <option value="">None</option>
                {(catalog.custom_columns || []).map((col) => (
                  <option key={col.entity + col.header} value={col.header}>{col.header}</option>
                ))}
              </select>
            </label>
          </div>
          <div className="builder-section">
            <h3>Metrics</h3>
            <div className="metric-picks">
              {metrics.map((row) => (
                <button
                  type="button"
                  key={row.id}
                  className={metricIds.includes(row.id) ? "metric-pick on" : "metric-pick"}
                  aria-pressed={metricIds.includes(row.id)}
                  onClick={() => toggleMetric(row.id)}
                >
                  {row.label}
                </button>
              ))}
            </div>
          </div>
          <div className="builder-options">
            <label className="check-line">
              <input type="checkbox" checked={schedule} onChange={(e) => setSchedule(e.target.checked)} />
              Include in the weekly report
            </label>
            {dimension === "product" ? (
              <label className="check-line">
                <input type="checkbox" checked={showPack} onChange={(e) => setShowPack(e.target.checked)} />
                Show pack size
              </label>
            ) : null}
          </div>
          <div className="builder-actions">
            <p className="muted">A draft stays hidden until you approve it.</p>
            <div className="analytics-foot-actions">
              <button type="button" className="secondary" onClick={previewReport} disabled={!metricIds.length}>Preview</button>
              <button type="button" onClick={saveReport} disabled={!metricIds.length}>Save draft</button>
            </div>
          </div>
        </div>
      ) : null}
      {err ? <p className="err">{err}</p> : null}
      {msg ? <p className="ok analytics-flash">{msg}</p> : null}
      {preview ? (
        <div className="card table-card list-panel analytics-table">
          <div className="table-card-head">
            <h3>Preview</h3>
            <span className="muted">{COMPARISON_LABEL[preview.comparison] || ""}</span>
          </div>
          <div className="table-wrap">
            <table className="dense list-table compact">
              <thead>
                <tr>
                  <th>{DIMENSION_LABEL[preview.dimension] || "Name"}</th>
                  {(preview.metrics || []).map((metric) => <th key={metric.id} className="num">{metric.label}</th>)}
                  {preview.show_pack_size ? <th className="num">Pack size</th> : null}
                  {preview.custom_column ? <th>{preview.custom_column}</th> : null}
                </tr>
              </thead>
              <tbody>
                {(preview.rows || []).length ? preview.rows.map((row) => (
                  <tr key={row.name}>
                    <td>{row.name}</td>
                    {(preview.metrics || []).map((metric) => {
                      const cell = row.cells?.[metric.id];
                      const quiet = !cell || cell.value == null || cell.value === "";
                      return <td key={metric.id} className={quiet ? "num muted" : "num"}>{cellLabel(metric.id, cell)}</td>;
                    })}
                    {preview.show_pack_size ? <td className="num">{row.pack_size === "" || row.pack_size == null ? "—" : row.pack_size}</td> : null}
                    {preview.custom_column ? <td>{row.custom || "—"}</td> : null}
                  </tr>
                )) : (
                  <tr><td className="muted" colSpan={1 + (preview.metrics || []).length}>{(preview.metrics || []).map((metric) => metric.reason).filter(Boolean).join(" ") || "No rows."}</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
      <div className="card table-card list-panel analytics-table">
        <div className="table-card-head"><h3>Saved reports</h3></div>
        <div className="table-wrap">
          <table className="dense list-table compact">
            <thead>
              <tr>
                <th>Name</th>
                <th>Grouping</th>
                <th>Comparison</th>
                <th>Status</th>
                <th>Owner</th>
                <th className="num">Action</th>
              </tr>
            </thead>
            <tbody>
              {reports.length ? reports.map((row) => (
                <tr key={row.id}>
                  <td>{row.name}{row.schedule ? <span className="pill credit builder-weekly">Weekly</span> : null}</td>
                  <td>{DIMENSION_LABEL[row.dimension] || row.dimension}</td>
                  <td>{COMPARISON_LABEL[row.comparison] || row.comparison}</td>
                  <td><span className={"pill " + (row.status === "approved" ? "credit" : "warn")}>{row.status === "approved" ? "Approved" : "Draft"}</span></td>
                  <td>{row.owner}</td>
                  <td className="num">
                    {manage && row.status !== "approved" ? (
                      <button type="button" className="secondary analytics-assign" onClick={() => approve(row.id)}>Approve</button>
                    ) : null}
                    {row.status === "approved" ? (
                      <button type="button" className="secondary analytics-assign" onClick={() => api.downloadSavedReport(row.id, { report_date: run?.report_date || "", run: run?.id || "" }).catch((e) => setErr(e.message || "Could not download"))}>Download</button>
                    ) : null}
                  </td>
                </tr>
              )) : (
                <tr><td className="muted" colSpan={6}>No saved reports yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
