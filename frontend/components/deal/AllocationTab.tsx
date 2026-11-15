"use client";

import Link from "next/link";
import { CardSkeleton } from "@/components/Skeleton";
import { EmptyState, ErrorBox, Pill, Stat, fmtTime } from "@/components/ui";
import { ApiError, api } from "@/lib/client";
import { fmtK } from "@/lib/format";
import { useLoad } from "@/lib/use-load";

/** The latest allocation proposal for the deal: state, key figures, bands and the explanation. */
export default function AllocationTab({ dealId }: { dealId: string }) {
  // Two steps: the list of proposals first, then the newest one in full.
  const { data: proposal, error, loading } = useLoad(async () => {
    const list = await api.proposals(dealId);
    // Prefer an approved proposal; otherwise the newest open one (the list is newest first).
    const pick = list.find((p) => p.state === "APPROVED") ?? list.find((p) => p.state === "PROPOSED");
    return pick ? await api.proposal(pick.id) : null;
  }, [dealId]);

  if (loading && proposal === null && !error) return <CardSkeleton lines={5} label="Loading the allocation" />;
  if (error instanceof ApiError && error.status === 403) {
    return <EmptyState title="Allocation is for the Syndicate, Approver and Administrator roles.">Sign in with one of those roles to see it here.</EmptyState>;
  }
  if (error) return <ErrorBox error={error} />;
  if (!proposal) {
    return (
      <EmptyState title="No allocation proposed yet">
        Once the book has closed, a syndicate user can <Link href={`/allocation?deal=${dealId}`}>propose an allocation</Link>. A different person approves it (four-eyes).
      </EmptyState>
    );
  }

  const approved = proposal.state === "APPROVED";
  return (
    <>
      <section className="stats">
        <Stat name="State" value={approved ? "Approved" : "Proposed"} note={approved ? `by ${proposal.approved_by}` : `by ${proposal.proposed_by}, awaiting approval`} />
        <Stat name="Final spread" value={`${proposal.final_spread_bp}bp`} />
        <Stat name="Allocated" value={fmtK(proposal.total_allocated_k)} note={`of ${fmtK(proposal.deal_size_k)}`} />
        <Stat name="Eligible demand" value={fmtK(proposal.eligible_demand_k)} />
      </section>
      <section className="card">
        <div className="row between">
          <h2>Proposal {proposal.id.split(":").pop()}</h2>
          <Pill tone={approved ? "good" : "warn"}>{approved ? "approved" : "waiting for approval"}</Pill>
        </div>
        <p className="muted small">Proposed {fmtTime(proposal.proposed_at)} by {proposal.proposed_by}.</p>
        <p>{proposal.explanation}</p>
        <p className="muted small">Explanation written by: {proposal.explanation_source}.</p>
      </section>
      <section className="card">
        <h2>Priority bands</h2>
        <div className="table-wrap">
<table>
          <thead><tr><th>Band</th><th>Orders</th><th>Demand</th><th>Allocated</th><th>Scale</th></tr></thead>
          <tbody>
            {proposal.bands.map((b) => (
              <tr key={b.band}><td>{b.band}</td><td>{b.orders}</td><td>{fmtK(b.demand_k)}</td><td>{fmtK(b.allocated_k)}</td><td>{b.scale_pct}%</td></tr>
            ))}
          </tbody>
        </table>
</div>
      </section>
      <p><Link href={`/allocation?deal=${dealId}`}>Open the allocation page</Link> to preview other spreads or approve.</p>
    </>
  );
}
