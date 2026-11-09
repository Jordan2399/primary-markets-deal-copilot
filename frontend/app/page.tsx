"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ErrorBox, Pill, Progress, fmtDate } from "@/components/ui";
import { api, getRole } from "@/lib/client";
import type { CreateDealInput, DealSummary, Issuer, Stage } from "@/lib/types";

function tomorrowPlus(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

export default function Pipeline() {
  const [stages, setStages] = useState<Stage[]>([]);
  const [deals, setDeals] = useState<DealSummary[]>([]);
  const [issuers, setIssuers] = useState<Issuer[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const canCreate = typeof window !== "undefined" && ["marketer", "admin"].includes(getRole());

  const load = useCallback(async () => {
    try {
      const [s, d, i] = await Promise.all([api.stages(), api.deals(), api.issuers()]);
      setStages(s);
      setDeals(d);
      setIssuers(i);
      setError(null);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <main className="container wide">
      <div className="row between">
        <div>
          <h1>Deal pipeline</h1>
          <p className="muted">New-issue deals by stage, from mandate to booking. All data is synthetic.</p>
        </div>
        {canCreate && (
          <button className="primary" onClick={() => setShowForm((v) => !v)}>
            {showForm ? "Close" : "New deal"}
          </button>
        )}
      </div>
      <ErrorBox error={error} />
      {showForm && <NewDealForm issuers={issuers} onCreated={() => { setShowForm(false); void load(); }} />}
      {loading ? (
        <p className="muted">Loading...</p>
      ) : (
        <div className="board">
          {stages.map((stage) => {
            const inStage = deals.filter((d) => d.stage_code === stage.code);
            return (
              <section key={stage.code} className="column" aria-label={stage.name}>
                <h2>
                  {stage.name} <span className="muted">({inStage.length})</span>
                </h2>
                {inStage.length === 0 && <p className="muted small">No deals</p>}
                {inStage.map((deal) => (
                  <Link key={deal.id} href={`/deals/${deal.id}`} className="deal">
                    <strong>{deal.issuer_name}</strong>
                    <span className="small">
                      {deal.currency} {deal.size_mm}m
                    </span>
                    <span className="muted small">Launch {fmtDate(deal.launch_date)}</span>
                    <Progress done={deal.tasks_done} total={deal.tasks_total} />
                    <span className="small">
                      {deal.blockers_open > 0 ? (
                        <Pill tone="warn">{deal.blockers_open} blocking</Pill>
                      ) : (
                        <Pill tone="good">stage clear</Pill>
                      )}
                    </span>
                  </Link>
                ))}
              </section>
            );
          })}
        </div>
      )}
    </main>
  );
}

function NewDealForm({ issuers, onCreated }: { issuers: Issuer[]; onCreated: () => void }) {
  const [form, setForm] = useState<CreateDealInput>({
    issuer_id: "",
    name: "",
    currency: "EUR",
    size_mm: 500,
    tenor_years: 5,
    format: "Reg S",
    launch_date: tomorrowPlus(21),
  });
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const set = <K extends keyof CreateDealInput>(key: K, value: CreateDealInput[K]) => setForm((f) => ({ ...f, [key]: value }));

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      await api.createDeal(form);
      onCreated();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card form" onSubmit={submit}>
      <h2>New deal</h2>
      <ErrorBox error={error} />
      <label>Issuer
        <select required value={form.issuer_id} onChange={(e) => set("issuer_id", e.target.value)}>
          <option value="">Select...</option>
          {issuers.map((i) => <option key={i.id} value={i.id}>{i.name} ({i.rating_band})</option>)}
        </select>
      </label>
      <label>Deal name
        <input required minLength={3} value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="Issuer EUR 500m 5Y" />
      </label>
      <div className="grid4">
        <label>Currency
          <select value={form.currency} onChange={(e) => set("currency", e.target.value as CreateDealInput["currency"])}>
            {["EUR", "USD", "GBP", "CHF"].map((c) => <option key={c}>{c}</option>)}
          </select>
        </label>
        <label>Size (millions)
          <input type="number" min={50} max={5000} value={form.size_mm} onChange={(e) => set("size_mm", Number(e.target.value))} />
        </label>
        <label>Tenor (years)
          <input type="number" min={1} max={40} value={form.tenor_years} onChange={(e) => set("tenor_years", Number(e.target.value))} />
        </label>
        <label>Format
          <select value={form.format} onChange={(e) => set("format", e.target.value as CreateDealInput["format"])}>
            {["Reg S", "144A", "Domestic"].map((f) => <option key={f}>{f}</option>)}
          </select>
        </label>
      </div>
      <label>Target launch date
        <input type="date" required value={form.launch_date} onChange={(e) => set("launch_date", e.target.value)} />
      </label>
      <button className="primary" disabled={busy}>{busy ? "Creating..." : "Create deal"}</button>
    </form>
  );
}
