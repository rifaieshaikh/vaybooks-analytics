import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api";
import { hashSet, money } from "./format";

const GAP_COLORS = ["#1f6b4a", "#3d8f6a", "#6a9e5a", "#c4a35a", "#9f1239"];
const WAIT_COLORS = ["#44403c", "#1f6b4a", "#c4a35a", "#9f1239"];

function days(value) {
  if (value == null || value === "") return "—";
  return String(value);
}

function rangeLabel(period) {
  if (period?.p25 == null || period?.p75 == null) return "—";
  if (period.p25 === period.p75) return period.p25 + " days";
  return period.p25 + "–" + period.p75 + " days";
}

function headline(period, memberAxis) {
  if (period?.median == null) return "No repeat purchase in this period.";
  const between = period.p25 != null && period.p75 != null && period.p25 !== period.p75
    ? " Most come back between " + period.p25 + " and " + period.p75 + " days."
    : "";
  const lead = memberAxis === "customer"
    ? "Customers buy this again after about " + period.median + " days."
    : "Bought again after about " + period.median + " days.";
  return lead + between;
}

function openEntity(kind, uk, name) {
  const id = uk || name;
  if (!id) return;
  hashSet(kind + "/" + encodeURIComponent(id));
}

function NameLink({ kind, uk, name, className = "linkish" }) {
  if (!name && !uk) return "—";
  return (
    <button type="button" className={className} onClick={() => openEntity(kind, uk, name)}>
      {name || uk}
    </button>
  );
}

function sharePct(value, total) {
  const base = Number(total) || 0;
  if (base <= 0) return "0%";
  const pct = ((Number(value) || 0) / base) * 100;
  return pct.toLocaleString(undefined, { maximumFractionDigits: 0 }) + "%";
}

function CountBar({ parts, selected, onSelect, unit }) {
  const rows = parts || [];
  const sum = rows.reduce((total, part) => total + (Number(part.count) || 0), 0);
  const widthBase = sum || 1;

  function toggle(key) {
    if (!onSelect) return;
    onSelect(selected === key ? "" : key);
  }

  return (
    <div>
      <div className="owe-bar">
        {rows.map((part) => (
          <button
            key={part.key}
            type="button"
            className={selected === part.key ? "on" : ""}
            title={part.label + " · " + (part.count || 0) + " " + unit}
            aria-pressed={selected === part.key}
            aria-label={part.label}
            onClick={() => toggle(part.key)}
            style={{
              width: `${((Number(part.count) || 0) / widthBase) * 100}%`,
              background: part.color,
              minWidth: part.count ? 4 : 0,
            }}
          />
        ))}
      </div>
      <div className="legend">
        {rows.map((part) => (
          <button
            key={part.key}
            type="button"
            className={selected === part.key ? "on" : ""}
            aria-pressed={selected === part.key}
            onClick={() => toggle(part.key)}
            style={{ background: part.color, color: "#fff" }}
          >
            {part.label} · {part.count || 0} ({sharePct(part.count, sum)})
          </button>
        ))}
      </div>
    </div>
  );
}

function Between({ rows }) {
  const items = rows || [];
  if (!items.length) return "Nothing else";
  const shown = items.slice(0, 4);
  const extra = items.length - shown.length;
  return (
    <>
      {shown.map((row, index) => (
        <span key={(row.uk || row.name) + index}>
          {index ? ", " : ""}
          <NameLink kind="item" uk={row.uk} name={row.name} />
        </span>
      ))}
      {extra > 0 ? " +" + extra : ""}
    </>
  );
}

function toUtcDay(iso) {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ""));
  if (!match) return null;
  return Date.UTC(+match[1], +match[2] - 1, +match[3]) / 86400000;
}

