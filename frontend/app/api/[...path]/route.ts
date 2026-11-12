/**
 * Runtime proxy: the browser calls /api/..., this handler forwards to the backend.
 *
 * Why: the backend address (API_INTERNAL_URL) is read at runtime, not baked in at build time,
 * so the same image works in dev and prod. It also avoids CORS, and it streams the Copilot's
 * server-sent events through without buffering.
 */
import type { NextRequest } from "next/server";

export const dynamic = "force-dynamic";

const FORWARD_HEADERS = ["content-type", "x-demo-role", "x-demo-user", "x-request-id"];

async function proxy(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  const base = process.env.API_INTERNAL_URL ?? "http://localhost:8000";
  const target = `${base}/api/v1/${path.map(encodeURIComponent).join("/")}${request.nextUrl.search}`;

  const headers = new Headers();
  for (const name of FORWARD_HEADERS) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }

  const hasBody = !["GET", "HEAD"].includes(request.method);
  try {
    const upstream = await fetch(target, {
      method: request.method,
      headers,
      body: hasBody ? await request.arrayBuffer() : undefined,
      cache: "no-store",
      signal: AbortSignal.timeout(180_000),
    });
    const out = new Headers();
    for (const name of ["content-type", "cache-control", "x-request-id"]) {
      const value = upstream.headers.get(name);
      if (value) out.set(name, value);
    }
    out.set("x-accel-buffering", "no");
    return new Response(upstream.body, { status: upstream.status, headers: out });
  } catch {
    return Response.json(
      { error: { code: "api_unreachable", message: "The API is not reachable.", request_id: "", details: {} } },
      { status: 502 },
    );
  }
}

export { proxy as GET, proxy as POST, proxy as PATCH, proxy as PUT, proxy as DELETE };
