import { useEffect, useState } from "react";
import { api } from "./api";
import { can } from "./theme";

export default function SetupWizard({ user, onGo }) {
  const [visible, setVisible] = useState(false);
  const [check, setCheck] = useState(null);
  const [policy, setPolicy] = useState(null);
  const [saved, setSaved] = useState("");

  useEffect(() => {
    if (!can(user, "settings.advanced") || sessionStorage.getItem("vay-wizard-dismissed")) return;
    let cancelled = false;
    api.settlement()
      .then((settings) => {
        if (!cancelled && !settings.setup_complete) setVisible(true);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [user]);

  useEffect(() => {
    if (!visible) return undefined;
    let cancelled = false;
    api.onboarding().then((payload) => { if (!cancelled) setCheck(payload); }).catch(() => {});
    api.orgPolicy().then((payload) => { if (!cancelled) setPolicy(payload); }).catch(() => {});
    return () => { cancelled = true; };
  }, [visible]);

  function dismiss() {
    sessionStorage.setItem("vay-wizard-dismissed", "1");
    setVisible(false);
  }

  if (!visible) return null;
  return (
    <div className="card">
      <div className="row gap" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <h3>Finish first-time setup</h3>
          <p className="muted">Confirm company policy, import your workbook, then create your first reports.</p>
          {policy ? (
            <div className="form-grid">
              <label>Company name
                <input value={policy.company_name || ""} onChange={(e) => setPolicy({ ...policy, company_name: e.target.value })} />
              </label>
              <label>Timezone
                <input value={policy.timezone || ""} onChange={(e) => setPolicy({ ...policy, timezone: e.target.value })} />
              </label>
              <label>Currency
                <input value={policy.currency_code || ""} onChange={(e) => setPolicy({ ...policy, currency_code: e.target.value })} />
              </label>
              <button type="button" className="secondary" onClick={() => {
                api.setOrgPolicy(policy).then(() => setSaved("Policy saved.")).catch((e) => setSaved(e.message || "Could not save policy"));
              }}>Save policy</button>
            </div>
          ) : null}
          {saved ? <p className="muted">{saved}</p> : null}
          {(check?.decisions || []).map((row) => <p key={row.type} className="muted">{row.message}</p>)}
          {(check?.templates || []).length ? (
            <p className="muted">Templates: {(check.templates || []).map((row) => row.type + " (" + row.columns.join(", ") + ")").join("; ")}</p>
          ) : null}
          {check ? (
            <div>
              {(check.missing_files || []).length ? (
                <p className="muted">Still needed: {(check.missing_files || []).map((row) => row.label).join(", ")}.</p>
              ) : null}
              {(check.sources || []).filter((row) => row.present && !row.date_ok).map((row) => (
                <p key={row.type} className="warn">{row.label}: {row.date_note}</p>
              ))}
              {(check.exceptions || []).map((row) => (
                <p key={row.id} className="warn">{row.message}</p>
              ))}
            </div>
          ) : null}
          <div className="row gap">
            <button type="button" onClick={() => onGo("settings", "settlement")}>1. Settlement</button>
            <button type="button" className="secondary" onClick={() => onGo("data", "import")}>2. Import</button>
            <button type="button" className="secondary" onClick={() => onGo("reports", "create")}>3. Create</button>
          </div>
        </div>
        <button type="button" className="ghost" onClick={dismiss}>Dismiss</button>
      </div>
    </div>
  );
}
