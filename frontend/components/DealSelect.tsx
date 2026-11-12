"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/client";
import type { DealSummary } from "@/lib/types";

const BOOK_POSITION = 5; // Book building is the fifth stage

/** Loads the deals and lets the user pick one. Preselects the preferred deal so the page is never empty. */
export default function DealSelect({
  value,
  onChange,
  bookStagesOnly = false,
  allowNone = false,
  preferred = "D-2026-007",
}: {
  value: string;
  onChange: (id: string) => void;
  bookStagesOnly?: boolean;
  allowNone?: boolean;
  preferred?: string;
}) {
  const [deals, setDeals] = useState<DealSummary[]>([]);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    api.deals().then((all) => {
      const list = bookStagesOnly ? all.filter((d) => d.stage_position >= BOOK_POSITION) : all;
      setDeals(list);
      if (!value && !allowNone) {
        const pick = list.find((d) => d.id === preferred) ?? list[0];
        if (pick) onChange(pick.id);
      }
    }).catch(() => setFailed(true));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (failed) return <span className="bad small">Deals could not be loaded.</span>;
  return (
    <label className="inline">Deal
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        {allowNone && <option value="">(no deal: validation rules only)</option>}
        {deals.map((d) => (
          <option key={d.id} value={d.id}>{d.name} - {d.stage_name}</option>
        ))}
      </select>
    </label>
  );
}
