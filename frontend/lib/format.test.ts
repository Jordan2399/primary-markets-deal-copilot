import { describe, expect, it } from "vitest";
import { fmtK, fmtPct, label } from "./format";

describe("format", () => {
  it("shows thousands as millions", () => {
    expect(fmtK(750_000)).toBe("750m");
    expect(fmtK(12_500)).toBe("12.5m");
    expect(fmtK(1_234_567)).toBe("1,234.6m");
  });
  it("formats percentages and labels", () => {
    expect(fmtPct(33.333)).toBe("33.3%");
    expect(label("real_money")).toBe("real money");
  });
});
