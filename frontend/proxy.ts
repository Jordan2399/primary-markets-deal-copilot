import { NextResponse, type NextRequest } from "next/server";

/**
 * First gate: no session cookie means no page, only the sign-in page.
 * This only checks that a cookie exists. The API checks the signed token on every request, and
 * the session provider (lib/session.tsx) asks the server whether the token is still valid.
 */
export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  // The sign-in page itself must stay reachable, otherwise nobody could ever sign in.
  if (pathname === "/login") return NextResponse.next();
  // A cookie is present: let the page load (the server validates the token later).
  if (request.cookies.get("dc_session")?.value) return NextResponse.next();
  // No cookie: redirect to /login and remember where the user wanted to go (the `next` value).
  const url = request.nextUrl.clone();
  url.pathname = "/login";
  url.search = "";
  url.searchParams.set("next", pathname + search);
  return NextResponse.redirect(url);
}

// The matcher decides which paths run this function.
// Pages only: the API routes answer 401 themselves, and static files need no session.
export const config = { matcher: ["/((?!api/|_next/|favicon.ico|.*\\..*).*)"] };