import { useEffect, useMemo, useState } from "react";
import BusinessPage from "./Business";
import CashPage from "./Cash";
import ChangePasswordPage from "./ChangePassword";
import CreatePage from "./Create";
import CustomersPage from "./Customers";
import AnalyticsPage from "./Analytics";
import DashboardPage from "./Dashboard";
import DataPage from "./DataPage";
import ExcelPage from "./Excel";
import ExportPage from "./Export";
import ExplorePage from "./Explore";
import GroupsPage from "./Groups";
import ItemDimsPage from "./ItemDims";
import ImportPage from "./Import";
import ItemsPage from "./Items";
import LoginPage from "./Login";
import ReportsPage from "./Reports";
import RepsPage from "./Reps";
import SalesPage from "./Sales";
import SettingsPage from "./Settings";
import SnapshotPicker from "./SnapshotPicker";
import SetupWizard from "./SetupWizard";
import StockPage from "./Stock";
import { api } from "./api";
import { can, findItem, firstRoute, visibleNav } from "./theme";
import { profitRan } from "./reportUtils";
import { hashReset, hashSet } from "./format";
import "./styles.css";

function DemoCard({ user, onOpened }) {
  const [status, setStatus] = useState(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!can(user, "reports.create")) return;
    api.demoStatus().then(setStatus).catch(() => setStatus(null));
  }, [user]);
  if (!can(user, "reports.create") || !status || status.blocked) return null;
  async function open() {
    setBusy(true);
    setErr("");
    try {
      const next = await api.openDemo();
      setStatus(next);
      if (onOpened) onOpened(next.report_id || next.report?.id);
    } catch (e) {
      setErr(e.message || "Could not open the demo");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="card">
      <h3>Sample company</h3>
      <p className="muted">Open Vay Demo Traders without preparing an import. Reset replaces only the sample rows.</p>
      <ul>
        {(status.scenarios || []).map((row) => <li key={row.id}>{row.name}: {row.summary}</li>)}
      </ul>
      {err ? <p className="err">{err}</p> : null}
      <button type="button" disabled={busy} onClick={open}>{status.present ? "Reset sample" : "Open sample"}</button>
    </div>
  );
}

function createProgressLabel(run) {
  const progress = run?.generate_progress;
  const steps = progress?.steps || [];
  const total = progress?.total || steps.length || 0;
  const done = progress?.done || 0;
  const fraction = Math.max(0, Math.min(0.99, Number(progress?.fraction) || 0));
  const pct = total ? Math.min(100, Math.round(((done + fraction) / total) * 100)) : 0;
  const current = steps.find((row) => row.id === progress?.current);
  if (current?.title) return current.title + (total ? " · " + pct + "%" : "");
  return total ? "Creating reports · " + pct + "%" : "Creating reports…";
}

function routeFromHash(h, u) {
  if ((h.startsWith("customer/") || h.startsWith("list/customers")) && can(u, "customer.view")) {
    return { tab: "customers", sub: "customers" };
  }
  if (h.startsWith("group/") && can(u, "customer.view")) return { tab: "customers", sub: "groups" };
  if (h.startsWith("rep/") && can(u, "customer.view")) return { tab: "customers", sub: "reps" };
  if (h.startsWith("invoice/") && can(u, "sales.view")) return { tab: "sales", sub: "sales" };
  if (h.startsWith("item/") && can(u, "stock.view")) return { tab: "customers", sub: "items" };
  if (h.startsWith("category/") && can(u, "stock.view")) return { tab: "customers", sub: "item-category" };
  if (h.startsWith("item-group/") && can(u, "stock.view")) return { tab: "customers", sub: "item-group" };
  if (h.startsWith("brand/") && can(u, "stock.view")) return { tab: "customers", sub: "brand" };
  if (h.startsWith("supplier/") && can(u, "stock.view")) return { tab: "customers", sub: "supplier" };
  if (h.startsWith("list/stock") && can(u, "stock.view")) return { tab: "stock", sub: "stock" };
  if (h.startsWith("list/arr") && can(u, "arr.view")) return { tab: "finance", sub: "arr" };
  return null;
}

