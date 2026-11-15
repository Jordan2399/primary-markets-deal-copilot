/**
 * Layout of the investor network graph. A pure function: data in, coordinates out.
 *
 * The picture is a fan: the deal sits in the middle, the investors form wedges around it (one
 * wedge per investor type), and inside a wedge the biggest orders sit closest to the deal. Nothing
 * is random and nothing is simulated, so the same data always gives the same picture. That makes
 * it easy to compare two deals, to test, and to describe in a demo.
 */
import type { NetworkNode } from "./types";

/** Fixed order of the investor types. It also fixes each type's colour across all deals. */
export const INVESTOR_TYPES = [
  "asset_manager",
  "insurer",
  "pension_fund",
  "bank_treasury",
  "official_institution",
  "hedge_fund",
] as const;

// Drawing area in SVG units; the viewBox scales it to the screen.
export const SIZE = 640;
export const CENTER = SIZE / 2;
const MAX_RADIUS = 292; // outermost ring; nodes never go beyond this
const INNER_RADIUS = 74; // first ring, outside the deal circle in the middle
const RING_GAP = 28;
const SPACING = 26; // minimum distance between neighbouring nodes on one ring
const NODE_MIN = 4;
const NODE_MAX = 11;
const MIN_SECTOR_SHARE = 0.05; // a type with one investor still gets a readable wedge

export type PlacedNode = {
  id: string;
  name: string;
  type: string;
  region: string;
  realMoney: boolean;
  amountK: number;
  x: number;
  y: number;
  r: number;
  colorIndex: number;
};

export type Sector = {
  type: string;
  colorIndex: number;
  start: number; // radians, 0 = pointing right, growing clockwise on screen
  end: number;
  count: number;
  demandK: number;
};

export type Layout = { nodes: PlacedNode[]; sectors: Sector[] };

/** Index of a type in the colour list; an unknown type shares the last colour. */
export function colorIndex(type: string): number {
  const index = INVESTOR_TYPES.indexOf(type as (typeof INVESTOR_TYPES)[number]);
  return index < 0 ? INVESTOR_TYPES.length - 1 : index;
}

/** Place every investor. Types appear clockwise from the top in the fixed type order. */
export function layoutNetwork(nodes: NetworkNode[]): Layout {
  if (nodes.length === 0) return { nodes: [], sectors: [] };

  // Group by type.
  const groups = new Map<string, NetworkNode[]>();
  for (const node of nodes) groups.set(node.type, [...(groups.get(node.type) ?? []), node]);
  const types = [...groups.keys()].sort((a, b) => colorIndex(a) - colorIndex(b) || a.localeCompare(b));

  // Each wedge is proportional to its investor count, with a floor so small groups stay visible.
  const total = nodes.length;
  const weights = types.map((t) => Math.max(groups.get(t)!.length, total * MIN_SECTOR_SHARE));
  const weightSum = weights.reduce((a, b) => a + b, 0);
  const maxAmount = Math.max(...nodes.map((n) => n.amount_k), 1);

  const placed: PlacedNode[] = [];
  const sectors: Sector[] = [];
  let angle = -Math.PI / 2; // start at the top

  types.forEach((type, t) => {
    const span = (2 * Math.PI * weights[t]) / weightSum;
    const start = angle;
    const end = angle + span;
    angle = end;

    // Largest orders first (ties by id), so the biggest investors sit closest to the deal.
    const members = [...groups.get(type)!].sort((a, b) => b.amount_k - a.amount_k || a.investor_id.localeCompare(b.investor_id));
    sectors.push({
      type,
      colorIndex: colorIndex(type),
      start,
      end,
      count: members.length,
      demandK: members.reduce((sum, m) => sum + m.amount_k, 0),
    });

    // Fill ring after ring until everyone is placed. A ring holds as many nodes as fit on its arc.
    let done = 0;
    for (let ring = 0; done < members.length; ring++) {
      const radius = Math.min(INNER_RADIUS + ring * RING_GAP, MAX_RADIUS);
      const lastRing = radius >= MAX_RADIUS; // out of room: everything left goes on this ring
      const capacity = lastRing ? members.length - done : Math.max(1, Math.floor((span * radius) / SPACING));
      const take = Math.min(capacity, members.length - done);
      const pad = span * 0.06; // keep nodes off the wedge edges
      for (let j = 0; j < take; j++) {
        const m = members[done + j];
        const a = start + pad + ((span - 2 * pad) * (j + 0.5)) / take;
        placed.push({
          id: m.investor_id,
          name: m.name,
          type: m.type,
          region: m.region,
          realMoney: m.real_money,
          amountK: m.amount_k,
          x: CENTER + radius * Math.cos(a),
          y: CENTER + radius * Math.sin(a),
          r: NODE_MIN + (NODE_MAX - NODE_MIN) * Math.sqrt(m.amount_k / maxAmount),
          colorIndex: colorIndex(m.type),
        });
      }
      done += take;
    }
  });

  return { nodes: placed, sectors };
}
