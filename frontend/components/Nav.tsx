"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import Brand from "@/components/Brand";
import CommandPalette from "@/components/CommandPalette";
import ThemeToggle from "@/components/ThemeToggle";
import { useSession } from "@/lib/session";
import { ROLE_CAN, ROLE_LABEL, linksFor } from "@/lib/session-utils";

/** Up to two capital letters from a display name, for the avatar circle ("Anna Keller" -> "AK"). */
function initials(name: string): string {
  return name
    .replace(/\(.*\)/, "") // drop a role suffix like "(Syndicate)"
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase())
    .join("");
}

/** The navy top bar: brand, role-filtered menu, theme switch, user card and sign-out. */
export default function Nav() {
  const pathname = usePathname();
  const { user, signOut } = useSession();
  // Which menu item is highlighted. Pipeline also covers /deals/... pages.
  const current = (href: string) => (href === "/" ? pathname === "/" || pathname.startsWith("/deals") : pathname.startsWith(href));

  return (
    <header className="topbar">
      <div className="topbar-inner">
        <Link href="/" className="brand" aria-label="Deal Copilot home">
          <Brand />
          <span className="brand-text">
            <strong>Deal Copilot</strong>
            <small>Primary Markets</small>
          </span>
        </Link>
        <nav aria-label="Main" className="mainnav">
          {/* linksFor hides pages the role cannot use; the API still enforces the real rule. */}
          {linksFor(user.role).map((l) => (
            <Link key={l.href} href={l.href} aria-current={current(l.href) ? "page" : undefined}>
              {l.label}
            </Link>
          ))}
        </nav>
        <div className="topbar-right">
          <CommandPalette />
          <ThemeToggle />
          <UserMenu />
        </div>
      </div>
    </header>
  );
}

/** The avatar button with a small account panel: who you are, what your role allows, sign out. */
function UserMenu() {
  const { user, signOut } = useSession();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  // Close on a click outside the panel or on Escape, like any native menu.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const name = user.display_name.replace(/\s*\(.*\)/, "");
  return (
    <div className="usermenu" ref={box}>
      <button className="usercard" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <span className="avatar" aria-hidden="true">{initials(user.display_name) || user.username[0]?.toUpperCase()}</span>
        <span className="user-text">
          <span className="user-name">{name}</span>
          <span className="user-role">{ROLE_LABEL[user.role]}</span>
        </span>
        <svg className="chev" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>
      </button>
      {open && (
        <div className="menu-panel" role="menu">
          <div className="menu-head">
            <span className="avatar large" aria-hidden="true">{initials(user.display_name) || user.username[0]?.toUpperCase()}</span>
            <div>
              <strong>{name}</strong>
              <div className="muted small">{user.username}</div>
            </div>
          </div>
          <div className="menu-role">
            <span className={`role-badge role-${user.role}`}>{ROLE_LABEL[user.role]}</span>
            <p className="muted small">{ROLE_CAN[user.role]}</p>
          </div>
          <button role="menuitem" className="menu-item" onClick={() => void signOut()}>Sign out</button>
        </div>
      )}
    </div>
  );
}
