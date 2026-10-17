export const CHART = {
  sales: "#1f6b4a",
  collection: "#78716c",
  accent: "#1f6b4a",
  agingNew: "#a8a29e",
  aging15: "#c2410c",
  aging30: "#b91c1c",
  due: "#b45309",
};

export const REQUIRED_FIELDS = {
  sales: ["Date", "Party Name", "Sales Rep", "Net Amount"],
  receipt: ["Date", "Account Name", "Sales Rep", "Amount"],
  credit_note: ["Date", "Party Name", "Invoice No", "Net Amount"],
  arr: ["Account Name", "Group", "Balance"],
  items: ["Date", "Item Name", "Qty", "Rate"],
  stock: ["Item Name", "Qty", "P.Price"],
  payments: ["Date", "Account Name", "Amount"],
  reservation: ["Item Name", "Qty", "Need By"],
  incoming: ["Item Name", "Qty", "Expected Date", "Confirmed"],
  item_cost: ["Item Name", "Cost", "Effective Date"],
  opening_cash: ["Date", "Amount"],
  payable: ["Account Name", "Amount", "Due Date"],
  customer_opening: ["Date", "Account Name", "Balance"],
  stock_opening: ["Date", "Item Name", "Qty", "Unit"],
  purchases: ["Date", "Item Name", "Qty", "Unit"],
  stock_movement: ["Date", "Item Name", "Qty", "Unit", "Movement"],
  party: ["Account Name", "Group"],
};

export const ITEM_ATTR_FIELDS = ["Category", "Item Group", "Brand", "Supplier"];

export const TYPE_META = {
  sales: {
    label: "Sales",
    partyLabel: "Party Name",
    dates: true,
    rep: true,
    group: true,
    item: "column",
  },
  receipt: {
    label: "Receipts",
    partyLabel: "Party",
    dates: true,
    rep: true,
    group: true,
    item: false,
  },
  credit_note: {
    label: "Credit notes",
    partyLabel: "Party Name",
    dates: true,
    rep: false,
    group: true,
    item: false,
  },
  arr: {
    label: "Outstanding",
    partyLabel: "Party",
    dates: false,
    rep: false,
    group: true,
    item: false,
    balance: true,
  },
  payments: {
    label: "Payments",
    partyLabel: "Party",
    dates: true,
    rep: false,
    group: true,
    item: false,
  },
  party: {
    label: "Parties",
    partyLabel: "Party",
    dates: false,
    rep: false,
    group: true,
    item: false,
    balance: true,
    partyType: true,
  },
  items: {
    label: "Item-wise sales",
    partyLabel: "Party / account",
    dates: true,
    rep: false,
    group: true,
    item: true,
  },
  stock: {
    label: "Stock",
    partyLabel: "",
    dates: false,
    rep: false,
    group: false,
    item: true,
  },
  reservation: { label: "Reservations", partyLabel: "", dates: true, rep: false, group: false, item: true },
  incoming: { label: "Incoming", partyLabel: "", dates: true, rep: false, group: false, item: true },
  item_cost: { label: "Item cost", partyLabel: "", dates: true, rep: false, group: false, item: true },
  opening_cash: { label: "Opening cash", partyLabel: "", dates: true, rep: false, group: false, item: false },
  payable: { label: "Payables", partyLabel: "Supplier", dates: true, rep: false, group: false, item: false },
  customer_opening: { label: "Customer openings", partyLabel: "Customer", dates: true, rep: false, group: false, item: false, balance: true },
  stock_opening: { label: "Stock openings", partyLabel: "", dates: true, rep: false, group: false, item: true },
  purchases: { label: "Purchases", partyLabel: "Supplier", dates: true, rep: false, group: false, item: true },
  stock_movement: { label: "Stock movements", partyLabel: "", dates: true, rep: false, group: false, item: true },
};

const LIBRARY_TABS = [
  { id: "performance", label: "Performance", family: "Performance", perm: "reports.view.performance" },
  { id: "followup", label: "Follow-up", family: "Follow-up", perm: "reports.view.followup" },
  { id: "monthly", label: "Monthly", family: "Monthly", perm: "reports.view.monthly" },
  { id: "items", label: "Items", family: "Items", perm: "reports.view.items" },
  { id: "profit", label: "Profit", family: "Profit", perm: "reports.view.profit" },
];

