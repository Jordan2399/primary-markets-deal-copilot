"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import DealSelect from "@/components/DealSelect";
import { ErrorBox, Pill, fmtTime } from "@/components/ui";
import { ApiError, api, getRole } from "@/lib/client";
import { fmtK, label } from "@/lib/format";
import { dealFromUrl } from "@/lib/session-utils";
import type { AllocationResult, Proposal, ProposalSummary } from "@/lib/types";

/** Allocation: preview the engine's result, propose it, and approve it (a different person). */
export default function AllocationPage() {
  // Start from ?deal=... in the address so other pages can link straight here.
  const [dealId, setDealId] = useState(dealFromUrl);
  const [spread, setSpread] = useState<number | null>(null);
  const [preview, setPreview] = useState<AllocationResult | null>(null);
  const [proposals, setProposals] = useState<ProposalSummary[]>([]);
  const [selected, setSelected] = useState<Proposal | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [role, setRole] = useState("viewer");

  useEffect(() => setRole(getRole()), []);
  // These flags only decide what is shown; the API refuses the call for the wrong role anyway.
  const allowed = ["syndicate", "approver", "admin"].includes(role);
  const canPropose = ["syndicate", "admin"].includes(role);
  const canApprove = ["approver", "admin"].includes(role);

  /** Load the saved proposals for a deal (skipped when no deal or the role may not see them). */
  const loadProposals = useCallback(async (id: string) => {
    if (!id || !allowed) return;
    try {
      setProposals(await api.proposals(id));
    } catch (e) {
      setError(e);
    }
  }, [allowed]);

  /** Ask the engine for an allocation at a spread (null = let it pick the final spread). */
  const loadPreview = useCallback(async (id: string, bp: number | null) => {
    if (!id || !allowed) return;
    try {
      const result = await api.preview(id, bp ?? undefined);
      setPreview(result);
      setError(null);
      // On the first load, adopt the spread the engine chose as the starting value.
      if (bp === null) setSpread(result.final_spread_bp);
    } catch (e) {
      setPreview(null);
      setError(e);
    }
  }, [allowed]);

  // Changing the deal resets the screen and reloads both the preview and the proposals.
  useEffect(() => {
    setSpread(null);
    setSelected(null);
    void loadPreview(dealId, null);
    void loadProposals(dealId);
  }, [dealId, loadPreview, loadProposals]);

  /** Save the current preview as a proposal waiting for approval. */
  async function propose() {
    setBusy(true);
    try {
      const p = await api.propose(dealId, spread);
      setSelected(p);
      setError(null);
      await loadProposals(dealId);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  async function open(id: string) {
    try {
      setSelected(await api.proposal(id));
    } catch (e) {
      setError(e);
    }
  }

  async function approve(p: Proposal) {
    setBusy(true);
    try {
      setSelected(await api.approve(p.deal_id, p.id));
      setError(null);
      await loadProposals(dealId);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  const shown = selected ?? preview;
  const balanced = shown ? shown.total_allocated_k === shown.deal_size_k : false;

  return (
    <main className="container wide">
      <h1>Allocation</h1>
      <p className="muted">The system proposes and explains; a person decides. The person who proposes cannot approve (four-eyes).</p>
      {!allowed ? (
        <div className="alert">Allocation is for the Syndicate, Approver and Administrator roles. Your account does not have access. Sign in with a different account to use this page.</div>
      ) : (
        <>
          <div className="row">
            <DealSelect value={dealId} onChange={setDealId} bookStagesOnly preferred="D-2026-009" />
            <label className="inline">Final spread (bp)
              <input type="number" min={0} max={1000} value={spread ?? ""} style={{ width: 90 }}
                onChange={(e) => { const v = Number(e.target.value); setSpread(v); setSelected(null); void loadPreview(dealId, v); }} />
            </label>
            {canPropose && <button className="primary" disabled={busy || !preview} onClick={propose}>Propose allocation</button>}
          </div>
          <ErrorBox error={error} />
          {error instanceof ApiError && error.status === 409 && error.message.toLowerCase().includes("empty") && dealId && (
            <p>
              {canPropose ? (
                <Link className="button primary" href={`/orderbook?deal=${encodeURIComponent(dealId)}`}>Go to the order book and simulate one</Link>
              ) : (
                <span className="muted">A syndicate user needs to simulate the order book first.</span>
              )}
            </p>
          )}

          {shown && (
            <>
              <section className="card">
                <div className="row between">
                  <h2>{selected ? `Proposal ${selected.id}` : "Preview (not saved)"} {selected && <Pill tone={selected.state === "APPROVED" ? "good" : selected.state === "PROPOSED" ? "warn" : "plain"}>{selected.state.toLowerCase()}</Pill>}</h2>
                  <span className={balanced ? "good" : "bad"} role="status">
                    {balanced ? "Sum check OK" : "Undersubscribed"}: {fmtK(shown.total_allocated_k)} allocated of {fmtK(shown.deal_size_k)}
                  </span>
                </div>
                <p className="small">Status: <strong>{shown.status}</strong> at {shown.final_spread_bp}bp. Eligible demand {fmtK(shown.eligible_demand_k)}.</p>
                <table>
                  <thead><tr><th>Band</th><th>Orders</th><th>Demand</th><th>Allocated</th><th>Filled</th></tr></thead>
                  <tbody>
                    {shown.bands.map((b) => (
                      <tr key={b.band}><td>{b.band}</td><td>{b.orders}</td><td>{fmtK(b.demand_k)}</td><td>{fmtK(b.allocated_k)}</td><td>{b.scale_pct}%</td></tr>
                    ))}
                  </tbody>
                </table>
              </section>

              {selected && (
                <section className="card">
                  <h2>Explanation</h2>
                  <p>{selected.explanation}</p>
                  <p className="muted small">Written by {selected.explanation_source === "template" ? "a fixed template (no model was available)" : selected.explanation_source}. The numbers come from the engine, not the model.</p>
                  <p className="small">Proposed by {selected.proposed_by} at {fmtTime(selected.proposed_at)}{selected.approved_by ? `; approved by ${selected.approved_by}` : ""}.</p>
                  {canApprove && selected.state === "PROPOSED" && (
                    <button className="primary" disabled={busy} onClick={() => approve(selected)}>Approve allocation</button>
                  )}
                </section>
              )}

              <section className="card scroll">
                <h2>Orders ({shown.lines.length})</h2>
                <table>
                  <thead><tr><th>Investor</th><th>Type</th><th>Band</th><th>Ordered</th><th>Allocated</th><th>Filled</th><th>Note</th></tr></thead>
                  <tbody>
                    {shown.lines.map((l) => (
                      <tr key={l.order_id}>
                        <td>{l.investor_name}</td><td>{label(l.investor_type)}</td><td>{l.band ?? "-"}</td>
                        <td>{fmtK(l.ordered_k)}</td><td>{fmtK(l.allocated_k)}</td><td>{l.fill_pct}%</td>
                        <td className="small">{l.note}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
            </>
          )}

          <section className="card">
            <h2>Proposals for this deal</h2>
            {proposals.length === 0 ? <p className="muted">None yet.</p> : (
              <table>
                <thead><tr><th>Id</th><th>State</th><th>Spread</th><th>Allocated</th><th>Proposed by</th><th>Approved by</th><th /></tr></thead>
                <tbody>
                  {proposals.map((p) => (
                    <tr key={p.id}>
                      <td>{p.id}</td><td>{p.state.toLowerCase()}</td><td>{p.final_spread_bp}bp</td>
                      <td>{fmtK(p.total_allocated_k)} / {fmtK(p.deal_size_k)}</td><td>{p.proposed_by}</td><td>{p.approved_by ?? "-"}</td>
                      <td><button onClick={() => open(p.id)}>Open</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        </>
      )}
    </main>
  );
}
