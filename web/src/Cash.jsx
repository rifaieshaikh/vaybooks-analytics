import { useEffect, useState } from "react";
import { api } from "./api";
import { money } from "./format";

export default function CashPage() {
  const [data, setData] = useState(null);
  const [forecast, setForecast] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    let gone = false;
    api.cash().then((body) => {
      if (!gone) setData(body);
    }).catch((ex) => {
      if (!gone) setErr(ex.message || "Could not load cash.");
    });
    api.recoveryForecast().then((body) => {
      if (!gone) setForecast(body);
    }).catch(() => {
      if (!gone) setForecast(null);
    });
    return () => { gone = true; };
  }, []);

  return (
    <div className="page">
      <h2>Cash</h2>
      <p className="muted">Weekly promises are the amounts already entered. Expected recovery is a separate check and is left out of those weeks.</p>
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
      {forecast ? <RecoveryForecast forecast={forecast} /> : null}
    </div>
  );
}

function RecoveryForecast({ forecast }) {
  const interval = forecast.interval || {};
  const evidence = forecast.evidence || {};
  const backtest = forecast.backtest || {};
  return (
    <div className="card">
      <h3>Expected recovery · {forecast.horizon_days} days</h3>
      <p className="muted">{forecast.method_label}</p>
      {forecast.released ? (
        <p>Expected cash {money(forecast.expected_cash)} · range {money(interval.low)} to {money(interval.high)}</p>
      ) : (
        <p>{forecast.reason}</p>
      )}
      <p className="muted">
        Completed periods used {evidence.closed_periods ?? 0} of {evidence.required_periods ?? 0} required.
        Backtest origins {backtest.origins ?? 0} of {backtest.required_origins ?? 0}.
        {backtest.bias_ratio == null ? "" : " Bias " + backtest.bias_ratio + "."}
        {backtest.interval_coverage == null ? "" : " Interval coverage " + backtest.interval_coverage + "."}
      </p>
      {(forecast.assumptions || []).map((line) => <p key={line} className="muted">{line}</p>)}
      {(forecast.exclusions || []).map((line) => <p key={line} className="warn">{line}</p>)}
      {(forecast.segments || []).map((row) => (
        <p key={row.segment} className="muted">
          {row.segment}: {row.released ? money(row.expected_cash) : (row.reason || "Withheld")}
        </p>
      ))}
    </div>
  );
}