const SETTINGS_TABS = {
  organization: [
    { id: "organization", label: "Organization", section: "organization", perm: "settings.advanced" },
    { id: "account-names", label: "Account migrations and name review", section: "account-names", perm: "settings.advanced" },
    { id: "party-types", label: "Party types", section: "party-types", perm: "settings.advanced" },
  ],
  "business-rules": [
    { id: "settlement", label: "Settlement", section: "settlement", perm: "settings.advanced" },
    { id: "due-days", label: "Due days", section: "due-days", perm: "settings.advanced" },
    { id: "order-check", label: "Order check", section: "order-check", perm: "settings.advanced" },
  ],
  "users-roles": [
    { id: "users", label: "Users", section: "users", perm: "users.view" },
    { id: "roles", label: "Roles", section: "roles", perm: "roles.view" },
  ],
  "system-support": [
    { id: "network", label: "Network", section: "network", perm: "__home__" },
    { id: "license", label: "Plan and support", section: "license", perm: "settings.advanced" },
    { id: "audit", label: "Audit", section: "audit", perm: "settings.advanced" },
    { id: "advanced", label: "Advanced", section: "advanced", perm: "settings.advanced" },
  ],
};

export const NAV = [
  {
    id: "overview",
    label: "Overview",
    items: [
      { id: "dashboard", label: "Dashboard", kind: "home", perm: "__home__" },
      { id: "today", label: "Today's work", kind: "analytics", section: "today", perm: "reports.view.followup" },
      { id: "business", label: "Business overview", kind: "business", perm: "customer.view" },
      { id: "scorecard", label: "Scorecard", kind: "analytics", section: "scorecard", perm: "reports.view.scorecard" },
      { id: "weekly-review", label: "Weekly review", kind: "analytics", section: "review", perm: "reports.view.scorecard" },
    ],
  },
  {
    id: "sales",
    label: "Sales",
    items: [
      { id: "invoices", label: "Invoices", kind: "sales", perm: "sales.view" },
      { id: "returns-credit-notes", label: "Returns and credit notes", kind: "data", type: "credit_note", perm: "credit_note.view" },
      { id: "item-wise", label: "Item-wise sales", kind: "items", perm: "items.view" },
      { id: "reps", label: "Sales reps", kind: "reps", perm: "customer.view" },
      { id: "change", label: "Sales change", kind: "analytics", section: "sales-change", perm: "reports.view.scorecard" },
    ],
  },
  {
    id: "customers",
    label: "Customers",
    items: [
      { id: "list", label: "Customers", kind: "customers", perm: "customer.view" },
      { id: "groups", label: "Customer groups", kind: "groups", perm: "customer.view" },
      { id: "movement", label: "Customer movement", kind: "analytics", section: "customer-movement", perm: "reports.view.scorecard" },
    ],
  },
  {
    id: "finance",
    label: "Finance",
    items: [
      { id: "collection-worklist", label: "Collection worklist", kind: "analytics", section: "collection", perm: "reports.view.followup" },
      { id: "outstanding", label: "Outstanding", kind: "data", type: "arr", perm: "arr.view" },
      { id: "receipts", label: "Receipts", kind: "data", type: "receipt", perm: "receipt.view" },
      { id: "payments", label: "Payments", kind: "data", type: "payments", perm: "payments.view" },
      { id: "cash", label: "Cash", kind: "cash", perm: "payments.view" },
      { id: "parties", label: "Parties", kind: "data", type: "party", perm: "party.view" },
    ],
  },
  {
    id: "inventory",
    label: "Inventory",
    items: [
      { id: "stock", label: "Stock", kind: "stock", perm: "stock.view" },
      { id: "item-profiles", label: "Item profiles", kind: "items360", perm: "stock.view" },
      { id: "categories", label: "Categories", kind: "item-dim", dimension: "category", perm: "stock.view" },
      { id: "item-groups", label: "Item groups", kind: "item-dim", dimension: "item_group", perm: "stock.view" },
      { id: "brands", label: "Brands", kind: "item-dim", dimension: "brand", perm: "stock.view" },
      { id: "suppliers", label: "Suppliers", kind: "item-dim", dimension: "supplier", perm: "stock.view" },
      { id: "stock-decisions", label: "Stock decisions", kind: "analytics", section: "stock", perm: "reports.view.items" },
      { id: "reorder", label: "Reorder", kind: "analytics", section: "reorder", perm: "reports.view.items" },
    ],
  },
  {
    id: "reports",
    label: "Reports",
    items: [
      { id: "create", label: "Create reports", kind: "create", perm: "reports.create" },
      { id: "library", label: "Report library", kind: "reports", tabs: LIBRARY_TABS },
      { id: "builder", label: "Report builder", kind: "analytics", section: "builder", perm: "__builder__" },
      { id: "pdf-exports", label: "PDF exports", kind: "export", perm: "reports.create" },
      { id: "excel-exports", label: "Excel exports", kind: "excel", perm: "__excel__" },
    ],
  },
  {
    id: "data",
    label: "Data",
    items: [
      { id: "import", label: "Import", kind: "import", perm: "__import__" },
      { id: "explore", label: "Explore", kind: "explore", perm: "__explore__" },
      { id: "quality", label: "Data quality", kind: "analytics", section: "quality", perm: "reports.view.quality" },
      { id: "issue-reports", label: "Data issue reports", kind: "reports", family: "Data issues", perm: "reports.view.issues" },
    ],
  },
  {
    id: "settings",
    label: "Settings",
    items: [
      { id: "organization", label: "Organization", kind: "settings", tabs: SETTINGS_TABS.organization },
      { id: "business-rules", label: "Business rules", kind: "settings", tabs: SETTINGS_TABS["business-rules"] },
      { id: "users-roles", label: "Users and roles", kind: "settings", tabs: SETTINGS_TABS["users-roles"] },
      { id: "system-support", label: "System and support", kind: "settings", tabs: SETTINGS_TABS["system-support"] },
    ],
  },
];

