"use client";

import { useEffect, useState } from "react";
import { ErrorBox, fmtTime } from "@/components/ui";
import { api, getRole } from "@/lib/client";
import type { AuditEvent } from "@/lib/types";

export default function AuditPage() {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [filter, setFilter] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [role, setRole] = useState("viewer");

  useEffect(() => {
    setRole(getRole());
  }, []);

  useEffect(() => {
    if (getRole() !== "admin") return;
    api.audit(filter || undefined).then((e) => { setEvents(e); setError(null); }).catch(setError);
  }, [filter]);

  return (
    <main className="container wide">
      <h1>Audit trail</h1>
      <p className="muted">Every change and every Copilot answer is recorded here, with the model, prompt hash and sources used.</p>
      {role !== "admin" ? (
        <div className="alert">Only the admin role may read the audit trail. Switch the demo role at the top right.</div>
      ) : (
        <>
          <label className="inline">Action
            <select value={filter} onChange={(e) => setFilter(e.target.value)}>
              <option value="">All</option>
              <option value="copilot">copilot</option>
              <option value="task">task</option>
              <option value="deal">deal</option>
            </select>
          </label>
          <ErrorBox error={error} />
          <table className="card">
            <thead><tr><th>Time</th><th>Who</th><th>Action</th><th>Entity</th><th>Details</th></tr></thead>
            <tbody>
              {events.map((e) => (
                <tr key={e.id}>
                  <td>{fmtTime(e.ts)}</td>
                  <td>{e.actor} <span className="muted">({e.role})</span></td>
                  <td>{e.action}</td>
                  <td>{e.entity_id}</td>
                  <td className="small">
                    {e.model ? <div>model {e.model} &middot; prompt {e.prompt_hash}</div> : null}
                    {e.sources.length > 0 ? <div>{e.sources.length} sources</div> : null}
                    <code>{JSON.stringify(e.details).slice(0, 160)}</code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </main>
  );
}
