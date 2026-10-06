import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";

async function loadAccountNames() {
  const data = await api.customers({ limit: "1", page: "1" });
  const names = (data.options && data.options.party) || [];
  return [...names].sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));
}

function SearchableSelect({ value, options, onChange, disabled, placeholder }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const rootRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    function onDoc(e) {
      if (rootRef.current && !rootRef.current.contains(e.target)) {
        setOpen(false);
        setQuery("");
      }
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (options || []).filter((name) => !q || name.toLowerCase().includes(q));
  }, [options, query]);

  useEffect(() => {
    setActive(0);
  }, [query, open]);

  function close() {
    setOpen(false);
    setQuery("");
  }

  function pick(name) {
    onChange(name);
    close();
  }

  function onKeyDown(e) {
    if (disabled) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setActive((i) => Math.min(i + 1, Math.max(filtered.length - 1, 0)));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setOpen(true);
      setActive((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" && open) {
      e.preventDefault();
      if (filtered[active]) pick(filtered[active]);
    } else if (e.key === "Escape") {
      e.preventDefault();
      close();
    }
  }

  return (
    <div className="account-select" ref={rootRef}>
      <input
        role="combobox"
        aria-expanded={open}
        aria-autocomplete="list"
        value={open ? query : value}
        placeholder={open && value ? value : (placeholder || "Search accounts")}
        disabled={disabled}
        autoComplete="off"
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
        onFocus={() => {
          if (disabled) return;
          setQuery("");
          setOpen(true);
        }}
        onKeyDown={onKeyDown}
      />
      {open && !disabled ? (
        <div className="account-select-menu" role="listbox">
          {filtered.length ? filtered.map((name, i) => (
            <button
              type="button"
              key={name}
              role="option"
              aria-selected={name === value}
              className={"account-select-option" + (i === active || name === value ? " on" : "")}
              onMouseEnter={() => setActive(i)}
              onClick={() => pick(name)}
            >
              {name}
            </button>
          )) : (
            <p className="muted account-select-empty">No matching accounts.</p>
          )}
        </div>
      ) : null}
    </div>
  );
}

export default function AccountNamesSection() {
  const [aliases, setAliases] = useState([]);
  const [names, setNames] = useState([]);
  const [open, setOpen] = useState(false);
  const [source, setSource] = useState("");
  const [destination, setDestination] = useState("");
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  function load() {
    return Promise.all([api.accountAliases(), loadAccountNames()])
      .then(([data, accounts]) => {
        setAliases(data.aliases || []);
        setNames(accounts);
      })
      .catch((e) => setErr(e.message));
  }

  useEffect(() => {
    load();
  }, []);

  const sources = useMemo(() => new Set(aliases.map((row) => row.source.toLowerCase())), [aliases]);
  const oldOptions = names.filter((name) => !sources.has(name.toLowerCase()));
  const newOptions = names.filter((name) => name !== source);

  function close() {
    setOpen(false);
    setSource("");
    setDestination("");
  }

  async function merge(e) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    setMsg("");
    try {
      const out = await api.migrateAccount({ source, destination });
      setAliases(out.aliases || []);
      close();
      setMsg(out.source + " now stays on " + out.destination + ". Later imports of the old name use the new account.");
      const accounts = await loadAccountNames();
      setNames(accounts);
    } catch (ex) {
      setErr(ex.message);
    } finally {
      setBusy(false);
    }
  }

  async function remove(name) {
    setBusy(true);
    setErr("");
    setMsg("");
    try {
      const out = await api.removeAccountAlias(name);
      setAliases(out.aliases || []);
      setMsg("Stopped rewriting " + name + ". Rows already moved stay on the new account.");
    } catch (ex) {
      setErr(ex.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card stack">
      <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
        <h2 style={{ margin: 0 }}>Account migrations</h2>
        <button type="button" onClick={() => { setErr(""); setOpen(true); }}>Add</button>
      </div>
      <p className="muted">
        Move one existing account onto another. Sales, collections, outstanding, and notes follow the new name.
        The old name is remembered, so the next import still lands on the new account.
        Both names must already exist. Removing a row stops future rewrites and does not undo rows already moved.
      </p>
      {msg ? <p className="ok">{msg}</p> : null}
      {err && !open ? <p className="err">{err}</p> : null}
      {aliases.length ? (
        <table className="dense list-table">
          <thead>
            <tr>
              <th>Old account</th>
              <th>New account</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {aliases.map((row) => (
              <tr key={row.source}>
                <td>{row.source}</td>
                <td>{row.destination}</td>
                <td>
                  <button type="button" className="secondary" disabled={busy} onClick={() => remove(row.source)}>
                    Remove
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : <p className="muted">No migrations yet.</p>}

      {open ? (
        <div className="modal-backdrop" onClick={close}>
          <form className="modal confirm-modal" onClick={(e) => e.stopPropagation()} onSubmit={merge}>
            <h3>Add migration</h3>
            <p className="muted">Choose two accounts that already exist. A new name cannot be typed in.</p>
            <div className="stack">
              <label>
                Old account
                <SearchableSelect
                  value={source}
                  options={oldOptions}
                  disabled={busy}
                  onChange={(name) => { setSource(name); if (name === destination) setDestination(""); }}
                />
              </label>
              <label>
                New account
                <SearchableSelect
                  value={destination}
                  options={newOptions}
                  disabled={busy || !source}
                  onChange={setDestination}
                />
              </label>
            </div>
            {err ? <p className="err">{err}</p> : null}
            <div className="modal-actions">
              <button type="button" className="secondary" onClick={close} disabled={busy}>Cancel</button>
              <button type="submit" disabled={busy || !source || !destination || source === destination}>Move account</button>
            </div>
          </form>
        </div>
      ) : null}
    </div>
  );
}
