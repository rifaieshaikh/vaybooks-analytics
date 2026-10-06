import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { TYPE_META, can } from "./theme";
import { moneyOrDash } from "./format";
import { EmptyCard, FilterBar, ListPager, SortTh, dataFields, toggleSort } from "./FilterBar";

const TYPE_HINTS = {
  party: "Finance party master. Outstanding still holds the live balance.",
  arr: "Latest outstanding balances. Create uses these rows.",
  receipt: "Collections by party.",
  credit_note: "Sales returns. Net amount reduces sales and what the customer owes.",
  payments: "Payments by party.",
  stock: "On-hand stock by item, with category, item group, brand, and supplier.",
};

const COLUMNS = {
  party: [
    { id: "party", label: "Party" },
    { id: "party_type", label: "Type" },
    { id: "group", label: "Group" },
    { id: "amount", label: "Balance", money: true },
  ],
  arr: [
    { id: "party", label: "Party" },
    { id: "group", label: "Group" },
    { id: "amount", label: "Balance", money: true },
    { id: "days", label: "Days", field: "Days" },
  ],
  receipt: [
    { id: "date", label: "Date" },
    { id: "party", label: "Party" },
    { id: "group", label: "Group" },
    { id: "rep", label: "Salesperson" },
    { id: "amount", label: "Amount", money: true },
  ],
  credit_note: [
    { id: "date", label: "Date" },
    { id: "invoice", label: "Credit note" },
    { id: "party", label: "Party" },
    { id: "Sales Amount", label: "Sales amount", field: "Sales Amount", money: true },
    { id: "SGST", label: "SGST", field: "SGST", money: true },
    { id: "CGST", label: "CGST", field: "CGST", money: true },
    { id: "IGST", label: "IGST", field: "IGST", money: true },
    { id: "amount", label: "Net amount", money: true },
  ],
  payments: [
    { id: "date", label: "Date" },
    { id: "party", label: "Party" },
    { id: "group", label: "Group" },
    { id: "amount", label: "Amount", money: true },
  ],
  stock: [
    { id: "item", label: "Item" },
    { id: "category", label: "Category", field: "Category" },
    { id: "item_group", label: "Item group", field: "Item Group" },
    { id: "brand", label: "Brand", field: "Brand" },
    { id: "supplier", label: "Supplier", field: "Supplier" },
    { id: "qty", label: "Qty", field: "Qty", num: true },
    { id: "rate", label: "Rate", field: "P.Price", money: true },
  ],
};

function cellValue(row, col) {
  if (col.field) return row.fields?.[col.field];
  if (col.id === "date") return row.date || row.fields?.Date;
  if (col.id === "party") return row.party;
  if (col.id === "party_type") return row.party_type_label || row.party_type;
  if (col.id === "group") return row.group;
  if (col.id === "rep") return row.rep;
  if (col.id === "item") return row.item;
  if (col.id === "invoice") return row.invoice;
  if (col.id === "amount") return row.amount;
  return row[col.id];
}

export default function DataPage({ type, user, title }) {
  const meta = TYPE_META[type] || TYPE_META.sales;
  const heading = title || meta.label;
  const fields = useMemo(() => dataFields(meta), [meta]);
  const empty = useMemo(() => {
    const next = {};
    fields.forEach((field) => {
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
    return next;
  }, [fields]);
  const canUpload = can(user, `${type}.upload`);
  const [filters, setFilters] = useState(empty);
  const [sort, setSort] = useState(meta.dates ? "date" : (type === "stock" ? "item" : "party"));
  const [dir, setDir] = useState(meta.dates || type === "arr" ? "desc" : "asc");
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);
  const [savingUk, setSavingUk] = useState("");
  const columns = COLUMNS[type] || COLUMNS.party;
  const partyTypes = data?.party_types || [];

  function load(nextFilters, nextPage, nextSort, nextDir) {
    const params = { type, limit: "50", page: String(nextPage || 1), sort: nextSort, dir: nextDir, ...nextFilters };
    setLoading(true);
    api.rows(params)
      .then(setData)
      .catch((e) => setErr(e.message))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    setPage(1);
    load(filters, 1, sort, dir);
  }, [filters, sort, dir]);

  function onSort(id) {
    const next = toggleSort(sort, dir, id, ["date", "amount", "qty", "days"]);
    setSort(next.sort);
    setDir(next.dir);
  }

  async function onPartyType(row, nextType) {
    if ((row.party_type || "") === (nextType || "")) return;
    setErr("");
    setSavingUk(row.uk);
    try {
      await api.patchParty(row.uk, { party_type: nextType });
      load(filters, page, sort, dir);
    } catch (e) {
      setErr(e.message);
    } finally {
      setSavingUk("");
    }
  }

  return (
    <div className="workspace-page">
      <div className="page-head">
        <div className="page-head-copy">
          <h2>{heading}</h2>
          <p className="muted">{TYPE_HINTS[type] || "Browse saved rows. Import files from Data → Import."}{canUpload ? " Add files in Data → Import." : ""}</p>
        </div>
        <span className="page-stat">{data ? `${data.total} ${data.total === 1 ? "row" : "rows"}` : "…"}</span>
      </div>
      <FilterBar filters={filters} options={data?.options} onChange={setFilters} fields={fields} />
      {err ? <p className="err">{err}</p> : null}
      {loading && !data ? <EmptyCard title={"Loading " + heading.toLowerCase()} copy="Pulling the latest rows." /> : null}
      {!loading && !data?.rows?.length ? <EmptyCard title="No rows match" copy={"Clear a filter, or import a file to add " + heading.toLowerCase() + "."} /> : null}
      {data?.rows?.length ? (
        <div className="card table-card list-panel">
          <table className="dense list-table">
            <thead>
              <tr>
                {columns.map((col) => (
                  <SortTh key={col.id} id={col.id} label={col.label} sort={sort} dir={dir} onSort={onSort} className={col.money || col.num ? "num" : ""} />
                ))}
              </tr>
            </thead>
            <tbody>
              {data.rows.map((row) => (
                <tr key={row.uk}>
                  {columns.map((col) => {
                    const value = cellValue(row, col);
                    if (col.money) return <td key={col.id} className="num amount">{moneyOrDash(value)}</td>;
                    if (col.num) return <td key={col.id} className="num">{value ?? "—"}</td>;
                    if (col.id === "party_type" && type === "party" && canUpload) {
                      return (
                        <td key={col.id}>
                          <select
                            value={row.party_type || ""}
                            disabled={savingUk === row.uk}
                            onChange={(e) => onPartyType(row, e.target.value)}
                          >
                            <option value="">—</option>
                            {row.party_type && !partyTypes.some((item) => item.id === row.party_type) ? (
                              <option value={row.party_type}>{row.party_type_label || row.party_type}</option>
                            ) : null}
                            {partyTypes.map((item) => (
                              <option key={item.id} value={item.id}>{item.label}</option>
                            ))}
                          </select>
                        </td>
                      );
                    }
                    if (col.id === "group") return <td key={col.id}>{value ? <span className="soft-tag">{value}</span> : <span className="quiet">—</span>}</td>;
                    if (col.id === "date") return <td key={col.id} className="quiet">{value || "—"}</td>;
                    return <td key={col.id}>{value || "—"}</td>;
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      <ListPager page={page} total={data?.total} onPage={(p) => { setPage(p); load(filters, p, sort, dir); }} />
    </div>
  );
}
