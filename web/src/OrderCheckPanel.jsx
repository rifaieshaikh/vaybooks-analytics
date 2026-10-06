import { useEffect, useMemo, useRef, useState } from "react";
import SectionTabs from "./SectionTabs";
import { api } from "./api";
import { money } from "./format";
import { DueDaysEditor } from "./OrderingPanel";

const BUILTIN_DEFAULTS = {
  followup_age_days: 15,
  urgent_age_days: 30,
  overdue_grace_days: 0,
  credit_limit: 0,
  max_order_value: 0,
  max_order_value_vs_avg: 1.5,
  max_order_qty_vs_usual: 1.3,
  min_gap_factor: 0.7,
  flagged_ratio_push: 0.25,
  settlement_old_share_push: 0.45,
  premium_limit_factor: 1.5,
  reduce_vs_usual: 1.0,
  premium_demote: true,
};

const POLICY_SECTIONS = [
  {
    id: "credit",
    title: "Credit & due",
    fields: [
      { key: "followup_age_days", label: "Follow-up age (days)", hint: "Open AR this old → follow up", step: 1 },
      { key: "urgent_age_days", label: "Urgent age (days)", hint: "Open AR this old → strong push back", step: 1 },
      { key: "overdue_grace_days", label: "Overdue grace (days)", hint: "Extra days past due days before push back", step: 1 },
      { key: "credit_limit", label: "Credit limit", hint: "0 = no limit. Open + proposed vs this cap", step: 1 },
    ],
  },
  {
    id: "size",
    title: "Order size",
    fields: [
      { key: "max_order_value", label: "Max order value", hint: "0 = no absolute ceiling", step: 1 },
      { key: "max_order_value_vs_avg", label: "Max vs avg sale", hint: "e.g. 1.5 = 150% of average sale", step: 0.1 },
      { key: "max_order_qty_vs_usual", label: "Max vs usual qty", hint: "e.g. 1.3 = 130% of usual basket", step: 0.1 },
      { key: "reduce_vs_usual", label: "Reduce-to usual factor", hint: "Suggested qty when reducing volume", step: 0.1 },
    ],
  },
  {
    id: "behavior",
    title: "Frequency & behavior",
    fields: [
      { key: "min_gap_factor", label: "Min gap factor", hint: "Too soon if days since last < avg gap × factor", step: 0.1 },
      { key: "flagged_ratio_push", label: "Overdue-order ratio", hint: "Flagged sales value / sales → push back", step: 0.05 },
      { key: "settlement_old_share_push", label: "Old settlement share", hint: "Share in oldest band → follow up", step: 0.05 },
    ],
  },
  {
    id: "premium",
    title: "Premium",
    fields: [
      { key: "premium_limit_factor", label: "Premium limit factor", hint: "Premium multiplies value/qty limits", step: 0.1 },
    ],
  },
];

const POLICY_FIELDS = POLICY_SECTIONS.flatMap((s) => s.fields);

const ACTION_CLASS = {
  create_order: "ok",
  reduce_volume: "warn",
  follow_up: "warn",
  push_back: "bad",
  strong_push_back: "bad",
};

const SOURCE_LABEL = {
  customer: "customer",
  group: "group",
  rep: "sales rep",
  default: "default",
};

function fieldValue(raw, key) {
  if (raw === "" || raw === null || raw === undefined) {
    const d = BUILTIN_DEFAULTS[key];
    return d === undefined || d === null ? "0" : String(d);
  }
  return String(raw);
}

function parseField(field, raw) {
  const n = Number(raw === "" || raw == null ? BUILTIN_DEFAULTS[field.key] : raw);
  return Number.isFinite(n) ? n : Number(BUILTIN_DEFAULTS[field.key] ?? 0);
}