export const ALIASES = {
  "home/home": { tab: "overview", sub: "dashboard" },
  "reports/today": { tab: "overview", sub: "today" },
  "customers/business": { tab: "overview", sub: "business" },
  "reports/scorecard": { tab: "overview", sub: "scorecard" },
  "reports/weekly-review": { tab: "overview", sub: "weekly-review" },
  "sales/sales": { tab: "sales", sub: "invoices" },
  "sales/returns": { tab: "sales", sub: "returns-credit-notes" },
  "finance/credit_note": { tab: "sales", sub: "returns-credit-notes" },
  "sales/items": { tab: "sales", sub: "item-wise" },
  "customers/reps": { tab: "sales", sub: "reps" },
  "reports/sales-change": { tab: "sales", sub: "change" },
  "customers/customers": { tab: "customers", sub: "list" },
  "customers/groups": { tab: "customers", sub: "groups" },
  "reports/customer-movement": { tab: "customers", sub: "movement" },
  "reports/collection-worklist": { tab: "finance", sub: "collection-worklist" },
  "finance/arr": { tab: "finance", sub: "outstanding" },
  "finance/receipt": { tab: "finance", sub: "receipts" },
  "finance/payments": { tab: "finance", sub: "payments" },
  "finance/cash": { tab: "finance", sub: "cash" },
  "finance/party": { tab: "finance", sub: "parties" },
  "stock/stock": { tab: "inventory", sub: "stock" },
  "customers/items": { tab: "inventory", sub: "item-profiles" },
  "customers/item-category": { tab: "inventory", sub: "categories" },
  "customers/item-group": { tab: "inventory", sub: "item-groups" },
  "customers/brand": { tab: "inventory", sub: "brands" },
  "customers/supplier": { tab: "inventory", sub: "suppliers" },
  "reports/stock-decisions": { tab: "inventory", sub: "stock-decisions" },
  "reports/reorder": { tab: "inventory", sub: "reorder" },
  "reports/create": { tab: "reports", sub: "create" },
  "reports/performance": { tab: "reports", sub: "library", section: "performance" },
  "reports/followup": { tab: "reports", sub: "library", section: "followup" },
  "reports/monthly": { tab: "reports", sub: "library", section: "monthly" },
  "reports/items": { tab: "reports", sub: "library", section: "items" },
  "reports/profit": { tab: "reports", sub: "library", section: "profit" },
  "reports/report-builder": { tab: "reports", sub: "builder" },
  "data/export": { tab: "reports", sub: "pdf-exports" },
  "data/excel": { tab: "reports", sub: "excel-exports" },
  "data/import": { tab: "data", sub: "import" },
  "data/explore": { tab: "data", sub: "explore" },
  "reports/data-quality": { tab: "data", sub: "quality" },
  "reports/issues": { tab: "data", sub: "issue-reports" },
  "settings/organization": { tab: "settings", sub: "organization", section: "organization" },
  "settings/account-names": { tab: "settings", sub: "organization", section: "account-names" },
  "settings/party-types": { tab: "settings", sub: "organization", section: "party-types" },
  "settings/settlement": { tab: "settings", sub: "business-rules", section: "settlement" },
  "settings/due-days": { tab: "settings", sub: "business-rules", section: "due-days" },
  "settings/order-check": { tab: "settings", sub: "business-rules", section: "order-check" },
  "settings/users": { tab: "settings", sub: "users-roles", section: "users" },
  "settings/roles": { tab: "settings", sub: "users-roles", section: "roles" },
  "settings/network": { tab: "settings", sub: "system-support", section: "network" },
  "settings/license": { tab: "settings", sub: "system-support", section: "license" },
  "settings/audit": { tab: "settings", sub: "system-support", section: "audit" },
  "settings/advanced": { tab: "settings", sub: "system-support", section: "advanced" },
};

