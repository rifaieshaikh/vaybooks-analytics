import { useEffect, useState } from "react";
import { api } from "./api";

const TYPES = ["", "sales", "receipt", "credit_note", "arr", "party", "items", "stock", "payments", "combined"];

export default function FilesPage() {
  const [list, setList] = useState([]);
  const [type, setType] = useState("combined");
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);
  const [err, setErr] = useState("");
  const [browseId, setBrowseId] = useState("");
  const [browseType, setBrowseType] = useState("sales");
  const [rows, setRows] = useState(null);

  function refresh() {
    api.uploads().then((d) => setList(d.uploads || [])).catch((e) => setErr(e.message));
  }
  useEffect(refresh, []);

  async function upload() {
    setErr("");
    try {
      const out = await api.upload(file, type === "combined" ? "" : type);
      setResult(out);
      refresh();
    } catch (e) {
      setErr(e.message);
    }
  }

  async function openRows(id, t) {
    setBrowseId(id);
    setBrowseType(t || "sales");
    const data = await api.rows({ type: t || "sales", upload: id, limit: "50" });
    setRows(data);
  }

  const snapshot = browseType === "arr" || browseType === "stock";

  return (
    <div>
      <div className="card">
        <h2>Upload a file</h2>
        <label>Kind</label>
        <select value={type} onChange={(e) => setType(e.target.value)}>
          {TYPES.filter(Boolean).map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <label>Excel or CSV</label>
        <input type="file" onChange={(e) => setFile(e.target.files[0])} />
        <button disabled={!file} onClick={upload}>Save file</button>
        {err ? <p className="err">{err}</p> : null}
        {result ? <pre className="ok">{JSON.stringify(result.types, null, 2)}</pre> : null}
      </div>
      <div className="card">
        <h2>Library</h2>
        <table>
          <thead><tr><th>File</th><th>Kind</th><th></th></tr></thead>
          <tbody>
            {list.map((u) => (
              <tr key={u.id}>
                <td>{u.filename}</td>
                <td>{u.type}</td>
                <td>
                  <button className="secondary" onClick={() => api.downloadUpload(u.id, u.filename)}>Download as-is</button>{" "}
                  <button className="secondary" onClick={() => openRows(u.id, u.type === "combined" ? "sales" : u.type)}>Browse rows</button>{" "}
                  <button className="secondary" onClick={() => api.deleteUpload(u.id).then(refresh)}>Delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {browseId ? (
        <div className="card">
          <h2>Rows in this file</h2>
          <label>Type</label>
          <select value={browseType} onChange={(e) => openRows(browseId, e.target.value)}>
            {["sales", "receipt", "arr", "party", "items", "stock", "payments"].map((t) => <option key={t}>{t}</option>)}
          </select>
          {snapshot ? <p className="muted">Date filters do not apply to arr or stock.</p> : null}
          {rows ? <p className="muted">{rows.total} row(s)</p> : null}
          <div className="table-wrap">
            <table>
              <tbody>
                {(rows?.rows || []).map((r, i) => (
                  <tr key={i}>
                    {Object.entries(r.fields || {}).map(([k, v]) => <td key={k}><span className="muted">{k}:</span> {String(v)}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </div>
  );
}
