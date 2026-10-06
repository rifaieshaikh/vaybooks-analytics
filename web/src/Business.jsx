import { useEffect, useState } from "react";
import SectionTabs, { rememberedTab } from "./SectionTabs";
import { api } from "./api";
import { EmptyCard } from "./FilterBar";
import { hashSet, money } from "./format";
import SettlementsPanel from "./SettlementsPanel";
import SalesGapsPanel from "./SalesGapsPanel";

function prettyStamp(value) {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function pct(n) {
  if (n === null || n === undefined || n === "") return "—";
  const v = Number(n);
  if (!Number.isFinite(v)) return "—";
  return v.toLocaleString(undefined, { maximumFractionDigits: 1, minimumFractionDigits: 0 }) + "%";
}

function qty(n) {
  if (n === null || n === undefined || n === "") return "—";
  const v = Number(n);
  if (!Number.isFinite(v)) return "—";
  return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function flowText(flow, kind) {
  if (!flow || flow.value === null || flow.value === undefined) return "—";
  return kind === "pct" ? pct(flow.value) : money(flow.value);
}

function flowHint(flow, kind) {
  if (!flow) return "";
  const fmt = kind === "pct" ? pct : money;
  const bits = [];
  if (flow.prior !== null && flow.prior !== undefined) bits.push("Prior " + fmt(flow.prior));
  if (flow.prior_year !== null && flow.prior_year !== undefined) bits.push("Last year " + fmt(flow.prior_year));
  if (flow.target !== null && flow.target !== undefined) bits.push("Target " + fmt(flow.target));
  return bits.join(" · ");
}

function profitText(cell, kind) {
  if (!cell) return "—";
  if (cell.unavailable) return "Unavailable";
  if (cell.value === null || cell.value === undefined) return "—";
  return kind === "pct" ? pct(cell.value) : money(cell.value);
}

function ebitdaHint(profit) {
  if (!profit) return "";
  const fmt = (node) => {
    if (!node || node.unavailable || node.value === null || node.value === undefined) return "";
    return money(node.value);
  };
  const bits = [];
  const prior = fmt((profit.prior || {}).ebitda);
  const year = fmt((profit.prior_year || {}).ebitda);
  if (prior) bits.push("Prior EBITDA " + prior);
  if (year) bits.push("Last year " + year);
  return bits.join(" · ");
}

const PERIODS = [
  ["overall", "Overall"],
  ["fy", "This FY"],
  ["month", "This month"],
];

function PeriodCard({ label, period }) {
  if (!period?.sales) return null;
  const sales = period.sales;
  const collected = period.collection;
  const salesN = Number(sales?.value);
  const collN = Number(collected?.value);
  const max = Math.max(Number.isFinite(salesN) ? salesN : 0, Number.isFinite(collN) ? collN : 0, 1);
  const hint = flowHint(sales, "money");
  return (
    <article className="biz-period">
      <div className="dash-period-name">{label}</div>
      <div className="label">Sales</div>
      <div className="value sales">{flowText(sales, "money")}</div>
      {collected ? (
        <div
          className="owe-bar dash-collect-bar"
          title="Collection against sales"
          style={{
            "--coll": String((Number.isFinite(collN) ? collN : 0) / max),
            "--gap": String(Math.max(0, (Number.isFinite(salesN) ? salesN : 0) - (Number.isFinite(collN) ? collN : 0)) / max),
          }}
        >
          <i className="coll" />
          <i className="gap" />
        </div>
      ) : null}
      <div className="biz-metric"><span>Collected</span><strong className="collection">{flowText(collected, "money")}</strong></div>
      <div className="biz-metric"><span>Gap</span><strong>{flowText(period.gap, "money")}</strong></div>
      <div className="biz-metric"><span>Collection rate</span><strong>{flowText(period.rate, "pct")}</strong></div>
      {hint ? <p className="dash-ytd">{hint}</p> : null}
    </article>
  );
}

function cellReady(cell) {
  return Boolean(cell) && !cell.unavailable && cell.value !== null && cell.value !== undefined;
}

function explainGap(reason) {
  const text = String(reason || "");
  if (/missing item cost/i.test(text)) {
    return "Gross profit, margin, and EBITDA need a purchase price on every item sold. Some items are missing that price.";
  }
  if (/payments were not imported/i.test(text)) {
    return "Operating expenses and EBITDA need the payments file. It was not part of this snapshot.";
  }
  if (/not on the profit report|profit report was not created/i.test(text)) {
    return "This snapshot has no cost of items sold, so EBITDA cannot be calculated.";
  }
  return text;
}

function profitGaps(periods) {
  const reasons = [];
  PERIODS.forEach(([key]) => {
    const profit = periods[key]?.profit;
    if (!profit) return;
    ["ebitda", "gross_profit", "operating_expenses"].forEach((field) => {
      const reason = profit[field]?.unavailable ? profit[field].reason : "";
      if (reason && !reasons.includes(reason)) reasons.push(reason);
    });
  });
  return reasons;
}

function salesProfitHint(profit) {
  if (!profit) return "";
  const bits = [];
  const prior = (profit.prior || {}).sales_profit;
  const year = (profit.prior_year || {}).sales_profit;
  if (prior !== null && prior !== undefined) bits.push("Prior " + money(prior));
  if (year !== null && year !== undefined) bits.push("Last year " + money(year));
  return bits.join(" · ");
}

function Metric({ label, children }) {
  if (children === null || children === undefined || children === "") return null;
  return (
    <div className="biz-metric">
      <span>{label}</span>
      <strong>{children}</strong>
    </div>
  );
}

function ProfitCard({ label, profit }) {
  if (!profit) return null;
  const ebitdaReady = cellReady(profit.ebitda);
  const prior = ebitdaReady ? ebitdaHint(profit) : salesProfitHint(profit);
  return (
    <article className="biz-period">
      <div className="dash-period-name">{label}</div>
      <div className="label">{ebitdaReady ? "EBITDA" : "Sales profit"}</div>
      <div className="value">
        {ebitdaReady ? profitText(profit.ebitda, "money") : (profit.sales_profit != null ? money(profit.sales_profit) : "—")}
      </div>
      <Metric label="Sale before tax">{profit.sale_before_tax != null ? money(profit.sale_before_tax) : null}</Metric>
      {cellReady(profit.gross_profit) ? <Metric label="Gross profit">{profitText(profit.gross_profit, "money")}</Metric> : null}
      {cellReady(profit.operating_expenses) ? <Metric label="Operating expenses">{profitText(profit.operating_expenses, "money")}</Metric> : null}
      {cellReady(profit.gross_margin_pct) ? <Metric label="Gross margin">{profitText(profit.gross_margin_pct, "pct")}</Metric> : null}
      {cellReady(profit.expense_ratio_pct) ? <Metric label="Expense ratio">{profitText(profit.expense_ratio_pct, "pct")}</Metric> : null}
      {ebitdaReady ? <Metric label="Sales profit">{profit.sales_profit != null ? money(profit.sales_profit) : null}</Metric> : null}
      {prior ? <p className="dash-ytd">{prior}</p> : null}
    </article>
  );
}

function shareOf(value, total) {
  const base = Number(total) || 0;
  if (base <= 0) return "—";
  const pct = ((Number(value) || 0) / base) * 100;
  return pct.toLocaleString(undefined, { maximumFractionDigits: 1, minimumFractionDigits: 0 }) + "%";
}

function SettlementStory({ data }) {
  const settlements = data?.settlements;
  if (!settlements) {
    return (
      <EmptyCard
        title="Settlements are not on this snapshot"
        copy="Create the report again. How receipts were applied is saved with that report."
      />
    );
  }
  const overall = Number(settlements.overall?.total) || 0;
  const months = (settlements.months || []).filter((row) => Number(row.total) > 0);
  const first = months[months.length - 1];
  const last = months[0];
  const span = first && last && first.key !== last.key ? first.label + " through " + last.label : (last?.label || data?.as_of_label || "");
  return (
    <>
      <SettlementsPanel
        showParty
        detail={{
          uk: "business",
          settlements,
          aging_bands: settlements.aging_bands,
          collection_buckets: settlements.overall?.buckets || {},
        }}
      />
      {months.length ? (
        <div className="card table-card">
          <h3>Settled over the period</h3>
          <p className="muted">
            Receipts applied to invoices{span ? ", " + span : ""}.
            {data?.as_of_label ? " Through " + data.as_of_label + "." : ""}
          </p>
          <div className="table-wrap">
            <table className="dense list-table compact">
              <thead>
                <tr>
                  <th>Month</th>
                  <th className="num">Settled</th>
                  <th className="num">Share of all settled</th>
                </tr>
              </thead>
              <tbody>
                {months.map((row) => (
                  <tr key={row.key}>
                    <td>{row.label}</td>
                    <td className="num">{money(row.total || 0)}</td>
                    <td className="num">{shareOf(row.total, overall)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <p className="muted">No receipts were applied to invoices in this snapshot.</p>
      )}
    </>
  );
}

function MixTable({ title, rows, columns, onOpen }) {
  if (!rows?.length) return null;
  return (
    <div className="card table-card">
      <h3>{title}</h3>
      <table className="dense list-table compact">
        <thead>
          <tr>
            {columns.map((col) => <th key={col.id} className={col.num ? "num" : ""}>{col.label}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr
              key={(row.uk || row.name || "row") + "-" + index}
              className={onOpen ? "click-row" : ""}
              onClick={onOpen ? () => onOpen(row) : undefined}
            >
              {columns.map((col) => (
                <td key={col.id} className={col.num ? "num" : ""}>{col.get(row)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function BusinessPage({ runId, onGo }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);
  const [pdfBusy, setPdfBusy] = useState(false);
  const [tab, setTab] = useState(() => rememberedTab("business", "overview", ["overview", "quantity", "sales", "settlements", "breakdown"]));
  const [sections, setSections] = useState({});

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setSections({});
    api.business(runId ? { run: runId } : {})
      .then((next) => {
        if (!cancelled) {
          setData(next);
          setErr("");
        }
      })
      .catch((e) => {
        if (!cancelled) setErr(e.message || "Could not load the Business view.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [runId]);

  useEffect(() => {
    if (!data || !runId) return undefined;
    const want = tab === "settlements" && data.settlements_separate && !Object.prototype.hasOwnProperty.call(sections, "settlements")
      ? "settlements"
      : tab === "sales" && data.sales_gaps_separate && !Object.prototype.hasOwnProperty.call(sections, "sales_gaps")
        ? "sales_gaps"
        : "";
    if (!want) return undefined;
    let cancelled = false;
    api.business({ run: runId, section: want })
      .then((part) => {
        if (cancelled) return;
        setSections((prev) => ({ ...prev, [want]: part[want] || null }));
      })
      .catch((e) => {
        if (cancelled) return;
        setSections((prev) => ({ ...prev, [want]: null }));
        setErr(e.message || "Could not load this section.");
      });
    return () => { cancelled = true; };
  }, [tab, runId, data, sections]);

  useEffect(() => {
    setTab("overview");
  }, [runId]);

  async function onPdf() {
    setPdfBusy(true);
    try {
      await api.businessPdf(runId ? { run: runId } : {});
    } catch (e) {
      setErr(e.message || "Could not prepare the brief.");
    } finally {
      setPdfBusy(false);
    }
  }

  if (loading && !data) return <EmptyCard title="Loading Business" copy="Reading the saved 360 view." />;
  if (err && !data) return <EmptyCard title="Could not load Business" copy={err} />;
  if (data?.empty) {
    return <EmptyCard title="Business view is not on this snapshot" copy={data.message || "Create the report again."} />;
  }

  const view = {
    ...data,
    settlements: data.settlements || sections.settlements,
    sales_gaps: data.sales_gaps || sections.sales_gaps,
  };
  const receivables = view.receivables;
  const stock = view.stock;
  const mix = view.mix || {};
  const movement = view.movement || {};
  const counts = movement.counts || {};
  const uploaded = prettyStamp(data?.last_upload_at);
  const periods = data?.periods || {};
  const showSales = PERIODS.some(([key]) => periods[key]?.sales);
  const showProfit = PERIODS.some(([key]) => periods[key]?.profit);
  const gaps = showProfit ? profitGaps(periods) : [];
  const gapAction = (data?.exceptions || []).find((row) => row.id === "missing_cost")
    || (data?.exceptions || []).find((row) => row.id === "unmapped");
  const hasLists = Boolean(
    mix.groups?.length || mix.reps?.length || mix.expenses?.length || mix.invoices?.length
    || mix.buy?.length || movement.customers?.length || movement.products?.length
  );
  const settlementsPending = Boolean(data.settlements_separate && !view.settlements && !Object.prototype.hasOwnProperty.call(sections, "settlements"));
  const salesPending = Boolean(data.sales_gaps_separate && !view.sales_gaps && !Object.prototype.hasOwnProperty.call(sections, "sales_gaps"));
  const tabs = [["overview", "Overview"]];
  if (showSales) tabs.push(["quantity", "Quantity"]);
  tabs.push(["sales", "Sales"]);
  if (view.settlements || data.settlements_separate) tabs.push(["settlements", "Settlements"]);
  if (hasLists) tabs.push(["breakdown", "Breakdown"]);
  const active = tabs.some(([id]) => id === tab) ? tab : "overview";

  return (
    <div className="workspace-page">
      <div className="page-head">
        <div className="page-head-copy">
          <h2>{data?.name || "Business"}</h2>
          <p className="muted">Company profile for this snapshot.</p>
        </div>
        <div className="dash-head-right">
          <div className="dash-pills">
            {data?.as_of_label ? <span className="pill ok">As of {data.as_of_label}</span> : null}
            {data?.fy_label ? <span className="pill">{data.fy_label}</span> : null}
            {uploaded ? <span className="pill">Last import {uploaded}</span> : null}
            {data?.import_newer ? <span className="pill warn">Imports after snapshot</span> : null}
          </div>
          <button type="button" onClick={onPdf} disabled={pdfBusy}>{pdfBusy ? "Preparing…" : "Share"}</button>
        </div>
      </div>
      {data?.import_newer ? (
        <div className="card dash-banner">
          <p>Data was imported after this snapshot. These figures stay as of {data.as_of_label || "the report date"}.</p>
        </div>
      ) : null}
      {err ? <p className="err">{err}</p> : null}
      {tabs.length > 1 ? (
        <SectionTabs
          label="Business sections"
          storageKey="business"
          sticky
          value={active}
          onChange={setTab}
          tabs={tabs.map(([id, label]) => ({ id, label }))}
        />
      ) : null}
      <div className="tab-panel">
      {active === "overview" ? (
        <>
      {showSales ? (
        <>
          <div className="dash-section">Sales and collections</div>
          <div className="biz-periods">
            {PERIODS.map(([key, label]) => (
              <PeriodCard key={key} label={label} period={periods[key]} />
            ))}
          </div>
        </>
      ) : null}
      {showProfit ? (
        <>
          <div className="dash-section">Profit</div>
          {gaps.length ? (
            <div className="card dash-banner biz-alerts">
              {gaps.map((reason) => <p key={reason}>{explainGap(reason)}</p>)}
              {gapAction ? (
                <p>
                  <button type="button" className="linkish" onClick={() => gapAction.nav && onGo && onGo(gapAction.nav[0], gapAction.nav[1])}>
                    {gapAction.label}
                  </button>
                  {" "}
                  {gapAction.value}
                </p>
              ) : /payments were not imported/i.test(gaps.join(" ")) ? (
                <p>
                  <button type="button" className="linkish" onClick={() => onGo && onGo("data", "import")}>Import payments</button>
                </p>
              ) : null}
            </div>
          ) : null}
          <div className="biz-periods">
            {PERIODS.map(([key, label]) => (
              <ProfitCard key={key} label={label} profit={periods[key]?.profit} />
            ))}
          </div>
          {!gaps.length && data?.cost_note ? <p className="muted biz-note">{data.cost_note}</p> : null}
        </>
      ) : null}
      {receivables || stock ? <div className="dash-section">As of the report date</div> : null}
      {receivables || stock ? (
        <div className="kpis">
          {receivables ? (
            <>
              <button type="button" className="dash-tile" onClick={() => onGo && onGo("customers", "customers")}>
                <div className="label">Outstanding{receivables.ar_balance?.target != null ? " · target " + money(receivables.ar_balance.target) : ""}</div>
                <div className="value">{cellReady(receivables.ar_balance) ? profitText(receivables.ar_balance, "money") : "—"}</div>
                {receivables.ar_balance?.unavailable && receivables.ar_balance.reason ? <div className="muted">{receivables.ar_balance.reason}</div> : null}
              </button>
              <button type="button" className="dash-tile" onClick={() => onGo && onGo("customers", "customers")}>
                <div className="label">Overdue 30+</div>
                <div className="value">{cellReady(receivables.overdue_30) ? profitText(receivables.overdue_30, "money") : "—"}</div>
                {receivables.overdue_30?.unavailable && receivables.overdue_30.reason ? <div className="muted">{receivables.overdue_30.reason}</div> : null}
              </button>
              <button type="button" className="dash-tile" onClick={() => onGo && onGo("customers", "customers")}>
                <div className="label">DSO (days)</div>
                <div className="value">{receivables.dso?.unavailable ? "—" : (receivables.dso?.value ?? "—")}</div>
                {receivables.dso?.unavailable && receivables.dso.reason ? <div className="muted">{receivables.dso.reason}</div> : null}
              </button>
              <button type="button" className="dash-tile" onClick={() => onGo && onGo("customers", "customers")}>
                <div className="label">Customers</div>
                <div className="value">{receivables.urgent || 0} urgent</div>
                <div className="muted">{receivables.followup || 0} follow-up</div>
              </button>
            </>
          ) : null}
          {stock ? (
            <>
              <button type="button" className="dash-tile" onClick={() => onGo && onGo("customers", "items")}>
                <div className="label">Stock cover</div>
                <div className="value">{stock.cover_days?.unavailable ? "—" : (stock.cover_days?.value ?? "—")}</div>
                {stock.cover_days?.unavailable && stock.cover_days.reason ? <div className="muted">{stock.cover_days.reason}</div> : null}
              </button>
              <button type="button" className="dash-tile" onClick={() => onGo && onGo("customers", "items")}>
                <div className="label">Slow stock</div>
                <div className="value">{cellReady(stock.slow_value) ? profitText(stock.slow_value, "money") : "—"}</div>
                {stock.slow_value?.unavailable && stock.slow_value.reason ? <div className="muted">{stock.slow_value.reason}</div> : null}
              </button>
              <button type="button" className="dash-tile" onClick={() => onGo && onGo("customers", "items")}>
                <div className="label">Below minimum</div>
                <div className="value">{stock.low_count || 0}</div>
              </button>
              <button type="button" className="dash-tile" onClick={() => onGo && onGo("customers", "items")}>
                <div className="label">Suggested buy</div>
                <div className="value">{money(stock.buy_value_sum || 0)}</div>
              </button>
            </>
          ) : null}
        </div>
      ) : null}
      {receivables?.aging?.length ? (
        <div className="card biz-aging">
          <div className="dash-section">Outstanding by age</div>
          <div className="biz-age-row">
            {receivables.aging.map((band) => (
              <div key={band.id}>
                <span className="muted">{band.label}</span>
                <strong>{money(band.value || 0)}</strong>
              </div>
            ))}
          </div>
        </div>
      ) : null}
      {counts.new || counts.repeat || counts.inactive || counts.reactivated ? (
        <>
        <div className="dash-section">Customers this month</div>
        <div className="kpis">
          <div className="kpi"><div className="label">New customers</div><div className="value">{counts.new || 0}</div></div>
          <div className="kpi"><div className="label">Repeat</div><div className="value">{counts.repeat || 0}</div></div>
          <div className="kpi"><div className="label">Inactive</div><div className="value">{counts.inactive || 0}</div></div>
          <div className="kpi"><div className="label">Returned</div><div className="value">{counts.reactivated || 0}</div></div>
        </div>
        </>
      ) : null}
        </>
      ) : null}
      {active === "settlements" ? (
        settlementsPending
          ? <EmptyCard title="Loading settlements" copy="Reading receipts applied to invoices." />
          : <SettlementStory data={view} />
      ) : null}
      {active === "quantity" ? (
        data?.qty_available ? (
          <div className="biz-periods">
            {PERIODS.map(([key, label]) => (
              <article className="biz-period" key={key}>
                <div className="dash-period-name">{label}</div>
                <div className="label">Quantity</div>
                <div className="value">{qty(periods[key]?.qty)}</div>
              </article>
            ))}
          </div>
        ) : (
          <div className="card">
            <h3>Quantity</h3>
            <p className="muted">Quantity needs item lines in these periods.</p>
          </div>
        )
      ) : null}
      {active === "sales" ? (
        <>
          {salesPending
            ? <EmptyCard title="Loading sales" copy="Reading the saved order gaps." />
            : <SalesGapsPanel detail={{ uk: "business", sales_gaps: view.sales_gaps }} showParty />}
        </>
      ) : null}
      {active === "breakdown" && hasLists ? (
      <div className="biz-split">
      <MixTable
        title="Customer groups"
        rows={mix.groups}
        onOpen={(row) => row.uk && hashSet("group/" + encodeURIComponent(row.uk))}
        columns={[
          { id: "name", label: "Group", get: (row) => row.name },
          { id: "customers", label: "Customers", num: true, get: (row) => row.customers || 0 },
          { id: "sales", label: "This year sales", num: true, get: (row) => row.ytd_sales == null ? "—" : money(row.ytd_sales) },
          { id: "due", label: "Due", num: true, get: (row) => money(row.due || 0) },
        ]}
      />
      <MixTable
        title="Sales reps"
        rows={mix.reps}
        onOpen={(row) => row.uk && hashSet("rep/" + encodeURIComponent(row.uk))}
        columns={[
          { id: "name", label: "Sales rep", get: (row) => row.name },
          { id: "customers", label: "Customers", num: true, get: (row) => row.customers || 0 },
          { id: "sales", label: "This year sales", num: true, get: (row) => money(row.ytd_sales || 0) },
          { id: "due", label: "Due", num: true, get: (row) => money(row.due || 0) },
        ]}
      />
      <MixTable
        title="Expenses this year"
        rows={mix.expenses}
        columns={[
          { id: "name", label: "Category", get: (row) => row.name },
          { id: "amount", label: "Amount", num: true, get: (row) => money(row.amount || 0) },
        ]}
      />
      <MixTable
        title="Largest open invoices"
        rows={mix.invoices}
        onOpen={(row) => row.customer_uk && hashSet("customer/" + encodeURIComponent(row.customer_uk))}
        columns={[
          { id: "party", label: "Customer", get: (row) => row.party },
          { id: "invoice", label: "Invoice", get: (row) => row.invoice || "—" },
          { id: "age", label: "Age", num: true, get: (row) => row.age_days || 0 },
          { id: "due", label: "Due", num: true, get: (row) => money(row.due || 0) },
        ]}
      />
      <MixTable
        title="Items to buy"
        rows={mix.buy}
        onOpen={(row) => row.uk && hashSet("item/" + encodeURIComponent(row.uk))}
        columns={[
          { id: "name", label: "Item", get: (row) => row.name },
          { id: "status", label: "Status", get: (row) => row.status_label || "—" },
          { id: "qty", label: "Buy qty", num: true, get: (row) => qty(row.buy_qty) },
          { id: "value", label: "Buy value", num: true, get: (row) => money(row.buy_value || 0) },
        ]}
      />
      <MixTable
        title="Sales change by customer"
        rows={movement.customers}
        onOpen={(row) => row.uk && hashSet("customer/" + encodeURIComponent(row.uk))}
        columns={[
          { id: "name", label: "Customer", get: (row) => row.name },
          { id: "current", label: "This month", num: true, get: (row) => row.current == null ? "—" : money(row.current) },
          { id: "change", label: "Change", num: true, get: (row) => money(row.change || 0) },
        ]}
      />
      <MixTable
        title="Sales change by item"
        rows={movement.products}
        onOpen={(row) => row.uk && hashSet("item/" + encodeURIComponent(row.uk))}
        columns={[
          { id: "name", label: "Item", get: (row) => row.name },
          { id: "current", label: "This month", num: true, get: (row) => row.current == null ? "—" : money(row.current) },
          { id: "change", label: "Change", num: true, get: (row) => money(row.change || 0) },
        ]}
      />
      </div>
      ) : null}
      </div>
    </div>
  );
}
