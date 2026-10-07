import { useEffect, useRef, useState } from "react";
import { ChartBox } from "./Charts";
import { EmptyCard } from "./FilterBar";
import SnapshotPicker from "./SnapshotPicker";
import { api } from "./api";
import ExplainFigure from "./ExplainFigure";
import { hashSet, initials, money } from "./format";
import { CHART, can } from "./theme";

function prettyStamp(value) {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function greeting() {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

function qty(n) {
  if (n === null || n === undefined || n === "") return "—";
  const v = Number(n);
  if (!Number.isFinite(v)) return "—";
  return v.toLocaleString(undefined, { maximumFractionDigits: 2, minimumFractionDigits: 0 });
}

function pct(n) {
  if (n === null || n === undefined || n === "") return "—";
  const v = Number(n);
  if (!Number.isFinite(v)) return "—";
  return v.toLocaleString(undefined, { maximumFractionDigits: 1, minimumFractionDigits: 0 }) + "%";
}

function daysLabel(n) {
  if (n === null || n === undefined || n === "") return "—";
  const v = Number(n);
  if (!Number.isFinite(v)) return "—";
  return v.toLocaleString(undefined, { maximumFractionDigits: 1, minimumFractionDigits: 0 });
}

function kpiMap(rows) {
  const out = {};
  (rows || []).forEach((row) => {
    out[row.id] = row.value;
    if (row.unavailable) out[row.id + "_unavailable"] = row.reason || "Unavailable";
  });
  return out;
}

function num(value) {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value === "number" && Number.isFinite(value)) return value;
  const n = Number(String(value).replace(/[,₹\s]/g, ""));
  return Number.isFinite(n) ? n : null;
}

function pairStats(sales, collection) {
  const salesN = num(sales);
  const collN = num(collection);
  if (salesN == null && collN == null) return null;
  const s = salesN == null ? 0 : salesN;
  const c = collN == null ? 0 : collN;
  return {
    sales: s,
    collection: c,
    gap: Math.round((s - c) * 100) / 100,
    rate: s ? Math.round((c / s) * 1000) / 10 : null,
  };
}

function nearlyEqual(a, b) {
  const x = num(a);
  const y = num(b);
  if (x == null || y == null) return false;
  return Math.abs(x - y) < 0.05;
}

function customerPill(status) {
  if (status === "urgent") return "err";
  if (status === "followup") return "warn";
  if (status === "credit") return "credit";
  return "ok";
}

function stockPill(status) {
  if (status === "low") return "err";
  if (status === "soon" || status === "watch" || status === "excess") return "warn";
  if (status === "stopped") return "stopped";
  return "";
}

function hasKey(obj, key) {
  return Object.prototype.hasOwnProperty.call(obj || {}, key);
}

function totalHint(source) {
  if (source === "fiscal") return "all years";
  if (source === "imported") return "imported to date";
  return "all years";
}

function PeriodRow({ label, hint, sales, collection, salesExplain, collectionExplain, gapExplain }) {
  const stats = pairStats(sales, collection);
  if (!stats) return null;
  const max = Math.max(stats.sales, stats.collection, 1);
  const over = stats.gap < 0;
  return (
    <div className="dash-period">
      <div className="dash-period-name">{label}{hint ? <span className="quiet"> · {hint}</span> : null}</div>
      <div
        className="owe-bar dash-collect-bar"
        title={label + " collection against sales"}
        style={{ "--coll": String(stats.collection / max), "--gap": String(Math.max(0, stats.gap) / max) }}
      >
        <i className="coll" />
        <i className="gap" />
      </div>
      <div className="dash-period-nums">
        <div>
          <div className="label">Sales</div>
          <div className="value sales">{money(stats.sales)}</div>
        </div>
        <div>
          <div className="label">Collection</div>
          <div className="value collection">{money(stats.collection)}</div>
        </div>
        <div>
          <div className="label">{over ? "Over" : "Gap"}</div>
          <div className={"value" + (over ? " sales" : "")}>{money(Math.abs(stats.gap))}</div>
        </div>
        <div>
          <div className="label">Collected</div>
          <div className="value">{stats.rate == null ? "—" : stats.rate + "%"}</div>
        </div>
      </div>
      {salesExplain || collectionExplain || gapExplain ? (
        <div className="row gap">
          <ExplainFigure explanation={salesExplain} label="Explain sales" />
          <ExplainFigure explanation={collectionExplain} label="Explain collection" />
          <ExplainFigure explanation={gapExplain} label="Explain gap" />
        </div>
      ) : null}
    </div>
  );
}

function Tile({ label, value, tone, onClick }) {
  return (
    <button type="button" className={"dash-tile" + (tone ? " " + tone : "")} onClick={onClick}>
      <div className="label">{label}</div>
      <div className="value">{value}</div>
    </button>
  );
}

function CustomerTable({ customers, onAll }) {
  return (
    <div className="card table-card list-panel">
      <div className="table-card-head">
        <h3>Customers needing attention</h3>
        <button type="button" className="linkish" onClick={onAll}>All</button>
      </div>
      {customers.top?.length ? (
        <table className="dense list-table compact">
          <thead>
            <tr>
              <th>Customer</th>
              <th className="hide-narrow">Rep</th>
              <th className="hide-narrow">Last sale</th>
              <th>Status</th>
              <th className="num">Due</th>
            </tr>
          </thead>
          <tbody>
            {customers.top.map((c) => (
              <tr key={c.uk} className="click-row" onClick={() => hashSet("customer/" + encodeURIComponent(c.uk))}>
                <td>
                  <div className="name-cell">
                    <span className="avatar sm">{initials(c.name)}</span>
                    <span className="clip" title={c.name}><strong>{c.name}</strong></span>
                  </div>
                </td>
                <td className="clip hide-narrow">{c.salesperson || "—"}</td>
                <td className="quiet hide-narrow">{c.last_sale_label || "—"}</td>
                <td><span className={"pill " + customerPill(c.status)}>{c.status_label || "On track"}</span></td>
                <td className={"num amount" + (c.credit ? " credit" : "")}>{c.credit ? money(Math.abs(c.due)) : money(c.due)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="muted">No urgent or follow-up customers.</p>
      )}
    </div>
  );
}

function StockTable({ stock, onAll }) {
  return (
    <div className="card table-card list-panel">
      <div className="table-card-head">
        <h3>Low stock</h3>
        <button type="button" className="linkish" onClick={onAll}>All</button>
      </div>
      {stock.top?.length ? (
        <table className="dense list-table compact">
          <thead>
            <tr>
              <th>Item</th>
              <th>Status</th>
              <th className="num">Qty</th>
              <th className="num">Buy</th>
            </tr>
          </thead>
          <tbody>
            {stock.top.map((item) => (
              <tr key={item.uk} className="click-row" onClick={() => hashSet("item/" + encodeURIComponent(item.uk))}>
                <td>
                  <div className="name-cell">
                    <span className="avatar sm">{initials(item.name)}</span>
                    <span className="clip" title={item.name}><strong>{item.name}</strong></span>
                  </div>
                </td>
                <td><span className={"pill " + stockPill(item.status)}>{item.status_label || "On track"}</span></td>
                <td className="num">{qty(item.qty)}</td>
                <td className="num">{item.buy_qty ? qty(item.buy_qty) : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="muted">No items below minimum hold.</p>
      )}
    </div>
  );
}

export default function DashboardPage({ user, run, runs = [], busy = false, onSelectRun, onGo }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);
  const snapshotId = run?.status === "succeeded" ? run.id : "";
  const snapshotRef = useRef(snapshotId);
  snapshotRef.current = snapshotId;

  useEffect(() => {
    if (!user) return undefined;
    let cancelled = false;
    setLoading(true);
    const initial = snapshotRef.current;
    api.dashboard(initial ? { run: initial } : {})
      .then((next) => {
        if (cancelled) return;
        setData(next);
        setErr("");
      })
      .catch((e) => {
        if (!cancelled) setErr(e.message || "Could not load dashboard.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [user]);

  useEffect(() => {
    if (!user || !snapshotId || !data?.run?.id) return undefined;
    if (String(data.run.id) === String(snapshotId)) return undefined;
    let cancelled = false;
    setLoading(true);
    api.dashboard({ run: snapshotId })
      .then((next) => {
        if (cancelled) return;
        setData(next);
        setErr("");
      })
      .catch((e) => {
        if (!cancelled) setErr(e.message || "Could not load dashboard.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [user, snapshotId, data?.run?.id]);

  function openList(hash, tab, sub) {
    onGo(tab, sub);
    hashSet(hash);
  }

  if (loading && !data) return <EmptyCard title="Loading dashboard" copy="Pulling the latest numbers." />;
  if (err && !data) return <EmptyCard title="Could not load dashboard" copy={err} />;

  const hasData = Boolean(data?.has_data);
  const canImport = can(user, "__import__");
  const canCreate = can(user, "reports.create");
  const canCustomers = can(user, "customer.view");
  const canPerformance = can(user, "reports.view.performance");
  const canStock = can(user, "stock.view");
  const canSales = can(user, "sales.view");
  const canIssues = can(user, "reports.view.issues");
  const canProfit = can(user, "reports.view.profit");
  const kpis = canPerformance && hasKey(data, "kpis") ? kpiMap(data.kpis) : {};
  const explanations = data?.explanations || {};
  const customers = canCustomers && hasKey(data, "customers") ? data.customers : null;
  const stock = canStock && hasKey(data, "stock") ? data.stock : null;
  const invoices = canSales && hasKey(data, "invoices") ? data.invoices : null;
  const issues = canIssues && hasKey(data, "issues") ? (data.issues?.count || 0) : 0;
  const exceptions = Array.isArray(data?.exceptions) ? data.exceptions : [];
  const profit = canProfit && hasKey(data, "profit") ? data.profit : null;
  const profitKpis = profit ? kpiMap(profit.kpis) : {};
  const chart = canPerformance && hasKey(data, "chart") ? (data.chart || []).slice(0, 5) : [];
  const chartGroups = canPerformance && hasKey(data, "chart_groups") ? (data.chart_groups || []).slice(0, 6) : [];
  const chartGroupsMtd = canPerformance && hasKey(data, "chart_groups_mtd") ? (data.chart_groups_mtd || []).slice(0, 6) : [];
  const chartMonthly = canPerformance && hasKey(data, "chart_monthly") ? (data.chart_monthly || []) : [];
  const chartAging = canPerformance && hasKey(data, "chart_aging") ? (data.chart_aging || []) : [];
  const chartRate = canPerformance && hasKey(data, "chart_rate") ? (data.chart_rate || []) : [];
  const chartDue = canCustomers && hasKey(data, "chart_due") ? (data.chart_due || []) : [];
  const chartExpense = profit?.chart?.length ? profit.chart.slice(0, 6) : [];
  const chartStatus = customers?.counts
    ? [
        { name: "Urgent", count: customers.counts.urgent || 0 },
        { name: "Follow-up", count: customers.counts.followup || 0 },
        { name: "Advance", count: customers.counts.credit || 0 },
        { name: "On track", count: customers.counts.ontrack || 0 },
      ].filter((row) => row.count > 0)
    : [];
  const importNewer = Boolean(data?.import_newer);
  const reportDate = data?.run?.report_date || data?.freshness?.report_date;
  const fy = data?.run?.fy_label || data?.freshness?.fy_label;
  const uploaded = prettyStamp(data?.freshness?.last_upload_at);
  const snapLabel = reportDate
    ? (fy ? reportDate + " · " + fy : reportDate)
    : "";
  const urgent = customers?.counts?.urgent || 0;
  const followup = customers?.counts?.followup || 0;
  const credit = customers?.counts?.credit || 0;
  const due = customers?.counts?.due_total || 0;
  const low = stock?.low_count || 0;
  const soon = stock?.soon_count || 0;
  const buyQty = stock?.buy_qty_sum || 0;
  const buyValue = stock?.buy_value_sum || 0;
  const mtdStats = pairStats(kpis.mtd_sales, kpis.mtd_collection);
  const hasOfficial = Boolean(
    mtdStats
    || pairStats(kpis.d15_sales, kpis.d15_collection)
    || pairStats(kpis.ytd_sales, kpis.ytd_collection)
    || pairStats(kpis.total_sales, kpis.total_collection),
  );
  const showTotal = kpis.total_sales != null || kpis.total_collection != null;
  const totalSameAsYtd = showTotal
    && nearlyEqual(kpis.total_sales, kpis.ytd_sales)
    && nearlyEqual(kpis.total_collection, kpis.ytd_collection);
  const showOfficialHero = hasData && hasOfficial;
  const showDueHero = hasData && Boolean(customers) && !showOfficialHero;
  const showStockHero = hasData && Boolean(stock) && !showOfficialHero && !showDueHero;
  const showCustomerTiles = hasData && Boolean(customers);
  const showStockTiles = hasData && Boolean(stock) && (showStockHero || low || soon || buyQty || buyValue);
  const showStockList = hasData && Boolean(stock) && (showStockHero || Boolean(stock.top?.length));
  const arUnavailable = kpis.ar_balance_unavailable || kpis.dso_unavailable || "";
  const stockUnavailable = stock?.cover?.status === "unavailable" || stock?.slow?.status === "unavailable";
  const showOfficialExtras = hasData && (
    kpis.ar_balance != null || kpis.due_0_15 != null || kpis.due_90 != null || arUnavailable || stockUnavailable
    || kpis.overdue_30 != null || kpis.overdue_15 != null || kpis.new_credit != null
    || kpis.dso != null || kpis.top_rep_share != null || kpis.mom_sales_pct != null
    || kpis.mom_collection_pct != null || kpis.mtd_gap_pct != null || kpis.active_customers_mtd != null
    || kpis.inactive_mtd != null || kpis.collection_followups != null
    || kpis.invoice_mtd_count != null || kpis.invoice_mtd_avg != null
    || profitKpis.expense_mtd != null || profitKpis.expense_ytd != null
    || profitKpis.profit_mtd != null || profitKpis.profit_ytd != null
    || profitKpis.margin_mtd_pct != null || profitKpis.margin_ytd_pct != null
  );
  const showSections = showOfficialHero && (showCustomerTiles || showStockTiles || showOfficialExtras);
  const hasCharts = Boolean(
    chartMonthly.length || chart.length || chartGroups.length || chartGroupsMtd.length
    || chartAging.length || chartRate.length || chartStatus.length || chartExpense.length || chartDue.length,
  );
  const hasLists = Boolean(customers || showStockList);
  const actions = [];
  if (!hasData && canImport) {
    actions.push({ tab: "data", sub: "import", label: "Import files" });
  } else if (hasData && canCreate && (importNewer || !hasOfficial)) {
    actions.push({ tab: "reports", sub: "create", label: "Create reports" });
  }

  return (
    <div className="workspace-page">
      <div className="page-head">
        <div className="page-head-copy">
          <h2>{greeting()}, {user.username}</h2>
          <p className="muted">{user.role}{snapLabel ? " · snapshot " + snapLabel : ""}</p>
        </div>
        <div className="dash-head-right">
          {runs.length && onSelectRun ? (
            <SnapshotPicker
              runs={runs}
              currentId={snapshotId}
              busy={busy}
              onSelect={onSelectRun}
            />
          ) : null}
          <div className="dash-pills">
            {canPerformance ? (
              reportDate
                ? <span className="pill ok">Snapshot {reportDate}{fy ? " · " + fy : ""}</span>
                : <span className="pill">No official reports yet</span>
            ) : null}
            {uploaded ? <span className="pill">Last import {uploaded}</span> : null}
            {importNewer ? <span className="pill warn">Imports after snapshot</span> : null}
          </div>
        </div>
      </div>
      {actions.length ? (
        <div className="dash-actions">
          {actions.map((action) => (
            <button key={action.tab + action.sub} type="button" onClick={() => onGo(action.tab, action.sub)}>{action.label}</button>
          ))}
        </div>
      ) : null}
      {importNewer && hasOfficial ? (
        <div className="card dash-banner">
          <p>
            Data was imported after this snapshot. Official MTD / YTD stay as of {reportDate || "that run"}.{" "}
            {canCreate ? (
              <button type="button" className="linkish" onClick={() => onGo("reports", "create")}>Create reports</button>
            ) : (
              <span className="muted">Ask someone to Create reports for fresh official numbers.</span>
            )}
          </p>
        </div>
      ) : null}
      {issues || exceptions.length ? (
        <div className="card dash-banner">
          {exceptions.map((ex, i) => (
            <p
              key={(ex.metric_id || "ex") + i}
              className={ex.severity === "error" ? "err" : ex.severity === "warning" ? "warn" : "muted"}
            >
              {ex.severity ? ex.severity + ": " : ""}
              {ex.message}
              {ex.affected_reports?.length ? " — " + ex.affected_reports.join(", ") : ""}
            </p>
          ))}
          {issues ? (
            <p className="err">
              {issues} data {issues === 1 ? "issue" : "issues"} in the last run.{" "}
              {canIssues ? (
                <button type="button" className="linkish" onClick={() => onGo("reports", "issues")}>Open Data issues</button>
              ) : null}
            </p>
          ) : canIssues ? (
            <p>
              <button type="button" className="linkish" onClick={() => onGo("reports", "issues")}>Open Data issues</button>
            </p>
          ) : null}
        </div>
      ) : null}
      {!hasData ? (
        <EmptyCard
          title={canImport ? "Import Excel from AppSheet to get started" : "Nothing to show yet"}
          copy={canImport
            ? "Upload sales, receipts, outstanding, or stock. Official numbers appear after you create reports."
            : "Ask someone to import files and create reports."}
        />
      ) : null}
      {showOfficialHero ? (
        <div className="dash-hero">
          {showSections ? <div className="dash-section">Official snapshot{snapLabel ? " · " + snapLabel : ""}</div> : null}
          {data?.explanations_message ? <p className="muted">{data.explanations_message}</p> : null}
          <PeriodRow label="MTD" sales={kpis.mtd_sales} collection={kpis.mtd_collection} salesExplain={explanations.mtd_sales} collectionExplain={explanations.mtd_collection} gapExplain={explanations.mtd_gap} />
          {kpis.d15_sales != null || kpis.d15_collection != null ? (
            <PeriodRow label="15 days" sales={kpis.d15_sales} collection={kpis.d15_collection} salesExplain={explanations.d15_sales} collectionExplain={explanations.d15_collection} gapExplain={explanations.d15_gap} />
          ) : null}
          {kpis.ytd_sales != null || kpis.ytd_collection != null ? (
            <PeriodRow label="YTD" hint={fy || ""} sales={kpis.ytd_sales} collection={kpis.ytd_collection} salesExplain={explanations.ytd_sales} collectionExplain={explanations.ytd_collection} gapExplain={explanations.ytd_gap} />
          ) : null}
          {showTotal ? (
            <PeriodRow
              label="Total"
              hint={totalSameAsYtd ? "same as YTD · " + totalHint(data?.total_source) : totalHint(data?.total_source)}
              sales={kpis.total_sales}
              collection={kpis.total_collection}
              salesExplain={explanations.total_sales}
              collectionExplain={explanations.total_collection}
              gapExplain={explanations.total_gap}
            />
          ) : null}
          {mtdStats && mtdStats.gap > 0 ? (
            <p className="dash-ytd">{money(mtdStats.gap)} still to collect this month · snapshot {reportDate || "last run"}</p>
          ) : (
            <p className="dash-ytd">{reportDate ? "Official numbers from snapshot · " + reportDate : "Official numbers from the selected snapshot"}</p>
          )}
        </div>
      ) : null}
      {showDueHero ? (
        <div className="dash-hero">
          <div className="label">Outstanding due</div>
          <div className="hero-num">{money(due)}</div>
          <p className="muted">{urgent} urgent · {followup} follow-up · live after last import</p>
        </div>
      ) : null}
      {showStockHero ? (
        <div className="dash-hero">
          <div className="label">Stock to refill</div>
          <div className="hero-num">{low}</div>
          <p className="muted">
            {soon} to buy this week
            {buyQty ? " · buy " + qty(buyQty) + " units" : ""}
            {" · live after last import"}
          </p>
        </div>
      ) : null}
      {hasData && (showCustomerTiles || showStockTiles || showOfficialExtras) ? (
        <div>
          {showSections ? (
            <div className="dash-section">
              {showOfficialExtras && !showCustomerTiles && !showStockTiles
                ? "From last report"
                : showOfficialExtras
                  ? "KPIs & attention"
                  : "Needs attention · live after last import"}
            </div>
          ) : null}
          <div className="kpis">
            {showOfficialExtras ? (
              <>
                {stock?.cover?.value != null || stock?.cover?.status === "eligible" ? (
                  <Tile
                    label="Stock cover"
                    value={stock.cover.value != null ? daysLabel(stock.cover.value) + " days" : (stock.cover.label || "No recent demand")}
                    onClick={() => onGo("reports", "stock-decisions")}
                  />
                ) : stock?.cover?.status === "unavailable" ? (
                  <Tile label="Stock cover" value="Unavailable" onClick={() => onGo("reports", "stock-decisions")} />
                ) : null}
                {stock?.slow?.value != null ? (
                  <Tile label="Slow stock" value={money(stock.slow.value)} onClick={() => onGo("reports", "stock-decisions")} />
                ) : stock?.slow?.status === "unavailable" ? (
                  <Tile label="Slow stock" value="Unavailable" onClick={() => onGo("reports", "stock-decisions")} />
                ) : null}
                {kpis.ar_balance != null || kpis.ar_balance_unavailable ? (
                  <Tile
                    label="AR balance"
                    value={kpis.ar_balance != null ? money(kpis.ar_balance) : "Unavailable"}
                    onClick={() => onGo("reports", "performance")}
                  />
                ) : null}
                {kpis.dso != null || kpis.dso_unavailable ? (
                  <Tile
                    label="DSO (days)"
                    value={kpis.dso != null ? daysLabel(kpis.dso) : "Unavailable"}
                    onClick={() => onGo("reports", "performance")}
                  />
                ) : null}
                {kpis.due_0_15 != null || kpis.due_0_15_unavailable ? (
                  <Tile
                    label="Due 0–15 days"
                    value={kpis.due_0_15 != null ? money(kpis.due_0_15) : "Unavailable"}
                    onClick={() => onGo("reports", "performance")}
                  />
                ) : null}
                {kpis.due_15_30 != null || kpis.due_15_30_unavailable ? (
                  <Tile
                    label="Due 15–30 days"
                    value={kpis.due_15_30 != null ? money(kpis.due_15_30) : "Unavailable"}
                    onClick={() => onGo("reports", "performance")}
                  />
                ) : null}
                {kpis.due_30_45 != null || kpis.due_30_45_unavailable ? (
                  <Tile
                    label="Due 30–45 days"
                    value={kpis.due_30_45 != null ? money(kpis.due_30_45) : "Unavailable"}
                    onClick={() => onGo("reports", "performance")}
                  />
                ) : null}
                {kpis.due_45_60 != null || kpis.due_45_60_unavailable ? (
                  <Tile
                    label="Due 45–60 days"
                    value={kpis.due_45_60 != null ? money(kpis.due_45_60) : "Unavailable"}
                    onClick={() => onGo("reports", "performance")}
                  />
                ) : null}
                {kpis.due_60_90 != null || kpis.due_60_90_unavailable ? (
                  <Tile
                    label="Due 60–90 days"
                    value={kpis.due_60_90 != null ? money(kpis.due_60_90) : "Unavailable"}
                    tone={kpis.due_60_90 ? "followup-hero" : ""}
                    onClick={() => onGo("reports", "performance")}
                  />
                ) : null}
                {kpis.due_90 != null || kpis.due_90_unavailable ? (
                  <Tile
                    label="Due 90+ days"
                    value={kpis.due_90 != null ? money(kpis.due_90) : "Unavailable"}
                    tone={kpis.due_90 ? "urgent-hero" : ""}
                    onClick={() => onGo("reports", "performance")}
                  />
                ) : null}
                {kpis.overdue_30 != null || kpis.overdue_30_unavailable ? (
                  <Tile
                    label="30+ days overdue"
                    value={kpis.overdue_30 != null ? money(kpis.overdue_30) : "Unavailable"}
                    tone={kpis.overdue_30 ? "urgent-hero" : ""}
                    onClick={() => onGo("reports", "followup")}
                  />
                ) : null}
                {kpis.overdue_15 != null || kpis.overdue_15_unavailable ? (
                  <Tile
                    label="15-day credit lapsed"
                    value={kpis.overdue_15 != null ? money(kpis.overdue_15) : "Unavailable"}
                    tone={kpis.overdue_15 ? "followup-hero" : ""}
                    onClick={() => onGo("reports", "followup")}
                  />
                ) : null}
                {kpis.new_credit != null ? (
                  <Tile label="New credit added" value={money(kpis.new_credit)} onClick={() => onGo("reports", "followup")} />
                ) : null}
                {kpis.mom_sales_pct != null ? (
                  <Tile
                    label="MoM sales"
                    value={pct(kpis.mom_sales_pct)}
                    tone={kpis.mom_sales_pct < 0 ? "urgent-hero" : ""}
                    onClick={() => onGo("reports", "monthly")}
                  />
                ) : null}
                {kpis.mom_collection_pct != null ? (
                  <Tile
                    label="MoM collection"
                    value={pct(kpis.mom_collection_pct)}
                    tone={kpis.mom_collection_pct < 0 ? "urgent-hero" : ""}
                    onClick={() => onGo("reports", "monthly")}
                  />
                ) : null}
                {kpis.mtd_gap_pct != null ? (
                  <Tile
                    label="MTD gap %"
                    value={pct(kpis.mtd_gap_pct)}
                    tone={kpis.mtd_gap_pct > 0 ? "followup-hero" : ""}
                    onClick={() => onGo("reports", "performance")}
                  />
                ) : null}
                {kpis.top_rep_share != null ? (
                  <Tile label="Top rep MTD share" value={pct(kpis.top_rep_share)} onClick={() => onGo("reports", "performance")} />
                ) : null}
                {kpis.active_customers_mtd != null ? (
                  <Tile label="Active customers MTD" value={String(kpis.active_customers_mtd)} onClick={() => onGo("customers", "customers")} />
                ) : null}
                {kpis.inactive_mtd != null ? (
                  <Tile
                    label="Inactive customers"
                    value={String(kpis.inactive_mtd)}
                    tone={kpis.inactive_mtd ? "followup-hero" : ""}
                    onClick={() => onGo("reports", "followup")}
                  />
                ) : null}
                {kpis.collection_followups != null ? (
                  <Tile
                    label="Collection follow-ups"
                    value={String(kpis.collection_followups)}
                    tone={kpis.collection_followups ? "urgent-hero" : ""}
                    onClick={() => onGo("reports", "followup")}
                  />
                ) : null}
                {kpis.invoice_mtd_count != null ? (
                  <Tile label="Invoices MTD" value={String(kpis.invoice_mtd_count)} onClick={() => onGo("sales", "sales")} />
                ) : null}
                {kpis.invoice_mtd_avg != null ? (
                  <Tile label="Avg invoice MTD" value={money(kpis.invoice_mtd_avg)} onClick={() => onGo("sales", "sales")} />
                ) : null}
                {profitKpis.profit_mtd != null ? (
                  <Tile label="Sales profit MTD" value={money(profitKpis.profit_mtd)} onClick={() => onGo("reports", "profit")} />
                ) : null}
                {profitKpis.profit_ytd != null ? (
                  <Tile label="Sales profit YTD" value={money(profitKpis.profit_ytd)} onClick={() => onGo("reports", "profit")} />
                ) : null}
                {profitKpis.margin_mtd_pct != null ? (
                  <Tile label="Gross margin MTD" value={pct(profitKpis.margin_mtd_pct)} onClick={() => onGo("reports", "profit")} />
                ) : null}
                {profitKpis.margin_ytd_pct != null ? (
                  <Tile label="Gross margin YTD" value={pct(profitKpis.margin_ytd_pct)} onClick={() => onGo("reports", "profit")} />
                ) : null}
                {profitKpis.expense_mtd != null ? (
                  <Tile label="Expense MTD" value={money(profitKpis.expense_mtd)} onClick={() => onGo("reports", "profit")} />
                ) : null}
                {profitKpis.expense_ytd != null ? (
                  <Tile label="Expense YTD" value={money(profitKpis.expense_ytd)} onClick={() => onGo("reports", "profit")} />
                ) : null}
              </>
            ) : null}
            {showCustomerTiles ? (
              <>
                <Tile label="Urgent customers" value={String(urgent)} tone={urgent ? "urgent-hero" : ""} onClick={() => openList("list/customers/" + encodeURIComponent("Urgent"), "customers", "customers")} />
                <Tile label="Follow-up" value={String(followup)} tone={followup ? "followup-hero" : ""} onClick={() => openList("list/customers/" + encodeURIComponent("Follow up"), "customers", "customers")} />
                <Tile
                  label="Due"
                  value={money(due)}
                  onClick={() => openList("list/customers/", "customers", "customers")}
                />
                {credit ? (
                  <Tile
                    label="Advance"
                    value={String(credit)}
                    tone="followup-hero"
                    onClick={() => openList("list/customers/" + encodeURIComponent("Advance"), "customers", "customers")}
                  />
                ) : null}
              </>
            ) : null}
            {showStockTiles ? (
              <>
                <Tile label="Below min" value={String(low)} tone={low ? "urgent-hero" : ""} onClick={() => openList("list/stock/" + encodeURIComponent("Below min"), "stock", "stock")} />
                <Tile label="Buy this week" value={String(soon)} tone={soon ? "followup-hero" : ""} onClick={() => openList("list/stock/" + encodeURIComponent("Buy this week"), "stock", "stock")} />
                {buyQty ? (
                  <Tile
                    label="Buy qty"
                    value={qty(buyQty)}
                    tone={buyQty ? "followup-hero" : ""}
                    onClick={() => openList("list/stock/" + encodeURIComponent("Below min"), "stock", "stock")}
                  />
                ) : null}
                {buyValue ? (
                  <Tile
                    label="Buy value"
                    value={money(buyValue)}
                    tone={buyValue ? "followup-hero" : ""}
                    onClick={() => openList("list/stock/" + encodeURIComponent("Below min"), "stock", "stock")}
                  />
                ) : null}
              </>
            ) : null}
          </div>
          {arUnavailable ? <p className="muted">{arUnavailable}</p> : null}
          {stock?.cover?.status === "unavailable" ? <p className="muted">{stock.cover.reason}</p> : null}
          {stock?.cover?.status === "eligible" && stock?.cover?.label ? <p className="muted">{stock.cover.label}</p> : null}
          {stock?.slow?.uncosted ? <p className="muted">{stock.slow.uncosted} slow item{stock.slow.uncosted === 1 ? "" : "s"} excluded — missing cost</p> : null}
          {stock?.slow?.status === "unavailable" && stock?.slow?.reason !== stock?.cover?.reason ? (
            <p className="muted">{stock.slow.reason}</p>
          ) : null}
          {explanations.ar_balance || explanations.stock_cover_days || explanations.slow_stock_value ? (
            <div className="row gap">
              <ExplainFigure explanation={explanations.ar_balance} label="Explain AR balance" />
              <ExplainFigure explanation={explanations.stock_cover_days} label="Explain stock cover" />
              <ExplainFigure explanation={explanations.slow_stock_value} label="Explain slow stock" />
            </div>
          ) : null}
        </div>
      ) : null}
      {hasData && hasCharts ? (
        <div className="dash-charts">
          {chartMonthly.length ? (
            <ChartBox
              compact
              title={"Monthly · " + (fy || "this year")}
              data={chartMonthly}
              bars={[
                { key: "sales", name: "Sales", fill: CHART.sales },
                { key: "collection", name: "Collection", fill: CHART.collection },
              ]}
            />
          ) : null}
          {chartRate.length ? (
            <ChartBox
              compact
              title="Collection rate by month"
              data={chartRate}
              lines={[{ key: "rate", name: "Collected %", fill: CHART.accent }]}
            />
          ) : null}
          {chart.length ? (
            <ChartBox
              compact
              title="MTD by person"
              data={chart}
              bars={[
                { key: "sales", name: "Sales", fill: CHART.sales },
                { key: "collection", name: "Collection", fill: CHART.collection },
              ]}
            />
          ) : null}
          {chartGroupsMtd.length ? (
            <ChartBox
              compact
              title="MTD by group"
              data={chartGroupsMtd}
              bars={[
                { key: "sales", name: "Sales", fill: CHART.sales },
                { key: "collection", name: "Collection", fill: CHART.collection },
              ]}
            />
          ) : null}
          {chartGroups.length ? (
            <ChartBox
              compact
              title="YTD by group"
              data={chartGroups}
              bars={[
                { key: "sales", name: "Sales", fill: CHART.sales },
                { key: "collection", name: "Collection", fill: CHART.collection },
              ]}
            />
          ) : null}
          {chartAging.length ? (
            <ChartBox
              compact
              title={chartAging[0]?.d0_15 != null ? "Due aging" : "Credit aging"}
              stacked
              data={chartAging}
              bars={
                chartAging[0]?.d0_15 != null
                  ? [
                      { key: "d0_15", name: "0–15", fill: CHART.agingNew || CHART.sales },
                      { key: "d15_30", name: "15–30", fill: CHART.aging15 || "#3d8f6a" },
                      { key: "d30_45", name: "30–45", fill: "#6a9e5a" },
                      { key: "d45_60", name: "45–60", fill: CHART.aging30 || "#c4a35a" },
                      { key: "d60_90", name: "60–90", fill: "#b45309" },
                      { key: "d90", name: "90+", fill: "#9f1239" },
                    ]
                  : [
                      { key: "new", name: "New credit", fill: CHART.agingNew },
                      { key: "d15", name: "15-day lapsed", fill: CHART.aging15 },
                      { key: "d30", name: "30+ overdue", fill: CHART.aging30 },
                    ]
              }
            />
          ) : null}
          {chartStatus.length ? (
            <ChartBox
              compact
              title="Customers by status"
              data={chartStatus}
              bars={[{ key: "count", name: "Customers", fill: CHART.accent }]}
            />
          ) : null}
          {chartDue.length ? (
            <ChartBox
              compact
              title="Top due balances"
              data={chartDue}
              bars={[{ key: "due", name: "Due", fill: CHART.due }]}
            />
          ) : null}
          {chartExpense.length ? (
            <ChartBox
              compact
              title="Expense by category (YTD)"
              data={chartExpense}
              bars={[{ key: "amount", name: "YTD", fill: CHART.accent }]}
            />
          ) : null}
        </div>
      ) : null}
      {hasData && hasLists ? (
        <div className="dash-main single">
          <div className="dash-stack">
            {customers ? (
              <CustomerTable customers={customers} onAll={() => onGo("customers", "customers")} />
            ) : null}
            {showStockList ? (
              <StockTable stock={stock} onAll={() => onGo("stock", "stock")} />
            ) : null}
          </div>
        </div>
      ) : null}
      {hasData && invoices && invoices.length ? (
        <div className="card table-card list-panel">
          <div className="table-card-head">
            <h3>Recent invoices</h3>
            <button type="button" className="linkish" onClick={() => onGo("sales", "sales")}>All</button>
          </div>
          <table className="dense list-table compact">
            <thead>
              <tr>
                <th>Date</th>
                <th>Invoice</th>
                <th>Party</th>
                <th className="num">Amount</th>
              </tr>
            </thead>
            <tbody>
              {invoices.slice(0, 3).map((inv) => (
                <tr key={inv.id} className="click-row" onClick={() => hashSet("invoice/" + encodeURIComponent(inv.id))}>
                  <td className="quiet">{inv.date_label || "—"}</td>
                  <td>{inv.invoice || "—"}</td>
                  <td className="clip">
                    {canCustomers && inv.customer_uk ? (
                      <button
                        type="button"
                        className="linkish"
                        onClick={(e) => { e.stopPropagation(); hashSet("customer/" + encodeURIComponent(inv.customer_uk)); }}
                      >
                        {inv.party || "Customer"}
                      </button>
                    ) : (inv.party || "—")}
                  </td>
                  <td className="num amount">{money(inv.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
