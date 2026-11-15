"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState, type KeyboardEvent } from "react";
import { fmtK, label } from "@/lib/format";
import { CENTER, SIZE, colorIndex, layoutNetwork } from "@/lib/network-layout";
import type { DealNetwork } from "@/lib/types";

const WEDGE_LENGTH = 300; // how far the divider lines between investor types reach from the centre

/**
 * The investors in one deal's book, drawn as a fan around the deal.
 *
 *   wedge = investor type     size = order amount     filled = real money, hollow = trading account
 *
 * The positions come from `layoutNetwork` (a pure, tested function), so this component only draws.
 * Every node is keyboard-focusable and opens the investor's page; a table view shows the same
 * data for anyone who prefers it or uses a screen reader.
 */
export default function InvestorNetwork({ network }: { network: DealNetwork }) {
  const router = useRouter();
  const [asTable, setAsTable] = useState(false);
  // Layout is recomputed only when the data changes.
  const layout = useMemo(() => layoutNetwork(network.nodes), [network.nodes]);

  if (network.nodes.length === 0) return null;

  const open = (id: string) => router.push(`/investors/${encodeURIComponent(id)}`);
  const onKey = (event: KeyboardEvent, id: string) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      open(id);
    }
  };

  return (
    <div>
      <div className="row between">
        <p className="muted small">
          {network.nodes.length} investors, {fmtK(network.total_demand_k)} of orders for a {fmtK(network.deal_size_k)} deal.
        </p>
        <button type="button" className="small-btn" onClick={() => setAsTable((v) => !v)} aria-pressed={asTable}>
          {asTable ? "Show graph" : "Show as table"}
        </button>
      </div>

      {asTable ? (
        <div className="scroll">
          <table>
            <thead><tr><th>Investor</th><th>Type</th><th>Region</th><th>Real money</th><th>Orders</th><th>Amount</th></tr></thead>
            <tbody>
              {network.nodes.map((n) => (
                <tr key={n.investor_id}>
                  <td><Link href={`/investors/${n.investor_id}`}>{n.name}</Link></td>
                  <td>{label(n.type)}</td>
                  <td>{n.region}</td>
                  <td>{n.real_money ? "yes" : "no"}</td>
                  <td>{n.orders}</td>
                  <td>{fmtK(n.amount_k)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="network">
          <svg viewBox={`0 0 ${SIZE} ${SIZE}`} role="group" aria-label={`Investors in the ${network.deal_name} book, grouped by type`}>
            {/* Divider lines between the wedges of the different investor types. */}
            {layout.sectors.map((s) => (
              <line key={s.type} className="net-wedge" x1={CENTER} y1={CENTER}
                x2={CENTER + WEDGE_LENGTH * Math.cos(s.start)} y2={CENTER + WEDGE_LENGTH * Math.sin(s.start)} />
            ))}
            {/* The deal in the middle. */}
            <circle className="net-deal" cx={CENTER} cy={CENTER} r={54} />
            <text className="net-deal-text" x={CENTER} y={CENTER - 2}>{network.currency} {fmtK(network.deal_size_k)}</text>
            <text className="net-deal-text" x={CENTER} y={CENTER + 14}>book</text>
            {layout.nodes.map((n) => (
              <g key={n.id} className="net-node" tabIndex={0} role="link"
                aria-label={`${n.name}, ${label(n.type)}, ${n.region}, orders ${fmtK(n.amountK)}`}
                onClick={() => open(n.id)} onKeyDown={(e) => onKey(e, n.id)}>
                <circle cx={n.x} cy={n.y} r={n.r} className={`t${n.colorIndex} ${n.realMoney ? "filled" : "hollow"}`} />
                <title>{`${n.name} - ${label(n.type)}, ${n.region}\n${fmtK(n.amountK)}${n.realMoney ? ", real money" : ", trading account"}`}</title>
              </g>
            ))}
          </svg>

          <div>
            <h3>By investor type</h3>
            <ul className="legend">
              {network.by_type.map((g) => (
                <li key={g.label}>
                  <span><span className={`swatch t${colorIndex(g.label)}`} />{label(g.label)}</span>
                  <span>{g.investors} &middot; {fmtK(g.demand_k)} <span className="muted">({g.share_pct}%)</span></span>
                </li>
              ))}
            </ul>
            <h3 style={{ marginTop: 18 }}>By region</h3>
            <ul className="legend">
              {network.by_region.map((g) => (
                <li key={g.label}><span>{g.label}</span><span>{g.investors} &middot; {fmtK(g.demand_k)} <span className="muted">({g.share_pct}%)</span></span></li>
              ))}
            </ul>
            <p className="muted small legend-note">Circle size shows the order amount. Filled circles are real-money accounts, hollow ones are trading accounts. Click an investor to open the profile.</p>
          </div>
        </div>
      )}
    </div>
  );
}
