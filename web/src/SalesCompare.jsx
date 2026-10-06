import { money } from "./format";

export function formatQty(n) {
  if (n === null || n === undefined || n === "") return "—";
  const v = Number(n);
  if (!Number.isFinite(v)) return "—";
  return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

export function resultLabel(change) {
  if (change === null || change === undefined || change === "") return "—";
  const n = Number(change);
  if (!Number.isFinite(n)) return "—";
  if (n > 0) return "Up";
  if (n < 0) return "Down";
  return "Unchanged";
}

function signed(n, format) {
  if (n === null || n === undefined || n === "") return "—";
  const v = Number(n);
  if (!Number.isFinite(v)) return "—";
  const body = format(Math.abs(v));
  if (v > 0) return "+" + body;
  if (v < 0) return "-" + body;
  return body;
}

function changePct(change, prior) {
  if (change === null || change === undefined || prior === null || prior === undefined) return "—";
  const base = Number(prior);
  const delta = Number(change);
  if (!Number.isFinite(base) || !Number.isFinite(delta) || base === 0) return "—";
  const pct = (delta / base) * 100;
  const body = Math.abs(pct).toLocaleString(undefined, { maximumFractionDigits: 1, minimumFractionDigits: 1 }) + "%";
  if (pct > 0) return "+" + body;
  if (pct < 0) return "-" + body;
  return body;
}

function blocksOf(data) {
  if (!data) return [];
  if (data.month || data.year) return [data.month, data.year].filter(Boolean);
  if (data.qty || data.amount) return [data];
  return [];
}

function MeasureTable({ block }) {
  const qty = block.qty || {};
  const amount = block.amount || {};
  const currentLabel = block.current_label || "This period";
  const priorLabel = block.prior_label || "Prior period";
  const rows = [];
  if (qty.status === "unavailable") {
    rows.push(null);
  } else {
    rows.push(["Quantity", qty, formatQty]);
  }
  rows.push(["Amount", amount, money]);
  return (
    <div className="card table-card list-panel analytics-table">
      {block.label ? <div className="table-card-head"><h3>{block.label}</h3></div> : null}
      {block.verdict ? <p className="analytics-note">{block.verdict}</p> : null}
      {qty.status === "unavailable" && qty.reason ? <p className="muted analytics-note">{qty.reason}</p> : null}
      <div className="table-wrap">
        <table className="dense list-table compact">
          <thead>
            <tr>
              <th>Measure</th>
              <th className="num">{currentLabel}</th>
              <th className="num">{priorLabel}</th>
              <th className="num">Change</th>
              <th className="num">Change %</th>
              <th>Result</th>
            </tr>
          </thead>
          <tbody>
            {rows.filter(Boolean).map(([label, measure, format]) => (
              <tr key={label}>
                <td>{label}</td>
                <td className="num">{measure.current == null ? "—" : format(measure.current)}</td>
                <td className="num">{measure.prior == null ? "—" : format(measure.prior)}</td>
                <td className="num">{signed(measure.change, format)}</td>
                <td className="num">{changePct(measure.change, measure.prior)}</td>
                <td>{resultLabel(measure.change)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function SalesCompare({ data }) {
  const blocks = blocksOf(data);
  if (!blocks.length) return null;
  return (
    <div className="stack">
      {blocks.map((block) => <MeasureTable key={block.label || block.verdict} block={block} />)}
    </div>
  );
}
