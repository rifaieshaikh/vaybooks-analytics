import { useEffect, useMemo, useRef, useState } from "react";
import SectionTabs from "./SectionTabs";
import { api } from "./api";
import ReportProgress from "./ReportProgress";
import { ITEM_ATTR_FIELDS, REQUIRED_FIELDS, TYPE_META } from "./theme";

const IMPORT_TYPES = ["sales", "items", "arr", "receipt", "credit_note", "payments", "stock", "party", "reservation", "incoming", "item_cost", "opening_cash", "payable"];
const SKIP_DEST = "__skip__";

const STEPS = [
  { id: "file", title: "File" },
  { id: "sheets", title: "Sheets" },
  { id: "preview", title: "Preview" },
  { id: "mapping", title: "Mapping" },
  { id: "duplicates", title: "Duplicates" },
  { id: "existing", title: "Existing" },
  { id: "progress", title: "Import" },
  { id: "create", title: "Reports" },
];

const PACKS = [
  { id: "core", title: "Sales, collections, and follow-up", hint: "Performance and follow-up from sales, receipts, and outstanding." },
  { id: "fiscal", title: "Month-by-month by year", hint: "Wide monthly reports by fiscal year." },
  { id: "items", title: "Items and stock", hint: "Item quantity and stock reports." },
  { id: "profit", title: "Profit and expenses", hint: "P&L and expenses." },
];

function friendlyType(name) {
  return TYPE_META[name]?.label || name;
}

function isSkipDest(dest) {
  const v = String(dest || "").trim().toLowerCase();
  return !v || v === SKIP_DEST || v === "skip" || v === "(skip)";
}

function sheetMissing(sheet) {
  if (!sheet?.type) return ["No import type"];
  const dests = new Set();
  (sheet.headers || []).forEach((h) => {
    const dest = (sheet.column_map || {})[h];
    if (dest === undefined) dests.add(h);
    else if (!isSkipDest(dest)) dests.add(dest);
  });
  return (REQUIRED_FIELDS[sheet.type] || []).filter((name) => !dests.has(name));
}

function localReady(sheet) {
  if (!sheet || sheet.skip || !sheet.type) return false;
  if (sheet.allowed === false) return false;
  return sheetMissing(sheet).length === 0 && (sheet.unique_key || []).length > 0;
}

function mappingReady(sheet) {
  if (!sheet || sheet.skip || !sheet.type) return false;
  if (sheet.allowed === false) return false;
  if (sheet.header_changes?.changed && !sheet.mapping_confirmed) return false;
  return sheetMissing(sheet).length === 0;
}

function formatWhen(value) {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return parsed.toLocaleString();
}

function resultLine(name, info) {
  if (!info) return "";
  if (info.error) return `${friendlyType(name)}: ${info.error}`;
  const bits = [];
  if (info.added) bits.push(`${info.added} added`);
  if (info.updated) bits.push(`${info.updated} updated`);
  if (info.upserted) bits.push(`${info.upserted} saved`);
  if (info.skipped_total) bits.push(`${info.skipped_total} skipped`);
  else if (info.skipped) bits.push(`${info.skipped} skipped`);
  if (info.deleted) bits.push(`${info.deleted} deleted`);
  if (info.would_delete) bits.push(`${info.would_delete} would delete`);
  if (info.customers_created) bits.push(`${info.customers_created} customers created`);
  if (info.parties_created) bits.push(`${info.parties_created} parties created`);
  if (info.balances_updated) bits.push(`${info.balances_updated} balances updated`);
  return `${friendlyType(name)}: ${bits.join(", ") || "saved"}`;
}

function OnboardingPreview({ active, reportDate }) {
  const [data, setData] = useState(null);
  const [salesTotal, setSalesTotal] = useState("");
  const [outstandingTotal, setOutstandingTotal] = useState("");
  const [compareErr, setCompareErr] = useState("");

  function load(extra) {
    const params = { report_date: reportDate || "" };
    if (extra) Object.assign(params, extra);
    setCompareErr("");
    return api.onboarding(params).then((payload) => {
      setData(payload);
      const controls = payload?.controls || {};
      if (!extra) {
        if (controls.sales?.entered != null) setSalesTotal(String(controls.sales.entered));
        if (controls.outstanding?.entered != null) setOutstandingTotal(String(controls.outstanding.entered));
      }
      return payload;
    }).catch((err) => setCompareErr(err.message || "Could not compare totals"));
  }

  useEffect(() => {
    if (!active) return undefined;
    let cancelled = false;
    load().then(() => { if (cancelled) setData(null); });
    return () => { cancelled = true; };
  }, [active, reportDate]);

  if (!active || !data) return null;
  const blocked = (data.metrics || []).filter((row) => row.status !== "eligible");
  const sources = data.sources || [];
  return (
    <div className="card" style={{ marginTop: 12 }}>
      <h4>What this import can calculate</h4>
      {(data.missing_files || []).length ? (
        <p className="muted">Still missing: {(data.missing_files || []).map((row) => row.label).join(", ")}</p>
      ) : <p className="ok">Sales, receipts, outstanding, item sales, and stock are present.</p>}
      {sources.map((row) => (
        <p key={row.type} className={row.present && row.date_ok ? "muted" : "warn"}>
          {row.label}: {(row.required_fields || []).join(", ") || "No required fields"}. {row.date_note}
        </p>
      ))}
      <label>Agreed sales total
        <input value={salesTotal} onChange={(e) => setSalesTotal(e.target.value)} inputMode="decimal" />
      </label>
      <label>Agreed outstanding total
        <input value={outstandingTotal} onChange={(e) => setOutstandingTotal(e.target.value)} inputMode="decimal" />
      </label>
      <p>
        <button type="button" className="secondary" onClick={() => load({
          control_sales: salesTotal,
          control_outstanding: outstandingTotal,
        })}
        >Compare totals</button>
      </p>
      {compareErr ? <p className="err">{compareErr}</p> : null}
      {(data.exceptions || []).map((row) => (
        <p key={row.id} className="warn">{row.message}</p>
      ))}
      {blocked.length ? blocked.slice(0, 8).map((row) => (
        <p key={row.id} className="muted">{row.id}: {row.reason || "Unavailable"}. {row.fix}</p>
      )) : <p className="ok">Headline metrics are eligible for {data.report_date}.</p>}
    </div>
  );
}

