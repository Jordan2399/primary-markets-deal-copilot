import { describe, expect, it } from "vitest";
import { relativeTime, splitCitations } from "./citations";
import { linksFor, safeNext } from "./session-utils";

describe("safeNext", () => {
  it("keeps normal paths", () => {
    expect(safeNext("/orderbook")).toBe("/orderbook");
    expect(safeNext("/copilot?deal=D-1&c=abc")).toBe("/copilot?deal=D-1&c=abc");
  });
  it("refuses anything that could leave the site", () => {
    for (const bad of ["https://evil.example", "//evil.example", "/\\evil.example", "javascript:alert(1)", "evil", "", null, undefined]) {
      expect(safeNext(bad as string | null | undefined)).toBe("/");
    }
  });
  it("does not loop back to login or into the API", () => {
    expect(safeNext("/login?next=/")).toBe("/");
    expect(safeNext("/api/session")).toBe("/");
  });
});

describe("linksFor", () => {
  const labels = (role: Parameters<typeof linksFor>[0]) => linksFor(role).map((l) => l.label);
  it("hides pages a role cannot use", () => {
    expect(labels("viewer")).not.toContain("Audit");
    expect(labels("viewer")).not.toContain("Order book");
    expect(labels("syndicate")).toContain("Allocation");
    expect(labels("marketer")).not.toContain("Allocation");
  });
  it("shows everything to admin", () => {
    expect(labels("admin")).toHaveLength(7);
  });
});

describe("splitCitations", () => {
  it("separates text and markers", () => {
    expect(splitCitations("Open [S1] and [S12].")).toEqual([
      { type: "text", text: "Open " },
      { type: "cite", id: "S1" },
      { type: "text", text: " and " },
      { type: "cite", id: "S12" },
      { type: "text", text: "." },
    ]);
  });
  it("leaves text without markers alone", () => {
    expect(splitCitations("nothing here")).toEqual([{ type: "text", text: "nothing here" }]);
    expect(splitCitations("")).toEqual([]);
  });
});

describe("relativeTime", () => {
  const now = new Date("2026-11-12T12:00:00Z");
  it("describes recent and older times", () => {
    expect(relativeTime("2026-11-12T11:59:40Z", now)).toBe("just now");
    expect(relativeTime("2026-11-12T11:30:00Z", now)).toBe("30 min ago");
    expect(relativeTime("2026-11-12T09:00:00Z", now)).toBe("3 h ago");
    expect(relativeTime("2026-11-11T09:00:00Z", now)).toBe("yesterday");
    expect(relativeTime("not a date", now)).toBe("");
  });
});
