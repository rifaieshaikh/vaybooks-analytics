async function req(path, opts = {}) {
  const headers = Object.assign({}, opts.headers || {});
  const res = await fetch(path, Object.assign({ credentials: "include" }, opts, { headers }));
  if (res.status === 401 && !path.includes("/api/auth/login")) {
    window.dispatchEvent(new Event("vay-auth-lost"));
  }
  if (res.status === 204) return null;
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) {
    const data = await res.json();
    if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : res.statusText);
    return data;
  }
  if (!res.ok) throw new Error(await res.text());
  return res;
}

export const api = {
  health: () => fetch("/api/health").then((r) => r.json()),
  audit: () => req("/api/audit"),
  info: () => fetch("/api/info").then((r) => r.json()),
  login: (username, password) =>
    req("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    }),
  logout: () => req("/api/auth/logout", { method: "POST" }),
  me: () => req("/api/auth/me"),
  changePassword: (current_password, new_password) =>
    req("/api/auth/change-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ current_password, new_password }),
    }),
  analytics: (params) => {
    const q = {};
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v !== undefined && v !== null && String(v) !== "") q[k] = v;
    });
    const qs = new URLSearchParams(q).toString();
    return req("/api/analytics" + (qs ? "?" + qs : ""));
  },
  savedViews: () => req("/api/analytics/views"),
  saveView: (page, filters) =>
    req("/api/analytics/views", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ page, filters: filters || {} }),
    }),
  actions: (params) => {
    const q = {};
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v !== undefined && v !== null && String(v) !== "") q[k] = v;
    });
    const qs = new URLSearchParams(q).toString();
    return req("/api/actions" + (qs ? "?" + qs : ""));
  },
  createAction: (body) =>
    req("/api/actions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    }),
  setActionStatus: (id, status) =>
    req("/api/actions/" + encodeURIComponent(id) + "/status", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    }),
  collection: (params) => {
    const q = {};
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v !== undefined && v !== null && String(v) !== "") q[k] = v;
    });
    const qs = new URLSearchParams(q).toString();
    return req("/api/collection" + (qs ? "?" + qs : ""));
  },
  collectionQueues: () => req("/api/collection/queues"),
  collectionReminder: (customer) => req("/api/collection/reminder?customer=" + encodeURIComponent(customer || "")),
  demoStatus: () => req("/api/demo"),
  openDemo: () => req("/api/demo", { method: "POST" }),
  license: () => req("/api/license"),
  downloadDiagnostics: async () => {
    const data = await req("/api/license/diagnostics");
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "vay-diagnostics.json";
    a.click();
    URL.revokeObjectURL(url);
  },
  createCollectionContact: (body) =>
    req("/api/collection/contacts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    }),
  updateCollectionContact: (id, body) =>
    req("/api/collection/contacts/" + encodeURIComponent(id), {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    }),
  createCollectionPromise: (body) =>
    req("/api/collection/promises", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    }),
  updateCollectionPromise: (id, body) =>
    req("/api/collection/promises/" + encodeURIComponent(id), {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    }),
  createCollectionDispute: (body) =>
    req("/api/collection/disputes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    }),
  updateCollectionDispute: (id, body) =>
    req("/api/collection/disputes/" + encodeURIComponent(id), {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    }),
  confirmCollectionAllocation: (body) =>
    req("/api/collection/allocations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    }),
  clearCollectionAllocation: (id) =>
    req("/api/collection/allocations/" + encodeURIComponent(id), { method: "DELETE" }),
  review: (params) => {
    const q = {};
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v !== undefined && v !== null && String(v) !== "") q[k] = v;
    });
    const qs = new URLSearchParams(q).toString();
    return req("/api/review" + (qs ? "?" + qs : ""));
  },
  cash: () => req("/api/cash"),
  reorder: (params) => {
    const q = {};
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v !== undefined && v !== null && String(v) !== "") q[k] = v;
    });
    const qs = new URLSearchParams(q).toString();
    return req("/api/reorder" + (qs ? "?" + qs : ""));
  },
  savedReports: () => req("/api/saved-reports"),
  savedReportCatalog: () => req("/api/saved-reports/catalog"),
  previewSavedReport: (body) =>
    req("/api/saved-reports/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    }),
  createSavedReport: (body) =>
    req("/api/saved-reports", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    }),
  approveSavedReport: (id) =>
    req("/api/saved-reports/" + encodeURIComponent(id) + "/approve", { method: "POST" }),
  adoptPack: () => req("/api/saved-reports/adopt-pack", { method: "POST" }),
  adoptRetailPack: () => req("/api/saved-reports/adopt-retail", { method: "POST" }),
  askReport: (body) =>
    req("/api/saved-reports/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    }),
  forecast: (qs) => req("/api/forecast" + (qs || "")),
  mapperPresets: () => req("/api/mappers/presets"),
  applyMapperPreset: (type, presetId) =>
    req("/api/mappers/" + type + "/preset/" + encodeURIComponent(presetId), { method: "POST" }),
  downloadSavedReport: async (id, params) => {
    const q = {};
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v !== undefined && v !== null && String(v) !== "") q[k] = v;
    });
    q.format = "csv";
    const qs = new URLSearchParams(q).toString();
    const res = await fetch("/api/saved-reports/" + encodeURIComponent(id) + "/export?" + qs, { credentials: "include" });
    if (!res.ok) throw new Error("Could not download");
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "saved_report.csv";
    a.click();
    URL.revokeObjectURL(url);
  },
  saveReorder: (body) =>
    req("/api/reorder", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    }),
  refresh: (runId) => {
    const qs = runId ? "?run=" + encodeURIComponent(runId) : "";
    return req("/api/analytics/refresh" + qs);
  },
  onboarding: (params) => {
    const q = {};
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v !== undefined && v !== null && String(v) !== "") q[k] = v;
    });
    const qs = new URLSearchParams(q).toString();
    return req("/api/analytics/onboarding" + (qs ? "?" + qs : ""));
  },
  business: (params) => {
    const q = {};
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v !== undefined && v !== null && String(v) !== "") q[k] = v;
    });
    const qs = new URLSearchParams(q).toString();
    return req("/api/business" + (qs ? "?" + qs : ""));
  },
  businessPdf: async (params) => {
    const q = {};
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v !== undefined && v !== null && String(v) !== "") q[k] = v;
    });
    const qs = new URLSearchParams(q).toString();
    const res = await req("/api/business/pdf" + (qs ? "?" + qs : ""));
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "Business_brief.pdf";
    a.click();
    URL.revokeObjectURL(url);
  },
  dashboard: (params) => {
    const q = {};
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v !== undefined && v !== null && String(v) !== "") q[k] = v;
    });
    const qs = new URLSearchParams(q).toString();
    return req("/api/dashboard" + (qs ? "?" + qs : ""));
  },
  mappers: () => req("/api/mappers"),
  mapper: (type) => req("/api/mappers/" + type),
  saveMapper: (type, body) =>
    req("/api/mappers/" + type, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  rebuildUk: (type) => req("/api/mappers/" + type + "/rebuild-uk", { method: "POST" }),
  cleanupData: (body) =>
    req("/api/data/cleanup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    }),
  factoryReset: () => req("/api/data/factory-reset", { method: "POST" }),
  uploads: () => req("/api/uploads"),
  previewUpload: (file, type, maps) => {
    const fd = new FormData();
    fd.append("file", file);
    if (type) fd.append("type", type);
    if (maps) fd.append("maps", JSON.stringify(maps));
    return req("/api/uploads/preview", { method: "POST", body: fd });
  },
  upload: (file, type, maps, eventMode, onlySheet) => {
    const fd = new FormData();
    fd.append("file", file);
    if (type) fd.append("type", type);
    if (maps) fd.append("maps", JSON.stringify(maps));
    if (eventMode) fd.append("event_mode", eventMode);
    if (onlySheet) fd.append("only_sheet", onlySheet);
    return req("/api/uploads", { method: "POST", body: fd });
  },
  createImportJob: (file, maps, eventMode, opts) => {
    const fd = new FormData();
    fd.append("file", file);
    if (maps) fd.append("maps", JSON.stringify(maps));
    if (eventMode) fd.append("event_mode", eventMode);
    if (opts && opts.dry_run) fd.append("dry_run", "1");
    if (opts && opts.effective_date) fd.append("effective_date", opts.effective_date);
    return req("/api/import-jobs", { method: "POST", body: fd });
  },
  getImportJob: (id) => req("/api/import-jobs/" + id),
  uploadReconSidecar: (file) => {
    const fd = new FormData();
    fd.append("file", file);
    return req("/api/recon/sidecars", { method: "POST", body: fd });
  },
  listReconSidecars: () => req("/api/recon/sidecars"),
  downloadUpload: async (id, filename) => {
    const res = await req("/api/uploads/" + id + "/file");
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename || "file";
    a.click();
    URL.revokeObjectURL(url);
  },
  deleteUpload: (id) => req("/api/uploads/" + id, { method: "DELETE" }),
  rows: (params) => {
    const q = {};
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v !== undefined && v !== null && String(v) !== "") q[k] = v;
    });
    return req("/api/rows?" + new URLSearchParams(q));
  },
  listRuns: (params) => {
    const q = new URLSearchParams();
    if (params && params.page) q.set("page", String(params.page));
    if (params && params.limit) q.set("limit", String(params.limit));
    const suffix = q.toString();
    return req("/api/runs" + (suffix ? "?" + suffix : ""));
  },
  createRun: (body) =>
    req("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  getRun: (id, opts) => req("/api/runs/" + id + (opts && opts.snapshot === false ? "?snapshot=0" : "")),
  downloadRun: async (id) => {
    const res = await req("/api/runs/" + id + "/file");
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "vay_reports.xlsx";
    a.click();
    URL.revokeObjectURL(url);
  },
  getRunExport: (id) => req("/api/runs/" + id + "/export-pdf"),
  exportRunPdfs: (id, ids) =>
    req("/api/runs/" + id + "/export-pdf", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids: ids || [] }),
    }),
  downloadRunPdfZip: async (id, filename) => {
    const res = await req("/api/runs/" + id + "/export-pdf/file");
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename || "vay_reports.zip";
    a.click();
    URL.revokeObjectURL(url);
  },
  worklist: (params) => {
    const q = new URLSearchParams();
    Object.entries(params || {}).forEach(([key, value]) => {
      if (value !== undefined && value !== null && String(value) !== "") q.set(key, value);
    });
    const qs = q.toString();
    return req("/api/worklist" + (qs ? "?" + qs : ""));
  },
  users: () => req("/api/users"),
  createUser: (body) =>
    req("/api/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  patchUser: (username, body) =>
    req("/api/users/" + encodeURIComponent(username), {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  deleteUser: (username) => req("/api/users/" + encodeURIComponent(username), { method: "DELETE" }),
  roles: () => req("/api/roles"),
  createRole: (body) =>
    req("/api/roles", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  saveRole: (name, permissions) =>
    req("/api/roles/" + encodeURIComponent(name), {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ permissions }),
    }),
  customers: (params) => {
    const q = {};
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v !== undefined && v !== null && String(v) !== "") q[k] = v;
    });
    return req("/api/customers?" + new URLSearchParams(q));
  },
  customer: (uk, params) => {
    const q = {};
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v !== undefined && v !== null && String(v) !== "") q[k] = v;
    });
    const qs = new URLSearchParams(q).toString();
    return req("/api/customers/" + encodeURIComponent(uk) + (qs ? "?" + qs : ""));
  },
  groups: (params) => {
    const q = {};
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v !== undefined && v !== null && String(v) !== "") q[k] = v;
    });
    return req("/api/groups?" + new URLSearchParams(q));
  },
  group: (uk, params) => {
    const q = {};
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v !== undefined && v !== null && String(v) !== "") q[k] = v;
    });
    const qs = new URLSearchParams(q).toString();
    return req("/api/groups/" + encodeURIComponent(uk) + (qs ? "?" + qs : ""));
  },
  reps: (params) => {
    const q = {};
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v !== undefined && v !== null && String(v) !== "") q[k] = v;
    });
    return req("/api/reps?" + new URLSearchParams(q));
  },
  rep: (uk, params) => {
    const q = {};
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v !== undefined && v !== null && String(v) !== "") q[k] = v;
    });
    const qs = new URLSearchParams(q).toString();
    return req("/api/reps/" + encodeURIComponent(uk) + (qs ? "?" + qs : ""));
  },
  partyTypes: () => req("/api/settings/party-types"),
  addPartyType: (label) =>
    req("/api/settings/party-types", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ label }),
    }),
  deletePartyType: (uk) =>
    req("/api/settings/party-types/" + encodeURIComponent(uk), { method: "DELETE" }),
  settlement: () => req("/api/settings/settlement"),
  setSettlement: (body) =>
    req("/api/settings/settlement", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(typeof body === "string" ? { mode: body } : body),
    }),
  orgPolicy: () => req("/api/settings/org-policy"),
  setOrgPolicy: (body) =>
    req("/api/settings/org-policy", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    }),
  accountAliases: () => req("/api/settings/account-aliases"),
  migrateAccount: (body) =>
    req("/api/settings/account-aliases/migrate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    }),
  removeAccountAlias: (source) =>
    req("/api/settings/account-aliases?source=" + encodeURIComponent(source || ""), { method: "DELETE" }),
  entityReview: () => req("/api/settings/entity-review"),
  mergeEntityReview: (body) =>
    req("/api/settings/entity-review/merge", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    }),
  rejectEntityReview: (body) =>
    req("/api/settings/entity-review/reject", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    }),
  expenseCategories: () => req("/api/settings/expense-categories"),
  setExpenseCategories: (body) =>
    req("/api/settings/expense-categories", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    }),
  dueDays: () => req("/api/settings/due-days"),
  setDueDays: (body) =>
    req("/api/settings/due-days", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(typeof body === "number" ? { due_days: body } : body),
    }),
  setCustomerDueDays: (uk, due_days) =>
    req("/api/customers/" + encodeURIComponent(uk) + "/due-days", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ due_days }),
    }),
  setGroupDueDays: (uk, due_days) =>
    req("/api/groups/" + encodeURIComponent(uk) + "/due-days", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ due_days }),
    }),
  setRepDueDays: (uk, due_days) =>
    req("/api/reps/" + encodeURIComponent(uk) + "/due-days", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ due_days }),
    }),
  orderCheckSettings: () => req("/api/settings/order-check"),
  setOrderCheckSettings: (body) =>
    req("/api/settings/order-check", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    }),
  setCustomerOrderCheck: (uk, body) =>
    req("/api/customers/" + encodeURIComponent(uk) + "/order-check", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    }),
  setGroupOrderCheck: (uk, body) =>
    req("/api/groups/" + encodeURIComponent(uk) + "/order-check", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    }),
  setRepOrderCheck: (uk, body) =>
    req("/api/reps/" + encodeURIComponent(uk) + "/order-check", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    }),
  setCustomerOrderFlags: (uk, body) =>
    req("/api/customers/" + encodeURIComponent(uk) + "/order-flags", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    }),
  runOrderCheck: (uk, body, params) => {
    const q = {};
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v !== undefined && v !== null && String(v) !== "") q[k] = v;
    });
    const qs = new URLSearchParams(q).toString();
    return req("/api/customers/" + encodeURIComponent(uk) + "/order-check/run" + (qs ? "?" + qs : ""), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
  },
  runGroupOrderCheck: (uk, body, params) => {
    const q = {};
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v !== undefined && v !== null && String(v) !== "") q[k] = v;
    });
    const qs = new URLSearchParams(q).toString();
    return req("/api/groups/" + encodeURIComponent(uk) + "/order-check/run" + (qs ? "?" + qs : ""), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
  },
  runRepOrderCheck: (uk, body, params) => {
    const q = {};
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v !== undefined && v !== null && String(v) !== "") q[k] = v;
    });
    const qs = new URLSearchParams(q).toString();
    return req("/api/reps/" + encodeURIComponent(uk) + "/order-check/run" + (qs ? "?" + qs : ""), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
  },
  patchParty: (uk, body) =>
    req("/api/parties/" + encodeURIComponent(uk), {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  customerPdf: async (uk, name, params) => {
    const q = {};
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v !== undefined && v !== null && String(v) !== "") q[k] = v;
    });
    const view = q.view === "customer" || q.view === "reminder" ? q.view : "rep";
    q.view = view;
    const qs = new URLSearchParams(q).toString();
    const res = await req("/api/customers/" + encodeURIComponent(uk) + "/pdf?" + qs);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    const kind = view === "customer" ? "statement" : view === "reminder" ? "reminder" : "brief";
    a.download = "customer_" + (name || kind).replace(/\s+/g, "_") + "_" + kind + ".pdf";
    a.click();
    URL.revokeObjectURL(url);
  },
  groupPdf: async (uk, name, params) => {
    const q = {};
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v !== undefined && v !== null && String(v) !== "") q[k] = v;
    });
    const qs = new URLSearchParams(q).toString();
    const res = await req("/api/groups/" + encodeURIComponent(uk) + "/pdf" + (qs ? "?" + qs : ""));
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "group_" + (name || "brief").replace(/\s+/g, "_") + "_brief.pdf";
    a.click();
    URL.revokeObjectURL(url);
  },
  repPdf: async (uk, name, params) => {
    const q = {};
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v !== undefined && v !== null && String(v) !== "") q[k] = v;
    });
    const qs = new URLSearchParams(q).toString();
    const res = await req("/api/reps/" + encodeURIComponent(uk) + "/pdf" + (qs ? "?" + qs : ""));
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "rep_" + (name || "brief").replace(/\s+/g, "_") + "_brief.pdf";
    a.click();
    URL.revokeObjectURL(url);
  },
  invoices: (params) => {
    const q = {};
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v !== undefined && v !== null && String(v) !== "") q[k] = v;
    });
    return req("/api/invoices?" + new URLSearchParams(q));
  },
  invoice: (id) => req("/api/invoices/" + encodeURIComponent(id)),
  itemLines: (params) => {
    const q = {};
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v !== undefined && v !== null && String(v) !== "") q[k] = v;
    });
    return req("/api/item-lines?" + new URLSearchParams(q));
  },
  itemDims: (dimension, params) => {
    const q = {};
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v !== undefined && v !== null && String(v) !== "") q[k] = v;
    });
    return req("/api/item-dims/" + encodeURIComponent(dimension) + "?" + new URLSearchParams(q));
  },
  itemDim: (dimension, uk, params) => {
    const q = {};
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v !== undefined && v !== null && String(v) !== "") q[k] = v;
    });
    const qs = new URLSearchParams(q).toString();
    return req("/api/item-dims/" + encodeURIComponent(dimension) + "/" + encodeURIComponent(uk) + (qs ? "?" + qs : ""));
  },
  stockItems: (params) => {
    const q = {};
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v !== undefined && v !== null && String(v) !== "") q[k] = v;
    });
    return req("/api/items?" + new URLSearchParams(q));
  },
  stockItem: (uk, params) => {
    const q = {};
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v !== undefined && v !== null && String(v) !== "") q[k] = v;
    });
    const qs = new URLSearchParams(q).toString();
    return req("/api/items/" + encodeURIComponent(uk) + (qs ? "?" + qs : ""));
  },
  repurchase: (entity, uk, params) => {
    const q = { entity, uk };
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v !== undefined && v !== null && String(v) !== "") q[k] = v;
    });
    return req("/api/repurchase?" + new URLSearchParams(q));
  },
  saveItemHolding: (uk, body) =>
    req("/api/items/" + encodeURIComponent(uk) + "/holding", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    }),
  saveDefaultHolding: (body) =>
    req("/api/items/holding-default", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    }),
};
