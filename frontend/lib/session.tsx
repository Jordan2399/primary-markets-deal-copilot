"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { setCurrentUser } from "./client";
import type { UserInfo } from "./types";

/** What the provider knows: still checking, signed in, or the API did not answer. */
type State =
  | { status: "loading" }
  | { status: "ready"; user: UserInfo }
  | { status: "unreachable" };

// The context carries the signed-in user and a sign-out function to every page below.
const Ctx = createContext<{ user: UserInfo; signOut: () => Promise<void> } | null>(null);

/** Hook for pages: `const { user, signOut } = useSession()`. Only valid inside SessionProvider. */
export function useSession() {
  const value = useContext(Ctx);
  if (!value) throw new Error("useSession must be used inside SessionProvider");
  return value;
}

/** Send the browser to /login, remembering the current page so we can return after sign-in. */
function goToLogin() {
  const next = encodeURIComponent(window.location.pathname + window.location.search);
  window.location.replace(`/login?next=${next}`);
}

/** Asks the server who is signed in. Children render only once that is known. */
export function SessionProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>({ status: "loading" });

  // Ask the server who we are. The answer decides what renders, never anything stored in the browser.
  const check = useCallback(async () => {
    setState({ status: "loading" });
    try {
      const response = await fetch("/api/session", { cache: "no-store" });
      // 401 = no valid session: go to the sign-in page.
      if (response.status === 401) return goToLogin();
      if (!response.ok) return setState({ status: "unreachable" });
      const user = (await response.json()) as UserInfo;
      // Tell the API client who is signed in (used to attribute actions in the UI).
      setCurrentUser(user);
      setState({ status: "ready", user });
    } catch {
      setState({ status: "unreachable" });
    }
  }, []);

  // Check once when the app first loads.
  useEffect(() => {
    void check();
  }, [check]);

  // Sign out: tell the server (it clears the cookie), then always leave for /login.
  const signOut = useCallback(async () => {
    try {
      await fetch("/api/session", { method: "DELETE" });
    } finally {
      setCurrentUser(null);
      window.location.assign("/login");
    }
  }, []);

  // Children render only after the user is known, so no page ever flashes content for nobody.
  if (state.status === "loading") {
    return (
      <div className="splash" role="status" aria-live="polite">
        <span className="spinner" aria-hidden="true" /> Checking your session...
      </div>
    );
  }
  if (state.status === "unreachable") {
    return (
      <div className="splash">
        <div className="card narrow">
          <h2>The service is not reachable</h2>
          <p className="muted">The API did not answer. Check that the containers are running, then try again.</p>
          <button className="primary" onClick={() => void check()}>Try again</button>
        </div>
      </div>
    );
  }
  return <Ctx.Provider value={{ user: state.user, signOut }}>{children}</Ctx.Provider>;
}