function RefreshStatus({ runId, active }) {
  const [data, setData] = useState(null);
  useEffect(() => {
    if (!active) return undefined;
    let cancelled = false;
    api.refresh(runId || "").then((payload) => { if (!cancelled) setData(payload); }).catch(() => {});
    return () => { cancelled = true; };
  }, [active, runId]);
  if (!active || !data || (!data.report_finished_at && !(data.missing || []).length)) return null;
  const used = (data.types_used || []).join(", ");
  return (
    <div style={{ marginTop: 12 }}>
      {data.report_finished_at ? (
        <p className="muted">Report finished {formatWhen(data.report_finished_at)}.</p>
      ) : null}
      {data.current ? (
        <p className="ok">This report includes the batches for {used || "the sheets it used"}.</p>
      ) : (
        <div>
          <p className="warn">Later imports are not in this report.</p>
          {(data.missing || []).map((row) => (
            <p key={row.id} className="muted">
              {row.filename || "Import"} ({(row.types || []).join(", ")}) finished {formatWhen(row.finished_at) || "—"}.
            </p>
          ))}
        </div>
      )}
      {(data.included || []).filter((row) => row.finished_at).slice(0, 6).map((row) => (
        <p key={row.id} className="muted">
          Included upload {row.filename || row.id} finished {formatWhen(row.finished_at)}.
        </p>
      ))}
    </div>
  );
}

