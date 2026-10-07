import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "./api";
import { money } from "./format";

export default function ReminderDraft({ customerName, onClose, onDownload }) {
  const [draft, setDraft] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    let cancelled = false;
    api.collectionReminder(customerName)
      .then((payload) => { if (!cancelled) setDraft(payload); })
      .catch((e) => { if (!cancelled) setErr(e.message || "Could not load the reminder"); });
    return () => { cancelled = true; };
  }, [customerName]);

  return createPortal(
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <div className="card-head">
          <h3>Reminder draft</h3>
          <button type="button" className="ghost" onClick={onClose}>Close</button>
        </div>
        <p className="muted">Review this reminder before sharing it. Vay does not send it.</p>
        {err ? <p className="err">{err}</p> : null}
        {!draft && !err ? <p className="muted">Loading…</p> : null}
        {draft ? (
          <div>
            <p>{draft.company_name || "Account"} · {draft.customer_name}</p>
            <p className="muted">
              {draft.currency_code || ""}{draft.as_of ? " · " + draft.as_of : ""}
            </p>
            {(draft.promises || []).length ? (draft.promises || []).map((row) => (
              <p key={row.id}>
                Promised {money(row.amount)}
                {" · confirmed "}{money(row.allocated)}
                {" · remaining "}{money(row.remaining)}
                {row.promised_on ? " · " + row.promised_on : ""}
              </p>
            )) : <p className="muted">No open payment promise is recorded.</p>}
            {draft.next_step ? <p>Next step: {draft.next_step}</p> : null}
            {draft.next_follow_up ? <p className="muted">Follow up {draft.next_follow_up}</p> : null}
          </div>
        ) : null}
        <div className="modal-actions">
          <button type="button" className="secondary" onClick={onClose}>Back</button>
          <button type="button" onClick={onDownload}>Download PDF</button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
