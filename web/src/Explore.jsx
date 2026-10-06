import { useState } from "react";
import { api } from "./api";

export default function ExplorePage() {
  const [type, setType] = useState("sales");
  const [form, setForm] = useState({ party: "", rep: "", group: "", item: "", date_from: "", date_to: "" });
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const snapshot = type === "arr" || type === "stock" || type === "party";

  function set(k, v) {
    setForm({ ...form, [k]: v });
  }

  async function search() {
    setErr("");
    const params = { type, limit: "50", ...form };
    if (snapshot) {
      delete params.date_from;
      delete params.date_to;
    }
    if (type === "stock") delete params.group;
    try {
      setData(await api.rows(params));
    } catch (e) {
      setErr(e.message);
    }
  }

  return (
    <div className="card">
      <h2>Look at stored rows</h2>
      <p className="muted">This does not change official reports. Create always uses full history.</p>
      <label>Type</label>
      <select value={type} onChange={(e) => setType(e.target.value)}>
        {["sales", "receipt", "arr", "party", "items", "stock", "payments"].map((t) => <option key={t}>{t}</option>)}
      </select>
      <div className="row">
        <div><label>Party / account</label><input value={form.party} onChange={(e) => set("party", e.target.value)} /></div>
        <div><label>Sales rep</label><input value={form.rep} onChange={(e) => set("rep", e.target.value)} /></div>
        {type !== "stock" ? <div><label>Group</label><input value={form.group} onChange={(e) => set("group", e.target.value)} /></div> : null}
        <div><label>Item</label><input value={form.item} onChange={(e) => set("item", e.target.value)} /></div>
      </div>
      {snapshot ? <p className="muted">No date filter for outstanding, parties, or stock.</p> : (
        <div className="row">
          <div><label>From</label><input type="date" value={form.date_from} onChange={(e) => set("date_from", e.target.value)} /></div>
          <div><label>To</label><input type="date" value={form.date_to} onChange={(e) => set("date_to", e.target.value)} /></div>
        </div>
      )}
      <button onClick={search}>Search</button>
      {err ? <p className="err">{err}</p> : null}
      {data ? <p className="muted">{data.total} matching row(s)</p> : null}
      <div className="table-wrap">
        <table>
          <tbody>
            {(data?.rows || []).map((r, i) => (
              <tr key={i}>
                {Object.entries(r.fields || {}).slice(0, 8).map(([k, v]) => <td key={k}>{k}: {String(v)}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
