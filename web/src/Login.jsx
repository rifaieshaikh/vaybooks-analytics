import { useEffect, useState } from "react";
import { api } from "./api";

export default function LoginPage({ onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [info, setInfo] = useState(null);

  useEffect(() => {
    api.info().then(setInfo).catch(() => {});
  }, []);

  async function submit(ev) {
    ev.preventDefault();
    setErr("");
    setBusy(true);
    try {
      const user = await api.login(username, password);
      onLogin(user);
    } catch (e) {
      setErr(e.message || "Could not sign in.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <form className="card login-card" onSubmit={submit}>
        <h2>Vay Reports</h2>
        <p className="muted">Sign in to continue.</p>
        <p className="muted">First install: change the Admin password when prompted.</p>
        <label>Username</label>
        <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
        <label>Password</label>
        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
        {err ? <p className="err">{err}</p> : null}
        <button disabled={busy} type="submit">Sign in</button>
        {info?.lan_urls?.length ? (
          <div className="lan-box">
            <p className="muted">On this network, open:</p>
            {info.lan_urls.map((url) => (
              <p key={url}><code>{url}</code></p>
            ))}
          </div>
        ) : null}
      </form>
    </div>
  );
}
