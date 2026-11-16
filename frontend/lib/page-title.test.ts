import { describe, expect, it } from "vitest";
import { firstName, greeting, titleFor } from "./page-title";

describe("titleFor", () => {
  it("names the home page Pipeline", () => expect(titleFor("/")).toBe("Pipeline · Deal Copilot"));
  it("uses the first path segment", () => {
    expect(titleFor("/orderbook")).toBe("Order book · Deal Copilot");
    expect(titleFor("/deals/D-2026-007")).toBe("Deal · Deal Copilot");
  });
  it("falls back for unknown pages", () => expect(titleFor("/nope")).toBe("Deal Copilot"));
});

describe("greeting", () => {
  it("changes over the day", () => {
    expect(greeting(8)).toBe("Good morning");
    expect(greeting(12)).toBe("Good afternoon");
    expect(greeting(18)).toBe("Good evening");
  });
});

describe("firstName", () => {
  it("drops the role suffix", () => expect(firstName("Anna Keller (Syndicate)")).toBe("Anna"));
  it("copes with one word", () => expect(firstName("admin")).toBe("admin"));
});
