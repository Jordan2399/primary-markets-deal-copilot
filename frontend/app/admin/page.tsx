"use client";

import { Skeleton } from "@/components/Skeleton";
import { ErrorBox, Pill, Stat, fmtTime } from "@/components/ui";
import { api } from "@/lib/client";
import { useSession } from "@/lib/session";
import { PERMISSIONS, ROLE_LABEL } from "@/lib/session-utils";
import { useLoad } from "@/lib/use-load";
import type { Role } from "@/lib/types";

const ROLE_ORDER: Role[] = ["viewer", "marketer", "syndicate", "approver", "admin"];

/** Administration: who has access, what each role may do, and recent use of the system. */
export default function AdminPage() {
  const { user } = useSession();
  const isAdmin = user.role === "admin";
  // The request is skipped for other roles (the API would answer 403 anyway).
  const { data, error, loading } = useLoad(() => (isAdmin ? api.adminOverview() : Promise.resolve(null)), [isAdmin]);

  if (!isAdmin) {
    return (
      <main className="container wide">
        <h1>Administration</h1>
        <div className="alert">Only administrators may open this page.</div>
      </main>
    );
  }

  return (
    <main className="container wide">
      <p className="eyebrow">Administration</p>
      <h1>Users, roles and usage</h1>
      <p className="muted">Access is granted by role. Changes to users are made in the user store; this page shows the current state and how the system is used.</p>
      <ErrorBox error={error} />
      {loading && !data && <Skeleton lines={6} />}

      {data && (
        <>
          <div className="stats">
            <Stat name="Users" value={String(data.users.length)} note={`${data.users.filter((u) => u.active).length} active`} />
            <Stat name="Sign-ins" value={String(data.sign_ins)} note={`in the last ${data.events_total} events`} />
            <Stat name="Failed sign-ins" value={String(data.failed_sign_ins)} tone={data.failed_sign_ins ? "warn" : undefined} />
            <Stat name="Copilot answers" value={String(data.ai_calls)} note="each one is audited" />
          </div>

          <section className="card" aria-labelledby="a-users">
            <h2 id="a-users">Users</h2>
            <div className="table-wrap">
              <table>
                <thead><tr><th>Name</th><th>Username</th><th>Role</th><th>Status</th><th className="num">Actions</th><th>Last action</th></tr></thead>
                <tbody>
                  {data.users.map((u) => (
                    <tr key={u.username}>
                      <td>{u.display_name.replace(/\s*\(.*\)/, "")}</td>
                      <td><code>{u.username}</code></td>
                      <td><span className={`role-badge role-${u.role}`}>{ROLE_LABEL[u.role]}</span></td>
                      <td>{u.active ? <Pill tone="good">Active</Pill> : <Pill tone="plain">Disabled</Pill>}</td>
                      <td className="num">{u.actions}</td>
                      <td>{u.last_action ? fmtTime(u.last_action) : <span className="muted">No activity</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="card" aria-labelledby="a-roles">
            <h2 id="a-roles">What each role may do</h2>
            <div className="table-wrap">
              <table className="matrix">
                <thead>
                  <tr>
                    <th>Permission</th>
                    {ROLE_ORDER.map((r) => (
                      <th key={r} className="num">{ROLE_LABEL[r]}<div className="muted small">{(() => { const n = data.roles.find((x) => x.role === r)?.users ?? 0; return `${n} ${n === 1 ? "user" : "users"}`; })()}</div></th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {PERMISSIONS.map((p) => (
                    <tr key={p.label}>
                      <td>{p.label}</td>
                      {ROLE_ORDER.map((r) => (
                        <td key={r} className="num">
                          {p.roles.includes(r) ? <span className="yes" aria-label="allowed">✓</span> : <span className="no" aria-label="not allowed">–</span>}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="muted small">The API checks every request against these rules. Allocations need two people: the person who proposes cannot approve.</p>
          </section>
        </>
      )}
    </main>
  );
}
