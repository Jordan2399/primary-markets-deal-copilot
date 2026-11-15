/** The tabs of the deal workspace and how they are stored in the address bar (?tab=orderbook). */

export const DEAL_TABS = [
  { id: "overview", label: "Overview" },
  { id: "checklist", label: "Checklist" },
  { id: "orderbook", label: "Order book" },
  { id: "allocation", label: "Allocation" },
  { id: "documents", label: "Documents" },
  { id: "investors", label: "Investors" },
  { id: "timeline", label: "Timeline" },
] as const;

export type DealTabId = (typeof DEAL_TABS)[number]["id"];

const IDS = new Set<string>(DEAL_TABS.map((t) => t.id));

/** The tab named in a query string ("?tab=orderbook"); anything unknown falls back to Overview. */
export function parseTab(search: string): DealTabId {
  const value = new URLSearchParams(search).get("tab") ?? "";
  return IDS.has(value) ? (value as DealTabId) : "overview";
}

/** The query string with `tab` set, keeping every other parameter. Overview is the default, so it is left out. */
export function withTab(search: string, tab: DealTabId): string {
  const params = new URLSearchParams(search);
  if (tab === "overview") params.delete("tab");
  else params.set("tab", tab);
  const text = params.toString();
  return text ? `?${text}` : "";
}

/** Whole days from today until a YYYY-MM-DD date (negative when it has passed); null without a date. */
export function daysUntil(date: string | null, now: Date = new Date()): number | null {
  if (!date) return null;
  const target = new Date(`${date}T00:00:00`);
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  return Math.round((target.getTime() - today.getTime()) / 86_400_000);
}