export const PERMISSION_GROUPS = [
  {
    id: "sales",
    label: "Sales",
    perms: [
      { id: "sales.view", label: "View sales", short: "View" },
      { id: "sales.upload", label: "Import sales", short: "Import" },
      { id: "sales.map", label: "Map sales columns", short: "Map" },
    ],
  },
  {
    id: "receipt",
    label: "Receipts",
    perms: [
      { id: "receipt.view", label: "View receipts", short: "View" },
      { id: "receipt.upload", label: "Import receipts", short: "Import" },
      { id: "receipt.map", label: "Map receipt columns", short: "Map" },
    ],
  },
  {
    id: "credit_note",
    label: "Credit notes",
    perms: [
      { id: "credit_note.view", label: "View credit notes", short: "View" },
      { id: "credit_note.upload", label: "Import credit notes", short: "Import" },
      { id: "credit_note.map", label: "Map credit note columns", short: "Map" },
    ],
  },
  {
    id: "arr",
    label: "Outstanding",
    perms: [
      { id: "arr.view", label: "View outstanding", short: "View" },
      { id: "arr.upload", label: "Import outstanding", short: "Import" },
      { id: "arr.map", label: "Map outstanding columns", short: "Map" },
    ],
  },
  {
    id: "payments",
    label: "Payments",
    perms: [
      { id: "payments.view", label: "View payments", short: "View" },
      { id: "payments.upload", label: "Import payments", short: "Import" },
      { id: "payments.map", label: "Map payment columns", short: "Map" },
    ],
  },
  {
    id: "party",
    label: "Parties",
    perms: [
      { id: "party.view", label: "View parties", short: "View" },
      { id: "party.upload", label: "Import parties", short: "Import" },
      { id: "party.map", label: "Map party columns", short: "Map" },
    ],
  },
  {
    id: "customer",
    label: "Customers",
    perms: [
      { id: "customer.view", label: "View customers", short: "View" },
    ],
  },
  {
    id: "items",
    label: "Items",
    perms: [
      { id: "items.view", label: "View item-wise sales", short: "View" },
      { id: "items.upload", label: "Import item-wise sales", short: "Import" },
      { id: "items.map", label: "Map item-wise columns", short: "Map" },
    ],
  },
  {
    id: "stock",
    label: "Stock",
    perms: [
      { id: "stock.view", label: "View stock", short: "View" },
      { id: "stock.upload", label: "Import stock", short: "Import" },
      { id: "stock.map", label: "Map stock columns", short: "Map" },
    ],
  },
  {
    id: "reports",
    label: "Reports",
    perms: [
      { id: "reports.create", label: "Create reports", short: "Create" },
      { id: "reports.view.performance", label: "View Performance", short: "Performance" },
      { id: "reports.view.followup", label: "View Follow-up", short: "Follow-up" },
      { id: "reports.view.monthly", label: "View Monthly", short: "Monthly" },
      { id: "reports.view.items", label: "View Items", short: "Items" },
      { id: "reports.view.profit", label: "View Profit", short: "Profit" },
      { id: "reports.view.issues", label: "View Data issues", short: "Data issues" },
      { id: "reports.view.scorecard", label: "View Scorecard", short: "Scorecard" },
      { id: "reports.view.quality", label: "View Data quality", short: "Data quality" },
      { id: "actions.manage", label: "Assign and complete actions", short: "Actions" },
      { id: "reports.manage", label: "Build and approve reports", short: "Build" },
    ],
  },
  {
    id: "users",
    label: "Users",
    perms: [
      { id: "users.view", label: "View users", short: "View" },
      { id: "users.manage", label: "Manage users", short: "Manage" },
    ],
  },
  {
    id: "roles",
    label: "Roles",
    perms: [
      { id: "roles.view", label: "View roles and permissions", short: "View" },
      { id: "roles.manage", label: "Manage roles and permissions", short: "Manage" },
    ],
  },
  {
    id: "settings",
    label: "Settings",
    perms: [
      { id: "settings.import", label: "Import any type", short: "Import any" },
      { id: "settings.advanced", label: "Advanced settings", short: "Advanced" },
    ],
  },
];

