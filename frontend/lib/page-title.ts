/** Browser tab titles and the time-of-day greeting. Pure functions, so they are easy to test. */

// Longest prefix first is not needed: each entry is a distinct first path segment.
const TITLES: Record<string, string> = {
  orderbook: "Order book",
  allocation: "Allocation",
  investors: "Investors",
  termsheets: "Term sheets",
  copilot: "Copilot",
  audit: "Audit trail",
  status: "System status",
  deals: "Deal",
  login: "Sign in",
};

/** "Order book · Deal Copilot" for /orderbook; "Pipeline · Deal Copilot" for the home page. */
export function titleFor(pathname: string): string {
  const first = pathname.split("/").filter(Boolean)[0];
  const page = first ? TITLES[first] : "Pipeline";
  return page ? `${page} · Deal Copilot` : "Deal Copilot";
}

/** "Good morning", "Good afternoon" or "Good evening" for an hour 0-23. */
export function greeting(hour: number): string {
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

/** First name from a display name such as "Anna Keller (Syndicate)". */
export function firstName(displayName: string): string {
  return displayName.replace(/\s*\(.*\)/, "").trim().split(/\s+/)[0] ?? "";
}
