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

/* ---- Day 2: order book, allocation, term sheets ---- */

export type BookParams = { open_at: string; close_at: string; ipt_bp: number };
export type Bucket = { label: string; demand_k: number; orders: number; share_pct: number };
export type LadderLevel = { spread_bp: number; demand_k: number; cover: number };
export type TimelinePoint = { minute: number; cumulative_demand_k: number; orders: number };
export type BookMetrics = {
  deal_size_k: number;
  order_count: number;
  valid_order_count: number;
  investor_count: number;
  total_demand_k: number;
  valid_demand_k: number;
  cover_ratio: number;
  real_money_share_pct: number;
  anomaly_count: number;
  by_type: Bucket[];
  by_region: Bucket[];
  ladder: LadderLevel[];
  timeline: TimelinePoint[];
  suggested_final_spread_bp: number | null;
};
export type Anomaly = { order_id: string; rule: string; severity: string; excludes: boolean; message: string };
export type OrderOut = {
  id: string;
  investor_id: string;
  investor_name: string;
  investor_type: string;
  region: string;
  amount_k: number;
  limit_bp: number;
  placed_at: string;
  flags: string[];
};
export type OrderBook = {
  deal_id: string;
  params: BookParams | null;
  metrics: BookMetrics | null;
  orders: OrderOut[];
  anomalies: Anomaly[];
};
export type SimulateInput = { seed: number; target_cover: number; anomalies: number; extend: boolean };

export type AllocationLine = {
  order_id: string;
  investor_id: string;
  investor_name: string;
  investor_type: string;
  band: number | null;
  score: number | null;
  ordered_k: number;
  allocated_k: number;
  fill_pct: number;
  note: string;
};
export type BandSummary = { band: number; orders: number; demand_k: number; allocated_k: number; scale_pct: number };
export type AllocationResult = {
  deal_size_k: number;
  final_spread_bp: number;
  eligible_demand_k: number;
  total_allocated_k: number;
  status: string;
  bands: BandSummary[];
  lines: AllocationLine[];
};
export type Proposal = AllocationResult & {
  id: string;
  deal_id: string;
  state: "PROPOSED" | "APPROVED" | "SUPERSEDED";
  proposed_by: string;
  proposed_at: string;
  approved_by: string | null;
  approved_at: string | null;
  explanation: string;
  explanation_source: string;
};
export type ProposalSummary = {
  id: string;
  deal_id: string;
  state: string;
  final_spread_bp: number;
  total_allocated_k: number;
  deal_size_k: number;
  proposed_by: string;
  proposed_at: string;
  approved_by: string | null;
};

export type TermSheetRecord = {
  issuer: string | null;
  isin: string | null;
  currency: string | null;
  size_mm: number | null;
  coupon_pct: number | null;
  issue_date: string | null;
  maturity: string | null;
  format: string | null;
  listing: string | null;
  governing_law: string | null;
};
export type Extraction = {
  document_id: string;
  filename: string;
  deal_id: string | null;
  method: string;
  model: string | null;
  text_chars: number;
  record: TermSheetRecord;
};
export type Check = { field: string; rule: string; ok: boolean; severity: "error" | "warning"; message: string };
export type DiffRow = {
  field: string;
  term_sheet: string | null;
  booking: string | null;
  status: "match" | "mismatch" | "missing_in_term_sheet" | "missing_in_booking";
};
export type ValidationReport = {
  document_id: string;
  deal_id: string | null;
  checks: Check[];
  diff: DiffRow[] | null;
  has_errors: boolean;
  has_mismatch: boolean;
};
export type Sample = { filename: string; text: string; variant: string };
