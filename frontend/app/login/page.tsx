"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Brand from "@/components/Brand";
import ThemeToggle from "@/components/ThemeToggle";
import { ApiError, api } from "@/lib/client";
import { ROLE_CAN, ROLE_LABEL, safeNext } from "@/lib/session-utils";
import type { DemoAccount } from "@/lib/types";

// Only the username is remembered between visits, never the password.
const USER_KEY = "dc-last-user";

/** The sign-in page: a product panel on the left, the form on the right. */
function LoginForm() {
  const search = useSearchParams();
  // Where to go after signing in; safeNext refuses anything that is not a path on this site.
  const next = safeNext(search.get("next"));
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [capsLock, setCapsLock] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [accounts, setAccounts] = useState<DemoAccount[]>([]);

  useEffect(() => {
    // Already signed in? Go straight on.
    // (The server decides: a leftover cookie that is no longer valid gets a 401 here.)
    fetch("/api/session", { cache: "no-store" })
      .then((r) => { if (r.ok) window.location.replace(next); })
      .catch(() => undefined);
    // Pre-fill the username used last time.
    try {
      const last = window.localStorage.getItem(USER_KEY);
      if (last) setUsername(last);
    } catch {
      /* storage can be blocked; the field simply starts empty */
    }
    // The API returns the quick-access list only in development; otherwise it stays empty.
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
        body: JSON.stringify({ username: username.trim(), password }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new ApiError(response.status, body?.error?.code ?? "error", body?.error?.message ?? "Sign-in failed.");
      }
      try {
        window.localStorage.setItem(USER_KEY, username.trim());
      } catch {
        /* not remembering the name is harmless */
      }
      // A full page load (not a client-side route) makes the new cookie take effect everywhere.
      window.location.assign(next);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The service is not reachable. Please try again in a moment.");
      setPassword("");
      setBusy(false);
    }
  }

  return (
    <main className="login">
      <aside className="login-aside">
        <div className="login-brand"><Brand size={34} /><span>Deal Copilot</span></div>

        <div className="login-hero">
          <p className="eyebrow light">Primary Markets</p>
          <h1>Every new issue, from mandate to booking.</h1>
          <p className="lead">
            One workspace for DCM and syndicate teams: deal workflow and approvals, order books and allocation,
            term sheet checks, and an assistant that answers from your data and shows its sources.
          </p>
        </div>

        {/* A miniature of the deal lifecycle: the product in one picture. */}
        <ol className="login-flow" aria-label="Deal lifecycle">
          {["Mandate", "Documentation", "Marketing", "Book building", "Allocation", "Booking"].map((s, i) => (
            <li key={s} style={{ animationDelay: `${i * 90}ms` }}><span>{i + 1}</span>{s}</li>
          ))}
        </ol>

        <ul className="login-features">
          <li><strong>Controlled</strong><span>Role-based access and four-eyes approval on every allocation.</span></li>
          <li><strong>Traceable</strong><span>Every change and every AI answer is written to the audit trail.</span></li>
          <li><strong>Explainable</strong><span>The model explains; people decide.</span></li>
        </ul>
      </aside>

      <section className="login-main">
        <div className="login-top"><ThemeToggle /></div>
        <div className="login-wrap">
          <form className="login-card" onSubmit={submit} aria-labelledby="signin-title">
            <div>
              <h2 id="signin-title">Sign in</h2>
              <p className="muted">Welcome back. Enter your credentials to continue.</p>
            </div>
            {error && <div className="alert" role="alert">{error}</div>}
            <label>Username
              <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" autoCapitalize="none" spellCheck={false} required autoFocus={!username} />
            </label>
            <label>
              <span className="label-row">Password {capsLock && <span className="caps-warning" role="status">Caps Lock is on</span>}</span>
              <span className="password">
                <input
                  type={show ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  // getModifierState tells us whether Caps Lock is on while typing.
                  onKeyUp={(e) => setCapsLock(e.getModifierState("CapsLock"))}
                  onBlur={() => setCapsLock(false)}
                  autoComplete="current-password"
                  autoFocus={Boolean(username)}
                  required
                />
                <button type="button" className="ghost" onClick={() => setShow((v) => !v)} aria-pressed={show}>{show ? "Hide" : "Show"}</button>
              </span>
            </label>
            <button className="primary wide large" disabled={busy || !username || !password}>
              {busy ? <><span className="spinner light" aria-hidden="true" />Signing in</> : "Sign in"}
            </button>
            <p className="login-help muted small">Trouble signing in? Contact your administrator.</p>
          </form>

          {/* Development environments only: the list is empty in production, so nothing is shown. */}
          {accounts.length > 0 && (
            <details className="dev-access">
              <summary>Development access</summary>
              <p className="muted small">Choose an account to fill in the username. The password is set in your environment file.</p>
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
            </details>
          )}
          <p className="login-legal muted small">Authorised users only. Activity is monitored and recorded.</p>
        </div>
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
