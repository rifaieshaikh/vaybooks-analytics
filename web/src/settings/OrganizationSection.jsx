import { useEffect, useMemo, useRef, useState } from "react";
import SectionTabs, { rememberedTab } from "../SectionTabs";
import { api } from "../api";

const MONTHS = [
  { value: 1, label: "January" },
  { value: 2, label: "February" },
  { value: 3, label: "March" },
  { value: 4, label: "April" },
  { value: 5, label: "May" },
  { value: 6, label: "June" },
  { value: 7, label: "July" },
  { value: 8, label: "August" },
  { value: 9, label: "September" },
  { value: 10, label: "October" },
  { value: 11, label: "November" },
  { value: 12, label: "December" },
];

const TARGET_KEYS = [
  ["sales_mtd", "Sales"],
  ["collections_mtd", "Collections"],
  ["ar_balance", "Outstanding"],
];

const TERM_KEYS = [
  ["customer", "Customer"],
  ["party", "Party"],
  ["outstanding", "Outstanding"],
  ["sales_rep", "Sales rep"],
  ["group", "Group"],
  ["item", "Item"],
];

function normName(value) {
  return String(value || "").trim().toLowerCase();
}

function isCustomerParty(row) {
  const id = normName(row.party_type);
  const label = normName(row.party_type_label);
  return id === "customer" || label === "customer";
}

function categoriesFromMap(map) {
  return Object.entries(map || {}).map(([name, accounts]) => ({
    name,
    accounts: Array.isArray(accounts) ? accounts.map(String) : [],
  }));
}

function mapFromCategories(rows) {
  const out = {};
  for (const row of rows) {
    const name = String(row.name || "").trim();
    if (!name) continue;
    out[name] = (row.accounts || []).map((a) => String(a).trim()).filter(Boolean);
  }
  return out;
}

async function loadAllParties() {
  const parties = [];
  let page = 1;
  for (;;) {
    const data = await api.rows({ type: "party", limit: 200, page, sort: "party", dir: "asc" });
    const batch = data.rows || [];
    parties.push(...batch);
    if (parties.length >= (data.total || 0) || !batch.length) break;
    page += 1;
    if (page > 50) break;
  }
  const byName = new Map();
  for (const row of parties) {
    const name = String(row.party || "").trim();
    if (!name) continue;
    if (!byName.has(normName(name))) byName.set(normName(name), { name, party_type: row.party_type, party_type_label: row.party_type_label });
  }
  return [...byName.values()].sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: "base" }));
}