function InfoTip({ text }) {
  if (!text) return null;
  return (
    <span
      className="order-check-info"
      tabIndex={0}
      title={text}
      aria-label={text}
      onClick={(e) => e.stopPropagation()}
      onMouseDown={(e) => e.stopPropagation()}
      onKeyDown={(e) => e.stopPropagation()}
    >
      <span className="order-check-info-mark" aria-hidden>i</span>
      <span className="order-check-info-bubble" role="tooltip">{text}</span>
    </span>
  );
}

function GearIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 1v2.5M12 20.5V23M4.2 4.2l1.8 1.8M18 18l1.8 1.8M1 12h2.5M20.5 12H23M4.2 19.8l1.8-1.8M18 6l1.8-1.8" />
    </svg>
  );
}

function oldestOpenLabel(detail) {
  // Prefer ages computed with Due (oldest_due_*); same open_invoices list otherwise.
  if (detail.oldest_due_age != null) {
    const kind = detail.oldest_due_kind || "sale";
    return {
      age: Number(detail.oldest_due_age) || 0,
      kind,
      label: kind === "opening" ? "opening balance" : "open invoice",
    };
  }
  const lines = (detail.open_invoices || []).filter((l) => (Number(l.due) || 0) >= 0.005);
  const invoices = lines.filter((l) => (l.kind || "") !== "opening");
  const pool = invoices.length ? invoices : lines;
  if (!pool.length) return { age: 0, kind: "", label: "" };
  let best = pool[0];
  for (const line of pool) {
    if ((Number(line.age_days) || 0) > (Number(best.age_days) || 0)) best = line;
  }
  const kind = best.kind || "sale";
  return {
    age: Number(best.age_days) || 0,
    kind,
    label: kind === "opening" ? "opening balance" : "open invoice",
  };
}

function avgGapDays(detail) {
  if (detail.avg_gap_days != null && !(detail.buying?.periods)) return Number(detail.avg_gap_days) || 0;
  const periods = (detail.buying || {}).periods || {};
  for (const key of ["this_year", "all", "last_year"]) {
    const items = (periods[key] || {}).items || [];
    const gaps = items.map((i) => Number(i.avg_gap_days) || 0).filter((g) => g > 0);
    if (gaps.length) return Math.round(gaps.reduce((a, b) => a + b, 0) / gaps.length);
  }
  return 0;
}

function daysSinceLastSale(detail) {
  if (!detail.last_sale || !detail.as_of) return null;
  const last = new Date(detail.last_sale);
  const asOf = new Date(detail.as_of);
  if (Number.isNaN(last.getTime()) || Number.isNaN(asOf.getTime())) return null;
  return Math.max(0, Math.round((asOf - last) / 86400000));
}

function PolicyFieldGrid({ fields, values, onChange, disabled }) {
  return (
    <div className="order-check-grid">
      {fields.map((f) => (
        <label key={f.key} className="muted order-check-field">
          <span className="order-check-field-label">
            {f.label}
            <InfoTip text={f.hint} />
          </span>
          <input
            type="number"
            step={f.step}
            min={0}
            value={fieldValue(values[f.key], f.key)}
            disabled={disabled}
            onChange={(e) => onChange(f.key, e.target.value)}
          />
        </label>
      ))}
    </div>
  );
}

