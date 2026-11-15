"use client";

import Link from "next/link";
import { Pill, fmtDate, fmtTime } from "@/components/ui";
import type { DealTabId } from "@/lib/deal-tabs";
import { daysUntil } from "@/lib/deal-tabs";
import type { AuditEvent, DealDetail, Task } from "@/lib/types";

/** The landing tab: key terms, what blocks the deal right now, and the latest activity. */
export default function OverviewTab({
  deal,
  tasks,
  timeline,
  onOpenTab,
}: {
  deal: DealDetail;
  tasks: Task[];
  timeline: AuditEvent[];
  onOpenTab: (tab: DealTabId) => void;
}) {
  // What stops the deal from moving on: blocking tasks of the current stage that are not done.
  const blockers = tasks.filter((t) => t.stage_code === deal.stage_code && t.blocking && t.status !== "DONE");
  // The next few things to do in this stage, soonest due date first.
  const upcoming = tasks
    .filter((t) => t.stage_code === deal.stage_code && t.status !== "DONE")
    .sort((a, b) => (a.due ?? "9999").localeCompare(b.due ?? "9999"))
    .slice(0, 5);
  const days = daysUntil(deal.launch_date);

  return (
    <div className="grid2">
      <section className="card">
        <h2>Key terms</h2>
        <dl className="kv">
          <dt>Issuer</dt><dd>{deal.issuer_name}</dd>
          <dt>Size</dt><dd>{deal.currency} {deal.size_mm}m</dd>
          <dt>Launch</dt>
          <dd>
            {fmtDate(deal.launch_date)}
            {days !== null && !deal.is_complete && (
              <span className="muted small"> ({days > 0 ? `in ${days} days` : days === 0 ? "today" : `${-days} days ago`})</span>
            )}
          </dd>
          <dt>Stage</dt><dd>{deal.stage_name}</dd>
        </dl>
        {deal.tranches.map((t) => (
          <dl key={t.id} className="kv" style={{ marginTop: 14 }}>
            <dt>Tranche</dt><dd>{t.tenor_years}Y {t.format}</dd>
            {t.maturity && (<><dt>Maturity</dt><dd>{fmtDate(t.maturity)}</dd></>)}
            {t.coupon != null && (<><dt>Coupon</dt><dd>{t.coupon.toFixed(3)}%</dd></>)}
            {t.isin && (<><dt>ISIN</dt><dd>{t.isin}</dd></>)}
          </dl>
        ))}
      </section>

      <section className="card">
        <h2>Next up in {deal.stage_name}</h2>
        {blockers.length > 0 && (
          <div className="alert warn" role="status" style={{ marginTop: 0 }}>
            <strong>{blockers.length} blocking {blockers.length === 1 ? "task" : "tasks"} before this deal can advance:</strong>
            <ul>{blockers.map((b) => <li key={b.id}>{b.title} <span className="muted">({b.owner_role})</span></li>)}</ul>
          </div>
        )}
        {upcoming.length === 0 ? (
          <p className="muted">Nothing left in this stage. {deal.is_complete ? "The deal is complete." : "It is ready to advance."}</p>
        ) : (
          <ul className="todo">
            {upcoming.map((t) => (
              <li key={t.id}>
                <span>{t.title}</span>
                {t.blocking && <Pill tone="warn">blocking</Pill>}
                <span className="muted small">{t.owner_role} &middot; due {fmtDate(t.due)}</span>
              </li>
            ))}
          </ul>
        )}
        <button type="button" className="small-btn" style={{ marginTop: 12 }} onClick={() => onOpenTab("checklist")}>Open the checklist</button>
      </section>

      <section className="card">
        <h2>Recent activity</h2>
        {timeline.length === 0 ? (
          <p className="muted">No activity yet.</p>
        ) : (
          <ul className="timeline">
            {timeline.slice(0, 5).map((e) => (
              <li key={e.id}>
                <strong>{e.action}</strong> by {e.actor} <span className="muted">({e.role})</span>
                <div className="muted small">{fmtTime(e.ts)}</div>
              </li>
            ))}
          </ul>
        )}
        <button type="button" className="small-btn" onClick={() => onOpenTab("timeline")}>Full timeline</button>
      </section>

      <section className="card">
        <h2>Go further</h2>
        <ul className="todo">
          <li><Link href={`/copilot?deal=${deal.id}`}>Ask the Copilot about this deal</Link></li>
          <li><button type="button" className="link" onClick={() => onOpenTab("investors")}>Investor network and target list</button></li>
          <li><button type="button" className="link" onClick={() => onOpenTab("documents")}>Term sheets for this deal</button></li>
        </ul>
      </section>
    </div>
  );
}
