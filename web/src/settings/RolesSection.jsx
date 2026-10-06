import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { can, groupedPermissions } from "../theme";
import { EmptyCard } from "../FilterBar";

function samePerms(a, b) {
  const left = [...new Set(a || [])].sort();
  const right = [...new Set(b || [])].sort();
  return left.length === right.length && left.every((name, i) => name === right[i]);
}

function permCount(role, all) {
  const allowed = new Set(all || []);
  return (role.permissions || []).filter((p) => allowed.has(p)).length;
}

function patchRole(roles, name, permissions) {
  return roles.map((r) => (r.name === name ? { ...r, permissions } : r));
}

function RoleNav({ roles, all, saved, selected, onSelect }) {
  return (
    <nav className="card list-panel role-nav" aria-label="Roles">
      {roles.map((role) => {
        const dirty = !samePerms(role.permissions, saved[role.name]);
        const n = permCount(role, all);
        return (
          <button
            type="button"
            key={role.name}
            className={"role-nav-item" + (selected === role.name ? " on" : "")}
            onClick={() => onSelect(role.name)}
          >
            <span className="role-nav-name">{role.name}</span>
            <span className="role-nav-meta">
              {dirty ? <span className="pill warn">Unsaved</span> : null}
              <span className="quiet">{n}/{all.length}</span>
            </span>
          </button>
        );
      })}
    </nav>
  );
}

