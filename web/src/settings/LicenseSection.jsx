import { useEffect, useState } from "react";
import { api } from "../api";

export default function LicenseSection() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    api.license().then(setData).catch((e) => setErr(e.message || "Could not load the license"));
  }, []);

  return (
    <div className="card">
      <h3>Plan and support</h3>
      {err ? <p className="err">{err}</p> : null}
      {!data && !err ? <p className="muted">Loading…</p> : null}
      {data ? (
        <div className="stack">
          <p>{data.message}</p>
          <p className="muted">Version {data.version || "dev"}</p>
          <p>Wholesale {data.packs?.wholesale ? "enabled" : "off"} · Retail {data.packs?.retail ? "enabled" : "off"}</p>
          <p className="muted">{data.renewal_note}</p>
          {data.support_contact ? <p>Support {data.support_contact}</p> : <p className="muted">No support contact is configured.</p>}
          <button type="button" onClick={() => api.downloadDiagnostics().catch((e) => setErr(e.message || "Could not download diagnostics"))}>
            Download diagnostics
          </button>
        </div>
      ) : null}
    </div>
  );
}