export default function App() {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);
  const [tab, setTab] = useState("sales");
  const [sub, setSub] = useState("sales");
  const [openTab, setOpenTab] = useState("sales");
  const [run, setRun] = useState(null);
  const [runId, setRunId] = useState("");
  const [runs, setRuns] = useState([]);

  useEffect(() => {
    api.me().then((u) => {
      setUser(u);
      const h = (window.location.hash || "").replace(/^#/, "");
      const hashed = routeFromHash(h, u);
      const route = hashed || firstRoute(u);
      setTab(route.tab);
      setSub(route.sub);
      setOpenTab(route.tab);
    }).catch(() => setUser(null)).finally(() => setReady(true));
  }, []);

  useEffect(() => {
    function lost() {
      setUser(null);
    }
    window.addEventListener("vay-auth-lost", lost);
    return () => window.removeEventListener("vay-auth-lost", lost);
  }, []);

  useEffect(() => {
    if (!user || user.must_change_password) return undefined;
    function onHash() {
      const h = (window.location.hash || "").replace(/^#/, "");
      const hashed = routeFromHash(h, user);
      if (hashed) {
        setTab(hashed.tab);
        setSub(hashed.sub);
        setOpenTab(hashed.tab);
      }
    }
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, [user]);

  async function loadRuns(preferId) {
    const d = await api.listRuns();
    const rows = (d.runs || []).filter((r) => r.status === "succeeded" || r.status === "queued" || r.status === "running");
    setRuns(d.runs || []);
    const succeeded = (d.runs || []).filter((r) => r.status === "succeeded");
    const active = (d.runs || []).find((r) => r.status === "queued" || r.status === "running");
    const pickId = preferId || active?.id || succeeded[0]?.id || (d.runs || [])[0]?.id;
    if (!pickId) {
      setRun(null);
      return;
    }
    const pick = (d.runs || []).find((r) => r.id === pickId);
    setRun((prev) => {
      const active = prev && (prev.status === "queued" || prev.status === "running");
      if (!preferId && active && prev.id && String(prev.id) !== String(pickId)) return prev;
      if (prev && String(prev.id) === String(pickId) && prev.snapshot) return prev;
      return { ...(prev && String(prev.id) === String(pickId) ? prev : {}), ...(pick || { id: pickId }) };
    });
    if (pick && (pick.status === "queued" || pick.status === "running")) setRunId(pick.id);
    if (!pick || pick.status !== "succeeded") {
      const full = await api.getRun(pickId, { snapshot: false });
      setRun((prev) => {
        const active = prev && (prev.status === "queued" || prev.status === "running");
        if (!preferId && active && prev.id && String(prev.id) !== String(full.id)) return prev;
        return full;
      });
      if (full.status === "queued" || full.status === "running") setRunId(full.id);
      return;
    }
    api.getRun(pickId, { snapshot: false }).then((full) => {
      setRun((prev) => {
        if (!prev || String(prev.id) !== String(full.id)) return prev;
        if (prev.status === "queued" || prev.status === "running") return prev;
        return { ...full, snapshot: prev.snapshot };
      });
    }).catch(() => {});
  }

  function queueRun(res) {
    const id = res && typeof res === "object" ? res.id : res;
    if (!id) return;
    const status = (res && res.status) || "queued";
    setRun({
      id,
      status,
      generate_progress: (res && res.generate_progress) || null,
    });
    setRunId(status === "queued" || status === "running" ? id : "");
  }

  useEffect(() => {
    if (!user || user.must_change_password) return undefined;
    loadRuns().catch(() => {});
    return undefined;
  }, [user]);

  useEffect(() => {
    if (!runId) return undefined;
    let cancelled = false;
    let timer;
    let failures = 0;
    async function poll() {
      try {
        const doc = await api.getRun(runId, { snapshot: false });
        if (cancelled) return;
        failures = 0;
        setRun(doc);
        if (doc.status === "queued" || doc.status === "running") {
          timer = setTimeout(poll, 1000);
        } else {
          setRunId("");
          loadRuns(doc.id).catch(() => {});
        }
      } catch (e) {
        if (cancelled) return;
        failures += 1;
        if (failures >= 5) {
          setRun((prev) => ({ ...(prev || {}), id: runId, status: "failed", message: e.message }));
          setRunId("");
          return;
        }
        timer = setTimeout(poll, 1000);
      }
    }
    timer = setTimeout(poll, 400);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [runId]);

  const nav = useMemo(() => (user ? visibleNav(user) : []), [user]);
  const item = findItem(tab, sub);
  const snapshotNeeded = item?.kind === "reports" || item?.kind === "export";
  useEffect(() => {
    if (!snapshotNeeded || run?.status !== "succeeded" || !run?.id || run.snapshot) return undefined;
    let cancelled = false;
    api.getRun(run.id).then((full) => {
      if (cancelled) return;
      setRun((prev) => {
        if (!prev || String(prev.id) !== String(full.id)) return prev;
        return full;
      });
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [snapshotNeeded, run?.id, run?.status, run?.snapshot]);
  const crumb = useMemo(() => {
    const group = nav.find((t) => t.id === tab);
    const current = group?.items.find((i) => i.id === sub);
    if (!group || !current) return { section: "Vay Reports", page: "" };
    return { section: group.label, page: current.label };
  }, [nav, tab, sub]);

  useEffect(() => {
    document.title = crumb.page ? crumb.section + " · " + crumb.page : crumb.section;
  }, [crumb]);

  const succeeded = run?.status === "succeeded";
  const reports = run?.snapshot?.reports || run?.pdf_catalog || [];
  const busy = run?.status === "queued" || run?.status === "running";
  const succeededRuns = useMemo(() => (runs || []).filter((r) => r.status === "succeeded"), [runs]);
  const familyPresent = (family) => {
    if (!succeeded) return false;
    if (family === "Profit") return profitRan(reports);
    return (reports || []).some((r) => r.group === family);
  };

  function go(nextTab, nextSub) {
    setTab(nextTab);
    setSub(nextSub);
    setOpenTab(nextTab);
    if (window.location.hash && window.location.hash !== "#") {
      hashSet("");
    }
    hashReset();
  }

  async function selectRun(id) {
    if (!id || id === run?.id) return;
    const summary = (runs || []).find((row) => row.id === id);
    if (summary) setRun(summary);
    const full = await api.getRun(id, { snapshot: false });
    setRun((prev) => (prev && String(prev.id) !== String(full.id) ? prev : full));
    setRunId(full.status === "queued" || full.status === "running" ? full.id : "");
  }

  async function logout() {
    await api.logout().catch(() => {});
    setUser(null);
    setRun(null);
    setRuns([]);
  }

  if (!ready) return <div className="login-wrap"><p className="muted">Loading…</p></div>;
  if (!user) return <LoginPage onLogin={(u) => { setUser(u); const route = firstRoute(u); go(route.tab, route.sub); }} />;
  if (user.must_change_password) return <ChangePasswordPage user={user} onChanged={setUser} />;

  const viewRunId = succeeded ? run?.id : "";

  return (
    <div className="shell">
      <aside className="sidebar">
        <button type="button" className="brand" onClick={() => go("home", "home")}><span>Vay Reports</span></button>
        {nav.map((group) => (
          <div className="nav-group" key={group.id}>
            <button className={"nav-tab" + (openTab === group.id ? " open" : "")} onClick={() => {
              setOpenTab(group.id === openTab ? "" : group.id);
              if (group.items[0]) go(group.id, group.items[0].id);
            }}>
              <span>{group.label}</span>
            </button>
            <div className={"nav-sub" + (openTab === group.id ? " open" : "")}>
              {group.items.map((entry) => {
                const disabled = (entry.kind === "reports" && !familyPresent(entry.family))
                  || (entry.kind === "analytics" && entry.id !== "today" && !succeeded);
                return (
                  <button
                    type="button"
                    key={entry.id}
                    className={"nav-item" + (tab === group.id && sub === entry.id ? " active" : "") + (disabled ? " disabled" : "")}
                    title={disabled ? "Create reports first" : ""}
                    onClick={() => { if (!disabled) go(group.id, entry.id); }}
                  >
                    {entry.label}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div className="topbar-left">
            <nav className="topbar-crumb" aria-label="Breadcrumb">
              <span className="topbar-crumb-section">{crumb.section}</span>
              {crumb.page ? (
                <>
                  <span className="topbar-crumb-sep" aria-hidden="true" />
                  <h1 className="topbar-crumb-page">{crumb.page}</h1>
                </>
              ) : null}
            </nav>
          </div>
          <div className="topbar-right">
            <div className="topbar-meta">
              {busy ? (
                <span className="pill warn topbar-status" title={createProgressLabel(run)}>
                  <span className="topbar-pulse" aria-hidden="true" />
                  <span className="topbar-status-text">{createProgressLabel(run)}</span>
                </span>
              ) : null}
              <SnapshotPicker
                runs={succeededRuns}
                currentId={succeeded ? run?.id : ""}
                busy={busy}
                onSelect={selectRun}
              />
              {!run && !busy ? <span className="topbar-idle">Idle</span> : null}
            </div>
            <div className="user-menu">
              <span className="user-avatar" aria-hidden="true">{(user.username || "?").slice(0, 1).toUpperCase()}</span>
              <div className="user-meta">
                <span className="user-name">{user.username}</span>
                <span className="user-role">{user.role}</span>
              </div>
              <button type="button" className="ghost user-logout" onClick={logout}>Log out</button>
            </div>
          </div>
        </header>
        <main className="content">
          <SetupWizard user={user} onGo={go} />
          <DemoCard user={user} onOpened={loadRuns} />
          {item?.kind === "home" ? (
            <DashboardPage
              user={user}
              run={succeeded ? run : null}
              runs={succeededRuns}
              busy={busy}
              onSelectRun={selectRun}
              onGo={go}
            />
          ) : null}
          {item?.kind === "import" ? (
            <ImportPage
              onGo={go}
              busy={busy}
              run={run}
              onQueued={queueRun}
            />
          ) : null}
          {item?.kind === "explore" ? <ExplorePage /> : null}
          {item?.kind === "data" ? <DataPage key={item.id} type={item.type} title={item.label} user={user} /> : null}
          {item?.kind === "sales" ? <SalesPage /> : null}
          {item?.kind === "items" ? <ItemsPage /> : null}
          {item?.kind === "business" ? <BusinessPage user={user} runId={viewRunId} onGo={go} /> : null}
          {item?.kind === "customers" ? <CustomersPage user={user} runId={viewRunId} /> : null}
          {item?.kind === "items360" ? <StockPage user={user} profile runId={viewRunId} /> : null}
          {item?.kind === "item-dim" ? <ItemDimsPage dimension={item.dimension} runId={viewRunId} /> : null}
          {item?.kind === "groups" ? <GroupsPage user={user} runId={viewRunId} /> : null}
          {item?.kind === "reps" ? <RepsPage user={user} runId={viewRunId} /> : null}
          {item?.kind === "stock" ? <StockPage user={user} profile={false} runId={viewRunId} /> : null}
          {item?.kind === "cash" ? <CashPage /> : null}
          {item?.kind === "create" ? (
            <CreatePage
              user={user}
              busy={busy}
              run={run}
              onGo={go}
              onQueued={queueRun}
            />
          ) : null}
          {item?.kind === "reports" ? <ReportsPage run={run} family={item.family} /> : null}
          {item?.kind === "analytics" ? <AnalyticsPage section={item.section} run={succeeded ? run : null} user={user} /> : null}
          {item?.kind === "export" ? <ExportPage run={run} /> : null}
          {item?.kind === "excel" ? <ExcelPage run={run} /> : null}
          {item?.kind === "settings" ? <SettingsPage section={item.section} user={user} onFactoryReset={() => { setRun(null); setRuns([]); }} /> : null}
        </main>
      </div>
    </div>
  );
}
