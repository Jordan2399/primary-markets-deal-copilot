"use client";

import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";

type Tone = "good" | "bad" | "plain";
type ToastItem = { id: number; message: string; tone: Tone };

const AUTO_HIDE_MS = 4500;

// Without a provider (in tests, or a page outside the shell) notify() simply does nothing.
const Ctx = createContext<{ notify: (message: string, tone?: Tone) => void }>({ notify: () => {} });

/** `const { notify } = useToast(); notify("Task updated", "good")` shows a short message. */
export function useToast() {
  return useContext(Ctx);
}

/** Holds the visible messages and draws them in the bottom corner. Placed once in the app shell. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const counter = useRef(0);

  const dismiss = useCallback((id: number) => setItems((all) => all.filter((t) => t.id !== id)), []);

  const notify = useCallback(
    (message: string, tone: Tone = "plain") => {
      const id = ++counter.current;
      setItems((all) => [...all.slice(-3), { id, message, tone }]); // at most four at once
      setTimeout(() => dismiss(id), AUTO_HIDE_MS);
    },
    [dismiss],
  );

  const value = useMemo(() => ({ notify }), [notify]);
  return (
    <Ctx.Provider value={value}>
      {children}
      {/* aria-live announces new messages to screen readers without moving the focus. */}
      <div className="toasts" aria-live="polite" role="status">
        {items.map((t) => (
          <div key={t.id} className={`toast ${t.tone}`}>
            <span>{t.message}</span>
            <button type="button" aria-label="Dismiss" onClick={() => dismiss(t.id)}>&times;</button>
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}
