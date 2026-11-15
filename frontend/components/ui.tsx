"use client";

import { ApiError } from "@/lib/client";
import type { ReactNode } from "react";

export function ErrorBox({ error }: { error: unknown }) {
  if (!error) return null;
  const e = error instanceof ApiError ? error : null;
  return (
    <div className="alert" role="alert">
      <strong>{e ? e.message : "Something went wrong."}</strong>
      {e?.requestId ? <div className="muted small">Request id: {e.requestId}</div> : null}
    </div>
  );
}

export function Progress({ done, total }: { done: number; total: number }) {
  const pct = total ? Math.round((done / total) * 100) : 0;
  return (
    <div className="progress" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label="Tasks done">
      <div style={{ width: `${pct}%` }} />
    </div>
  );
}

export function Pill({ tone, children }: { tone: "good" | "warn" | "bad" | "plain"; children: ReactNode }) {
  return <span className={`pill ${tone}`}>{children}</span>;
}

export function fmtDate(value: string | null): string {
  if (!value) return "-";
  return new Date(`${value}T00:00:00`).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
}

export function fmtTime(value: string): string {
  return new Date(value).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" });
}

/** One small labelled figure with an optional note underneath (used in the KPI rows). */
export function Stat({ name, value, note, tone }: { name: string; value: string; note?: string; tone?: "warn" }) {
  return (
    <div className="stat">
      <div className="muted small">{name}</div>
      <div className={`stat-value${tone === "warn" ? " warn" : ""}`}>{value}</div>
      {note ? <div className="muted small">{note}</div> : null}
    </div>
  );
}

/** A friendly "nothing here yet" box that says what to do next. */
export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <strong>{title}</strong>
      {children ? <p className="muted small">{children}</p> : null}
    </div>
  );
}
