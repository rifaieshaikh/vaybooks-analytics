import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "./api";
import { money } from "./format";

const ENTRY_TYPES = [
  ["contact", "Contact"],
  ["promise", "Promise"],
  ["dispute", "Dispute"],
];

const CHANNELS = [
  ["phone", "Phone"],
  ["visit", "Visit"],
  ["whatsapp", "WhatsApp"],
  ["email", "Email"],
  ["other", "Other"],
];

const STATUS_LABEL = {
  open: "Open",
  partial: "Partial",
  kept: "Kept",
  missed: "Missed",
  pending_refresh: "Pending refresh",
  resolved: "Resolved",
};

function statusLabel(value) {
  return STATUS_LABEL[value] || value || "";
}

function channelLabel(value) {
  const found = CHANNELS.find(([id]) => id === value);
  return found ? found[1] : (value || "");
}

function todayInput() {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return now.getFullYear() + "-" + month + "-" + day;
}

function tone(status) {
  if (status === "missed") return "err";
  if (status === "kept" || status === "resolved") return "credit";
  return "warn";
}

function recordedAt(value) {
  const text = String(value || "");
  if (!text) return "—";
  return text.replace("T", " ").replace(/\.\d+/, "").replace(/Z$/, "").slice(0, 16);
}

function invoiceChoices(lines) {
  const out = [];
  const seen = new Set();
  (lines || []).forEach((line) => {
    const invoice = String(line.invoice || "").trim();
    const due = line.due != null ? line.due : line.remaining;
    const key = invoice.toLowerCase();
    if (!invoice || seen.has(key) || !(Number(due) > 0)) return;
    seen.add(key);
    out.push({ invoice, due });
  });
  return out;
}

function invoiceRefs(selected, other) {
  const extra = String(other || "").split(",").map((item) => item.trim()).filter(Boolean);
  const out = [];
  const seen = new Set();
  [...(selected || []), ...extra].forEach((item) => {
    const key = item.toLowerCase();
    if (!item || seen.has(key)) return;
    seen.add(key);
    out.push(item);
  });
  return out;
}

function blankContact() {
  return { contacted_on: todayInput(), channel: "phone", note: "", next_step: "", next_follow_up: "" };
}

function splitInvoiceRefs(refs, lines) {
  const known = new Set((lines || []).map((line) => line.invoice.toLowerCase()));
  const selected = [];
  const other = [];
  (refs || []).forEach((ref) => {
    const text = String(ref || "").trim();
    if (!text) return;
    if (known.has(text.toLowerCase())) selected.push(text);
    else other.push(text);
  });
  return { selected, other: other.join(", ") };
}

function entryTitle(mode, kind) {
  const verb = mode === "edit" ? "Edit" : "Add";
  const noun = kind === "promise" ? "promise" : kind === "dispute" ? "dispute" : "contact";
  return verb + " " + noun;
}

function InvoiceField({ lines, selected, other, onToggle, onOther }) {
  if (!lines.length) {
    return (
      <label className="span-2">
        Invoices
        <input value={other} placeholder="Optional, comma-separated" onChange={(e) => onOther(e.target.value)} />
      </label>
    );
  }
  return (
    <div className="span-2">
      <span className="follow-field-label">Invoices</span>
      <div className="follow-invoice-list">
        {lines.map((line) => (
          <label className="follow-invoice" key={line.invoice}>
            <input type="checkbox" checked={selected.includes(line.invoice)} onChange={() => onToggle(line.invoice)} />
            <span>{line.invoice}</span>
            <span className="muted">{money(line.due)}</span>
          </label>
        ))}
      </div>
      <label>
        Other invoice
        <input value={other} placeholder="Optional" onChange={(e) => onOther(e.target.value)} />
      </label>
    </div>
  );
}

