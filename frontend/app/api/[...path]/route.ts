/**
 * Runtime proxy: the browser calls /api/..., this handler forwards to the backend.
 *
 * Why: the backend address (API_INTERNAL_URL) is read at runtime, not baked in at build time,
 * so the same image works in dev and prod. It also avoids CORS, and it streams the Copilot's
 * server-sent events through without buffering.
 */
import type { NextRequest } from "next/server";
import { SESSION_COOKIE, apiBase, crossSiteWrite, errorBody } from "@/lib/server-auth";

export const dynamic = "force-dynamic";

// Identity is never taken from the browser: the token comes from the httpOnly session cookie.
// Only these request headers are passed on; everything else from the browser is dropped.
const FORWARD_HEADERS = ["content-type", "x-request-id"];

/** Forward any /api/... request to the backend, adding the user's token from the cookie. */
async function proxy(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  if (crossSiteWrite(request)) {
    return Response.json(errorBody("forbidden", "Cross-site request refused."), { status: 403 });
  }
  // Rebuild the backend URL from the path pieces (each one encoded) and the query string.
  const { path } = await params;
  const base = apiBase();
  const target = `${base}/api/v1/${path.map(encodeURIComponent).join("/")}${request.nextUrl.search}`;

  const headers = new Headers();
  for (const name of FORWARD_HEADERS) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }

  // The Authorization header is built here from the cookie; a header sent by the browser is ignored.
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (token) headers.set("authorization", `Bearer ${token}`);

  // GET and HEAD have no body; everything else forwards the raw bytes (JSON or file uploads).
  const hasBody = !["GET", "HEAD"].includes(request.method);
  try {
    const upstream = await fetch(target, {
      method: request.method,
      headers,
      body: hasBody ? await request.arrayBuffer() : undefined,
      cache: "no-store",
      signal: AbortSignal.timeout(180_000),
    });
    // Copy back only a few safe response headers.
    const out = new Headers();
    for (const name of ["content-type", "cache-control", "x-request-id"]) {
      const value = upstream.headers.get(name);
      if (value) out.set(name, value);
    }
    out.set("x-accel-buffering", "no"); // ask proxies not to buffer, so streamed tokens arrive live
    return new Response(upstream.body, { status: upstream.status, headers: out });
  } catch {
    return Response.json(errorBody("api_unreachable", "The API is not reachable."), { status: 502 });
  }
}

// One handler serves every method.
export { proxy as GET, proxy as POST, proxy as PATCH, proxy as PUT, proxy as DELETE };
