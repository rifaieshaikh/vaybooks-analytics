import { useEffect, useState } from "react";
import { api } from "./api";
import { money } from "./format";

export default function CashPage() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    let gone = false;
    api.cash().then((body) => {
      if (!gone) setData(body);
    }).catch((ex) => {
      if (!gone) setErr(ex.message || "Could not load cash.");
    });
    return () => { gone = true; };
  }, []);

  return (
    <div className="page">
      <h2>Cash</h2>
      {err ? <p className="err">{err}</p> : null}
      {data?.opening_label ? <p className="warn">{data.opening_label}</p> : null}
      {data && data.opening != null ? (
        <p className="muted">Opening {money(data.opening)}{data.opening_date ? " · " + data.opening_date : ""}</p>
      ) : null}
      <div className="analytics-list">
        {(data?.weeks || []).map((week) => (
          <article className="analytics-item" key={week.week}>
            <div>
              <p className="analytics-title">Week of {week.week}</p>
              <div className="analytics-meta">
                <span>Opening {week.opening == null ? "Not in this file" : money(week.opening)}</span>
                <span>Promises {money(week.promises || 0)}</span>
                <span>Payables {money(week.payables || 0)}</span>
                <span>Committed {money(week.committed || 0)}</span>
                <span>Net {week.net == null ? "—" : money(week.net)}</span>
              </div>
            </div>
          </article>
        ))}
      </div>
      {(data?.pending || []).length ? (
        <div className="card">
          <h3>Pending confirmation</h3>
          {(data.pending || []).map((row) => (
            <p key={row.customer_name + row.promised_on}>{row.customer_name} · {row.promised_on} · {money(row.amount)} · {row.label}</p>
          ))}
        </div>
      ) : null}
      {(data?.uncosted || []).length ? (
        <div className="card">
          <h3>Uncosted commitments</h3>
          {(data.uncosted || []).map((row) => (
            <p key={row.name}>{row.name} · {row.qty}{row.label ? " · " + row.label : ""}</p>
          ))}
        </div>
      ) : null}
    </div>
  );
}