export default function CollectionFollowUp({ customerName, customerUk, invoices, actionId, canManage, onReminder, user }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [composer, setComposer] = useState("");
  const [entryType, setEntryType] = useState("contact");
  const [byName, setByName] = useState(user?.username || "");
  const [owners, setOwners] = useState([]);
  const [editing, setEditing] = useState(null);
  const [contact, setContact] = useState(blankContact);
  const [promise, setPromise] = useState({ amount: "", promised_on: "" });
  const [promiseInvoices, setPromiseInvoices] = useState([]);
  const [promiseOther, setPromiseOther] = useState("");
  const [dispute, setDispute] = useState({ note: "", promise_id: "" });
  const [disputeInvoices, setDisputeInvoices] = useState([]);
  const [disputeOther, setDisputeOther] = useState("");
  const [openInvoices, setOpenInvoices] = useState([]);

  function load() {
    if (!customerName) return;
    api.collection({ customer: customerName })
      .then((payload) => { setData(payload); setErr(""); })
      .catch((e) => setErr(e.message || "Could not load follow-up"));
  }

  useEffect(() => { load(); }, [customerName]);

  async function run(work) {
    setBusy(true);
    setErr("");
    try {
      await work();
      load();
      return true;
    } catch (e) {
      setErr(e.message || "Could not save");
      return false;
    } finally {
      setBusy(false);
    }
  }

  function clearEntryFields() {
    setContact(blankContact());
    setPromise({ amount: "", promised_on: "" });
    setPromiseInvoices([]);
    setPromiseOther("");
    setDispute({ note: "", promise_id: "" });
    setDisputeInvoices([]);
    setDisputeOther("");
  }

  function assignInvoiceRefs(kind, refs, lines) {
    const split = splitInvoiceRefs(refs, lines);
    if (kind === "promise") {
      setPromiseInvoices(split.selected);
      setPromiseOther(split.other);
    } else if (kind === "dispute") {
      setDisputeInvoices(split.selected);
      setDisputeOther(split.other);
    }
  }

  function loadOpenInvoices(kind, refs) {
    const seeded = invoiceChoices(invoices);
    setOpenInvoices(seeded);
    if (refs) assignInvoiceRefs(kind, refs, seeded);
    api.customer(customerUk || customerName, { section: "due" }).then((detail) => {
      if (detail && Object.prototype.hasOwnProperty.call(detail, "open_invoices")) {
        const lines = invoiceChoices(detail.open_invoices);
        setOpenInvoices(lines);
        if (refs) assignInvoiceRefs(kind, refs, lines);
        return null;
      }
      return api.customer(customerUk || customerName);
    }).then((detail) => {
      if (!detail || !detail.open_invoices) return;
      const lines = invoiceChoices(detail.open_invoices);
      setOpenInvoices(lines);
      if (refs) assignInvoiceRefs(kind, refs, lines);
    }).catch(() => {});
  }

  function openComposer(mode, item) {
    const row = item?.row;
    const kind = row ? item.kind : "contact";
    setEditing(row ? row.id : null);
    setEntryType(kind);
    setByName((row && (row.staff || row.created_by)) || user?.username || "");
    clearEntryFields();
    if (kind === "contact" && row) {
      setContact({
        contacted_on: row.contacted_on || todayInput(),
        channel: row.channel || "phone",
        note: row.note || "",
        next_step: row.next_step || "",
        next_follow_up: row.next_follow_up || "",
      });
    } else if (kind === "promise" && row) {
      setPromise({ amount: row.amount ?? "", promised_on: row.promised_on || "" });
    } else if (kind === "dispute" && row) {
      setDispute({ note: row.note || "", promise_id: row.promise_id || "" });
    }
    setComposer(mode);
    api.actions().then((payload) => setOwners(payload.owners || [])).catch(() => setOwners([]));
    loadOpenInvoices(kind, row ? (row.invoice_refs || []) : null);
  }

  function chooseType(kind) {
    if (kind === entryType) return;
    setEntryType(kind);
    clearEntryFields();
  }

  async function saveEntry(event) {
    event.preventDefault();
    const refs = invoiceRefs(
      entryType === "promise" ? promiseInvoices : disputeInvoices,
      entryType === "promise" ? promiseOther : disputeOther,
    );
    let ok = false;
    if (composer === "edit") {
      if (entryType === "contact") {
        ok = await run(() => api.updateCollectionContact(editing, { staff: byName, ...contact }));
      } else if (entryType === "promise") {
        ok = await run(() => api.updateCollectionPromise(editing, {
          staff: byName,
          amount: Number(promise.amount),
          promised_on: promise.promised_on,
          invoice_refs: refs,
        }));
      } else {
        ok = await run(() => api.updateCollectionDispute(editing, {
          staff: byName,
          note: dispute.note,
          promise_id: dispute.promise_id,
          invoice_refs: refs,
        }));
      }
    } else if (entryType === "contact") {
      ok = await run(() => api.createCollectionContact({
        customer_name: customerName,
        action_id: actionId || "",
        staff: byName,
        ...contact,
      }));
    } else if (entryType === "promise") {
      ok = await run(() => api.createCollectionPromise({
        customer_name: customerName,
        action_id: actionId || "",
        staff: byName,
        amount: Number(promise.amount),
        promised_on: promise.promised_on,
        invoice_refs: refs,
      }));
    } else {
      ok = await run(() => api.createCollectionDispute({
        customer_name: customerName,
        promise_id: dispute.promise_id,
        staff: byName,
        note: dispute.note,
        invoice_refs: refs,
      }));
    }
    if (ok) setComposer("");
  }

  useEffect(() => {
    if (!composer) return undefined;
    function onKey(event) {
      if (event.key === "Escape") setComposer("");
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [composer]);

  if (!customerName) return null;
  const contacts = data?.contacts || [];
  const promises = data?.promises || [];
  const disputes = data?.disputes || [];
  const rows = [
    ...contacts.map((row) => ({ kind: "contact", row })),
    ...promises.map((row) => ({ kind: "promise", row })),
    ...disputes.map((row) => ({ kind: "dispute", row })),
  ].sort((a, b) => (b.row.created_at || "").localeCompare(a.row.created_at || ""));

  return (
    <div className="stack">
      {err ? <p className="err">{err}</p> : null}
      <div className="follow-toolbar">
        {onReminder ? (
          <button type="button" className="ghost" onClick={onReminder}>Download reminder</button>
        ) : null}
        {canManage ? (
          <button type="button" onClick={() => openComposer("add")}>Add</button>
        ) : null}
      </div>
      <p className="muted">Recording a call does not mark an invoice paid.</p>
      {composer ? createPortal(
        <div className="modal-backdrop follow-composer" onClick={() => { if (!busy) setComposer(""); }}>
          <form
            className="modal assign-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="follow-composer-title"
            onClick={(event) => event.stopPropagation()}
            onSubmit={saveEntry}
          >
            <h3 id="follow-composer-title">{entryTitle(composer, entryType)}</h3>
            <p className="muted">{customerName}</p>
            {composer === "add" ? (
              <div className="follow-type" role="radiogroup" aria-label="Type">
                {ENTRY_TYPES.map(([id, label]) => (
                  <button
                    type="button"
                    key={id}
                    className={entryType === id ? "" : "secondary"}
                    aria-pressed={entryType === id}
                    onClick={() => chooseType(id)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            ) : null}
            <div className="assign-form">
              <label className="span-2">
                By
                <select value={byName} onChange={(e) => setByName(e.target.value)} required>
                  <option value="">Select</option>
                  {(owners.includes(byName) || !byName ? owners : [byName, ...owners]).map((name) => (
                    <option key={name} value={name}>{name}</option>
                  ))}
                </select>
              </label>
              {entryType === "contact" ? (
                <>
                  <label>
                    Date
                    <input type="date" value={contact.contacted_on} onChange={(e) => setContact({ ...contact, contacted_on: e.target.value })} required />
                  </label>
                  <label>
                    Channel
                    <select value={contact.channel} onChange={(e) => setContact({ ...contact, channel: e.target.value })}>
                      {CHANNELS.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
                    </select>
                  </label>
                  <label className="span-2">
                    Note
                    <textarea rows={3} value={contact.note} onChange={(e) => setContact({ ...contact, note: e.target.value })} />
                  </label>
                  <label>
                    Next step
                    <input value={contact.next_step} onChange={(e) => setContact({ ...contact, next_step: e.target.value })} />
                  </label>
                  <label>
                    Next follow-up
                    <input type="date" value={contact.next_follow_up} onChange={(e) => setContact({ ...contact, next_follow_up: e.target.value })} />
                  </label>
                  <p className="muted span-2">Recording a call does not mark an invoice paid.</p>
                </>
              ) : null}
              {entryType === "promise" ? (
                <>
                  <label>
                    Amount
                    <input type="number" min="0.01" step="0.01" value={promise.amount} onChange={(e) => setPromise({ ...promise, amount: e.target.value })} required />
                  </label>
                  <label>
                    Promised date
                    <input type="date" value={promise.promised_on} onChange={(e) => setPromise({ ...promise, promised_on: e.target.value })} required />
                  </label>
                  <InvoiceField
                    lines={openInvoices}
                    selected={promiseInvoices}
                    other={promiseOther}
                    onToggle={(invoice) => setPromiseInvoices((current) => (
                      current.includes(invoice) ? current.filter((item) => item !== invoice) : [...current, invoice]
                    ))}
                    onOther={setPromiseOther}
                  />
                </>
              ) : null}
              {entryType === "dispute" ? (
                <>
                  <label className="span-2">
                    Note
                    <textarea rows={3} value={dispute.note} onChange={(e) => setDispute({ ...dispute, note: e.target.value })} required />
                  </label>
                  <label className="span-2">
                    Promise
                    <select value={dispute.promise_id} onChange={(e) => setDispute({ ...dispute, promise_id: e.target.value })}>
                      <option value="">None</option>
                      {promises.map((row) => (
                        <option key={row.id} value={row.id}>{money(row.amount)} · {row.promised_on}</option>
                      ))}
                    </select>
                  </label>
                  <InvoiceField
                    lines={openInvoices}
                    selected={disputeInvoices}
                    other={disputeOther}
                    onToggle={(invoice) => setDisputeInvoices((current) => (
                      current.includes(invoice) ? current.filter((item) => item !== invoice) : [...current, invoice]
                    ))}
                    onOther={setDisputeOther}
                  />
                </>
              ) : null}
            </div>
            {err ? <p className="err">{err}</p> : null}
            <div className="modal-actions">
              <button type="button" className="ghost" onClick={() => setComposer("")} disabled={busy}>Cancel</button>
              <button type="submit" disabled={busy}>Save</button>
            </div>
          </form>
        </div>,
        document.body,
      ) : null}
      {!data ? <p className="muted">Loading follow-up…</p> : (
        <div className="card table-card list-panel">
          <div className="table-wrap">
            <table className="dense list-table compact">
              <thead>
                <tr>
                  <th>Recorded</th>
                  <th>Type</th>
                  <th>Detail</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {rows.length ? rows.map((item) => (
                  <tr key={item.kind + item.row.id}>
                    <td>{recordedAt(item.row.created_at)}</td>
                    <td>{item.kind === "contact" ? "Contact" : item.kind === "promise" ? "Promise" : "Dispute"}</td>
                    <td>
                      {item.kind === "contact" ? (
                        <>
                          <div>{channelLabel(item.row.channel)}{item.row.contacted_on ? " · " + item.row.contacted_on : ""} · By {item.row.staff || item.row.created_by || "—"}</div>
                          {item.row.note ? <div>{item.row.note}</div> : null}
                          {item.row.next_step ? <div className="muted">Next: {item.row.next_step}</div> : null}
                          {canManage ? <button type="button" className="ghost" onClick={() => openComposer("edit", item)}>Edit</button> : null}
                        </>
                      ) : null}
                      {item.kind === "promise" ? (
                        <>
                          <div>{money(item.row.amount)} promised {item.row.promised_on} · By {item.row.staff || item.row.created_by || "—"}{item.row.invoice_refs?.length ? " · " + item.row.invoice_refs.join(", ") : ""}</div>
                          <div className="muted">
                            {money(item.row.remaining)} remaining
                            {item.row.receipt_coverage_through ? " · Receipts through " + item.row.receipt_coverage_through : ""}
                          </div>
                          {item.row.message ? <div className="muted">{item.row.message}</div> : null}
                          {(item.row.allocations || []).filter((alloc) => !alloc.voided_at || alloc.void_reason).map((alloc) => (
                            <div className="muted" key={alloc.id}>
                              {alloc.basis_label}
                              {alloc.amount ? " · " + money(alloc.amount) : ""}
                              {alloc.confirmed_by ? " · " + alloc.confirmed_by : ""}
                              {canManage && alloc.basis === "confirmed_inferred" && !alloc.voided_at ? (
                                <button type="button" className="ghost" disabled={busy} onClick={() => run(() => api.clearCollectionAllocation(alloc.id))}>Clear</button>
                              ) : null}
                            </div>
                          ))}
                          {canManage ? <button type="button" className="ghost" onClick={() => openComposer("edit", item)}>Edit</button> : null}
                          {(item.row.suggestions || []).map((suggestion) => (
                            <div key={suggestion.source_uk}>
                              {suggestion.label} {money(suggestion.unused)}
                              {suggestion.date ? " on " + suggestion.date : ""}
                              {canManage ? (
                                <button
                                  type="button"
                                  className="secondary"
                                  disabled={busy}
                                  onClick={() => run(() => api.confirmCollectionAllocation({
                                    promise_id: item.row.id,
                                    source_uk: suggestion.source_uk,
                                    source_type: suggestion.source_type,
                                  }))}
                                >
                                  Confirm
                                </button>
                              ) : null}
                            </div>
                          ))}
                        </>
                      ) : null}
                      {item.kind === "dispute" ? (
                        <div>
                          {item.row.note}{item.row.opened_on ? " · Opened " + item.row.opened_on : ""} · By {item.row.staff || item.row.created_by || "—"}
                          {canManage ? <button type="button" className="ghost" onClick={() => openComposer("edit", item)}>Edit</button> : null}
                        </div>
                      ) : null}
                    </td>
                    <td>
                      {item.kind === "contact" ? (
                        item.row.next_follow_up ? "Follow up " + item.row.next_follow_up : "—"
                      ) : null}
                      {item.kind === "promise" ? (
                        <span className={"pill " + tone(item.row.payment_status)}>{statusLabel(item.row.payment_status)}</span>
                      ) : null}
                      {item.kind === "dispute" ? (
                        <>
                          <span className={"pill " + tone(item.row.status)}>{statusLabel(item.row.status)}</span>
                          {canManage && item.row.status === "open" ? (
                            <div>
                              <button type="button" className="ghost" disabled={busy} onClick={() => run(() => api.updateCollectionDispute(item.row.id, { status: "resolved" }))}>
                                Mark resolved
                              </button>
                            </div>
                          ) : null}
                        </>
                      ) : null}
                    </td>
                  </tr>
                )) : (
                  <tr><td className="muted" colSpan={4}>No follow-up yet.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
