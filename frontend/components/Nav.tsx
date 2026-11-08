"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { ROLES, getRole, setRole } from "@/lib/client";
import type { Role } from "@/lib/types";

const LINKS = [
  { href: "/", label: "Pipeline" },
  { href: "/copilot", label: "Copilot" },
  { href: "/audit", label: "Audit" },
  { href: "/status", label: "Status" },
];

export default function Nav() {
  const pathname = usePathname();
  const [role, setLocalRole] = useState<Role>("viewer");

  useEffect(() => {
    setLocalRole(getRole());
    const sync = () => setLocalRole(getRole());
    window.addEventListener("rolechange", sync);
    return () => window.removeEventListener("rolechange", sync);
  }, []);

  return (
    <header className="nav">
      <strong className="brand">Deal Copilot</strong>
      <nav aria-label="Main">
        {LINKS.map((l) => (
          <Link
            key={l.href}
            href={l.href}
            aria-current={(l.href === "/" ? pathname === "/" || pathname.startsWith("/deals") : pathname.startsWith(l.href)) ? "page" : undefined}
          >
            {l.label}
          </Link>
        ))}
      </nav>
      <label className="role">
        <span className="muted">Demo role</span>
        <select
          value={role}
          onChange={(e) => {
            setRole(e.target.value as Role);
            window.location.reload();
          }}
        >
          {ROLES.map((r) => (
            <option key={r} value={r}>{r}</option>
          ))}
        </select>
      </label>
    </header>
  );
}
