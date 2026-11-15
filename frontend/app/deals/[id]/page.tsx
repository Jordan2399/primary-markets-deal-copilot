"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useMemo, useState } from "react";
import AllocationTab from "@/components/deal/AllocationTab";
import DocumentsTab from "@/components/deal/DocumentsTab";
import InvestorsTab from "@/components/deal/InvestorsTab";
import OrderBookTab from "@/components/deal/OrderBookTab";
import OverviewTab from "@/components/deal/OverviewTab";
import ConfirmDialog from "@/components/ConfirmDialog";
import { CardSkeleton, Skeleton } from "@/components/Skeleton";
import StageStepper from "@/components/StageStepper";
import Tabs from "@/components/Tabs";
import { useToast } from "@/components/Toast";
import { ErrorBox, Pill, Progress, Stat, fmtDate, fmtTime } from "@/components/ui";
import { ApiError, api } from "@/lib/client";
import { DEAL_TABS, daysUntil, parseTab, withTab, type DealTabId } from "@/lib/deal-tabs";
import { fmtK } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { AuditEvent, DealDetail, Stage, Task, TaskStatus } from "@/lib/types";

type Blocker = { key: string; title: string; owner_role: string };

/**
 * The deal workspace: one page per deal with everything about it in tabs.
 * The open tab is kept in the address (?tab=orderbook), so a link or a refresh lands in the same place.
 */
