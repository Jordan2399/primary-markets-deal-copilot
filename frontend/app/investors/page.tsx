"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Skeleton } from "@/components/Skeleton";
import { EmptyState, ErrorBox, Pill } from "@/components/ui";
import { ApiError, api } from "@/lib/client";
import { fmtK, label } from "@/lib/format";
import { useLoad } from "@/lib/use-load";
import type { InvestorQuery } from "@/lib/types";

const PAGE_SIZE = 25;
const SORTS: { value: NonNullable<InvestorQuery["sort"]>; label: string }[] = [
  { value: "name", label: "Name" },
  { value: "ordered", label: "Most ordered" },
  { value: "orders", label: "Most orders" },
  { value: "participation", label: "Most past deals" },
];

/** The investor directory: search, filter, sort and page through the synthetic investors. */
export default function InvestorDirectory() {
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState(""); // the search text a moment after typing stops
  const [type, setType] = useState("");
  const [region, setRegion] = useState("");
  const [realMoney, setRealMoney] = useState<"" | "true" | "false">("");
  const [esg, setEsg] = useState(false);
  const [sort, setSort] = useState<NonNullable<InvestorQuery["sort"]>>("name");
  const [page, setPage] = useState(1);

  // Wait 250 ms after the last keystroke so each letter does not trigger a request.
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(search.trim()), 250);
    return () => clearTimeout(timer);
  }, [search]);

  // Any change to a filter starts again from page 1.
  useEffect(() => setPage(1), [debounced, type, region, realMoney, esg, sort]);

  const { data, error, loading } = useLoad(
    () =>
      api.investors({
        q: debounced,
        type,
        region,
        real_money: realMoney === "" ? undefined : realMoney === "true",
        esg: esg ? true : undefined,
        sort,
        page,
        page_size: PAGE_SIZE,
      }),
    [debounced, type, region, realMoney, esg, sort, page],
  );

  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  const filtered = Boolean(debounced || type || region || realMoney || esg);

  // 403 = viewers have no access to investor data.
  if (error instanceof ApiError && error.status === 403) {
    return (
      <main className="container wide">
        <h1>Investors</h1>
        <EmptyState title="Investor data is for the Marketer, Syndicate, Approver and Administrator roles.">Sign in with one of those roles to use this page.</EmptyState>
      </main>
    );
  }

  return (
    <main className="container wide">
      <h1>Investors</h1>
      <p className="muted">The investor base behind the order books: who they are, what they usually buy, and what they did on each deal. All investors are synthetic.</p>

      <div className="filters" role="search">
        <label>Search
          <input type="search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Name or id" maxLength={60} />
        </label>
        <label>Type
          <select value={type} onChange={(e) => setType(e.target.value)}>
            <option value="">All types</option>
            {data?.types.map((f) => <option key={f.value} value={f.value}>{label(f.value)} ({f.count})</option>)}
          </select>
        </label>
        <label>Region
          <select value={region} onChange={(e) => setRegion(e.target.value)}>
            <option value="">All regions</option>
            {data?.regions.map((f) => <option key={f.value} value={f.value}>{f.value} ({f.count})</option>)}
          </select>
        </label>
        <label>Account
          <select value={realMoney} onChange={(e) => setRealMoney(e.target.value as "" | "true" | "false")}>
            <option value="">Any</option>
            <option value="true">Real money</option>
            <option value="false">Trading</option>
          </select>
        </label>
        <label className="inline"><input type="checkbox" checked={esg} onChange={(e) => setEsg(e.target.checked)} /> ESG focus</label>
        <label>Sort by
          <select value={sort} onChange={(e) => setSort(e.target.value as NonNullable<InvestorQuery["sort"]>)}>
            {SORTS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
        </label>
        {filtered && (
          <button type="button" onClick={() => { setSearch(""); setType(""); setRegion(""); setRealMoney(""); setEsg(false); }}>
            Clear filters
          </button>
        )}
      </div>

      <ErrorBox error={error} />
      <section className="card scroll" style={{ maxHeight: "none" }} aria-busy={loading}>
        {loading && !data ? (
          <Skeleton lines={8} height={18} />
        ) : data && data.items.length === 0 ? (
          <EmptyState title="No investors match these filters">Try removing a filter or searching for a different name.</EmptyState>
        ) : (
          data && (
            <>
              <p className="muted small" aria-live="polite">{data.total} investors{filtered ? " match" : ""}</p>
              <table>
                <thead>
                  <tr><th>Investor</th><th>Type</th><th>Region</th><th>Account</th><th>Typical ticket</th><th>Past deals</th><th>Orders here</th><th>Ordered</th><th>Allocated</th></tr>
                </thead>
                <tbody>
                  {data.items.map((i) => (
                    <tr key={i.id}>
                      <td><Link href={`/investors/${i.id}`}>{i.name}</Link> {i.esg_focus && <Pill tone="good">ESG</Pill>}</td>
                      <td>{label(i.type)}</td>
                      <td>{i.region}</td>
                      <td>{i.real_money ? "real money" : "trading"}</td>
                      <td>{fmtK(i.ticket_mean_k)}</td>
                      <td>{i.past_participation}</td>
                      <td>{i.orders}</td>
                      <td>{i.ordered_k ? fmtK(i.ordered_k) : "-"}</td>
                      <td>{i.allocated_k ? fmtK(i.allocated_k) : "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="pager">
                <button type="button" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button>
                <span>Page {page} of {pages}</span>
                <button type="button" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</button>
              </div>
            </>
          )
        )}
      </section>
    </main>
  );
}
