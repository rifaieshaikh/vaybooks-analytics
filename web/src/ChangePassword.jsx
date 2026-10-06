import { useState } from "react";
import { api } from "./api";

export default function ChangePasswordPage({ user, onChanged }) {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setErr("");
    if (newPassword.length < 8) {
      setErr("New password must be at least 8 characters.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setErr("New passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      await api.changePassword(currentPassword, newPassword);
      const refreshed = await api.me();
      onChanged({ ...user, ...refreshed, must_change_password: false });
    } catch (error) {
      setErr(error.message || "Could not change password.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <form className="card login-card" onSubmit={submit}>
        <h2>Change your password</h2>
        <p className="muted">Choose a private password before continuing to Vay Reports.</p>
        <label>Current password</label>
        <input type="password" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} autoComplete="current-password" />
        <label>New password</label>
        <input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} autoComplete="new-password" />
        <label>Confirm new password</label>
        <input type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} autoComplete="new-password" />
        {err ? <p className="err">{err}</p> : null}
        <button type="submit" disabled={busy}>{busy ? "Saving…" : "Change password"}</button>
      </form>
    </div>
  );
}
