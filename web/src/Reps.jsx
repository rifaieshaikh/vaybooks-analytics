import { useEffect, useState } from "react";
import SectionTabs, { rememberedTab } from "./SectionTabs";
import { api } from "./api";
import { CHART, can } from "./theme";
import { AGE_KEYS, AGE_LABELS, ageLabel, bandKey, bucketMoney, hashBack, hashGet, hashReturnLabel, hashSet, initials, money, rowBucket } from "./format";
import AgeBar, { ageParts } from "./AgeBar";
import { EmptyCard, FilterBar, ListPager, MemberCustomersTable, REP_FIELDS, REP_SORT_OPTIONS, SortTh, toggleSort } from "./FilterBar";
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

function ItemLink({ uk, name, enabled }) {
  if (uk && enabled) {
    return (
      <button type="button" className="linkish" onClick={() => hashSet("item/" + encodeURIComponent(uk))}>{name}</button>
    );
  }
  return name || "—";
}

function Directory({ filters, setFilters, q, setQ, data, page, loading, sort, dir, onSort, onSortChange, onOpen, onPage }) {
  return (
    <div className="workspace-page aging-page">
      <div className="page-head">
        <div className="page-head-copy">
          <h2>Sales reps</h2>
          <p className="muted">Search, filter, sort by due age, and open a salesperson.</p>
        </div>
        <div className="page-head-tools">
          <input
            className="search-input"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search name or group"
          />
          <span className="page-stat">
            {data ? `${data.total} ${data.total === 1 ? "salesperson" : "salespeople"}` : "…"}
            {loading && data ? " · Updating…" : ""}
          </span>
        </div>
      </div>
      <FilterBar
        filters={filters}
        options={data?.options}
        onChange={setFilters}
        fields={REP_FIELDS}
        sort={sort}
        dir={dir}
        sortOptions={REP_SORT_OPTIONS}
        onSortChange={onSortChange}
      />
      {loading && !data ? <EmptyCard title="Loading salespeople" copy="Pulling the latest sales reps." /> : null}
      {!loading && !data?.reps?.length ? (
        <EmptyCard title="No salespeople match" copy="Clear a filter, or import sales with a Sales Rep column." />
      ) : null}
      {data?.reps?.length ? (
        <div className="card table-card list-panel">
          <table className="dense list-table aging">
            <thead>
              <tr>
                <SortTh id="name" label="Salesperson" sort={sort} dir={dir} onSort={onSort} />
                <SortTh id="customers" label="Customers" sort={sort} dir={dir} onSort={onSort} className="num" />
                <SortTh id="group" label="Groups" sort={sort} dir={dir} onSort={onSort} />
                <SortTh id="status" label="Status" sort={sort} dir={dir} onSort={onSort} />
                <SortTh id="last_sale" label="Last sale" sort={sort} dir={dir} onSort={onSort} />
                <SortTh id="ytd_sales" label="This year" sort={sort} dir={dir} onSort={onSort} className="num" />
                <SortTh id="due" label="Due" sort={sort} dir={dir} onSort={onSort} className="num" />
                {AGE_KEYS.map((k) => (
                  <SortTh key={k} id={k} label={AGE_LABELS[k]} sort={sort} dir={dir} onSort={onSort} className="num" />
                ))}
              </tr>
            </thead>
            <tbody>
              {data.reps.map((row) => (
                <tr key={row.uk} className="click-row" onClick={() => onOpen(row.uk)}>
                  <td>
                    <div className="name-cell">
                      <span className="avatar sm">{initials(row.name)}</span>
                      <span className="clip" title={row.name}><strong>{row.name}</strong></span>
                    </div>
                  </td>
                  <td className="num">{row.customers}</td>
                  <td className="clip" title={(row.groups || []).join(", ")}>{(row.groups || []).join(", ") || "—"}</td>
                  <td>
                    <span className={"pill " + statusClass(row.status)}>{row.status_label || statusLabel(row.status)}</span>
                    {row.ordered_overdue ? <span className="pill order-overdue">Ordered overdue</span> : null}
                  </td>
                  <td className="quiet">{row.last_sale_label || "—"}</td>
                  <td className="num amount">{money(row.ytd_sales)}</td>
                  <td className={"num amount" + (row.credit ? " credit" : "")}>{row.credit ? money(Math.abs(row.due)) : money(row.due)}</td>
                  {AGE_KEYS.map((k) => (
                    <td key={k} className="num">{bucketMoney(rowBucket(row, k))}</td>
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
          <div className="fy-card" key={y.start || y.label}>
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

const BUYING_PERIODS = ["this_month", "last_month", "last_3m", "this_year", "last_year", "all"];

const REP_TABS = ["due", "settlements", "sales", "quantity", "years", "buying", "repurchase", "ordering", "order-check", "customers", "groups", "activity"];

function repTabGroups(detail) {
  const open = Number(detail.invoices_waiting) || 0;
  return [
    { tabs: [
      { id: "due", label: "Due", count: open > 0 ? open : null },
      { id: "settlements", label: "Settlements" },
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
      { id: "customers", label: "Customers" },
      { id: "groups", label: "Groups" },
      { id: "activity", label: "Activity" },
    ] },
  ];
}

function Profile({ detail, runId, canSales, canStock, canEditDueDays, onBack, backLabel, onReload, onPdf, pdfBusy }) {
  const [tab, setTab] = useState(() => rememberedTab("rep", "customers", REP_TABS));
  const [dueBand, setDueBand] = useState("");
  const [period, setPeriod] = useState((detail.buying || {}).default_period || "this_year");
  const [parts, setParts] = useState({});
  const section = {
    customers: "customers",
    due: "due",
    settlements: "settlements",
    sales: "sales",
    ordering: "ordering",
    buying: "buying",
    activity: "activity",
  }[tab] || "";
  const view = { ...detail };
  Object.keys(parts).forEach((key) => Object.assign(view, parts[key] || {}));
  const buying = view.buying || {};
  const periods = buying.periods || {};
  const periodItems = (periods[period] || periods[buying.default_period] || periods.all || {}).items || [];
  const orderLine = orderingHeroLine(view);
  const insight = detail.insight || {};
  const pdfBusyAny = Boolean(pdfBusy);
  const dueInvoices = (view.open_invoices || []).filter((line) => (Number(line.due) || 0) >= 0.005 && (!dueBand || bandKey(line.age_days, detail.aging_bands) === dueBand));
  const sectionPending = Boolean(section && detail.sections?.[section] && !Object.prototype.hasOwnProperty.call(parts, section));

  useEffect(() => {
    setDueBand("");
    setParts({});
  }, [detail.uk]);

  useEffect(() => {
    if (!section || !detail.sections?.[section]) return undefined;
    if (Object.prototype.hasOwnProperty.call(parts, section)) return undefined;
    let cancelled = false;
    api.rep(detail.uk, { run: runId || detail.run_id || "", section })
      .then((part) => {
        if (!cancelled) setParts((prev) => ({ ...prev, [section]: part || {} }));
      })
      .catch(() => {
        if (!cancelled) setParts((prev) => ({ ...prev, [section]: {} }));
      });
    return () => { cancelled = true; };
  }, [section, detail.uk, detail.run_id, detail.sections, runId, parts]);

  return (
    <div className="workspace-page aging-page">
      <div className="profile-nav">
        <button className="ghost" onClick={onBack}>← {backLabel}</button>
        <button type="button" onClick={() => onPdf && onPdf()} disabled={pdfBusyAny || !onPdf}>
          {pdfBusyAny ? "Preparing…" : "Share"}
        </button>
      </div>
      <div className={"hero card" + heroClass(detail.status)}>
        <div>
          <h2>{detail.name}</h2>
          <p className="muted">
            {detail.customer_count || 0} {(detail.customer_count || 0) === 1 ? "customer" : "customers"}
            {detail.last_sale_label ? " · Last sale " + detail.last_sale_label : ""}
            {detail.as_of_label ? " · As of " + detail.as_of_label : ""}
          </p>
          <DueDaysEditor
            entity="rep"
            uk={detail.uk}
            detail={detail}
            canEdit={canEditDueDays}
            onSaved={() => onReload && onReload()}
          />
          {orderLine ? <p className="muted" style={{ marginTop: 6 }}>{orderLine}</p> : null}
        </div>
        <div className="hero-due">
          <span className="muted">This year sales</span>
          <div className="hero-num">{money(detail.ytd_sales)}</div>
          <span className={"pill " + statusClass(detail.status)}>{insight.health_label || detail.status_label || statusLabel(detail.status)}</span>
          {detail.ordered_overdue ? <span className="pill order-overdue">Ordered overdue</span> : null}
        </div>
      </div>
      <div className="buy-tiles">
        <div className="card buy-tile"><span className="muted">Due</span><strong>{money(detail.credit ? Math.abs(detail.due) : detail.due)}</strong></div>
        <div className="card buy-tile"><span className="muted">This year collected</span><strong>{money(detail.ytd_collection)}</strong></div>
        <div className="card buy-tile"><span className="muted">Last sale</span><strong>{detail.last_sale_label || "—"}</strong></div>
        <div className="card buy-tile"><span className="muted">Open amounts</span><strong>{detail.invoices_waiting || 0}</strong></div>
      </div>
      {insight.money_bit || insight.action ? (
        <p className="muted next-move">{[insight.money_bit, insight.action].filter(Boolean).join(" ")}</p>
      ) : null}
      <SectionTabs
        label="Sales rep sections"
        storageKey="rep"
        sticky
        groups={repTabGroups(detail)}
        value={tab}
        onChange={setTab}
      />
      <div className="tab-panel">
        {tab === "customers" ? (
          sectionPending ? <p className="muted">Loading customers…</p> :
          <MemberCustomersTable
            rows={view.customers}
            extra={{
              id: "group",
              label: "Group",
              get: (row) => row.group,
              href: (row) => row.group ? "group/" + encodeURIComponent(row.group) : "",
            }}
          />
        ) : null}
        {tab === "due" ? (
          sectionPending ? <p className="muted">Loading what they owe…</p> :
          <div className="card">
            <h3>What they owe</h3>
            <AgeBar parts={ageParts(detail.owe_buckets, detail.aging_bands)} title="Outstanding by age" selected={dueBand} onSelect={setDueBand} />
            {dueInvoices.length ? (
              <div className="table-wrap">
                <table className="dense list-table compact">
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>Customer</th>
                      <th>Invoice</th>
                      <th>What</th>
                      <th>Still due</th>
                      <th>Age</th>
                    </tr>
                  </thead>
                  <tbody>
                    {dueInvoices.map((line, i) => (
                      <tr key={i} className={line.kind === "opening" ? "total" : ""}>
                        <td>{line.date_label}</td>
                        <td>
                          {line.customer_uk ? (
                            <button type="button" className="linkish" onClick={() => hashSet("customer/" + encodeURIComponent(line.customer_uk))}>{line.party}</button>
                          ) : (line.party || "—")}
                        </td>
                        <td>
                          {line.invoice_id && canSales ? (
                            <button type="button" className="linkish" onClick={() => hashSet("invoice/" + encodeURIComponent(line.invoice_id))}>{line.invoice || "Sale"}</button>
                          ) : (line.invoice || "—")}
                        </td>
                        <td>{line.what}</td>
                        <td>{money(line.due)}</td>
                        <td>{line.age_days} days</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <p className="muted">{dueBand ? "No invoices in " + (ageLabel(dueBand, detail.aging_bands) + " days") + "." : "Nothing waiting."}</p>}
          </div>
        ) : null}
        {tab === "settlements" ? (sectionPending ? <p className="muted">Loading settlements…</p> : <SettlementsPanel detail={view} showParty />) : null}
        {tab === "sales" ? (
          <>
            {sectionPending ? <p className="muted">Loading sales…</p> : <SalesGapsPanel detail={view} showParty />}
          </>
        ) : null}
        {tab === "repurchase" ? <RepurchasePanel detail={detail} entity="rep" showCustomer showItem /> : null}
        {tab === "ordering" ? (sectionPending ? <p className="muted">Loading ordering…</p> : <OrderingPanel detail={view} showParty />) : null}
        {tab === "order-check" ? (
          <OrderCheckPanel entity="rep" detail={detail} canEdit={canEditDueDays} onSaved={() => onReload && onReload()} />
        ) : null}
        {tab === "groups" ? (
          <div className="card table-card list-panel">
            <h3>Customer groups</h3>
            {(detail.groups || []).length ? (
              <div className="table-wrap">
                <table className="dense list-table compact">
                  <thead>
                    <tr>
                      <th>Group</th>
                      <th>Status</th>
                      <th className="num">Customers</th>
                      <th>Last sale</th>
                      <th className="num">This year</th>
                      <th className="num">Collected</th>
                      <th className="num">Due</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(detail.groups || []).map((row) => (
                      <tr key={row.uk} className="click-row" onClick={() => hashSet("group/" + encodeURIComponent(row.uk))}>
                        <td>
                          <div className="name-cell">
                            <span className="avatar sm">{initials(row.name)}</span>
                            <div>
                              <span className="clip"><strong>{row.name}</strong></span>
                              {(row.urgent_count || row.followup_count) ? (
                                <div className="quiet" style={{ fontSize: 12 }}>
                                  {[
                                    row.urgent_count ? row.urgent_count + " urgent" : "",
                                    row.followup_count ? row.followup_count + " follow up" : "",
                                  ].filter(Boolean).join(" · ")}
                                </div>
                              ) : null}
                            </div>
                          </div>
                        </td>
                        <td>
                          <span className={"pill " + statusClass(row.status)}>{row.status_label || statusLabel(row.status)}</span>
                          {row.ordered_overdue ? <span className="pill order-overdue">Ordered overdue</span> : null}
                        </td>
                        <td className="num">{row.customers}</td>
                        <td className="quiet">{row.last_sale_label || "—"}</td>
                        <td className="num amount">{money(row.ytd_sales)}</td>
                        <td className="num amount">{money(row.ytd_collection)}</td>
                        <td className={"num amount" + (row.credit ? " credit" : "")}>{row.credit ? money(Math.abs(row.due)) : money(row.due)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <p className="muted">No customer groups on their book.</p>}
          </div>
        ) : null}
        {tab === "years" ? <YearBlock fy={detail.fy_years || []} /> : null}
        {tab === "quantity" ? <QtyYearBlock fy={detail.fy_years || []} /> : null}
        {tab === "buying" ? (
          sectionPending ? <p className="muted">Loading buying…</p> :
          <div>
            {buying.last_order_date ? <p className="muted">Last order {buying.last_order_date}</p> : null}
            <div className="chips">
              {BUYING_PERIODS.map((id) => (
                <button type="button" key={id} className={period === id ? "" : "secondary"} onClick={() => setPeriod(id)}>
                  {(periods[id] || {}).label || id}
                </button>
              ))}
            </div>
            <div className="card table-card list-panel">
              <h3>{(periods[period] || {}).label || "Buying"}</h3>
              {periodItems.length ? (
                <table className="dense list-table compact">
                  <thead>
                    <tr>
                      <th>Item</th>
                      <th className="num">Qty</th>
                      <th className="num">Amount</th>
                      <th className="num">Times</th>
                      <th>Last bought</th>
                    </tr>
                  </thead>
                  <tbody>
                    {periodItems.map((item) => (
                      <tr key={item.name}>
                        <td><ItemLink uk={item.item_uk} name={item.name} enabled={canStock} /></td>
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
          </div>
        ) : null}
        {tab === "activity" ? (
          sectionPending ? <p className="muted">Loading activity…</p> :
          <div className="card table-card list-panel">
            <h3>Activity</h3>
            {(view.activity || []).length ? (
              <table className="dense list-table compact">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Type</th>
                    <th>Customer</th>
                    <th>Detail</th>
                    <th className="num">Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {(view.activity || []).map((e, i) => (
                    <tr key={e.invoice_id || e.kind + e.date + i}>
                      <td>{e.date_label}</td>
                      <td><span className={"pill act-" + (e.kind === "sale" || e.kind === "collection" || e.kind === "credit_note" ? e.kind : "logged")}>{e.label}</span></td>
                      <td>{e.party || "—"}</td>
                      <td>
                        {e.kind === "sale" && e.invoice_id && canSales ? (
                          <button type="button" className="linkish" onClick={() => hashSet("invoice/" + encodeURIComponent(e.invoice_id))}>{e.invoice || "Invoice"}</button>
                        ) : (e.invoice || e.note || "—")}
                      </td>
                      <td className="num">{money(e.amount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : <p className="muted">No sales or collections for this salesperson.</p>}
          </div>
        ) : null}
      </div>
    </div>
  );
}

const emptyFilters = { group: "", status: "" };

export default function RepsPage({ user, runId }) {
  const [filters, setFilters] = useState(emptyFilters);
  const [q, setQ] = useState("");
  const [qDebounced, setQDebounced] = useState("");
  const [sort, setSort] = useState("ytd_sales");
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

  function loadList(nextFilters, nextPage, nextSort, nextDir, nextQ) {
    setLoading(true);
    api.reps({
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

  useEffect(() => {
    const h = hashGet();
    if (h.startsWith("rep/")) setUk(h.slice("rep/".length));
  }, []);

  useEffect(() => {
    function onHash() {
      const h = hashGet();
      if (h.startsWith("rep/")) setUk(h.slice("rep/".length));
      else if (!h) {
        setUk("");
        setDetail(null);
      }
    }
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  useEffect(() => {
    if (!uk) return undefined;
    setDetail(null);
    api.rep(uk, { run: runId || "", view: "profile" }).then(setDetail).catch((e) => setErr(e.message));
    return undefined;
  }, [uk, runId]);

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
            backLabel={hashReturnLabel("Sales reps")}
            onBack={() => hashBack("")}
            onReload={() => api.rep(uk, { run: runId || "", view: "profile" }).then(setDetail).catch((e) => setErr(e.message))}
            pdfBusy={pdfBusy}
            onPdf={() => {
              setPdfBusy(true);
              api.repPdf(uk, detail.name, { run: runId || "" })
                .catch((e) => setErr(e.message || "PDF failed"))
                .finally(() => setPdfBusy(false));
            }}
          />
        </>
      );
    }
    return (
      <div className="card">
        {err ? <p className="err">{err}</p> : <p className="muted">Opening salesperson…</p>}
        <button className="ghost" onClick={() => hashBack("")}>← {hashReturnLabel("Sales reps")}</button>
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
          const next = toggleSort(sort, dir, id, ["due", "customers", "ytd_sales", "last_sale", ...AGE_KEYS]);
          setSort(next.sort);
          setDir(next.dir);
        }}
        onSortChange={(next) => {
          setSort(next.sort);
          setDir(next.dir);
        }}
        onOpen={(next) => { setUk(next); hashSet("rep/" + encodeURIComponent(next)); }}
        onPage={(p) => { setPage(p); loadList(filters, p, sort, dir, qDebounced); }}
      />
    </>
  );
}
