import { useEffect, useState } from "react";
import SectionTabs, { rememberedTab } from "./SectionTabs";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "./api";
import { EmptyCard, ListPager, SortTh, toggleSort } from "./FilterBar";
import { hashBack, hashGet, hashReturnLabel, hashSet, initials, money, moneyOrDash } from "./format";
import { CHART } from "./theme";
import RepurchasePanel from "./RepurchasePanel";
const PREFIX = {
  category: "category/",
  item_group: "item-group/",
  brand: "brand/",
  supplier: "supplier/",
};

const NUMERIC = ["items", "qty", "stock_value", "sales_qty", "sales_value", "buy_qty", "buy_value", "low_count", "soon_count", "under_count", "dead_count", "out_count", "days_cover", "last_sale"];

const MIX = {
  category: [
    ["brand_count", "brand", "brands"],
    ["item_group_count", "item group", "item groups"],
    ["supplier_count", "supplier", "suppliers"],
  ],
  item_group: [
    ["category_count", "category", "categories"],
    ["brand_count", "brand", "brands"],
    ["supplier_count", "supplier", "suppliers"],
  ],
  brand: [
    ["category_count", "category", "categories"],
    ["item_group_count", "item group", "item groups"],
    ["supplier_count", "supplier", "suppliers"],
  ],
  supplier: [
    ["category_count", "category", "categories"],
    ["item_group_count", "item group", "item groups"],
    ["brand_count", "brand", "brands"],
  ],
};

const MEMBER_COLS = {
  category: [
    { key: "item_group", uk: "item_group_uk", hash: "item-group/", label: "Item group" },
    { key: "brand", uk: "brand_uk", hash: "brand/", label: "Brand" },
    { key: "supplier", uk: "supplier_uk", hash: "supplier/", label: "Supplier" },
  ],
  item_group: [
    { key: "category", uk: "category_uk", hash: "category/", label: "Category" },
    { key: "brand", uk: "brand_uk", hash: "brand/", label: "Brand" },
    { key: "supplier", uk: "supplier_uk", hash: "supplier/", label: "Supplier" },
  ],
  brand: [
    { key: "category", uk: "category_uk", hash: "category/", label: "Category" },
    { key: "item_group", uk: "item_group_uk", hash: "item-group/", label: "Item group" },
    { key: "supplier", uk: "supplier_uk", hash: "supplier/", label: "Supplier" },
  ],
  supplier: [
    { key: "category", uk: "category_uk", hash: "category/", label: "Category" },
    { key: "item_group", uk: "item_group_uk", hash: "item-group/", label: "Item group" },
    { key: "brand", uk: "brand_uk", hash: "brand/", label: "Brand" },
  ],
};

function mixLine(row, dimension) {
  return (MIX[dimension] || []).map(([key, one, many]) => {
    const n = Number(row?.[key] || 0);
    if (!n) return "";
    return n + " " + (n === 1 ? one : many);
  }).filter(Boolean).join(" · ");
}

function healthLine(totals) {
  if (!totals) return "";
  return [
    totals.under_count ? totals.under_count + " understocked" : "",
    totals.over_count ? totals.over_count + " overstocked" : "",
    totals.dead_count ? totals.dead_count + " dead" : "",
    totals.out_count ? totals.out_count + " not in stock" : "",
    totals.stopped_count ? totals.stopped_count + " discontinued" : "",
    totals.up_count ? totals.up_count + " up" : "",
    totals.down_count ? totals.down_count + " down" : "",
  ].filter(Boolean).join(" · ");
}

const PAGE_SIZE = 50;

function slicePage(rows, page) {
  const start = ((page || 1) - 1) * PAGE_SIZE;
  return (rows || []).slice(start, start + PAGE_SIZE);
}

