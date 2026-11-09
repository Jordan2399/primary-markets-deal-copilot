"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ErrorBox, Pill } from "@/components/ui";
import { ApiError, api, streamCopilot } from "@/lib/client";
import type { DealSummary, Source } from "@/lib/types";

type Message = {
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  cited?: string[];
  intent?: string;
  model?: string;
  failed?: string;
};

const EXAMPLES = ["What is left before launch?", "Which blocking tasks are still open and who owns them?", "How does allocation and scale back work?"];

function CopilotInner() {
  const search = useSearchParams();
  const [deals, setDeals] = useState<DealSummary[]>([]);
  const [dealId, setDealId] = useState<string>(search.get("deal") ?? "");
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const abort = useRef<AbortController | null>(null);
  const bottom = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    api.deals().then((d) => {
      setDeals(d);
      setDealId((current) => current || d.find((x) => x.id === "D-DEMO-001")?.id || "");
    }).catch(setError);
  }, []);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  function patchLast(patch: (m: Message) => Message) {
    setMessages((all) => all.map((m, i) => (i === all.length - 1 ? patch(m) : m)));
  }

  async function ask(text: string) {
    const question = text.trim();
    if (!question || busy) return;
    const history = messages.filter((m) => !m.failed).slice(-4).map((m) => ({ role: m.role, content: m.content }));
    setInput("");
    setError(null);
    setBusy(true);
    setMessages((all) => [...all, { role: "user", content: question }, { role: "assistant", content: "" }]);
    abort.current = new AbortController();
    try {
      await streamCopilot({ message: question, deal_id: dealId || null, history }, (event) => {
        if (event.event === "meta") patchLast((m) => ({ ...m, sources: event.data.sources, intent: event.data.intent, model: event.data.model }));
        else if (event.event === "token") patchLast((m) => ({ ...m, content: m.content + event.data.text }));
        else if (event.event === "done") patchLast((m) => ({ ...m, cited: event.data.cited }));
        else if (event.event === "error") patchLast((m) => ({ ...m, failed: event.data.message }));
      }, abort.current.signal);
    } catch (e) {
      if (!(e instanceof DOMException && e.name === "AbortError")) {
        setError(e);
        patchLast((m) => ({ ...m, failed: e instanceof ApiError ? e.message : "The answer could not be completed." }));
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="container wide">
      <h1>Copilot</h1>
      <p className="muted">Answers come only from the deal&apos;s tasks and the playbook, with sources you can check. It assists; people decide.</p>
      <div className="row">
        <label className="inline">Deal
          <select value={dealId} onChange={(e) => setDealId(e.target.value)}>
            <option value="">(none - process questions only)</option>
            {deals.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
        </label>
      </div>
      <ErrorBox error={error} />

      <div className="chat" aria-live="polite">
        {messages.length === 0 && (
          <div className="examples">
            {EXAMPLES.map((q) => <button key={q} onClick={() => ask(q)}>{q}</button>)}
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            <div className="bubble">
              {m.content || (m.role === "assistant" && !m.failed ? <span className="muted">Thinking...</span> : null)}
              {m.failed && <div className="bad small">{m.failed}</div>}
            </div>
            {m.role === "assistant" && m.sources && m.sources.length > 0 && (
              <details className="evidence">
                <summary>
                  Evidence ({m.sources.length}){m.cited && m.cited.length > 0 ? ` - cited: ${m.cited.join(", ")}` : ""}
                  {m.model ? ` - ${m.model}` : ""}
                </summary>
                <ul>
                  {m.sources.map((s) => (
                    <li key={s.id} className={m.cited?.includes(s.id) ? "cited" : ""}>
                      <strong>[{s.id}]</strong> <Pill tone="plain">{s.type}</Pill> {s.title}
                      <div className="muted small">{s.snippet}</div>
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </div>
        ))}
        <div ref={bottom} />
      </div>

      <form className="composer" onSubmit={(e) => { e.preventDefault(); void ask(input); }}>
        <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask about the deal or the process..." maxLength={2000} aria-label="Your question" />
        {busy ? <button type="button" onClick={() => abort.current?.abort()}>Stop</button> : <button className="primary" disabled={!input.trim()}>Ask</button>}
      </form>
    </main>
  );
}

export default function CopilotPage() {
  return (
    <Suspense fallback={<main className="container"><p className="muted">Loading...</p></main>}>
      <CopilotInner />
    </Suspense>
  );
}
