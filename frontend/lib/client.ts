"use client";

import { SseParser } from "./sse";
import type {
  AllocationResult, AuditEvent, ConversationDetail, ConversationSummary, CopilotEvent, CreateDealInput, DealDetail,
  DealSummary, DemoAccount, Extraction, Issuer, OrderBook, Proposal, ProposalSummary, Role, Sample, SimulateInput,
  Stage, Task, TaskStatus, UserInfo, ValidationReport,
} from "./types";

export const ROLES: Role[] = ["viewer", "marketer", "syndicate", "approver", "admin"];

// The signed-in user. It is set once by the session provider (see lib/session.tsx) after the
// server confirms the session. The role is only used to show or hide buttons: the API checks
// the signed token on every request, so changing this value in the browser grants nothing.
let currentUser: UserInfo | null = null;

export function setCurrentUser(user: UserInfo | null): void {
  currentUser = user;
}

export function getUser(): UserInfo | null {
  return currentUser;
}

export function getRole(): Role {
  return currentUser?.role ?? "viewer";
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

/** A 401 on a normal call means the session ended: go to the sign-in page and come back here. */
function handleUnauthorized(): void {
  if (typeof window === "undefined" || window.location.pathname.startsWith("/login")) return;
  setCurrentUser(null);
  const next = encodeURIComponent(window.location.pathname + window.location.search);
  window.location.assign(`/login?next=${next}`);
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
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
  });
  if (response.status === 401) handleUnauthorized();
  if (!response.ok) throw await toError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

async function form<T>(path: string, body: FormData): Promise<T> {
  // No Content-Type header: the browser adds the multipart boundary itself.
  const response = await fetch(`/api${path}`, { method: "POST", body, cache: "no-store" });
  if (response.status === 401) handleUnauthorized();
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
  conversations: () => request<ConversationSummary[]>("/conversations"),
  conversation: (id: string) => request<ConversationDetail>(`/conversations/${encodeURIComponent(id)}`),
  renameConversation: (id: string, title: string) =>
    request<ConversationDetail>(`/conversations/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify({ title }) }),
  deleteConversation: (id: string) => request<void>(`/conversations/${encodeURIComponent(id)}`, { method: "DELETE" }),
  demoAccounts: () => request<DemoAccount[]>("/auth/demo-accounts"),
  audit: (action?: string) => request<AuditEvent[]>(`/audit?limit=200${action ? `&action=${encodeURIComponent(action)}` : ""}`),
};

/** Ask the Copilot and receive events as they stream in. */
export async function streamCopilot(
  body: { message: string; deal_id: string | null; conversation_id: string | null },
  onEvent: (event: CopilotEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch("/api/copilot/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (response.status === 401) handleUnauthorized();
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
