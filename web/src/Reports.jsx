import { useEffect, useMemo, useState } from "react";
import Charts from "./Charts";
import { formatReportCell } from "./format";
import { EmptyCard, FilterBar, SortTh, toggleSort } from "./FilterBar";
import {
  findFollowup,
  followupGroups,
  fyBlocks,
  isWide,
  profitRan,
  reportsInGroup,
  sliceRows,
  sortReportRows,
  uniqueById,
  uniqueCol,
} from "./reportUtils";

const LEGEND = {
  sales: [
    ["#f4cccc", "Urgent"],
    ["#fff2cc", "Follow up"],
    ["#ead1dc", "Newly inactive"],
    ["#d9d9d9", "Dormant"],
  ],
  collection: [
    ["#f4cccc", "Urgent"],
    ["#fff2cc", "Follow up"],
    ["#cfe2f3", "Watch"],
  ],
};

function hasCol(headers, name) {
  return (headers || []).includes(name);
}

function kpisFrom(headers, rows) {
  const total = (rows || []).find((r) => String(r[0] || "").trim().toLowerCase() === "total");
  if (!total) return [];
  const out = [];
  headers.forEach((h, i) => {
    if (i === 0) return;
    const raw = total[i];
    if (raw === "" || raw == null) return;
    const n = Number(String(raw).replace(/,/g, ""));
    if (!Number.isFinite(n) && String(raw).length > 24) return;
    out.push({ label: h, value: formatReportCell(raw, h) });
  });
  return out.slice(0, 8);
}

const emptyFilters = {
  report: "",
  kind: "",
  followGroup: "",
  year: "",
  name: "",
  group: "",
  rep: "",
  account: "",
  item: "",
  status: "",
};

