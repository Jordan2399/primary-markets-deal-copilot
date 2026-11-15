"use client";

import Link from "next/link";
import { BarList, LadderChart, LineChart } from "@/components/Charts";
import { CardSkeleton } from "@/components/Skeleton";
import { EmptyState, ErrorBox, Stat } from "@/components/ui";
import { ApiError, api } from "@/lib/client";
import { fmtK } from "@/lib/format";
import { useLoad } from "@/lib/use-load";

/** A summary of the deal's order book. Simulating a book stays on the full Order book page. */
export default function OrderBookTab({ dealId }: { dealId: string }) {
  const { data: book, error, loading } = useLoad(() => api.orderbook(dealId), [dealId]);

  if (loading && !book) return <CardSkeleton lines={5} label="Loading the order book" />;
  // 403 = this role may not read the book (the API enforces it); explain instead of showing an error.
  if (error instanceof ApiError && error.status === 403) {
    return <EmptyState title="The order book is for the Syndicate, Approver and Administrator roles.">Sign in with one of those roles to see it here.</EmptyState>;
  }
  if (error) return <ErrorBox error={error} />;
  const m = book?.metrics;
  if (!book || !m) {
    return (
      <EmptyState title="No orders yet">
        The book opens at the Book building stage. A syndicate user can <Link href={`/orderbook?deal=${dealId}`}>simulate a book</Link>.
      </EmptyState>
    );
  }

  return (
    <>
      <section className="stats">
        <Stat name="Cover" value={`${m.cover_ratio}x`} note={`${fmtK(m.valid_demand_k)} of ${fmtK(m.deal_size_k)}`} />
        <Stat name="Valid orders" value={String(m.valid_order_count)} note={`${m.order_count} placed`} />
        <Stat name="Investors" value={String(m.investor_count)} />
        <Stat name="Real money" value={`${m.real_money_share_pct}%`} note="of valid demand" />
        <Stat name="Flagged" value={String(m.anomaly_count)} note="anomalies" tone={m.anomaly_count > 0 ? "warn" : undefined} />
        <Stat name="Suggested final" value={m.suggested_final_spread_bp != null ? `${m.suggested_final_spread_bp}bp` : "-"} note="tightest at 1.5x cover" />
      </section>
      <div className="grid2">
        <section className="card"><h2>Demand over time</h2><LineChart points={m.timeline} ariaLabel="Cumulative demand over the book window" /></section>
        <section className="card"><h2>Demand by spread limit (bp)</h2><LadderChart levels={m.ladder} dealSizeK={m.deal_size_k} finalBp={m.suggested_final_spread_bp} /></section>
        <section className="card"><BarList title="By investor type" buckets={m.by_type} /></section>
        <section className="card"><BarList title="By region" buckets={m.by_region} /></section>
      </div>
      <p><Link href={`/orderbook?deal=${dealId}`}>Open the full order book</Link> for every order and the anomaly list.</p>
    </>
  );
}
