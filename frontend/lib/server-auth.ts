/** Shared by the Next.js route handlers (server side only). */
import type { NextRequest } from "next/server";

/** Name of the httpOnly cookie that holds the signed token. */
export const SESSION_COOKIE = "dc_session";

/** Where the backend lives. Read at runtime, so one build works in dev and prod. */
export function apiBase(): string {
  return process.env.API_INTERNAL_URL ?? "http://localhost:8000";
}

/** Cookie settings for the session; maxAge 0 deletes the cookie (used when signing out). */
export function cookieOptions(maxAgeSeconds: number) {
  return {
    httpOnly: true, // JavaScript in the page cannot read the token, which limits what XSS can steal
    sameSite: "lax" as const, // the browser does not send it on cross-site POST requests
    secure: process.env.COOKIE_SECURE === "true", // set true when the site is served over HTTPS
    path: "/",
    maxAge: maxAgeSeconds,
  };
}

/** An error in the same JSON shape the backend uses, so the UI handles both the same way. */
export function errorBody(code: string, message: string) {
  return { error: { code, message, request_id: "", details: {} } };
}

/**
 * Defence in depth against cross-site requests: when the browser says which site a state-changing
 * request came from, it must be this site. (The SameSite cookie already blocks most of this.)
 */
export function crossSiteWrite(request: NextRequest): boolean {
  // Reading never changes anything, so only writes are checked.
  if (["GET", "HEAD", "OPTIONS"].includes(request.method)) return false;
  const origin = request.headers.get("origin");
  // No Origin header (for example a server-to-server call): nothing to compare.
  if (!origin) return false;
  try {
    // Same site means the origin's host equals the host this request was sent to.
    return new URL(origin).host !== request.headers.get("host");
  } catch {
    return true; // an unreadable Origin is treated as hostile
  }
}
