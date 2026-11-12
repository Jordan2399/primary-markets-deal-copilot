"use client";

import { useCallback, useEffect, useState } from "react";
import { BarList, LadderChart, LineChart } from "@/components/Charts";
import DealSelect from "@/components/DealSelect";
import { ErrorBox, Pill, fmtTime } from "@/components/ui";
import { api, getRole } from "@/lib/client";
import { fmtClock, fmtK, label } from "@/lib/format";
import type { OrderBook } from "@/lib/types";

export default function OrderBookPage() {
  const [dealId, setDealId] = useState("");
  const [book, setBook] = useState<OrderBook | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [seed, setSeed] = useState(1);
  const [cover, setCover] = useState(2.8);
  const [role, setRole] = useState("viewer");

  useEffect(() => setRole(getRole()), []);
  const allowed = ["syndicate", "approver", "admin"].includes(role);
  const canSimulate = ["syndicate", "admin"].includes(role);

  const load = useCallback(async (id: string) => {
    if (!id || !allowed) return;
    try {
      setBook(await api.orderbook(id));
      setError(null);
    } catch (e) {
      setBook(null);
      setError(e);
    }
  }, [allowed]);

  useEffect(() => {
    void load(dealId);
  }, [dealId, load]);

  async function simulate(extend: boolean) {
    setBusy(true);
    try {
      setBook(await api.simulate(dealId, { seed, target_cover: cover, anomalies: 4, extend }));
      setError(null);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  const m = book?.metrics;
  return (
    <main className="container wide">
      <h1>Order book</h1>
      <p className="muted">Demand, price tension and flagged orders for deals from Book building onwards. All orders are synthetic.</p>
      {!allowed ? (
        <div className="alert">The order book is for the syndicate, approver and admin roles. Switch the demo role at the top right.</div>
      ) : (
        <>
          <div className="row">
            <DealSelect value={dealId} onChange={setDealId} bookStagesOnly />
            {canSimulate && (
              <>
                <label className="inline">Seed <input type="number" min={0} max={9999} value={seed} onChange={(e) => setSeed(Number(e.target.value))} style={{ width: 80 }} /></label>
                <label className="inline">Target cover <input type="number" step={0.1} min={1} max={6} value={cover} onChange={(e) => setCover(Number(e.target.value))} style={{ width: 80 }} /></label>
                <button disabled={busy || !dealId} onClick={() => simulate(false)}>Simulate new book</button>
                <button disabled={busy || !dealId} onClick={() => simulate(true)}>Add more orders</button>
              </>
            )}
          </div>
          <ErrorBox error={error} />
          {book && !m && <p className="muted">This deal has no orders yet. {canSimulate ? "Use Simulate new book." : "A syndicate user can simulate one."}</p>}

          {book && m && (
            <>
              <section className="stats">
                <Stat name="Cover" value={`${m.cover_ratio}x`} note={`${fmtK(m.valid_demand_k)} of ${fmtK(m.deal_size_k)}`} />
                <Stat name="Valid orders" value={String(m.valid_order_count)} note={`${m.order_count} placed`} />
                <Stat name="Investors" value={String(m.investor_count)} />
                <Stat name="Real money" value={`${m.real_money_share_pct}%`} note="of valid demand" />
                <Stat name="Flagged" value={String(m.anomaly_count)} note="anomalies" />
                <Stat name="IPT" value={book.params ? `${book.params.ipt_bp}bp` : "-"} note={book.params ? `${fmtClock(book.params.open_at)}-${fmtClock(book.params.close_at)} UTC` : ""} />
                <Stat name="Suggested final" value={m.suggested_final_spread_bp != null ? `${m.suggested_final_spread_bp}bp` : "-"} note="tightest at 1.5x cover" />
              </section>

              <div className="grid2">
                <section className="card"><h2>Demand over time</h2><LineChart points={m.timeline} ariaLabel="Cumulative demand over the book window" /></section>
                <section className="card"><h2>Demand by spread limit (bp)</h2><LadderChart levels={m.ladder} dealSizeK={m.deal_size_k} finalBp={m.suggested_final_spread_bp} /></section>
                <section className="card"><BarList title="By investor type" buckets={m.by_type} /></section>
                <section className="card"><BarList title="By region" buckets={m.by_region} /></section>
              </div>

              <section className="card">
                <h2>Anomalies ({book.anomalies.length})</h2>
                {book.anomalies.length === 0 ? <p className="muted">None found.</p> : (
                  <table>
                    <thead><tr><th>Order</th><th>Rule</th><th>Effect</th><th>Why</th></tr></thead>
                    <tbody>
                      {book.anomalies.map((a, i) => (
                        <tr key={`${a.order_id}-${a.rule}-${i}`}>
                          <td>{a.order_id.split(":")[1]}</td>
                          <td><Pill tone={a.severity === "high" ? "bad" : "warn"}>{label(a.rule)}</Pill></td>
                          <td>{a.excludes ? "excluded from allocation" : "flagged for review"}</td>
                          <td className="small">{a.message}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </section>

              <section className="card scroll">
                <h2>Orders ({book.orders.length})</h2>
                <table>
                  <thead><tr><th>Time (UTC)</th><th>Investor</th><th>Type</th><th>Region</th><th>Amount</th><th>Limit</th><th>Flags</th></tr></thead>
                  <tbody>
                    {book.orders.map((o) => (
                      <tr key={o.id}>
                        <td>{fmtTime(o.placed_at)}</td>
                        <td>{o.investor_name}</td>
                        <td>{label(o.investor_type)}</td>
                        <td>{o.region}</td>
                        <td>{fmtK(o.amount_k)}</td>
                        <td>{o.limit_bp}bp</td>
                        <td>{o.flags.map((f) => <Pill key={f} tone="warn">{label(f)}</Pill>)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
            </>
          )}
        </>
      )}
    </main>
  );
}

function Stat({ name, value, note }: { name: string; value: string; note?: string }) {
  return (
    <div className="stat">
      <div className="muted small">{name}</div>
      <div className="stat-value">{value}</div>
      {note ? <div className="muted small">{note}</div> : null}
    </div>
  );
}
