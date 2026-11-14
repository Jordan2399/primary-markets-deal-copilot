"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import Brand from "@/components/Brand";
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
          <ThemeToggle />
          <div className="usercard" title={ROLE_CAN[user.role]}>
            <span className="avatar" aria-hidden="true">{initials(user.display_name) || user.username[0]?.toUpperCase()}</span>
            <span className="user-text">
              <span className="user-name">{user.display_name.replace(/\s*\(.*\)/, "")}</span>
              <span className={`role-badge role-${user.role}`}>{ROLE_LABEL[user.role]}</span>
            </span>
          </div>
          <button className="ghost" onClick={() => void signOut()}>Sign out</button>
        </div>
      </div>
    </header>
  );
}
