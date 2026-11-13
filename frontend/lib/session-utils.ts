import type { Role } from "./types";

/**
 * Where to go after signing in. Only a path on this site is allowed: anything else (another
 * host, "//host", a backslash trick) falls back to the home page, so the login page cannot be
 * used to send someone to a different site.
 */
export function safeNext(value: string | null | undefined): string {
  // Must be a local absolute path: '//evil.com' and 'https://...' are rejected here.
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.includes("\\")) return "/";
  // Never bounce back to the login page or into the API after signing in.
  if (value.startsWith("/login") || value.startsWith("/api/")) return "/";
  return value;
}

/** One menu entry and the roles that should see it ("all" = everyone signed in). */
export type NavLink = { href: string; label: string; roles: Role[] | "all" };

// The full menu. Order here is the order shown in the top bar.
export const NAV_LINKS: NavLink[] = [
  { href: "/", label: "Pipeline", roles: "all" },
  { href: "/orderbook", label: "Order book", roles: ["syndicate", "approver", "admin"] },
  { href: "/allocation", label: "Allocation", roles: ["syndicate", "approver", "admin"] },
  { href: "/termsheets", label: "Term sheets", roles: "all" },
  { href: "/copilot", label: "Copilot", roles: "all" },
  { href: "/audit", label: "Audit", roles: ["admin"] },
  { href: "/status", label: "Status", roles: "all" },
];

/** Links worth showing for a role. This only tidies the menu; the API enforces the real rules. */
export function linksFor(role: Role): NavLink[] {
  // Admin sees every link; others see the links that list their role or "all".
  return NAV_LINKS.filter((l) => l.roles === "all" || l.roles.includes(role) || role === "admin");
}

/** Human-readable role names for badges. */
export const ROLE_LABEL: Record<Role, string> = {
  viewer: "Viewer",
  marketer: "Marketer",
  syndicate: "Syndicate",
  approver: "Approver",
  admin: "Administrator",
};

/** One-line summary of what each role may do (shown on the login page). */
export const ROLE_CAN: Record<Role, string> = {
  viewer: "Read the pipeline and ask the Copilot",
  marketer: "Create deals, update tasks, advance stages",
  syndicate: "Run order books, propose allocations, update tasks",
  approver: "Approve allocations (four-eyes)",
  admin: "Everything, plus the audit trail",
};

/** The deal named in the address (?deal=D-2026-007), so pages can link to each other. */
export function dealFromUrl(): string {
  if (typeof window === "undefined") return ""; // server rendering has no address bar
  const value = new URLSearchParams(window.location.search).get("deal") ?? "";
  // Only plain id characters are accepted, so a crafted link cannot inject anything.
  return /^[A-Za-z0-9-]{1,60}$/.test(value) ? value : "";
}
