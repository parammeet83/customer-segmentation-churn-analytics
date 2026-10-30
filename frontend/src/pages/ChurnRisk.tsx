import { useEffect, useRef } from "react";
import { useSearchParams } from "react-router";
import { Async, Banner, ErrorState, Loading, PageHeader, Panel, Pill, SegmentSwatch } from "../components/ui";
import { ContributionBars } from "../components/ContributionBars";
import { useApi } from "../lib/api";
import { clusterColor, count, money, num, pct, prettyFeature } from "../lib/format";
import type { CustomerDetail, CustomerList, CustomerRow, SegmentsResponse } from "../lib/types";

const BANDS = ["Very high", "High", "Medium", "Low"] as const;
const SORTS = { risk: "Risk rank", value_at_risk: "Expected revenue at risk", monetary: "180-day spend", recency: "Days since purchase" } as const;

const bandTone = (b: string) => (b === "Very high" ? "bad" : b === "High" ? "warn" : "neutral") as "bad" | "warn" | "neutral";

export default function ChurnRisk() {
  const [params, setParams] = useSearchParams();
  const page = Number(params.get("page") ?? 1);
  const segment = params.get("segment") ?? "";
  const band = params.get("band") ?? "";
  const top = params.get("top") === "1";
  const sort = (params.get("sort") ?? "risk") as keyof typeof SORTS;
  const selected = params.get("customer");

  const segs = useApi<SegmentsResponse>("/segments", { scatter_points: 0 });
  const list = useApi<CustomerList>("/customers", {
    page,
    page_size: 25,
    segment: segment || undefined,
    risk_band: band || undefined,
    top_decile: top ? true : undefined,
    sort,
  });

  const update = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(patch)) {
      if (v === null || v === "") next.delete(k);
      else next.set(k, v);
    }
    if (!("page" in patch)) next.delete("page");
    setParams(next);
  };

  return (
    <>
      <PageHeader title="Churn risk" subtitle="Customers ranked by predicted probability of no purchase in the next 90 days. Keys are pseudonymous." />
      <div className="space-y-6">
        <Banner label="How to use this list">
          Start with the top-10% cohort, then sort by expected revenue at risk: a high probability on a low-spend customer is worth less than a
          moderate probability on a valuable one.
        </Banner>

        <Panel title="Filters">
          <form className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5" onSubmit={(e) => e.preventDefault()}>
            <label className="text-sm text-ink-3">
              Segment
              <select value={segment} onChange={(e) => update({ segment: e.target.value })} className="mt-1 w-full rounded-md border border-line bg-navy-900 px-2 py-2 text-ink">
                <option value="">All segments</option>
                {segs.data?.profiles.map((p) => (
                  <option key={p.cluster_id} value={p.cluster_id}>
                    {p.segment_name}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-sm text-ink-3">
              Risk band
              <select value={band} onChange={(e) => update({ band: e.target.value })} className="mt-1 w-full rounded-md border border-line bg-navy-900 px-2 py-2 text-ink">
                <option value="">All bands</option>
                {BANDS.map((b) => (
                  <option key={b}>{b}</option>
                ))}
              </select>
            </label>
            <label className="text-sm text-ink-3">
              Sort by
              <select value={sort} onChange={(e) => update({ sort: e.target.value })} className="mt-1 w-full rounded-md border border-line bg-navy-900 px-2 py-2 text-ink">
                {Object.entries(SORTS).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex items-end gap-2 pb-2 text-sm text-ink-2">
              <input type="checkbox" checked={top} onChange={(e) => update({ top: e.target.checked ? "1" : null })} className="h-4 w-4 accent-[#f5c542]" />
              Top-10% cohort only
            </label>
            <div className="flex items-end pb-1">
              <button type="button" onClick={() => setParams(new URLSearchParams())} className="rounded-md border border-line px-3 py-2 text-sm text-ink-2 hover:border-gold hover:text-gold">
                Reset filters
              </button>
            </div>
          </form>
        </Panel>

        <Async state={list} isEmpty={(d) => d.items.length === 0}>
          {(d) => (
            <Panel title={`${count(d.meta.total)} customers`} subtitle={`Page ${d.meta.page} of ${d.meta.pages}. Select a row for the customer's profile and explanation.`}>
              <CustomerTable rows={d.items} selected={selected} onSelect={(k) => update({ customer: k, page: String(page) })} />
              <nav aria-label="Pagination" className="mt-4 flex items-center justify-between gap-2 text-sm">
                <button type="button" disabled={page <= 1} onClick={() => update({ page: String(page - 1) })} className="rounded-md border border-line px-3 py-1.5 text-ink-2 disabled:opacity-40">
                  ← Previous
                </button>
                <span className="text-ink-3">
                  {(page - 1) * d.meta.page_size + 1}–{Math.min(page * d.meta.page_size, d.meta.total)} of {count(d.meta.total)}
                </span>
                <button type="button" disabled={page >= d.meta.pages} onClick={() => update({ page: String(page + 1) })} className="rounded-md border border-line px-3 py-1.5 text-ink-2 disabled:opacity-40">
                  Next →
                </button>
              </nav>
            </Panel>
          )}
        </Async>
      </div>
      {selected && <CustomerDrawer key={selected} customerKey={selected} onClose={() => update({ customer: null, page: String(page) })} />}
    </>
  );
}

function CustomerTable({ rows, selected, onSelect }: { rows: CustomerRow[]; selected: string | null; onSelect: (k: string) => void }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[860px] text-left text-sm">
        <caption className="sr-only">Customers ranked by churn risk</caption>
        <thead>
          <tr className="border-b border-line text-xs text-ink-3 uppercase">
            <th scope="col" className="px-2 py-2 text-right">Rank</th>
            <th scope="col" className="px-2 py-2">Customer</th>
            <th scope="col" className="px-2 py-2">Segment</th>
            <th scope="col" className="px-2 py-2 text-right">Probability</th>
            <th scope="col" className="px-2 py-2">Band</th>
            <th scope="col" className="px-2 py-2 text-right">Recency (d)</th>
            <th scope="col" className="px-2 py-2 text-right">Invoices 180d</th>
            <th scope="col" className="px-2 py-2 text-right">Spend 180d</th>
            <th scope="col" className="px-2 py-2 text-right">Exp. revenue at risk</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.customer_key} className={`border-b border-line/50 ${selected === r.customer_key ? "bg-navy-700" : "hover:bg-navy-850"}`}>
              <td className="tabular px-2 py-2 text-right text-ink-3">{r.risk_rank}</td>
              <td className="px-2 py-2">
                <button type="button" onClick={() => onSelect(r.customer_key)} className="font-mono text-gold underline-offset-2 hover:underline" aria-label={`Open details for customer ${r.customer_key}`}>
                  {r.customer_key}
                </button>
                {r.in_top_decile && <span className="ml-2"><Pill tone="gold">top 10%</Pill></span>}
              </td>
              <td className="px-2 py-2 text-ink-2">
                <SegmentSwatch color={clusterColor(r.cluster_id)} name={r.segment_name} />
              </td>
              <td className="px-2 py-2 text-right">
                <span className="tabular inline-flex items-center justify-end gap-2 text-ink">
                  <span className="hidden h-1.5 w-16 overflow-hidden rounded-full bg-navy-700 sm:inline-block" aria-hidden="true">
                    <span className="block h-full rounded-full bg-gold" style={{ width: `${r.churn_probability * 100}%` }} />
                  </span>
                  {pct(r.churn_probability)}
                </span>
              </td>
              <td className="px-2 py-2"><Pill tone={bandTone(r.risk_band)}>{r.risk_band}</Pill></td>
              <td className="tabular px-2 py-2 text-right text-ink-2">{num(r.recency_days, 0)}</td>
              <td className="tabular px-2 py-2 text-right text-ink-2">{r.frequency}</td>
              <td className="tabular px-2 py-2 text-right text-ink-2">{money(r.monetary)}</td>
              <td className="tabular px-2 py-2 text-right text-ink">{money(r.expected_revenue_at_risk)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CustomerDrawer({ customerKey, onClose }: { customerKey: string; onClose: () => void }) {
  const state = useApi<CustomerDetail>(`/customers/${encodeURIComponent(customerKey)}`);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-navy-950/60" onClick={onClose}>
      <div
        ref={ref}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={`Customer ${customerKey}`}
        onClick={(e) => e.stopPropagation()}
        className="h-full w-full max-w-xl overflow-y-auto border-l border-line bg-navy-900 p-5 shadow-2xl"
      >
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <p className="text-xs text-ink-3">Customer (pseudonymous key)</p>
            <h2 className="font-mono text-xl font-bold text-gold">{customerKey}</h2>
          </div>
          <button type="button" onClick={onClose} className="rounded-md border border-line px-3 py-1.5 text-sm text-ink-2">
            Close
          </button>
        </div>
        {state.error ? (
          <ErrorState error={state.error} onRetry={state.retry} />
        ) : !state.data ? (
          <Loading />
        ) : (
          <DrawerBody d={state.data} />
        )}
      </div>
    </div>
  );
}

function DrawerBody({ d }: { d: CustomerDetail }) {
  const c = d.customer;
  const featureKeys = ["recency_days", "frequency", "monetary", "frequency_lifetime", "tenure_days", "mean_gap_days", "spend_trend", "frequency_trend", "return_rate"];
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3">
        <div className="panel p-3">
          <p className="text-xs text-ink-3">Inactivity probability</p>
          <p className="tabular text-2xl font-extrabold text-gold">{pct(c.churn_probability)}</p>
          <p className="text-xs text-ink-3">rank {c.risk_rank} · {c.risk_band}</p>
        </div>
        <div className="panel p-3">
          <p className="text-xs text-ink-3">Expected revenue at risk</p>
          <p className="tabular text-2xl font-extrabold text-ink">{money(c.expected_revenue_at_risk)}</p>
          <p className="text-xs text-ink-3">of {money(c.projected_revenue)} projected (estimate)</p>
        </div>
      </div>
      <p className="text-sm text-ink-2">
        Segment: <SegmentSwatch color={clusterColor(c.cluster_id)} name={c.segment_name} /> · features as of {d.observation_date}
      </p>
      <section>
        <h3 className="mb-2 font-bold text-ink">Why the model scored this customer</h3>
        {d.explanation_available ? (
          <ContributionBars items={d.explanation} />
        ) : (
          <p className="text-sm text-ink-3">Individual explanations are stored for the top-10% risk cohort only.</p>
        )}
        <p className="mt-2 text-xs text-ink-3">{d.note}</p>
      </section>
      <section>
        <h3 className="mb-2 font-bold text-ink">Behaviour features</h3>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
          {featureKeys.map((k) => (
            <div key={k}>
              <dt className="text-xs text-ink-3">{prettyFeature(k)}</dt>
              <dd className="tabular text-ink">{d.features[k] === null || d.features[k] === undefined ? "n/a" : num(d.features[k] as number, 2)}</dd>
            </div>
          ))}
        </dl>
      </section>
    </div>
  );
}
