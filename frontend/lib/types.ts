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
  | {
      event: "meta";
      data: {
        intent: string;
        model: string;
        sources: Source[];
        conversation_id: string | null;
        understood_as: string | null;
      };
    }
  | { event: "token"; data: { text: string } }
  | { event: "done"; data: { cited: string[]; audit_id: string | null; conversation_id: string | null } }
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
  source: "text" | "file"; // which input was read; the API accepts only one
  focused: boolean; // true when only the passages around the terms went to the model
  model_chars: number; // how many characters the model read
  not_found: string[]; // required fields no reader could find
  model_error: string | null; // why the model gave no answer, when the rules were used alone
  model_skipped: boolean; // true when the rules found every required field
  filled_by_model: string[]; // fields only the model filled
  language: string; // detected document language: en, de, fr, es, it or nl
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

/* ---- Sign-in and saved conversations ---- */

export type UserInfo = { username: string; display_name: string; role: Role; active: boolean };
export type DemoAccount = { username: string; display_name: string; role: Role };

export type ConversationSummary = {
  id: string;
  title: string;
  deal_id: string | null;
  created_at: string;
  updated_at: string;
  message_count: number;
};
export type StoredMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  sources: Source[];
  cited: string[];
  intent: string | null;
  audit_id: string | null;
};
export type ConversationDetail = ConversationSummary & { messages: StoredMessage[] };

/* ---- Day 3b: investors, the deal network and documents per deal ---- */

export type Investor = {
  id: string;
  name: string;
  type: string;
  region: string;
  real_money: boolean;
  esg_focus: boolean;
  ticket_mean_k: number;
  ticket_std_k: number;
  past_participation: number;
};
/** An investor plus a roll-up of its activity in the books we hold. */
export type InvestorSummary = Investor & { deals: number; orders: number; ordered_k: number; allocated_k: number };
export type Facet = { value: string; count: number };
export type InvestorPage = {
  total: number;
  page: number;
  page_size: number;
  items: InvestorSummary[];
  types: Facet[];
  regions: Facet[];
};
export type InvestorOrder = {
  investor_id: string;
  order_id: string;
  deal_id: string;
  deal_name: string;
  stage_name: string;
  currency: string;
  deal_size_mm: number;
  amount_k: number;
  limit_bp: number;
  placed_at: string;
  allocated_k: number | null;
};
export type InvestorProfile = { investor: InvestorSummary; orders: InvestorOrder[]; similar: InvestorSummary[] };
export type InvestorQuery = {
  q?: string;
  type?: string;
  region?: string;
  real_money?: boolean;
  esg?: boolean;
  sort?: "name" | "orders" | "ordered" | "participation";
  page?: number;
  page_size?: number;
};
export type NetworkNode = {
  investor_id: string;
  name: string;
  type: string;
  region: string;
  real_money: boolean;
  amount_k: number;
  orders: number;
};
export type NetworkGroup = { label: string; investors: number; demand_k: number; share_pct: number };
export type DealNetwork = {
  deal_id: string;
  deal_name: string;
  currency: string;
  deal_size_k: number;
  total_demand_k: number;
  nodes: NetworkNode[];
  by_type: NetworkGroup[];
  by_region: NetworkGroup[];
};
export type Target = { investor: InvestorSummary; score: number; reasons: string[]; cautions: string[] };
export type DocumentSummary = {
  id: string;
  filename: string;
  method: string;
  model: string | null;
  extracted_by: string;
  extracted_at: string;
  issuer: string | null;
  isin: string | null;
};

// ---- Reports, admin console and search (Day 3c) ----

export type Kpis = {
  active_deals: number; in_market: number; completed_deals: number; orders: number;
  investors_active: number; avg_cover: number | null; pending_approvals: number; blocking_tasks: number;
};
export type StageRow = { code: string; name: string; position: number; deals: number };
export type CurrencyVolume = { currency: string; deals: number; size_mm: number };
export type BookRow = {
  deal_id: string; name: string; issuer: string; currency: string; size_mm: number; stage_name: string;
  launch_date: string | null; tasks_done: number; tasks_total: number; blockers_open: number;
  orders: number; investors: number; demand_k: number; cover: number | null; allocated_k: number;
  allocation_state: "PROPOSED" | "APPROVED" | null;
};
export type Mix = { label: string; demand_k: number; share_pct: number };
export type ActivityDay = { day: string; events: number };
export type CountRow = { label: string; count: number };
export type ReportOverview = {
  generated_at: string; kpis: Kpis; stages: StageRow[]; volume: CurrencyVolume[]; books: BookRow[];
  mix_by_type: Mix[]; mix_by_region: Mix[]; activity: ActivityDay[]; top_actions: CountRow[];
};

export type UserActivity = {
  username: string; display_name: string; role: Role; active: boolean; actions: number; last_action: string | null;
};
export type AdminOverview = {
  users: UserActivity[]; roles: { role: Role; users: number }[];
  events_total: number; ai_calls: number; sign_ins: number; failed_sign_ins: number;
};

export type SearchResults = {
  query: string;
  deals: { id: string; name: string; issuer: string; stage: string }[];
  investors: { id: string; name: string; type: string; region: string }[];
};
