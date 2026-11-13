"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ErrorBox, Pill } from "@/components/ui";
import { ApiError, api, streamCopilot } from "@/lib/client";
import { relativeTime, splitCitations } from "@/lib/citations";
import type { ConversationSummary, DealSummary, Source, StoredMessage } from "@/lib/types";

/** One chat bubble as the page holds it (live, or rebuilt from a saved thread). */
type Message = {
  role: "user" | "assistant";
  content: string;
  sources?: Source[]; // the evidence the answer was built from
  cited?: string[]; // which source labels (S1, S2...) the answer actually cites
  intent?: string | null;
  model?: string;
  understood?: string | null; // the rewritten follow-up, shown as "Understood as ..."
  failed?: string; // set when this answer could not be completed
};

// Starter questions shown on an empty conversation; clicking one asks it.
const EXAMPLES = [
  { q: "What is left before launch?", hint: "Open tasks by stage, owner and due date" },
  { q: "Which blocking tasks are still open and who owns them?", hint: "What stops the deal moving on" },
  { q: "How does allocation and scale back work?", hint: "From the playbook, with sources" },
];

// Suggested next questions, keyed by what the last answer was about (its intent).
const FOLLOW_UPS: Record<string, string[]> = {
  deal: ["Who owns those tasks?", "Which of them are blocking?", "What are the due dates?"],
  both: ["Who owns those tasks?", "Why is that rule in place?"],
  process: ["Can you give an example?", "Who is responsible for that step?"],
};

/** Convert a message loaded from the server into the shape the page renders. */
function fromStored(m: StoredMessage): Message {
  return { role: m.role, content: m.content, sources: m.sources, cited: m.cited, intent: m.intent };
}

/** Render an answer, turning [S2]-style markers into small superscript citations with a tooltip. */
function Answer({ text, sources }: { text: string; sources: Source[] }) {
  return (
    <>
      {splitCitations(text).map((piece, i) => {
        if (piece.type === "text") return <span key={i}>{piece.text}</span>;
        // A marker with no matching source is styled "unknown" so a made-up citation is visible.
        const source = sources.find((s) => s.id === piece.id);
        return <sup key={i} className={`cite${source ? "" : " unknown"}`} title={source?.title ?? "Unknown source"}>{piece.id}</sup>;
      })}
    </>
  );
}

