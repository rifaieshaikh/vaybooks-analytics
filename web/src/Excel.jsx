import { api } from "./api";
import { EmptyCard } from "./FilterBar";

export default function ExcelPage({ run }) {
  const ready = run?.status === "succeeded";

  if (!ready) {
    return (
      <EmptyCard
        title="Create reports first"
        copy="Excel downloads the filtered workbook for the current report snapshot after a run succeeds."
      />
    );
  }

  return (
    <div className="workspace-page">
      <div className="page-head">
        <div className="page-head-copy">
          <h2>Excel</h2>
          <p className="muted">
            Workbook for {run.report_date}
            {run.fy_label ? " · " + run.fy_label : ""}. Sheets match the reports you can view.
          </p>
        </div>
        <button type="button" className="secondary" onClick={() => api.downloadRun(run.id)}>
          Download Excel
        </button>
      </div>
      <div className="card">
        <p className="muted">
          Download includes only sheets you have permission to see. Switch the snapshot in the top bar to export a different run.
        </p>
        <button type="button" onClick={() => api.downloadRun(run.id)}>Download Excel</button>
      </div>
    </div>
  );
}
