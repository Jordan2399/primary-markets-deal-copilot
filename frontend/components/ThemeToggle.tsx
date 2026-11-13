"use client";

import { useEffect, useState } from "react";

type Theme = "light" | "dark";

/** The theme currently in effect: the explicit choice if made, else the system setting. */
function effectiveTheme(): Theme {
  const explicit = document.documentElement.getAttribute("data-theme");
  if (explicit === "light" || explicit === "dark") return explicit;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/** Sun/moon button that switches between light and dark and remembers the choice. */
export default function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("light");
  // Read the real theme after the first render (the server cannot know the browser's setting).
  useEffect(() => setTheme(effectiveTheme()), []);

  function toggle() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    // The CSS reads data-theme on <html>, so changing it restyles the whole page at once.
    document.documentElement.setAttribute("data-theme", next);
    try {
      window.localStorage.setItem("dc-theme", next);
    } catch {
      /* storage can be blocked; the choice then lasts for this visit only */
    }
    setTheme(next);
  }

  return (
    <button className="icon-button" onClick={toggle} aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`} title="Switch theme">
      {theme === "dark" ? (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
          <circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
        </svg>
      ) : (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z" />
        </svg>
      )}
    </button>
  );
}
