"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Brand from "@/components/Brand";
import ThemeToggle from "@/components/ThemeToggle";
import { ApiError, api } from "@/lib/client";
import { ROLE_CAN, ROLE_LABEL, safeNext } from "@/lib/session-utils";
import type { DemoAccount } from "@/lib/types";

/** The sign-in form plus the list of demo accounts (development only). */
function LoginForm() {
  const search = useSearchParams();
  // Where to go after signing in; safeNext refuses anything that is not a path on this site.
  const next = safeNext(search.get("next"));
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [accounts, setAccounts] = useState<DemoAccount[]>([]);

  useEffect(() => {
    // Already signed in? Go straight on.
    // (The server decides: a leftover cookie that is no longer valid gets a 401 here.)
    fetch("/api/session", { cache: "no-store" })
      .then((r) => { if (r.ok) window.location.replace(next); })
      .catch(() => undefined);
    // The API returns demo accounts only in development; otherwise the list stays empty.
    api.demoAccounts().then(setAccounts).catch(() => setAccounts([]));
  }, [next]);

  /** Post the credentials to /api/session; on success the cookie is set and we move on. */
  async function submit(event: React.FormEvent) {
    event.preventDefault(); // stop the browser's own form submit
    setBusy(true);
    setError(null);
    try {
      const response = await fetch("/api/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new ApiError(response.status, body?.error?.code ?? "error", body?.error?.message ?? "Sign-in failed.");
      }
      // A full page load (not a client-side route) makes the new cookie take effect everywhere.
      window.location.assign(next);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The service is not reachable.");
      setBusy(false);
    }
  }

  return (
    <main className="login">
      <aside className="login-aside">
        <div className="login-brand"><Brand size={36} /><span>Deal Copilot</span></div>
        <h1>Primary markets, in one place.</h1>
        <p>
          Follow a bond new issue from mandate to booking: workflow and approvals, order book and allocation,
          term sheet checks, and an assistant that answers from the data and shows its sources.
        </p>
        <ul className="login-points">
          <li>Role-based access: what you can do depends on who you are</li>
          <li>Every change and every AI answer is written to an audit trail</li>
          <li>The model explains; people decide</li>
        </ul>
        <p className="login-note">All data is synthetic. This is a portfolio project, not a bank system.</p>
      </aside>

      <section className="login-main">
        <div className="login-top"><ThemeToggle /></div>
        <form className="login-card" onSubmit={submit} aria-labelledby="signin-title">
          <h2 id="signin-title">Sign in</h2>
          <p className="muted small">Use one of the demo accounts below.</p>
          {error && <div className="alert" role="alert">{error}</div>}
          <label>Username
            <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" autoCapitalize="none" spellCheck={false} required autoFocus />
          </label>
          <label>Password
            <span className="password">
              <input type={show ? "text" : "password"} value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
              <button type="button" className="ghost" onClick={() => setShow((v) => !v)} aria-pressed={show}>{show ? "Hide" : "Show"}</button>
            </span>
          </label>
          <button className="primary wide" disabled={busy || !username || !password}>{busy ? "Signing in..." : "Sign in"}</button>
        </form>

        {accounts.length > 0 && (
          <div className="login-card demo">
            <h3>Demo accounts</h3>
            <p className="muted small">Pick one to fill in the username. The password is DEMO_USER_PASSWORD from your .env.dev (default in the README).</p>
            <ul>
              {accounts.map((a) => (
                <li key={a.username}>
                  <button type="button" onClick={() => { setUsername(a.username); setPassword(""); }}>
                    <span className="demo-name">{a.display_name.replace(/\s*\(.*\)/, "")} <code>{a.username}</code></span>
                    <span className={`role-badge role-${a.role}`}>{ROLE_LABEL[a.role]}</span>
                    <span className="muted small">{ROLE_CAN[a.role]}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>
    </main>
  );
}

/** Page wrapper; Suspense is needed because the form reads the address (useSearchParams). */
export default function LoginPage() {
  return (
    <Suspense fallback={<div className="splash"><span className="spinner" aria-hidden="true" /> Loading...</div>}>
      <LoginForm />
    </Suspense>
  );
}
