import { Fragment, useEffect, useState } from "react";
import SectionTabs, { rememberedTab } from "./SectionTabs";
import { api } from "./api";
import CollectionFollowUp from "./CollectionFollowUp";
import { CHART, can } from "./theme";
import { AGE_KEYS, AGE_LABELS, ageLabel, bandKey, bucketMoney, hashBack, hashGet, hashReturnLabel, hashSet, initials, money, moneyOrDash, round2, rowBucket } from "./format";
import AgeBar, { ageParts } from "./AgeBar";
import { CUSTOMER_FIELDS, CUSTOMER_SORT_OPTIONS, EmptyCard, FilterBar, ListPager, SortTh, toggleSort } from "./FilterBar";
import SettlementsPanel from "./SettlementsPanel";
import SalesGapsPanel from "./SalesGapsPanel";
import RepurchasePanel from "./RepurchasePanel";
import OrderingPanel, { DueDaysEditor, orderingHeroLine } from "./OrderingPanel";
import OrderCheckPanel from "./OrderCheckPanel";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

function statusLabel(status) {
  if (status === "urgent") return "Urgent";
  if (status === "followup") return "Follow up";
  if (status === "credit") return "Advance";
  return "On track";
}

function statusClass(status) {
  if (status === "urgent") return "err";
  if (status === "followup") return "warn";
  if (status === "credit") return "credit";
  return "ok";
}

function heroClass(status) {
  if (status === "credit") return " credit-hero";
  if (status === "urgent") return " urgent-hero";
  if (status === "followup") return " followup-hero";
  return "";
}

function InvoiceLink({ id, label, enabled, onOpen }) {
  if (id && enabled) {
    return (
      <button type="button" className="linkish" onClick={(e) => { e.stopPropagation(); onOpen(id); }}>
        {label || "Invoice"}
      </button>
    );
  }
  return label || "—";
}

function ItemLink({ uk, name, enabled, onOpen }) {
  if (uk && enabled) {
    return (
      <button type="button" className="linkish" onClick={(e) => { e.stopPropagation(); onOpen(uk); }}>
        {name}
      </button>
    );
  }
  return name || "—";
}

