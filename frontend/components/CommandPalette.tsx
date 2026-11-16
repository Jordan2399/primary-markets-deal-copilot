"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/client";
import { useSession } from "@/lib/session";
import { isPaletteShortcut } from "@/lib/palette";
import { linksFor } from "@/lib/session-utils";
import { label } from "@/lib/format";
import type { SearchResults } from "@/lib/types";

type Item = { key: string; group: string; title: string; hint?: string; href: string };

/**
 * Search everywhere: pages, deals and investors, from one box. Opens with Ctrl+K / Cmd+K or the
 * button in the top bar. Arrow keys move, Enter opens, Escape closes. Deal and investor hits come
 * from the API (which hides investors from viewers); pages are filtered here by role.
 */
export default function CommandPalette() {
  const router = useRouter();
  const { user } = useSession();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResults | null>(null);
  const [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);

  // The global shortcut works on every page.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (isPaletteShortcut(e)) {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Reset and focus each time it opens.
  useEffect(() => {
    if (open) {
      setQuery("");
      setResults(null);
      setActive(0);
      setTimeout(() => input.current?.focus(), 0);
    }
  }, [open]);

  // Ask the API after a short pause in typing (300 ms), so each keystroke is not a request.
  useEffect(() => {
    const text = query.trim();
    if (!text) {
      setResults(null);
      return;
    }
    let stale = false;
    const timer = setTimeout(() => {
      api.search(text).then((r) => { if (!stale) setResults(r); }).catch(() => { if (!stale) setResults(null); });
    }, 300);
    return () => {
      stale = true; // a newer keystroke makes this answer irrelevant
      clearTimeout(timer);
    };
  }, [query]);

  const items = useMemo<Item[]>(() => {
    const text = query.trim().toLowerCase();
    const pages = linksFor(user.role)
      .filter((l) => !text || l.label.toLowerCase().includes(text))
      .map((l) => ({ key: `p:${l.href}`, group: "Pages", title: l.label, href: l.href }));
    const deals = (results?.deals ?? []).map((d) => ({
      key: `d:${d.id}`, group: "Deals", title: d.name, hint: `${d.issuer} · ${d.stage}`, href: `/deals/${encodeURIComponent(d.id)}`,
    }));
    const investors = (results?.investors ?? []).map((i) => ({
      key: `i:${i.id}`, group: "Investors", title: i.name, hint: `${label(i.type)} · ${i.region}`, href: `/investors/${encodeURIComponent(i.id)}`,
    }));
    return [...deals, ...investors, ...pages];
  }, [query, results, user.role]);

  function go(item: Item) {
    setOpen(false);
    router.push(item.href);
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Escape") setOpen(false);
    else if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, items.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
    else if (e.key === "Enter" && items[active]) go(items[active]);
  }

  return (
    <>
      <button type="button" className="search-button" onClick={() => setOpen(true)} aria-label="Search (Ctrl+K)" title="Search (Ctrl+K)">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
        <span>Search</span>
        <kbd>Ctrl K</kbd>
      </button>
      {open && (
        <div className="palette-backdrop" onMouseDown={() => setOpen(false)}>
          <div className="palette" role="dialog" aria-modal="true" aria-label="Search" onMouseDown={(e) => e.stopPropagation()} onKeyDown={onKeyDown}>
            <input
              ref={input}
              value={query}
              onChange={(e) => { setQuery(e.target.value); setActive(0); }}
              placeholder="Search deals, investors and pages"
              aria-label="Search deals, investors and pages"
              role="combobox"
              aria-expanded="true"
              aria-controls="palette-list"
              autoComplete="off"
            />
            <ul id="palette-list" role="listbox">
              {items.length === 0 && <li className="palette-empty muted">No matches</li>}
              {items.map((item, i) => (
                <li key={item.key} role="option" aria-selected={i === active} className={i === active ? "active" : ""} onMouseEnter={() => setActive(i)} onClick={() => go(item)}>
                  <span className="palette-group">{item.group}</span>
                  <span className="palette-title">{item.title}</span>
                  {item.hint && <span className="muted small">{item.hint}</span>}
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </>
  );
}
