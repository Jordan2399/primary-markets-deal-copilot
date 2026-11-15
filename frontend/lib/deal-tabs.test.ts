import { describe, expect, it } from "vitest";
import { daysUntil, parseTab, withTab } from "./deal-tabs";

describe("parseTab", () => {
  it("reads a known tab and defaults to overview", () => {
    expect(parseTab("?tab=orderbook")).toBe("orderbook");
    expect(parseTab("?deal=D-1&tab=investors")).toBe("investors");
    expect(parseTab("")).toBe("overview");
    expect(parseTab("?tab=<script>")).toBe("overview");
    expect(parseTab("?tab=")).toBe("overview");
  });
});

describe("withTab", () => {
  it("sets the tab and keeps other parameters", () => {
    expect(withTab("", "allocation")).toBe("?tab=allocation");
    expect(withTab("?x=1&tab=timeline", "documents")).toBe("?x=1&tab=documents");
  });
  it("drops the parameter for the default tab", () => {
    expect(withTab("?tab=timeline", "overview")).toBe("");
    expect(withTab("?x=1&tab=timeline", "overview")).toBe("?x=1");
  });
});

describe("daysUntil", () => {
  const now = new Date(2026, 10, 14, 15, 30); // 14 Nov 2026, afternoon
  it("counts whole days, ignoring the time of day", () => {
    expect(daysUntil("2026-11-14", now)).toBe(0);
    expect(daysUntil("2026-11-28", now)).toBe(14);
    expect(daysUntil("2026-11-10", now)).toBe(-4);
  });
  it("is null without a date", () => {
    expect(daysUntil(null, now)).toBeNull();
  });
});
