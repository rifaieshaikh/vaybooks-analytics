import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { can } from "../theme";
import { FilterBar, SortTh, toggleSort } from "../FilterBar";

function UsersTable({ users, roles, filters, setFilters, sort, dir, setSort, setDir, refresh, setErr, canManage }) {
  const shown = useMemo(() => {
    const rows = users.filter((u) => {
      if (filters.role && u.role !== filters.role) return false;
      if (filters.status === "Active" && !u.enabled) return false;
      if (filters.status === "Disabled" && u.enabled) return false;
      return true;
    });
    const copy = rows.slice();
    copy.sort((a, b) => {
      const av = sort === "status" ? (a.enabled ? "Active" : "Disabled") : a[sort];
      const bv = sort === "status" ? (b.enabled ? "Active" : "Disabled") : b[sort];
      const cmp = String(av || "").localeCompare(String(bv || ""));
      return dir === "desc" ? -cmp : cmp;
    });
    return copy;
  }, [users, filters, sort, dir]);

  function onSort(id) {
    const next = toggleSort(sort, dir, id, []);
    setSort(next.sort);
    setDir(next.dir);
  }

  return (
    <div className="workspace-page">
      <div className="page-head">
        <div className="page-head-copy">
          <h2>Users</h2>
          <p className="muted">Filter and sort the people who can sign in.</p>
        </div>
        <span className="page-stat">{shown.length} {shown.length === 1 ? "user" : "users"}</span>
      </div>
      <FilterBar
        filters={filters}
        options={{ role: roles, status: ["Active", "Disabled"] }}
        onChange={setFilters}
        fields={[{ key: "role", label: "Role" }, { key: "status", label: "Status" }]}
      />
      <div className="card table-card list-panel">
        <table className={"dense list-table" + (canManage ? "" : " compact")}>
          <thead>
            <tr>
              <SortTh id="username" label="Username" sort={sort} dir={dir} onSort={onSort} />
              <SortTh id="role" label="Role" sort={sort} dir={dir} onSort={onSort} />
              <SortTh id="status" label="Status" sort={sort} dir={dir} onSort={onSort} />
              <th>Sales reps</th>
              {canManage ? <th></th> : null}
            </tr>
          </thead>
          <tbody>
            {shown.map((u) => (
              <tr key={u.username}>
                <td>{u.username}</td>
                <td>
                  {canManage ? (
                    <select value={u.role} onChange={(e) => api.patchUser(u.username, { role: e.target.value }).then(refresh).catch((err) => setErr(err.message))}>
                      {(roles.length ? roles : ["Admin"]).map((r) => <option key={r}>{r}</option>)}
                    </select>
                  ) : u.role}
                </td>
                <td><span className={u.enabled ? "pill ok" : "pill err"}>{u.enabled ? "Active" : "Disabled"}</span></td>
                <td>
                  {canManage ? (
                    <input
                      key={(u.sales_reps || []).join(",")}
                      defaultValue={(u.sales_reps || []).join(", ")}
                      placeholder="Asha, Rita"
                      aria-label={"Sales reps for " + u.username}
                      onBlur={(e) => {
                        const sales_reps = e.target.value.split(",").map((name) => name.trim()).filter(Boolean);
                        const current = (u.sales_reps || []).join(", ");
                        if (sales_reps.join(", ") === current) return;
                        api.patchUser(u.username, { sales_reps }).then(refresh).catch((err) => setErr(err.message));
                      }}
                    />
                  ) : (u.sales_reps || []).join(", ") || "—"}
                </td>
                {canManage ? (
                <td>
                  <button className="secondary" onClick={() => {
                    const next = window.prompt("New password for " + u.username);
                    if (next) api.patchUser(u.username, { password: next }).then(refresh).catch((err) => setErr(err.message));
                  }}>Reset password</button>{" "}
                  <button className="secondary" onClick={() => api.patchUser(u.username, { enabled: !u.enabled }).then(refresh).catch((err) => setErr(err.message))}>
                    {u.enabled ? "Disable" : "Enable"}
                  </button>{" "}
                  <button className="danger" onClick={() => {
                    if (window.confirm("Delete " + u.username + "?")) api.deleteUser(u.username).then(refresh).catch((err) => setErr(err.message));
                  }}>Delete</button>
                </td>
                ) : null}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function UsersSection({ user }) {
  const [users, setUsers] = useState([]);
  const [roles, setRoles] = useState([]);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("Viewer");
  const [err, setErr] = useState("");
  const [filters, setFilters] = useState({ role: "", status: "" });
  const [sort, setSort] = useState("username");
  const [dir, setDir] = useState("asc");
  const canManage = can(user, "users.manage");

  function refresh() {
    api.users().then((d) => setUsers(d.users || [])).catch((e) => setErr(e.message));
    api.roles().then((d) => setRoles((d.roles || []).map((r) => r.name))).catch(() => {});
  }
  useEffect(refresh, []);

  async function create() {
    setErr("");
    try {
      await api.createUser({ username, password, role });
      setUsername("");
      setPassword("");
      refresh();
    } catch (e) {
      setErr(e.message);
    }
  }

  const roleOptions = roles.length ? roles : [...new Set(users.map((u) => u.role).filter(Boolean))];

  return (
    <div>
      {canManage ? (
      <div className="card">
        <h2>Add user</h2>
        <div className="row">
          <div><label>Username</label><input value={username} onChange={(e) => setUsername(e.target.value)} /></div>
          <div><label>Password</label><input type="password" value={password} onChange={(e) => setPassword(e.target.value)} /></div>
          <div>
            <label>Role</label>
            <select value={role} onChange={(e) => setRole(e.target.value)}>
              {(roleOptions.length ? roleOptions : ["Admin", "Sales", "Finance", "Warehouse", "Viewer"]).map((r) => <option key={r}>{r}</option>)}
            </select>
          </div>
        </div>
        <button onClick={create}>Create user</button>
        {err ? <p className="err">{err}</p> : null}
      </div>
      ) : null}
      {!canManage && err ? <p className="err">{err}</p> : null}
      <UsersTable users={users} roles={roleOptions} filters={filters} setFilters={setFilters} sort={sort} dir={dir} setSort={setSort} setDir={setDir} refresh={refresh} setErr={setErr} canManage={canManage} />
    </div>
  );
}