function Directory({ filters, setFilters, q, setQ, data, page, loading, sort, dir, onSort, onSortChange, onOpen, onPage }) {
  return (
    <div className="workspace-page aging-page">
      <div className="page-head">
        <div className="page-head-copy">
          <h2>Customers</h2>
          <p className="muted">Search, filter, sort by due age, and open a customer.</p>
        </div>
        <div className="page-head-tools">
          <input
            className="search-input"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search name, group, or salesperson"
          />
          <span className="page-stat">
            {data ? `${data.total} ${data.total === 1 ? "customer" : "customers"}` : "…"}
            {loading && data ? " · Updating…" : ""}
          </span>
        </div>
      </div>
      <FilterBar
        filters={filters}
        options={{ ...(data?.options || {}), balance_issue: ["Mismatch", "Missing ARR"] }}
        onChange={setFilters}
        fields={CUSTOMER_FIELDS}
        sort={sort}
        dir={dir}
        sortOptions={CUSTOMER_SORT_OPTIONS}
        onSortChange={onSortChange}
      />
      {loading && !data ? <EmptyCard title="Loading customers" copy="Pulling the latest directory." /> : null}
      {!loading && !data?.customers?.length ? (
        <EmptyCard title="No customers match" copy="Clear a filter, or import sales or Outstanding to add them." />
      ) : null}
      {data?.customers?.length ? (
        <div className="card table-card list-panel">
          <table className="dense list-table aging">
            <thead>
              <tr>
                <SortTh id="party" label="Customer" sort={sort} dir={dir} onSort={onSort} />
                <SortTh id="group" label="Group" sort={sort} dir={dir} onSort={onSort} />
                <SortTh id="rep" label="Salesperson" sort={sort} dir={dir} onSort={onSort} />
                <SortTh id="status" label="Status" sort={sort} dir={dir} onSort={onSort} />
                <SortTh id="last_sale" label="Last sale" sort={sort} dir={dir} onSort={onSort} />
                <SortTh id="due" label="Due" sort={sort} dir={dir} onSort={onSort} className="num" />
                <SortTh id="balance_diff" label="AR Diff" sort={sort} dir={dir} onSort={onSort} className="num" />
                {AGE_KEYS.map((k) => (
                  <SortTh key={k} id={k} label={AGE_LABELS[k]} sort={sort} dir={dir} onSort={onSort} className="num" />
                ))}
              </tr>
            </thead>
            <tbody>
              {data.customers.map((c) => (
                <tr key={c.uk} className="click-row" onClick={() => onOpen(c.uk)}>
                  <td>
                    <div className="name-cell">
                      <span className="avatar sm">{initials(c.name)}</span>
                      <span className="clip" title={c.name}><strong>{c.name}</strong></span>
                    </div>
                  </td>
                  <td>{c.group ? <span className="soft-tag" title={c.group}>{c.group}</span> : <span className="quiet">—</span>}</td>
                  <td className="clip" title={c.salesperson || ""}>{c.salesperson || "—"}</td>
                  <td>
                    <span className={"pill " + statusClass(c.status)}>{c.status_label || statusLabel(c.status)}</span>
                    {c.balance_issue === "mismatch" ? <span className="pill followup">Mismatch</span> : null}
                    {c.balance_issue === "missing_arr" ? <span className="pill order-overdue">Missing ARR</span> : null}
                    {c.ordered_overdue ? <span className="pill order-overdue">Ordered overdue</span> : null}
                    {c.premium ? <span className="pill premium">Premium</span> : null}
                    {c.blacklisted ? <span className="pill blacklisted">Blacklisted</span> : null}
                  </td>
                  <td className="quiet">{c.last_sale_label || "—"}</td>
                  <td className={"num amount" + (c.credit ? " credit" : "")}>{c.credit ? money(Math.abs(c.due)) : money(c.due)}</td>
                  <td className={"num amount" + (Number(c.balance_diff) < 0 ? " credit" : "")}>{moneyOrDash(c.balance_diff)}</td>
                  {AGE_KEYS.map((k) => (
                    <td key={k} className="num">{bucketMoney(rowBucket(c, k))}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      <ListPager page={page} total={data?.total} onPage={onPage} />
    </div>
  );
}

function DueTable({ rows, canSales, onOpenInvoice }) {
  // Oldest first by default — matches order-check "oldest open invoice".
  const [sort, setSort] = useState("age");
  const [dir, setDir] = useState("desc");
  function onSort(id) {
    const next = toggleSort(sort, dir, id, ["due", "age"]);
    setSort(next.sort);
    setDir(next.dir);
  }
  const ordered = rows
    .filter((line) => (Number(line.due) || 0) >= 0.005)
    .slice()
    .sort((a, b) => {
    const key = sort === "age" ? "age_days" : sort === "date" ? "date" : sort === "invoice" ? "invoice" : sort;
    const av = a[key];
    const bv = b[key];
    const cmp = typeof av === "number" && typeof bv === "number" ? av - bv : String(av || "").localeCompare(String(bv || ""));
    return dir === "desc" ? -cmp : cmp;
  });
  return (
    <div className="table-wrap">
      <table className="dense list-table compact">
        <thead>
          <tr>
            <SortTh id="date" label="Date" sort={sort} dir={dir} onSort={onSort} />
            <SortTh id="invoice" label="Invoice" sort={sort} dir={dir} onSort={onSort} />
            <SortTh id="what" label="What" sort={sort} dir={dir} onSort={onSort} />
            <SortTh id="due" label="Still due" sort={sort} dir={dir} onSort={onSort} />
            <SortTh id="age" label="Age" sort={sort} dir={dir} onSort={onSort} />
          </tr>
        </thead>
        <tbody>
          {ordered.map((line, i) => (
            <tr key={i} className={line.kind === "opening" ? "total" : ""}>
              <td>{line.date_label}</td>
              <td>
                {line.kind === "opening" ? "—" : (
                  <InvoiceLink id={line.invoice_id} label={line.invoice || "Sale"} enabled={canSales} onOpen={onOpenInvoice} />
                )}
              </td>
              <td>{line.what}</td>
              <td>{money(line.due)}</td>
              <td>{line.age_days} days</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function BuyingTable({ title, rows, canStock, onOpenItem }) {
  const [sort, setSort] = useState("amount");
  const [dir, setDir] = useState("desc");
  function onSort(id) {
    const next = toggleSort(sort, dir, id, ["qty", "amount", "times"]);
    setSort(next.sort);
    setDir(next.dir);
  }
  const ordered = rows.slice().sort((a, b) => {
    const key = sort === "item" ? "name" : sort === "last" ? "last_label" : sort;
    const av = a[key];
    const bv = b[key];
    const cmp = typeof av === "number" && typeof bv === "number" ? av - bv : String(av || "").localeCompare(String(bv || ""));
    return dir === "desc" ? -cmp : cmp;
  });
  return (
    <div className="card table-card list-panel">
      <h3>{title}</h3>
      {rows.length ? (
        <table className="dense list-table compact">
          <thead>
            <tr>
              <SortTh id="item" label="Item" sort={sort} dir={dir} onSort={onSort} />
              <SortTh id="qty" label="Qty" sort={sort} dir={dir} onSort={onSort} className="num" />
              <SortTh id="amount" label="Amount" sort={sort} dir={dir} onSort={onSort} className="num" />
              <SortTh id="times" label="Times" sort={sort} dir={dir} onSort={onSort} className="num" />
              <SortTh id="last" label="Last bought" sort={sort} dir={dir} onSort={onSort} />
            </tr>
          </thead>
          <tbody>
            {ordered.map((item) => (
              <tr key={item.name}>
                <td><ItemLink uk={item.item_uk} name={item.name} enabled={canStock} onOpen={onOpenItem} /></td>
                <td className="num">{item.qty}</td>
                <td className="num">{money(item.amount)}</td>
                <td className="num">{item.times}</td>
                <td>{item.last_label || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : <p className="muted">No item lines in this period.</p>}
    </div>
  );
}

function ledgerYears(ar) {
  let running = round2(ar.opening || 0);
  return (ar.years || []).map((year) => {
    const fyOpening = running;
    const months = (year.months || []).map((month) => {
      const opening = running;
      const sales = round2(month.sales || 0);
      const collection = round2(month.collection || 0);
      const creditNotes = round2(month.credit_notes || 0);
      const balance = round2(opening + sales - collection - creditNotes);
      running = balance;
      return { ...month, opening, sales, collection, credit_notes: creditNotes, balance };
    });
    const sum = (key) => round2(months.reduce((total, month) => total + month[key], 0));
    return {
      ...year,
      opening: fyOpening,
      sales: sum("sales"),
      collection: sum("collection"),
      credit_notes: sum("credit_notes"),
      balance: months.length ? months[months.length - 1].balance : fyOpening,
      months,
    };
  });
}

function ArMismatchPanel({ detail }) {
  const ar = detail.ar_mismatch || {};
  const years = ledgerYears(ar);
  const issue = ar.balance_issue === "mismatch";
  const opening = round2(ar.opening || 0);
  return (
    <div className="card">
      <h3>AR mismatch</h3>
      <p className="muted">
        {opening
          ? "Opening balance " + money(opening) + (ar.opening_month ? " starts in " + ar.opening_month : "") + ". Each later month opens with the previous balance. "
          : "Each month opens with the previous month’s balance. "}
        Outstanding {money(ar.outstanding)}
        {" · Opening + sales − collection − credit notes "}
        {money(round2((ar.opening || 0) + (ar.sales || 0) - (ar.collection || 0) - (ar.credit_notes || 0)))}
        {" · Difference "}{money(ar.balance_diff)}
        {" "}
        {issue ? <span className="pill followup">Mismatch</span> : <span className="pill ok">Matches</span>}
      </p>
      {years.length ? (
        <div className="table-wrap">
          <table className="dense list-table compact">
            <thead>
              <tr>
                <th>Month</th>
                <th>Opening</th>
                <th>Sales</th>
                <th>Collection</th>
                <th>Credit notes</th>
                <th>Balance</th>
              </tr>
            </thead>
            <tbody>
              {years.map((year) => (
                <Fragment key={year.start}>
                  {year.months.map((month) => (
                    <tr key={month.start}>
                      <td>{month.label}</td>
                      <td>{money(month.opening)}</td>
                      <td>{money(month.sales)}</td>
                      <td>{money(month.collection)}</td>
                      <td>{money(month.credit_notes)}</td>
                      <td>{money(month.balance)}</td>
                    </tr>
                  ))}
                  <tr className="fy-summary">
                    <td><strong>{year.label}</strong></td>
                    <td><strong>{money(year.opening)}</strong></td>
                    <td><strong>{money(year.sales)}</strong></td>
                    <td><strong>{money(year.collection)}</strong></td>
                    <td><strong>{money(year.credit_notes)}</strong></td>
                    <td><strong>{money(year.balance)}</strong></td>
                  </tr>
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      ) : <p className="muted">No sales, collections, or credit notes yet.</p>}
    </div>
  );
}

function YearBlock({ fy }) {
  if (!fy.length) {
    return (
      <div className="card">
        <h3>Sales and collection by year</h3>
        <p className="muted">No sales or collections yet.</p>
      </div>
    );
  }
  return (
    <div className="card">
      <h3>Sales and collection by year</h3>
      <div className="fy-grid">
        {fy.map((y) => (
          <div className="fy-card" key={y.start}>
            <div className="fy-label">{y.label}</div>
            <div className="fy-metric sales"><span className="muted">Sales</span> <strong>{money(y.sales)}</strong></div>
            <div className="fy-metric collection"><span className="muted">Collection</span> <strong>{money(y.collection)}</strong></div>
          </div>
        ))}
      </div>
      {fy.length > 1 ? (
        <div style={{ width: "100%", height: 220, marginTop: 12 }}>
          <ResponsiveContainer>
            <BarChart data={fy.slice().reverse()}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="label" />
              <YAxis />
              <Tooltip />
              <Legend />
              <Bar dataKey="sales" name="Sales" fill={CHART.sales} />
              <Bar dataKey="collection" name="Collection" fill={CHART.collection} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      ) : null}
    </div>
  );
}

function formatQty(n) {
  if (n === null || n === undefined || n === "") return "—";
  const v = Number(n);
  if (!Number.isFinite(v)) return "—";
  return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function QtyYearBlock({ fy }) {
  const known = fy.some((row) => row.qty !== null && row.qty !== undefined);
  if (!fy.length) {
    return (
      <div className="card">
        <h3>Quantity by year</h3>
        <p className="muted">No sales yet.</p>
      </div>
    );
  }
  if (!known) {
    return (
      <div className="card">
        <h3>Quantity by year</h3>
        <p className="muted">Quantity needs item lines in these periods.</p>
      </div>
    );
  }
  return (
    <div className="card">
      <h3>Quantity by year</h3>
      <div className="fy-grid">
        {fy.map((y) => (
          <div className="fy-card" key={y.start || y.label}>
            <div className="fy-label">{y.label}</div>
            <div className="fy-metric sales"><span className="muted">Quantity</span> <strong>{formatQty(y.qty)}</strong></div>
          </div>
        ))}
      </div>
      {fy.length > 1 ? (
        <div style={{ width: "100%", height: 220, marginTop: 12 }}>
          <ResponsiveContainer>
            <BarChart data={fy.slice().reverse()}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="label" />
              <YAxis />
              <Tooltip />
              <Bar dataKey="qty" name="Quantity" fill={CHART.sales} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      ) : null}
    </div>
  );
}

function pillKind(kind) {
  if (["sale", "collection", "credit_note", "visit", "sales_followup", "collection_followup"].includes(kind)) return kind;
  return "logged";
}

function ActivityTable({ rows, shown, canSales, onOpenInvoice }) {
  const [sort, setSort] = useState("date");
  const [dir, setDir] = useState("desc");
  function onSort(id) {
    const next = toggleSort(sort, dir, id, ["amount"]);
    setSort(next.sort);
    setDir(next.dir);
  }
  const ordered = rows.slice().sort((a, b) => {
    const key = sort === "type" ? "label" : sort === "detail" ? "note" : sort;
    const av = a[key];
    const bv = b[key];
    const cmp = typeof av === "number" && typeof bv === "number" ? av - bv : String(av || "").localeCompare(String(bv || ""));
    return dir === "desc" ? -cmp : cmp;
  });
  const visible = ordered.slice(0, shown || ordered.length);
  return (
    <div className="table-wrap">
      <table className="dense list-table compact">
        <thead>
          <tr>
            <SortTh id="date" label="Date" sort={sort} dir={dir} onSort={onSort} />
            <SortTh id="type" label="Type" sort={sort} dir={dir} onSort={onSort} />
            <SortTh id="detail" label="Detail" sort={sort} dir={dir} onSort={onSort} />
            <SortTh id="amount" label="Amount" sort={sort} dir={dir} onSort={onSort} className="num" />
            <SortTh id="rep" label="Assignee" sort={sort} dir={dir} onSort={onSort} />
          </tr>
        </thead>
        <tbody>
          {visible.map((e, i) => (
            <tr key={e.id || e.invoice_id || e.kind + e.date + i}>
              <td>{e.date_label}</td>
              <td><span className={"pill act-" + pillKind(e.kind)}>{e.label}</span></td>
              <td>
                {e.kind === "sale" ? (
                  <InvoiceLink id={e.invoice_id} label={e.invoice || e.label} enabled={canSales} onOpen={onOpenInvoice} />
                ) : (e.kind === "credit_note" ? (e.invoice || e.note || "—") : (e.note || "—"))}
              </td>
              <td className="num">{e.kind === "sale" || e.kind === "collection" || e.kind === "credit_note" ? money(e.amount) : "—"}</td>
              <td className="clip" title={e.rep || ""}>{e.rep || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const BUYING_PERIODS = ["this_month", "last_month", "last_3m", "this_year", "last_year", "all"];
const BUYING_CHIPS = [...BUYING_PERIODS, "suggest"];

function firstBuyingPeriod(periods, fallback) {
  if (fallback && fallback !== "suggest" && ((periods[fallback] || {}).items || []).length) return fallback;
  return BUYING_PERIODS.find((id) => ((periods[id] || {}).items || []).length) || "all";
}

const CUSTOMER_TABS = ["due", "settlements", "ar-mismatch", "sales", "quantity", "years", "buying", "repurchase", "ordering", "order-check", "activity", "follow-up"];

function customerTabGroups(detail) {
  const open = Number(detail.invoices_waiting) || 0;
  return [
    { tabs: [
      { id: "due", label: "Due", count: open > 0 ? open : null },
      { id: "settlements", label: "Settlements" },
      { id: "ar-mismatch", label: "AR mismatch" },
    ] },
    { tabs: [
      { id: "sales", label: "Sales" },
      { id: "quantity", label: "Quantity" },
      { id: "years", label: "Years" },
      { id: "buying", label: "Buying" },
      { id: "repurchase", label: "Repurchase" },
    ] },
    { tabs: [
      { id: "ordering", label: "Ordering" },
      { id: "order-check", label: "Order check" },
    ] },
    { tabs: [
      { id: "activity", label: "Activity" },
      { id: "follow-up", label: "Follow-up" },
    ] },
  ];
}

function Profile({ detail, runId, canSales, canStock, canEditDueDays, canManage, user, onBack, onPdf, pdfBusy, backLabel, onOpenInvoice, onOpenItem, onReload }) {
  const [tab, setTab] = useState(() => rememberedTab("customer", "due", CUSTOMER_TABS));
  const [filter, setFilter] = useState("all");
  const [period, setPeriod] = useState(() => firstBuyingPeriod((detail.buying || {}).periods || {}, (detail.buying || {}).default_period || "this_year"));
  const [shown, setShown] = useState(30);
  const [shareOpen, setShareOpen] = useState(false);
  const [dueBand, setDueBand] = useState("");
  const [parts, setParts] = useState({});
  const section = {
    settlements: "settlements",
    sales: "sales",
    ordering: "ordering",
    buying: "buying",
    activity: "activity",
    "ar-mismatch": "ar-mismatch",
  }[tab] || "";
  const view = { ...detail };
  Object.keys(parts).forEach((key) => Object.assign(view, parts[key] || {}));
  const events = (view.activity || []).filter((e) => filter === "all" || e.kind === filter);
  const kindFilters = [
    ["all", "All"],
    ["sale", "Sales"],
    ["credit_note", "Credit notes"],
    ["collection", "Collections"],
  ];
  const fy = view.fy_years || detail.fy_years || [];
  const buying = view.buying || {};
  const periods = buying.periods || {};
  const periodItems = (periods[period] || {}).items || [];

  useEffect(() => {
    setParts({});
    setPeriod(firstBuyingPeriod((detail.buying || {}).periods || {}, (detail.buying || {}).default_period || "all"));
    setDueBand("");
  }, [detail.uk]);

  useEffect(() => {
    const periods = parts.buying?.buying?.periods;
    if (!periods) return undefined;
    setPeriod((current) => {
      if (current && current !== "suggest" && ((periods[current] || {}).items || []).length) return current;
      return firstBuyingPeriod(periods, parts.buying.buying.default_period || "this_year");
    });
    return undefined;
  }, [detail.uk, parts.buying]);

  useEffect(() => {
    if (!section || !detail.sections?.[section]) return undefined;
    if (Object.prototype.hasOwnProperty.call(parts, section)) return undefined;
    let cancelled = false;
    api.customer(detail.uk, { run: runId || detail.run_id || "", section })
      .then((part) => {
        if (!cancelled) setParts((prev) => ({ ...prev, [section]: part || {} }));
      })
      .catch(() => {
        if (!cancelled) setParts((prev) => ({ ...prev, [section]: {} }));
      });
    return () => { cancelled = true; };
  }, [section, detail.uk, detail.run_id, detail.sections, runId, parts]);
  const dueInvoices = (detail.open_invoices || []).filter((line) => (Number(line.due) || 0) >= 0.005 && (!dueBand || bandKey(line.age_days, detail.aging_bands) === dueBand));
  const insight = detail.insight || {};
  const orderLine = orderingHeroLine(detail);
  const pdfBusyAny = Boolean(pdfBusy);
  const sectionPending = Boolean(section && detail.sections?.[section] && !Object.prototype.hasOwnProperty.call(parts, section));

  function pickShare(view) {
    setShareOpen(false);
    onPdf(view);
  }

  return (
    <div className="workspace-page">
      <div className="profile-nav">
        <button className="ghost" onClick={onBack}>← {backLabel}</button>
        <button onClick={() => setShareOpen(true)} disabled={pdfBusyAny}>
          {pdfBusyAny ? "Preparing…" : "Share"}
        </button>
      </div>
      {shareOpen ? (
        <div className="modal-backdrop" onClick={() => { if (!pdfBusyAny) setShareOpen(false); }}>
          <div className="modal confirm-modal" role="dialog" aria-modal="true" aria-labelledby="share-pdf-title" onClick={(e) => e.stopPropagation()}>
            <h3 id="share-pdf-title">Download PDF</h3>
            <p className="muted">Choose which copy to download.</p>
            <div className="modal-actions" style={{ flexDirection: "column", alignItems: "stretch" }}>
              <button type="button" disabled={pdfBusyAny} onClick={() => pickShare("customer")}>
                Customer copy
              </button>
              <button type="button" className="ghost" disabled={pdfBusyAny} onClick={() => pickShare("rep")}>
                Rep copy
              </button>
              <button type="button" className="ghost" disabled={pdfBusyAny} onClick={() => pickShare("reminder")}>
                Payment reminder
              </button>
              <button type="button" className="ghost" disabled={pdfBusyAny} onClick={() => setShareOpen(false)}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      ) : null}
      <div className={"hero card" + heroClass(detail.status)}>
        <div>
          <h2>{detail.name}</h2>
          <p className="muted">
            {detail.group ? (
              <span className="chip">
                <button type="button" onClick={() => hashSet("group/" + encodeURIComponent(detail.group))}>{detail.group}</button>
              </span>
            ) : null}
            {" "}
            {detail.salesperson ? (
              <button type="button" className="linkish" onClick={() => hashSet("rep/" + encodeURIComponent(detail.salesperson))}>
                {detail.salesperson}
              </button>
            ) : "No salesperson"}
            {detail.last_sale_label ? " · Last sale " + detail.last_sale_label : ""}
            {detail.as_of_label ? " · As of " + detail.as_of_label : ""}
          </p>
          <DueDaysEditor
            entity="customer"
            uk={detail.uk}
            detail={detail}
            canEdit={canEditDueDays}
            onSaved={() => onReload && onReload()}
          />
          {orderLine ? <p className="muted" style={{ marginTop: 6 }}>{orderLine}</p> : null}
        </div>
        <div className="hero-due">
          <span className="muted">{detail.credit ? "Advance" : "Amount due"}</span>
          <div className="hero-num">{money(detail.credit ? Math.abs(detail.due) : detail.due)}</div>
          {detail.balance_issue || detail.ledger_opening ? (
            <p className="muted">
              Opening {money(detail.ledger_opening || 0)}
              {" + sales − collection − credit notes "}
              {money(round2((detail.ledger_opening || 0) + (detail.ledger_gap || 0)))}
              {" · Outstanding "}
              {detail.arr_balance == null ? "—" : money(detail.arr_balance)}
            </p>
          ) : null}
          <span className={"pill " + statusClass(detail.status)}>{insight.health_label || statusLabel(detail.status)}</span>
          {detail.balance_issue === "mismatch" ? <span className="pill followup">Mismatch</span> : null}
          {detail.balance_issue === "missing_arr" ? <span className="pill order-overdue">Missing ARR</span> : null}
          {detail.ordered_overdue ? <span className="pill order-overdue">Ordered overdue</span> : null}
          {detail.premium ? <span className="pill premium">Premium</span> : null}
          {detail.blacklisted ? <span className="pill blacklisted">Blacklisted</span> : null}
        </div>
      </div>
      <div className="buy-tiles">
        <div className="card buy-tile">
          <span className="muted">This year sales</span>
          <strong>{money(detail.ytd_sales)}</strong>
        </div>
        <div className="card buy-tile">
          <span className="muted">This year collected</span>
          <strong>{money(detail.ytd_collection)}</strong>
        </div>
        <div className="card buy-tile">
          <span className="muted">Last collection</span>
          <strong>{detail.last_collection_label || "—"}</strong>
        </div>
        <div className="card buy-tile">
          <span className="muted">Open amounts</span>
          <strong>{detail.invoices_waiting || 0}</strong>
        </div>
      </div>
      {insight.money_bit || insight.action ? (
        <p className="muted next-move">{[insight.money_bit, insight.action].filter(Boolean).join(" ")}</p>
      ) : null}
      <SectionTabs
        label="Customer sections"
        storageKey="customer"
        controlsPrefix="customer"
        sticky
        groups={customerTabGroups(detail)}
        value={tab}
        onChange={setTab}
      />
      <div className="tab-panel" role="tabpanel" id={"customer-panel-" + tab} aria-labelledby={"customer-" + tab}>
      {tab === "due" ? (
        <div className="card">
          <h3>What they owe</h3>
          <AgeBar parts={ageParts(detail.owe_buckets, detail.aging_bands)} title="Outstanding by age" selected={dueBand} onSelect={setDueBand} />
          {dueInvoices.length ? (
            <DueTable rows={dueInvoices} canSales={canSales} onOpenInvoice={onOpenInvoice} />
          ) : (
            <p className="muted">{dueBand ? "No invoices in " + (ageLabel(dueBand, detail.aging_bands) + " days") + "." : "Nothing waiting."}</p>
          )}
        </div>
      ) : null}
      {tab === "settlements" ? (
        sectionPending ? <EmptyCard title="Loading settlements" copy="Reading receipts applied to invoices." /> : <SettlementsPanel detail={view} />
      ) : null}
      {tab === "sales" ? (
        <>
          {sectionPending ? <EmptyCard title="Loading sales" copy="Reading the saved order gaps." /> : <SalesGapsPanel detail={view} />}
        </>
      ) : null}
      {tab === "repurchase" ? <RepurchasePanel detail={detail} entity="customer" showCustomer={false} showItem /> : null}
      {tab === "ordering" ? (
        sectionPending ? <EmptyCard title="Loading ordering" copy="Reading orders placed while amounts were overdue." /> : (
        <OrderingPanel
          detail={view}
          canEditDueDays={canEditDueDays}
          onDueDaysSaved={() => onReload && onReload()}
        />
        )
      ) : null}
      {tab === "order-check" ? (
        <OrderCheckPanel detail={detail} canEdit={canEditDueDays} onSaved={() => onReload && onReload()} />
      ) : null}
      {tab === "follow-up" ? (
        <CollectionFollowUp
          customerName={detail.name}
          customerUk={detail.uk}
          invoices={detail.open_invoices || parts.due?.open_invoices}
          canManage={canManage}
          user={user}
          onReminder={() => onPdf("reminder")}
        />
      ) : null}
      {tab === "activity" ? (
        sectionPending ? <EmptyCard title="Loading activity" copy="Reading sales, credit notes, and collections." /> : (
        <div className="card">
          <div className="card-head">
            <h3>Activity</h3>
          </div>
          <div className="chips">
            {kindFilters.map(([id, label]) => (
              <button type="button" key={id} className={filter === id ? "" : "secondary"} onClick={() => { setFilter(id); setShown(30); }}>{label}</button>
            ))}
          </div>
          {events.length ? (
            <ActivityTable
              rows={events}
              shown={shown}
              canSales={canSales}
              onOpenInvoice={onOpenInvoice}
            />
          ) : <p className="muted">No activity yet. Import sales and receipts to see them here.</p>}
          {events.length > shown ? (
            <button type="button" className="ghost" onClick={() => setShown((n) => n + 30)}>Show more</button>
          ) : null}
        </div>
        )
      ) : null}
      {tab === "years" ? (
        <YearBlock fy={fy} />
      ) : null}
      {tab === "quantity" ? <QtyYearBlock fy={fy} /> : null}
      {tab === "ar-mismatch" ? (
        sectionPending ? <EmptyCard title="Loading AR mismatch" copy="Reading the saved balance check." /> : <ArMismatchPanel detail={view} />
      ) : null}
      {tab === "buying" ? (
        sectionPending ? <EmptyCard title="Loading buying" copy="Reading items this customer has bought." /> : (
          <div>
            {buying.last_order_date ? <p className="muted">Last order {buying.last_order_date}{buying.usual?.length ? " · Usually " + buying.usual.slice(0, 3).join(", ") : ""}</p> : null}
            <div className="chips">
              {BUYING_CHIPS.map((id) => (
                <button type="button" key={id} className={period === id ? "" : "secondary"} onClick={() => setPeriod(id)}>
                  {id === "suggest" ? "Suggest next" : ((periods[id] || {}).label || id)}
                </button>
              ))}
            </div>
            {period === "suggest" ? (
              <div className="card">
                <h3>Suggest next</h3>
                {(buying.suggested || []).length ? (
                  <ul className="suggest-list">
                    {buying.suggested.map((item) => (
                      <li key={item.name}>
                        <strong><ItemLink uk={item.item_uk} name={item.name} enabled={canStock} onOpen={onOpenItem} /></strong>
                        <div className="muted">{item.reason}</div>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted">
                    {buying.has_item_rows
                      ? "Nothing in stock to suggest."
                      : "Import item-wise sales with the customer name to see buying and suggestions."}
                  </p>
                )}
              </div>
            ) : (
              <BuyingTable title={(periods[period] || {}).label || "Buying"} rows={periodItems} canStock={canStock} onOpenItem={onOpenItem} />
            )}
          </div>
        )
      ) : null}
      </div>
    </div>
  );
}

const emptyCustomerFilters = { group: "", rep: "", status: "", balance_issue: "" };

export default function CustomersPage({ user, runId }) {
  const [filters, setFilters] = useState(emptyCustomerFilters);
  const [q, setQ] = useState("");
  const [qDebounced, setQDebounced] = useState("");
  const [sort, setSort] = useState("due");
  const [dir, setDir] = useState("desc");
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [uk, setUk] = useState("");
  const [detail, setDetail] = useState(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);
  const [pdfBusy, setPdfBusy] = useState(false);
  const canSales = can(user, "sales.view");
  const canStock = can(user, "stock.view");
  const canEditDueDays = can(user, "settings.advanced");
  const canManage = can(user, "actions.manage");

  function loadList(nextFilters, nextPage, nextSort, nextDir, nextQ) {
    setLoading(true);
    api.customers({
      ...nextFilters,
      q: nextQ,
      sort: nextSort,
      dir: nextDir,
      page: String(nextPage || 1),
      run: runId || "",
    })
      .then(setData)
      .catch((e) => setErr(e.message))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    const t = setTimeout(() => setQDebounced(q.trim()), 300);
    return () => clearTimeout(t);
  }, [q]);

  useEffect(() => {
    setPage(1);
    loadList(filters, 1, sort, dir, qDebounced);
  }, [filters, sort, dir, qDebounced, runId]);

  function applyHash(h) {
    if (h.startsWith("customer/")) {
      setUk(h.slice("customer/".length));
      return;
    }
    if (h.startsWith("list/customers/")) {
      const status = decodeURIComponent(h.slice("list/customers/".length));
      if (status) setFilters((prev) => ({ ...prev, status }));
    }
    setUk("");
    setDetail(null);
  }

  useEffect(() => {
    applyHash(hashGet());
  }, []);

  useEffect(() => {
    function onHash() {
      applyHash(hashGet());
    }
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  useEffect(() => {
    if (!uk) return undefined;
    setDetail(null);
    api.customer(uk, { run: runId || "", view: "profile" }).then(setDetail).catch((e) => setErr(e.message));
    return undefined;
  }, [uk, runId]);

  function goBack() {
    hashBack("");
  }

  if (uk) {
    if (detail && detail.uk === uk) {
      return (
        <>
          {err ? <p className="err">{err}</p> : null}
          <Profile
            detail={detail}
            runId={runId}
            canSales={canSales}
            canStock={canStock}
            canEditDueDays={canEditDueDays}
            canManage={canManage}
            user={user}
            backLabel={hashReturnLabel("Customers")}
            pdfBusy={pdfBusy}
            onBack={goBack}
            onOpenInvoice={(id) => hashSet("invoice/" + encodeURIComponent(id))}
            onOpenItem={(itemUk) => hashSet("item/" + encodeURIComponent(itemUk))}
            onReload={() => api.customer(uk, { run: runId || "", view: "profile" }).then(setDetail).catch((e) => setErr(e.message))}
            onPdf={(view) => {
              setPdfBusy(view || "rep");
              api.customerPdf(uk, detail.name, { view: view || "rep", run: runId || "" })
                .catch((e) => setErr(e.message))
                .finally(() => setPdfBusy(false));
            }}
          />
        </>
      );
    }
    return (
      <div className="card">
        {err ? <p className="err">{err}</p> : <p className="muted">Opening customer…</p>}
        <button className="ghost" onClick={goBack}>← {hashReturnLabel("Customers")}</button>
      </div>
    );
  }

  return (
    <>
      {err ? <p className="err">{err}</p> : null}
      <Directory
        filters={filters}
        setFilters={setFilters}
        q={q}
        setQ={setQ}
        data={data}
        page={page}
        loading={loading}
        sort={sort}
        dir={dir}
        onSort={(id) => {
          const next = toggleSort(sort, dir, id, ["due", "balance_diff", "last_sale", ...AGE_KEYS]);
          setSort(next.sort);
          setDir(next.dir);
        }}
        onSortChange={(next) => {
          setSort(next.sort);
          setDir(next.dir);
        }}
        onOpen={(next) => { setUk(next); hashSet("customer/" + encodeURIComponent(next)); }}
        onPage={(p) => { setPage(p); loadList(filters, p, sort, dir, qDebounced); }}
      />
    </>
  );
}