function BuyerTabs({ detail }) {
  const [tab, setTab] = useState("group");
  const [page, setPage] = useState(1);
  if (!("groups" in (detail || {})) && !("reps" in (detail || {}))) {
    return (
      <EmptyCard
        title="Customer group and sales rep"
        copy="Create the report again to see how these items sell by customer group and salesperson."
      />
    );
  }
  const rows = tab === "group" ? (detail.groups || []) : (detail.reps || []);
  const shown = slicePage(rows, page);
  const whole = (detail.overall || {}).amount || 0;
  const hash = tab === "group" ? "group/" : "rep/";
  return (
    <div className="card">
      <h3>Who bought</h3>
      <div className="chips">
        <button type="button" className={tab === "group" ? "" : "secondary"} onClick={() => { setTab("group"); setPage(1); }}>Customer group</button>
        <button type="button" className={tab === "rep" ? "" : "secondary"} onClick={() => { setTab("rep"); setPage(1); }}>Sales rep</button>
      </div>
      {shown.length ? (
        <table className="dense list-table" style={{ marginTop: 12 }}>
          <thead>
            <tr>
              <th>{tab === "group" ? "Customer group" : "Sales rep"}</th>
              <th className="num">Sold</th>
              <th className="num">Sales</th>
              <th className="num">Share</th>
              <th className="num">Lines</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((row) => (
              <tr key={row.uk || row.name}>
                <td>
                  {row.none || !row.name ? row.name : (
                    <button type="button" className="linkish" onClick={() => hashSet(hash + encodeURIComponent(row.uk || row.name))}>
                      {row.name}
                    </button>
                  )}
                </td>
                <td className="num">{qty(row.qty)}</td>
                <td className="num">{money(row.amount)}</td>
                <td className="num quiet">{share(row.amount, whole)}</td>
                <td className="num">{row.times || 0}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : <p className="muted">No sales yet.</p>}
      <ListPager page={page} total={rows.length} onPage={setPage} />
    </div>
  );
}

function AttrLink({ row, col }) {
  const name = row[col.key];
  if (!name) return "—";
  return (
    <button type="button" className="linkish" onClick={() => hashSet(col.hash + encodeURIComponent(row[col.uk] || name))}>
      {name}
    </button>
  );
}

function qty(n) {
  const v = Number(n || 0);
  if (!v) return "0";
  return String(Math.round(v * 100) / 100);
}

function share(part, whole) {
  const total = Number(whole || 0);
  if (!total) return "—";
  return (Math.round(1000 * Number(part || 0) / total) / 10) + "%";
}

function pillClass(status) {
  if (status === "up") return "ok";
  if (status === "down" || status === "low" || status === "under") return "err";
  if (status === "soon" || status === "over" || status === "tight") return "warn";
  if (status === "ok" || status === "balanced" || status === "flat") return "ok";
  if (status === "stopped" || status === "dead") return "stopped";
  return "";
}

function Summary({ totals, hasValue }) {
  if (!totals) return null;
  const buyNote = [
    totals.low_count ? totals.low_count + " below min" : "",
    totals.soon_count ? totals.soon_count + " this week" : "",
  ].filter(Boolean).join(" · ");
  return (
    <>
    <div className="buy-tiles">
      <div className="card buy-tile">
        <span className="muted">On hand</span>
        <strong>{qty(totals.qty)}</strong>
        <span className="quiet">{totals.items} {totals.items === 1 ? "item" : "items"}</span>
      </div>
      {hasValue ? (
        <div className="card buy-tile">
          <span className="muted">Stock value</span>
          <strong>{money(totals.stock_value)}</strong>
        </div>
      ) : null}
      <div className="card buy-tile">
        <span className="muted">Sales this year</span>
        <strong>{money(totals.sales_value)}</strong>
        <span className="quiet">{qty(totals.sales_qty)} sold</span>
      </div>
      <div className="card buy-tile">
        <span className="muted">To buy</span>
        <strong>{qty(totals.buy_qty)}</strong>
        <span className="quiet">{buyNote || (totals.buy_value ? money(totals.buy_value) : "Nothing waiting")}</span>
      </div>
    </div>
    {healthLine(totals) ? <p className="muted">{healthLine(totals)}</p> : null}
  </>
  );
}

function SalesChart({ rows, labelKey, dataKey, name }) {
  if (!rows || rows.length < 2) return null;
  return (
    <div style={{ width: "100%", height: 220, marginTop: 12 }}>
      <ResponsiveContainer>
        <BarChart data={rows}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey={labelKey} />
          <YAxis />
          <Tooltip />
          <Bar dataKey={dataKey} name={name} fill={CHART.sales} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function SalesTabs({ detail }) {
  const [tab, setTab] = useState("overall");
  const [measure, setMeasure] = useState("amount");
  const [page, setPage] = useState(1);
  const overall = detail.overall;
  const months = detail.months || [];
  const years = detail.fy_years || [];
  const monthRows = slicePage(months, page);
  const quantity = measure === "qty";
  if (!overall && !months.length && !years.length) {
    return (
      <EmptyCard
        title="Sales by period"
        copy="Create the report again to see overall, monthly, and fiscal-year sales."
      />
    );
  }
  return (
    <div className="card">
      <div className="chips">
        <button type="button" className={measure === "amount" ? "" : "secondary"} onClick={() => setMeasure("amount")}>Amount</button>
        <button type="button" className={quantity ? "" : "secondary"} onClick={() => setMeasure("qty")}>Quantity</button>
      </div>
      <div className="chips">
        {[
          ["overall", "Overall"],
          ["monthly", "Monthly"],
          ["fy", "FY"],
        ].map(([id, label]) => (
          <button type="button" key={id} className={tab === id ? "" : "secondary"} onClick={() => { setTab(id); setPage(1); }}>
            {label}
          </button>
        ))}
      </div>
      {tab === "overall" ? (
        <div className="fy-grid" style={{ marginTop: 12 }}>
          <div className="fy-card">
            <div className="fy-label">All sales</div>
            {quantity ? (
              <div className="fy-metric sales"><span className="muted">Sold</span> <strong>{qty((overall || {}).qty)}</strong></div>
            ) : (
              <div className="fy-metric sales"><span className="muted">Sales</span> <strong>{money((overall || {}).amount || 0)}</strong></div>
            )}
            <div className="fy-metric"><span className="muted">Lines</span> <strong>{(overall || {}).times || 0}</strong></div>
          </div>
        </div>
      ) : null}
      {tab === "monthly" ? (
        months.length ? (
          <>
            <SalesChart rows={months} labelKey="label" dataKey={quantity ? "qty" : "amount"} name={quantity ? "Quantity" : "Sales"} />
            <table className="dense list-table" style={{ marginTop: 12 }}>
              <thead>
                <tr>
                  <th>Month</th>
                  <th className="num">{quantity ? "Sold" : "Sales"}</th>
                  <th className="num">Lines</th>
                </tr>
              </thead>
              <tbody>
                {monthRows.map((row) => (
                  <tr key={row.key}>
                    <td>{row.label}</td>
                    <td className="num">{quantity ? qty(row.qty) : money(row.amount)}</td>
                    <td className="num">{row.times || 0}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <ListPager page={page} total={months.length} onPage={setPage} />
          </>
        ) : <p className="muted">No monthly sales yet.</p>
      ) : null}
      {tab === "fy" ? (
        years.length ? (
          <>
            <div className="fy-grid" style={{ marginTop: 12 }}>
              {years.map((row) => (
                <div className="fy-card" key={row.start || row.label}>
                  <div className="fy-label">{row.label}</div>
                  {quantity ? (
                    <div className="fy-metric sales"><span className="muted">Sold</span> <strong>{qty(row.qty)}</strong></div>
                  ) : (
                    <div className="fy-metric sales"><span className="muted">Sales</span> <strong>{money(row.amount)}</strong></div>
                  )}
                </div>
              ))}
            </div>
            <SalesChart rows={years.slice().reverse()} labelKey="label" dataKey={quantity ? "qty" : "amount"} name={quantity ? "Quantity" : "Sales"} />
          </>
        ) : <p className="muted">No fiscal-year sales yet.</p>
      ) : null}
    </div>
  );
}

function Directory({ label, plural, q, setQ, data, page, loading, sort, dir, onSort, onOpen, onPage }) {
  const [tab, setTab] = useState(() => rememberedTab("item-dir:" + (label || "items"), "sales", ["sales", "stock"]));
  const noun = data?.total === 1 ? (label || "row").toLowerCase() : (plural || "rows");
  const showValue = Boolean(data?.totals?.has_stock_value);
  return (
    <div className="workspace-page aging-page">
      <div className="page-head">
        <div className="page-head-copy">
          <h2>{plural ? plural.charAt(0).toUpperCase() + plural.slice(1) : label}</h2>
          <p className="muted">Stock on hand, sales this year, and items that need a buy.</p>
        </div>
        <div className="page-head-tools">
          <input
            className="search-input"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={"Search " + (label || "").toLowerCase()}
          />
          <span className="page-stat">
            {data ? `${data.total} ${noun}` : "…"}
            {loading && data ? " · Updating…" : ""}
          </span>
        </div>
      </div>
      {loading && !data ? <EmptyCard title={"Loading " + (plural || "rows")} copy="Reading the saved 360 view." /> : null}
      {!loading && data?.needs_rebuild ? (
        <EmptyCard
          title="Saved with the report"
          copy="Create the report again. Category, item group, brand, and supplier are read from that saved 360 view, including items with no value."
        />
      ) : null}
      {!loading && data && !data.needs_rebuild && !data.rows?.length ? (
        <EmptyCard title="Nothing matches" copy="Clear the search, or map this column on a stock or item-wise sales file and create the report again." />
      ) : null}
      {data?.rows?.length ? <Summary totals={data.totals} hasValue={showValue} /> : null}
      {data?.rows?.length ? (
        <>
          <SectionTabs
            label={(label || "Dimension") + " list"}
            storageKey={"item-dir:" + (label || "items")}
            sticky
            value={tab}
            onChange={setTab}
            tabs={[
              { id: "sales", label: "Sales" },
              { id: "stock", label: "Stock" },
            ]}
          />
          <div className="tab-panel" role="tabpanel">
            <div className="card table-card list-panel">
              <table className="dense list-table">
                <thead>
                  <tr>
                    <SortTh id="name" label={label || "Name"} sort={sort} dir={dir} onSort={onSort} />
                    <SortTh id="items" label="Items" sort={sort} dir={dir} onSort={onSort} className="num" />
                    {tab === "sales" ? (
                      <>
                        <SortTh id="sales_qty" label="Sold" sort={sort} dir={dir} onSort={onSort} className="num" />
                        <SortTh id="sales_value" label="Sales" sort={sort} dir={dir} onSort={onSort} className="num" />
                        <th className="num">Share</th>
                        <SortTh id="last_sale" label="Last sale" sort={sort} dir={dir} onSort={onSort} />
                      </>
                    ) : (
                      <>
                        <SortTh id="qty" label="On hand" sort={sort} dir={dir} onSort={onSort} className="num" />
                        {showValue ? <SortTh id="stock_value" label="Stock value" sort={sort} dir={dir} onSort={onSort} className="num" /> : null}
                        <SortTh id="days_cover" label="Days left" sort={sort} dir={dir} onSort={onSort} className="num" />
                        <SortTh id="low_count" label="Below min" sort={sort} dir={dir} onSort={onSort} className="num" />
                        <SortTh id="buy_qty" label="To buy" sort={sort} dir={dir} onSort={onSort} className="num" />
                      </>
                    )}
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((row) => (
                    <tr key={row.uk} className="click-row" onClick={() => onOpen(row.uk)}>
                      <td>
                        <div className="name-cell">
                          <span className="avatar sm">{initials(row.name)}</span>
                          <span className="clip" title={row.name}>
                            <strong>{row.name}</strong>
                            {row.trend_label ? <span className={"pill " + pillClass(row.trend)}>{row.trend_label}</span> : null}
                            {(row.up_count || row.down_count) ? (
                              <span className="quiet"> · {row.up_count || 0} up · {row.down_count || 0} down</span>
                            ) : null}
                            {mixLine(row, data.dimension) ? <span className="quiet"> · {mixLine(row, data.dimension)}</span> : null}
                          </span>
                        </div>
                      </td>
                      <td className="num">{row.items}</td>
                      {tab === "sales" ? (
                        <>
                          <td className="num">{qty(row.sales_qty)}</td>
                          <td className="num">{money(row.sales_value)}</td>
                          <td className="num quiet">{share(row.sales_value, data.totals?.sales_value)}</td>
                          <td className="quiet">{row.last_sale_label || "—"}</td>
                        </>
                      ) : (
                        <>
                          <td className="num">{qty(row.qty)}</td>
                          {showValue ? <td className="num">{moneyOrDash(row.stock_value)}</td> : null}
                          <td className="num">{row.days_cover == null ? "—" : row.days_cover}</td>
                          <td className="num">{row.low_count ? row.low_count : "—"}</td>
                          <td className="num">{row.buy_qty ? qty(row.buy_qty) : "—"}</td>
                        </>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      ) : null}
      <ListPager page={page} total={data?.total} onPage={onPage} />
    </div>
  );
}

const ITEM_DETAIL_TABS = ["overview", "sales", "repurchase", "buyers", "items"];

function Detail({ detail, onBack, backLabel, members, memberTotal, membersLoading, onItems }) {
  const [tab, setTab] = useState(() => rememberedTab("item-detail:" + (detail.dimension || "item"), "overview", ITEM_DETAIL_TABS));
  const [focus, setFocus] = useState("all");
  const [itemPage, setItemPage] = useState(1);
  useEffect(() => {
    if (tab !== "items" || !onItems) return undefined;
    onItems(focus, itemPage);
    return undefined;
  }, [tab, focus, itemPage, detail.uk]);
  const itemRows = members || [];
  const hasValue = detail.stock_value != null || itemRows.some((row) => row.value != null);
  const attrCols = MEMBER_COLS[detail.dimension] || [];
  const sections = [
    { id: "overview", label: "Overview" },
    { id: "sales", label: "Sales" },
    { id: "repurchase", label: "Repurchase" },
    { id: "buyers", label: "Who bought" },
    { id: "items", label: "Items", count: detail.items ? detail.items : null },
  ];
  return (
    <div className="workspace-page">
      <div className="profile-nav">
        <button className="ghost" onClick={onBack}>← {backLabel || detail.dimension_label}</button>
      </div>
      <div className="hero card">
        <div>
          <h2>{detail.name}</h2>
          <p className="muted">
            {detail.items} {detail.items === 1 ? "item" : "items"}
            {mixLine(detail, detail.dimension) ? " · " + mixLine(detail, detail.dimension) : ""}
            {detail.last_sale_label ? " · Last sale " + detail.last_sale_label : ""}
            {detail.days_cover != null ? " · " + detail.days_cover + " days left" : ""}
          </p>
          {detail.trend_label ? (
            <div className="hero-pills">
              <span className={"pill " + pillClass(detail.trend)}>{detail.trend_label}</span>
              <span className="muted">
                {(detail.up_count || 0) + " up · " + (detail.down_count || 0) + " down · " + (detail.flat_count || 0) + " steady"}
              </span>
            </div>
          ) : null}
        </div>
        <div className="hero-due">
          <span className="muted">Sales this year</span>
          <div className="hero-num">{money(detail.sales_value)}</div>
          <span className="muted">{qty(detail.sales_qty)} sold</span>
        </div>
      </div>
      <SectionTabs
        label={detail.dimension_label || "Sections"}
        storageKey={"item-detail:" + (detail.dimension || "item")}
        sticky
        tabs={sections}
        value={tab}
        onChange={setTab}
      />
      <div className="tab-panel" role="tabpanel">
      {tab === "overview" ? (
        <Summary
          totals={{
            items: detail.items,
            qty: detail.qty,
            stock_value: detail.stock_value,
            sales_qty: detail.sales_qty,
            sales_value: detail.sales_value,
            buy_qty: detail.buy_qty,
            buy_value: detail.buy_value,
            low_count: detail.low_count,
            soon_count: detail.soon_count,
            under_count: detail.under_count,
            over_count: detail.over_count,
            dead_count: detail.dead_count,
            out_count: detail.out_count,
            stopped_count: detail.stopped_count,
            up_count: detail.up_count,
            down_count: detail.down_count,
          }}
          hasValue={detail.stock_value != null}
        />
      ) : null}
      {tab === "sales" ? <SalesTabs detail={detail} /> : null}
      {tab === "repurchase" ? <RepurchasePanel detail={detail} entity={detail.dimension || "category"} showCustomer showItem /> : null}
      {tab === "buyers" ? <BuyerTabs detail={detail} /> : null}
      {tab === "items" ? (
      <>
      <div className="chips stock-presets">
        {[
          { id: "all", label: "All items" },
          { id: "buy", label: (detail.low_count || 0) + (detail.soon_count || 0) ? "Need a buy · " + ((detail.low_count || 0) + (detail.soon_count || 0)) : "Need a buy" },
          { id: "low", label: detail.low_count ? "Below min · " + detail.low_count : "Below min" },
          { id: "soon", label: detail.soon_count ? "Buy this week · " + detail.soon_count : "Buy this week" },
          { id: "under", label: detail.under_count ? "Understocked · " + detail.under_count : "Understocked" },
          { id: "dead", label: detail.dead_count ? "Dead stock · " + detail.dead_count : "Dead stock" },
          { id: "out", label: detail.out_count ? "Not in stock · " + detail.out_count : "Not in stock" },
          { id: "up", label: detail.up_count ? "Up · " + detail.up_count : "Up" },
          { id: "down", label: detail.down_count ? "Down · " + detail.down_count : "Down" },
        ].map((chip) => (
          <button type="button" key={chip.id} className={focus === chip.id ? "" : "secondary"} onClick={() => { setFocus(chip.id); setItemPage(1); }}>
            {chip.label}
          </button>
        ))}
      </div>
      {membersLoading && !itemRows.length ? <p className="muted">Loading items…</p> : null}
      {!membersLoading && itemRows.length ? (
        <>
        <div className="card table-card list-panel">
          <table className="dense list-table">
            <thead>
              <tr>
                <th>Item</th>
                {attrCols.map((col) => <th key={col.key}>{col.label}</th>)}
                <th className="num">On hand</th>
                {hasValue ? <th className="num">Stock value</th> : null}
                <th className="num">Sold</th>
                <th className="num">Sales</th>
                <th className="num">Share</th>
                <th className="num">Days left</th>
                <th>Stock</th>
                <th>Buy</th>
                <th className="num">To buy</th>
              </tr>
            </thead>
            <tbody>
              {itemRows.map((row) => (
                <tr key={row.uk}>
                  <td>
                    <button type="button" className="linkish" onClick={() => hashSet("item/" + encodeURIComponent(row.uk))}>
                      {row.name}
                    </button>
                    {row.trend_label ? <span className={"pill " + pillClass(row.trend)}>{row.trend_label}</span> : null}
                  </td>
                  {attrCols.map((col) => (
                    <td key={col.key}><AttrLink row={row} col={col} /></td>
                  ))}
                  <td className="num">{qty(row.qty)}</td>
                  {hasValue ? <td className="num">{moneyOrDash(row.value)}</td> : null}
                  <td className="num">{qty(row.sales_qty)}</td>
                  <td className="num">{money(row.sales_value)}</td>
                  <td className="num quiet">{share(row.sales_value, detail.sales_value)}</td>
                  <td className="num">{row.days_cover == null ? "—" : row.days_cover}</td>
                  <td>{row.stock_position_label ? <span className={"pill " + pillClass(row.stock_position)}>{row.stock_position_label}</span> : "—"}</td>
                  <td>{row.status_label ? <span className={"pill " + pillClass(row.status)}>{row.status_label}</span> : "—"}</td>
                  <td className="num">{row.buy_qty ? qty(row.buy_qty) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <ListPager page={itemPage} total={memberTotal} onPage={setItemPage} />
        </>
      ) : null}
      {!membersLoading && !itemRows.length ? (
        <EmptyCard title="No items in this filter" copy="Choose All items to see every item here." />
      ) : null}
      </>
      ) : null}
      </div>
    </div>
  );
}

export default function ItemDimsPage({ dimension, runId }) {
  const prefix = PREFIX[dimension] || "category/";
  const [q, setQ] = useState("");
  const [data, setData] = useState(null);
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState("sales_value");
  const [dir, setDir] = useState("desc");
  const [loading, setLoading] = useState(false);
  const [uk, setUk] = useState("");
  const [detail, setDetail] = useState(null);
  const [members, setMembers] = useState([]);
  const [memberTotal, setMemberTotal] = useState(0);
  const [membersLoading, setMembersLoading] = useState(false);
  const [err, setErr] = useState("");

  function loadList(nextQ, nextPage, nextSort, nextDir) {
    setLoading(true);
    api.itemDims(dimension, {
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
    setPage(1);
    setData(null);
    loadList(q, 1, sort, dir);
  }, [dimension, q, sort, dir, runId]);

  function applyHash(h) {
    if (h.startsWith(prefix)) {
      setUk(decodeURIComponent(h.slice(prefix.length)));
      return;
    }
    setUk("");
    setDetail(null);
  }

  useEffect(() => {
    applyHash(hashGet());
  }, [dimension]);

  useEffect(() => {
    function onHash() {
      applyHash(hashGet());
    }
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, [dimension]);

  useEffect(() => {
    if (!uk) return undefined;
    setDetail(null);
    setMembers([]);
    setMemberTotal(0);
    api.itemDim(dimension, uk, { run: runId || "" }).then(setDetail).catch((e) => setErr(e.message));
    return undefined;
  }, [dimension, uk, runId]);

  function loadMembers(focus, page) {
    if (!uk) return;
    setMembersLoading(true);
    api.itemDim(dimension, uk, {
      run: runId || "",
      members: "1",
      focus,
      page: String(page || 1),
    })
      .then((row) => {
        setMembers(row.members || []);
        setMemberTotal(row.member_total || 0);
      })
      .catch((e) => setErr(e.message))
      .finally(() => setMembersLoading(false));
  }

  if (uk) {
    if (detail && detail.uk === uk) {
      return (
        <>
          {err ? <p className="err">{err}</p> : null}
          <Detail
            detail={detail}
            backLabel={hashReturnLabel(data?.label || "Back")}
            onBack={() => hashBack("")}
            members={members}
            memberTotal={memberTotal}
            membersLoading={membersLoading}
            onItems={loadMembers}
          />
        </>
      );
    }
    return (
      <div className="card">
        {err ? <p className="err">{err}</p> : <p className="muted">Opening…</p>}
        <button className="ghost" onClick={() => hashBack("")}>← {hashReturnLabel(data?.label || "Back")}</button>
      </div>
    );
  }

  return (
    <>
      {err ? <p className="err">{err}</p> : null}
      <Directory
        label={data?.label}
        plural={data?.plural}
        q={q}
        setQ={(value) => { setQ(value); setPage(1); }}
        data={data}
        page={page}
        loading={loading}
        sort={sort}
        dir={dir}
        onSort={(id) => {
          const next = toggleSort(sort, dir, id, NUMERIC);
          setSort(next.sort);
          setDir(next.dir);
        }}
        onOpen={(next) => {
          setUk(next);
          hashSet(prefix + encodeURIComponent(next));
        }}
        onPage={(p) => { setPage(p); loadList(q, p, sort, dir); }}
      />
    </>
  );
}
