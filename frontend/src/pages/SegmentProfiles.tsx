import { useSearchParams } from "react-router";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Async, DataTable, PageHeader, Panel, Pill, Stat, TooltipBox } from "../components/ui";
import { AXIS, GRID } from "../lib/chart";
import { useApi } from "../lib/api";
import { clusterColor, count, money, num, pct } from "../lib/format";
import type { Bin, SegmentDetail, SegmentsResponse } from "../lib/types";

const DIST_LABELS = {
  recency_days: { title: "Recency", unit: (b: Bin) => `${b.bin_start}–${b.bin_end} d` },
  frequency: { title: "Frequency", unit: (b: Bin) => `${b.bin_start}–${b.bin_end - 1}` },
  monetary: { title: "Monetary", unit: (b: Bin) => `£${b.bin_start >= 1000 ? `${b.bin_start / 1000}k` : b.bin_start}+` },
} as const;

export default function SegmentProfiles() {
  const list = useApi<SegmentsResponse>("/segments", { scatter_points: 0 });
  const [params, setParams] = useSearchParams();
  const selected = Number(params.get("segment") ?? 0);
  const detail = useApi<SegmentDetail>(`/segments/${selected}`);

  return (
    <>
      <PageHeader title="Segment profiles" subtitle="What each segment looks like in plain numbers, and how much churn risk sits inside it." />
      <Async state={list}>
        {(segs) => (
          <div className="space-y-6">
            <div role="tablist" aria-label="Segments" className="flex flex-wrap gap-2">
              {segs.profiles.map((p) => (
                <button
                  key={p.cluster_id}
                  role="tab"
                  aria-selected={p.cluster_id === selected}
                  onClick={() => setParams({ segment: String(p.cluster_id) })}
                  className={`rounded-lg border px-3 py-2 text-sm ${p.cluster_id === selected ? "border-gold bg-navy-700 font-bold text-ink" : "border-line text-ink-2 hover:text-ink"}`}
                  style={{ borderLeft: `4px solid ${clusterColor(p.cluster_id)}` }}
                >
                  {p.segment_name}
                </button>
              ))}
            </div>
            <Async state={detail}>{(d) => <Profile d={d} segs={segs} />}</Async>
          </div>
        )}
      </Async>
    </>
  );
}

function Profile({ d, segs }: { d: SegmentDetail; segs: SegmentsResponse }) {
  const p = d.profile;
  const color = clusterColor(p.cluster_id);
  const popMed = segs.population_quantiles;
  return (
    <div className="space-y-6" role="tabpanel" aria-label={p.segment_name}>
      <div className="panel p-5" style={{ borderLeft: `6px solid ${color}` }}>
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-2xl font-extrabold text-ink">{p.segment_name}</h2>
          <Pill>{p.levels.recency}</Pill>
          <Pill>{p.levels.frequency} frequency</Pill>
          <Pill>{p.levels.monetary} spend</Pill>
          {p.levels.is_new && <Pill tone="gold">new</Pill>}
        </div>
        <p className="mt-2 max-w-3xl text-ink-2">
          <span className="font-bold text-gold">Recommended action: </span>
          {p.recommended_action}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Customers" value={count(p.customers)} hint={`${pct(p.share)} of the base`} />
        <Stat label="Revenue share" value={pct(p.revenue_share)} hint={`${money(p.revenue)} lifetime gross`} />
        <Stat
          label="Scored for churn"
          value={count(d.scored_customers)}
          hint={d.scored_customers ? `bought in the last 180 days` : "none purchased in the last 180 days"}
        />
        <Stat
          label="Mean churn probability"
          value={d.mean_churn_probability === null ? "n/a" : pct(d.mean_churn_probability)}
          hint={`${count(d.top_decile_customers)} in the top-10% risk cohort`}
          accent
        />
      </div>

      <Panel title="Median profile vs whole customer base">
        <DataTable
          caption="Median comparison"
          columns={[
            { key: "m", label: "Measure" },
            { key: "seg", label: p.segment_name, align: "right" },
            { key: "q", label: "Segment interquartile range", align: "right" },
            { key: "pop", label: "All customers (median)", align: "right" },
          ]}
          rows={[
            { m: "Days since last purchase", seg: num(p.median.recency_days, 0), q: iqr(p.quartiles.recency_days, 0), pop: num(popMed.recency_days?.["0.5"] ?? NaN, 0) },
            { m: "Invoices (lifetime)", seg: num(p.median.frequency, 0), q: iqr(p.quartiles.frequency, 0), pop: num(popMed.frequency?.["0.5"] ?? NaN, 0) },
            { m: "Gross spend (lifetime)", seg: money(p.median.monetary), q: iqr(p.quartiles.monetary, 0, "£"), pop: money(popMed.monetary?.["0.5"] ?? NaN) },
            { m: "Tenure (days)", seg: num(p.median.tenure_days, 0), q: "—", pop: num(popMed.tenure_days?.["0.5"] ?? NaN, 0) },
          ]}
        />
      </Panel>

      <div className="grid gap-6 lg:grid-cols-3">
        {(Object.keys(DIST_LABELS) as (keyof typeof DIST_LABELS)[]).map((key) => {
          const bins = d.distributions[key].map((b) => ({ ...b, label: DIST_LABELS[key].unit(b) }));
          return (
            <Panel
              key={key}
              title={`${DIST_LABELS[key].title} distribution`}
              subtitle="Customers per bin (bins widen with value)."
              table={
                <DataTable columns={[{ key: "label", label: "Bin" }, { key: "customers", label: "Customers", align: "right" }]} rows={bins.map((b) => ({ label: b.label, customers: count(b.customers) }))} />
              }
            >
              <div className="h-52">
                <ResponsiveContainer>
                  <BarChart data={bins} margin={{ left: 0, right: 4 }}>
                    <CartesianGrid {...GRID} />
                    <XAxis dataKey="label" {...AXIS} tick={{ ...AXIS.tick, fontSize: 10 }} interval={0} angle={-30} textAnchor="end" height={48} />
                    <YAxis {...AXIS} width={40} />
                    <Tooltip
                      cursor={{ fill: "rgba(245,197,66,0.06)" }}
                      content={({ active, payload }) =>
                        active && payload?.length ? <TooltipBox title={payload[0].payload.label} rows={[["Customers", count(payload[0].payload.customers)]]} /> : null
                      }
                    />
                    <Bar dataKey="customers" fill={color} radius={[4, 4, 0, 0]} isAnimationActive={false} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Panel>
          );
        })}
      </div>
    </div>
  );
}

function iqr(q: number[] | undefined, digits: number, prefix = "") {
  if (!q || q.length < 3) return "—";
  return `${prefix}${num(q[0], digits)} – ${prefix}${num(q[2], digits)}`;
}
