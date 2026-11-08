"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useMemo, useState } from "react";
import { ErrorBox, Pill, Progress, fmtDate, fmtTime } from "@/components/ui";
import { ApiError, api, getRole } from "@/lib/client";
import type { AuditEvent, DealDetail, Task, TaskStatus } from "@/lib/types";

type Blocker = { key: string; title: string; owner_role: string };

export default function DealWorkspace({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [deal, setDeal] = useState<DealDetail | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [timeline, setTimeline] = useState<AuditEvent[]>([]);
  const [tab, setTab] = useState<"tasks" | "timeline">("tasks");
  const [error, setError] = useState<unknown>(null);
  const [blockers, setBlockers] = useState<Blocker[]>([]);
  const canEdit = typeof window !== "undefined" && ["marketer", "syndicate", "admin"].includes(getRole());

  const load = useCallback(async () => {
    try {
      const [d, t, e] = await Promise.all([api.deal(id), api.tasks(id), api.timeline(id)]);
      setDeal(d);
      setTasks(t);
      setTimeline(e);
    } catch (err) {
      setError(err);
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  const byStage = useMemo(() => {
    const groups = new Map<string, { name: string; position: number; tasks: Task[] }>();
    for (const task of tasks) {
      const g = groups.get(task.stage_code) ?? { name: task.stage_name, position: task.stage_position, tasks: [] };
      g.tasks.push(task);
      groups.set(task.stage_code, g);
    }
    return [...groups.entries()].sort((a, b) => a[1].position - b[1].position);
  }, [tasks]);

  async function changeStatus(task: Task, status: TaskStatus) {
    setError(null);
    try {
      await api.updateTask(task.id, status);
      await load();
    } catch (err) {
      setError(err);
    }
  }

  async function advance() {
    setError(null);
    setBlockers([]);
    try {
      await api.advance(id);
      await load();
    } catch (err) {
      if (err instanceof ApiError && Array.isArray(err.details.blockers)) setBlockers(err.details.blockers as Blocker[]);
      setError(err);
    }
  }

  if (!deal) {
    return (
      <main className="container">
        <ErrorBox error={error} />
        {!error && <p className="muted">Loading...</p>}
        <Link href="/">Back to pipeline</Link>
      </main>
    );
  }

  return (
    <main className="container wide">
      <Link href="/" className="small">&larr; Pipeline</Link>
      <div className="row between">
        <div>
          <h1>{deal.name}</h1>
          <p className="muted">
            {deal.issuer_name} &middot; {deal.currency} {deal.size_mm}m &middot; launch {fmtDate(deal.launch_date)} &middot; <strong>{deal.stage_name}</strong>
          </p>
        </div>
        <div className="row">
          <Link className="button" href={`/copilot?deal=${deal.id}`}>Ask the Copilot</Link>
          {canEdit && !deal.is_complete && <button className="primary" onClick={advance}>Advance stage</button>}
        </div>
      </div>

      <ErrorBox error={error} />
      {blockers.length > 0 && (
        <div className="alert" role="alert">
          <strong>These blocking tasks must be done first:</strong>
          <ul>{blockers.map((b) => <li key={b.key}>{b.title} <span className="muted">({b.owner_role})</span></li>)}</ul>
        </div>
      )}

      <section className="card">
        <Progress done={deal.tasks_done} total={deal.tasks_total} />
        <p className="small muted">{deal.tasks_done} of {deal.tasks_total} tasks done &middot; {deal.blockers_open} blocking in this stage</p>
        {deal.tranches.map((t) => (
          <p key={t.id} className="small">
            Tranche: {t.tenor_years}Y {t.format}
            {t.maturity ? <> &middot; matures {fmtDate(t.maturity)}</> : null}
            {t.coupon != null ? <> &middot; coupon {t.coupon.toFixed(3)}%</> : null}
            {t.isin ? <> &middot; {t.isin}</> : null}
          </p>
        ))}
      </section>

      <div className="tabs" role="tablist">
        <button role="tab" aria-selected={tab === "tasks"} onClick={() => setTab("tasks")}>Checklist</button>
        <button role="tab" aria-selected={tab === "timeline"} onClick={() => setTab("timeline")}>Timeline ({timeline.length})</button>
      </div>

      {tab === "tasks" &&
        byStage.map(([code, group]) => (
          <section key={code} className={`card${code === deal.stage_code ? " current" : ""}`}>
            <h2>{group.name} {code === deal.stage_code && <Pill tone="plain">current</Pill>}</h2>
            <table>
              <thead><tr><th>Task</th><th>Owner</th><th>Due</th><th>Status</th></tr></thead>
              <tbody>
                {group.tasks.map((task) => (
                  <tr key={task.id}>
                    <td>{task.title} {task.blocking && <Pill tone="warn">blocking</Pill>}</td>
                    <td>{task.owner_role}</td>
                    <td>{fmtDate(task.due)}</td>
                    <td>
                      <select
                        aria-label={`Status of ${task.title}`}
                        value={task.status}
                        disabled={!canEdit}
                        onChange={(e) => changeStatus(task, e.target.value as TaskStatus)}
                      >
                        <option value="TODO">To do</option>
                        <option value="IN_PROGRESS">In progress</option>
                        <option value="DONE">Done</option>
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        ))}

      {tab === "timeline" && (
        <section className="card">
          {timeline.length === 0 && <p className="muted">No events yet.</p>}
          <ul className="timeline">
            {timeline.map((e) => (
              <li key={e.id}>
                <strong>{e.action}</strong> by {e.actor} ({e.role})
                <div className="muted small">{fmtTime(e.ts)}</div>
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