function stateLabel(state) {
  if (state === "waiting") return "Waiting";
  if (state === "running") return "In progress";
  if (state === "done") return "Completed";
  if (state === "failed") return "Failed";
  if (state === "skipped") return "Skipped";
  return state || "";
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

const PREVIEW_BUCKETS = [
  ["added", "Added"],
  ["updated", "Updated"],
  ["upserted", "Upserted"],
  ["skipped", "Skipped"],
  ["would_delete", "Would delete"],
];

function bucketCount(sheet, key) {
  if (!sheet) return 0;
  if (key === "skipped") {
    if (sheet.skipped_total != null) return Number(sheet.skipped_total) || 0;
    return Number(sheet.skipped || 0)
      + Number(sheet.total_skipped || 0)
      + Number(sheet.blank_skipped || 0)
      + Number(sheet.failed_row || 0)
      + Number(sheet.clash || 0);
  }
  return Number(sheet[key] || 0);
}

function previewFieldHeaders(rows) {
  const keys = new Set();
  (rows || []).forEach((row) => {
    Object.keys(row.fields || {}).forEach((k) => keys.add(k));
  });
  return Array.from(keys);
}

function DryRunDetails({ sheets }) {
  const detailSheets = useMemo(
    () => (sheets || []).filter((s) => s && !s.skipped && !s.error && s.preview_rows),
    [sheets],
  );
  const [sheetIdx, setSheetIdx] = useState(0);
  const [bucket, setBucket] = useState("skipped");

  useEffect(() => {
    setSheetIdx(0);
  }, [detailSheets.length]);

  const active = detailSheets[Math.min(sheetIdx, Math.max(0, detailSheets.length - 1))] || null;

  useEffect(() => {
    if (!active) return;
    const first = PREVIEW_BUCKETS.find(([key]) => bucketCount(active, key) > 0);
    if (first) setBucket(first[0]);
  }, [active?.sheet, active?.type]);

  if (!detailSheets.length) return null;

  const rows = (active?.preview_rows && active.preview_rows[bucket]) || [];
  const total = bucketCount(active, bucket);
  const truncated = Boolean(active?.preview_truncated && active.preview_truncated[bucket]);
  const fieldHeaders = previewFieldHeaders(rows);
  const showReason = bucket === "skipped" || bucket === "would_delete";

  return (
    <div className="card dry-run-details" style={{ marginTop: 12, padding: 12 }}>
      <h4 style={{ marginTop: 0 }}>Dry-run details</h4>
      <p className="muted">Inspect which rows would be added, updated, skipped, or deleted. Skipped rows include a reason.</p>
      {detailSheets.length > 1 ? (
        <div className="chips" style={{ marginBottom: 8 }}>
          {detailSheets.map((s, i) => (
            <button
              key={s.sheet + String(i)}
              type="button"
              className={sheetIdx === i ? "" : "secondary"}
              onClick={() => setSheetIdx(i)}
            >
              {s.sheet}
              {s.type ? ` · ${friendlyType(s.type)}` : ""}
            </button>
          ))}
        </div>
      ) : (
        <p className="muted">{active?.sheet}{active?.type ? ` · ${friendlyType(active.type)}` : ""}</p>
      )}
      <SectionTabs
        label="Dry-run buckets"
        value={bucket}
        onChange={setBucket}
        tabs={PREVIEW_BUCKETS.flatMap(([key, label]) => {
          const n = bucketCount(active, key);
          if (!n && key !== bucket) return [];
          return [{ id: key, label, count: n }];
        })}
      />
      <div className="tab-panel" style={{ paddingTop: 10 }}>
        {truncated ? (
          <p className="muted">Showing {rows.length} of {total}</p>
        ) : (
          <p className="muted">{total} row{total === 1 ? "" : "s"}</p>
        )}
        {rows.length ? (
          <div className="table-wrap preview-table wizard-preview">
            <table className="dense">
              <thead>
                <tr>
                  {showReason ? <th>Reason</th> : null}
                  {fieldHeaders.map((h) => <th key={h}>{h}</th>)}
                  <th>Key</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, i) => (
                  <tr key={(row.uk || "") + String(i)}>
                    {showReason ? (
                      <td>{row.reason_label || row.reason || "—"}</td>
                    ) : null}
                    {fieldHeaders.map((h) => (
                      <td key={h}>{row.fields && row.fields[h] != null ? String(row.fields[h]) : ""}</td>
                    ))}
                    <td className="muted" style={{ maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis" }}>
                      {row.uk || ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="muted">No rows in this bucket.</p>
        )}
      </div>
    </div>
  );
}

function MappingModal({ sheet, onClose, onSave }) {
  const [columnMap, setColumnMap] = useState(() => ({ ...(sheet.column_map || {}) }));
  const fields = useMemo(() => {
    const req = REQUIRED_FIELDS[sheet.type] || [];
    const optional = sheet.type === "items" || sheet.type === "stock" ? ITEM_ATTR_FIELDS : [];
    const fromMap = Object.values(columnMap).filter((d) => !isSkipDest(d));
    return Array.from(new Set([...req, ...optional, ...fromMap, "Invoice No", "Taxable Amount", "Tax Amount"]));
  }, [sheet.type, columnMap]);

  const missing = useMemo(() => {
    const dests = new Set();
    (sheet.headers || []).forEach((h) => {
      const dest = columnMap[h];
      if (dest === undefined) dests.add(h);
      else if (!isSkipDest(dest)) dests.add(dest);
    });
    return (REQUIRED_FIELDS[sheet.type] || []).filter((name) => !dests.has(name));
  }, [sheet.headers, sheet.type, columnMap]);

  return (
    <div className="modal-backdrop map-backdrop" onClick={onClose}>
      <div className="modal map-modal" onClick={(e) => e.stopPropagation()}>
        <h3>Set mapping · {sheet.sheet}</h3>
        <p className="muted">
          Defaults come from Settings → Data mappers for {friendlyType(sheet.type)}. Map each column, or skip it.
        </p>
        {missing.length ? <p className="warn">Still need: {missing.join(" · ")}</p> : <p className="ok">Required fields are covered.</p>}
        {sheet.type === "sales" ? (
          <p>
            <button
              type="button"
              className="secondary"
              onClick={() => {
                const preset = {
                  "Invoice Date": "Date",
                  "Customer": "Party Name",
                  "Rep": "Sales Rep",
                  "Amount": "Net Amount",
                };
                setColumnMap((prev) => {
                  const next = { ...prev };
                  (sheet.headers || []).forEach((header) => {
                    if (preset[header]) next[header] = preset[header];
                  });
                  return next;
                });
                api.applyMapperPreset("sales", "plain_sales").catch(() => {});
              }}
            >
              Use plain sales headers
            </button>
          </p>
        ) : null}
        <div className="map-modal-list">
          {(sheet.headers || []).map((src) => {
            const val = columnMap[src];
            const selectVal = isSkipDest(val) ? SKIP_DEST : (val || src);
            return (
              <div className="map-row" key={src}>
                <span title={src}>{src}</span>
                <span className="muted">→</span>
                <select
                  value={selectVal}
                  onChange={(e) => setColumnMap((prev) => ({ ...prev, [src]: e.target.value }))}
                >
                  <option value={SKIP_DEST}>Skip column</option>
                  {fields.map((f) => <option key={f} value={f}>{f}</option>)}
                </select>
              </div>
            );
          })}
        </div>
        <div className="modal-actions">
          <button type="button" className="secondary" onClick={onClose}>Cancel</button>
          <button
            type="button"
            disabled={missing.length > 0}
            onClick={() => onSave(columnMap)}
          >
            Save mapping
          </button>
        </div>
      </div>
    </div>
  );
}

export default function ImportPage({ onGo, onQueued, busy: reportBusy, run }) {
  const [wizardOpen, setWizardOpen] = useState(false);
  const [step, setStep] = useState(0);
  const [file, setFile] = useState(null);
  const [sheets, setSheets] = useState([]);
  const [previewTab, setPreviewTab] = useState(0);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [mapSheetIdx, setMapSheetIdx] = useState(null);
  const [importSteps, setImportSteps] = useState([]);
  const [importResult, setImportResult] = useState(null);
  const [packs, setPacks] = useState({ core: true, fiscal: true, items: false, profit: false });
  const [reportDate, setReportDate] = useState(new Date().toISOString().slice(0, 10));
  const [createErr, setCreateErr] = useState("");
  const [creatingLocal, setCreatingLocal] = useState(false);
  const [setupGate, setSetupGate] = useState(null);
  const [settlementSummary, setSettlementSummary] = useState("");
  const importLock = useRef(false);

  const included = useMemo(() => sheets.filter((s) => !s.skip && s.type), [sheets]);
  const stepId = STEPS[step]?.id;

  function mapsPayload(list) {
    const out = {};
    (list || sheets).forEach((s) => {
      out[s.sheet] = {
        type: s.skip ? "" : (s.type || ""),
        skip: Boolean(s.skip),
        column_map: s.column_map || {},
        unique_key: s.unique_key || [],
        event_mode: s.event_mode || "skip",
        mapping_confirmed: Boolean(s.mapping_confirmed),
      };
    });
    return out;
  }

  function updateSheet(idx, patch) {
    setSheets((prev) => prev.map((s, i) => (i === idx ? { ...s, ...patch } : s)));
  }

  function resetWizard() {
    setStep(0);
    setFile(null);
    setSheets([]);
    setPreviewTab(0);
    setErr("");
    setBusy(false);
    setMapSheetIdx(null);
    setImportSteps([]);
    setImportResult(null);
    setCreateErr("");
    setCreatingLocal(false);
    importLock.current = false;
  }

  function openWizard() {
    resetWizard();
    setWizardOpen(true);
  }

  function closeWizard() {
    if (busy || creatingLocal || reportBusy) return;
    setWizardOpen(false);
  }

  async function loadPreview(nextFile, nextMaps) {
    setErr("");
    setBusy(true);
    try {
      const out = await api.previewUpload(nextFile, "", nextMaps || undefined);
      const rows = (out.sheets || []).map((s) => ({
        ...s,
        skip: Boolean(s.skip) || !s.type,
        event_mode: s.event_mode || "skip",
        mapping_confirmed: false,
        mapping_touched: false,
      }));
      setSheets(rows);
      setPreviewTab(0);
      return rows;
    } catch (e) {
      setErr(e.message);
      setSheets([]);
      return [];
    } finally {
      setBusy(false);
    }
  }

  async function onPickFile(chosen) {
    setFile(chosen || null);
    setSheets([]);
    setErr("");
    if (chosen) await loadPreview(chosen);
  }

  async function changeSheetType(idx, typeValue) {
    const skip = typeValue === "" || typeValue === "__skip__";
    const type = skip ? "" : typeValue;
    const next = sheets.map((s, i) => (
      i === idx
        ? { ...s, type: type || null, skip, mapping_touched: false }
        : s
    ));
    setSheets(next);
    if (!file) return;
    setBusy(true);
    setErr("");
    try {
      const out = await api.previewUpload(file, "", mapsPayload(next));
      const rows = (out.sheets || []).map((s, i) => {
        const plannedSkip = Boolean(next[i]?.skip);
        const prev = next[i] || {};
        const sameDrift = JSON.stringify(prev.header_changes || {}) === JSON.stringify(s.header_changes || {});
        const typeChanged = (prev.type || null) !== (s.type || null);
        return {
          ...s,
          skip: plannedSkip,
          type: plannedSkip ? null : (s.type || prev.type || null),
          event_mode: typeChanged ? (s.event_mode || "skip") : (prev.event_mode || s.event_mode || "skip"),
          mapping_confirmed: sameDrift ? Boolean(prev.mapping_confirmed) : false,
          mapping_touched: false,
        };
      });
      setSheets(rows);
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  function canNext() {
    if (stepId === "file") return Boolean(file) && sheets.length > 0 && !busy;
    if (stepId === "sheets") return included.length > 0 && !busy;
    if (stepId === "preview") return included.length > 0;
    if (stepId === "mapping") return included.length > 0 && included.every(mappingReady);
    if (stepId === "duplicates") return included.every((s) => (s.unique_key || []).length > 0);
    if (stepId === "existing") return included.length > 0 && !busy;
    return false;
  }

  async function goNext() {
    if (stepId === "existing") {
      await startImport({ dry_run: false });
      return;
    }
    if (step < STEPS.length - 1) setStep((s) => s + 1);
  }

  function goBack() {
    if (stepId === "progress" || stepId === "create") return;
    if (step > 0) setStep((s) => s - 1);
  }

  async function startImport(opts) {
    if (!file || importLock.current) return;
    const toImport = sheets.filter((s) => !s.skip && s.type);
    if (!toImport.length) return;
    const dryRun = Boolean(opts && opts.dry_run);
    importLock.current = true;
    setStep(STEPS.findIndex((s) => s.id === "progress"));
    setErr("");
    setBusy(true);
    setImportSteps(toImport.map((s) => ({
      sheet: s.sheet,
      type: s.type,
      state: "waiting",
      detail: "",
    })));
    try {
      const maps = mapsPayload(sheets);
      const queued = await api.createImportJob(file, maps, "skip", { dry_run: dryRun });
      const jobId = queued.id;
      let doc = queued;
      // Apply progress if the job already finished (sync mode).
      const applyProgress = (job) => {
        const progressSheets = job.progress?.sheets || [];
        if (!progressSheets.length) return;
        setImportSteps(progressSheets
          .filter((s) => s.state !== "skipped")
          .map((s) => ({
            sheet: s.sheet,
            type: s.type,
            state: s.state || "waiting",
            detail: s.error
              || [
                s.added && `${s.added} added`,
                s.updated && `${s.updated} updated`,
                s.upserted && `${s.upserted} saved`,
                s.skipped && `${s.skipped} skipped`,
                s.deleted && `${s.deleted} deleted`,
                s.would_delete && `${s.would_delete} would delete`,
              ]
                .filter(Boolean)
                .join(", "),
          })));
      };
      applyProgress(doc);
      let pollDelay = 2000;
      while (doc.status === "queued" || doc.status === "running") {
        await sleep(pollDelay);
        doc = await api.getImportJob(jobId);
        applyProgress(doc);
        pollDelay = Math.min(pollDelay * 2, 8000);
      }
      applyProgress(doc);
      setImportResult({
        id: doc.upload_id || doc.id,
        upload_id: doc.upload_id,
        types: doc.types || {},
        sheets: doc.sheets || [],
        dry_run: Boolean(doc.dry_run),
        file_sha256: doc.file_sha256 || "",
        finished_at: doc.finished_at || "",
      });
      if (doc.status === "failed" && doc.message) setErr(doc.message);
      if (doc.message === "Already imported") setErr("This file is already imported.");
      if (dryRun) {
        setStep(STEPS.findIndex((s) => s.id === "existing"));
      } else {
        setStep(STEPS.findIndex((s) => s.id === "create"));
      }
    } catch (e) {
      setErr(e.message || "Import failed");
      setImportSteps((prev) => prev.map((row) => (
        row.state === "running" || row.state === "waiting"
          ? { ...row, state: "failed", detail: e.message || "Import failed" }
          : row
      )));
      setStep(STEPS.findIndex((s) => s.id === (dryRun ? "existing" : "create")));
    } finally {
      setBusy(false);
      importLock.current = false;
    }
  }

  async function undoImport() {
    const uid = importResult?.upload_id || importResult?.id;
    if (!uid) return;
    setErr("");
    try {
      await api.deleteUpload(uid);
      setImportResult(null);
      setErr("");
      alert("Import undone — rows from that upload were removed.");
    } catch (e) {
      setErr(e.message || "Could not undo import");
    }
  }

  useEffect(() => {
    if (!creatingLocal) return;
    if (run?.status === "succeeded" || run?.status === "failed") {
      setCreatingLocal(false);
    }
  }, [creatingLocal, run?.status]);

  async function createReports() {
    setCreateErr("");
    setSetupGate(null);
    try {
      const settings = await api.settlement();
      if (!settings.setup_complete) {
        setSetupGate({
          mode: settings.mode,
          bands: settings.aging_bands || [],
        });
        return;
      }
      const labels = (settings.aging_bands || []).map((b) => b.label).filter(Boolean);
      const modeLabel = settings.mode === "specific" ? "Specific" : "Oldest to latest";
      setSettlementSummary(
        modeLabel + (labels.length ? " · bands " + labels.join(", ") : "")
      );
      const res = await api.createRun({ packs, report_date: reportDate });
      if (onQueued) onQueued(res);
      setCreatingLocal(true);
    } catch (e) {
      setCreateErr(e.message);
    }
  }

  const progress = run?.generate_progress || null;

  const importDoneCount = importSteps.filter((s) => s.state === "done" || s.state === "failed").length;
  const importPct = importSteps.length ? Math.min(100, Math.round((importDoneCount / importSteps.length) * 100)) : 0;
  const anyImported = importSteps.some((s) => s.state === "done");
  const creating = creatingLocal || reportBusy;

  const previewSheet = included[previewTab] || included[0];
  const sampleCols = useMemo(() => {
    if (!previewSheet?.sample?.length) return previewSheet?.headers || [];
    return Array.from(new Set(previewSheet.sample.flatMap((row) => Object.keys(row))));
  }, [previewSheet]);

  const mapTarget = mapSheetIdx != null ? sheets[mapSheetIdx] : null;

  return (
    <div>
      <div className="card">
        <h2>Import</h2>
        <p className="muted">
          Choose a file, preview with the last import mode, commit, then create the report.
          Outstanding and stock stay upserts with an effective date.
        </p>
        <div className="row gap">
          <button type="button" onClick={openWizard}>Start import</button>
          <button type="button" className="secondary" onClick={openWizard}>Refresh</button>
        </div>
        <RefreshStatus runId={run?.status === "succeeded" ? run.id : ""} active />
        <OnboardingPreview active />
      </div>

      {wizardOpen ? (
        <div className="modal-backdrop wizard-backdrop" onClick={closeWizard}>
          <div className="modal wizard-modal" onClick={(e) => e.stopPropagation()}>
            <div className="wizard-head">
              <h3>Import wizard</h3>
              <button type="button" className="ghost wizard-close" disabled={busy || creating} onClick={closeWizard}>Close</button>
            </div>

            <div className="wizard-steps" aria-label="Steps">
              {STEPS.map((s, i) => (
                <div key={s.id} className={"wizard-step" + (i === step ? " current" : "") + (i < step ? " done" : "")}>
                  <span className="wizard-step-num">{i + 1}</span>
                  <span className="wizard-step-label">{s.title}</span>
                </div>
              ))}
            </div>

            <div className="wizard-body">
              {err && stepId !== "progress" ? <p className="err">{err}</p> : null}

              {stepId === "file" ? (
                <div>
                  <h4>Select a file</h4>
                  <p className="muted">Excel or CSV workbook. The last import mode for each sheet is selected again on the Existing step.</p>
                  <label className="dropzone">
                    <input type="file" accept=".xlsx,.xls,.csv" onChange={(e) => onPickFile(e.target.files[0])} />
                    <strong>{file ? file.name : "Choose a file"}</strong>
                    <span className="muted">{file ? "Click to replace" : "Excel or CSV"}</span>
                  </label>
                  {busy ? <p className="muted">Reading file…</p> : null}
                  {file && sheets.length ? (
                    <p className="ok">{sheets.length} sheet{sheets.length === 1 ? "" : "s"} found</p>
                  ) : null}
                </div>
              ) : null}

              {stepId === "sheets" ? (
                <div>
                  <h4>Map sheets to import types</h4>
                  <p className="muted">Skip sheets you do not need. Several sheets can use the same type.</p>
                  <div className="sheet-plan-list">
                    {sheets.map((s, i) => (
                      <div className="sheet-plan-row" key={s.sheet + i}>
                        <div className="sheet-plan-name">
                          <strong>{s.sheet}</strong>
                          <span className="muted">{s.row_count} rows</span>
                        </div>
                        <select
                          value={s.skip || !s.type ? "__skip__" : s.type}
                          onChange={(e) => changeSheetType(i, e.target.value)}
                          disabled={busy}
                        >
                          <option value="__skip__">Skip</option>
                          {IMPORT_TYPES.map((t) => (
                            <option key={t} value={t}>{friendlyType(t)}</option>
                          ))}
                        </select>
                        <span className={"pill " + (s.skip || !s.type ? "" : "ok")}>
                          {s.skip || !s.type ? "Skip" : friendlyType(s.type)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}

              {stepId === "preview" ? (
                <div>
                  <h4>Sample data</h4>
                  <p className="muted">Review a few rows from each included sheet.</p>
                  <div className="chips">
                    {included.map((s, i) => (
                      <button
                        type="button"
                        key={s.sheet}
                        className={previewTab === i ? "" : "secondary"}
                        onClick={() => setPreviewTab(i)}
                      >
                        {s.sheet}
                      </button>
                    ))}
                  </div>
                  {previewSheet ? (
                    <>
                      <p className="muted">{friendlyType(previewSheet.type)} · {previewSheet.row_count} rows</p>
                      <div className="table-wrap preview-table wizard-preview">
                        <table>
                          <thead><tr>{sampleCols.map((h) => <th key={h}>{h}</th>)}</tr></thead>
                          <tbody>
                            {(previewSheet.sample || []).slice(0, 8).map((row, i) => (
                              <tr key={i}>{sampleCols.map((h) => <td key={h}>{row[h] == null ? "" : String(row[h])}</td>)}</tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                      {!previewSheet.sample?.length ? <p className="muted">This sheet is empty.</p> : null}
                    </>
                  ) : null}
                </div>
              ) : null}

              {stepId === "mapping" ? (
                <div>
                  <h4>Column mapping</h4>
                  <p className="muted">Defaults come from Settings. Open Set mapping to adjust or skip columns.</p>
                  <div className="wizard-map-list">
                    {included.map((s) => {
                      const idx = sheets.findIndex((x) => x.sheet === s.sheet);
                      const ready = mappingReady(s);
                      const missing = sheetMissing(s);
                      return (
                        <div className="wizard-map-row" key={s.sheet}>
                          <div>
                            <strong>{s.sheet}</strong>
                            <div className="muted">{friendlyType(s.type)} · {s.row_count} rows</div>
                            {!ready && missing.length ? <div className="warn">{missing.join(" · ")}</div> : null}
                            {s.header_changes?.changed ? (
                              <div className="warn">
                                Headers changed.
                                {(s.header_changes.removed || []).length ? ` Removed: ${s.header_changes.removed.join(", ")}.` : ""}
                                {(s.header_changes.added || []).length ? ` Added: ${s.header_changes.added.join(", ")}.` : ""}
                                {" "}Confirm the mapping before import.
                                {s.mapping_confirmed ? null : (
                                  <div style={{ marginTop: 8 }}>
                                    <button type="button" onClick={() => updateSheet(idx, { mapping_confirmed: true })}>Confirm mapping</button>
                                  </div>
                                )}
                              </div>
                            ) : null}
                          </div>
                          <span className={"pill " + (ready ? "ok" : "warn")}>{ready ? "Ready" : "Needs mapping"}</span>
                          <button type="button" className="secondary" onClick={() => setMapSheetIdx(idx)}>Set mapping</button>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ) : null}

              {stepId === "duplicates" ? (
                <div>
                  <h4>Duplicate check keys</h4>
                  <p className="muted">Fields used to detect an existing row. Defaults come from Settings for each type.</p>
                  {included.map((s) => {
                    const idx = sheets.findIndex((x) => x.sheet === s.sheet);
                    const optional = s.type === "items" || s.type === "stock" ? ITEM_ATTR_FIELDS : [];
                    const fields = Array.from(new Set([
                      ...(REQUIRED_FIELDS[s.type] || []),
                      ...optional,
                      ...Object.values(s.column_map || {}).filter((d) => !isSkipDest(d)),
                      ...(s.fields || []),
                    ]));
                    return (
                      <div className="wizard-dup-block" key={s.sheet}>
                        <div className="wizard-dup-head">
                          <strong>{s.sheet}</strong>
                          <span className="muted">{friendlyType(s.type)}</span>
                        </div>
                        <div className="chips">
                          {fields.map((name) => (
                            <button
                              type="button"
                              key={name}
                              className={(s.unique_key || []).includes(name) ? "" : "secondary"}
                              onClick={() => {
                                const cur = s.unique_key || [];
                                const next = cur.includes(name) ? cur.filter((x) => x !== name) : [...cur, name];
                                updateSheet(idx, { unique_key: next });
                              }}
                            >{name}</button>
                          ))}
                        </div>
                        {!(s.unique_key || []).length ? <p className="warn">Select at least one key.</p> : null}
                      </div>
                    );
                  })}
                </div>
              ) : null}

              {stepId === "existing" ? (
                <div>
                  <h4>Existing rows</h4>
                  <p className="muted">
                    For event sheets choose skip, update, replace matching keys, or replace the date period in the file.
                    Outstanding and stock always upsert (set effective date from import when available).
                  </p>
                  {included.map((s) => {
                    const idx = sheets.findIndex((x) => x.sheet === s.sheet);
                    const isSnapshot = s.type === "arr" || s.type === "stock" || s.type === "party";
                    const mode = s.event_mode || "skip";
                    return (
                      <div className="wizard-dup-block" key={s.sheet}>
                        <div className="wizard-dup-head">
                          <strong>{s.sheet}</strong>
                          <span className="muted">{friendlyType(s.type)}</span>
                        </div>
                        {isSnapshot ? (
                          <p className="muted">Always updates matching rows.</p>
                        ) : (
                          <div className="chips">
                            {[
                              ["skip", "Skip existing"],
                              ["update", "Update existing"],
                              ["replace_batch", "Replace matching keys"],
                              ["replace_period", "Replace date period"],
                            ].map(([id, label]) => (
                              <button
                                key={id}
                                type="button"
                                className={mode === id ? "" : "secondary"}
                                onClick={() => updateSheet(idx, { event_mode: id })}
                              >{label}</button>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                  {importResult?.dry_run ? (
                    <div style={{ marginTop: 12 }}>
                      <div className="ok import-summary">
                        <p><strong>Dry-run preview</strong></p>
                        {Object.entries(importResult.types || {}).map(([name, info]) => (
                          <p key={name}>{resultLine(name, info)}</p>
                        ))}
                      </div>
                      <DryRunDetails sheets={importResult.sheets || []} />
                    </div>
                  ) : null}
                  <div className="row gap" style={{ marginTop: 12 }}>
                    <button type="button" className="secondary" disabled={busy} onClick={() => startImport({ dry_run: true })}>
                      Preview changes
                    </button>
                  </div>
                </div>
              ) : null}

              {stepId === "progress" ? (
                <div>
                  <h4>Importing…</h4>
                  <p className="muted">{file?.name}</p>
                  <div className="progress-bar"><span style={{ width: importPct + "%" }} /></div>
                  <div className="export-group">
                    {importSteps.map((row) => (
                      <div className="export-row" key={row.sheet}>
                        <span className="grow">
                          {row.sheet}
                          {row.type ? <span className="muted"> · {friendlyType(row.type)}</span> : null}
                          {row.detail ? <span className="muted"> — {row.detail}</span> : null}
                        </span>
                        <span className={"pill" + (row.state === "failed" ? " err" : row.state === "done" ? " ok" : row.state === "running" ? " warn" : "")}>
                          {stateLabel(row.state)}
                        </span>
                      </div>
                    ))}
                  </div>
                  {err ? <p className="err">{err}</p> : null}
                </div>
              ) : null}

              {stepId === "create" ? (
                <div>
                  <h4>Import finished</h4>
                  {importResult?.types ? (
                    <div className="ok import-summary">
                      {Object.entries(importResult.types).map(([name, info]) => (
                        <p key={name}>{resultLine(name, info)}</p>
                      ))}
                      {importResult.file_sha256 ? (
                        <p className="muted">File SHA-256: {importResult.file_sha256.slice(0, 12)}…</p>
                      ) : null}
                    </div>
                  ) : null}
                  {importResult?.finished_at ? (
                    <p className="muted">Upload finished {formatWhen(importResult.finished_at)}.</p>
                  ) : null}
                  <OnboardingPreview active={Boolean(importResult) && !importResult?.dry_run} reportDate={reportDate} />
                  {run?.status === "succeeded" ? (
                    <RefreshStatus runId={run.id} active />
                  ) : null}
                  {importResult?.upload_id || importResult?.id ? (
                    <p>
                      <button type="button" className="secondary" onClick={undoImport}>
                        Undo this import
                      </button>
                    </p>
                  ) : null}
                  {!anyImported ? (
                    <p className="err">No sheets were imported successfully.</p>
                  ) : (
                    <div className="import-create">
                      <h4>Create official reports?</h4>
                      <p className="muted">Uses all stored rows for the packs you choose. 360 View pages and the home dashboard are saved for the same date: business, customers, groups, sales reps, items, category, item group, brand, and supplier.</p>
                      {settlementSummary ? (
                        <p className="muted">Settlement: {settlementSummary}</p>
                      ) : null}
                      <label>Report date</label>
                      <input type="date" value={reportDate} onChange={(e) => setReportDate(e.target.value)} disabled={creating} />
                      <div className="pack-grid pack-grid-compact">
                        {PACKS.map((p) => (
                          <label className="pack-card" key={p.id}>
                            <h3>
                              <input
                                type="checkbox"
                                disabled={creating}
                                checked={Boolean(packs[p.id])}
                                onChange={(e) => setPacks({ ...packs, [p.id]: e.target.checked })}
                              />{" "}
                              {p.title}
                            </h3>
                            <p className="muted">{p.hint}</p>
                          </label>
                        ))}
                      </div>
                      {creating || progress ? <ReportProgress progress={progress} active={creating || run?.status === "queued" || run?.status === "running"} /> : null}
                      {run?.status === "failed" ? <p className="err">{run.message || "Could not create reports."}</p> : null}
                      {run?.status === "succeeded" ? (
                        <p className={run.message ? "err" : "ok"}>{run.message || "Reports are ready. Open a family in the Reports menu."}</p>
                      ) : null}
                      {createErr ? <p className="err">{createErr}</p> : null}
                    </div>
                  )}
                </div>
              ) : null}
            </div>

            <div className="wizard-foot">
              {stepId !== "progress" && stepId !== "create" && stepId !== "file" ? (
                <button type="button" className="secondary" disabled={busy} onClick={goBack}>Back</button>
              ) : <span />}
              <div className="wizard-foot-right">
                {stepId === "create" && anyImported && run?.status !== "succeeded" ? (
                  <button type="button" disabled={creating} onClick={createReports}>Create reports</button>
                ) : null}
                {stepId === "create" && run?.status === "succeeded" && onGo ? (
                  <button type="button" onClick={() => { setWizardOpen(false); onGo("home", "home"); }}>Done</button>
                ) : null}
                {stepId === "create" ? (
                  <button type="button" className="secondary" disabled={creating} onClick={closeWizard}>Close</button>
                ) : null}
                {stepId === "existing" ? (
                  <button type="button" disabled={!canNext() || busy} onClick={goNext}>Start import</button>
                ) : null}
                {stepId !== "existing" && stepId !== "progress" && stepId !== "create" ? (
                  <button type="button" disabled={!canNext()} onClick={goNext}>Next</button>
                ) : null}
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {mapTarget ? (
        <MappingModal
          sheet={mapTarget}
          onClose={() => setMapSheetIdx(null)}
          onSave={(columnMap) => {
            const dests = new Set();
            (mapTarget.headers || []).forEach((h) => {
              const dest = columnMap[h];
              if (dest === undefined) dests.add(h);
              else if (!isSkipDest(dest)) dests.add(dest);
            });
            const missing = (REQUIRED_FIELDS[mapTarget.type] || []).filter((name) => !dests.has(name));
            updateSheet(mapSheetIdx, {
              column_map: columnMap,
              fields: Array.from(new Set([
                ...(REQUIRED_FIELDS[mapTarget.type] || []),
                ...(mapTarget.type === "items" || mapTarget.type === "stock" ? ITEM_ATTR_FIELDS : []),
                ...Object.values(columnMap).filter((d) => !isSkipDest(d)),
                "Invoice No", "Taxable Amount", "Tax Amount",
              ])),
              mapping_touched: true,
              missing,
              mapping_confirmed: true,
              ready: missing.length === 0,
            });
            setMapSheetIdx(null);
          }}
        />
      ) : null}

      {setupGate ? (
        <div className="modal-backdrop" onClick={() => setSetupGate(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 480 }}>
            <h3>Set up settlement first</h3>
            <p>
              Before creating reports, save a settlement mode and aging bands in Settings.
              Outstanding due uses newest→oldest on unsettled invoices; collections use Opening then
              oldest→newest (or Specific with that remainder).
            </p>
            <div className="row gap" style={{ marginTop: 16, justifyContent: "flex-end" }}>
              <button type="button" className="secondary" onClick={() => setSetupGate(null)}>Cancel</button>
              <button
                type="button"
                onClick={() => {
                  setSetupGate(null);
                  setWizardOpen(false);
                  if (onGo) onGo("settings", "settlement");
                }}
              >
                Open Settings
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
