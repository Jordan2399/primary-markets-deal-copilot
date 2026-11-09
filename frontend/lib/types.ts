/** Shapes returned by the API. Keep in sync with the models.py files in backend/app. */

export type TaskStatus = "TODO" | "IN_PROGRESS" | "DONE";
export type Role = "viewer" | "marketer" | "syndicate" | "approver" | "admin";

export type Stage = { code: string; name: string; position: number };
export type Issuer = { id: string; name: string; sector: string; country: string; rating_band: string };

export type DealSummary = {
  id: string;
  name: string;
  issuer_id: string;
  issuer_name: string;
  currency: string;
  size_mm: number;
  launch_date: string | null;
  stage_code: string;
  stage_name: string;
  stage_position: number;
  tasks_total: number;
  tasks_done: number;
  blockers_open: number;
  is_complete: boolean;
};

export type Tranche = {
  id: string;
  tenor_years: number;
  format: string;
  maturity: string | null;
  coupon: number | null;
  isin: string | null;
};

export type DealDetail = DealSummary & { tranches: Tranche[] };

export type Task = {
  id: string;
  deal_id: string;
  key: string;
  title: string;
  owner_role: string;
  due: string | null;
  status: TaskStatus;
  blocking: boolean;
  stage_code: string;
  stage_name: string;
  stage_position: number;
  depends_on: string[];
};

export type CreateDealInput = {
  issuer_id: string;
  name: string;
  currency: "EUR" | "USD" | "GBP" | "CHF";
  size_mm: number;
  tenor_years: number;
  format: "Reg S" | "144A" | "Domestic";
  launch_date: string;
};

export type AuditEvent = {
  id: string;
  ts: string;
  actor: string;
  role: string;
  action: string;
  entity_type: string;
  entity_id: string;
  deal_id: string | null;
  details: Record<string, unknown>;
  model: string | null;
  prompt_hash: string | null;
  sources: string[];
};

export type Source = {
  id: string;
  type: "deal" | "task" | "playbook";
  ref: string;
  title: string;
  snippet: string;
  meta: Record<string, string>;
};

export type CopilotEvent =
  | { event: "meta"; data: { intent: string; model: string; sources: Source[] } }
  | { event: "token"; data: { text: string } }
  | { event: "done"; data: { cited: string[]; audit_id: string | null } }
  | { event: "error"; data: { code: string; message: string; retry: boolean } };