/** Multi-select dropdown: selected chips + searchable checklist of eligible parties. */
function PartyMultiSelect({ selected, options, disabled, onChange }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const rootRef = useRef(null);
  const selectedSet = useMemo(() => new Set((selected || []).map(normName)), [selected]);

  useEffect(() => {
    if (!open) return undefined;
    function onDoc(e) {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const filtered = useMemo(() => {
    const q = normName(query);
    return (options || []).filter((p) => !q || normName(p.name).includes(q));
  }, [options, query]);

  function toggle(name) {
    const key = normName(name);
    if (selectedSet.has(key)) {
      onChange((selected || []).filter((a) => normName(a) !== key));
    } else {
      onChange([...(selected || []), name]);
    }
  }

  function remove(name) {
    onChange((selected || []).filter((a) => normName(a) !== normName(name)));
  }

  return (
    <div className="party-multiselect" ref={rootRef}>
      <div
        className={"party-multiselect-box" + (open ? " open" : "") + (disabled ? " disabled" : "")}
        role="combobox"
        aria-expanded={open}
        aria-haspopup="listbox"
        onClick={() => {
          if (!disabled) setOpen(true);
        }}
      >
        {(selected || []).length ? (
          <div className="chips" style={{ margin: 0 }}>
            {(selected || []).map((name) => (
              <span key={name} className="chip">
                {name}
                <button
                  type="button"
                  disabled={disabled}
                  aria-label={"Remove " + name}
                  onClick={(e) => {
                    e.stopPropagation();
                    remove(name);
                  }}
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        ) : (
          <span className="muted">Select parties…</span>
        )}
        <input
          className="party-multiselect-search"
          value={query}
          disabled={disabled}
          placeholder={(selected || []).length ? "Search…" : "Search parties…"}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onClick={(e) => e.stopPropagation()}
        />
      </div>
      {open && !disabled ? (
        <div className="party-multiselect-menu" role="listbox" aria-multiselectable="true">
          {filtered.length ? (
            filtered.map((p) => {
              const checked = selectedSet.has(normName(p.name));
              return (
                <label key={p.name} className={"party-multiselect-option" + (checked ? " on" : "")}>
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggle(p.name)}
                  />
                  <span>{p.name}</span>
                  {p.party_type_label ? <span className="muted">{p.party_type_label}</span> : null}
                </label>
              );
            })
          ) : (
            <p className="muted" style={{ margin: 0, padding: "8px 10px" }}>
              {query.trim() ? "No matching eligible parties." : "No eligible parties left."}
            </p>
          )}
        </div>
      ) : null}
    </div>
  );
}

export default function OrganizationSection() {
  const [policy, setPolicy] = useState(null);
  const [categories, setCategories] = useState([]);
  const [pack, setPack] = useState("vay_wholesale");
  const [parties, setParties] = useState([]);
  const [sectionTab, setSectionTab] = useState(() => rememberedTab("org-section", "policy", ["policy", "expenses"]));
  const [catTab, setCatTab] = useState(() => {
    const stored = Number(rememberedTab("expense-cat", "0"));
    return Number.isFinite(stored) ? stored : 0;
  });
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [partiesErr, setPartiesErr] = useState("");

  useEffect(() => {
    Promise.all([api.orgPolicy(), api.expenseCategories()])
      .then(([p, e]) => {
        setPolicy(p);
        setPack(e.pack || "vay_wholesale");
        const cats = categoriesFromMap(e.categories || {});
        setCategories(cats);
        setCatTab(0);
      })
      .catch((e) => setErr(e.message));
    loadAllParties()
      .then(setParties)
      .catch((e) => setPartiesErr(e.message || "Could not load parties"));
  }, []);

  useEffect(() => {
    if (catTab >= categories.length) setCatTab(Math.max(0, categories.length - 1));
  }, [categories.length, catTab]);

  const takenElsewhere = useMemo(() => {
    const map = new Map();
    categories.forEach((cat, idx) => {
      (cat.accounts || []).forEach((name) => {
        const key = normName(name);
        if (!key) return;
        if (!map.has(key)) map.set(key, idx);
      });
    });
    return map;
  }, [categories]);

  function optionsForCategory(idx) {
    const selected = categories[idx]?.accounts || [];
    const selectedKeys = new Set(selected.map(normName));
    const eligible = parties.filter((p) => {
      if (isCustomerParty(p)) return false;
      const key = normName(p.name);
      const owner = takenElsewhere.get(key);
      if (owner !== undefined && owner !== idx) return false;
      return true;
    });
    // Keep orphan / legacy names already on this category visible even if not in party master
    const known = new Set(eligible.map((p) => normName(p.name)));
    for (const name of selected) {
      if (!known.has(normName(name))) {
        eligible.push({ name, party_type: "", party_type_label: "Current" });
        known.add(normName(name));
      }
    }
    return eligible.sort((a, b) => {
      const aSel = selectedKeys.has(normName(a.name)) ? 0 : 1;
      const bSel = selectedKeys.has(normName(b.name)) ? 0 : 1;
      if (aSel !== bSel) return aSel - bSel;
      return a.name.localeCompare(b.name, undefined, { sensitivity: "base" });
    });
  }

  function patch(field, value) {
    setPolicy((prev) => ({ ...(prev || {}), [field]: value }));
  }

  function patchTerm(key, value) {
    setPolicy((prev) => ({
      ...(prev || {}),
      terminology: { ...((prev && prev.terminology) || {}), [key]: value },
    }));
  }

  function updateCategory(idx, patchObj) {
    setCategories((prev) => prev.map((row, i) => (i === idx ? { ...row, ...patchObj } : row)));
  }

  function addCategory() {
    setCategories((prev) => {
      const next = [...prev, { name: "", accounts: [] }];
      setCatTab(next.length - 1);
      return next;
    });
  }

  function removeCategory(idx) {
    setCategories((prev) => {
      const next = prev.filter((_, i) => i !== idx);
      setCatTab((t) => Math.min(t, Math.max(0, next.length - 1)));
      return next;
    });
  }

  async function savePolicy() {
    if (!policy || busy) return;
    setBusy(true);
    setErr("");
    setMsg("");
    try {
      const out = await api.setOrgPolicy({
        fiscal_year_start_month: Number(policy.fiscal_year_start_month),
        timezone: policy.timezone,
        currency_code: policy.currency_code,
        currency_symbol: policy.currency_symbol,
        sales_tax_inclusive_rate: Number(policy.sales_tax_inclusive_rate),
        ar_balance_tolerance: Number(policy.ar_balance_tolerance ?? 0.5),
        expense_pack: policy.expense_pack || pack,
        terminology: policy.terminology || {},
        targets: policy.targets || {},
        thresholds: policy.thresholds || {},
        weekly_run: Boolean(policy.weekly_run),
        wholesale_pack: Boolean(policy.wholesale_pack),
        retail_pack: Boolean(policy.retail_pack),
        custom_columns: policy.custom_columns || [],
      });
      setPolicy(out);
      setMsg("Organization policy saved.");
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function saveExpenses() {
    if (busy) return;
    setBusy(true);
    setErr("");
    setMsg("");
    try {
      if (categories.some((c) => !String(c.name || "").trim())) {
        throw new Error("Every category needs a name (or remove empty ones).");
      }
      const names = categories.map((c) => String(c.name || "").trim());
      if (new Set(names).size !== names.length) {
        throw new Error("Category names must be unique.");
      }
      const payload = mapFromCategories(categories);
      const out = await api.setExpenseCategories({ categories: payload, pack });
      setCategories(categoriesFromMap(out.categories || {}));
      setPack(out.pack || pack);
      setMsg("Expense categories saved.");
    } catch (e) {
      setErr(e.message || "Could not save expense categories");
    } finally {
      setBusy(false);
    }
  }

  if (!policy) {
    return <div className="card">{err || "Loading organization settings…"}</div>;
  }

  const safeCat = categories.length ? Math.min(Math.max(0, catTab), categories.length - 1) : 0;
  const active = categories[safeCat];

  return (
    <div className="card stack">
      <h2>Organization</h2>
      <p className="muted">
        Fiscal year, timezone, currency, tax, labels, and expense category ↔ party maps.
      </p>
      {err ? <p className="err">{err}</p> : null}
      {msg ? <p className="ok">{msg}</p> : null}

      <SectionTabs
        label="Organization sections"
        storageKey="org-section"
        value={sectionTab}
        onChange={setSectionTab}
        tabs={[
          { id: "policy", label: "Policy" },
          { id: "expenses", label: "Expense categories" },
        ]}
      />

      <div className="tab-panel">
        {sectionTab === "policy" ? (
          <div className="stack">
            <div className="form-grid">
              <label>
                Fiscal year starts
                <select
                  value={policy.fiscal_year_start_month || 4}
                  onChange={(e) => patch("fiscal_year_start_month", Number(e.target.value))}
                >
                  {MONTHS.map((m) => (
                    <option key={m.value} value={m.value}>{m.label}</option>
                  ))}
                </select>
              </label>
              <label>
                Timezone
                <input value={policy.timezone || ""} onChange={(e) => patch("timezone", e.target.value)} />
              </label>
              <label>
                Currency code
                <input value={policy.currency_code || ""} onChange={(e) => patch("currency_code", e.target.value)} />
              </label>
              <label>
                Currency symbol
                <input value={policy.currency_symbol || ""} onChange={(e) => patch("currency_symbol", e.target.value)} />
              </label>
              <label>
                Inclusive sales tax rate
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  max="1"
                  value={policy.sales_tax_inclusive_rate ?? 0.18}
                  onChange={(e) => patch("sales_tax_inclusive_rate", e.target.value)}
                />
              </label>
              <label>
                Ledger vs outstanding tolerance (₹)
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={policy.ar_balance_tolerance ?? 0.5}
                  onChange={(e) => patch("ar_balance_tolerance", e.target.value)}
                />
              </label>
            </div>
            <p className="muted">
              A customer is flagged when sales minus collection differs from outstanding by at least this amount. Zero flags any difference.
            </p>

            <div className="policy-block">
            <h3>Thresholds</h3>
            <p className="muted">Crossing a threshold suggests an action. It is not saved until someone assigns it.</p>
            <div className="form-grid">
              <label>
                Overdue amount
                <input
                  type="number"
                  value={(policy.thresholds && policy.thresholds.overdue_amount != null) ? policy.thresholds.overdue_amount : ""}
                  onChange={(e) => {
                    const raw = e.target.value;
                    setPolicy((prev) => {
                      const thresholds = { ...((prev && prev.thresholds) || {}) };
                      if (raw === "") delete thresholds.overdue_amount;
                      else thresholds.overdue_amount = Number(raw);
                      return { ...prev, thresholds };
                    });
                  }}
                />
              </label>
              <label>
                Cover days
                <input
                  type="number"
                  value={(policy.thresholds && policy.thresholds.cover_days != null) ? policy.thresholds.cover_days : ""}
                  onChange={(e) => {
                    const raw = e.target.value;
                    setPolicy((prev) => {
                      const thresholds = { ...((prev && prev.thresholds) || {}) };
                      if (raw === "") delete thresholds.cover_days;
                      else thresholds.cover_days = Number(raw);
                      return { ...prev, thresholds };
                    });
                  }}
                />
              </label>
            </div>
            <label className="check-line">
              <input
                type="checkbox"
                checked={Boolean(policy.weekly_run)}
                onChange={(e) => patch("weekly_run", e.target.checked)}
              />
              Create one report each week while this app is open
            </label>
            </div>

            <div className="policy-block">
            <h3>Targets</h3>
            <p className="muted">Optional. The scorecard shows “No target” for a metric left blank.</p>
            <div className="form-grid">
              {TARGET_KEYS.map(([key, label]) => (
                <label key={key}>
                  {label}
                  <input
                    type="number"
                    step="0.01"
                    value={(policy.targets && policy.targets[key] != null) ? policy.targets[key] : ""}
                    onChange={(e) => {
                      const raw = e.target.value;
                      setPolicy((prev) => {
                        const targets = { ...((prev && prev.targets) || {}) };
                        if (raw === "") delete targets[key];
                        else targets[key] = Number(raw);
                        return { ...prev, targets };
                      });
                    }}
                  />
                </label>
              ))}
            </div>
            </div>

            <div className="policy-block">
            <h3>Wholesale pack</h3>
            <p className="muted">Turning this on copies salesperson, overdue, and short-cover templates as drafts. It does not change expense account names.</p>
            <label className="check-line">
              <input
                type="checkbox"
                checked={Boolean(policy.wholesale_pack)}
                onChange={(e) => patch("wholesale_pack", e.target.checked)}
              />
              Use the wholesale pack
            </label>
            </div>

            <div className="policy-block">
            <h3>Retail pack</h3>
            <p className="muted">Turning this on copies returns and repeat-customer templates as drafts. The expense map stays empty.</p>
            <label className="check-line">
              <input
                type="checkbox"
                checked={Boolean(policy.retail_pack)}
                onChange={(e) => patch("retail_pack", e.target.checked)}
              />
              Use the retail pack
            </label>
            </div>

            <div className="policy-block">
            <h3>Custom columns</h3>
            <p className="muted">Name a column that already exists on imported customer or product rows. A blank value stays blank.</p>
            <div className="form-grid">
              <label>
                Customer column
                <input
                  value={((policy.custom_columns || []).find((col) => col.entity === "customer") || {}).header || ""}
                  onChange={(e) => {
                    const header = e.target.value;
                    setPolicy((prev) => {
                      const rest = ((prev && prev.custom_columns) || []).filter((col) => col.entity !== "customer");
                      const custom_columns = header.trim() ? rest.concat([{ entity: "customer", header }]) : rest;
                      return { ...prev, custom_columns };
                    });
                  }}
                />
              </label>
              <label>
                Product column
                <input
                  value={((policy.custom_columns || []).find((col) => col.entity === "product") || {}).header || ""}
                  onChange={(e) => {
                    const header = e.target.value;
                    setPolicy((prev) => {
                      const rest = ((prev && prev.custom_columns) || []).filter((col) => col.entity !== "product");
                      const custom_columns = header.trim() ? rest.concat([{ entity: "product", header }]) : rest;
                      return { ...prev, custom_columns };
                    });
                  }}
                />
              </label>
            </div>
            </div>

            <div className="policy-block">
            <h3>Terminology</h3>
            <div className="form-grid">
              {TERM_KEYS.map(([key, label]) => (
                <label key={key}>
                  {label}
                  <input
                    value={(policy.terminology && policy.terminology[key]) || ""}
                    onChange={(e) => patchTerm(key, e.target.value)}
                  />
                </label>
              ))}
            </div>
            </div>
            <button type="button" disabled={busy} onClick={savePolicy}>Save organization policy</button>
          </div>
        ) : null}

        {sectionTab === "expenses" ? (
          <div className="stack">
            <p className="muted">
              Each tab is a category. Pick non-customer parties that are not already mapped to another category.
              Seeded from pack <code>{pack}</code> on first load.
            </p>
            {partiesErr ? <p className="err">{partiesErr}</p> : null}

            <SectionTabs
              label="Expense categories"
              storageKey="expense-cat"
              value={safeCat}
              onChange={(id) => setCatTab(id)}
              tabs={categories.map((cat, idx) => ({
                id: idx,
                label: cat.name.trim() || "Untitled",
                title: cat.name || "Untitled",
                count: (cat.accounts || []).length || null,
              }))}
              trailing={(
                <button type="button" className="secondary" disabled={busy} onClick={addCategory}>
                  + Add
                </button>
              )}
            />

            {active ? (
              <div className="tab-panel" style={{ paddingTop: 12 }}>
                <div className="row gap" style={{ alignItems: "flex-end", flexWrap: "wrap" }}>
                  <label className="grow" style={{ flex: 1, minWidth: 200 }}>
                    Category name
                    <input
                      value={active.name}
                      onChange={(e) => updateCategory(safeCat, { name: e.target.value })}
                      placeholder="e.g. Office Expenses"
                    />
                  </label>
                  <button type="button" className="secondary" disabled={busy} onClick={() => removeCategory(safeCat)}>
                    Remove category
                  </button>
                </div>

                <label style={{ display: "block", marginTop: 12 }}>
                  Parties
                  <PartyMultiSelect
                    selected={active.accounts || []}
                    options={optionsForCategory(safeCat)}
                    disabled={busy}
                    onChange={(next) => updateCategory(safeCat, { accounts: next })}
                  />
                </label>
                <p className="muted" style={{ marginTop: 6 }}>
                  Customers and parties already used on other categories are hidden from this list.
                </p>
              </div>
            ) : (
              <p className="muted">No categories yet. Click + Add to create one.</p>
            )}

            <div className="row gap" style={{ flexWrap: "wrap" }}>
              <button type="button" disabled={busy || !categories.length} onClick={saveExpenses}>
                Save expense categories
              </button>
            </div>

            <details>
              <summary className="muted">Advanced: pack id</summary>
              <label>
                Pack id
                <input value={pack} onChange={(e) => setPack(e.target.value)} />
              </label>
            </details>
          </div>
        ) : null}
      </div>
    </div>
  );
}
