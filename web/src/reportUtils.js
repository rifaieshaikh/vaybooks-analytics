const SALES_FOLLOW = "sales_follow_up_";
const COLL_FOLLOW = "collection_follow_up_";
const GROUP_ORDER = ["Performance", "Follow-up", "Monthly", "Items", "Profit", "Data issues"];

export function reportId(r) {
  return r.id || "";
}

export function isWide(r) {
  return Boolean(r.wide);
}

export function fyBlocks(report) {
  if (!report.wide) return [];
  const headers = report.headers || [];
  const labelCols = report.label_cols || 1;
  const trailing = report.trailing || 0;
  const rows = [...(report.rows || [])];
  if (report.total) rows.push(report.total);
  const pair = report.wide === "pair";
  let n = report.n_fy;
  if (n == null) {
    if (pair) n = Math.floor((headers.length - labelCols - 2) / 26);
    else n = Math.floor((headers.length - labelCols - 1 - trailing) / 13);
  }
  const blocks = [];
  for (let yi = 0; yi < Math.max(n, 1); yi += 1) {
    const start = pair ? labelCols + yi * 26 : labelCols + yi * 13;
    const end = pair ? start + 26 : start + 13;
    const cols = [...Array(labelCols).keys(), ...Array.from({ length: end - start }, (_, i) => start + i)];
    if (trailing) {
      const t0 = headers.length - trailing;
      for (let i = t0; i < headers.length; i += 1) cols.push(i);
    }
    const names = cols.map((i) => headers[i]);
    const data = rows.map((row) => cols.map((i) => (i < row.length ? row[i] : "")));
    const fyHeaders = report.header_row1 || [];
    blocks.push({ title: fyHeaders[start] || "Year " + (yi + 1), names, data });
  }
  return blocks;
}

export function visibleGroups(reports) {
  const present = new Set();
  for (const r of reports) {
    if (r.id === "source_data_warnings" && !(r.rows || []).length) continue;
    present.add(r.group);
  }
  return GROUP_ORDER.filter((g) => present.has(g));
}

export function reportsInGroup(reports, group) {
  return reports.filter((r) => r.group === group && !(r.id === "source_data_warnings" && !(r.rows || []).length));
}

export function followupGroups(reports, kind) {
  const prefix = kind === "sales" ? SALES_FOLLOW : COLL_FOLLOW;
  const names = [];
  const seen = new Set();
  for (const r of reports) {
    if (!(r.id || "").startsWith(prefix)) continue;
    const name = r.id.slice(prefix.length);
    if (name && !seen.has(name)) {
      seen.add(name);
      names.push(name);
    }
  }
  names.sort((a, b) => a.localeCompare(b));
  return names;
}

export function findFollowup(reports, kind, group) {
  const id = (kind === "sales" ? SALES_FOLLOW : COLL_FOLLOW) + group;
  return reports.find((r) => r.id === id);
}

export function uniqueById(reports) {
  const seen = new Set();
  const out = [];
  for (const r of reports) {
    if (seen.has(r.id)) continue;
    seen.add(r.id);
    out.push(r);
  }
  return out;
}

function isTotal(val) {
  return String(val || "").trim().toLowerCase() === "total";
}

function eqCell(cell, want) {
  if (!(want || "").trim()) return true;
  return String(cell || "").trim().toLowerCase() === String(want).trim().toLowerCase();
}

export function uniqueCol(rows, headers, name) {
  const idx = headers.indexOf(name);
  if (idx < 0) return [];
  const vals = new Set();
  (rows || []).forEach((row) => {
    const val = String(row[idx] || "").trim();
    if (val && val.toLowerCase() !== "total") vals.add(val);
  });
  return Array.from(vals).sort((a, b) => a.localeCompare(b));
}

export function sortReportRows(rows, headers, sort, dir) {
  const idx = headers.indexOf(sort);
  if (idx < 0) return rows;
  const body = [];
  const totals = [];
  (rows || []).forEach((row) => {
    if (isTotal(row[0])) totals.push(row);
    else body.push(row);
  });
  const desc = dir === "desc";
  body.sort((a, b) => {
    const av = a[idx];
    const bv = b[idx];
    const an = parseFloat(String(av ?? "").replace(/,/g, ""));
    const bn = parseFloat(String(bv ?? "").replace(/,/g, ""));
    if (Number.isFinite(an) && Number.isFinite(bn)) return desc ? bn - an : an - bn;
    return desc ? String(bv || "").localeCompare(String(av || "")) : String(av || "").localeCompare(String(bv || ""));
  });
  return body.concat(totals);
}

export function sliceRows(report, { query, group, rep, account, item, status }) {
  const headers = report.headers || [];
  let rows = [...(report.rows || [])];
  if (report.total) rows = rows.concat([report.total]);
  const keyCol = report.key_col || 0;
  const gi = headers.indexOf("Group");
  const ri = headers.indexOf("Sales Rep");
  const ai = headers.indexOf("Account Name") >= 0 ? headers.indexOf("Account Name") : headers.indexOf("Customer");
  const ii = headers.indexOf("Item Name");
  const si = headers.indexOf("Status") >= 0 ? headers.indexOf("Status") : headers.indexOf("Stock Status");
  const nameIdx = report.id === "source_data_warnings" && headers.indexOf("Key") >= 0 ? headers.indexOf("Key") : keyCol;
  return rows.filter((row) => {
    if (isTotal(row[0]) && report.total) return true;
    if (!eqCell(row[nameIdx], query)) return false;
    if (gi >= 0 && !eqCell(row[gi], group)) return false;
    if (ri >= 0 && !eqCell(row[ri], rep)) return false;
    if (ai >= 0 && !eqCell(row[ai], account)) return false;
    if (ii >= 0 && !eqCell(row[ii], item)) return false;
    if (si >= 0 && !eqCell(row[si], status)) return false;
    return true;
  });
}

export function num(val) {
  const n = parseFloat(String(val).replace(/,/g, ""));
  return Number.isFinite(n) ? n : 0;
}

export function profitRan(reports) {
  return reports.some((r) => r.id === "monthly_profit_report" || r.id === "expense_by_category");
}
