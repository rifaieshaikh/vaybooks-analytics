import { useEffect, useState } from "react";
import { api } from "./api";
import { hashBack, hashGet, hashReturnLabel, hashSet, initials, money, moneyOrDash } from "./format";
import { EmptyCard, FilterBar, ListPager, SortTh, STOCK_FIELDS, toggleSort } from "./FilterBar";
import { can } from "./theme";
import RepurchasePanel from "./RepurchasePanel";
const ITEM_LINKS = [
  { key: "category", uk: "category_uk", hash: "category/", label: "Category" },
  { key: "item_group", uk: "item_group_uk", hash: "item-group/", label: "Item group" },
  { key: "brand", uk: "brand_uk", hash: "brand/", label: "Brand" },
  { key: "supplier", uk: "supplier_uk", hash: "supplier/", label: "Supplier" },
];

function qty(n) {
  if (n === null || n === undefined || n === "") return "—";
  const v = Number(n);
  if (!Number.isFinite(v)) return "—";
  return v.toLocaleString(undefined, { maximumFractionDigits: 2, minimumFractionDigits: 0 });
}

function pace(n) {
  if (n === null || n === undefined || n === "") return "—";
  const v = Number(n);
  if (!Number.isFinite(v) || v === 0) return "—";
  return qty(v) + "/d";
}

function pillClass(status) {
  if (status === "low" || status === "under") return "err";
  if (status === "soon" || status === "watch" || status === "excess" || status === "over" || status === "tight" || status === "up") return "warn";
  if (status === "ok" || status === "balanced" || status === "flat") return "ok";
  if (status === "stopped" || status === "dead" || status === "down") return "stopped";
  return "";
}

function openEntity(kind, uk, name) {
  const id = uk || name;
  if (!id) return;
  hashSet(kind + "/" + encodeURIComponent(id));
}

function LinkName({ kind, uk, name }) {
  if (!name) return "—";
  return (
    <button
      type="button"
      className="linkish"
      onClick={(e) => { e.stopPropagation(); openEntity(kind, uk, name); }}
    >
      {name}
    </button>
  );
}

