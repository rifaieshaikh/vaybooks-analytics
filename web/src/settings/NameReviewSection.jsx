import { useEffect, useState } from "react";
import { api } from "../api";

export default function NameReviewSection() {
  const [items, setItems] = useState([]);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  function load() {
    return api.entityReview()
      .then((data) => setItems(data.items || []))
      .catch((e) => setErr(e.message));
  }

  useEffect(() => {
    load();
  }, []);

  async function act(item, mode) {
    setBusy(true);
    setErr("");
    setMsg("");
    const body = {
      kind: item.kind,
      left_name: item.left_name,
      right_entity_id: item.right_entity_id,
    };
    try {
      const out = mode === "merge" ? await api.mergeEntityReview(body) : await api.rejectEntityReview(body);
      setItems(out.items || []);
      setMsg(mode === "merge"
        ? item.left_name + " now stays on " + item.right_name + "."
        : item.left_name + " stays separate from " + item.right_name + ".");
    } catch (ex) {
      setErr(ex.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card stack">
      <h2 style={{ margin: 0 }}>Name review</h2>
      <p className="muted">
        Imports that look like the same customer or product, but are not an exact match, wait here.
        Merge moves the new spelling onto the existing name. Keep separate remembers the pair so it is not asked again.
      </p>
      {msg ? <p className="ok">{msg}</p> : null}
      {err ? <p className="err">{err}</p> : null}
      {items.length ? (
        <table className="dense list-table">
          <thead>
            <tr>
              <th>New name</th>
              <th>Existing name</th>
              <th>Kind</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.kind + item.left_name + item.right_entity_id}>
                <td>{item.left_name}</td>
                <td>{item.right_name}</td>
                <td>{item.kind === "product" ? "Product" : "Customer"}</td>
                <td>
                  <button type="button" disabled={busy} onClick={() => act(item, "merge")}>Merge</button>
                  {" "}
                  <button type="button" className="secondary" disabled={busy} onClick={() => act(item, "reject")}>
                    Keep separate
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : <p className="muted">No names waiting for review.</p>}
    </div>
  );
}
