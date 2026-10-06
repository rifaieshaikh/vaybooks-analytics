import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { EmptyCard } from "./FilterBar";

const GROUP_ORDER = ["Performance", "Follow-up", "Monthly", "Items", "Profit", "Data issues"];

function snapshotRows(run) {
  return (run?.snapshot?.reports || []).map((row) => ({
    id: row.id,
    title: row.friendly_title || row.title || row.id,
    group: row.group || "",
    exists: false,
    state: "idle",
  }));
}

function stateLabel(state) {
  if (state === "waiting") return "Waiting";
  if (state === "running") return "Exporting";
  if (state === "done") return "Done";
  if (state === "failed") return "Failed";
  if (state === "idle") return "";
  return state || "";
}

export default function ExportPage({ run }) {
  const ready = run?.status === "succeeded";
  const [exp, setExp] = useState(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const [picked, setPicked] = useState(null);

  useEffect(() => {
    if (!run?.id || run.status !== "succeeded") {
      setExp(null);
      return undefined;
    }
    let cancelled = false;
    api.getRunExport(run.id).then((d) => {
      if (!cancelled) setExp(d);
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [run?.id, run?.status]);

  const exporting = exp?.status === "queued" || exp?.status === "running";

  useEffect(() => {
    if (!run?.id || !exporting) return undefined;
    const t = setInterval(async () => {
      try {
        const d = await api.getRunExport(run.id);
        setExp(d);
      } catch (e) {
        setErr(e.message);
      }
    }, 1000);
    return () => clearInterval(t);
  }, [run?.id, exporting]);

  const reports = exp?.reports?.length ? exp.reports : snapshotRows(run);

  useEffect(() => {
    if (!open || !reports.length) return;
    setPicked((prev) => {
      if (prev) return prev;
      const next = {};
      reports.forEach((row) => {
        next[row.id] = exporting
          ? row.state === "waiting" || row.state === "running" || row.state === "done"
          : !row.exists;
      });
      return next;
    });
  }, [open, reports, exporting]);

  const groups = useMemo(() => {
    const by = {};
    reports.forEach((row) => {
      const key = row.group || "Reports";
      if (!by[key]) by[key] = [];
      by[key].push(row);
    });
    const known = GROUP_ORDER.filter((name) => by[name]).map((name) => [name, by[name]]);
    const extra = Object.keys(by).filter((name) => !GROUP_ORDER.includes(name)).sort();
    return known.concat(extra.map((name) => [name, by[name]]));
  }, [reports]);

  const selectedIds = reports.filter((row) => picked && picked[row.id]).map((row) => row.id);
  const zipName = (exp?.folder || "vay_reports").replace(/\//g, "_") + ".zip";
  const working = busy || exporting;
  const total = exp?.total || selectedIds.length || 0;
  const done = exp?.done || 0;
  const pct = total ? Math.min(100, Math.round((done / total) * 100)) : 0;
  const currentRow = reports.find((row) => row.id === exp?.current);

  async function start() {
    if (!selectedIds.length) {
      setErr("Select at least one report.");
      return;
    }
    setErr("");
    setBusy(true);
    try {
      const d = await api.exportRunPdfs(run.id, selectedIds);
      setExp(d);
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  function toggleGroup(name, on) {
    const ids = (groups.find(([g]) => g === name) || [name, []])[1].map((row) => row.id);
    setPicked((prev) => {
      const next = { ...(prev || {}) };
      ids.forEach((id) => { next[id] = on; });
      return next;
    });
  }

  async function openModal() {
    setErr("");
    setPicked(null);
    setOpen(true);
    if (!run?.id) return;
    try {
      const d = await api.getRunExport(run.id);
      setExp(d);
      const exportingNow = d.status === "queued" || d.status === "running";
      const next = {};
      (d.reports || []).forEach((row) => {
        next[row.id] = exportingNow
          ? row.state === "waiting" || row.state === "running" || row.state === "done"
          : !row.exists;
      });
      setPicked(next);
    } catch (e) {
      setErr(e.message);
    }
  }

  if (!ready) {
    return <EmptyCard title="Create reports first" copy="Export writes a PDF for each generated report after a run succeeds." />;
  }

  return (
    <div className="workspace-page">
      <div className="page-head">
        <div className="page-head-copy">
          <h2>Export</h2>
          <p className="muted">PDFs for {run.report_date}{run.fy_label ? " · " + run.fy_label : ""}. Choose which reports to generate. Only reports you can view are listed.</p>
        </div>
        {exp?.zip_ready ? (
          <button className="secondary" onClick={() => api.downloadRunPdfZip(run.id, zipName)}>Download zip</button>
        ) : null}
      </div>
      <div className="card">
        <p className="muted">The zip contains only the reports you generate. Existing files are labelled so you can leave them or generate again.</p>
        <button disabled={working && !open} onClick={openModal}>{exporting ? "Export in progress…" : "Export PDFs"}</button>
        {exp?.status === "succeeded" && exp.message ? <p className="ok">{exp.message}</p> : null}
        {exp?.status === "failed" ? <p className="err">{exp.message || "Could not export PDFs. Click Export PDFs and Generate to try again."}</p> : null}
        {err && !open ? <p className="err">{err}</p> : null}
      </div>
      {open ? (
        <div className="modal-backdrop" onClick={() => { if (!working) setOpen(false); }}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>Export PDFs</h3>
            <p className="muted">Select reports for {run.report_date}. The zip will include only those reports. Tick an existing file to generate it again.</p>
            {working ? (
              <div className="export-progress">
                <div className="muted">
                  {exp?.current === "zip"
                    ? "Packing zip…"
                    : currentRow
                      ? "Exporting " + currentRow.title
                      : "Exporting PDFs…"}
                  {total ? " · " + done + " of " + total : ""}
                </div>
                <div className="progress-bar"><span style={{ width: pct + "%" }} /></div>
              </div>
            ) : null}
            {groups.map(([name, rows]) => (
              <div className="export-group" key={name}>
                <div className="export-group-head">
                  <h4>{name}</h4>
                  {!working ? (
                    <span>
                      <button type="button" className="ghost" onClick={() => toggleGroup(name, true)}>Select all</button>
                      <button type="button" className="ghost" onClick={() => toggleGroup(name, false)}>None</button>
                    </span>
                  ) : null}
                </div>
                {rows.map((row) => (
                  <label className="export-row" key={row.id}>
                    <input
                      type="checkbox"
                      disabled={working}
                      checked={Boolean(picked && picked[row.id])}
                      onChange={(e) => setPicked((prev) => ({ ...(prev || {}), [row.id]: e.target.checked }))}
                    />
                    <span className="grow">{row.title}</span>
                    {row.exists && !working ? <span className="pill">Already exported</span> : null}
                    {working || row.state === "failed" ? (
                      stateLabel(row.state) ? <span className={"pill" + (row.state === "failed" ? " err" : "")}>{stateLabel(row.state)}</span> : null
                    ) : null}
                  </label>
                ))}
              </div>
            ))}
            {!groups.length ? <p className="muted">No reports you can view are in this run.</p> : null}
            {err ? <p className="err">{err}</p> : null}
            <div className="modal-actions">
              <button type="button" className="ghost" onClick={() => setOpen(false)}>Close</button>
              {exp?.zip_ready && !working ? (
                <button type="button" className="secondary" onClick={() => api.downloadRunPdfZip(run.id, zipName)}>Download zip</button>
              ) : null}
              <button type="button" disabled={working || !selectedIds.length} onClick={start}>Generate</button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
