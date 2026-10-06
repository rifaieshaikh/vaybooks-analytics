import { useEffect, useState } from "react";
import { api } from "./api";
import { hashBack, hashGet, hashReturnLabel, hashSet, initials, money, moneyOrDash } from "./format";
import InvoiceView from "./InvoiceView";
import { EmptyCard, FilterBar, ListPager, SALES_FIELDS, SortTh, toggleSort } from "./FilterBar";

const emptyFilters = { party: "", group: "", rep: "", invoice: "", date_from: "", date_to: "" };

export default function SalesPage() {
  const [filters, setFilters] = useState(emptyFilters);
  const [sort, setSort] = useState("date");
  const [dir, setDir] = useState("desc");
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [invoiceId, setInvoiceId] = useState("");
  const [detail, setDetail] = useState(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);

  function load(nextFilters, nextPage, nextSort, nextDir) {
    setLoading(true);
    api.invoices({
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

  useEffect(() => {
    const h = hashGet();
    if (h.startsWith("invoice/")) setInvoiceId(h.slice("invoice/".length));
  }, []);

  useEffect(() => {
    function onHash() {
      const h = hashGet();
      if (h.startsWith("invoice/")) setInvoiceId(h.slice("invoice/".length));
      else if (!h) {
        setInvoiceId("");
        setDetail(null);
      }
    }
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  useEffect(() => {
    if (!invoiceId) return undefined;
    setLoading(true);
    api.invoice(invoiceId).then(setDetail).catch((e) => setErr(e.message)).finally(() => setLoading(false));
    return undefined;
  }, [invoiceId]);

  function openInvoice(id) {
    setInvoiceId(id);
    hashSet("invoice/" + id);
  }

  function onSort(id) {
    const next = toggleSort(sort, dir, id, ["date", "amount", "tax", "before_tax", "items"]);
    setSort(next.sort);
    setDir(next.dir);
  }

  if (invoiceId) {
    if (detail && detail.id === invoiceId) {
      return (
        <>
          {err ? <p className="err">{err}</p> : null}
          <InvoiceView
            detail={detail}
            onBack={() => hashBack("")}
            backLabel={hashReturnLabel("Sales invoices")}
          />
        </>
      );
    }
    return <EmptyCard title="Opening invoice" copy={err || "One moment…"} />;
  }

  return (
    <div className="workspace-page">
      <div className="page-head">
        <div className="page-head-copy">
          <h2>Sales invoices</h2>
          <p className="muted">Filter, sort, and open any invoice for customer, tax, and line items.</p>
        </div>
        <span className="page-stat">{data ? `${data.total} ${data.total === 1 ? "invoice" : "invoices"}` : "…"}</span>
      </div>
      <FilterBar filters={filters} options={data?.options} onChange={setFilters} fields={SALES_FIELDS} />
      {err ? <p className="err">{err}</p> : null}
      {loading && !data ? <EmptyCard title="Loading invoices" copy="Pulling the latest sales." /> : null}
      {!loading && !data?.invoices?.length ? <EmptyCard title="No invoices match" copy="Clear a filter, or import sales to see invoices here." /> : null}
      {data?.invoices?.length ? (
        <div className="card table-card list-panel">
          <table className="dense list-table">
            <thead>
              <tr>
                <SortTh id="invoice" label="Invoice" sort={sort} dir={dir} onSort={onSort} className="sticky-inv" />
                <SortTh id="party" label="Customer" sort={sort} dir={dir} onSort={onSort} />
                <SortTh id="group" label="Group" sort={sort} dir={dir} onSort={onSort} />
                <SortTh id="rep" label="Salesperson" sort={sort} dir={dir} onSort={onSort} />
                <SortTh id="date" label="Date" sort={sort} dir={dir} onSort={onSort} />
                <SortTh id="items" label="Items" sort={sort} dir={dir} onSort={onSort} className="num" />
                <SortTh id="before_tax" label="Before tax" sort={sort} dir={dir} onSort={onSort} className="num" />
                <SortTh id="tax" label="Tax" sort={sort} dir={dir} onSort={onSort} className="num" />
                <SortTh id="amount" label="Amount" sort={sort} dir={dir} onSort={onSort} className="num sticky-amt" />
              </tr>
            </thead>
            <tbody>
              {data.invoices.map((inv) => (
                <tr key={inv.id} className="click-row" onClick={() => openInvoice(inv.id)}>
                  <td className="sticky-inv"><span className="inv-no">{inv.invoice || "—"}</span></td>
                  <td>
                    <div className="name-cell">
                      <span className="avatar sm">{initials(inv.party)}</span>
                      <span className="clip">
                        {inv.customer_uk ? (
                          <button type="button" className="linkish" onClick={(e) => { e.stopPropagation(); hashSet("customer/" + encodeURIComponent(inv.customer_uk)); }}>{inv.party || "Customer"}</button>
                        ) : <strong>{inv.party || "—"}</strong>}
                      </span>
                    </div>
                  </td>
                  <td>{inv.group ? <span className="soft-tag">{inv.group}</span> : <span className="quiet">—</span>}</td>
                  <td className="clip">{inv.rep || "—"}</td>
                  <td className="quiet">{inv.date_label || "—"}</td>
                  <td className="num"><span className={"item-badge" + (inv.line_count ? "" : " empty")}>{inv.line_count || 0}</span></td>
                  <td className="num quiet">{moneyOrDash(inv.before_tax)}</td>
                  <td className="num quiet">{moneyOrDash(inv.tax)}</td>
                  <td className="num amount sticky-amt">{money(inv.amount)}</td>
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
