import { useMemo, useState } from "react";

export function stateLabel(state) {
  if (state === "waiting") return "Waiting";
  if (state === "running") return "In progress";
  if (state === "done") return "Success";
  if (state === "failed") return "Failed";
  return state || "";
}

export function progressStats(progress) {
  const steps = progress?.steps || [];
  const total = progress?.total || steps.length || 0;
  const done = progress?.done || steps.filter((row) => row.state === "done" || row.state === "failed").length;
  const fraction = Math.max(0, Math.min(0.99, Number(progress?.fraction) || 0));
  const pct = total ? Math.min(100, Math.round(((done + fraction) / total) * 100)) : 0;
  const failed = steps.filter((row) => row.state === "failed");
  const succeeded = steps.filter((row) => row.state === "done");
  return { steps, total, done, pct, failed, succeeded };
}

function groupKind(rows) {
  if (rows.some((row) => row.state === "running")) return "running";
  if (rows.some((row) => row.state === "failed")) return "failed";
  if (rows.length && rows.every((row) => row.state === "done")) return "done";
  if (rows.every((row) => !row.state || row.state === "waiting")) return "waiting";
  return "mixed";
}

function defaultOpen(variant, rows) {
  const kind = groupKind(rows);
  if (variant === "full") return true;
  if (variant === "live") return kind === "running" || kind === "failed" || kind === "mixed";
  return kind === "failed" || kind === "mixed";
}

function groupSummary(rows) {
  const kind = groupKind(rows);
  const failed = rows.filter((row) => row.state === "failed").length;
  const succeeded = rows.filter((row) => row.state === "done").length;
  if (kind === "waiting") return "Waiting";
  if (kind === "running") return "In progress";
  if (kind === "done") return succeeded + " succeeded";
  if (failed && succeeded) return succeeded + " succeeded · " + failed + " failed";
  if (failed) return failed + " failed";
  return "";
}

export default function ReportProgress({ progress, active, variant = "full", note = "" }) {
  const { steps, total, done, pct, failed } = progressStats(progress);
  const [opened, setOpened] = useState({});
  const groups = useMemo(() => {
    const by = {};
    steps.forEach((row) => {
      const key = row.group || "Reports";
      if (!by[key]) by[key] = [];
      by[key].push(row);
    });
    return Object.entries(by);
  }, [steps]);
  if (!steps.length && active) {
    return <p className="muted">Creating reports…</p>;
  }
  if (!steps.length) return null;
  const current = steps.find((row) => row.id === progress?.current);
  const compact = variant === "live" || variant === "result";
  return (
    <div className="create-progress">
      <div className="muted">
        {active && current?.title ? "Working on " + current.title : (failed.length ? failed.length + " failed" : "Finished")}
        {total ? " · " + done + " of " + total : ""}
        {note ? " · " + note : ""}
      </div>
      <div className="progress-bar"><span style={{ width: (active ? pct : (failed.length ? pct : 100)) + "%" }} /></div>
      {groups.map(([name, rows]) => {
        const open = name in opened ? opened[name] : defaultOpen(variant, rows);
        return (
          <div className="export-group" key={name}>
            {compact ? (
              <button
                type="button"
                className="export-group-head create-group-toggle"
                onClick={() => setOpened((prev) => ({ ...prev, [name]: !open }))}
              >
                <h4>{name}</h4>
                <span className="muted">{open ? "Hide" : groupSummary(rows)}</span>
              </button>
            ) : (
              <div className="export-group-head"><h4>{name}</h4></div>
            )}
            {open ? rows.map((row) => (
              <div key={row.id}>
                <div className="export-row">
                  <span className="grow">{row.title}</span>
                  {stateLabel(row.state) ? (
                    <span className={"pill" + (row.state === "failed" ? " err" : row.state === "done" ? " ok" : row.state === "running" ? " warn" : "")}>
                      {stateLabel(row.state)}
                    </span>
                  ) : null}
                </div>
                {row.state === "failed" && row.message ? <p className="err">{row.message}</p> : null}
              </div>
            )) : null}
          </div>
        );
      })}
    </div>
  );
}
