/**
 * Typed API client. Every page talks to the backend through this module only.
 * Types will later be generated from the API's OpenAPI spec.
 */

export type DependencyStatus = {
  ok: boolean;
  detail: string;
  extra: Record<string, unknown>;
};

export type HealthResponse = {
  status: "ok" | "degraded";
  version: string;
  environment: string;
  llm_provider: string;
  dependencies: Record<string, DependencyStatus>;
};

/** Server-side calls use the Docker network name; browser calls use the public URL. */
function baseUrl(): string {
  return process.env.API_INTERNAL_URL ?? "http://localhost:8000";
}

export async function getHealth(): Promise<HealthResponse | null> {
  try {
    const response = await fetch(`${baseUrl()}/api/v1/health`, {
      cache: "no-store",
      signal: AbortSignal.timeout(8000),
    });
    if (!response.ok) return null;
    return (await response.json()) as HealthResponse;
  } catch {
    return null;
  }
}
