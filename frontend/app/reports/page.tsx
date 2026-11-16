"use client";

import Link from "next/link";
import { ActivityColumns, BarList, StageBars } from "@/components/Charts";
import { Skeleton } from "@/components/Skeleton";
import { EmptyState, ErrorBox, Pill, Stat, fmtDate, fmtTime } from "@/components/ui";
import { api } from "@/lib/client";
import { label } from "@/lib/format";
import { useLoad } from "@/lib/use-load";
import type { BookRow, Mix } from "@/lib/types";

/** The report API sends shares; the bar list component wants buckets, so fill in what it ignores. */
const asBuckets = (mix: Mix[]) => mix.map((m) => ({ ...m, orders: 0 }));

/** Cover colour: under 1.0x the book is not covered, 2x and up is comfortable. */
function coverTone(cover: number | null): "good" | "warn" | "bad" | "plain" {
  if (cover === null) return "plain";
  if (cover < 1) return "bad";
  return cover >= 2 ? "good" : "warn";
}

function AllocationPill({ row }: { row: BookRow }) {
  if (row.allocation_state === "APPROVED") return <Pill tone="good">Approved</Pill>;
  if (row.allocation_state === "PROPOSED") return <Pill tone="warn">Awaiting approval</Pill>;
  return <span className="muted">None</span>;
}

/** Management view: pipeline, books, demand mix and activity across all deals. Open to every role. */
export default function ReportsPage() {
  const { data, error, loading } = useLoad(() => api.reportOverview(), []);

  return (
    <main className="container wide report">
      <div className="page-head">
        <div>
          <p className="eyebrow">Reports</p>
          <h1>Pipeline and book report</h1>
          <p className="muted">
            {data ? `Generated ${fmtTime(data.generated_at)}. ` : ""}All figures are calculated from the deals, books and allocations as they are now.
          </p>
        </div>
        <div className="actions no-print">
          {/* A plain link: the browser downloads the file with the session cookie. */}
          <a className="button" href="/api/reports/pipeline.csv" download>Download CSV</a>
          <button type="button" onClick={() => window.print()}>Print / save as PDF</button>
        </div>
      </div>

      <ErrorBox error={error} />
      {loading && !data && <Skeleton lines={6} />}

      {data && (
        <>
          <div className="stats">
            <Stat name="Active deals" value={String(data.kpis.active_deals)} note={`${data.kpis.completed_deals} completed`} />
            <Stat name="In market" value={String(data.kpis.in_market)} note="book building or later" />
            <Stat name="Orders" value={data.kpis.orders.toLocaleString("en-GB")} note={`${data.kpis.investors_active} investors`} />
            <Stat name="Average cover" value={data.kpis.avg_cover === null ? "-" : `${data.kpis.avg_cover.toFixed(2)}x`} note="deals with a book" />
            <Stat name="Awaiting approval" value={String(data.kpis.pending_approvals)} note="allocation proposals" tone={data.kpis.pending_approvals ? "warn" : undefined} />
            <Stat name="Blocking tasks" value={String(data.kpis.blocking_tasks)} note="open in current stage" tone={data.kpis.blocking_tasks ? "warn" : undefined} />
          </div>

          <div className="grid2">
            <section className="card" aria-labelledby="r-stage">
              <h2 id="r-stage">Deals by stage</h2>
              <StageBars stages={data.stages} />
              {data.volume.length > 0 && (
                <p className="muted small volume">
                  Volume: {data.volume.map((v) => `${v.currency} ${v.size_mm.toLocaleString("en-GB")}m (${v.deals} ${v.deals === 1 ? "deal" : "deals"})`).join(" · ")}
                </p>
              )}
            </section>
            <section className="card" aria-labelledby="r-act">
              <h2 id="r-act">Activity</h2>
              <ActivityColumns days={data.activity} />
              {data.top_actions.length > 0 && (
                <p className="muted small">Most frequent: {data.top_actions.map((a) => `${a.label} (${a.count})`).join(", ")}</p>
              )}
            </section>
          </div>

          <section className="card" aria-labelledby="r-books">
            <h2 id="r-books">Deals and books</h2>
            {data.books.length === 0 ? (
              <EmptyState title="No deals yet">Create a deal on the Pipeline page and it appears here.</EmptyState>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr><th>Deal</th><th>Stage</th><th className="num">Size</th><th className="num">Orders</th><th className="num">Cover</th><th className="num">Allocated</th><th>Allocation</th><th className="num">Blocking</th></tr>
                  </thead>
                  <tbody>
                    {data.books.map((b) => (
                      <tr key={b.deal_id}>
                        <td><Link href={`/deals/${encodeURIComponent(b.deal_id)}`}>{b.name}</Link><div className="muted small">{b.issuer} · launch {fmtDate(b.launch_date)}</div></td>
                        <td>{b.stage_name}</td>
                        <td className="num">{b.currency} {b.size_mm.toLocaleString("en-GB")}m</td>
                        <td className="num">{b.orders ? `${b.orders} (${b.investors} investors)` : "-"}</td>
                        <td className="num">{b.cover === null ? "-" : <Pill tone={coverTone(b.cover)}>{b.cover.toFixed(2)}x</Pill>}</td>
                        <td className="num">{b.allocated_k ? `${(b.allocated_k / 1000).toLocaleString("en-GB", { maximumFractionDigits: 1 })}m` : "-"}</td>
                        <td><AllocationPill row={b} /></td>
                        <td className="num">{b.blockers_open || "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <div className="grid2">
            <section className="card"><BarList title="Demand by investor type" buckets={asBuckets(data.mix_by_type).map((m) => ({ ...m, label: label(m.label) }))} /></section>
            <section className="card"><BarList title="Demand by region" buckets={asBuckets(data.mix_by_region)} /></section>
          </div>
        </>
      )}
    </main>
  );
}
