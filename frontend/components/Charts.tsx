"use client";

/**
 * Small SVG charts. They draw only what the API computed; no chart calculates its own numbers.
 * Colour is never the only signal: values are printed, and shapes differ.
 */
import { fmtK, label } from "@/lib/format";
import type { Bucket, LadderLevel, TimelinePoint } from "@/lib/types";

const W = 520;
const H = 200;
const PAD = { l: 46, r: 12, t: 12, b: 28 };

export function LineChart({ points, ariaLabel }: { points: TimelinePoint[]; ariaLabel: string }) {
  if (points.length < 2) return <p className="muted small">No data yet.</p>;
  const maxY = Math.max(...points.map((p) => p.cumulative_demand_k), 1);
  const maxX = Math.max(...points.map((p) => p.minute), 1);
  const x = (m: number) => PAD.l + (m / maxX) * (W - PAD.l - PAD.r);
  const y = (v: number) => H - PAD.b - (v / maxY) * (H - PAD.t - PAD.b);
  const path = points.map((p, i) => `${i ? "L" : "M"}${x(p.minute).toFixed(1)},${y(p.cumulative_demand_k).toFixed(1)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={ariaLabel} className="chart">
      <line x1={PAD.l} y1={H - PAD.b} x2={W - PAD.r} y2={H - PAD.b} className="axis" />
      <line x1={PAD.l} y1={PAD.t} x2={PAD.l} y2={H - PAD.b} className="axis" />
      <text x={PAD.l - 6} y={PAD.t + 8} textAnchor="end" className="tick">{fmtK(maxY)}</text>
      <text x={PAD.l - 6} y={H - PAD.b} textAnchor="end" className="tick">0</text>
      <text x={PAD.l} y={H - 8} className="tick">open</text>
      <text x={W - PAD.r} y={H - 8} textAnchor="end" className="tick">close ({Math.round(maxX / 60)}h)</text>
      <path d={path} className="line" fill="none" />
    </svg>
  );
}

export function LadderChart({ levels, dealSizeK, finalBp }: { levels: LadderLevel[]; dealSizeK: number; finalBp?: number | null }) {
  if (levels.length === 0) return <p className="muted small">No data yet.</p>;
  const maxY = Math.max(dealSizeK, ...levels.map((l) => l.demand_k), 1);
  const slot = (W - PAD.l - PAD.r) / levels.length;
  const y = (v: number) => H - PAD.b - (v / maxY) * (H - PAD.t - PAD.b);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Demand by spread limit" className="chart">
      <line x1={PAD.l} y1={H - PAD.b} x2={W - PAD.r} y2={H - PAD.b} className="axis" />
      {levels.map((l, i) => (
        <g key={l.spread_bp}>
          <rect
            x={PAD.l + i * slot + 2}
            y={y(l.demand_k)}
            width={Math.max(slot - 4, 2)}
            height={H - PAD.b - y(l.demand_k)}
            className={l.spread_bp === finalBp ? "bar picked" : "bar"}
          >
            <title>{`${l.spread_bp}bp: ${fmtK(l.demand_k)} (${l.cover}x)`}</title>
          </rect>
          {(levels.length <= 12 || i % 2 === 0) && (
            <text x={PAD.l + i * slot + slot / 2} y={H - 10} textAnchor="middle" className="tick">{l.spread_bp}</text>
          )}
        </g>
      ))}
      <line x1={PAD.l} y1={y(dealSizeK)} x2={W - PAD.r} y2={y(dealSizeK)} className="sizeline" />
      <text x={W - PAD.r} y={y(dealSizeK) - 4} textAnchor="end" className="tick">deal size {fmtK(dealSizeK)}</text>
      <text x={PAD.l - 6} y={PAD.t + 8} textAnchor="end" className="tick">{fmtK(maxY)}</text>
    </svg>
  );
}

export function BarList({ buckets, title }: { buckets: Bucket[]; title: string }) {
  const max = Math.max(...buckets.map((b) => b.demand_k), 1);
  return (
    <div>
      <h3>{title}</h3>
      {buckets.length === 0 && <p className="muted small">No data yet.</p>}
      <ul className="bars">
        {buckets.map((b) => (
          <li key={b.label}>
            <span className="bar-label">{label(b.label)}</span>
            <span className="bar-track"><span className="bar-fill" style={{ width: `${(b.demand_k / max) * 100}%` }} /></span>
            <span className="bar-value">{fmtK(b.demand_k)} <span className="muted">({b.share_pct}%)</span></span>
          </li>
        ))}
      </ul>
    </div>
  );
}
