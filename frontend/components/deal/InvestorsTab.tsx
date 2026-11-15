"use client";

import Link from "next/link";
import InvestorNetwork from "@/components/InvestorNetwork";
import { CardSkeleton } from "@/components/Skeleton";
import { EmptyState, ErrorBox } from "@/components/ui";
import { ApiError, api } from "@/lib/client";
import { fmtK, label } from "@/lib/format";
import { useLoad } from "@/lib/use-load";

/** Who is in the deal's book (graph) and who should be called next (ranked target list). */
export default function InvestorsTab({ dealId }: { dealId: string }) {
  const network = useLoad(() => api.investorNetwork(dealId), [dealId]);
  const targets = useLoad(() => api.investorTargets(dealId, 15), [dealId]);

  // 403 = viewers may not see investor data (the API enforces it); say so plainly.
  const denied = [network.error, targets.error].find((e) => e instanceof ApiError && e.status === 403);
  if (denied) {
    return <EmptyState title="Investor data is for the Marketer, Syndicate, Approver and Administrator roles.">Sign in with one of those roles to see it here.</EmptyState>;
  }
  if (network.loading && !network.data) return <CardSkeleton lines={6} label="Loading the investor network" />;

  return (
    <>
      <section className="card">
        <h2>Investors in the book</h2>
        <ErrorBox error={network.error} />
        {network.data && network.data.nodes.length === 0 ? (
          <EmptyState title="No orders yet">The graph appears once the book has orders. The target list below works already.</EmptyState>
        ) : (
          network.data && <InvestorNetwork network={network.data} />
        )}
      </section>

      <section className="card">
        <h2>Who to call next</h2>
        <p className="muted small">
          Investors not yet in the book, ranked by a fit score out of 100: real-money account (30), past deals (25), typical ticket against the
          deal size (30) and a region the book lacks (15). Each score lists its reasons.
        </p>
        <ErrorBox error={targets.error} />
        {targets.loading && !targets.data ? <CardSkeleton lines={4} label="Loading targets" /> : (
          targets.data && (
            <div className="table-wrap">
<table>
              <thead><tr><th>Score</th><th>Investor</th><th>Type</th><th>Region</th><th>Typical ticket</th><th>Why</th></tr></thead>
              <tbody>
                {targets.data.map((t) => (
                  <tr key={t.investor.id}>
                    <td>
                      <span className="score">{t.score}<span className="score-bar"><span style={{ width: `${t.score}%` }} /></span></span>
                    </td>
                    <td><Link href={`/investors/${t.investor.id}`}>{t.investor.name}</Link></td>
                    <td>{label(t.investor.type)}</td>
                    <td>{t.investor.region}</td>
                    <td>{fmtK(t.investor.ticket_mean_k)}</td>
                    <td>
                      <ul className="reasons">
                        {t.reasons.map((r) => <li key={r}>{r}</li>)}
                        {t.cautions.map((c) => <li key={c} className="caution">{c}</li>)}
                      </ul>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
</div>
          )
        )}
      </section>
    </>
  );
}