export function groupedPermissions(all) {
  const allowed = new Set(all || []);
  const known = new Set();
  const groups = [];
  for (const group of PERMISSION_GROUPS) {
    const perms = group.perms.filter((p) => allowed.has(p.id));
    perms.forEach((p) => known.add(p.id));
    if (perms.length) groups.push({ id: group.id, label: group.label, perms });
  }
  const extra = (all || []).filter((id) => !known.has(id)).map((id) => ({ id, label: id, short: id }));
  if (extra.length) groups.push({ id: "other", label: "Other", perms: extra });
  return groups;
}

export function can(user, perm) {
  const perms = user?.permissions || [];
  if (perm === "__home__") return Boolean(user);
  if (perm === "__import__") {
    return Boolean(perms.some((p) => p.endsWith(".upload") || p === "settings.import"));
  }
  if (perm === "__explore__") {
    return Boolean(perms.some((p) => p.endsWith(".view")));
  }
  if (perm === "__builder__") {
    return perms.includes("reports.manage") || perms.some((p) => p.startsWith("reports.view."));
  }
  if (perm === "__excel__") {
    return Boolean(
      perms.includes("reports.create")
      || perms.some((p) => p.startsWith("reports.view."))
    );
  }
  if (perm === "users.view") {
    return perms.includes("users.view") || perms.includes("users.manage");
  }
  if (perm === "roles.view") {
    return perms.includes("roles.view") || perms.includes("roles.manage");
  }
  return perms.includes(perm);
}

export function permittedTabs(user, item) {
  return (item?.tabs || []).filter((tab) => can(user, tab.perm));
}

export function destinationAllowed(user, item) {
  if (!item) return false;
  if (item.tabs?.length) return permittedTabs(user, item).length > 0;
  return can(user, item.perm);
}

export function visibleNav(user) {
  return NAV.map((tab) => ({
    ...tab,
    items: tab.items.filter((item) => destinationAllowed(user, item)),
  })).filter((tab) => tab.items.length);
}

export function resolveRoute(tab, sub) {
  const alias = ALIASES[String(tab || "") + "/" + String(sub || "")];
  if (alias) return { tab: alias.tab, sub: alias.sub, section: alias.section || "" };
  return { tab, sub, section: "" };
}

function rememberedSection(itemId, allowedIds) {
  try {
    const stored = sessionStorage.getItem("vay-tab:nav:" + itemId);
    if (stored && allowedIds.includes(stored)) return stored;
  } catch {
    /* private mode */
  }
  return "";
}

export function chooseSection(user, item, explicit) {
  const tabs = permittedTabs(user, item);
  if (!tabs.length) return "";
  if (explicit && tabs.some((tab) => tab.id === explicit)) {
    try {
      sessionStorage.setItem("vay-tab:nav:" + item.id, explicit);
    } catch {
      /* private mode */
    }
    return explicit;
  }
  const remembered = rememberedSection(item.id, tabs.map((tab) => tab.id));
  if (remembered) return remembered;
  return tabs[0].id;
}

export function firstRoute(user) {
  const tabs = visibleNav(user);
  const overview = tabs.find((group) => group.id === "overview");
  const dashboard = overview?.items.find((item) => item.id === "dashboard");
  if (dashboard) return { tab: "overview", sub: "dashboard", section: "" };
  if (!tabs.length || !tabs[0].items[0]) return { tab: "overview", sub: "dashboard", section: "" };
  return { tab: tabs[0].id, sub: tabs[0].items[0].id, section: "" };
}

export function findItem(tabId, subId) {
  const resolved = resolveRoute(tabId, subId);
  const tab = NAV.find((group) => group.id === resolved.tab);
  return (tab?.items || []).find((item) => item.id === resolved.sub) || null;
}