export default function DealWorkspace({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { user } = useSession();
  const { notify } = useToast();
  const [deal, setDeal] = useState<DealDetail | null>(null);
  const [stages, setStages] = useState<Stage[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [timeline, setTimeline] = useState<AuditEvent[]>([]);
  const [tab, setTab] = useState<DealTabId>("overview");
  const [error, setError] = useState<unknown>(null);
  const [blockers, setBlockers] = useState<Blocker[]>([]);
  const [confirming, setConfirming] = useState(false);
  const [advancing, setAdvancing] = useState(false);
  // UX only: hides buttons the role cannot use. The API enforces the real rules.
  const canEdit = ["marketer", "syndicate", "admin"].includes(user.role);

  /** Fetch the deal, its tasks and its timeline together. */
  const load = useCallback(async () => {
    try {
      const [d, t, e] = await Promise.all([api.deal(id), api.tasks(id), api.timeline(id)]);
      setDeal(d);
      setTasks(t);
      setTimeline(e);
      setError(null);
    } catch (err) {
      setError(err);
    }
  }, [id]);

  useEffect(() => {
    void load();
    api.stages().then(setStages).catch(() => undefined); // the stepper is a nice-to-have
  }, [load]);

  // Read the tab from the address once the page is in the browser, and follow back/forward.
  useEffect(() => {
    const read = () => setTab(parseTab(window.location.search));
    read();
    window.addEventListener("popstate", read);
    return () => window.removeEventListener("popstate", read);
  }, []);

  /** Switch tab and write it into the address without adding a history entry for every click. */
  function openTab(next: DealTabId) {
    setTab(next);
    window.history.replaceState(null, "", `${window.location.pathname}${withTab(window.location.search, next)}`);
  }

  // Tasks grouped by stage in process order, for the checklist tab.
  const byStage = useMemo(() => {
    const groups = new Map<string, { name: string; position: number; tasks: Task[] }>();
    for (const task of tasks) {
      const g = groups.get(task.stage_code) ?? { name: task.stage_name, position: task.stage_position, tasks: [] };
      g.tasks.push(task);
      groups.set(task.stage_code, g);
    }
    return [...groups.entries()].sort((a, b) => a[1].position - b[1].position);
  }, [tasks]);

  /** Change a task's status. The row updates at once; if the API refuses, it is put back. */
  async function changeStatus(task: Task, status: TaskStatus) {
    setError(null);
    const before = tasks;
    setTasks((all) => all.map((t) => (t.id === task.id ? { ...t, status } : t))); // optimistic
    try {
      await api.updateTask(task.id, status);
      notify(`"${task.title}" is now ${status === "DONE" ? "done" : status === "IN_PROGRESS" ? "in progress" : "to do"}`, "good");
      await load(); // refresh the counts and blockers shown elsewhere on the page
    } catch (err) {
      setTasks(before);
      setError(err);
      notify("The task could not be updated", "bad");
    }
  }

  // Open blocking tasks in the current stage: the same rule the API applies when advancing.
  const openBlockers = useMemo(
    () => (deal ? tasks.filter((t) => t.stage_code === deal.stage_code && t.blocking && t.status !== "DONE") : []),
    [tasks, deal],
  );
  const nextStage = deal ? stages.find((s) => s.position === deal.stage_position + 1) : undefined;

  /** Move the deal to the next stage (called from the confirmation box). */
  async function advance() {
    setError(null);
    setBlockers([]);
    setAdvancing(true);
    try {
      await api.advance(id);
      setConfirming(false);
      notify(`Moved to ${nextStage?.name ?? "the next stage"}`, "good");
      await load();
    } catch (err) {
      setConfirming(false);
      if (err instanceof ApiError && Array.isArray(err.details.blockers)) setBlockers(err.details.blockers as Blocker[]);
      setError(err);
    } finally {
      setAdvancing(false);
    }
  }

  if (!deal) {
    return (
      <main className="container wide">
        <ErrorBox error={error} />
        {!error && (
          <>
            <Skeleton lines={2} height={22} />
            <CardSkeleton lines={4} label="Loading the deal" />
          </>
        )}
        <Link href="/">Back to pipeline</Link>
      </main>
    );
  }

  const days = daysUntil(deal.launch_date);
  return (
    <main className="container wide">
      <nav className="crumbs" aria-label="Breadcrumb">
        <Link href="/">Pipeline</Link> <span aria-hidden="true">/</span> <span aria-current="page">{deal.name}</span>
      </nav>
      <div className="row between">
        <div>
          <h1>{deal.name}</h1>
          <p className="muted">
            {deal.issuer_name} &middot; {deal.currency} {deal.size_mm}m &middot; launch {fmtDate(deal.launch_date)} &middot; <strong>{deal.stage_name}</strong>
          </p>
        </div>
        <div className="row">
          <Link className="button" href={`/copilot?deal=${deal.id}`}>Ask the Copilot</Link>
          {canEdit && !deal.is_complete && (
            <button
              className="primary"
              onClick={() => setConfirming(true)}
              title={openBlockers.length > 0 ? `${openBlockers.length} blocking task(s) must be done first` : undefined}
            >
              Advance stage
            </button>
          )}
        </div>
      </div>

      <StageStepper stages={stages} currentPosition={deal.stage_position} complete={deal.is_complete} />

      <ErrorBox error={error} />
      {blockers.length > 0 && (
        <div className="alert" role="alert">
          <strong>These blocking tasks must be done first:</strong>
          <ul>{blockers.map((b) => <li key={b.key}>{b.title} <span className="muted">({b.owner_role})</span></li>)}</ul>
        </div>
      )}

      {/* The strip of key figures stays visible whichever tab is open. */}
      <section className="stats" aria-label="Deal summary">
        <Stat name="Size" value={`${deal.currency} ${fmtK(deal.size_mm * 1000)}`} note={deal.tranches[0] ? `${deal.tranches[0].tenor_years}Y ${deal.tranches[0].format}` : undefined} />
        <Stat name="Tasks" value={`${deal.tasks_done}/${deal.tasks_total}`} note="done" />
        <Stat name="Blocking" value={String(deal.blockers_open)} note="in this stage" tone={deal.blockers_open > 0 ? "warn" : undefined} />
        <Stat name="Launch" value={days === null ? "-" : days > 0 ? `${days}d` : days === 0 ? "today" : "passed"} note={deal.launch_date ? fmtDate(deal.launch_date) : undefined} />
      </section>
      <Progress done={deal.tasks_done} total={deal.tasks_total} />

      <Tabs tabs={DEAL_TABS.map((t) => (t.id === "timeline" ? { ...t, count: timeline.length } : t))} value={tab} onChange={openTab} ariaLabel="Deal sections" />

      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`} style={{ marginTop: 16 }}>
        {tab === "overview" && <OverviewTab deal={deal} tasks={tasks} timeline={timeline} onOpenTab={openTab} />}

        {tab === "checklist" &&
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
                          title={canEdit ? undefined : "Your role cannot change tasks"}
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

        {tab === "orderbook" && <OrderBookTab dealId={id} />}
        {tab === "allocation" && <AllocationTab dealId={id} />}
        {tab === "documents" && <DocumentsTab dealId={id} />}
        {tab === "investors" && <InvestorsTab dealId={id} />}

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
      </div>

      {/* Advancing is hard to undo, so it asks first and shows what still blocks it. */}
      <ConfirmDialog
        open={confirming}
        title={nextStage ? `Move to ${nextStage.name}?` : "Advance this deal?"}
        confirmLabel="Advance"
        confirmDisabled={openBlockers.length > 0}
        busy={advancing}
        onConfirm={advance}
        onCancel={() => setConfirming(false)}
      >
        {openBlockers.length > 0 ? (
          <>
            <p>These blocking tasks are not done yet:</p>
            <ul>{openBlockers.map((b) => <li key={b.id}>{b.title} <span className="muted">({b.owner_role})</span></li>)}</ul>
          </>
        ) : (
          <p>
            {deal.name} moves from <strong>{deal.stage_name}</strong>
            {nextStage ? <> to <strong>{nextStage.name}</strong></> : null}. The step is recorded in the audit trail.
          </p>
        )}
      </ConfirmDialog>
    </main>
  );
}
