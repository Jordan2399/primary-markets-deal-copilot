import { getHealth } from "@/lib/api";

// Always render on request so the status is live.
export const dynamic = "force-dynamic";

export default async function Home() {
  const health = await getHealth();

  return (
    <main className="container">
      <h1>System status</h1>
      <p className="muted">
        Live health of the services behind this application. All data in this project is synthetic.
      </p>

      <section className="card">
        <h2>Service status</h2>
        {health === null ? (
          <p className="bad">The API is not reachable.</p>
        ) : (
          <>
            <p>
              Overall:{" "}
              <strong className={health.status === "ok" ? "good" : "warn"}>
                {health.status}
              </strong>{" "}
              <span className="muted">
                (v{health.version}, {health.environment}, LLM provider: {health.llm_provider})
              </span>
            </p>
            <ul className="statuslist">
              {Object.entries(health.dependencies).map(([name, dep]) => (
                <li key={name}>
                  <span className={`dot ${dep.ok ? "ok" : "down"}`} aria-hidden="true" />
                  <strong>{name}</strong>
                  <span className={dep.ok ? "good" : "bad"}>{dep.ok ? "ok" : "down"}</span>
                  <span className="muted small">{dep.detail}</span>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
    </main>
  );
}
