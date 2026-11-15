import { describe, expect, it } from "vitest";
import { CENTER, SIZE, colorIndex, layoutNetwork } from "./network-layout";
import type { NetworkNode } from "./types";

function node(id: number, type: string, amount_k: number): NetworkNode {
  return { investor_id: `INV-${id}`, name: `Investor ${id}`, type, region: "UK", real_money: id % 2 === 0, amount_k, orders: 1 };
}

// 60 investors across all six types, with spread-out order sizes.
const many: NetworkNode[] = Array.from({ length: 60 }, (_, i) =>
  node(i, ["asset_manager", "insurer", "pension_fund", "bank_treasury", "official_institution", "hedge_fund"][i % 6], 5_000 + i * 700),
);

describe("layoutNetwork", () => {
  it("returns nothing for an empty book", () => {
    expect(layoutNetwork([])).toEqual({ nodes: [], sectors: [] });
  });

  it("is deterministic: the same data gives the same picture", () => {
    expect(layoutNetwork(many)).toEqual(layoutNetwork([...many].reverse()));
  });

  it("places every investor exactly once, inside the drawing area", () => {
    const { nodes } = layoutNetwork(many);
    expect(nodes).toHaveLength(60);
    expect(new Set(nodes.map((n) => n.id)).size).toBe(60);
    for (const n of nodes) {
      expect(n.x - n.r).toBeGreaterThanOrEqual(0);
      expect(n.x + n.r).toBeLessThanOrEqual(SIZE);
      expect(n.y - n.r).toBeGreaterThanOrEqual(0);
      expect(n.y + n.r).toBeLessThanOrEqual(SIZE);
    }
  });

  it("keeps each investor type inside its own wedge", () => {
    const { nodes, sectors } = layoutNetwork(many);
    for (const n of nodes) {
      const sector = sectors.find((s) => s.type === n.type)!;
      let a = Math.atan2(n.y - CENTER, n.x - CENTER);
      if (a < sector.start) a += 2 * Math.PI; // bring the angle into the wedge's range
      expect(a).toBeGreaterThanOrEqual(sector.start - 1e-9);
      expect(a).toBeLessThanOrEqual(sector.end + 1e-9);
    }
    // The wedges together cover the full circle.
    expect(sectors.reduce((sum, s) => sum + (s.end - s.start), 0)).toBeCloseTo(2 * Math.PI, 6);
  });

  it("draws bigger orders bigger and closer to the deal", () => {
    const { nodes } = layoutNetwork([node(1, "insurer", 100_000), node(2, "insurer", 1_000), node(3, "insurer", 50_000)]);
    const [big, mid, small] = ["INV-1", "INV-3", "INV-2"].map((id) => nodes.find((n) => n.id === id)!);
    expect(big.r).toBeGreaterThan(mid.r);
    expect(mid.r).toBeGreaterThan(small.r);
    const dist = (n: { x: number; y: number }) => Math.hypot(n.x - CENTER, n.y - CENTER);
    expect(dist(big)).toBeLessThanOrEqual(dist(small));
  });

  it("copes with a single investor and with 150 in one type", () => {
    expect(layoutNetwork([node(1, "hedge_fund", 1000)]).nodes).toHaveLength(1);
    const crowd = Array.from({ length: 150 }, (_, i) => node(i, "asset_manager", 1_000 + i));
    const { nodes } = layoutNetwork(crowd);
    expect(nodes).toHaveLength(150);
    expect(nodes.every((n) => Number.isFinite(n.x) && Number.isFinite(n.y))).toBe(true);
  });
});

describe("colorIndex", () => {
  it("is stable per type and falls back for unknown types", () => {
    expect(colorIndex("asset_manager")).toBe(0);
    expect(colorIndex("hedge_fund")).toBe(5);
    expect(colorIndex("something_new")).toBe(5);
  });
});
