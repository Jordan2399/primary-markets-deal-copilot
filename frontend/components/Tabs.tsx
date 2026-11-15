"use client";

import { useRef, type KeyboardEvent } from "react";

export type TabItem<T extends string> = { id: T; label: string; count?: number };

/**
 * An accessible tab bar. Arrow keys, Home and End move between the tabs (the selected tab
 * follows the focus), and only the selected tab is in the Tab order, as screen-reader users expect.
 * The page renders the matching panel itself and gives it `id="panel-<id>"`.
 */
export default function Tabs<T extends string>({
  tabs,
  value,
  onChange,
  ariaLabel,
}: {
  tabs: readonly TabItem<T>[];
  value: T;
  onChange: (id: T) => void;
  ariaLabel: string;
}) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});

  function onKeyDown(event: KeyboardEvent, index: number) {
    // Work out which tab the key points at; other keys are left alone.
    let next = index;
    if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
    else if (event.key === "ArrowLeft") next = (index - 1 + tabs.length) % tabs.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = tabs.length - 1;
    else return;
    event.preventDefault();
    onChange(tabs[next].id);
    refs.current[tabs[next].id]?.focus();
  }

  return (
    <div className="tabs" role="tablist" aria-label={ariaLabel}>
      {tabs.map((tab, index) => (
        <button
          key={tab.id}
          ref={(el) => {
            refs.current[tab.id] = el;
          }}
          role="tab"
          id={`tab-${tab.id}`}
          aria-selected={tab.id === value}
          aria-controls={`panel-${tab.id}`}
          tabIndex={tab.id === value ? 0 : -1}
          onClick={() => onChange(tab.id)}
          onKeyDown={(e) => onKeyDown(e, index)}
        >
          {tab.label}
          {tab.count !== undefined && <span className="tab-count">{tab.count}</span>}
        </button>
      ))}
    </div>
  );
}
