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
};

export const NAV = [
  {
    id: "home",
    label: "Home",
    items: [
      { id: "home", label: "Dashboard", kind: "home", perm: "__home__" },
    ],
  },
  {
    id: "data",
    label: "Data",
    items: [
      { id: "import", label: "Import", kind: "import", perm: "__import__" },
      { id: "explore", label: "Explore", kind: "explore", perm: "__explore__" },
      { id: "export", label: "Export", kind: "export", perm: "reports.create" },
      { id: "excel", label: "Excel", kind: "excel", perm: "__excel__" },
    ],
  },
  {
    id: "sales",
    label: "Sales",
    items: [
      { id: "sales", label: "Sales invoices", kind: "sales", perm: "sales.view" },
      { id: "returns", label: "Sales returns", kind: "data", type: "credit_note", perm: "credit_note.view" },
      { id: "items", label: "Item-wise sales", kind: "items", perm: "items.view" },
    ],
  },
  {
    id: "customers",
    label: "360 View",
    items: [
      { id: "business", label: "Business", kind: "business", perm: "customer.view" },
      { id: "customers", label: "Customers", kind: "customers", perm: "customer.view" },
      { id: "items", label: "Items", kind: "items360", perm: "stock.view" },
      { id: "item-category", label: "Category", kind: "item-dim", dimension: "category", perm: "stock.view" },
      { id: "item-group", label: "Item group", kind: "item-dim", dimension: "item_group", perm: "stock.view" },
      { id: "brand", label: "Brand", kind: "item-dim", dimension: "brand", perm: "stock.view" },
      { id: "supplier", label: "Supplier", kind: "item-dim", dimension: "supplier", perm: "stock.view" },
      { id: "groups", label: "Customer group", kind: "groups", perm: "customer.view" },
      { id: "reps", label: "Sales rep", kind: "reps", perm: "customer.view" },
    ],
  },
  {
    id: "finance",
    label: "Finance",
    items: [
      { id: "party", label: "Parties", kind: "data", type: "party", perm: "party.view" },
      { id: "arr", label: "Outstanding", kind: "data", type: "arr", perm: "arr.view" },
      { id: "receipt", label: "Receipts", kind: "data", type: "receipt", perm: "receipt.view" },
      { id: "credit_note", label: "Credit notes", kind: "data", type: "credit_note", perm: "credit_note.view" },
      { id: "payments", label: "Payments", kind: "data", type: "payments", perm: "payments.view" },
    ],
  },
  {
    id: "stock",
    label: "Stock",
    items: [
      { id: "stock", label: "Stock", kind: "stock", perm: "stock.view" },
    ],
  },
  {
    id: "reports",
    label: "Reports",
    items: [
      { id: "create", label: "Create", kind: "create", perm: "reports.create" },
      { id: "performance", label: "Performance", kind: "reports", family: "Performance", perm: "reports.view.performance" },
      { id: "followup", label: "Follow-up", kind: "reports", family: "Follow-up", perm: "reports.view.followup" },
      { id: "monthly", label: "Monthly", kind: "reports", family: "Monthly", perm: "reports.view.monthly" },
      { id: "items", label: "Items", kind: "reports", family: "Items", perm: "reports.view.items" },
      { id: "profit", label: "Profit", kind: "reports", family: "Profit", perm: "reports.view.profit" },
      { id: "issues", label: "Data issues", kind: "reports", family: "Data issues", perm: "reports.view.issues" },
      { id: "scorecard", label: "Scorecard", kind: "analytics", section: "scorecard", perm: "reports.view.scorecard" },
      { id: "sales-change", label: "Sales change", kind: "analytics", section: "sales-change", perm: "reports.view.scorecard" },
      { id: "customer-movement", label: "Customer movement", kind: "analytics", section: "customer-movement", perm: "reports.view.scorecard" },
      { id: "collection-worklist", label: "Collection worklist", kind: "analytics", section: "collection", perm: "reports.view.followup" },
      { id: "stock-decisions", label: "Stock decisions", kind: "analytics", section: "stock", perm: "reports.view.items" },
      { id: "data-quality", label: "Data quality", kind: "analytics", section: "quality", perm: "reports.view.quality" },
      { id: "weekly-review", label: "Weekly review", kind: "analytics", section: "review", perm: "reports.view.scorecard" },
      { id: "reorder", label: "Reorder", kind: "analytics", section: "reorder", perm: "reports.view.items" },
      { id: "report-builder", label: "Report builder", kind: "analytics", section: "builder", perm: "__builder__" },
    ],
  },
  {
    id: "settings",
    label: "Settings",
    items: [
      { id: "network", label: "Network", kind: "settings", section: "network", perm: "__home__" },
      { id: "organization", label: "Organization", kind: "settings", section: "organization", perm: "settings.advanced" },
      { id: "account-names", label: "Account migrations", kind: "settings", section: "account-names", perm: "settings.advanced" },
      { id: "settlement", label: "Settlement", kind: "settings", section: "settlement", perm: "settings.advanced" },
      { id: "due-days", label: "Due days", kind: "settings", section: "due-days", perm: "settings.advanced" },
      { id: "order-check", label: "Order check", kind: "settings", section: "order-check", perm: "settings.advanced" },
      { id: "party-types", label: "Party types", kind: "settings", section: "party-types", perm: "settings.advanced" },
      { id: "audit", label: "Audit", kind: "settings", section: "audit", perm: "settings.advanced" },
      { id: "advanced", label: "Advanced", kind: "settings", section: "advanced", perm: "settings.advanced" },
      { id: "users", label: "Users", kind: "settings", section: "users", perm: "users.view" },
      { id: "roles", label: "Roles", kind: "settings", section: "roles", perm: "roles.view" },
    ],
  },
];

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

export function visibleNav(user) {
  return NAV.map((tab) => ({
    ...tab,
    items: tab.items.filter((item) => can(user, item.perm)),
  })).filter((tab) => tab.items.length);
}

export function firstRoute(user) {
  const tabs = visibleNav(user);
  const home = tabs.find((t) => t.id === "home");
  if (home?.items[0]) return { tab: home.id, sub: home.items[0].id };
  if (!tabs.length) return { tab: "home", sub: "home" };
  return { tab: tabs[0].id, sub: tabs[0].items[0].id };
}

export function findItem(tabId, subId) {
  const tab = NAV.find((t) => t.id === tabId);
  return (tab?.items || []).find((i) => i.id === subId) || null;
}
