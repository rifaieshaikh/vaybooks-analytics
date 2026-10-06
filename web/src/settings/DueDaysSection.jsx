import { useEffect, useState } from "react";
import { api } from "../api";

export default function DueDaysSection() {
  const [days, setDays] = useState(30);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    api.dueDays()
      .then((d) => setDays(Number(d.due_days) || 30))
      .catch((e) => setErr(e.message))
      .finally(() => setLoaded(true));
  }, []);

  async function save() {
    setBusy(true);
    setErr("");
    setMsg("");
    try {
      const out = await api.setDueDays({ due_days: Number(days) });
      setDays(Number(out.due_days) || 30);
      setMsg("Saved.");
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <h2>Ordering due days</h2>
      <p className="muted">
        Default credit terms for Ordering (ordered while overdue) and Order check
        (oldest open vs due days). Customers, groups, and sales reps can override.
        You can also edit the default under Settings → Order check.
      </p>
      <div className="row gap" style={{ marginTop: 12, alignItems: "center" }}>
        <label>
          Default due days
          <input
            type="number"
            min={0}
            style={{ width: 96, marginLeft: 8 }}
            value={days}
            disabled={!loaded || busy}
            onChange={(e) => setDays(e.target.value)}
          />
        </label>
        <button type="button" disabled={!loaded || busy} onClick={save}>Save</button>
      </div>
      {msg ? <p className="ok">{msg}</p> : null}
      {err ? <p className="err">{err}</p> : null}
    </div>
  );
}
