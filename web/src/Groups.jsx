import { useEffect, useState } from "react";
import SectionTabs, { rememberedTab } from "./SectionTabs";
import { api } from "./api";
import { CHART, can } from "./theme";
import { AGE_KEYS, AGE_LABELS, ageLabel, bandKey, bucketMoney, hashBack, hashGet, hashReturnLabel, hashSet, initials, money, rowBucket } from "./format";
import AgeBar, { ageParts } from "./AgeBar";
import { EmptyCard, FilterBar, GROUP_FIELDS, GROUP_SORT_OPTIONS, ListPager, MemberCustomersTable, SortTh, toggleSort } from "./FilterBar";
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
          <h2>Customer groups</h2>
          <p className="muted">Search, filter, sort by due age, and open a group.</p>
        </div>
        <div className="page-head-tools">
          <input
            className="search-input"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search group or salesperson"
          />
          <span className="page-stat">
            {data ? `${data.total} ${data.total === 1 ? "group" : "groups"}` : "…"}
            {loading && data ? " · Updating…" : ""}
          </span>
        </div>
      </div>
      <FilterBar
        filters={filters}
        options={data?.options}
        onChange={setFilters}
        fields={GROUP_FIELDS}
        sort={sort}
        dir={dir}
        sortOptions={GROUP_SORT_OPTIONS}
        onSortChange={onSortChange}
      />
      {loading && !data ? <EmptyCard title="Loading groups" copy="Pulling the latest customer groups." /> : null}
      {!loading && !data?.groups?.length ? (
        <EmptyCard title="No groups match" copy="Clear a filter, or import outstanding with a Group column." />
      ) : null}
      {data?.groups?.length ? (
        <div className="card table-card list-panel">
          <table className="dense list-table aging">
            <thead>
              <tr>
                <SortTh id="name" label="Group" sort={sort} dir={dir} onSort={onSort} />
                <SortTh id="customers" label="Customers" sort={sort} dir={dir} onSort={onSort} className="num" />
                <SortTh id="rep" label="Salespeople" sort={sort} dir={dir} onSort={onSort} />
                <SortTh id="status" label="Status" sort={sort} dir={dir} onSort={onSort} />
                <SortTh id="last_sale" label="Last sale" sort={sort} dir={dir} onSort={onSort} />
                <SortTh id="due" label="Due" sort={sort} dir={dir} onSort={onSort} className="num" />
                {AGE_KEYS.map((k) => (
                  <SortTh key={k} id={k} label={AGE_LABELS[k]} sort={sort} dir={dir} onSort={onSort} className="num" />
                ))}
              </tr>
            </thead>
            <tbody>
              {data.groups.map((row) => (
                <tr key={row.uk} className="click-row" onClick={() => onOpen(row.uk)}>
                  <td>
                    <div className="name-cell">
                      <span className="avatar sm">{initials(row.name)}</span>
                      <span className="clip" title={row.name}><strong>{row.name}</strong></span>
                    </div>
                  </td>
                  <td className="num">{row.customers}</td>
                  <td className="clip" title={(row.reps || []).join(", ")}>{(row.reps || []).join(", ") || "—"}</td>
                  <td>
                    <span className={"pill " + statusClass(row.status)}>{row.status_label || statusLabel(row.status)}</span>
                    {row.ordered_overdue ? <span className="pill order-overdue">Ordered overdue</span> : null}
                  </td>
                  <td className="quiet">{row.last_sale_label || "—"}</td>
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

const GROUP_TABS = ["due", "settlements", "sales", "quantity", "years", "buying", "repurchase", "ordering", "order-check", "customers", "reps"];

function groupTabGroups(detail) {
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
      { id: "reps", label: "Salespeople" },
    ] },
  ];
}

function Profile({ detail, runId, canSales, canStock, canEditDueDays, onBack, backLabel, onReload, onPdf, pdfBusy }) {
  const [tab, setTab] = useState(() => rememberedTab("group", "customers", GROUP_TABS));
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
    api.group(detail.uk, { run: runId || detail.run_id || "", section })
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
            entity="group"
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
          <span className={"pill " + statusClass(detail.status)}>{insight.health_label || detail.status_label || statusLabel(detail.status)}</span>
          {detail.ordered_overdue ? <span className="pill order-overdue">Ordered overdue</span> : null}
        </div>
      </div>
      <div className="buy-tiles">
        <div className="card buy-tile"><span className="muted">This year sales</span><strong>{money(detail.ytd_sales)}</strong></div>
        <div className="card buy-tile"><span className="muted">This year collected</span><strong>{money(detail.ytd_collection)}</strong></div>
        <div className="card buy-tile"><span className="muted">Last collection</span><strong>{detail.last_collection_label || "—"}</strong></div>
        <div className="card buy-tile"><span className="muted">Open amounts</span><strong>{detail.invoices_waiting || 0}</strong></div>
      </div>
      {insight.money_bit || insight.action ? (
        <p className="muted next-move">{[insight.money_bit, insight.action].filter(Boolean).join(" ")}</p>
      ) : null}
      <SectionTabs
        label="Group sections"
        storageKey="group"
        sticky
        groups={groupTabGroups(detail)}
        value={tab}
        onChange={setTab}
      />
      <div className="tab-panel">
        {tab === "customers" ? (
          sectionPending ? <p className="muted">Loading customers…</p> :
          <MemberCustomersTable
            rows={view.customers}
            extra={{
              id: "rep",
              label: "Salesperson",
              get: (row) => row.salesperson,
              href: (row) => row.salesperson ? "rep/" + encodeURIComponent(row.salesperson) : "",
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
        {tab === "repurchase" ? <RepurchasePanel detail={detail} entity="group" showCustomer showItem /> : null}
        {tab === "ordering" ? (sectionPending ? <p className="muted">Loading ordering…</p> : <OrderingPanel detail={view} showParty />) : null}
        {tab === "order-check" ? (
          <OrderCheckPanel entity="group" detail={detail} canEdit={canEditDueDays} onSaved={() => onReload && onReload()} />
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
        {tab === "reps" ? (
          <div className="card table-card list-panel">
            <h3>Salespeople</h3>
            {(view.salespeople || detail.salespeople || []).length ? (
              <div className="table-wrap">
                <table className="dense list-table compact">
                  <thead>
                    <tr>
                      <th>Salesperson</th>
                      <th>Status</th>
                      <th className="num">Customers</th>
                      <th>Last sale</th>
                      <th className="num">This year</th>
                      <th className="num">Collected</th>
                      <th className="num">Due</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(view.salespeople || detail.salespeople || []).map((row) => (
                      <tr key={row.uk} className="click-row" onClick={() => hashSet("rep/" + encodeURIComponent(row.uk))}>
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
            ) : <p className="muted">No salesperson on these customers.</p>}
          </div>
        ) : null}
      </div>
    </div>
  );
}

const emptyFilters = { rep: "", status: "" };

export default function GroupsPage({ user, runId }) {
  const [filters, setFilters] = useState(emptyFilters);
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

  function loadList(nextFilters, nextPage, nextSort, nextDir, nextQ) {
    setLoading(true);
    api.groups({
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
    if (h.startsWith("group/")) setUk(h.slice("group/".length));
  }, []);

  useEffect(() => {
    function onHash() {
      const h = hashGet();
      if (h.startsWith("group/")) setUk(h.slice("group/".length));
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
    api.group(uk, { run: runId || "", view: "profile" }).then(setDetail).catch((e) => setErr(e.message));
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
            backLabel={hashReturnLabel("Customer groups")}
            onBack={() => hashBack("")}
            onReload={() => api.group(uk, { run: runId || "", view: "profile" }).then(setDetail).catch((e) => setErr(e.message))}
            pdfBusy={pdfBusy}
            onPdf={() => {
              setPdfBusy(true);
              api.groupPdf(uk, detail.name, { run: runId || "" })
                .catch((e) => setErr(e.message || "PDF failed"))
                .finally(() => setPdfBusy(false));
            }}
          />
        </>
      );
    }
    return (
      <div className="card">
        {err ? <p className="err">{err}</p> : <p className="muted">Opening group…</p>}
        <button className="ghost" onClick={() => hashBack("")}>← {hashReturnLabel("Customer groups")}</button>
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
          const next = toggleSort(sort, dir, id, ["due", "customers", "last_sale", ...AGE_KEYS]);
          setSort(next.sort);
          setDir(next.dir);
        }}
        onSortChange={(next) => {
          setSort(next.sort);
          setDir(next.dir);
        }}
        onOpen={(next) => { setUk(next); hashSet("group/" + encodeURIComponent(next)); }}
        onPage={(p) => { setPage(p); loadList(filters, p, sort, dir, qDebounced); }}
      />
    </>
  );
}