function formatDay(utcDay) {
  return new Date(utcDay * 86400000).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

function historyBounds(rows, asOf) {
  let min = null;
  let max = null;
  (rows || []).forEach((row) => {
    (row.points || []).forEach((point) => {
      const day = toUtcDay(point.date_iso);
      if (day == null) return;
      if (min == null || day < min) min = day;
      if (max == null || day > max) max = day;
    });
  });
  const end = toUtcDay(asOf);
  if (end != null && (max == null || end > max)) max = end;
  if (min == null || max == null) return null;
  return { min, max };
}

function inWindow(iso, start, end) {
  const day = toUtcDay(iso);
  return day != null && day >= start && day <= end;
}

function pctOfDay(day, windowStart, spanDays) {
  const pct = ((day - windowStart) / Math.max(spanDays, 1)) * 100;
  return Math.min(100, Math.max(0, pct)) + "%";
}

function placePct(iso, windowStart, spanDays) {
  const day = toUtcDay(iso);
  if (day == null) return "0%";
  return pctOfDay(day, windowStart, spanDays);
}

function SeriesTrack({ points, windowStart, windowEnd }) {
  const marks = points || [];
  const span = Math.max(windowEnd - windowStart, 1);
  const visible = marks.some((point) => inWindow(point.date_iso, windowStart, windowEnd));
  if (!visible) return null;
  return (
    <div className="repurchase-plot">
      <div className="repurchase-track">
        {marks.map((point, index) => {
          const prev = index ? marks[index - 1] : null;
          const shown = inWindow(point.date_iso, windowStart, windowEnd);
          const prevShown = prev && inWindow(prev.date_iso, windowStart, windowEnd);
          const gap = point.gap_days;
          const midIso = prev && shown && prevShown ? ((toUtcDay(prev.date_iso) + toUtcDay(point.date_iso)) / 2) : null;
          return (
            <span key={(point.date_iso || "") + "-" + index}>
              {midIso != null && gap != null ? (
                <span
                  className="repurchase-gap"
                  style={{ left: pctOfDay(midIso, windowStart, span) }}
                >
                  {gap}d
                </span>
              ) : null}
              {shown ? (
                <span
                  className="repurchase-dot"
                  title={(point.date_label || "") + (gap == null ? " · First buy" : " · " + gap + " days") + (point.intervene_orders ? " · " + point.intervene_orders + " other orders" : "")}
                  style={{ left: placePct(point.date_iso, windowStart, span) }}
                />
              ) : null}
            </span>
          );
        })}
      </div>
    </div>
  );
}

function historyCopy(kind) {
  if (kind === "item") {
    return "Every item this customer has bought. One mark is a single purchase. The number between marks is the days until that same item was bought again.";
  }
  if (kind === "customer") {
    return "Every customer who bought this. One mark is a single purchase. The number between marks is the days until they bought it again.";
  }
  return "Every customer and item in this view. One mark is a single purchase. The number between marks is the days until that customer bought that item again.";
}

function RowLabel({ row }) {
  if (row.kind === "both") {
    return (
      <span className="repurchase-name">
        <NameLink kind="customer" uk={row.party_uk} name={row.party} />
        <span className="quiet"> · </span>
        <NameLink kind="item" uk={row.item_uk} name={row.item} />
      </span>
    );
  }
  return (
    <NameLink
      className="linkish repurchase-name"
      kind={row.kind === "item" ? "item" : "customer"}
      uk={row.uk}
      name={row.name}
    />
  );
}

function DurationWheel({ min, max, start, end, onChange }) {
  const trackRef = useRef(null);
  useEffect(() => {
    const node = trackRef.current;
    if (!node) return undefined;
    function onWheel(event) {
      event.preventDefault();
      const span = end - start;
      if (span >= max - min) return;
      const raw = event.deltaY || event.deltaX || 0;
      if (!raw) return;
      const step = raw > 0 ? 7 : -7;
      let nextStart = start + step;
      let nextEnd = end + step;
      if (nextStart < min) {
        nextEnd += min - nextStart;
        nextStart = min;
      }
      if (nextEnd > max) {
        nextStart -= nextEnd - max;
        nextEnd = max;
      }
      onChange(nextStart, nextEnd);
    }
    node.addEventListener("wheel", onWheel, { passive: false });
    return () => node.removeEventListener("wheel", onWheel);
  }, [min, max, start, end, onChange]);

  const span = Math.max(max - min, 1);
  const left = ((start - min) / span) * 100;
  const width = ((end - start) / span) * 100;
  return (
    <div className="duration-wheel">
      <span className="duration-date">{formatDay(start)}</span>
      <div className="duration-track" ref={trackRef}>
        <div className="duration-rail" />
        <div className="duration-fill" style={{ left: left + "%", width: width + "%" }} />
        <input
          type="range"
          min={min}
          max={max}
          step={1}
          value={start}
          aria-label="Start date"
          onChange={(event) => {
            const next = Math.min(Number(event.target.value), end);
            onChange(next, end);
          }}
        />
        <input
          type="range"
          min={min}
          max={max}
          step={1}
          value={end}
          aria-label="End date"
          onChange={(event) => {
            const next = Math.max(Number(event.target.value), start);
            onChange(start, next);
          }}
        />
      </div>
      <span className="duration-date">{formatDay(end)}</span>
    </div>
  );
}

function Timeline({ rows, asOf, span, onNearEnd, total }) {
  const bounds = useMemo(() => {
    if (span && span.min != null && span.max != null) return span;
    return historyBounds(rows, asOf);
  }, [rows, asOf, span]);
  const listRef = useRef(null);
  const [windowRows, setWindowRows] = useState({ start: 0, end: 24 });
  const [start, setStart] = useState(() => bounds?.min ?? 0);
  const [end, setEnd] = useState(() => bounds?.max ?? 0);
  const sig = [
    rows.length,
    rows[0]?.party_uk || "",
    rows[0]?.item_uk || "",
    asOf || "",
    bounds?.min ?? "",
    bounds?.max ?? "",
  ].join("|");
  useEffect(() => {
    if (!bounds) return;
    setStart(bounds.min);
    setEnd(bounds.max);
  }, [sig]);

  const shown = useMemo(
    () => (rows || []).filter((row) => (row.points || []).some((point) => inWindow(point.date_iso, start, end))),
    [rows, start, end],
  );
  if (!rows.length || !bounds) return null;
  const daysWide = end - start;
  const kind = rows[0]?.kind;
  const noun = kind === "item" ? "item" : kind === "customer" ? "customer" : "series";
  const counted = (count) => count + " " + noun + (count === 1 || noun === "series" ? "" : "s");
  const duration = daysWide <= 0 ? "Same day" : daysWide === 1 ? "1 day" : daysWide + " days";
  const all = total || rows.length;
  const coverage = shown.length === all ? counted(all) : shown.length + " of " + counted(all);
  const rowHeight = 64;
  const rowStart = Math.max(0, Math.min(windowRows.start, shown.length));
  const rowEnd = Math.max(rowStart, Math.min(windowRows.end, shown.length));
  const visible = shown.slice(rowStart, rowEnd);

  function onListScroll(event) {
    const node = event.currentTarget;
    const nextStart = Math.max(0, Math.floor(node.scrollTop / rowHeight) - 3);
    const nextEnd = Math.min(shown.length, nextStart + Math.ceil(node.clientHeight / rowHeight) + 8);
    setWindowRows((prev) => (prev.start === nextStart && prev.end === nextEnd ? prev : { start: nextStart, end: nextEnd }));
    if (onNearEnd && nextEnd >= shown.length - 6) onNearEnd();
  }

  return (
    <div className="card" style={{ marginTop: 12 }}>
      <h3>Repeat history</h3>
      <p className="muted">{historyCopy(rows[0]?.kind)}</p>
      <DurationWheel
        min={bounds.min}
        max={bounds.max}
        start={start}
        end={end}
        onChange={(nextStart, nextEnd) => {
          setStart(nextStart);
          setEnd(nextEnd);
        }}
      />
      <p className="muted duration-caption">
        {duration} · {coverage}. Scroll the bar to move through history. Drag either side to change the duration.
      </p>
      <div className="repurchase-list" ref={listRef} onScroll={onListScroll} style={{ maxHeight: 480, overflow: "auto" }}>
        {shown.length ? (
          <div style={{ height: shown.length * rowHeight, position: "relative" }}>
            {visible.map((row, index) => (
              <div
                className="repurchase-row"
                key={(row.party_uk || "") + "-" + (row.item_uk || row.uk || row.name)}
                style={{ position: "absolute", top: (rowStart + index) * rowHeight, left: 0, right: 0, height: rowHeight }}
              >
                <div>
                  <RowLabel row={row} />
                  <div className="quiet">{(row.purchases || (row.points || []).length) === 1 ? "Once" : (row.purchases || (row.points || []).length) + " times"}</div>
                </div>
                <SeriesTrack points={row.points} windowStart={start} windowEnd={end} />
              </div>
            ))}
          </div>
        ) : (
          <p className="muted">Nothing in this duration. Widen the wheel or scroll back toward the start.</p>
        )}
      </div>
    </div>
  );
}

function CompanionTable({ rows, empty }) {
  return (
    <div className="table-wrap">
      <table className="dense list-table compact">
        <thead>
          <tr>
            <th>Item</th>
            <th className="num">Orders</th>
            <th className="num">Qty</th>
            <th className="num">Amount</th>
          </tr>
        </thead>
        <tbody>
          {rows.length ? rows.map((row) => (
            <tr key={(row.uk || row.name)}>
              <td><NameLink kind="item" uk={row.uk} name={row.name} /></td>
              <td className="num">{row.times || 0}</td>
              <td className="num">{row.qty || 0}</td>
              <td className="num">{money(row.amount || 0)}</td>
            </tr>
          )) : (
            <tr><td colSpan={4} className="muted">{empty}</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

export default function RepurchasePanel({ detail, entity = "customer", showCustomer = true, showItem = true }) {
  const embedded = detail?.repurchase;
  const [loaded, setLoaded] = useState(null);
  const [timeline, setTimeline] = useState(null);
  const [timelineMeta, setTimelineMeta] = useState(null);
  const [linePack, setLinePack] = useState({});
  const [periodPack, setPeriodPack] = useState({});
  const [loading, setLoading] = useState(false);
  const loadingPage = useRef(false);
  const separate = Boolean(detail?.repurchase_separate) && !embedded;
  useEffect(() => {
    setLoaded(null);
    setTimeline(null);
    setTimelineMeta(null);
    setLinePack({});
    setPeriodPack({});
    loadingPage.current = false;
    if (!separate || !detail?.uk) return undefined;
    let cancelled = false;
    setLoading(true);
    const run = detail.run_id || "";
    api.repurchase(entity, detail.uk, { run })
      .then((row) => {
        if (cancelled) return;
        setLoaded(row);
        if (row?.timeline_separate) {
          loadingPage.current = true;
          api.repurchase(entity, detail.uk, { run, part: "timeline", page: "0" })
            .then((extra) => {
              if (cancelled) return;
              setTimeline(extra?.timeline || []);
              setTimelineMeta({
                page: extra?.page || 0,
                pages: extra?.pages || 0,
                total: extra?.total || 0,
                min: toUtcDay(extra?.min_iso),
                max: toUtcDay(extra?.max_iso),
              });
            })
            .catch(() => { if (!cancelled) setTimeline([]); })
            .finally(() => { loadingPage.current = false; });
        } else {
          setTimeline(row?.timeline || []);
        }
      })
      .catch(() => { if (!cancelled) setLoaded(null); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [separate, entity, detail?.uk, detail?.run_id]);
  const data = embedded || (loaded ? { ...loaded, timeline: timeline || loaded.timeline || [] } : null);
  const years = data?.by_fy || [];
  const months = data?.months || [];
  const yearSig = years.map((row) => row.key).join("|");
  const monthSig = months.map((row) => row.key).join("|");
  const [view, setView] = useState("overall");
  const [fyKey, setFyKey] = useState(years[0]?.key || "");
  const [monthKey, setMonthKey] = useState(months[0]?.key || "");
  const [gapKey, setGapKey] = useState("");
  const [waitKey, setWaitKey] = useState("");

  useEffect(() => {
    setView("overall");
    setFyKey(yearSig.split("|")[0] || "");
    setMonthKey(monthSig.split("|")[0] || "");
    setGapKey("");
    setWaitKey("");
  }, [detail?.uk, yearSig, monthSig]);

  const selectedYear = years.find((row) => row.key === fyKey) || years[0] || data?.fy;
  const selectedMonth = months.find((row) => row.key === monthKey) || months[0] || data?.month;
  const period = !data
    ? null
    : view === "fy"
      ? (selectedYear || { buckets: [], intervene: [], lines: [], orders: 0, value: 0, members: [] })
      : view === "month"
        ? (selectedMonth || { buckets: [], intervene: [], lines: [], orders: 0, value: 0, members: [] })
        : (data.overall || { buckets: [], intervene: [], lines: [], orders: 0, value: 0, members: [] });
  const lineToken = view + ":" + (view === "fy" ? (selectedYear?.key || "") : view === "month" ? (selectedMonth?.key || "") : "overall");
  const fetchedLines = linePack[lineToken];
  const fetchedPeriod = view === "overall" ? null : periodPack[lineToken];
  const shownPeriod = fetchedPeriod ? { ...period, ...fetchedPeriod } : period;
  useEffect(() => {
    if (!separate || !detail?.uk || !period?.lines_separate || period.lines || fetchedLines) return undefined;
    let cancelled = false;
    api.repurchase(entity, detail.uk, {
      run: detail.run_id || "",
      part: "lines",
      period: view,
      key: view === "fy" ? (selectedYear?.key || "") : view === "month" ? (selectedMonth?.key || "") : "overall",
    })
      .then((row) => {
        if (!cancelled) setLinePack((prev) => ({ ...prev, [lineToken]: row?.lines || [] }));
      })
      .catch(() => {
        if (!cancelled) setLinePack((prev) => ({ ...prev, [lineToken]: [] }));
      });
    return () => { cancelled = true; };
  }, [separate, entity, detail?.uk, detail?.run_id, view, lineToken, period?.lines_separate, fetchedLines]);
  useEffect(() => {
    if (!separate || !detail?.uk || view === "overall" || !period || period.buckets || fetchedPeriod) return undefined;
    let cancelled = false;
    api.repurchase(entity, detail.uk, {
      run: detail.run_id || "",
      part: "period",
      period: view,
      key: view === "fy" ? (selectedYear?.key || "") : (selectedMonth?.key || ""),
    })
      .then((row) => {
        if (!cancelled) setPeriodPack((prev) => ({ ...prev, [lineToken]: row?.period || {} }));
      })
      .catch(() => {
        if (!cancelled) setPeriodPack((prev) => ({ ...prev, [lineToken]: {} }));
      });
    return () => { cancelled = true; };
  }, [separate, entity, detail?.uk, detail?.run_id, view, lineToken, period, fetchedPeriod, selectedYear, selectedMonth]);

  if (loading && !data) {
    return (
      <div className="card">
        <h3>Repurchase</h3>
        <p className="muted">Loading repeat purchases…</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="card">
        <h3>Repurchase</h3>
        <p className="muted">This snapshot was saved before repeat purchases were stored. Open Snapshot at the top and choose the latest report. Two reports from the same day are listed with their times.</p>
      </div>
    );
  }

  const activePeriod = shownPeriod || period;
  let historySpan = null;
  if (timelineMeta && timelineMeta.min != null && timelineMeta.max != null) {
    const asOfDay = toUtcDay(data.as_of || detail?.as_of);
    historySpan = {
      min: timelineMeta.min,
      max: asOfDay != null && asOfDay > timelineMeta.max ? asOfDay : timelineMeta.max,
    };
  }
  function loadMoreHistory() {
    if (!separate || !detail?.uk || loadingPage.current || !timelineMeta) return;
    const next = (timelineMeta.page || 0) + 1;
    if (next >= (timelineMeta.pages || 0)) return;
    loadingPage.current = true;
    api.repurchase(entity, detail.uk, {
      run: detail.run_id || "",
      part: "timeline",
      page: String(next),
    })
      .then((extra) => {
        setTimeline((prev) => (prev || []).concat(extra?.timeline || []));
        setTimelineMeta((prev) => ({ ...(prev || {}), page: extra?.page ?? next, pages: extra?.pages ?? prev?.pages }));
      })
      .finally(() => { loadingPage.current = false; });
  }
  const lines = (fetchedLines || activePeriod.lines || []).filter((row) => (!gapKey || row.bucket === gapKey) && (!waitKey || row.intervene === waitKey));
  const members = activePeriod.members || [];
  const memberAxis = data.member_axis === "item" ? "item" : "customer";
  const colSpan = 5 + (showCustomer ? 1 : 0) + (showItem ? 1 : 0);

  return (
    <div>
      <div className="card">
        <h3>Repurchase</h3>
        <p>{headline(activePeriod, memberAxis)}</p>
        <div className="buy-tiles" style={{ marginTop: 12 }}>
          <div className="card buy-tile">
            <span className="muted">Bought again</span>
            <strong>{activePeriod.orders || 0}</strong>
          </div>
          <div className="card buy-tile">
            <span className="muted">Usual gap</span>
            <strong>{activePeriod.median == null ? "—" : activePeriod.median + " days"}</strong>
          </div>
          <div className="card buy-tile">
            <span className="muted">Most gaps fall between</span>
            <strong>{rangeLabel(activePeriod)}</strong>
          </div>
          <div className="card buy-tile">
            <span className="muted">Bought only once</span>
            <strong>{data.once || 0}</strong>
            <span className="quiet">All time</span>
          </div>
        </div>
        {data.timeline_separate && timeline == null ? (
          <p className="muted" style={{ marginTop: 12 }}>Loading repeat history…</p>
        ) : (
          <Timeline
            rows={data.timeline || []}
            asOf={data.as_of || detail?.as_of}
            span={historySpan}
            total={timelineMeta?.total || (data.timeline || []).length}
            onNearEnd={loadMoreHistory}
          />
        )}
        <div className="chips" style={{ marginTop: 12 }}>
          <button type="button" className={view === "overall" ? "" : "secondary"} onClick={() => { setView("overall"); setGapKey(""); setWaitKey(""); }}>Overall</button>
          <button type="button" className={view === "fy" ? "" : "secondary"} onClick={() => { setView("fy"); setGapKey(""); setWaitKey(""); }} disabled={!years.length && !data.fy}>Fiscal year</button>
          <button type="button" className={view === "month" ? "" : "secondary"} onClick={() => { setView("month"); setGapKey(""); setWaitKey(""); }} disabled={!months.length && !data.month}>Month</button>
        </div>
        {view === "fy" && years.length ? (
          <div className="card-head" style={{ alignItems: "center", gap: 12, flexWrap: "wrap", marginTop: 12 }}>
            <h4 className="quiet" style={{ margin: 0 }}>Fiscal year</h4>
            <select value={selectedYear?.key || ""} onChange={(e) => { setFyKey(e.target.value); setGapKey(""); setWaitKey(""); }} aria-label="Fiscal year">
              {years.map((row) => (
                <option key={row.key} value={row.key}>{row.label} · {row.orders || 0} bought again</option>
              ))}
            </select>
          </div>
        ) : null}
        {view === "month" && months.length ? (
          <div className="card-head" style={{ alignItems: "center", gap: 12, flexWrap: "wrap", marginTop: 12 }}>
            <h4 className="quiet" style={{ margin: 0 }}>Month</h4>
            <select value={selectedMonth?.key || ""} onChange={(e) => { setMonthKey(e.target.value); setGapKey(""); setWaitKey(""); }} aria-label="Month">
              {months.map((row) => (
                <option key={row.key} value={row.key}>{row.label} · {row.orders || 0} bought again</option>
              ))}
            </select>
          </div>
        ) : null}
        <div style={{ marginTop: 16 }}>
          <h4 className="quiet">How long until the same item is bought again</h4>
          <CountBar
            unit="repeats"
            parts={(activePeriod.buckets || []).map((bucket, index) => ({
              key: bucket.key,
              label: bucket.label || bucket.key,
              count: Number(bucket.count) || 0,
              color: GAP_COLORS[index % GAP_COLORS.length],
            }))}
            selected={gapKey}
            onSelect={setGapKey}
          />
        </div>
        <div style={{ marginTop: 16 }}>
          <h4 className="quiet">Other orders in that gap</h4>
          <CountBar
            unit="repeats"
            parts={(activePeriod.intervene || []).map((bucket, index) => ({
              key: bucket.key,
              label: bucket.label || bucket.key,
              count: Number(bucket.count) || 0,
              color: WAIT_COLORS[index % WAIT_COLORS.length],
            }))}
            selected={waitKey}
            onSelect={setWaitKey}
          />
        </div>
        <div className="table-wrap" style={{ marginTop: 8 }}>
          <table className="dense list-table compact">
            <thead>
              <tr>
                <th>From</th>
                <th>Again</th>
                {showCustomer ? <th>Customer</th> : null}
                {showItem ? <th>Item</th> : null}
                <th className="num">Gap</th>
                <th>In between</th>
                <th className="num">Amount</th>
              </tr>
            </thead>
            <tbody>
              {activePeriod.lines_separate && fetchedLines == null ? (
                <tr>
                  <td colSpan={colSpan} className="muted">Loading repeats…</td>
                </tr>
              ) : lines.length ? lines.map((row, index) => (
                <tr key={(row.date_iso || "") + "-" + (row.party_uk || "") + "-" + (row.item_uk || "") + "-" + index}>
                  <td>{row.prev_label || "—"}</td>
                  <td>
                    {row.invoice_id ? (
                      <button type="button" className="linkish" onClick={() => hashSet("invoice/" + encodeURIComponent(row.invoice_id))}>
                        {row.date_label || "Sale"}
                      </button>
                    ) : (row.date_label || "—")}
                  </td>
                  {showCustomer ? <td><NameLink kind="customer" uk={row.party_uk} name={row.party} /></td> : null}
                  {showItem ? <td><NameLink kind="item" uk={row.item_uk} name={row.item} /></td> : null}
                  <td className="num">{row.gap_days == null ? "—" : row.gap_days + " days"}</td>
                  <td><Between rows={row.between} /></td>
                  <td className="num">{money(row.amount || 0)}</td>
                </tr>
              )) : (
                <tr>
                  <td colSpan={colSpan} className="muted">No repeat purchases in this period.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        {activePeriod.lines_truncated ? (
          <p className="muted" style={{ marginTop: 8 }}>Showing the latest 200.</p>
        ) : null}
      </div>

      <div className="buy-grid" style={{ marginTop: 12 }}>
        <div className="card">
          <h3>Bought while waiting</h3>
          <p className="muted">Other items ordered on days between two purchases of the same item.</p>
          <CompanionTable rows={activePeriod.wait_items || []} empty="No other items in these gaps." />
        </div>
        <div className="card">
          <h3>Bought the same day</h3>
          <p className="muted">Other items on the day the item was bought again.</p>
          <CompanionTable rows={activePeriod.same_day_items || []} empty="No other items on those days." />
        </div>
      </div>

      <div className="card" style={{ marginTop: 12 }}>
        <h3>{memberAxis === "item" ? "Items" : "Customers"}</h3>
        <div className="table-wrap">
          <table className="dense list-table compact">
            <thead>
              <tr>
                <th>{memberAxis === "item" ? "Item" : "Customer"}</th>
                <th className="num">Bought again</th>
                <th className="num">Usual gap</th>
                <th className="num">Most gaps fall between</th>
                <th className="num">Amount</th>
              </tr>
            </thead>
            <tbody>
              {members.length ? members.map((row) => (
                <tr key={row.uk || row.name}>
                  <td><NameLink kind={memberAxis === "item" ? "item" : "customer"} uk={row.uk} name={row.name} /></td>
                  <td className="num">{row.cycles || 0}</td>
                  <td className="num">{row.median == null ? "—" : row.median + " days"}</td>
                  <td className="num">{rangeLabel(row)}</td>
                  <td className="num">{money(row.value || 0)}</td>
                </tr>
              )) : (
                <tr><td colSpan={5} className="muted">No repeat purchases in this period.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card" style={{ marginTop: 12 }}>
        <h3>Due to buy again</h3>
        <p className="muted">Last purchase is older than that customer’s usual gap for this item.</p>
        <div className="table-wrap">
          <table className="dense list-table compact">
            <thead>
              <tr>
                <th>Customer</th>
                <th>Item</th>
                <th>Last bought</th>
                <th className="num">Days since</th>
                <th className="num">Usually every</th>
              </tr>
            </thead>
            <tbody>
              {(data.overdue || []).length ? data.overdue.map((row) => (
                <tr key={(row.party_uk || "") + "-" + (row.item_uk || "")}>
                  <td><NameLink kind="customer" uk={row.party_uk} name={row.party} /></td>
                  <td><NameLink kind="item" uk={row.item_uk} name={row.item} /></td>
                  <td>{row.last_label || "—"}</td>
                  <td className="num">{days(row.days_since)}</td>
                  <td className="num">{row.median == null ? "—" : row.median + " days"}</td>
                </tr>
              )) : (
                <tr><td colSpan={5} className="muted">Nobody is past their usual gap.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
