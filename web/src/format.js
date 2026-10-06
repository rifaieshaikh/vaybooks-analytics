export function round2(n) {
  const v = Number(n);
  if (!Number.isFinite(v)) return 0;
  return Math.round((v + Number.EPSILON) * 100) / 100;
}

export function money(n) {
  const v = round2(n || 0);
  return v.toLocaleString(undefined, { maximumFractionDigits: 2, minimumFractionDigits: 2 });
}

const REPORT_TEXT_HEADERS = new Set([
  "Status", "Stock Status", "Issue", "Type", "Source", "Key", "Detail",
  "Message", "Report", "Customer", "Account Name", "Group", "Sales Rep",
  "Item Name", "Generated At", "Report Date", "Timezone", "Phase", "Export Folder",
  "Line", "Category", "Component",
]);

export function formatReportCell(value, header) {
  if (value === "" || value == null) return "";
  if (REPORT_TEXT_HEADERS.has(header)) return String(value);
  const n = Number(value);
  if (!Number.isFinite(n)) return String(value);
  return money(n);
}

export function moneyOrDash(n) {
  if (n === null || n === undefined || n === "") return "—";
  return money(n);
}

/** Outstanding / sales age band keys (default 6 bands). */
export const AGE_KEYS = ["d0_15", "d15_30", "d30_45", "d45_60", "d60_90", "d90"];

export const AGE_LABELS = {
  d0_15: "0–15",
  d15_30: "15–30",
  d30_45: "30–45",
  d45_60: "45–60",
  d60_90: "60–90",
  d90: "90+",
};

export const AGE_COLORS = {
  d0_15: "#1f6b4a",
  d15_30: "#3d8f6a",
  d30_45: "#6a9e5a",
  d45_60: "#c4a35a",
  d60_90: "#b45309",
  d90: "#9f1239",
};

const FALLBACK_COLORS = ["#1f6b4a", "#3d8f6a", "#6a9e5a", "#c4a35a", "#b45309", "#9f1239", "#7c2d12", "#44403c"];

/** Prefer keys from a buckets map (supports custom aging bands). */
export function ageKeysFrom(buckets, bands) {
  if (Array.isArray(bands) && bands.length) {
    return bands.map((b) => b.key).filter(Boolean);
  }
  if (buckets && typeof buckets === "object") {
    const keys = Object.keys(buckets);
    if (keys.length) return keys;
  }
  return AGE_KEYS;
}

export function ageLabel(key, bands) {
  if (Array.isArray(bands)) {
    const hit = bands.find((b) => b.key === key);
    if (hit?.label) return hit.label;
  }
  return AGE_LABELS[key] || key;
}

export function ageColor(key, index = 0) {
  return AGE_COLORS[key] || FALLBACK_COLORS[index % FALLBACK_COLORS.length];
}

const DEFAULT_BANDS = [
  { key: "d0_15", max_days: 15 },
  { key: "d15_30", max_days: 30 },
  { key: "d30_45", max_days: 45 },
  { key: "d45_60", max_days: 60 },
  { key: "d60_90", max_days: 90 },
  { key: "d90", max_days: null },
];

/** Same rule as vay.settlement.bucket_key: first band whose max covers the age. */
export function bandKey(ageDays, bands) {
  const list = Array.isArray(bands) && bands.length ? bands : DEFAULT_BANDS;
  const days = Math.max(0, Math.trunc(Number(ageDays) || 0));
  for (const band of list) {
    if (!band?.key) continue;
    const max = band.max_days;
    if (max == null || max === "") return band.key;
    if (days <= Number(max)) return band.key;
  }
  return list[list.length - 1].key;
}

/** Keep a row when its date falls in the selected month (YYYY-MM) or fiscal year (start ISO). */
export function inSelectedPeriod(dateIso, view, monthKey, fyKey) {
  if (view !== "month" && view !== "fy") return true;
  const day = String(dateIso || "").slice(0, 10);
  if (view === "month") {
    const month = String(monthKey || "").slice(0, 7);
    return Boolean(month) && day.slice(0, 7) === month;
  }
  const start = String(fyKey || "").slice(0, 10);
  if (start.length < 10 || day.length < 10) return false;
  const end = (Number(start.slice(0, 4)) + 1) + start.slice(4);
  return day >= start && day < end;
}

export function rowBucket(row, key) {
  if (!row) return 0;
  if (row[key] != null && row[key] !== "") return Number(row[key]) || 0;
  return Number((row.owe_buckets || {})[key]) || 0;
}

export function rowCollectionBucket(row, key) {
  if (!row) return 0;
  const flat = "c_" + key;
  if (row[flat] != null && row[flat] !== "") return Number(row[flat]) || 0;
  return Number((row.collection_buckets || {})[key]) || 0;
}

export function bucketMoney(n) {
  const v = Number(n || 0);
  return v ? money(v) : "—";
}

export function initials(name) {
  const parts = String(name || "").trim().split(/\s+/).slice(0, 2);
  return parts.map((p) => p[0] || "").join("").toUpperCase() || "?";
}

let prevHash = "";
let skipPrev = false;

export function hashGet() {
  return decodeURIComponent((window.location.hash || "").replace(/^#/, ""));
}

export function hashSet(value) {
  const next = value ? "#" + value : "#";
  if (!skipPrev) prevHash = hashGet();
  skipPrev = false;
  if (window.location.hash !== next) window.location.hash = next;
}

export function hashBack(fallback = "") {
  const target = prevHash;
  skipPrev = true;
  prevHash = "";
  hashSet(target || fallback);
}

export function hashReset() {
  prevHash = "";
}

export function hashReturnLabel(fallback = "Back") {
  if (prevHash.startsWith("invoice/")) return "Invoice";
  if (prevHash.startsWith("item/")) return "Item";
  if (prevHash.startsWith("customer/")) return "Customer";
  if (prevHash.startsWith("group/")) return "Customer group";
  if (prevHash.startsWith("rep/")) return "Sales rep";
  if (prevHash.startsWith("category/")) return "Category";
  if (prevHash.startsWith("item-group/")) return "Item group";
  if (prevHash.startsWith("brand/")) return "Brand";
  if (prevHash.startsWith("supplier/")) return "Supplier";
  return fallback;
}