export function OrderCheckResult({ result }) {
  const [showSignals, setShowSignals] = useState(false);
  if (!result) return null;
  const cls = ACTION_CLASS[result.action] || "";
  const sig = result.signals || {};
  const groups = result.reason_groups || [];

  return (
    <div className={"order-check-result " + cls}>
      <div className="order-check-verdict-head">
        <strong className={"order-check-action order-check-" + (result.action || "")}>
          {result.action_label || result.action}
        </strong>
        <div className="order-check-verdict-pills">
          {result.premium ? <span className="pill premium">Premium</span> : null}
          {result.blacklisted ? <span className="pill blacklisted">Blacklisted</span> : null}
        </div>
      </div>

      {(result.suggested_value != null || result.suggested_qty != null) && result.action === "reduce_volume" ? (
        <p className="order-check-suggest">
          Suggested
          {result.suggested_value != null ? <> value <strong>{money(result.suggested_value)}</strong></> : null}
          {result.suggested_value != null && result.suggested_qty != null ? " · " : null}
          {result.suggested_qty != null ? <> qty <strong>{result.suggested_qty}</strong></> : null}
        </p>
      ) : null}

      {sig.due_days != null ? (
        <p className="muted order-check-due-line">
          Oldest open <strong>{sig.oldest_open_age != null ? sig.oldest_open_age + "d" : "—"}</strong>
          {" / due days "}
          <strong>{sig.due_days}d</strong>
          {" · from "}{SOURCE_LABEL[sig.due_days_source] || sig.due_days_source || "default"}
          {sig.due != null ? <> · due {money(sig.due)}</> : null}
        </p>
      ) : null}

      {groups.length ? (
        <div className="order-check-groups">
          {groups.map((g) => (
            <div key={g.id} className="order-check-group">
              <h5 className="quiet">{g.label}</h5>
              <ul className="order-check-reasons">
                {(g.reasons || []).map((r, i) => (
                  <li key={(r.code || "") + "-" + i}>{r.message}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      ) : (
        <ul className="order-check-reasons">
          {(result.reasons || []).map((r, i) => (
            <li key={(r.code || "") + "-" + i}>{r.message}</li>
          ))}
        </ul>
      )}

      <button type="button" className="linkish order-check-signals-toggle" onClick={() => setShowSignals((v) => !v)}>
        {showSignals ? "Hide signals" : "Signals used"}
      </button>
      {showSignals ? (
        <div className="order-check-signals-table">
          {[
            ["Due", money(sig.due)],
            ["Due days", (sig.due_days != null ? sig.due_days + "d" : "—") + " · " + (SOURCE_LABEL[sig.due_days_source] || "default")],
            ["Oldest open invoice", sig.oldest_open_age != null ? sig.oldest_open_age + "d" + (sig.oldest_open_kind === "opening" ? " (opening)" : "") : "—"],
            ["Avg sale", money(sig.avg_sale)],
            ["Usual qty", sig.usual_qty != null ? String(sig.usual_qty) : "—"],
            ["Days since last sale", sig.days_since_last_sale != null ? sig.days_since_last_sale + "d" : "—"],
            ["Usual gap", sig.avg_gap_days ? sig.avg_gap_days + "d" : "—"],
            ["Overdue-order ratio", sig.flagged_ratio != null ? (sig.flagged_ratio * 100).toFixed(0) + "%" : "—"],
            ["Old settlement share", sig.settlement_old_share != null ? (sig.settlement_old_share * 100).toFixed(0) + "%" : "—"],
            ["Proposed value", sig.proposed_value != null ? money(sig.proposed_value) : "—"],
            ["Proposed qty", sig.proposed_qty != null ? String(sig.proposed_qty) : "—"],
          ].map(([label, val]) => (
            <div key={label} className="order-check-signal-row">
              <span className="muted">{label}</span>
              <strong>{val}</strong>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function ToggleSwitch({ checked, disabled, onChange, label, hint, tone }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={!!checked}
      aria-label={label}
      disabled={disabled}
      className={
        "order-check-switch" +
        (checked ? " on" : "") +
        (tone === "danger" ? " danger" : "") +
        (tone === "ok" ? " ok" : "")
      }
      onClick={() => {
        if (!disabled && onChange) onChange(!checked);
      }}
    >
      <span className="order-check-switch-copy">
        <span className="order-check-field-label">
          <strong>{label}</strong>
          <InfoTip text={hint} />
        </span>
      </span>
      <span className="order-check-switch-track" aria-hidden>
        <span className="order-check-switch-thumb" />
      </span>
    </button>
  );
}

function OrderCheckSettingsModal({
  open,
  onClose,
  detail,
  entity = "customer",
  canEdit,
  snapshot,
  premium,
  blacklisted,
  flagBusy,
  onToggleFlag,
  draft,
  setDraft,
  policyBusy,
  policyMsg,
  onSaveOverride,
  onClearOverride,
  onSaved,
}) {
  const [tab, setTab] = useState("due");
  const wasOpen = useRef(false);
  const isCustomer = entity === "customer";
  const entityLabel = entity === "group" ? "group" : entity === "rep" ? "sales rep" : "customer";

  useEffect(() => {
    if (open && !wasOpen.current) {
      setTab("due");
    }
    wasOpen.current = open;
    if (!open) return undefined;
    function onKey(e) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const busy = flagBusy || policyBusy;

  return (
    <div
      className="modal-backdrop"
      onClick={() => { if (!busy) onClose(); }}
    >
      <div
        className="modal order-check-settings-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="order-check-settings-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="order-check-modal-head">
          <div>
            <h3 id="order-check-settings-title">Order check settings</h3>
            <p className="muted" style={{ margin: 0 }}>
              {detail.name || entityLabel} · due days {snapshot.dueDays}d from {snapshot.dueSource}
              {detail.order_check_own ? " · own thresholds" : ""}
            </p>
          </div>
          <button
            type="button"
            className="order-check-modal-close ghost"
            aria-label="Close"
            disabled={busy}
            onClick={onClose}
          >
            ✕
          </button>
        </div>

        <SectionTabs
          className="order-check-modal-tabs"
          label="Settings sections"
          value={tab}
          onChange={setTab}
          tabs={[
            { id: "due", label: isCustomer ? "Flags" : "Due days" },
            { id: "thresholds", label: "Thresholds", disabled: !canEdit },
          ]}
        />

        <div className="order-check-modal-body">
          {tab === "due" ? (
            <section className="order-check-section" style={{ marginTop: 0 }}>
              <h4 className="quiet">Ordering due days</h4>
              <p className="muted" style={{ marginTop: 0 }}>
                {isCustomer
                  ? "Override for this customer (falls back to group → rep → default). Used by Ordering and Check for order."
                  : `Override for this ${entityLabel} (falls back to default). Used by Ordering and Check for order.`}
              </p>
              <DueDaysEditor
                entity={entity}
                uk={detail.uk}
                detail={detail}
                canEdit={canEdit}
                onSaved={() => onSaved && onSaved()}
              />
              {isCustomer ? (
                <>
                  <h4 className="quiet" style={{ marginTop: 16 }}>Customer flags</h4>
                  {canEdit ? (
                    <div className="order-check-switch-list">
                      <ToggleSwitch
                        checked={premium}
                        disabled={flagBusy}
                        tone="ok"
                        label="Premium customer"
                        hint="Eases severity one step and raises size limits"
                        onChange={(next) => onToggleFlag({ premium: next })}
                      />
                      <ToggleSwitch
                        checked={blacklisted}
                        disabled={flagBusy}
                        tone="danger"
                        label="Blacklisted"
                        hint="Blocks order creation until cleared"
                        onChange={(next) => onToggleFlag({ blacklisted: next })}
                      />
                    </div>
                  ) : (
                    <div className="order-check-switch-list readonly">
                      <div className={"order-check-switch static" + (premium ? " on ok" : "")}>
                        <span className="order-check-switch-copy">
                          <strong>Premium customer</strong>
                          <span className="muted">{premium ? "On" : "Off"}</span>
                        </span>
                      </div>
                      <div className={"order-check-switch static" + (blacklisted ? " on danger" : "")}>
                        <span className="order-check-switch-copy">
                          <strong>Blacklisted</strong>
                          <span className="muted">{blacklisted ? "On" : "Off"}</span>
                        </span>
                      </div>
                    </div>
                  )}
                </>
              ) : null}
            </section>
          ) : null}

          {tab === "thresholds" && canEdit ? (
            <section className="order-check-section" style={{ marginTop: 0 }}>
              <p className="muted" style={{ marginTop: 0 }}>
                Values shown are effective for this {entityLabel}. Save to override default policy.
              </p>
              {POLICY_SECTIONS.map((sec) => (
                <div key={sec.id} className="order-check-subsection">
                  <h5 className="quiet">{sec.title}</h5>
                  <PolicyFieldGrid
                    fields={sec.fields}
                    values={draft}
                    disabled={policyBusy}
                    onChange={(key, val) => setDraft((prev) => ({ ...prev, [key]: val }))}
                  />
                  {sec.id === "premium" ? (
                    <div className="order-check-switch-list" style={{ marginTop: 10 }}>
                      <ToggleSwitch
                        checked={!!draft.premium_demote}
                        disabled={policyBusy}
                        tone="ok"
                        label="Ease severity for premium"
                        hint="When premium is on, demote push-back / follow-up by one step"
                        onChange={(next) => setDraft((prev) => ({ ...prev, premium_demote: next }))}
                      />
                    </div>
                  ) : null}
                </div>
              ))}
              {policyMsg ? <p className="ok">{policyMsg}</p> : null}
            </section>
          ) : null}
        </div>

        <div className="modal-actions order-check-modal-actions">
          {tab === "thresholds" && canEdit && detail.order_check_own ? (
            <button type="button" className="ghost" disabled={busy} onClick={onClearOverride}>
              Clear override
            </button>
          ) : (
            <span />
          )}
          <div className="order-check-modal-actions-right">
            <button type="button" className="ghost" disabled={busy} onClick={onClose}>
              Close
            </button>
            {tab === "thresholds" && canEdit ? (
              <button type="button" disabled={busy} onClick={onSaveOverride}>
                {policyBusy ? "Saving…" : "Save thresholds"}
              </button>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function OrderCheckPanel({ detail, entity = "customer", canEdit, onSaved }) {
  const [value, setValue] = useState("");
  const [qty, setQty] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [result, setResult] = useState(null);
  const [premium, setPremium] = useState(!!detail.premium);
  const [blacklisted, setBlacklisted] = useState(!!detail.blacklisted);
  const [flagBusy, setFlagBusy] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [draft, setDraft] = useState({});
  const [policyBusy, setPolicyBusy] = useState(false);
  const [policyMsg, setPolicyMsg] = useState("");
  const isCustomer = entity === "customer";
  const settingsLabel = entity === "group" ? "Group settings" : entity === "rep" ? "Sales rep settings" : "Customer settings";

  const snapshot = useMemo(() => {
    const ordering = detail.ordering?.overall ? detail.ordering : (detail.ordering_brief || detail.ordering || {});
    const overall = ordering.overall || {};
    const avg = overall.sales_count ? (Number(overall.sales_value) || 0) / (Number(overall.sales_count) || 1) : 0;
    const last = detail.buying?.last_order || [];
    const usualQty = last.reduce((s, x) => s + (Number(x.qty) || 0), 0);
    const oldestMeta = oldestOpenLabel(detail);
    const oldest = oldestMeta.age;
    const dueDays = detail.due_days != null ? detail.due_days : 30;
    const dueSource = SOURCE_LABEL[detail.due_days_source] || detail.due_days_source || "default";
    const since = daysSinceLastSale(detail);
    const gap = avgGapDays(detail);
    return { avg, usualQty, oldest, oldestKind: oldestMeta.kind, oldestLabel: oldestMeta.label, dueDays, dueSource, since, gap };
  }, [detail]);

  // Only re-seed form/draft when switching customer — not when flags/detail refresh mid-edit.
  useEffect(() => {
    setPremium(!!detail.premium);
    setBlacklisted(!!detail.blacklisted);
    setResult(null);
    setErr("");
    setPolicyMsg("");
    setValue(snapshot.avg ? String(Math.round(snapshot.avg * 100) / 100) : "");
    setQty(snapshot.usualQty ? String(Math.round(snapshot.usualQty * 100) / 100) : "");
    const own = detail.order_check_override || {};
    const effective = detail.order_check_policy || {};
    const next = {};
    POLICY_FIELDS.forEach((f) => {
      const src = detail.order_check_own && Object.prototype.hasOwnProperty.call(own, f.key)
        ? own[f.key]
        : effective[f.key];
      next[f.key] = fieldValue(src, f.key);
    });
    next.premium_demote = effective.premium_demote !== false;
    setDraft(next);
  }, [detail.uk]);

  useEffect(() => {
    setPremium(!!detail.premium);
    setBlacklisted(!!detail.blacklisted);
  }, [detail.premium, detail.blacklisted]);

  const settingsWasOpen = useRef(false);
  useEffect(() => {
    const justOpened = showSettings && !settingsWasOpen.current;
    settingsWasOpen.current = showSettings;
    if (!justOpened) return;
    const own = detail.order_check_override || {};
    const effective = detail.order_check_policy || {};
    const next = {};
    POLICY_FIELDS.forEach((f) => {
      const src = detail.order_check_own && Object.prototype.hasOwnProperty.call(own, f.key)
        ? own[f.key]
        : effective[f.key];
      next[f.key] = fieldValue(src, f.key);
    });
    next.premium_demote = effective.premium_demote !== false;
    setDraft(next);
    setPolicyMsg("");
  }, [showSettings, detail.uk, detail.order_check_own, detail.order_check_override, detail.order_check_policy]);

  async function runCheck() {
    setBusy(true);
    setErr("");
    try {
      const body = {};
      if (value !== "") body.order_value = Number(value);
      if (qty !== "") body.order_qty = Number(qty);
      const runner = entity === "group"
        ? api.runGroupOrderCheck
        : entity === "rep"
          ? api.runRepOrderCheck
          : api.runOrderCheck;
      const out = await runner(detail.uk, body);
      setResult(out);
    } catch (e) {
      setErr(e.message || "Check failed");
      setResult(null);
    } finally {
      setBusy(false);
    }
  }

  async function saveFlags(next) {
    if (!isCustomer) return;
    setFlagBusy(true);
    setErr("");
    try {
      await api.setCustomerOrderFlags(detail.uk, next);
      if (next.premium !== undefined) setPremium(!!next.premium);
      if (next.blacklisted !== undefined) setBlacklisted(!!next.blacklisted);
      if (onSaved) onSaved();
    } catch (e) {
      setErr(e.message || "Could not save flags");
    } finally {
      setFlagBusy(false);
    }
  }

  function savePolicyApi(body) {
    if (entity === "group") return api.setGroupOrderCheck(detail.uk, body);
    if (entity === "rep") return api.setRepOrderCheck(detail.uk, body);
    return api.setCustomerOrderCheck(detail.uk, body);
  }

  async function saveOverride() {
    setPolicyBusy(true);
    setErr("");
    setPolicyMsg("");
    try {
      const policy = {};
      POLICY_FIELDS.forEach((f) => {
        policy[f.key] = parseField(f, draft[f.key]);
      });
      policy.premium_demote = !!draft.premium_demote;
      await savePolicyApi({ policy });
      setPolicyMsg("Thresholds saved.");
      if (onSaved) onSaved();
    } catch (e) {
      setErr(e.message || "Could not save override");
    } finally {
      setPolicyBusy(false);
    }
  }

  async function clearOverride() {
    setPolicyBusy(true);
    setErr("");
    setPolicyMsg("");
    try {
      await savePolicyApi({ clear: true });
      setPolicyMsg("Override cleared.");
      if (onSaved) onSaved();
    } catch (e) {
      setErr(e.message || "Could not clear override");
    } finally {
      setPolicyBusy(false);
    }
  }

  function applySuggested() {
    if (!result) return;
    if (result.suggested_value != null) setValue(String(result.suggested_value));
    if (result.suggested_qty != null) setQty(String(result.suggested_qty));
  }

  const policySource = SOURCE_LABEL[detail.order_check_source] || detail.order_check_source || "default";
  const dueAmt = detail.credit ? Math.abs(detail.due || 0) : (detail.due || 0);
  const dueLabel = detail.credit ? "Advance" : "Amount due";

  return (
    <div className="card order-check-panel">
      <div className="card-head order-check-head">
        <div>
          <h3 style={{ margin: 0 }}>Order check</h3>
          <p className="muted" style={{ margin: "4px 0 0" }}>
            Due days, credit, size, frequency, and behavior — policy from <strong>{policySource}</strong>
            {detail.order_check_own ? " (own)" : ""}.
          </p>
        </div>
        <div className="order-check-head-right">
          <div className="order-check-verdict-pills">
            {isCustomer && premium ? <span className="pill premium">Premium</span> : null}
            {isCustomer && blacklisted ? <span className="pill blacklisted">Blacklisted</span> : null}
            {detail.ordered_overdue ? <span className="pill order-overdue">Ordered overdue</span> : null}
          </div>
          <button
            type="button"
            className={"order-check-gear" + (showSettings ? " on" : "")}
            aria-label={settingsLabel}
            title={settingsLabel}
            aria-haspopup="dialog"
            aria-expanded={showSettings}
            onClick={() => setShowSettings(true)}
          >
            <GearIcon />
          </button>
        </div>
      </div>

      <div className="buy-tiles order-check-tiles">
        <div className="card buy-tile">
          <span className="muted">{dueLabel}</span>
          <strong>{money(dueAmt)}</strong>
        </div>
        <div className="card buy-tile">
          <span className="muted">Oldest open invoice / terms</span>
          <strong>{snapshot.oldest}d / {snapshot.dueDays}d</strong>
          <span className="muted">
            {snapshot.oldestKind === "opening"
              ? "opening only · "
              : ""}
            {snapshot.oldest > snapshot.dueDays
              ? `${snapshot.oldest - snapshot.dueDays}d past terms · ${snapshot.dueSource}`
              : `within terms · ${snapshot.dueSource}`}
          </span>
        </div>
        <div className="card buy-tile">
          <span className="muted">Avg sale</span>
          <strong>{snapshot.avg ? money(snapshot.avg) : "—"}</strong>
          <span className="muted">Usual qty {snapshot.usualQty || "—"}</span>
        </div>
        <div className="card buy-tile">
          <span className="muted">Last sale</span>
          <strong>{snapshot.since != null ? snapshot.since + "d ago" : (detail.last_sale_label || "—")}</strong>
          <span className="muted">{snapshot.gap ? "Usual gap ~" + snapshot.gap + "d" : "No gap yet"}</span>
        </div>
      </div>

      <form
        className="order-check-run"
        onSubmit={(e) => {
          e.preventDefault();
          if (!busy) runCheck();
        }}
      >
        <label className="muted">
          Order value
          <input
            type="number"
            min={0}
            step="0.01"
            value={value}
            disabled={busy}
            onChange={(e) => setValue(e.target.value)}
          />
        </label>
        <label className="muted">
          Order qty
          <input
            type="number"
            min={0}
            step="0.01"
            value={qty}
            disabled={busy}
            onChange={(e) => setQty(e.target.value)}
          />
        </label>
        <button type="submit" className="btn order-check-cta" disabled={busy}>
          {busy ? "Checking…" : "Check for order"}
        </button>
        {result?.action === "reduce_volume" && (result.suggested_value != null || result.suggested_qty != null) ? (
          <button type="button" className="ghost" disabled={busy} onClick={applySuggested}>
            Apply suggested
          </button>
        ) : null}
      </form>

      <OrderCheckResult result={result} />
      {err ? <p className="err">{err}</p> : null}

      <OrderCheckSettingsModal
        open={showSettings}
        onClose={() => setShowSettings(false)}
        detail={detail}
        entity={entity}
        canEdit={canEdit}
        snapshot={snapshot}
        premium={premium}
        blacklisted={blacklisted}
        flagBusy={flagBusy}
        onToggleFlag={saveFlags}
        draft={draft}
        setDraft={setDraft}
        policyBusy={policyBusy}
        policyMsg={policyMsg}
        onSaveOverride={saveOverride}
        onClearOverride={clearOverride}
        onSaved={onSaved}
      />
    </div>
  );
}

export function OrderCheckDefaultsSection() {
  const [policy, setPolicy] = useState({});
  const [dueDays, setDueDays] = useState(30);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    Promise.all([api.orderCheckSettings(), api.dueDays()])
      .then(([d, due]) => {
        const p = d.policy || {};
        const next = {};
        POLICY_FIELDS.forEach((f) => {
          next[f.key] = fieldValue(p[f.key], f.key);
        });
        next.premium_demote = p.premium_demote !== false;
        setPolicy(next);
        setDueDays(Number(due.due_days) || 30);
      })
      .catch((e) => setErr(e.message))
      .finally(() => setLoaded(true));
  }, []);

  async function save() {
    setBusy(true);
    setErr("");
    setMsg("");
    try {
      const body = {};
      POLICY_FIELDS.forEach((f) => {
        body[f.key] = parseField(f, policy[f.key]);
      });
      body.premium_demote = !!policy.premium_demote;
      const [out] = await Promise.all([
        api.setOrderCheckSettings({ policy: body }),
        api.setDueDays({ due_days: Number(dueDays) || 30 }),
      ]);
      const p = out.policy || body;
      const next = {};
      POLICY_FIELDS.forEach((f) => {
        next[f.key] = fieldValue(p[f.key], f.key);
      });
      next.premium_demote = p.premium_demote !== false;
      setPolicy(next);
      setMsg("Saved.");
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <h2>Order check defaults</h2>
      <p className="muted">
        Default due days and thresholds for Check for order. Customers, groups, and sales reps can override.
        Due days also power the Ordering tab (ordered while overdue).
      </p>

      <section className="order-check-section" style={{ marginTop: 12 }}>
        <h4 className="quiet">Due days</h4>
        <label className="muted" style={{ display: "inline-flex", gap: 8, alignItems: "center" }}>
          Default due days
          <input
            type="number"
            min={0}
            style={{ width: 96 }}
            value={dueDays}
            disabled={!loaded || busy}
            onChange={(e) => setDueDays(e.target.value)}
          />
        </label>
        <p className="hint muted">Credit terms: a sale is flagged when open AR was older than this on the sale date.</p>
      </section>

      {POLICY_SECTIONS.map((sec) => (
        <section key={sec.id} className="order-check-section">
          <h4 className="quiet">{sec.title}</h4>
          <PolicyFieldGrid
            fields={sec.fields}
            values={policy}
            disabled={!loaded || busy}
            onChange={(key, val) => setPolicy((prev) => ({ ...prev, [key]: val }))}
          />
          {sec.id === "premium" ? (
            <label className="muted" style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 8 }}>
              <input
                type="checkbox"
                checked={!!policy.premium_demote}
                disabled={!loaded || busy}
                onChange={(e) => setPolicy((prev) => ({ ...prev, premium_demote: e.target.checked }))}
              />
              Premium eases severity one step
            </label>
          ) : null}
        </section>
      ))}

      <div style={{ marginTop: 12 }}>
        <button type="button" disabled={!loaded || busy} onClick={save}>Save</button>
      </div>
      {msg ? <p className="ok">{msg}</p> : null}
      {err ? <p className="err">{err}</p> : null}
    </div>
  );
}
