import { useEffect, useState } from "react";
import { api } from "./api";

const TYPES = ["sales", "receipt", "credit_note", "arr", "party", "items", "stock", "payments"];
const REQUIRED = {
  sales: ["Date", "Party Name", "Sales Rep", "Net Amount"],
  receipt: ["Date", "Account Name", "Sales Rep", "Amount"],
  credit_note: ["Date", "Party Name", "Invoice No", "Net Amount"],
  arr: ["Account Name", "Group", "Balance"],
  party: ["Account Name", "Group"],
  items: ["Date", "Item Name", "Qty", "Rate"],
  stock: ["Item Name", "Qty", "P.Price"],
  payments: ["Date", "Account Name", "Amount"],
};

export default function MappersPage() {
  const [type, setType] = useState("sales");
  const [columnMap, setColumnMap] = useState({});
  const [uniqueKey, setUniqueKey] = useState([]);
  const [extra, setExtra] = useState("");
  const [warning, setWarning] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  useEffect(() => {
    api.mapper(type).then((d) => {
      setColumnMap(d.column_map || {});
      setUniqueKey(d.unique_key || []);
      setWarning("");
      setMsg("");
    }).catch((e) => setErr(e.message));
  }, [type]);

  const optional = type === "items" || type === "stock"
    ? ["Category", "Item Group", "Brand", "Supplier"]
    : [];
  const fields = Array.from(new Set([
    ...(REQUIRED[type] || []),
    ...optional,
    ...Object.values(columnMap).filter((d) => d && !["__skip__", "skip", "(skip)"].includes(String(d).toLowerCase())),
    extra,
  ].filter(Boolean)));

  function toggleKey(name) {
    setUniqueKey((prev) => (prev.includes(name) ? prev.filter((x) => x !== name) : [...prev, name]));
  }

  async function save() {
    setErr("");
    try {
      const saved = await api.saveMapper(type, { column_map: columnMap, unique_key: uniqueKey, extra_types: {} });
      setWarning(saved.warning || "");
      setMsg("Saved.");
    } catch (e) {
      setErr(e.message);
    }
  }

  function onSample(ev) {
    const file = ev.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const text = String(reader.result || "");
      const first = text.split(/\r?\n/)[0];
      const headers = first.split(",").map((h) => h.trim()).filter(Boolean);
      const next = { ...columnMap };
      headers.forEach((h) => {
        if (!next[h]) next[h] = (REQUIRED[type] || []).includes(h) ? h : h;
      });
      setColumnMap(next);
      setMsg("Headers read from sample. Rows were not uploaded.");
    };
    reader.readAsText(file.slice(0, 4096));
  }

  return (
    <div className="card">
      <h2>Data mappers</h2>
      <p className="muted">Each file type has its own unique key. Sample files map headers only — they do not insert rows.</p>
      <label>Type</label>
      <select value={type} onChange={(e) => setType(e.target.value)}>
        {TYPES.map((t) => <option key={t}>{t}</option>)}
      </select>
      <label>Sample CSV (headers only)</label>
      <input type="file" accept=".csv,.txt" onChange={onSample} />
      <label>Column map (uploaded header → field)</label>
      {Object.keys(columnMap).map((src) => (
        <div className="row" key={src}>
          <input value={src} readOnly />
          <select
            value={!columnMap[src] || ["__skip__", "skip", "(skip)"].includes(String(columnMap[src]).toLowerCase()) ? "__skip__" : columnMap[src]}
            onChange={(e) => setColumnMap({ ...columnMap, [src]: e.target.value })}
          >
            <option value="__skip__">Skip column</option>
            {fields.map((f) => <option key={f} value={f}>{f}</option>)}
          </select>
        </div>
      ))}
      <label>Add extra field name (e.g. Invoice No)</label>
      <input value={extra} onChange={(e) => setExtra(e.target.value)} placeholder="Invoice No" />
      <label>Unique key</label>
      {fields.map((name) => (
        <label key={name} style={{ fontWeight: 400 }}>
          <input type="checkbox" checked={uniqueKey.includes(name)} onChange={() => toggleKey(name)} /> {name}
        </label>
      ))}
      {warning ? <p className="warn">{warning}</p> : null}
      {type === "sales" && new Set(uniqueKey).size === 4 && ["Date", "Party Name", "Sales Rep", "Net Amount"].every((n) => uniqueKey.includes(n)) ? (
        <p className="warn">Same customer + date + amount counts as one sale.</p>
      ) : null}
      {err ? <p className="err">{err}</p> : null}
      {msg ? <p className="ok">{msg}</p> : null}
      <button onClick={save}>Save mapper</button>
      {" "}
      <button className="secondary" onClick={() => api.rebuildUk(type).then(() => setMsg("Unique keys rebuilt.")).catch((e) => setErr(e.message))}>Rebuild unique keys</button>
    </div>
  );
}
