import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import ReportProgress, { progressStats } from "./ReportProgress";
import { can } from "./theme";

const GROUPS = [
  {
    id: "core",
    title: "Sales, collections, and follow-up",
    reports: [
      ["Sales rep performance", "core", "reports.view.performance"],
      ["Account performance", "core", "reports.view.performance"],
      ["Group performance", "core", "reports.view.performance"],
      ["Sales follow-up", "core", "reports.view.followup"],
      ["Collection follow-up", "core", "reports.view.followup"],
      ["phase2_collection", "", "reports.view.followup"],
    ],
  },
  {
    id: "fiscal",
    title: "Month-by-month by year",
    reports: [
      ["Fiscal monthly sales and collection", "fiscal", "reports.view.monthly"],
      ["Fiscal monthly account performance", "fiscal", "reports.view.monthly"],
      ["Fiscal monthly group performance", "fiscal", "reports.view.monthly"],
    ],
  },
  {
    id: "items",
    title: "Items and stock",
    reports: [
      ["Item-wise sales", "items", "reports.view.items"],
      ["Item cost exceptions", "items", "reports.view.items"],
      ["Item monthly quantity", "items", "reports.view.items"],
      ["phase2_stock", "", "reports.view.items"],
    ],
  },
  {
    id: "profit",
    title: "Profit and expenses",
    reports: [
      ["Item-wise profit", "profit", "reports.view.profit"],
      ["Item monthly profit", "profit", "reports.view.profit"],
      ["Monthly profit", "profit", "reports.view.profit"],
      ["Expense by category", "profit", "reports.view.profit"],
      ["Unmapped payment accounts", "profit", "reports.view.profit"],
      ["Expense by account", "profit", "reports.view.profit"],
    ],
  },
  {
    id: "scorecard",
    title: "Scorecard and movement",
    reports: [
      ["phase2_scorecard", "", "reports.view.scorecard"],
      ["phase2_sales_change", "", "reports.view.scorecard"],
      ["phase2_customer_movement", "", "reports.view.scorecard"],
    ],
  },
  {
    id: "warnings",
    title: "Data issues",
    reports: [
      ["Source data warnings", "core", "reports.view.issues"],
      ["phase2_quality", "", "reports.view.quality"],
    ],
  },
  {
    id: "360",
    title: "360 View",
    reports: [
      ["360-customers", "", "customer.view"],
      ["360-groups", "", "customer.view"],
      ["360-reps", "", "customer.view"],
      ["360-business", "", "customer.view"],
      ["360-items", "", "stock.view"],
      ["360-category", "", "stock.view"],
      ["360-item_group", "", "stock.view"],
      ["360-brand", "", "stock.view"],
      ["360-supplier", "", "stock.view"],
      ["360-repurchase", "", "customer.view|stock.view"],
    ],
  },
];

const TITLES = {
  "360-customers": "Customers 360",
  "360-groups": "Customer groups 360",
  "360-reps": "Sales reps 360",
  "360-items": "Items 360",
  "360-category": "Category 360",
  "360-item_group": "Item group 360",
  "360-brand": "Brand 360",
  "360-supplier": "Supplier 360",
  "360-repurchase": "Repeat purchases",
  "360-business": "Business 360",
  "phase2_scorecard": "Scorecard",
  "phase2_sales_change": "Sales change",
  "phase2_customer_movement": "Customer movement",
  "phase2_collection": "Collection worklist",
  "phase2_stock": "Stock decisions",
  "phase2_quality": "Data quality",
};

function allowReport(user, perm) {
  if (!perm) return true;
  return String(perm).split("|").some((name) => can(user, name));
}

function visibleGroups(user) {
  return GROUPS.map((group) => ({
    ...group,
    reports: group.reports.filter((row) => allowReport(user, row[2])),
  })).filter((group) => group.reports.length);
}

function reportTitle(id) {
  return TITLES[id] || id;
}

const REPORT_IDS = new Set(GROUPS.flatMap((group) => group.reports.map(([id]) => id)));

function knownReports(ids) {
  return (ids || []).filter((id) => REPORT_IDS.has(id));
}

