import { useEffect, useState } from "react";
import { api } from "../api";

export default function AuditSection() {
  const [events, setEvents] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    api.audit().then((body) => setEvents(body.events || [])).catch((e) => setErr(e.message || "Could not load audit"));
  }, []);

  if (err) return <div className="card">{err}</div>;
  if (!events) return <div className="card">Loading audit…</div>;
  return (
    <div className="card">
      <h2>Audit</h2>
      <p className="muted">Sign-in, create, cancel, entitlement, and restore events. This list is append-only.</p>
      {events.length ? (
        <table className="dense list-table compact">
          <thead>
            <tr><th>When</th><th>Who</th><th>Action</th><th>Detail</th></tr>
          </thead>
          <tbody>
            {events.map((row) => (
              <tr key={row.id}>
                <td>{row.created_at}</td>
                <td>{row.actor}</td>
                <td>{row.action}</td>
                <td>{row.detail}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : <p className="muted">No events yet.</p>}
    </div>
  );
}