function Directory({ filters, setFilters, data, page, loading, sort, dir, onSort, onOpen, onPage, title, copy }) {
  const notes = [];
  if (data?.low_count) notes.push(data.low_count + " below min");
  if (data?.soon_count) notes.push(data.soon_count + " to buy this week");
  if (data?.under_count) notes.push(data.under_count + " understocked");
  if (data?.over_count) notes.push(data.over_count + " overstocked");
  if (data?.dead_count) notes.push(data.dead_count + " dead stock");
  if (data?.out_of_stock_count) notes.push(data.out_of_stock_count + " not in stock file");

  const presets = [
    { id: "all", label: "All", status: "", position: "", in_stock: "" },
    { id: "buy", label: data?.buy_count ? "Buy now · " + data.buy_count : "Buy now", status: "Below min", position: "", in_stock: "" },
    { id: "low", label: data?.low_count ? "Below min · " + data.low_count : "Below min", status: "Below min", position: "", in_stock: "" },
    { id: "soon", label: data?.soon_count ? "Buy this week · " + data.soon_count : "Buy this week", status: "Buy this week", position: "", in_stock: "" },
    { id: "under", label: data?.under_count ? "Understocked · " + data.under_count : "Understocked", status: "", position: "Understocked", in_stock: "" },
    { id: "over", label: data?.over_count ? "Overstocked · " + data.over_count : "Overstocked", status: "", position: "Overstocked", in_stock: "" },
    { id: "dead", label: data?.dead_count ? "Dead stock · " + data.dead_count : "Dead stock", status: "", position: "Dead stock", in_stock: "" },
    { id: "oos", label: data?.out_of_stock_count ? "Not in stock · " + data.out_of_stock_count : "Not in stock", status: "", position: "", in_stock: "no" },
  ];

  function activePreset() {
    if (filters.in_stock === "no" && !filters.status && !filters.position) return "oos";
    if (!filters.status && !filters.position && !filters.in_stock) return "all";
    if (filters.status === "Below min" && !filters.position && !filters.in_stock) return "low";
    if (filters.status === "Buy this week" && !filters.position && !filters.in_stock) return "soon";
    if (filters.position === "Understocked" && !filters.status && !filters.in_stock) return "under";
    if (filters.position === "Overstocked" && !filters.status && !filters.in_stock) return "over";
    if (filters.position === "Dead stock" && !filters.status && !filters.in_stock) return "dead";
    return "";
  }

  const showBuyCol = filters.status === "Below min" || filters.status === "Buy this week" || !!data?.buy_count;

  return (
    <div className="workspace-page">
      <div className="page-head">
        <div className="page-head-copy">
          <h2>{title || "Stock"}</h2>
          <p className="muted">{copy || "On-hand, velocity, and when to buy."}</p>
        </div>
        <span className="page-stat">
          {data ? `${data.total} ${data.total === 1 ? "item" : "items"}` : "…"}
          {notes.length ? " · " + notes.join(" · ") : ""}
        </span>
      </div>

      {(data?.buy_count || data?.buy_qty_sum) ? (
        <div className="card buy-summary">
          <div>
            <strong>Need to buy</strong>
            <p className="muted" style={{ margin: "4px 0 0" }}>
              {data.buy_count || 0} {(data.buy_count || 0) === 1 ? "item" : "items"}
              {" · "}{qty(data.buy_qty_sum)} units
              {data.buy_value_sum ? " · " + money(data.buy_value_sum) : ""}
              {(data.low_count || data.soon_count) ? (
                <>
                  {" · "}
                  {[
                    data.low_count ? data.low_count + " below min" : null,
                    data.soon_count ? data.soon_count + " this week" : null,
                  ].filter(Boolean).join(" · ")}
                </>
              ) : null}
            </p>
          </div>
          <button
            type="button"
            className="secondary"
            onClick={() => setFilters((prev) => ({ ...prev, status: "Below min", position: "", item: "", in_stock: "" }))}
          >
            Show below min
          </button>
          <button
            type="button"
            onClick={() => setFilters((prev) => ({ ...prev, status: "Buy this week", position: "", item: "", in_stock: "" }))}
          >
            Show buy this week
          </button>
        </div>
      ) : null}

      <div className="chips stock-presets">
        {presets.map((p) => (
          <button
            type="button"
            key={p.id}
            className={activePreset() === p.id ? "" : "secondary"}
            onClick={() => setFilters((prev) => ({
              ...prev,
              status: p.status,
              position: p.position,
              in_stock: p.in_stock || "",
              item: "",
            }))}
          >
            {p.label}
          </button>
        ))}
      </div>

      <FilterBar filters={filters} options={data?.options} onChange={setFilters} fields={STOCK_FIELDS} />
      {loading && !data ? <EmptyCard title="Loading stock" copy="Pulling the latest items." /> : null}
      {!loading && !data?.items?.length ? (
        <EmptyCard title="No items match" copy="Clear a filter, or import stock to add items." />
      ) : null}
      {data?.items?.length ? (
        <div className="card table-card list-panel">
          <table className="dense list-table">
            <thead>
              <tr>
                <SortTh id="name" label="Item" sort={sort} dir={dir} onSort={onSort} />
                <SortTh id="category" label="Category" sort={sort} dir={dir} onSort={onSort} />
                <SortTh id="item_group" label="Item group" sort={sort} dir={dir} onSort={onSort} />
                <SortTh id="brand" label="Brand" sort={sort} dir={dir} onSort={onSort} />
                <SortTh id="supplier" label="Supplier" sort={sort} dir={dir} onSort={onSort} />
                <SortTh id="qty" label="On hand" sort={sort} dir={dir} onSort={onSort} className="num" />
                <SortTh id="pace_30" label="30d/day" sort={sort} dir={dir} onSort={onSort} className="num" />
                <SortTh id="days_cover" label="Days left" sort={sort} dir={dir} onSort={onSort} className="num" />
                {showBuyCol ? <SortTh id="buy_qty" label="Buy qty" sort={sort} dir={dir} onSort={onSort} className="num" /> : null}
                <SortTh id="position" label="Stock" sort={sort} dir={dir} onSort={onSort} />
                <SortTh id="status" label="Buy" sort={sort} dir={dir} onSort={onSort} />
                <SortTh id="last_sale" label="Last sale" sort={sort} dir={dir} onSort={onSort} />
                <SortTh id="value" label="Value" sort={sort} dir={dir} onSort={onSort} className="num" />
              </tr>
            </thead>
            <tbody>
              {data.items.map((row) => (
                <tr key={row.uk} className="click-row" onClick={() => onOpen(row.uk)}>
                  <td>
                    <div className="name-cell">
                      <span className="avatar sm">{initials(row.name)}</span>
                      <span className="clip">
                        <strong>{row.name}</strong>
                        {!row.in_stock ? <span className="quiet"> · not in stock</span> : null}
                      </span>
                    </div>
                  </td>
                  <td>{row.category ? <LinkName kind="category/" uk={row.category_uk} name={row.category} /> : "—"}</td>
                  <td>{row.item_group ? <LinkName kind="item-group/" uk={row.item_group_uk} name={row.item_group} /> : "—"}</td>
                  <td>{row.brand ? <LinkName kind="brand/" uk={row.brand_uk} name={row.brand} /> : "—"}</td>
                  <td>{row.supplier ? <LinkName kind="supplier/" uk={row.supplier_uk} name={row.supplier} /> : "—"}</td>
                  <td className="num amount">{qty(row.qty)}</td>
                  <td className="num quiet">{pace(row.pace_30)}</td>
                  <td className="num quiet">{row.days_cover == null ? "—" : row.days_cover}</td>
                  {showBuyCol ? <td className="num amount">{row.buy_qty ? qty(row.buy_qty) : "—"}</td> : null}
                  <td>
                    <span className={"pill " + pillClass(row.stock_position)}>
                      {row.stock_position_label || "—"}
                    </span>
                  </td>
                  <td><span className={"pill " + pillClass(row.status)}>{row.status_label}</span></td>
                  <td className="quiet">{row.last_sale_label || "—"}</td>
                  <td className="num amount">{moneyOrDash(row.value)}</td>
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

function HoldForm({ detail, canEdit, onSaved }) {
  const holding = detail.holding || {};
  const [minHold, setMinHold] = useState(String(detail.min_hold ?? 0));
  const [fillTo, setFillTo] = useState(holding.fill_to != null ? String(holding.fill_to) : "");
  const [lead, setLead] = useState(String(detail.lead_days ?? 0));
  const [reviewDays, setReviewDays] = useState(holding.review_days != null ? String(holding.review_days) : "");
  const [safety, setSafety] = useState(holding.safety_stock != null ? String(holding.safety_stock) : "");
  const [maxDays, setMaxDays] = useState(String(detail.max_days_hold ?? 60));
  const [disc, setDisc] = useState(!!detail.discontinued);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    setMinHold(String(detail.min_hold ?? 0));
    setFillTo(holding.fill_to != null ? String(holding.fill_to) : "");
    setLead(String(detail.lead_days ?? 0));
    setReviewDays(holding.review_days != null ? String(holding.review_days) : "");
    setSafety(holding.safety_stock != null ? String(holding.safety_stock) : "");
    setMaxDays(String(detail.max_days_hold ?? 60));
    setDisc(!!detail.discontinued);
    setErr("");
  }, [detail.uk, detail.min_hold, detail.lead_days, detail.max_days_hold, detail.discontinued, holding.fill_to]);

  if (!canEdit) {
    return (
      <div className="hold-readonly">
        <div><span className="muted">Min holding</span><strong>{qty(detail.min_hold)}</strong></div>
        <div><span className="muted">Fill to</span><strong>{holding.fill_to != null ? qty(holding.fill_to) : "Auto (" + qty(detail.fill_to) + ")"}</strong></div>
        <div><span className="muted">Days to arrive</span><strong>{detail.lead_days || 0}</strong></div>
        <div><span className="muted">Review days</span><strong>{holding.review_days != null ? holding.review_days : "—"}</strong></div>
        <div><span className="muted">Safety stock</span><strong>{holding.safety_stock != null ? qty(holding.safety_stock) : "—"}</strong></div>
        <div>
          <span className="muted">Max days hold</span>
          <strong>{detail.max_days_hold ?? 60}</strong>
          <span className="quiet">{detail.uses_default_max_days ? "Using default" : "Custom"}</span>
        </div>
        <div><span className="muted">Status</span><strong>{detail.discontinued ? "Discontinued" : "Active"}</strong></div>
      </div>
    );
  }

  async function save(e) {
    e.preventDefault();
    const minN = Number(minHold);
    const leadN = Number(lead);
    const maxN = Number(maxDays);
    if (!Number.isFinite(minN) || minN < 0) {
      setErr("Min holding must be 0 or more.");
      return;
    }
    if (!Number.isFinite(leadN) || leadN < 0) {
      setErr("Lead days must be 0 or more.");
      return;
    }
    if (!Number.isFinite(maxN) || maxN < 1) {
      setErr("Max days hold must be at least 1.");
      return;
    }
    const body = {
      min_hold: minN,
      lead_days: Math.round(leadN),
      max_days_hold: Math.round(maxN),
      discontinued: disc,
    };
    if (reviewDays !== "") {
      const reviewN = Number(reviewDays);
      if (!Number.isFinite(reviewN) || reviewN < 0) {
        setErr("Review days must be 0 or more, or blank.");
        return;
      }
      body.review_days = Math.round(reviewN);
    }
    if (safety !== "") {
      const safetyN = Number(safety);
      if (!Number.isFinite(safetyN) || safetyN < 0) {
        setErr("Safety stock must be 0 or more, or blank.");
        return;
      }
      body.safety_stock = safetyN;
    }
    if (fillTo === "" || fillTo == null) {
      body.clear_fill = true;
    } else {
      const fillN = Number(fillTo);
      if (!Number.isFinite(fillN) || fillN < 0) {
        setErr("Fill to must be 0 or more, or blank for auto.");
        return;
      }
      body.fill_to = fillN;
    }
    setSaving(true);
    setErr("");
    try {
      const next = await api.saveItemHolding(detail.uk, body);
      onSaved?.(next);
    } catch (ex) {
      setErr(ex.message || "Could not save.");
    } finally {
      setSaving(false);
    }
  }

  async function clearMaxDays() {
    setSaving(true);
    setErr("");
    try {
      const next = await api.saveItemHolding(detail.uk, { clear_max_days: true });
      onSaved?.(next);
    } catch (ex) {
      setErr(ex.message || "Could not save.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="hold-form" onSubmit={save}>
      <label>
        Min holding
        <span className="muted hold-hint">Lowest qty you want on the shelf. Below this → buy now.</span>
        <input type="number" min="0" step="any" value={minHold} disabled={saving} onChange={(e) => setMinHold(e.target.value)} />
      </label>
      <label>
        Fill to
        <span className="muted hold-hint">Target qty after buying. Blank = auto (min + pace × max days hold). Now auto · {qty(detail.fill_to)}.</span>
        <input type="number" min="0" step="any" value={fillTo} disabled={saving} placeholder={"Auto · " + qty(detail.fill_to)} onChange={(e) => setFillTo(e.target.value)} />
      </label>
      <label>
        Days to arrive
        <span className="muted hold-hint">Supplier lead time. Moves the “buy by” date earlier.</span>
        <input type="number" min="0" step="1" value={lead} disabled={saving} onChange={(e) => setLead(e.target.value)} />
      </label>
      <label>
        Review days
        <span className="muted hold-hint">Blank keeps the fill-to quantity. A number switches this item to a demand target.</span>
        <input type="number" min="0" step="1" value={reviewDays} disabled={saving} onChange={(e) => setReviewDays(e.target.value)} />
      </label>
      <label>
        Safety stock
        <span className="muted hold-hint">Extra units added to the demand target.</span>
        <input type="number" min="0" step="any" value={safety} disabled={saving} onChange={(e) => setSafety(e.target.value)} />
      </label>
      <label>
        Max days hold
        <span className="muted hold-hint">
          How many days of stock you’ll sit on when Fill to is auto.
          {detail.uses_default_max_days
            ? ` Using default (${detail.default_max_days ?? 60}).`
            : " Custom for this item."}
        </span>
        <input type="number" min="1" step="1" value={maxDays} disabled={saving} onChange={(e) => setMaxDays(e.target.value)} />
      </label>
      <label className="hold-check">
        <input type="checkbox" checked={disc} disabled={saving} onChange={(e) => setDisc(e.target.checked)} />
        Discontinued — do not buy more
      </label>
      <div className="hold-form-actions">
        <button type="submit" disabled={saving}>{saving ? "Saving…" : "Save holding"}</button>
        {!detail.uses_default_max_days ? (
          <button type="button" className="secondary" disabled={saving} onClick={clearMaxDays}>Use default max days</button>
        ) : null}
      </div>
      {err ? <p className="err" style={{ gridColumn: "1 / -1" }}>{err}</p> : null}
    </form>
  );
}

function RollTable({ rows, nameLabel, empty, linkKind }) {
  const [sort, setSort] = useState("qty");
  const [dir, setDir] = useState("desc");
  function onSort(id) {
    const next = toggleSort(sort, dir, id, ["qty", "amount", "times"]);
    setSort(next.sort);
    setDir(next.dir);
  }
  const ordered = rows.slice().sort((a, b) => {
    const key = sort === "last" ? "last_date" : sort;
    const av = a[key];
    const bv = b[key];
    const cmp = typeof av === "number" && typeof bv === "number" ? av - bv : String(av || "").localeCompare(String(bv || ""));
    return dir === "desc" ? -cmp : cmp;
  });
  if (!rows.length) return <p className="muted">{empty}</p>;
  return (
    <table className="dense">
      <thead>
        <tr>
          <SortTh id="name" label={nameLabel} sort={sort} dir={dir} onSort={onSort} />
          <SortTh id="qty" label="Qty" sort={sort} dir={dir} onSort={onSort} className="num" />
          <SortTh id="amount" label="Amount" sort={sort} dir={dir} onSort={onSort} className="num" />
          <SortTh id="times" label="Times" sort={sort} dir={dir} onSort={onSort} className="num" />
          <SortTh id="last" label="Last sale" sort={sort} dir={dir} onSort={onSort} />
        </tr>
      </thead>
      <tbody>
        {ordered.map((row) => (
          <tr key={row.uk || row.name}>
            <td>
              {linkKind ? <LinkName kind={linkKind} uk={row.uk} name={row.name} /> : row.name}
            </td>
            <td className="num">{qty(row.qty)}</td>
            <td className="num">{money(row.amount)}</td>
            <td className="num">{row.times}</td>
            <td className="quiet">{row.last_label || "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function MovementTable({ rows }) {
  if (!rows.length) return <p className="muted">No item-wise sales yet.</p>;
  return (
    <table className="dense">
      <thead>
        <tr>
          <th>Date</th>
          <th>Customer</th>
          <th>Group</th>
          <th>Salesperson</th>
          <th>Invoice</th>
          <th className="num">Qty</th>
          <th className="num">Rate</th>
          <th className="num">Amount</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row, i) => (
          <tr key={(row.date || "") + (row.invoice || "") + i}>
            <td className="quiet">{row.date_label || "—"}</td>
            <td><LinkName kind="customer" uk={row.party_uk} name={row.party} /></td>
            <td><LinkName kind="group" uk={row.group_uk} name={row.group} /></td>
            <td><LinkName kind="rep" uk={row.rep_uk} name={row.rep} /></td>
            <td>
              {row.invoice_id ? (
                <button type="button" className="linkish" onClick={() => hashSet("invoice/" + encodeURIComponent(row.invoice_id))}>
                  {row.invoice || "Invoice"}
                </button>
              ) : (row.invoice || "—")}
            </td>
            <td className="num">{qty(row.qty)}</td>
            <td className="num">{moneyOrDash(row.rate)}</td>
            <td className="num">{money(row.amount)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function InsightCard({ insight, discontinued }) {
  if (!insight?.headline) return null;
  const bits = [insight.velocity_bit, insight.cover_bit, insight.risk_bit, insight.concentration_bit].filter(Boolean);
  return (
    <div className={"card insight" + (discontinued ? " stopped" : "")}>
      <div>{insight.headline}</div>
      {bits.length ? (
        <ul className="insight-bits">
          {bits.map((bit) => <li key={bit}>{bit}</li>)}
        </ul>
      ) : null}
    </div>
  );
}

function VelocityStrip({ detail }) {
  const buckets = detail.velocity?.buckets || {};
  const order = [
    ["d7", "7d"],
    ["d30", "30d"],
    ["d90", "90d"],
    ["d365", "365d"],
    ["this_month", "This mo"],
    ["last_month", "Last mo"],
  ];
  return (
    <div className="velocity-strip">
      <div className="velocity-head">
        <h3>Velocity</h3>
        {detail.trend_label ? (
          <span className={"pill " + pillClass(detail.trend)}>{detail.trend_label}</span>
        ) : null}
      </div>
      <div className="buy-tiles velocity-tiles">
        {order.map(([id, short]) => {
          const b = buckets[id] || {};
          return (
            <div className="card buy-tile" key={id}>
              <span className="muted">{b.label || short}</span>
              <strong>{pace(b.per_day ?? detail["pace_" + id.replace("d", "")])}</strong>
              <span className="quiet">
                {qty(b.qty)} sold
                {b.days != null ? " · avg " + b.days + "d" : ""}
                {b.days_cover != null ? " · " + b.days_cover + "d cover" : ""}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Profile({ detail, runId, onBack, backLabel, canEdit, onSaved }) {
  const [tab, setTab] = useState("buy");
  const [moveView, setMoveView] = useState("sales");
  const [period, setPeriod] = useState("this_year");
  const [measure, setMeasure] = useState("amount");
  const [parts, setParts] = useState({});
  const view = { ...detail, ...(parts.buyers || {}), ...(parts.movement || {}) };
  const insight = view.insight || {};
  const buyerCount = view.buyers ? view.buyers.length : (detail.buyer_count || 0);

  useEffect(() => {
    setParts({});
  }, [detail.uk]);

  useEffect(() => {
    const want = [];
    if ((tab === "buyers" || (tab === "movement" && moveView === "customers")) && detail.sections?.buyers && !Object.prototype.hasOwnProperty.call(parts, "buyers")) {
      want.push("buyers");
    }
    if (tab === "movement" && detail.sections?.movement && !Object.prototype.hasOwnProperty.call(parts, "movement")) {
      want.push("movement");
    }
    if (!want.length) return undefined;
    let cancelled = false;
    want.forEach((section) => {
      api.stockItem(detail.uk, { run: runId || detail.run_id || "", section })
        .then((part) => {
          if (!cancelled) setParts((prev) => ({ ...prev, [section]: part || {} }));
        })
        .catch(() => {
          if (!cancelled) setParts((prev) => ({ ...prev, [section]: {} }));
        });
    });
    return () => { cancelled = true; };
  }, [tab, moveView, detail.uk, detail.run_id, detail.sections, runId, parts]);
  const periods = view.periods || {};
  const buyersPending = Boolean(detail.sections?.buyers && !Object.prototype.hasOwnProperty.call(parts, "buyers"));
  const movementPending = Boolean(detail.sections?.movement && !Object.prototype.hasOwnProperty.call(parts, "movement"));
  const periodOrder = ["this_month", "last_month", "last_3m", "this_year", "last_year", "all"];
  const current = periods[period] || periods.this_year || {};

  return (
    <div className="workspace-page">
      <div className="profile-nav">
        <button className="ghost" onClick={onBack}>← {backLabel || "Items"}</button>
      </div>
      <div className={"hero card" + (detail.discontinued ? " stopped-hero" : "")}>
        <div>
          <h2>{detail.name}</h2>
          <p className="muted">
            {detail.usual_buyer ? (
              <button type="button" className="chip linkish" onClick={() => openEntity("customer", null, detail.usual_buyer)}>
                {detail.usual_buyer}
              </button>
            ) : null}
            {" "}{detail.last_sale_label ? "Last sale " + detail.last_sale_label : "No sales yet"}
            {detail.last_sale_age_days != null ? " · " + detail.last_sale_age_days + "d ago" : ""}
            {!detail.in_stock ? " · not in stock file" : ""}
          </p>
          <div className="hero-pills">
            {ITEM_LINKS.map((link) => {
              const name = detail[link.key];
              if (!name) return <span key={link.key} className="pill">{link.label}: —</span>;
              return (
                <button
                  key={link.key}
                  type="button"
                  className="chip linkish"
                  onClick={() => hashSet(link.hash + encodeURIComponent(detail[link.uk] || name))}
                >
                  {link.label}: {name}
                </button>
              );
            })}
          </div>
          <div className="hero-pills">
            <span className={"pill " + pillClass(detail.stock_position)}>
              {insight.stock_label || detail.stock_position_label || "—"}
            </span>
            <span className={"pill " + pillClass(detail.status)}>{insight.health_label || detail.status_label}</span>
            {detail.trend_label ? <span className={"pill " + pillClass(detail.trend)}>{detail.trend_label}</span> : null}
          </div>
        </div>
        <div className="hero-due">
          <span className="muted">On hand</span>
          <div className="hero-num">{qty(detail.qty)}</div>
          <span className="muted">{pace(detail.pace_30)} · {detail.days_cover == null ? "—" : detail.days_cover + " days left"}</span>
        </div>
      </div>
      <InsightCard insight={insight} discontinued={detail.discontinued} />
      <div className="buy-tiles">
        <div className="card buy-tile">
          <span className="muted">Min holding</span>
          <strong>{qty(detail.min_hold)}</strong>
        </div>
        <div className="card buy-tile">
          <span className="muted">Target cover</span>
          <strong>{detail.target_days == null ? "—" : detail.target_days + "d"}</strong>
          <span className="quiet">max {detail.max_days_hold ?? 60}d hold</span>
        </div>
        <div className="card buy-tile">
          <span className="muted">Buy</span>
          <strong>{detail.buy_qty ? qty(detail.buy_qty) : "None"}</strong>
        </div>
        <div className="card buy-tile">
          <span className="muted">Buy by</span>
          <strong>{detail.buy_qty ? (detail.buy_by_label || "Now") : "—"}</strong>
        </div>
        <div className="card buy-tile">
          <span className="muted">Reserved</span>
          <strong>{detail.reserved == null ? "Not in this file" : qty(detail.reserved)}</strong>
        </div>
        <div className="card buy-tile">
          <span className="muted">Incoming on time</span>
          <strong>{detail.incoming_on_time == null ? "Not in this file" : qty(detail.incoming_on_time)}</strong>
        </div>
        <div className="card buy-tile">
          <span className="muted">Incoming late</span>
          <strong>{detail.incoming_late == null ? "Not in this file" : qty(detail.incoming_late)}</strong>
        </div>
        <div className="card buy-tile">
          <span className="muted">Position</span>
          <strong>{detail.position == null ? "Not in this file" : qty(detail.position)}</strong>
        </div>
      </div>
      {detail.demand_label ? <p className="muted">{detail.demand_label}{detail.demand_target != null ? " · Target " + qty(detail.demand_target) : ""}</p> : null}
      {detail.past_check ? (
        <p className="muted">
          {detail.past_check.label}
          {detail.past_check.buy_qty != null ? " · Earlier buy " + qty(detail.past_check.buy_qty) : ""}
          {detail.past_check.exceeded ? " · Later sales exceeded stock on hand" : ""}
        </p>
      ) : null}
      {insight.action || insight.next_move ? (
        <p className="muted next-move">{insight.action || insight.next_move}</p>
      ) : null}
      <VelocityStrip detail={detail} />
      <div className="chips">
        {[
          ["buy", "Buy"],
          ["repurchase", "Repurchase"],
          ["buyers", buyerCount ? "Buyers · " + buyerCount : "Buyers"],
          ["movement", "Movement"],
          ["periods", "Periods"],
        ].map(([id, label]) => (
          <button type="button" key={id} className={tab === id ? "" : "secondary"} onClick={() => setTab(id)}>{label}</button>
        ))}
      </div>
      {tab === "buy" ? (
        <div className="card">
          <h3>Holding</h3>
          <p className="muted">
            Set the shelf floor and how much to buy back to. Leave Fill to blank to auto-size from min holding plus up to {detail.max_days_hold ?? 60} days of sales pace
            {detail.uses_default_max_days ? " (default)" : ""}.
          </p>
          <HoldForm detail={detail} canEdit={canEdit} onSaved={onSaved} />
        </div>
      ) : null}
      {tab === "repurchase" ? <RepurchasePanel detail={detail} entity="item" showCustomer showItem={false} /> : null}
      {tab === "buyers" ? (
        buyersPending ? <EmptyCard title="Loading buyers" copy="Reading who has bought this item." /> : (
        <div className="card">
          <h3>Who buys this</h3>
          <RollTable rows={view.buyers || []} nameLabel="Customer" linkKind="customer" empty="No customers have bought this yet." />
        </div>
        )
      ) : null}
      {tab === "movement" ? (
        movementPending ? <EmptyCard title="Loading movement" copy="Reading recent sales of this item." /> : (
        <div className="card">
          <h3>Movement</h3>
          <div className="chips">
            {[
              ["sales", "Recent sales"],
              ["customers", "Customer"],
              ["groups", "Customer group"],
              ["reps", "Salesperson"],
            ].map(([id, label]) => (
              <button type="button" key={id} className={moveView === id ? "" : "secondary"} onClick={() => setMoveView(id)}>{label}</button>
            ))}
          </div>
          {moveView === "sales" ? <MovementTable rows={view.movement || []} /> : null}
          {moveView === "customers" ? (
            buyersPending ? <p className="muted">Loading customers…</p> : (
            <RollTable rows={view.buyers || []} nameLabel="Customer" linkKind="customer" empty="No customers have bought this yet." />
            )
          ) : null}
          {moveView === "groups" ? (
            <RollTable rows={view.groups || []} nameLabel="Customer group" linkKind="group" empty="No customer group on the sales yet." />
          ) : null}
          {moveView === "reps" ? (
            <RollTable rows={view.reps || []} nameLabel="Salesperson" linkKind="rep" empty="No salesperson on the sales yet." />
          ) : null}
        </div>
        )
      ) : null}
      {tab === "periods" ? (
        <div className="card">
          <h3>Sales by period</h3>
          <div className="chips">
            <button type="button" className={measure === "amount" ? "" : "secondary"} onClick={() => setMeasure("amount")}>Amount</button>
            <button type="button" className={measure === "qty" ? "" : "secondary"} onClick={() => setMeasure("qty")}>Quantity</button>
          </div>
          <div className="chips">
            {periodOrder.map((id) => (
              <button type="button" key={id} className={period === id ? "" : "secondary"} onClick={() => setPeriod(id)}>
                {(periods[id] || {}).label || id}
              </button>
            ))}
          </div>
          <div className="fy-grid" style={{ marginTop: 12 }}>
            <div className="fy-card">
              <div className="fy-label">{current.label || "Period"}</div>
              {measure === "qty" ? (
                <>
                  <div className="fy-metric sales"><span className="muted">Qty</span> <strong>{qty(current.qty)}</strong></div>
                  <div className="fy-metric collection"><span className="muted">Per day</span> <strong>{pace(current.per_day)}</strong></div>
                </>
              ) : (
                <>
                  <div className="fy-metric sales"><span className="muted">Amount</span> <strong>{money(current.amount || 0)}</strong></div>
                  <div className="fy-metric"><span className="muted">Customers</span> <strong>{current.buyers || 0}</strong></div>
                </>
              )}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default function StockPage({ user, profile = true, runId }) {
  const [filters, setFilters] = useState({ item: "", status: "", position: "", in_stock: "" });
  const [data, setData] = useState(null);
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState("name");
  const [dir, setDir] = useState("asc");
  const [loading, setLoading] = useState(false);
  const [uk, setUk] = useState("");
  const [detail, setDetail] = useState(null);
  const [err, setErr] = useState("");
  const canEdit = can(user, "stock.upload");

  function loadList(nextFilters, nextPage, nextSort, nextDir) {
    setLoading(true);
    api.stockItems({
      ...nextFilters,
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
    loadList(filters, 1, sort, dir);
  }, [filters, sort, dir, runId]);

  function applyHash(h) {
    if (profile && h.startsWith("item/")) {
      setUk(decodeURIComponent(h.slice("item/".length)));
      return;
    }
    if (!profile && h.startsWith("list/stock/")) {
      const status = decodeURIComponent(h.slice("list/stock/".length));
      if (status) setFilters((prev) => ({ ...prev, status }));
    }
    setUk("");
    setDetail(null);
  }

  useEffect(() => {
    applyHash(hashGet());
  }, [profile]);

  useEffect(() => {
    function onHash() {
      applyHash(hashGet());
    }
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, [profile]);

  useEffect(() => {
    if (!profile || !uk) return undefined;
    setDetail(null);
    api.stockItem(uk, { run: runId || "", view: "profile" }).then(setDetail).catch((e) => setErr(e.message));
    return undefined;
  }, [profile, uk, runId]);

  if (profile && uk) {
    if (detail && detail.uk === uk) {
      return (
        <>
          {err ? <p className="err">{err}</p> : null}
          <Profile
            detail={detail}
            runId={runId}
            backLabel={hashReturnLabel("Items")}
            onBack={() => hashBack("")}
            canEdit={canEdit}
            onSaved={() => api.stockItem(uk, { run: runId || "", view: "profile" }).then(setDetail).catch((e) => setErr(e.message))}
          />
        </>
      );
    }
    return (
      <div className="card">
        {err ? <p className="err">{err}</p> : <p className="muted">Opening item…</p>}
        <button className="ghost" onClick={() => hashBack("")}>← {hashReturnLabel("Items")}</button>
      </div>
    );
  }

  return (
    <>
      {err ? <p className="err">{err}</p> : null}
      <Directory
        filters={filters}
        setFilters={setFilters}
        data={data}
        page={page}
        loading={loading}
        sort={sort}
        dir={dir}
        onSort={(id) => {
          const next = toggleSort(sort, dir, id, ["qty", "min_hold", "days_cover", "value", "last_sale", "pace_30", "position", "buy_qty"]);
          setSort(next.sort);
          setDir(next.dir);
        }}
        title={profile ? "Items" : "Stock"}
        copy={profile ? "Velocity, stock position, and when to buy." : "On-hand, velocity, and when to buy."}
        onOpen={(next) => {
          if (profile) setUk(next);
          hashSet("item/" + encodeURIComponent(next));
        }}
        onPage={(p) => { setPage(p); loadList(filters, p, sort, dir); }}
      />
    </>
  );
}
