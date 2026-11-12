"use client";

import { useState } from "react";
import DealSelect from "@/components/DealSelect";
import { ErrorBox, Pill } from "@/components/ui";
import { api } from "@/lib/client";
import { label } from "@/lib/format";
import type { DiffRow, Extraction, ValidationReport } from "@/lib/types";

const FIELD_NAMES: Record<string, string> = {
  issuer: "Issuer", isin: "ISIN", currency: "Currency", size_mm: "Size (millions)",
  coupon_pct: "Coupon (%)", maturity: "Maturity", format: "Format",
};

function statusText(status: DiffRow["status"]): { text: string; tone: "good" | "bad" | "warn" } {
  if (status === "match") return { text: "match", tone: "good" };
  if (status === "mismatch") return { text: "MISMATCH", tone: "bad" };
  return { text: label(status), tone: "warn" };
}

export default function TermSheetLab() {
  const [dealId, setDealId] = useState("D-2026-008");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [extraction, setExtraction] = useState<Extraction | null>(null);
  const [report, setReport] = useState<ValidationReport | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function loadSample(variant: "good" | "bad") {
    if (!dealId) return;
    try {
      const sample = await api.sample(dealId, variant);
      setText(sample.text);
      setFile(null);
      setExtraction(null);
      setReport(null);
      setError(null);
    } catch (e) {
      setError(e);
    }
  }

  async function run() {
    setBusy(true);
    setError(null);
    setReport(null);
    try {
      const out = await api.extract({ file, text: file ? undefined : text, dealId: dealId || undefined });
      setExtraction(out);
      setReport(await api.validate(out.document_id, dealId || undefined));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  const failedChecks = report?.checks.filter((c) => !c.ok) ?? [];
  return (
    <main className="container wide">
      <h1>Term sheet lab</h1>
      <p className="muted">Extract a typed record from a term sheet, validate it in code, and compare it with the booking record. The model reads; code decides.</p>

      <section className="card">
        <div className="row">
          <DealSelect value={dealId} onChange={setDealId} allowNone />
          <button disabled={!dealId} onClick={() => loadSample("good")}>Load sample (matches booking)</button>
          <button disabled={!dealId} onClick={() => loadSample("bad")}>Load sample (with errors)</button>
        </div>
        <label className="block">Term sheet text
          <textarea rows={12} value={text} onChange={(e) => { setText(e.target.value); setFile(null); }} placeholder="Paste a term sheet here, or load a sample, or upload a file below." />
        </label>
        <div className="row">
          <label className="inline">or upload (.txt, .md, .pdf, max 2 MB)
            <input type="file" accept=".txt,.md,.pdf" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </label>
          <button className="primary" disabled={busy || (!text.trim() && !file)} onClick={run}>{busy ? "Working..." : "Extract and validate"}</button>
        </div>
      </section>
      <ErrorBox error={error} />

      {extraction && report && (
        <>
          <section className="card">
            <div className="row between">
              <h2>Result for {extraction.filename}</h2>
              <span role="status">
                {report.has_errors || report.has_mismatch
                  ? <Pill tone="bad">problems found</Pill>
                  : <Pill tone="good">all checks passed</Pill>}
              </span>
            </div>
            <p className="muted small">
              Read by {extraction.method === "rules" ? "fixed rules (no model available)" : `${extraction.model} (${extraction.method})`}; document {extraction.document_id}.
            </p>
            {report.diff ? (
              <table>
                <thead><tr><th>Field</th><th>Term sheet</th><th>Booking record</th><th>Result</th></tr></thead>
                <tbody>
                  {report.diff.map((row) => {
                    const s = statusText(row.status);
                    return (
                      <tr key={row.field} className={row.status === "mismatch" ? "row-bad" : ""}>
                        <td>{FIELD_NAMES[row.field] ?? row.field}</td>
                        <td>{row.term_sheet ?? "-"}</td>
                        <td>{row.booking ?? "-"}</td>
                        <td><Pill tone={s.tone}>{s.text}</Pill></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            ) : (
              <p className="muted">No deal selected, so there is no booking record to compare with.</p>
            )}
          </section>

          <section className="card">
            <h2>Validation checks ({failedChecks.length} failed of {report.checks.length})</h2>
            <ul className="checks">
              {report.checks.map((c, i) => (
                <li key={i} className={c.ok ? "" : c.severity === "error" ? "check-bad" : "check-warn"}>
                  <strong>{c.ok ? "PASS" : c.severity === "error" ? "FAIL" : "WARN"}</strong> {label(c.field)} / {label(c.rule)}: {c.message}
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </main>
  );
}
