"use client";

import Link from "next/link";
import { use } from "react";
import { CardSkeleton } from "@/components/Skeleton";
import { EmptyState, ErrorBox, Pill, Stat, fmtTime } from "@/components/ui";
import { ApiError, api } from "@/lib/client";
import { fmtK, label } from "@/lib/format";
import { useLoad } from "@/lib/use-load";

/** One investor: facts, what they did on each deal, and investors that look similar. */
export default function InvestorProfilePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data, error, loading } = useLoad(() => api.investor(id), [id]);

  if (error instanceof ApiError && error.status === 403) {
    return (
      <main className="container wide">
        <EmptyState title="Investor data is for the Marketer, Syndicate, Approver and Administrator roles.">Sign in with one of those roles to use this page.</EmptyState>
      </main>
    );
  }
  if (error instanceof ApiError && error.status === 404) {
    return (
      <main className="container wide">
        <EmptyState title="Investor not found"><Link href="/investors">Back to the directory</Link></EmptyState>
      </main>
    );
  }
  if (loading && !data) return <main className="container wide"><CardSkeleton lines={5} label="Loading the investor" /></main>;
  if (error || !data) return <main className="container wide"><ErrorBox error={error} /></main>;

  const { investor: inv, orders, similar } = data;
  return (
    <main className="container wide">
      <nav className="crumbs" aria-label="Breadcrumb">
        <Link href="/investors">Investors</Link> <span aria-hidden="true">/</span> <span aria-current="page">{inv.name}</span>
      </nav>
      <div className="row between">
        <div>
          <h1>{inv.name}</h1>
          <p className="muted">
            {label(inv.type)} &middot; {inv.region} &middot; {inv.real_money ? "real-money account" : "trading account"}
            {inv.esg_focus && <> &middot; <Pill tone="good">ESG focus</Pill></>}
          </p>
        </div>
      </div>

      <section className="stats">
        <Stat name="Typical ticket" value={fmtK(inv.ticket_mean_k)} note={`spread about ${fmtK(inv.ticket_std_k)}`} />
        <Stat name="Past deals" value={String(inv.past_participation)} note="before the deals shown here" />
        <Stat name="Deals here" value={String(inv.deals)} />
        <Stat name="Ordered" value={inv.ordered_k ? fmtK(inv.ordered_k) : "-"} note={`${inv.orders} orders`} />
        <Stat name="Allocated" value={inv.allocated_k ? fmtK(inv.allocated_k) : "-"} note={inv.ordered_k ? `${Math.round((100 * inv.allocated_k) / inv.ordered_k)}% of ordered` : undefined} />
      </section>

      <section className="card">
        <h2>Orders by deal</h2>
        {orders.length === 0 ? (
          <EmptyState title="No orders yet">This investor has not placed an order in any book we hold.</EmptyState>
        ) : (
          <div className="table-wrap"><table>
            <thead><tr><th>Deal</th><th>Stage</th><th>Ordered</th><th>Limit</th><th>Allocated</th><th>Placed</th></tr></thead>
            <tbody>
              {orders.map((o) => (
                <tr key={o.order_id}>
                  <td><Link href={`/deals/${o.deal_id}?tab=investors`}>{o.deal_name}</Link></td>
                  <td>{o.stage_name}</td>
                  <td>{o.currency} {fmtK(o.amount_k)}</td>
                  <td>{o.limit_bp}bp</td>
                  <td>{o.allocated_k == null ? <span className="muted">not allocated yet</span> : `${o.currency} ${fmtK(o.allocated_k)}`}</td>
                  <td className="small">{fmtTime(o.placed_at)}</td>
                </tr>
              ))}
            </tbody>
          </table></div>
        )}
      </section>

      <section className="card">
        <h2>Similar investors</h2>
        <p className="muted small">Same type and region, closest typical ticket first.</p>
        {similar.length === 0 ? (
          <p className="muted">No similar investors.</p>
        ) : (
          <div className="table-wrap"><table>
            <thead><tr><th>Investor</th><th>Typical ticket</th><th>Past deals</th></tr></thead>
            <tbody>
              {similar.map((s) => (
                <tr key={s.id}>
                  <td><Link href={`/investors/${s.id}`}>{s.name}</Link></td>
                  <td>{fmtK(s.ticket_mean_k)}</td>
                  <td>{s.past_participation}</td>
                </tr>
              ))}
            </tbody>
          </table></div>
        )}
      </section>
    </main>
  );
}
