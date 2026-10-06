import { useEffect, useState } from "react";
import { api } from "../api";

export default function PartyTypesSection() {
  const [types, setTypes] = useState([]);
  const [label, setLabel] = useState("");
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  function refresh() {
    api.partyTypes().then((d) => setTypes(d.types || [])).catch((e) => setErr(e.message));
  }
  useEffect(refresh, []);

  async function add() {
    setErr("");
    setMsg("");
    setBusy(true);
    try {
      const out = await api.addPartyType(label);
      setTypes(out.types || []);
      setLabel("");
      setMsg("Added.");
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="card">
        <h2>Add party type</h2>
        <p className="muted">These types appear on the Parties list. Outstanding imports tag a party as Customer.</p>
        <div className="row">
          <div>
            <label>Name</label>
            <input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Vendor" />
          </div>
        </div>
        <button disabled={busy || !label.trim()} onClick={add}>{busy ? "Adding…" : "Add type"}</button>
      </div>
      <div className="card table-card list-panel">
        <h2>Party types</h2>
        <table className="dense list-table">
          <thead>
            <tr>
              <th>Type</th>
              <th></th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {types.map((item) => (
              <tr key={item.id}>
                <td>{item.label}</td>
                <td>{item.builtin ? <span className="pill">Built in</span> : null}</td>
                <td className="num">
                  {item.builtin ? null : (
                    <button
                      type="button"
                      className="ghost"
                      onClick={() => {
                        if (!window.confirm("Remove " + item.label + "?")) return;
                        setErr("");
                        api.deletePartyType(item.id)
                          .then((d) => setTypes(d.types || []))
                          .catch((e) => setErr(e.message));
                      }}
                    >
                      Remove
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {msg ? <p className="ok">{msg}</p> : null}
      {err ? <p className="err">{err}</p> : null}
    </div>
  );
}
