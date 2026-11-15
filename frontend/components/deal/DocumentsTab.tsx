"use client";

import Link from "next/link";
import { CardSkeleton } from "@/components/Skeleton";
import { EmptyState, ErrorBox, fmtTime } from "@/components/ui";
import { api } from "@/lib/client";
import { useLoad } from "@/lib/use-load";

/** The term sheets that were extracted for this deal (newest first). */
export default function DocumentsTab({ dealId }: { dealId: string }) {
  const { data: docs, error, loading } = useLoad(() => api.documents(dealId), [dealId]);

  if (loading && !docs) return <CardSkeleton lines={3} label="Loading documents" />;
  if (error) return <ErrorBox error={error} />;
  if (!docs || docs.length === 0) {
    return (
      <EmptyState title="No term sheets for this deal yet">
        Upload one in the <Link href={`/termsheets?deal=${dealId}`}>Term sheet lab</Link> and choose this deal; it will be listed here.
      </EmptyState>
    );
  }
  return (
    <section className="card">
      <div className="row between">
        <h2>Term sheets ({docs.length})</h2>
        <Link className="button" href={`/termsheets?deal=${dealId}`}>Add a term sheet</Link>
      </div>
      <div className="table-wrap">
<table>
        <thead><tr><th>File</th><th>Issuer</th><th>ISIN</th><th>Read by</th><th>Extracted</th></tr></thead>
        <tbody>
          {docs.map((d) => (
            <tr key={d.id}>
              <td>{d.filename}</td>
              <td>{d.issuer ?? "-"}</td>
              <td>{d.isin ?? "-"}</td>
              <td>{d.model ? `${d.model} (${d.method})` : "fixed rules"}</td>
              <td className="small">{fmtTime(d.extracted_at)} <span className="muted">by {d.extracted_by}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
</div>
    </section>
  );
}