export default function ReportsPage({ run, family }) {
  const reports = run?.snapshot?.reports || [];
  const [filters, setFilters] = useState(emptyFilters);
  const [sort, setSort] = useState("");
  const [dir, setDir] = useState("asc");

  useEffect(() => {
    setFilters(emptyFilters);
    setSort("");
    setDir("asc");
  }, [family, run?.id]);

  const ready = run?.status === "succeeded";
  const inGroup = reportsInGroup(reports, family);
  const salesGs = followupGroups(reports, "sales");
  const collGs = followupGroups(reports, "collection");
  const familyPresent = family === "Follow-up" ? Boolean(salesGs.length || collGs.length) : inGroup.length > 0;

  const report = useMemo(() => {
    if (family === "Follow-up") {
      const kind = filters.kind === "Collections" || (!salesGs.length && collGs.length) ? "collection" : "sales";
      const names = kind === "sales" ? salesGs : collGs;
      const gname = filters.followGroup || names[0];
      return findFollowup(reports, kind, gname);
    }
    const list = uniqueById(inGroup);
    return list.find((r) => r.friendly_title === filters.report) || list[0];
  }, [family, filters.kind, filters.followGroup, filters.report, reports, inGroup, salesGs, collGs]);

  const blocks = report && isWide(report) ? fyBlocks(report) : [];
  const idx = blocks.findIndex((b) => b.title === filters.year);
  const activeBlock = blocks.length ? blocks[idx >= 0 ? idx : blocks.length - 1] : null;

  const displayHeaders = activeBlock ? activeBlock.names : (report?.headers || []);
  const displayRowsRaw = activeBlock ? activeBlock.data : (report ? [...(report.rows || []), ...(report.total ? [report.total] : [])] : []);
  const sliced = report
    ? sliceRows(
        { ...report, headers: displayHeaders, rows: displayRowsRaw, total: null },
        { query: filters.name, group: filters.group, rep: filters.rep, account: filters.account, item: filters.item, status: filters.status },
      )
    : [];
  const sorted = sort ? sortReportRows(sliced, displayHeaders, sort, dir) : sliced;

  const nameHeader = report?.id === "source_data_warnings" && hasCol(displayHeaders, "Key") ? "Key" : displayHeaders[report?.key_col || 0];
  const options = {
    report: uniqueById(inGroup).map((r) => r.friendly_title),
    kind: [salesGs.length ? "Sales" : null, collGs.length ? "Collections" : null].filter(Boolean),
    followGroup: (filters.kind === "Collections" || (!salesGs.length && collGs.length) ? collGs : salesGs),
    year: blocks.map((b) => b.title),
    name: uniqueCol(displayRowsRaw, displayHeaders, nameHeader),
    group: uniqueCol(displayRowsRaw, displayHeaders, "Group"),
    rep: uniqueCol(displayRowsRaw, displayHeaders, "Sales Rep"),
    account: uniqueCol(displayRowsRaw, displayHeaders, hasCol(displayHeaders, "Account Name") ? "Account Name" : "Customer"),
    item: uniqueCol(displayRowsRaw, displayHeaders, "Item Name"),
    status: uniqueCol(displayRowsRaw, displayHeaders, hasCol(displayHeaders, "Status") ? "Status" : "Stock Status"),
  };

  const filterFields = [];
  if (family === "Follow-up") {
    if (salesGs.length && collGs.length) filterFields.push({ key: "kind", label: "Kind" });
    filterFields.push({ key: "followGroup", label: "Group" });
  } else if (options.report.length > 1) {
    filterFields.push({ key: "report", label: "Report" });
  }
  if (blocks.length) filterFields.push({ key: "year", label: "Year" });
  if (nameHeader) {
    const nameLabel = nameHeader === "Account Name" || nameHeader === "Customer" ? "Account" : nameHeader === "Item Name" ? "Item" : nameHeader === "Sales Rep" ? "Salesperson" : nameHeader;
    filterFields.push({ key: "name", label: nameLabel });
  }
  if (hasCol(displayHeaders, "Group") && family !== "Follow-up" && nameHeader !== "Group") filterFields.push({ key: "group", label: "Group" });
  if (hasCol(displayHeaders, "Sales Rep") && nameHeader !== "Sales Rep") filterFields.push({ key: "rep", label: "Salesperson" });
  if ((hasCol(displayHeaders, "Account Name") || hasCol(displayHeaders, "Customer")) && nameHeader !== "Account Name" && nameHeader !== "Customer") filterFields.push({ key: "account", label: "Account" });
  if (hasCol(displayHeaders, "Item Name") && nameHeader !== "Item Name") filterFields.push({ key: "item", label: "Item" });
  if ((hasCol(displayHeaders, "Status") || hasCol(displayHeaders, "Stock Status")) && nameHeader !== "Status" && nameHeader !== "Stock Status") filterFields.push({ key: "status", label: "Status" });

  if (!ready) {
    return <EmptyCard title="Create reports first" copy="Analytics stay off until a run succeeds." />;
  }
  if (family === "Profit" && !profitRan(reports)) {
    return <EmptyCard title="Profit was not included" copy="Select the Profit pack and create again." />;
  }
  if (!familyPresent) {
    return <EmptyCard title="This family is not in the last run" copy="Create reports first." />;
  }

  const followKindActual = filters.kind === "Collections" || (!salesGs.length && collGs.length) ? "collection" : "sales";
  const kpis = kpisFrom(displayHeaders, sorted);

  function onSort(id) {
    const next = toggleSort(sort, dir, id, []);
    setSort(next.sort);
    setDir(next.dir);
  }

  return (
    <div className="workspace-page">
      <div className="page-head">
        <div className="page-head-copy">
          <h2>{family}</h2>
          <p className="muted">Showing {run.report_date}{run.fy_label ? " · " + run.fy_label : ""}</p>
          {run?.manifest?.reconciliation && run.manifest.reconciliation.status !== "unavailable" ? (
            <p className={run.manifest.reconciliation.status === "pass" ? "ok" : "err"}>
              Reconciliation: {run.manifest.reconciliation.status}
              {run.manifest.reconciliation.message ? " — " + run.manifest.reconciliation.message : ""}
            </p>
          ) : null}
          {run?.manifest?.eligibility?.ar_balance?.status === "unavailable" && (family === "Performance" || family === "Follow-up") ? (
            <p className="muted">
              {run.manifest.eligibility.ar_balance.reason}
              {run.manifest.eligibility.ar_balance.as_of ? " Snapshot dated " + run.manifest.eligibility.ar_balance.as_of + "." : ""}
            </p>
          ) : null}
          {run?.manifest?.eligibility?.stock_cover_days?.status === "unavailable" && family === "Items" ? (
            <p className="muted">
              {run.manifest.eligibility.stock_cover_days.reason}
              {run.manifest.eligibility.stock_cover_days.as_of ? " Snapshot dated " + run.manifest.eligibility.stock_cover_days.as_of + "." : ""}
            </p>
          ) : null}
          {run?.manifest ? (
            <details className="muted">
              <summary>Why these numbers?</summary>
              {run.manifest.calculation_version?.metrics ? (
                <ul>
                  {Object.entries(run.manifest.calculation_version.metrics).map(([id, ver]) => (
                    <li key={id}>{id} v{ver}</li>
                  ))}
                </ul>
              ) : null}
              <pre style={{ whiteSpace: "pre-wrap", fontSize: 12 }}>
                {JSON.stringify({
                  report_date: run.manifest.report_date,
                  data_version: run.manifest.data_version,
                  calculation_version: run.manifest.calculation_version,
                  eligibility: run.manifest.eligibility,
                  reconciliation: run.manifest.reconciliation,
                }, null, 2)}
              </pre>
            </details>
          ) : null}
        </div>
      </div>
      {kpis.length ? (
        <div className="kpis">
          {kpis.map((k) => (
            <div className="kpi" key={k.label}>
              <div className="label">{k.label}</div>
              <div className="value">{k.value}</div>
            </div>
          ))}
        </div>
      ) : null}
      <FilterBar filters={filters} options={options} onChange={setFilters} fields={filterFields} />
      {family === "Follow-up" ? (
        <div className="legend">
          {LEGEND[followKindActual === "collection" ? "collection" : "sales"].map(([c, l]) => <span key={l} style={{ background: c }}>{l}</span>)}
        </div>
      ) : null}
      {report ? (
        <div className="card table-card list-panel">
          <div className="table-card-head">
            <h3>{report.friendly_title}</h3>
            <span className="muted">{sorted.length} {sorted.length === 1 ? "row" : "rows"}</span>
          </div>
          <div className="table-wrap">
            <table className="dense list-table">
              <thead>
                <tr>
                  {displayHeaders.map((h) => (
                    <SortTh key={h} id={h} label={h} sort={sort} dir={dir} onSort={onSort} />
                  ))}
                </tr>
              </thead>
              <tbody>
                {sorted.map((row, i) => (
                  <tr key={i} className={String(row[0] || "").toLowerCase() === "total" ? "total" : ""}>
                    {row.map((c, j) => <td key={j}>{formatReportCell(c, displayHeaders[j])}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
      <Charts report={report} rows={sorted} fyTitle={activeBlock?.title} allReports={reports} />
    </div>
  );
}
