"use client";

import { useRef, useState } from "react";
import DealSelect from "@/components/DealSelect";
import { ErrorBox, Pill } from "@/components/ui";
import { api } from "@/lib/client";
import { label } from "@/lib/format";
import type { DiffRow, Extraction, ValidationReport } from "@/lib/types";

const FIELD_NAMES: Record<string, string> = {
  issuer: "Issuer", isin: "ISIN", currency: "Currency", size_mm: "Size (millions)",
  coupon_pct: "Coupon (%)", maturity: "Maturity", format: "Format",
  issue_date: "Issue date", listing: "Listing", governing_law: "Governing law",
};

// The order of the "Extracted deal" card: the six required fields first, then the extras.
const RECORD_FIELDS = [
  "issuer", "isin", "currency", "size_mm", "coupon_pct", "issue_date", "maturity",
  "format", "listing", "governing_law",
] as const;

function statusText(status: DiffRow["status"]): { text: string; tone: "good" | "bad" | "warn" } {
  if (status === "match") return { text: "match", tone: "good" };
  if (status === "mismatch") return { text: "MISMATCH", tone: "bad" };
  return { text: label(status), tone: "warn" };
}

/** The two ways to give the lab a document. Only one is active at a time. */
type Mode = "text" | "file";

export default function TermSheetLab() {
  // One input at a time: switching the mode throws away the other input, so what is sent is
  // always exactly what the page shows.
  const [mode, setMode] = useState<Mode>("text");
  const fileInput = useRef<HTMLInputElement | null>(null);
  // No deal is preselected: a fixed id would break on any database that does not contain it.
  const [dealId, setDealId] = useState("");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [extraction, setExtraction] = useState<Extraction | null>(null);
  const [report, setReport] = useState<ValidationReport | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  /** Change the input mode and clear the input of the mode being left. */
  function switchMode(next: Mode) {
    setMode(next);
    if (next === "text") chooseFile(null);
    else setText("");
    setExtraction(null);
    setReport(null);
    setError(null);
  }

  /** Set (or clear) the chosen file and keep the native file input in step with it. */
  function chooseFile(next: File | null) {
    setFile(next);
    if (!next && fileInput.current) fileInput.current.value = "";
  }

  async function loadSample(variant: "good" | "bad") {
    if (!dealId) return;
    try {
      const sample = await api.sample(dealId, variant);
      setMode("text"); // samples are text
      setText(sample.text);
      chooseFile(null);
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
      // Exactly one source goes to the API, chosen by the mode.
      const out = await api.extract({
        file: mode === "file" ? file : null,
        text: mode === "text" ? text : undefined,
        dealId: dealId || undefined,
      });
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
        {/* Two modes, one visible at a time: a segmented switch, not two inputs side by side. */}
        <div className="segmented" role="tablist" aria-label="Document source">
          <button role="tab" aria-selected={mode === "text"} className={mode === "text" ? "on" : ""} onClick={() => switchMode("text")}>Paste text</button>
          <button role="tab" aria-selected={mode === "file"} className={mode === "file" ? "on" : ""} onClick={() => switchMode("file")}>Upload file</button>
        </div>
        {mode === "text" ? (
          <label className="block">Term sheet text
            <textarea rows={12} value={text} onChange={(e) => setText(e.target.value)} placeholder="Paste a term sheet here, or load a sample above." />
          </label>
        ) : (
          <div className="dropzone">
            <p className="muted small">.txt, .md or .pdf, up to 2 MB and 40 pages. Long PDFs are cleaned (headers, footers, page numbers) and only the passages with the terms are read by the model.</p>
            <input ref={fileInput} type="file" accept=".txt,.md,.pdf" onChange={(e) => chooseFile(e.target.files?.[0] ?? null)} />
            {file && (
              <p className="small">
                <strong>{file.name}</strong> ({Math.round(file.size / 1024)} KB){" "}
                <button className="link" onClick={() => chooseFile(null)}>remove</button>
              </p>
            )}
          </div>
        )}
        <div className="row">
          <button className="primary" disabled={busy || (mode === "text" ? !text.trim() : !file)} onClick={run}>{busy ? "Working..." : "Extract and validate"}</button>
          <span className="muted small">Will read: {mode === "text" ? "the pasted text" : file ? "the uploaded file" : "nothing yet"}</span>
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
              Read from {extraction.source === "file" ? "the uploaded file" : "the pasted text"} by{" "}
              {extraction.model_skipped
                ? "fixed rules, which found every required field, so the model was not needed"
                : extraction.model
                  ? `${extraction.model} (${extraction.method})`
                  : "fixed rules"}
              ; document {extraction.document_id}.
              {extraction.model && extraction.focused && ` The model read ${extraction.model_chars.toLocaleString()} of ${extraction.text_chars.toLocaleString()} characters.`}
              {extraction.filled_by_model.length > 0 && ` Filled by the model: ${extraction.filled_by_model.map((f) => FIELD_NAMES[f] ?? f).join(", ")}.`}
            </p>
            {extraction.model_error && (
              <div className="alert warn" role="alert">
                The model did not answer, so fixed rules read the document ({extraction.model_error}). Check that Ollama is running and
                see the Status page.
              </div>
            )}
            {extraction.not_found.length > 0 && (
              <div className="alert warn" role="alert">
                Not found in this document: {extraction.not_found.map((f) => FIELD_NAMES[f] ?? f).join(", ")}.
                {extraction.source === "file" && " For a long PDF, copy the page with the terms into the text box and try again."}
              </div>
            )}
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
            <h2>Extracted deal</h2>
            <p className="muted small">What was read from the document, before any comparison with a booking.</p>
            <table>
              <thead><tr><th>Field</th><th>Value</th><th>Read by</th></tr></thead>
              <tbody>
                {RECORD_FIELDS.map((field) => {
                  const value = extraction.record[field];
                  // A field only the model filled is marked; everything else came from the rules
                  // or, in "always" mode, from the model with the rules as back-up.
                  const readBy = value === null ? "" : extraction.filled_by_model.includes(field)
                    ? "model" : extraction.model && !extraction.model_skipped ? extraction.model : "fixed rules";
                  return (
                    <tr key={field} className={value === null ? "row-bad" : ""}>
                      <td>{FIELD_NAMES[field]}</td>
                      <td>{value === null ? "not found" : String(value)}</td>
                      <td className="muted small">{readBy}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
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
