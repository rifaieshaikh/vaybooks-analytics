import { hashSet, initials, money, moneyOrDash, round2 } from "./format";

function CustomerLink({ uk, name }) {
  if (uk) {
    return (
      <button type="button" className="linkish" onClick={() => hashSet("customer/" + encodeURIComponent(uk))}>
        {name || "Customer"}
      </button>
    );
  }
  return name || "No customer";
}

function sumMoney(rows, key) {
  const vals = (rows || []).map((row) => row[key]).filter((v) => v !== null && v !== undefined && v !== "");
  if (!vals.length) return null;
  return round2(vals.reduce((s, v) => s + Number(v || 0), 0));
}

function MoneyTile({ label, value, strong }) {
  return (
    <div className={"inv-tile" + (strong ? " main" : "")}>
      <span>{label}</span>
      <strong>{strong ? money(value || 0) : moneyOrDash(value)}</strong>
    </div>
  );
}

export default function InvoiceView({ detail, onBack, backLabel }) {
  const lines = detail.lines || [];
  const qty = round2(lines.reduce((s, line) => s + Number(line.qty || 0), 0));
  const lineBefore = sumMoney(lines, "before_tax");
  const lineTax = sumMoney(lines, "tax");
  const lineTotal = sumMoney(lines, "amount");

  return (
    <div className="inv-wrap">
      <div className="inv-nav">
        <button type="button" className="back-btn" onClick={onBack}>{backLabel || "Sales invoices"}</button>
      </div>
      <article className="inv-sheet">
        <header className="inv-letterhead">
          <div className="inv-brand">
            <span className="inv-mark">V</span>
            <div>
              <strong>Vay</strong>
              <span>Sales invoice</span>
            </div>
          </div>
          <div className="inv-id">
            <span className="eyebrow">Invoice</span>
            <h2>{detail.invoice || "Sale"}</h2>
            <p>{detail.date_label || "No date"} · {lines.length} {lines.length === 1 ? "item" : "items"}</p>
          </div>
        </header>
        <div className="inv-body">
          <div className="inv-parties">
            <div className="inv-party-card">
              <span className="eyebrow">Customer</span>
              <div className="inv-party-row">
                <span className="avatar">{initials(detail.party)}</span>
                <div>
                  <div className="inv-name"><CustomerLink uk={detail.customer_uk} name={detail.party} /></div>
                  <div className="muted">{detail.group || "No group"}</div>
                </div>
              </div>
            </div>
            <div className="inv-party-card">
              <span className="eyebrow">Salesperson</span>
              <div className="inv-party-row">
                <span className="avatar">{initials(detail.rep)}</span>
                <div>
                  <div className="inv-name">{detail.rep || "—"}</div>
                </div>
              </div>
            </div>
          </div>
          <div className="inv-tiles">
            <MoneyTile label="Before tax" value={detail.before_tax} />
            <MoneyTile label="Tax" value={detail.tax} />
            <MoneyTile label="Amount" value={detail.amount} strong />
          </div>
          <div className="inv-section-head">
            <h3>Line items</h3>
            <span className="muted">{lines.length ? "Amounts as imported" : ""}</span>
          </div>
          {lines.length ? (
            <div className="inv-table">
              <table className="dense inv-lines">
                <thead>
                  <tr>
                    <th>Item</th>
                    <th className="num">Qty</th>
                    <th className="num">Rate</th>
                    <th className="num">Before tax</th>
                    <th className="num">Tax</th>
                    <th className="num">Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {lines.map((line) => (
                    <tr key={line.uk}>
                      <td className="item-cell">{line.item || "—"}</td>
                      <td className="num">{line.qty}</td>
                      <td className="num">{moneyOrDash(line.rate)}</td>
                      <td className="num">{moneyOrDash(line.before_tax)}</td>
                      <td className="num">{moneyOrDash(line.tax)}</td>
                      <td className="num amount">{money(line.amount)}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr>
                    <td>Total</td>
                    <td className="num">{qty}</td>
                    <td />
                    <td className="num">{moneyOrDash(lineBefore)}</td>
                    <td className="num">{moneyOrDash(lineTax)}</td>
                    <td className="num amount">{moneyOrDash(lineTotal)}</td>
                  </tr>
                </tfoot>
              </table>
            </div>
          ) : (
            <div className="inv-empty">
              <strong>No line items</strong>
              <p>{detail.link_note || "Import item-wise sales with the same invoice number to show them here."}</p>
            </div>
          )}
        </div>
      </article>
    </div>
  );
}