function PermEditor({ role, all, groups, dirty, saving, msg, err, canManage, onToggle, onSetGroup, onSave }) {
  const have = new Set(role.permissions || []);
  const n = permCount(role, all);
  const pct = all.length ? Math.round((n / all.length) * 100) : 0;
  return (
    <div className="card list-panel role-editor">
      <div className="table-card-head">
        <div>
          <h3>{role.name}</h3>
          <p className="muted">{n} of {all.length} {all.length === 1 ? "permission" : "permissions"}{canManage ? "" : " · View only"}</p>
          {all.length ? (
            <div className="progress-bar perm-progress" aria-hidden="true">
              <span style={{ width: pct + "%" }} />
            </div>
          ) : null}
        </div>
        <div className="perm-actions">
          {canManage && dirty ? <span className="pill warn">Unsaved</span> : null}
          {canManage ? (
            <button type="button" disabled={!dirty || saving} onClick={() => onSave(role)}>
              {saving ? "Saving…" : "Save permissions"}
            </button>
          ) : null}
        </div>
      </div>
      {msg ? <p className="ok">{msg}</p> : null}
      {err ? <p className="err">{err}</p> : null}
      <div className="perm-grid">
        {groups.map((group) => {
          const ids = group.perms.map((p) => p.id);
          const onCount = ids.filter((id) => have.has(id)).length;
          const full = ids.length > 0 && onCount === ids.length;
          const empty = onCount === 0;
          return (
            <section
              key={group.id}
              className={"perm-card" + (full ? " full" : empty ? " empty" : "") + (ids.length > 4 ? " wide" : "")}
            >
              <div className="perm-card-head">
                {canManage ? (
                  <button
                    type="button"
                    className="ghost perm-card-toggle"
                    onClick={() => onSetGroup(role.name, ids, !full)}
                    title={full ? "Clear " + group.label : "Grant all " + group.label}
                  >
                    <h4>{group.label}</h4>
                  </button>
                ) : (
                  <h4>{group.label}</h4>
                )}
                <span className="quiet">{onCount}/{ids.length}</span>
              </div>
              <div className="perm-chips">
                {group.perms.map((perm) => {
                  const on = have.has(perm.id);
                  return (
                    <button
                      type="button"
                      key={perm.id}
                      className={"perm-chip" + (on ? " on" : "")}
                      aria-pressed={on}
                      disabled={!canManage}
                      title={perm.label}
                      onClick={() => onToggle(role.name, perm.id)}
                    >
                      {perm.short || perm.label}
                    </button>
                  );
                })}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}

export default function RolesSection({ user }) {
  const [roles, setRoles] = useState([]);
  const [saved, setSaved] = useState({});
  const [all, setAll] = useState([]);
  const [selected, setSelected] = useState("");
  const [name, setName] = useState("");
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [formErr, setFormErr] = useState("");
  const [formMsg, setFormMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const canManage = can(user, "roles.manage");

  useEffect(() => {
    api.roles().then((d) => {
      const next = d.roles || [];
      setRoles(next);
      setAll(d.all_permissions || []);
      setSaved(Object.fromEntries(next.map((r) => [r.name, [...(r.permissions || [])]])));
      setSelected((current) => (current && next.some((r) => r.name === current) ? current : (next[0]?.name || "")));
    }).catch((e) => setErr(e.message)).finally(() => setLoaded(true));
  }, []);

  const groups = useMemo(() => groupedPermissions(all), [all]);
  const role = roles.find((r) => r.name === selected) || roles[0] || null;
  const dirty = role ? !samePerms(role.permissions, saved[role.name]) : false;

  function toggle(roleName, perm) {
    if (!canManage) return;
    setMsg("");
    setErr("");
    setRoles((prev) => {
      const current = prev.find((r) => r.name === roleName);
      if (!current) return prev;
      const have = current.permissions || [];
      const next = have.includes(perm) ? have.filter((p) => p !== perm) : [...have, perm];
      return patchRole(prev, roleName, next);
    });
  }

  function setGroup(roleName, ids, on) {
    if (!canManage) return;
    setMsg("");
    setErr("");
    setRoles((prev) => {
      const current = prev.find((r) => r.name === roleName);
      if (!current) return prev;
      const next = new Set(current.permissions || []);
      ids.forEach((id) => {
        if (on) next.add(id);
        else next.delete(id);
      });
      return patchRole(prev, roleName, [...next]);
    });
  }

  async function add() {
    setFormErr("");
    setFormMsg("");
    setBusy(true);
    try {
      const created = await api.createRole({ name, permissions: [] });
      setName("");
      setRoles((prev) => [...prev, created]);
      setSaved((prev) => ({ ...prev, [created.name]: [...(created.permissions || [])] }));
      setSelected(created.name);
      setFormMsg("Added " + created.name + ".");
    } catch (e) {
      setFormErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function save(target) {
    setErr("");
    setMsg("");
    setFormErr("");
    setFormMsg("");
    setSaving(true);
    try {
      const stored = await api.saveRole(target.name, target.permissions);
      setRoles((prev) => prev.map((r) => (r.name === stored.name ? stored : r)));
      setSaved((prev) => ({ ...prev, [stored.name]: [...(stored.permissions || [])] }));
      setMsg("Saved " + stored.name + ".");
    } catch (e) {
      setErr(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="workspace-page">
      <div className="page-head">
        <div className="page-head-copy">
          <h2>Roles</h2>
          <p className="muted">{canManage ? "Choose what each role can do. Assign people in Users." : "See what each role can do. Changing permissions needs Manage on Roles."}</p>
        </div>
        <span className="page-stat">{roles.length} {roles.length === 1 ? "role" : "roles"}</span>
      </div>
      {canManage ? (
      <div className="card">
        <h3>Add role</h3>
        <p className="muted">Create a role, then choose what it can do.</p>
        <div className="add-role-row">
          <div>
            <label>Name</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Auditor"
              onKeyDown={(e) => { if (e.key === "Enter" && name.trim()) add(); }}
            />
          </div>
          <button type="button" disabled={busy || !name.trim()} onClick={add}>{busy ? "Adding…" : "Add role"}</button>
        </div>
        {formMsg ? <p className="ok">{formMsg}</p> : null}
        {formErr ? <p className="err">{formErr}</p> : null}
      </div>
      ) : null}
      {!loaded ? <EmptyCard title="Loading roles" copy="Pulling roles and what they can do." /> : null}
      {loaded && !roles.length ? <EmptyCard title="No roles yet" copy="Add a role, then choose what it can do." /> : null}
      {role ? (
        <div className="roles-layout">
          <RoleNav
            roles={roles}
            all={all}
            saved={saved}
            selected={role.name}
            onSelect={(name) => { setSelected(name); setMsg(""); setErr(""); }}
          />
          <PermEditor
            role={role}
            all={all}
            groups={groups}
            dirty={dirty}
            saving={saving}
            msg={msg}
            err={err}
            canManage={canManage}
            onToggle={toggle}
            onSetGroup={setGroup}
            onSave={save}
          />
        </div>
      ) : null}
      {!role && err ? <p className="err">{err}</p> : null}
    </div>
  );
}