function failedReportIds(row) {
  return ((row && row.generate_progress && row.generate_progress.steps) || [])
    .filter((step) => step.state === "failed" && step.id && step.id !== "save-reports")
    .map((step) => step.id);
}

function formatElapsed(ms) {
  const seconds = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  if (minutes) return minutes + "m " + String(rest).padStart(2, "0") + "s";
  return rest + "s";
}

function runLabel(row) {
  const failed = progressStats(row.generate_progress).failed.length;
  if (row.status === "succeeded" && failed) return "Partial";
  return row.status || "";
}

const DEFAULT_GROUPS = new Set(["core", "fiscal", "scorecard", "warnings", "360"]);
const DEFAULT_EXTRA = new Set(["phase2_stock"]);

function defaultSelection(user) {
  const ids = [];
  visibleGroups(user).forEach((group) => {
    group.reports.forEach(([id]) => {
      if (DEFAULT_GROUPS.has(group.id) || DEFAULT_EXTRA.has(id)) ids.push(id);
    });
  });
  return ids;
}

function GroupCard({ group, selected, onToggle, onSetGroup }) {
  const ids = group.reports.map(([id]) => id);
  const onCount = ids.filter((id) => selected.includes(id)).length;
  return (
    <section className={"pick-group" + (onCount ? " on" : "")}>
      <div className="pick-group-head">
        <strong>{group.title}</strong>
        <span className="muted">{onCount} of {ids.length}</span>
        <button type="button" className="ghost" onClick={() => onSetGroup(true)}>All</button>
        <button type="button" className="ghost" onClick={() => onSetGroup(false)}>None</button>
      </div>
      <div className="pick-chips">
        {group.reports.map(([id]) => {
          const on = selected.includes(id);
          return (
            <button
              key={id}
              type="button"
              className={on ? "pick-chip on" : "pick-chip"}
              aria-pressed={on}
              onClick={() => onToggle(id)}
            >
              {reportTitle(id)}
            </button>
          );
        })}
      </div>
    </section>
  );
}

