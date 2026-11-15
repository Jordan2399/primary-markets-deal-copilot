"use client";

import { useEffect, useRef, type ReactNode } from "react";

/**
 * A modal "are you sure?" box for actions that are hard to undo. Escape and a click on the
 * backdrop cancel it, the focus starts on the safe button (Cancel) and returns to where it was
 * when the box closes.
 */
export default function ConfirmDialog({
  open,
  title,
  children,
  confirmLabel,
  onConfirm,
  onCancel,
  confirmDisabled = false,
  busy = false,
}: {
  open: boolean;
  title: string;
  children: ReactNode;
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
  confirmDisabled?: boolean;
  busy?: boolean;
}) {
  const cancelButton = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const before = document.activeElement as HTMLElement | null; // to give the focus back later
    cancelButton.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      before?.focus?.();
    };
  }, [open, onCancel]);

  if (!open) return null;
  return (
    <div className="dialog-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onCancel()}>
      <div className="dialog" role="dialog" aria-modal="true" aria-labelledby="dialog-title">
        <h2 id="dialog-title">{title}</h2>
        <div className="dialog-body">{children}</div>
        <div className="row end">
          <button ref={cancelButton} type="button" onClick={onCancel}>Cancel</button>
          <button type="button" className="primary" disabled={confirmDisabled || busy} onClick={onConfirm}>
            {busy ? "Working..." : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
