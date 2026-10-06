import { useEffect, useState } from "react";
import { api } from "./api";
import { hashBack, hashSet, initials, money, moneyOrDash } from "./format";
import InvoiceView from "./InvoiceView";
import { EmptyCard, FilterBar, ITEM_FIELDS, ListPager, SortTh, toggleSort } from "./FilterBar";

const emptyFilters = { party: "", group: "", rep: "", invoice: "", item: "", date_from: "", date_to: "" };

export default function ItemsPage() {
  const [filters, setFilters] = useState(emptyFilters);
  const [sort, setSort] = useState("date");
  const [dir, setDir] = useState("desc");
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [invoiceId, setInvoiceId] = useState("");
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);

  function load(nextFilters, nextPage, nextSort, nextDir) {
    setLoading(true);
    api.itemLines({
      ...nextFilters,
      sort: nextSort,
      dir: nextDir,
      page: String(nextPage || 1),
    })
      .then(setData)
      .catch((e) => setErr(e.message))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    setPage(1);
    load(filters, 1, sort, dir);
  }, [filters, sort, dir]);

  function onSort(id) {
    const next = toggleSort(sort, dir, id, ["date", "amount", "tax", "before_tax", "qty"]);
    setSort(next.sort);
    setDir(next.dir);
  }

  if (invoiceId) {
    return <EmbeddedInvoice invoiceId={invoiceId} onBack={() => { hashBack(""); setInvoiceId(""); }} />;
  }

  return (
    <div className="workspace-page">
      <div className="page-head">
        <div className="page-head-copy">
          <h2>Item-wise sales</h2>
          <p className="muted">Each line is tagged to a customer, group, and salesperson.</p>
        </div>
        <span className="page-stat">{data ? `${data.total} ${data.total === 1 ? "line" : "lines"}` : "…"}</span>
      </div>
      <FilterBar filters={filters} options={data?.options} onChange={setFilters} fields={ITEM_FIELDS} />
      {err ? <p className="err">{err}</p> : null}
      {loading && !data ? <EmptyCard title="Loading item lines" copy="Pulling the latest item-wise sales." /> : null}
      {!loading && !data?.lines?.length ? <EmptyCard title="No item lines match" copy="Clear a filter, or import item-wise sales to see lines here." /> : null}
      {data?.lines?.length ? (
        <div className="card table-card list-panel">
          <table className="dense list-table">
            <thead>
              <tr>
                <SortTh id="item" label="Item" sort={sort} dir={dir} onSort={onSort} className="sticky-inv" />
                <SortTh id="party" label="Customer" sort={sort} dir={dir} onSort={onSort} />
                <SortTh id="group" label="Group" sort={sort} dir={dir} onSort={onSort} />
                <SortTh id="rep" label="Salesperson" sort={sort} dir={dir} onSort={onSort} />
                <SortTh id="invoice" label="Invoice" sort={sort} dir={dir} onSort={onSort} />
                <SortTh id="date" label="Date" sort={sort} dir={dir} onSort={onSort} />
                <SortTh id="qty" label="Qty" sort={sort} dir={dir} onSort={onSort} className="num" />
                <SortTh id="tax" label="Tax" sort={sort} dir={dir} onSort={onSort} className="num" />
                <SortTh id="amount" label="Amount" sort={sort} dir={dir} onSort={onSort} className="num sticky-amt" />
              </tr>
            </thead>
            <tbody>
              {data.lines.map((line) => (
                <tr
                  key={line.uk}
                  className={line.invoice_id ? "click-row" : ""}
                  onClick={() => { if (line.invoice_id) { setInvoiceId(line.invoice_id); hashSet("invoice/" + line.invoice_id); } }}
                >
                  <td className="sticky-inv item-name"><strong>{line.item || "Item"}</strong></td>
                  <td>
                    <div className="name-cell">
                      <span className="avatar sm">{initials(line.party)}</span>
                      <span className="clip">
                        {line.customer_uk ? (
                          <button type="button" className="linkish" onClick={(e) => { e.stopPropagation(); hashSet("customer/" + encodeURIComponent(line.customer_uk)); }}>{line.party || "Customer"}</button>
                        ) : (line.party || "—")}
                      </span>
                    </div>
                  </td>
                  <td>{line.group ? <span className="soft-tag">{line.group}</span> : <span className="quiet">—</span>}</td>
                  <td className="clip">{line.rep || "—"}</td>
                  <td><span className="inv-no">{line.invoice || (line.invoice_id ? "Open" : "—")}</span></td>
                  <td className="quiet">{line.date_label || "—"}</td>
                  <td className="num">{line.qty}</td>
                  <td className="num quiet">{moneyOrDash(line.tax)}</td>
                  <td className="num amount sticky-amt">{money(line.amount)}</td>
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

function EmbeddedInvoice({ invoiceId, onBack }) {
  const [detail, setDetail] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    api.invoice(invoiceId).then(setDetail).catch((e) => setErr(e.message));
  }, [invoiceId]);
  if (err) {
    return (
      <div className="inv-wrap">
        <div className="inv-nav"><button type="button" className="back-btn" onClick={onBack}>Item-wise sales</button></div>
        <EmptyCard title="Could not open invoice" copy={err} />
      </div>
    );
  }
  if (!detail) return <EmptyCard title="Opening invoice" copy="One moment…" />;
  return <InvoiceView detail={detail} onBack={onBack} backLabel="Item-wise sales" />;
}