export default function CreatePage({ onQueued, busy, run, onGo, user }) {
  const [page, setPage] = useState(1);
  const [history, setHistory] = useState({ runs: [], total: 0, limit: 10 });
  const [wizard, setWizard] = useState(null);
  const [reportDate, setReportDate] = useState(new Date().toISOString().slice(0, 10));
  const [selected, setSelected] = useState(() => defaultSelection(user));
  const [err, setErr] = useState("");
  const [setupGate, setSetupGate] = useState(false);
  const [startedAt, setStartedAt] = useState(0);
  const [now, setNow] = useState(() => Date.now());
  const limit = 10;

  async function loadHistory(nextPage) {
    const res = await api.listRuns({ page: nextPage || page, limit });
    setHistory({
      runs: res.runs || [],
      total: res.total || 0,
      limit: res.limit || limit,
    });
  }

  useEffect(() => {
    loadHistory(page).catch(() => {});
  }, [page]);

  useEffect(() => {
    if (!busy) return undefined;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [busy]);

  useEffect(() => {
    if (run?.status === "succeeded" || run?.status === "failed" || run?.status === "cancelled") {
      loadHistory(page).catch(() => {});
      setWizard((prev) => {
        if (!prev || !run || prev.mode === "choose") return prev;
        const finished = run.status === "succeeded" || run.status === "failed" || run.status === "cancelled";
        return {
          ...prev,
          mode: finished ? "done" : prev.mode,
          title: finished ? "Reports · " + (reportDate || "") : prev.title,
          review: { ...(prev.review || {}), id: run.id, status: run.status, message: run.message, generate_progress: run.generate_progress, report_date: reportDate },
        };
      });
    }
  }, [run?.status, run?.id]);

  const pages = Math.max(1, Math.ceil((history.total || 0) / (history.limit || limit)));
  const latestId = page === 1 && history.runs[0] ? history.runs[0].id : "";

  function openNew() {
    setErr("");
    setReportDate(new Date().toISOString().slice(0, 10));
    setSelected(defaultSelection(user));
    setWizard({ title: "Create reports", mode: "choose", review: null });
  }

  function openRun(row) {
    setErr("");
    setReportDate(row.report_date || reportDate);
    setSelected(defaultSelection(user));
    const running = row.status === "running" || row.status === "queued";
    if (running) setStartedAt(Date.now());
    setWizard({
      title: (running ? "Creating reports" : "Reports") + (row.report_date ? " · " + row.report_date : ""),
      mode: running ? "running" : "done",
      review: row,
    });
  }

  function toggle(id) {
    setSelected((prev) => (prev.includes(id) ? prev.filter((item) => item !== id) : prev.concat(id)));
  }

  function setGroup(group, on) {
    const ids = group.reports.map(([id]) => id);
    setSelected((prev) => {
      const rest = prev.filter((id) => !ids.includes(id));
      return on ? rest.concat(ids) : rest;
    });
  }

  const offered = visibleGroups(user);
  const offeredIds = new Set(offered.flatMap((group) => group.reports.map(([id]) => id)));
  const reportTotal = offeredIds.size;

  async function submit(ids, sourceId, date) {
    setErr("");
    setSetupGate(false);
    const raw = ids ? ids.filter((id) => id && id !== "save-reports") : knownReports(selected);
    const chosen = raw.filter((id) => offeredIds.has(id) || !REPORT_IDS.has(id));
    const when = date || reportDate;
    if (!chosen.length) {
      setErr("Select at least one report.");
      return;
    }
    try {
      const settings = await api.settlement();
      if (!settings.setup_complete) {
        setSetupGate(true);
        return;
      }
      const packs = { core: false, fiscal: false, items: false, profit: false };
      GROUPS.forEach((group) => {
        group.reports.forEach(([id, pack]) => {
          if (pack && chosen.includes(id)) packs[pack] = true;
        });
      });
      setSelected(chosen);
      setReportDate(when);
      setStartedAt(Date.now());
      setWizard({ title: "Creating reports · " + when, mode: "running", review: null });
      const res = await api.createRun({
        packs,
        report_date: when,
        reports: chosen,
        from_run: sourceId || "",
      });
      if (onQueued) onQueued(res);
    } catch (e) {
      setErr(e.message);
      setWizard((prev) => (prev && prev.mode === "running" ? { ...prev, mode: "choose", title: "Create reports" } : prev));
    }
  }

  function rerunFailed(row) {
    const failed = failedReportIds(row);
    if (!failed.length) return;
    submit(failed, row.id, row.report_date || reportDate);
  }

  const screen = !wizard || wizard.mode === "choose" ? "choose" : (wizard.mode === "running" ? "running" : "done");
  const shownProgress = screen === "running"
    ? (run && run.generate_progress)
    : (wizard && wizard.review
      ? wizard.review.generate_progress
      : (screen === "done" ? (run && run.generate_progress) : null));
  const doneRow = (wizard && wizard.review) || (screen === "done" ? run : null);
  const elapsed = startedAt && screen === "running" ? formatElapsed(now - startedAt) : "";

  const rows = history.runs || [];
  const range = useMemo(() => {
    if (!history.total) return "No report runs yet";
    const start = (page - 1) * (history.limit || limit) + 1;
    const end = Math.min(history.total, start + rows.length - 1);
    return start + "–" + end + " of " + history.total;
  }, [history, page, rows.length]);

  return (
    <div className="card">
      <div className="row gap" style={{ justifyContent: "space-between", alignItems: "center" }}>
        <h2 style={{ margin: 0 }}>Create official reports</h2>
        <button type="button" disabled={busy} onClick={openNew}>Create reports</button>
      </div>
      <p className="muted">Each run keeps the sheets that succeeded. Open a run to see which reports failed and why. Rerun failed is available on the latest run.</p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Date</th>
              <th>Status</th>
              <th>Reports</th>
              <th>Failed</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {rows.length ? rows.map((row) => {
              const failed = progressStats(row.generate_progress).failed.length;
              const latest = row.id === latestId;
              const label = runLabel(row);
              return (
                <tr key={row.id} onClick={() => openRun(row)} style={{ cursor: "pointer" }}>
                  <td>{row.report_date || ""}</td>
                  <td>
                    <span className={"pill" + (label === "failed" ? " err" : label === "succeeded" ? " ok" : " warn")}>
                      {label}
                    </span>
                    {latest ? <span className="muted"> · Latest</span> : null}
                  </td>
                  <td>{row.report_count || 0}</td>
                  <td>{failed || ""}</td>
                  <td>
                    {latest && failedReportIds(row).length && row.status !== "running" && row.status !== "queued" ? (
                      <button
                        type="button"
                        className="secondary"
                        disabled={busy}
                        onClick={(e) => {
                          e.stopPropagation();
                          rerunFailed(row);
                        }}
                      >
                        Rerun failed
                      </button>
                    ) : null}
                  </td>
                </tr>
              );
            }) : (
              <tr><td colSpan={5} className="muted">No report runs yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>
      <div className="row gap" style={{ marginTop: 12, justifyContent: "space-between" }}>
        <span className="muted">{range}</span>
        <span className="row gap">
          <button type="button" className="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button>
          <button type="button" className="secondary" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</button>
        </span>
      </div>

      {wizard ? (
        <div className="modal-backdrop wizard-backdrop" onClick={() => { if (screen !== "running") setWizard(null); }}>
          <div className="modal wizard-modal" onClick={(e) => e.stopPropagation()}>
            <div className="wizard-head">
              <h3>{wizard.title}</h3>
              <button type="button" className="ghost wizard-close" disabled={screen === "running"} onClick={() => setWizard(null)}>Close</button>
            </div>
            <div className="wizard-body">
              {screen === "choose" ? (
                <>
                  <label>Report date</label>
                  <input type="date" value={reportDate} onChange={(e) => setReportDate(e.target.value)} />
                  <div className="pick-bar">
                    <span>{selected.filter((id) => offeredIds.has(id)).length} of {reportTotal} reports</span>
                    <span>
                      <button type="button" className="ghost" onClick={() => setSelected([...offeredIds])}>All</button>
                      <button type="button" className="ghost" onClick={() => setSelected([])}>None</button>
                    </span>
                  </div>
                  {offered.map((group) => (
                    <GroupCard
                      key={group.id}
                      group={group}
                      selected={selected}
                      onToggle={toggle}
                      onSetGroup={(on) => setGroup(group, on)}
                    />
                  ))}
                </>
              ) : null}
              {screen === "done" ? (
                <p className={progressStats(shownProgress).failed.length ? "err create-summary" : "ok create-summary"}>
                  {progressStats(shownProgress).succeeded.length} succeeded
                  {progressStats(shownProgress).failed.length ? " · " + progressStats(shownProgress).failed.length + " failed" : ""}
                  {doneRow && doneRow.message ? ". " + doneRow.message : ""}
                </p>
              ) : null}
              {screen !== "choose" && shownProgress ? (
                <ReportProgress
                  progress={shownProgress}
                  active={screen === "running"}
                  variant={screen === "running" ? "live" : "result"}
                  note={elapsed}
                />
              ) : null}
              {screen === "running" && !shownProgress ? <p className="muted">Creating reports…</p> : null}
              {err ? <p className="err">{err}</p> : null}
            </div>
            <div className="wizard-foot">
              <button type="button" className="secondary" disabled={screen === "running"} onClick={() => setWizard(null)}>Close</button>
              <div className="wizard-foot-right">
                {screen === "done" && doneRow && doneRow.id === latestId && failedReportIds(doneRow).length ? (
                  <button type="button" className="secondary" disabled={busy} onClick={() => rerunFailed(doneRow)}>Rerun failed</button>
                ) : null}
                {screen === "choose" ? (
                  <button type="button" disabled={busy || !selected.filter((id) => offeredIds.has(id)).length} onClick={() => submit()}>
                    Create {selected.filter((id) => offeredIds.has(id)).length} reports
                  </button>
                ) : null}
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {setupGate ? (
        <div className="modal-backdrop" onClick={() => setSetupGate(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 480 }}>
            <h3>Set up settlement first</h3>
            <p>Before creating reports, save a settlement mode and aging bands in Settings.</p>
            <div className="row gap" style={{ marginTop: 16, justifyContent: "flex-end" }}>
              <button type="button" className="secondary" onClick={() => setSetupGate(false)}>Cancel</button>
              <button type="button" onClick={() => { setSetupGate(false); if (onGo) onGo("settings", "settlement"); }}>Open Settlement settings</button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
