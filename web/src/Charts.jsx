import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import {
  Bar,
  BarChart,
  Brush,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { money } from "./format";
import { isWide, num, profitRan } from "./reportUtils";
import { CHART } from "./theme";

function ChartCanvas({ data, bars, lines, stacked, zoom }) {
  const Chart = lines?.length ? LineChart : BarChart;
  return (
    <ResponsiveContainer>
      <Chart data={data} margin={{ top: 8, right: 12, left: 0, bottom: zoom ? 8 : 0 }}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="name" interval={0} angle={-25} textAnchor="end" height={70} />
        <YAxis width={72} tickFormatter={(v) => money(v)} />
        <Tooltip formatter={(v) => money(v)} />
        <Legend />
        {(bars || []).map((b) => (
          <Bar
            key={b.key}
            dataKey={b.key}
            name={b.name}
            fill={b.fill}
            stackId={stacked ? (b.stackId || "stack") : undefined}
          />
        ))}
        {(lines || []).map((line) => (
          <Line
            key={line.key}
            type="monotone"
            dataKey={line.key}
            name={line.name}
            stroke={line.fill || CHART.accent}
            strokeWidth={2}
            dot={{ r: 3 }}
          />
        ))}
        {zoom && data.length > 2 ? (
          <Brush dataKey="name" height={28} stroke={CHART.accent} travellerWidth={10} />
        ) : null}
      </Chart>
    </ResponsiveContainer>
  );
}

export function ChartBox({ title, data, bars, lines, stacked, compact }) {
  const [open, setOpen] = useState(false);
  const [brushKey, setBrushKey] = useState(0);

  useEffect(() => {
    if (!open) return undefined;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    function onKey(e) {
      if (e.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (!data.length) return null;

  const dialog = open ? (
    <div className="modal-backdrop chart-backdrop" onClick={() => setOpen(false)}>
      <div
        className="modal chart-modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="chart-modal-head">
          <h3>{title}</h3>
          <div className="chart-modal-actions">
            <button type="button" className="ghost" onClick={() => setBrushKey((k) => k + 1)}>Reset zoom</button>
            <button type="button" className="ghost" onClick={() => setOpen(false)} aria-label="Close">×</button>
          </div>
        </div>
        <p className="muted chart-zoom-hint">Drag the brush below the chart to zoom a range.</p>
        <div className="chart-box chart-box-expanded" key={brushKey}>
          <ChartCanvas data={data} bars={bars} lines={lines} stacked={stacked} zoom />
        </div>
      </div>
    </div>
  ) : null;

  return (
    <div className="card">
      <div className="chart-card-head">
        <h3>{title}</h3>
        <button type="button" className="ghost chart-expand" onClick={() => { setBrushKey(0); setOpen(true); }}>
          Expand
        </button>
      </div>
      <div className={"chart-box" + (compact ? " compact" : "")}>
        <ChartCanvas data={data} bars={bars} lines={lines} stacked={stacked} zoom={data.length > 8} />
      </div>
      {dialog && typeof document !== "undefined" ? createPortal(dialog, document.body) : null}
    </div>
  );
}

function col(headers, name) {
  return headers.indexOf(name);
}

export default function Charts({ report, rows, fyTitle, allReports }) {
  if (!report) return null;
  const headers = report.headers || [];
  const id = report.id || "";

  if (id === "sales_rep_performance_report") {
    const data = rows.filter((r) => String(r[0]).toLowerCase() !== "total").map((r) => ({
      name: r[0],
      mtdSales: num(r[col(headers, "MTD Sales")]),
      mtdColl: num(r[col(headers, "MTD Collection")]),
      d15Sales: num(r[col(headers, "15 Days Sales")]),
      d15Coll: num(r[col(headers, "15 Days Collection")]),
      ytdSales: num(r[col(headers, "YTD Sales")]),
      ytdColl: num(r[col(headers, "YTD Collection")]),
    }));
    return (
      <>
        <ChartBox title="MTD sales vs collection by person" data={data} bars={[{ key: "mtdSales", name: "MTD Sales", fill: CHART.sales }, { key: "mtdColl", name: "MTD Collection", fill: CHART.collection }]} />
        <ChartBox title="15 days sales vs collection by person" data={data} bars={[{ key: "d15Sales", name: "15 Days Sales", fill: CHART.sales }, { key: "d15Coll", name: "15 Days Collection", fill: CHART.collection }]} />
        <ChartBox title="YTD sales vs collection by person" data={data} bars={[{ key: "ytdSales", name: "YTD Sales", fill: CHART.sales }, { key: "ytdColl", name: "YTD Collection", fill: CHART.collection }]} />
      </>
    );
  }

  if (id === "group_performance_report") {
    const data = rows.filter((r) => String(r[0]).toLowerCase() !== "total").map((r) => ({
      name: r[0],
      mtdSales: num(r[col(headers, "MTD Sales")]),
      mtdColl: num(r[col(headers, "MTD Collection")]),
      ytdSales: num(r[col(headers, "YTD Sales")]),
      ytdColl: num(r[col(headers, "YTD Collection")]),
    }));
    return (
      <>
        <ChartBox title="MTD sales vs collection by group" data={data} bars={[{ key: "mtdSales", name: "MTD Sales", fill: CHART.sales }, { key: "mtdColl", name: "MTD Collection", fill: CHART.collection }]} />
        <ChartBox title="YTD sales vs collection by group" data={data} bars={[{ key: "ytdSales", name: "YTD Sales", fill: CHART.sales }, { key: "ytdColl", name: "YTD Collection", fill: CHART.collection }]} />
      </>
    );
  }

  if (id.startsWith("sales_follow_up_") || id.startsWith("collection_follow_up_")) {
    const counts = {};
    rows.forEach((r) => {
      const st = String(r[col(headers, "Status")] || "—");
      counts[st] = (counts[st] || 0) + 1;
    });
    const data = Object.keys(counts).map((name) => ({ name, count: counts[name] }));
    return <ChartBox title="Follow-up status counts" data={data} bars={[{ key: "count", name: "Count", fill: CHART.accent }]} />;
  }

  if (isWide(report) && (id.startsWith("fiscal_monthly_") || id === "item_wise_monthly_qty" || id === "monthly_profit_report")) {
    const pair = report.wide === "pair";
    const labelCols = report.label_cols || 1;
    const monthNames = headers.slice(labelCols);
    if (pair) {
      const data = [];
      for (let i = 0; i < monthNames.length - 2; i += 2) {
        const name = String(monthNames[i] || "").replace(" Sales", "");
        let sales = 0;
        let coll = 0;
        rows.forEach((row) => {
          if (String(row[0]).toLowerCase() === "total") return;
          sales += num(row[labelCols + i]);
          coll += num(row[labelCols + i + 1]);
        });
        if (name.toLowerCase().includes("total")) continue;
        data.push({ name, sales, coll });
      }
      return <ChartBox title={"Monthly sales and collection — " + (fyTitle || "")} data={data} bars={[{ key: "sales", name: "Sales", fill: CHART.sales }, { key: "coll", name: "Collection", fill: CHART.collection }]} />;
    }
    const data = [];
    monthNames.forEach((name, i) => {
      if (String(name).toLowerCase() === "total") return;
      let v = 0;
      rows.forEach((row) => {
        if (String(row[0]).toLowerCase() === "total") return;
        v += num(row[labelCols + i]);
      });
      data.push({ name, value: v });
    });
    const title = id === "monthly_profit_report" ? "P&L monthly" : id === "item_wise_monthly_qty" ? "Item qty by month" : "Monthly";
    if (id === "monthly_profit_report" && !profitRan(allReports || [])) return null;
    return <ChartBox title={title + (fyTitle ? " — " + fyTitle : "")} data={data} bars={[{ key: "value", name: "Amount", fill: CHART.accent }]} />;
  }

  if (id === "expense_by_category") {
    if (!profitRan(allReports || [])) return null;
    const data = rows.filter((r) => String(r[0]).toLowerCase() !== "total").map((r) => ({
      name: r[0],
      ytd: num(r[col(headers, "YTD")]),
    }));
    return <ChartBox title="Expense by category (YTD)" data={data} bars={[{ key: "ytd", name: "YTD", fill: CHART.accent }]} />;
  }

  return null;
}
