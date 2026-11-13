/**
 * Session endpoints. The browser never sees the token: it is stored in an httpOnly cookie
 * here and added to API calls by the proxy (app/api/[...path]/route.ts).
 *
 *   POST   {username, password}  sign in; sets the cookie; returns {user}
 *   GET                          who is signed in (401 and the cookie is removed if it is invalid)
 *   DELETE                       sign out
 */
import { NextResponse, type NextRequest } from "next/server";
import { SESSION_COOKIE, apiBase, cookieOptions, crossSiteWrite, errorBody } from "@/lib/server-auth";

export const dynamic = "force-dynamic";

// Reused error body for when the backend cannot be reached at all.
const UNREACHABLE = errorBody("api_unreachable", "The API is not reachable.");

/** Sign in: forward the credentials to the API and store the returned token in the cookie. */
export async function POST(request: NextRequest) {
  if (crossSiteWrite(request)) return NextResponse.json(errorBody("forbidden", "Cross-site request refused."), { status: 403 });
  // Read the JSON body defensively: a malformed body is a 400, not a crash.
  let credentials: { username?: string; password?: string };
  try {
    credentials = await request.json();
  } catch {
    return NextResponse.json(errorBody("bad_request", "Send a username and a password."), { status: 400 });
  }
  try {
    const upstream = await fetch(`${apiBase()}/api/v1/auth/login`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ username: credentials.username ?? "", password: credentials.password ?? "" }),
      cache: "no-store",
      signal: AbortSignal.timeout(15_000),
    });
    const body = await upstream.json();
    // Wrong password, locked account and so on: pass the API's error through unchanged.
    if (!upstream.ok) return NextResponse.json(body, { status: upstream.status });
    // The browser gets only the user details; the token goes into the httpOnly cookie.
    const response = NextResponse.json({ user: body.user });
    response.cookies.set(SESSION_COOKIE, body.access_token, cookieOptions(body.expires_in));
    return response;
  } catch {
    return NextResponse.json(UNREACHABLE, { status: 502 });
  }
}

/** Who is signed in? Asks the API to validate the cookie's token. */
export async function GET(request: NextRequest) {
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (!token) return NextResponse.json(errorBody("unauthorized", "Please sign in."), { status: 401 });
  try {
    const upstream = await fetch(`${apiBase()}/api/v1/auth/me`, {
      headers: { authorization: `Bearer ${token}` },
      cache: "no-store",
      signal: AbortSignal.timeout(15_000),
    });
    if (upstream.status === 401) {
      const response = NextResponse.json(await upstream.json(), { status: 401 });
      response.cookies.set(SESSION_COOKIE, "", cookieOptions(0)); // stale or expired: remove it
      return response;
    }
    if (!upstream.ok) return NextResponse.json(await upstream.json(), { status: upstream.status });
    return NextResponse.json(await upstream.json());
  } catch {
    return NextResponse.json(UNREACHABLE, { status: 502 });
  }
}

/** Sign out: tell the API (for the audit trail), then delete the cookie. */
export async function DELETE(request: NextRequest) {
  if (crossSiteWrite(request)) return NextResponse.json(errorBody("forbidden", "Cross-site request refused."), { status: 403 });
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (token) {
    try {
      await fetch(`${apiBase()}/api/v1/auth/logout`, {
        method: "POST",
        headers: { authorization: `Bearer ${token}` },
        signal: AbortSignal.timeout(5_000),
      });
    } catch {
      /* the cookie is removed below either way */
    }
  }
  // 204 = success with no body. maxAge 0 removes the cookie from the browser.
  const response = new NextResponse(null, { status: 204 });
  response.cookies.set(SESSION_COOKIE, "", cookieOptions(0));
  return response;
}
