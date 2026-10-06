import { useEffect, useRef, useState } from "react";
import { AGE_KEYS, AGE_LABELS, bucketMoney, hashSet, initials, money, rowBucket } from "./format";

function prettyDay(iso) {
  if (!iso) return "";
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function Chip({ label, value, open, onClick, onClear }) {
  return (
    <div className={"filter-chip" + (value ? " on" : "") + (open ? " open" : "")}>
      <button type="button" className="filter-chip-btn" onClick={onClick}>
        <span className="filter-chip-copy">
          <span className="k">{label}</span>
          <span className="v">{value || "All"}</span>
        </span>
        <span className="caret" aria-hidden />
      </button>
      {value ? (
        <button type="button" className="filter-x" aria-label={"Clear " + label} onClick={onClear}>×</button>
      ) : null}
    </div>
  );
}

function Menu({ label, value, options, onChange }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const box = useRef(null);

  useEffect(() => {
    function hide(e) {
      if (box.current && !box.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", hide);
    return () => document.removeEventListener("mousedown", hide);
  }, []);

  const shown = (options || []).filter((name) => !q || String(name).toLowerCase().includes(q.toLowerCase()));

  return (
    <div className="filter-menu" ref={box}>
      <Chip label={label} value={value} open={open} onClick={() => setOpen((v) => !v)} onClear={() => onChange("")} />
      {open ? (
        <div className="filter-pop">
          <input className="filter-search" placeholder={"Search " + label.toLowerCase()} value={q} onChange={(e) => setQ(e.target.value)} autoFocus />
          <button type="button" className={"filter-choice" + (!value ? " on" : "")} onClick={() => { onChange(""); setOpen(false); setQ(""); }}>All</button>
          {shown.map((name) => (
            <button
              type="button"
              key={name}
              className={"filter-choice" + (name === value ? " on" : "")}
              onClick={() => { onChange(name); setOpen(false); setQ(""); }}
            >
              {name}
            </button>
          ))}
          {!shown.length ? <p className="muted pad">No matches</p> : null}
        </div>
      ) : null}
    </div>
  );
}

function prettyAmount(n) {
  if (n === "" || n === null || n === undefined) return "";
  const v = Number(n);
  if (!Number.isFinite(v)) return String(n);
  return v.toLocaleString(undefined, { maximumFractionDigits: 2, minimumFractionDigits: 0 });
}

function BalanceMenu({ label, from, to, onChange }) {
  const [open, setOpen] = useState(false);
  const box = useRef(null);
  const value = [prettyAmount(from), prettyAmount(to)].filter(Boolean).join(" – ");

  useEffect(() => {
    function hide(e) {
      if (box.current && !box.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", hide);
    return () => document.removeEventListener("mousedown", hide);
  }, []);

  return (
    <div className="filter-menu" ref={box}>
      <Chip
        label={label || "Balance"}
        value={value}
        open={open}
        onClick={() => setOpen((v) => !v)}
        onClear={() => onChange({ balance_from: "", balance_to: "" })}
      />
      {open ? (
        <div className="filter-pop date-pop">
          <label>From</label>
          <input type="number" step="0.01" placeholder="Min" value={from || ""} onChange={(e) => onChange({ balance_from: e.target.value, balance_to: to })} />
          <label>To</label>
          <input type="number" step="0.01" placeholder="Max" value={to || ""} onChange={(e) => onChange({ balance_from: from, balance_to: e.target.value })} />
        </div>
      ) : null}
    </div>
  );
}

function sortDirLabel(option, dir) {
  if (option?.numeric) return dir === "desc" ? "High to low" : "Low to high";
  return dir === "desc" ? "Z to A" : "A to Z";
}

function SortMenu({ sort, dir, options, onChange }) {
  const [open, setOpen] = useState(false);
  const box = useRef(null);
  const current = (options || []).find((item) => item.id === sort) || (options || [])[0];
  const value = current ? `${current.label} · ${sortDirLabel(current, dir)}` : "";

  useEffect(() => {
    function hide(e) {
      if (box.current && !box.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", hide);
    return () => document.removeEventListener("mousedown", hide);
  }, []);

  if (!options?.length) return null;

  return (
    <div className="filter-menu" ref={box}>
      <Chip label="Sort" value={value} open={open} onClick={() => setOpen((v) => !v)} />
      {open ? (
        <div className="filter-pop">
          {(options || []).map((item) => (
            <button
              type="button"
              key={item.id}
              className={"filter-choice" + (item.id === sort ? " on" : "")}
              onClick={() => {
                if (item.id === sort) onChange({ sort, dir: dir === "asc" ? "desc" : "asc" });
                else onChange({ sort: item.id, dir: item.numeric ? "desc" : "asc" });
                setOpen(false);
              }}
            >
              {item.label}
            </button>
          ))}
          <div className="filter-dir">
            <button
              type="button"
              className={"filter-choice" + (dir === "desc" ? " on" : "")}
              onClick={() => onChange({ sort, dir: "desc" })}
            >
              {sortDirLabel(current, "desc")}
            </button>
            <button
              type="button"
              className={"filter-choice" + (dir === "asc" ? " on" : "")}
              onClick={() => onChange({ sort, dir: "asc" })}
            >
              {sortDirLabel(current, "asc")}
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function DateMenu({ label, dateFrom, dateTo, onChange }) {
  const [open, setOpen] = useState(false);
  const box = useRef(null);
  const value = [prettyDay(dateFrom), prettyDay(dateTo)].filter(Boolean).join(" – ");

  useEffect(() => {
    function hide(e) {
      if (box.current && !box.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", hide);
    return () => document.removeEventListener("mousedown", hide);
  }, []);

  return (
    <div className="filter-menu" ref={box}>
      <Chip label={label || "Date"} value={value} open={open} onClick={() => setOpen((v) => !v)} onClear={() => onChange({ date_from: "", date_to: "" })} />
      {open ? (
        <div className="filter-pop date-pop">
          <label>From</label>
          <input type="date" value={dateFrom || ""} onChange={(e) => onChange({ date_from: e.target.value, date_to: dateTo })} />
          <label>To</label>
          <input type="date" value={dateTo || ""} onChange={(e) => onChange({ date_from: dateFrom, date_to: e.target.value })} />
        </div>
      ) : null}
    </div>
  );
}

export const SALES_FIELDS = [
  { key: "party", label: "Customer" },
  { key: "group", label: "Group" },
  { key: "rep", label: "Salesperson" },
  { key: "invoice", label: "Invoice" },
  { key: "date", kind: "date", label: "Date" },
];

export const ITEM_FIELDS = [
  { key: "party", label: "Customer" },
  { key: "group", label: "Group" },
  { key: "rep", label: "Salesperson" },
  { key: "invoice", label: "Invoice" },
  { key: "item", label: "Item" },
  { key: "date", kind: "date", label: "Date" },
];

export const CUSTOMER_FIELDS = [
  { key: "group", label: "Group" },
  { key: "rep", label: "Salesperson" },
  { key: "status", label: "Status" },
  { key: "balance_issue", label: "Mismatch" },
];

export const DUE_AGE_SORT = [
  { id: "due", label: "Due", numeric: true },
  { id: "d0_15", label: "0–15 days", numeric: true },
  { id: "d15_30", label: "15–30 days", numeric: true },
  { id: "d30_45", label: "30–45 days", numeric: true },
  { id: "d45_60", label: "45–60 days", numeric: true },
  { id: "d60_90", label: "60–90 days", numeric: true },
  { id: "d90", label: "90+ days", numeric: true },
];

export const CUSTOMER_SORT_OPTIONS = [
  { id: "due", label: "Due", numeric: true },
  { id: "balance_diff", label: "AR Diff", numeric: true },
  ...DUE_AGE_SORT.slice(1),
  { id: "last_sale", label: "Last sale", numeric: true },
  { id: "party", label: "Customer" },
  { id: "group", label: "Group" },
  { id: "rep", label: "Salesperson" },
  { id: "status", label: "Status" },
];

export const GROUP_SORT_OPTIONS = [
  ...DUE_AGE_SORT,
  { id: "customers", label: "Customers", numeric: true },
  { id: "last_sale", label: "Last sale", numeric: true },
  { id: "name", label: "Group" },
  { id: "rep", label: "Salespeople", numeric: true },
  { id: "status", label: "Status" },
];

export const REP_SORT_OPTIONS = [
  { id: "ytd_sales", label: "This year", numeric: true },
  ...DUE_AGE_SORT,
  { id: "customers", label: "Customers", numeric: true },
  { id: "last_sale", label: "Last sale", numeric: true },
  { id: "name", label: "Salesperson" },
  { id: "group", label: "Groups", numeric: true },
  { id: "status", label: "Status" },
];

export const MEMBER_SORT_OPTIONS = [
  ...DUE_AGE_SORT,
  { id: "last_sale", label: "Last sale", numeric: true },
  { id: "party", label: "Customer" },
  { id: "status", label: "Status" },
];

const MEMBER_NUMERIC = ["due", "last_sale", ...AGE_KEYS];

function memberStatusClass(status) {
  if (status === "urgent") return "err";
  if (status === "followup") return "warn";
  if (status === "credit") return "credit";
  return "ok";
}

function memberStatusLabel(status) {
  if (status === "urgent") return "Urgent";
  if (status === "followup") return "Follow up";
  if (status === "credit") return "Advance";
  return "On track";
}

export function MemberCustomersTable({ rows, extra }) {
  const [sort, setSort] = useState("due");
  const [dir, setDir] = useState("desc");
  const [page, setPage] = useState(1);
  const sortOptions = extra
    ? [...MEMBER_SORT_OPTIONS.slice(0, -1), { id: extra.id, label: extra.label, numeric: extra.numeric }, MEMBER_SORT_OPTIONS[MEMBER_SORT_OPTIONS.length - 1]]
    : MEMBER_SORT_OPTIONS;

  function onSort(id) {
    const next = toggleSort(sort, dir, id, extra?.numeric ? MEMBER_NUMERIC.concat(extra.id) : MEMBER_NUMERIC);
    setSort(next.sort);
    setDir(next.dir);
    setPage(1);
  }

  const ordered = (rows || []).slice().sort((a, b) => {
    const key = sort === "party" ? "name" : sort === "rep" ? "salesperson" : sort;
    const moneyKey = ["due", ...AGE_KEYS].includes(key);
    const av = moneyKey ? rowBucket(a, key) : String((key === extra?.id ? extra.get(a) : a[key]) || "").toLowerCase();
    const bv = moneyKey ? rowBucket(b, key) : String((key === extra?.id ? extra.get(b) : b[key]) || "").toLowerCase();
    if (av < bv) return dir === "asc" ? -1 : 1;
    if (av > bv) return dir === "asc" ? 1 : -1;
    return 0;
  });
  const total = ordered.length;
  const start = (page - 1) * 50;
  const pageRows = ordered.slice(start, start + 50);

  return (
    <div className="card table-card list-panel">
      <div className="table-card-head">
        <h3>Customers</h3>
      </div>
      <div className="member-filters">
        <FilterBar
          filters={{}}
          options={{}}
          onChange={() => {}}
          fields={[]}
          sort={sort}
          dir={dir}
          sortOptions={sortOptions}
          onSortChange={(next) => { setSort(next.sort); setDir(next.dir); setPage(1); }}
        />
      </div>
      {pageRows.length ? (
        <table className="dense list-table aging">
          <thead>
            <tr>
              <SortTh id="party" label="Customer" sort={sort} dir={dir} onSort={onSort} />
              {extra ? <SortTh id={extra.id} label={extra.label} sort={sort} dir={dir} onSort={onSort} /> : null}
              <SortTh id="status" label="Status" sort={sort} dir={dir} onSort={onSort} />
              <SortTh id="last_sale" label="Last sale" sort={sort} dir={dir} onSort={onSort} />
              <SortTh id="due" label="Due" sort={sort} dir={dir} onSort={onSort} className="num" />
              {AGE_KEYS.map((k) => (
                <SortTh key={k} id={k} label={AGE_LABELS[k]} sort={sort} dir={dir} onSort={onSort} className="num" />
              ))}
            </tr>
          </thead>
          <tbody>
            {pageRows.map((row) => (
              <tr key={row.uk} className="click-row" onClick={() => hashSet("customer/" + encodeURIComponent(row.uk))}>
                <td>
                  <div className="name-cell">
                    <span className="avatar sm">{initials(row.name)}</span>
                    <span className="clip" title={row.name}><strong>{row.name}</strong></span>
                  </div>
                </td>
                {extra ? (
                  <td>
                    {extra.get(row) ? (
                      extra.href(row) ? (
                        <button type="button" className="linkish" onClick={(e) => { e.stopPropagation(); hashSet(extra.href(row)); }}>{extra.get(row)}</button>
                      ) : extra.get(row)
                    ) : <span className="quiet">—</span>}
                  </td>
                ) : null}
                <td><span className={"pill " + memberStatusClass(row.status)}>{row.status_label || memberStatusLabel(row.status)}</span></td>
                <td className="quiet">{row.last_sale_label || "—"}</td>
                <td className={"num amount" + (row.credit ? " credit" : "")}>{row.credit ? money(Math.abs(row.due)) : money(row.due)}</td>
                {AGE_KEYS.map((k) => (
                  <td key={k} className="num">{bucketMoney(rowBucket(row, k))}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      ) : <p className="muted">No customers here.</p>}
      <ListPager page={page} total={total} onPage={setPage} />
    </div>
  );
}

export const STOCK_FIELDS = [
  { key: "item", label: "Item" },
  { key: "status", label: "Status" },
  { key: "position", label: "Stock" },
];

export const GROUP_FIELDS = [
  { key: "rep", label: "Salesperson" },
  { key: "status", label: "Status" },
];

export const REP_FIELDS = [
  { key: "group", label: "Group" },
  { key: "status", label: "Status" },
];

export function dataFields(meta) {
  const fields = [];
  if (meta?.item && !meta?.partyLabel) fields.push({ key: "item", label: "Item" });
  if (meta?.partyLabel) fields.push({ key: "party", label: meta.item === true && !meta.dates ? "Item" : meta.partyLabel === "Party Name" ? "Customer" : "Party" });
  if (meta?.group) fields.push({ key: "group", label: "Group" });
  if (meta?.partyType) fields.push({ key: "party_type", label: "Type" });
  if (meta?.rep) fields.push({ key: "rep", label: "Salesperson" });
  if (meta?.item && meta?.partyLabel) fields.push({ key: "item", label: "Item" });
  if (meta?.dates) fields.push({ key: "date", kind: "date", label: "Date" });
  if (meta?.balance) fields.push({ key: "balance", kind: "balance", label: "Balance" });
  return fields;
}

export function FilterBar({ filters, options, onChange, fields, sort, dir, sortOptions, onSortChange }) {
  const specs = fields || SALES_FIELDS;
  const opts = options || {};
  const active = specs.filter((field) => {
    if (field.kind === "date") return filters.date_from || filters.date_to;
    if (field.kind === "balance") return filters.balance_from || filters.balance_to;
    return filters[field.key];
  }).length;

  function clearAll() {
    const next = { ...filters };
    specs.forEach((field) => {
      if (field.kind === "date") {
        next.date_from = "";
        next.date_to = "";
      } else if (field.kind === "balance") {
        next.balance_from = "";
        next.balance_to = "";
      } else {
        next[field.key] = "";
      }
    });
    onChange(next);
  }

  return (
    <div className="filter-dock">
      {specs.map((field) => (
        field.kind === "date" ? (
          <DateMenu
            key="date"
            label={field.label}
            dateFrom={filters.date_from}
            dateTo={filters.date_to}
            onChange={(next) => onChange({ ...filters, ...next })}
          />
        ) : field.kind === "balance" ? (
          <BalanceMenu
            key="balance"
            label={field.label}
            from={filters.balance_from}
            to={filters.balance_to}
            onChange={(next) => onChange({ ...filters, ...next })}
          />
        ) : (
          <Menu
            key={field.key}
            label={field.label}
            value={filters[field.key]}
            options={opts[field.key]}
            onChange={(value) => onChange({ ...filters, [field.key]: value })}
          />
        )
      ))}
      {sortOptions?.length ? (
        <SortMenu sort={sort} dir={dir} options={sortOptions} onChange={onSortChange} />
      ) : null}
      {active ? <button type="button" className="filter-clear" onClick={clearAll}>Clear all</button> : null}
    </div>
  );
}

export function SortTh({ id, label, sort, dir, onSort, className }) {
  const active = sort === id || (id === "items" && sort === "line_count") || (id === "party" && sort === "name");
  return (
    <th className={"sort-th" + (active ? " on" : "") + (className ? " " + className : "")} onClick={() => onSort(id)}>
      <span>{label}</span>
      <i className={"sort-icon" + (active ? " " + dir : "")} />
    </th>
  );
}

export function toggleSort(sort, dir, id, numericIds) {
  if (sort === id) return { sort, dir: dir === "asc" ? "desc" : "asc" };
  return { sort: id, dir: (numericIds || []).includes(id) ? "desc" : "asc" };
}

export function ListPager({ page, total, onPage }) {
  if (!total || total <= 50) return null;
  return (
    <div className="list-pager">
      <button type="button" className="ghost" disabled={page <= 1} onClick={() => onPage(page - 1)}>Previous</button>
      <span>Page {page} of {Math.ceil(total / 50)}</span>
      <button type="button" className="ghost" disabled={page * 50 >= total} onClick={() => onPage(page + 1)}>Next</button>
    </div>
  );
}

export function EmptyCard({ title, copy }) {
  return (
    <div className="card empty-state">
      <strong>{title}</strong>
      <p className="muted">{copy}</p>
    </div>
  );
}
