"use client";

import { SseParser } from "./sse";
import type {
  AllocationResult, AuditEvent, CopilotEvent, CreateDealInput, DealDetail, DealSummary, Extraction, Issuer,
  OrderBook, Proposal, ProposalSummary, Role, Sample, SimulateInput, Stage, Task, TaskStatus, ValidationReport,
} from "./types";

const ROLE_KEY = "dealcopilot.role";
const USER_KEY = "dealcopilot.user";

export const ROLES: Role[] = ["viewer", "marketer", "syndicate", "approver", "admin"];

export function getRole(): Role {
  try {
    const stored = window.localStorage.getItem(ROLE_KEY) as Role | null;
    if (stored && ROLES.includes(stored)) return stored;
  } catch {
    /* storage can be blocked */
  }
  return "viewer";
}

export function setRole(role: Role): void {
  try {
    window.localStorage.setItem(ROLE_KEY, role);
    window.localStorage.setItem(USER_KEY, `demo.${role}`);
  } catch {
    /* ignore */
  }
  window.dispatchEvent(new Event("rolechange"));
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details: Record<string, unknown> = {},
    public requestId = "",
  ) {
    super(message);
  }
}

function identityHeaders(): Record<string, string> {
  const role = getRole();
  return { "X-Demo-Role": role, "X-Demo-User": `demo.${role}` };
}

async function toError(response: Response): Promise<ApiError> {
  try {
    const body = await response.json();
    const e = body.error ?? {};
    return new ApiError(response.status, e.code ?? "error", e.message ?? response.statusText, e.details ?? {}, e.request_id ?? "");
  } catch {
    return new ApiError(response.status, "error", response.statusText || "Request failed");
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    cache: "no-store",
    headers: { "Content-Type": "application/json", ...identityHeaders(), ...(init.headers ?? {}) },
  });
  if (!response.ok) throw await toError(response);
  return (await response.json()) as T;
}

async function form<T>(path: string, body: FormData): Promise<T> {
  // No Content-Type header: the browser adds the multipart boundary itself.
  const response = await fetch(`/api${path}`, { method: "POST", body, cache: "no-store", headers: identityHeaders() });
  if (!response.ok) throw await toError(response);
  return (await response.json()) as T;
}

export const api = {
  stages: () => request<Stage[]>("/stages"),
  issuers: () => request<Issuer[]>("/issuers"),
  deals: () => request<DealSummary[]>("/deals"),
  deal: (id: string) => request<DealDetail>(`/deals/${encodeURIComponent(id)}`),
  tasks: (id: string) => request<Task[]>(`/deals/${encodeURIComponent(id)}/tasks`),
  timeline: (id: string) => request<AuditEvent[]>(`/deals/${encodeURIComponent(id)}/timeline`),
  createDeal: (input: CreateDealInput) => request<DealDetail>("/deals", { method: "POST", body: JSON.stringify(input) }),
  updateTask: (taskId: string, status: TaskStatus) =>
    request<Task>(`/tasks/${encodeURIComponent(taskId)}`, { method: "PATCH", body: JSON.stringify({ status }) }),
  advance: (id: string) => request<DealDetail>(`/deals/${encodeURIComponent(id)}/advance`, { method: "POST" }),
  orderbook: (dealId: string) => request<OrderBook>(`/deals/${encodeURIComponent(dealId)}/orderbook`),
  simulate: (dealId: string, input: SimulateInput) =>
    request<OrderBook>(`/deals/${encodeURIComponent(dealId)}/orderbook/simulate`, { method: "POST", body: JSON.stringify(input) }),
  preview: (dealId: string, spread?: number) =>
    request<AllocationResult>(`/deals/${encodeURIComponent(dealId)}/allocation/preview${spread != null ? `?final_spread_bp=${spread}` : ""}`),
  proposals: (dealId: string) => request<ProposalSummary[]>(`/deals/${encodeURIComponent(dealId)}/allocation`),
  proposal: (id: string) => request<Proposal>(`/allocation/${encodeURIComponent(id)}`),
  propose: (dealId: string, spread: number | null) =>
    request<Proposal>(`/deals/${encodeURIComponent(dealId)}/allocation/propose`, {
      method: "POST",
      body: JSON.stringify({ final_spread_bp: spread }),
    }),
  approve: (dealId: string, proposalId: string) =>
    request<Proposal>(`/deals/${encodeURIComponent(dealId)}/allocation/approve?proposal_id=${encodeURIComponent(proposalId)}`, { method: "POST" }),
  sample: (dealId: string, variant: "good" | "bad") =>
    request<Sample>(`/deals/${encodeURIComponent(dealId)}/termsheet-sample?variant=${variant}`),
  extract: (data: { file?: File | null; text?: string; dealId?: string }) => {
    const body = new FormData();
    if (data.file) body.append("file", data.file);
    if (data.text) body.append("text", data.text);
    if (data.dealId) body.append("deal_id", data.dealId);
    return form<Extraction>("/documents/extract", body);
  },
  validate: (docId: string, dealId?: string) =>
    request<ValidationReport>(`/documents/${encodeURIComponent(docId)}/validate${dealId ? `?deal_id=${encodeURIComponent(dealId)}` : ""}`, { method: "POST" }),
  audit: (action?: string) => request<AuditEvent[]>(`/audit?limit=200${action ? `&action=${encodeURIComponent(action)}` : ""}`),
};

/** Ask the Copilot and receive events as they stream in. */
export async function streamCopilot(
  body: { message: string; deal_id: string | null; history: { role: "user" | "assistant"; content: string }[] },
  onEvent: (event: CopilotEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch("/api/copilot/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...identityHeaders() },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok || !response.body) throw await toError(response);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const parser = new SseParser();
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    for (const event of parser.push(decoder.decode(value, { stream: true }))) onEvent(event);
  }
}