/** The whole Copilot screen: thread list on the left, conversation on the right. */
function CopilotInner() {
  const search = useSearchParams();
  const [deals, setDeals] = useState<DealSummary[]>([]);
  const [dealId, setDealId] = useState<string>(search.get("deal") ?? "");
  // null = a new conversation that has not been saved yet (the server creates the id).
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [threads, setThreads] = useState<ConversationSummary[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [renaming, setRenaming] = useState<string | null>(null);
  const [renameText, setRenameText] = useState("");
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  // Lets the Stop button, or switching thread, cancel an answer that is still streaming.
  const abort = useRef<AbortController | null>(null);
  const bottom = useRef<HTMLDivElement | null>(null);

  /** Reload the sidebar list (after saving, renaming or deleting). */
  const refreshThreads = useCallback(async () => {
    try {
      setThreads(await api.conversations());
    } catch (e) {
      setError(e);
    }
  }, []);

  /** Keep the address bar in step (?c=<thread>&deal=<deal>) so a reload or a shared link reopens it. */
  function setUrl(thread: string | null, deal: string) {
    const params = new URLSearchParams();
    if (thread) params.set("c", thread);
    if (deal) params.set("deal", deal);
    const query = params.toString();
    window.history.replaceState(null, "", query ? `/copilot?${query}` : "/copilot");
  }

  /** Load a saved thread and show its messages and deal. */
  const openThread = useCallback(async (id: string) => {
    abort.current?.abort();
    setBusy(false);
    setError(null);
    try {
      const detail = await api.conversation(id);
      setConversationId(detail.id);
      setMessages(detail.messages.map(fromStored));
      setDealId(detail.deal_id ?? "");
      setUrl(detail.id, detail.deal_id ?? "");
    } catch (e) {
      setError(e);
    }
  }, []);

  /** Start a fresh conversation: clear the screen; the id is created on the first answer. */
  function newThread() {
    abort.current?.abort();
    setBusy(false);
    setConversationId(null);
    setMessages([]);
    setError(null);
    setUrl(null, dealId);
  }

  // On first load: fetch deals and threads, and open the thread named in the address, if any.
  useEffect(() => {
    api.deals().then((d) => {
      setDeals(d);
      setDealId((current) => current || d.find((x) => x.id === "D-DEMO-001")?.id || "");
    }).catch(setError);
    void refreshThreads();
    const wanted = search.get("c");
    if (wanted) void openThread(wanted);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Keep the newest message in view as tokens arrive.
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  /** Change only the last message (the answer being streamed) without touching the others. */
  function patchLast(patch: (m: Message) => Message) {
    setMessages((all) => all.map((m, i) => (i === all.length - 1 ? patch(m) : m)));
  }

  /** Send a question and fill the answer in live from the server-sent events. */
  async function ask(text: string) {
    const question = text.trim();
    if (!question || busy) return;
    setInput("");
    setError(null);
    setBusy(true);
    // Show the question at once, plus an empty answer bubble that the tokens will fill.
    setMessages((all) => [...all, { role: "user", content: question }, { role: "assistant", content: "" }]);
    abort.current = new AbortController();
    let thread = conversationId;
    try {
      await streamCopilot({ message: question, deal_id: dealId || null, conversation_id: conversationId }, (event) => {
        // meta arrives first: evidence, intent, model, the thread id and any rewritten question.
        if (event.event === "meta") {
          thread = event.data.conversation_id ?? thread;
          setConversationId(thread);
          setMessages((all) => all.map((m, i) => {
            if (i === all.length - 1) return { ...m, sources: event.data.sources, intent: event.data.intent, model: event.data.model };
            // The second-to-last message is the user's question: attach "Understood as" to it.
            if (i === all.length - 2) return { ...m, understood: event.data.understood_as };
            return m;
          }));
        // token: one piece of the answer text; append it.
        } else if (event.event === "token") patchLast((m) => ({ ...m, content: m.content + event.data.text }));
        // done: the turn was saved; record the citations and refresh the sidebar.
        else if (event.event === "done") {
          patchLast((m) => ({ ...m, cited: event.data.cited }));
          thread = event.data.conversation_id ?? thread;
          setUrl(thread, dealId);
          void refreshThreads();
        } else if (event.event === "error") patchLast((m) => ({ ...m, failed: event.data.message }));
      }, abort.current.signal);
    } catch (e) {
      // A user-pressed Stop is not an error; anything else is shown on the answer bubble.
      if (!(e instanceof DOMException && e.name === "AbortError")) {
        setError(e);
        patchLast((m) => ({ ...m, failed: e instanceof ApiError ? e.message : "The answer could not be completed." }));
      }
    } finally {
      setBusy(false);
    }
  }

  /** Save the new title typed in the sidebar (an empty title is ignored). */
  async function saveRename(id: string) {
    const title = renameText.trim();
    setRenaming(null);
    if (!title) return;
    try {
      await api.renameConversation(id, title);
      await refreshThreads();
    } catch (e) {
      setError(e);
    }
  }

  /** Delete a thread; if it is the one open, return to a blank conversation. */
  async function remove(id: string) {
    setConfirmDelete(null);
    try {
      await api.deleteConversation(id);
      if (id === conversationId) newThread();
      await refreshThreads();
    } catch (e) {
      setError(e);
    }
  }

  // Suggested follow-ups: only after a finished, successful answer, and never one already asked.
  const last = messages[messages.length - 1];
  const asked = new Set(messages.filter((m) => m.role === "user").map((m) => m.content.trim().toLowerCase()));
  const followUps = !busy && last?.role === "assistant" && !last.failed && last.content
    ? (FOLLOW_UPS[last.intent ?? "deal"] ?? []).filter((q) => !asked.has(q.toLowerCase()))
    : [];
  const dealName = deals.find((d) => d.id === dealId)?.name;

  return (
    <main className="container wide copilot-page">
      <div className="pagehead">
        <div>
          <h1>Copilot</h1>
          <p className="muted">Answers come only from the deal&apos;s tasks and the playbook, with sources you can check. It assists; people decide.</p>
        </div>
      </div>

      <div className="copilot">
        <aside className="threads" aria-label="Conversations">
          <button className="primary wide" onClick={newThread}>+ New conversation</button>
          {threads.length === 0 ? (
            <p className="muted small pad">Your conversations are saved here. Ask a question to start one.</p>
          ) : (
            <ul>
              {threads.map((t) => (
                <li key={t.id} className={t.id === conversationId ? "active" : ""}>
                  {renaming === t.id ? (
                    <form onSubmit={(e) => { e.preventDefault(); void saveRename(t.id); }} className="rename">
                      <input autoFocus value={renameText} maxLength={60} aria-label="Conversation title" onChange={(e) => setRenameText(e.target.value)} onKeyDown={(e) => { if (e.key === "Escape") setRenaming(null); }} />
                    </form>
                  ) : (
                    <button className="thread" onClick={() => void openThread(t.id)} aria-current={t.id === conversationId ? "true" : undefined}>
                      <span className="thread-title">{t.title}</span>
                      <span className="muted small">{relativeTime(t.updated_at)} &middot; {Math.ceil(t.message_count / 2)} Q&amp;A{t.deal_id ? ` · ${t.deal_id}` : ""}</span>
                    </button>
                  )}
                  {confirmDelete === t.id ? (
                    <span className="thread-actions confirm">
                      <button className="danger small-btn" onClick={() => void remove(t.id)}>Delete</button>
                      <button className="ghost small-btn" onClick={() => setConfirmDelete(null)}>Keep</button>
                    </span>
                  ) : renaming !== t.id && (
                    <span className="thread-actions">
                      <button className="ghost small-btn" aria-label={`Rename ${t.title}`} onClick={() => { setRenaming(t.id); setRenameText(t.title); }}>Rename</button>
                      <button className="ghost small-btn" aria-label={`Delete ${t.title}`} onClick={() => setConfirmDelete(t.id)}>Delete</button>
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </aside>

        <section className="copilot-main">
          <div className="row">
            <label className="inline">Deal
              <select value={dealId} onChange={(e) => { setDealId(e.target.value); if (!conversationId) setUrl(null, e.target.value); }}>
                <option value="">(none - process questions only)</option>
                {deals.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
              </select>
            </label>
            {conversationId && <span className="muted small">Saved conversation. A change of deal applies from your next question.</span>}
          </div>
          <ErrorBox error={error} />

          <div className="chat" aria-live="polite">
            {messages.length === 0 && (
              <div className="empty">
                <h2>Ask about {dealName ? dealName : "a deal or the process"}</h2>
                <p className="muted">Follow-up questions work: ask &ldquo;and who owns those?&rdquo; and the Copilot knows what &ldquo;those&rdquo; means.</p>
                <div className="example-grid">
                  {EXAMPLES.map((e) => (
                    <button key={e.q} className="example" onClick={() => void ask(e.q)}>
                      <strong>{e.q}</strong><span className="muted small">{e.hint}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
            {messages.map((m, i) => (
              <div key={i} className={`msg ${m.role}`}>
                <div className="bubble">
                  {m.role === "assistant" && m.content ? <Answer text={m.content} sources={m.sources ?? []} /> : m.content}
                  {!m.content && m.role === "assistant" && !m.failed && <span className="muted">Thinking...</span>}
                  {m.failed && <div className="bad small">{m.failed}</div>}
                </div>
                {m.role === "user" && m.understood && <div className="muted small understood">Understood as: {m.understood}</div>}
                {m.role === "assistant" && m.sources && m.sources.length > 0 && (
                  <details className="evidence">
                    <summary>
                      Evidence ({m.sources.length}){m.cited && m.cited.length > 0 ? ` · cited ${m.cited.join(", ")}` : ""}
                      {m.model ? ` · ${m.model}` : ""}
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
            {followUps.length > 0 && (
              <div className="followups" aria-label="Suggested follow-up questions">
                {followUps.map((q) => <button key={q} onClick={() => void ask(q)}>{q}</button>)}
              </div>
            )}
            <div ref={bottom} />
          </div>

          <form className="composer" onSubmit={(e) => { e.preventDefault(); void ask(input); }}>
            <input value={input} onChange={(e) => setInput(e.target.value)} placeholder={messages.length ? "Ask a follow-up..." : "Ask about the deal or the process..."} maxLength={2000} aria-label="Your question" />
            {busy ? <button type="button" onClick={() => abort.current?.abort()}>Stop</button> : <button className="primary" disabled={!input.trim()}>Ask</button>}
          </form>
        </section>
      </div>
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
