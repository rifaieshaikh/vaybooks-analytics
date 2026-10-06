import { useEffect, useState } from "react";
import { api } from "../api";

export default function NetworkSection() {
  const [info, setInfo] = useState(null);
  const [copied, setCopied] = useState("");

  useEffect(() => {
    api.info().then(setInfo).catch(() => {});
  }, []);

  async function copy(url) {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(url);
    } catch {
      setCopied("");
    }
  }

  const urls = info?.lan_urls || [];
  return (
    <div className="card">
      <h2>Network</h2>
      <p className="muted">This PC serves Vay Reports on the LAN. Other devices should use a browser — they do not need the desktop app installed.</p>
      {urls.length ? (
        <ul className="lan-list">
          {urls.map((url) => (
            <li key={url}>
              <code>{url}</code>
              <button type="button" className="secondary" onClick={() => copy(url)}>{copied === url ? "Copied" : "Copy"}</button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted">No LAN address found. Check this PC is on Wi‑Fi or Ethernet.</p>
      )}
      {info?.port ? <p className="muted">API port {info.port}. MongoDB stays on this PC only.</p> : null}
    </div>
  );
}
