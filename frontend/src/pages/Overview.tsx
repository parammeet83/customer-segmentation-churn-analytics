import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Link } from "react-router";
import { Async, Banner, DataTable, PageHeader, Panel, SegmentSwatch, Stat, Steps, TooltipBox } from "../components/ui";
import { AXIS, GRID } from "../lib/chart";
import { useApi } from "../lib/api";
import { clusterColor, compactMoney, count, dateOnly, money, num, pct, prettyModel } from "../lib/format";
import type { Summary } from "../lib/types";

const BAND_COLORS: Record<string, string> = { "Very high": "#ef5f67", High: "#f0a33a", Medium: "#7b83ec", Low: "#3b5687" };

export default function Overview() {
  const state = useApi<Summary>("/summary");
  return (
    <>
      <PageHeader title="Segmentation + churn" subtitle="Connect analysis to a business decision: who to keep, why they may leave, and what it could be worth." />
      <Async state={state}>{(s) => <OverviewBody s={s} />}</Async>
    </>
  );
}

function OverviewBody({ s }: { s: Summary }) {
  const k = s.kpis;
  const segData = s.segments.map((g) => ({ name: g.segment_name, id: g.cluster_id, customers: g.share, revenue: g.revenue_share }));
  return (
    <div className="space-y-6">
      <Banner>{s.takeaway}</Banner>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Stat label="Customers scored" value={count(k.eligible_customers)} hint={`of ${count(k.segmented_customers)} segmented`} />
        <Stat label="Segments (K)" value={k.segment_count} hint="silhouette-selected" />
        <Stat label="90-day inactivity rate" value={pct(k.churn_rate_test)} hint="test period, observed" />
        <Stat label="Test ROC-AUC" value={num(k.test_roc_auc, 3)} hint={`${prettyModel(k.selected_model)} · PR-AUC ${num(k.test_pr_auc, 3)}`} />
        <Stat label="Top-10% capture" value={pct(k.top_decile_capture_rate_test)} hint={`lift ${num(k.top_decile_lift_test, 2)}× on test`} />
        <Stat label="Revenue at risk, top 10%" value={compactMoney(k.expected_revenue_at_risk_top_decile)} hint={`${count(k.top_decile_customers)} customers · estimate`} accent />
      </div>

      <div className="grid gap-6 xl:grid-cols-5">
        <Panel
          className="xl:col-span-3"
          title="Customers vs revenue by segment"
          subtitle="Share of customers and share of lifetime gross spend in each K-Means segment."
          table={
            <DataTable
              caption="Segment shares"
              columns={[
                { key: "name", label: "Segment" },
                { key: "customers", label: "Customers", align: "right" },
                { key: "share", label: "Customer share", align: "right" },
                { key: "rev", label: "Revenue share", align: "right" },
              ]}
              rows={s.segments.map((g) => ({
                name: <SegmentSwatch color={clusterColor(g.cluster_id)} name={g.segment_name} />,
                customers: count(g.customers),
                share: pct(g.share),
                rev: pct(g.revenue_share),
              }))}
            />
          }
        >
          <div className="h-72">
            <ResponsiveContainer>
              <BarChart data={segData} layout="vertical" margin={{ left: 8, right: 24 }} barGap={2} barCategoryGap="28%">
                <CartesianGrid {...GRID} horizontal={false} vertical />
                <XAxis type="number" tickFormatter={(v) => pct(v, 0)} domain={[0, 1]} {...AXIS} />
                <YAxis type="category" dataKey="name" width={150} {...AXIS} />
                <Tooltip
                  cursor={{ fill: "rgba(245,197,66,0.06)" }}
                  content={({ active, payload }) =>
                    active && payload?.length ? (
                      <TooltipBox
                        title={payload[0].payload.name}
                        rows={[
                          ["Customers", pct(payload[0].payload.customers)],
                          ["Revenue", pct(payload[0].payload.revenue)],
                        ]}
                      />
                    ) : null
                  }
                />
                <Bar dataKey="customers" name="Customer share" radius={[0, 4, 4, 0]} fill="#3b5687" />
                <Bar dataKey="revenue" name="Revenue share" radius={[0, 4, 4, 0]}>
                  {segData.map((d) => (
                    <Cell key={d.id} fill={clusterColor(d.id)} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <p className="mt-2 flex flex-wrap gap-4 text-xs text-ink-3">
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2.5 w-4 rounded-sm bg-[#3b5687]" aria-hidden="true" /> Customer share
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2.5 w-4 rounded-sm bg-c0" aria-hidden="true" /> Revenue share (segment colour)
            </span>
          </p>
        </Panel>

        <Panel className="xl:col-span-2" title="How CustomerPulse gets there" subtitle="RFM, K-Means, then a churn model, ending in a decision.">
          <Steps
            items={[
              <>
                Scale RFM features, pick K with silhouette → <Link className="text-gold underline" to="/segments">K = {k.segment_count}</Link>
              </>,
              <>
                Name each segment in business language → <Link className="text-gold underline" to="/segment-profiles">profiles</Link>
              </>,
              <>
                Handle imbalance, judge by recall and ROC-AUC → <Link className="text-gold underline" to="/model-performance">recall {pct(k.test_recall)}</Link>
              </>,
              <>
                Explain churn drivers with SHAP → <Link className="text-gold underline" to="/explainability">drivers</Link>
              </>,
              <>
                Size the top-10% retention opportunity → <Link className="text-gold underline" to="/simulator">simulator</Link>
              </>,
            ]}
          />
        </Panel>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Panel
          title="Current risk bands"
          subtitle={`Scored customers by predicted 90-day inactivity rank (scoring date ${s.run.scoring_cutoff ?? "n/a"}).`}
          table={
            <DataTable
              columns={[
                { key: "band", label: "Band" },
                { key: "n", label: "Customers", align: "right" },
                { key: "p", label: "Mean probability", align: "right" },
                { key: "v", label: "Expected revenue at risk", align: "right" },
              ]}
              rows={s.risk_bands.map((b) => ({ band: b.risk_band, n: count(b.customers), p: pct(b.mean_probability), v: money(b.expected_revenue_at_risk) }))}
            />
          }
        >
          <div className="h-60">
            <ResponsiveContainer>
              <BarChart data={s.risk_bands} margin={{ left: 8, right: 8 }}>
                <CartesianGrid {...GRID} />
                <XAxis dataKey="risk_band" {...AXIS} />
                <YAxis {...AXIS} tickFormatter={(v) => compactMoney(v)} width={70} />
                <Tooltip
                  cursor={{ fill: "rgba(245,197,66,0.06)" }}
                  content={({ active, payload }) =>
                    active && payload?.length ? (
                      <TooltipBox
                        title={`${payload[0].payload.risk_band} risk`}
                        rows={[
                          ["Customers", count(payload[0].payload.customers)],
                          ["Mean probability", pct(payload[0].payload.mean_probability)],
                          ["Expected revenue at risk", money(payload[0].payload.expected_revenue_at_risk)],
                        ]}
                      />
                    ) : null
                  }
                />
                <Bar dataKey="expected_revenue_at_risk" name="Expected revenue at risk" radius={[4, 4, 0, 0]}>
                  {s.risk_bands.map((b) => (
                    <Cell key={b.risk_band} fill={BAND_COLORS[b.risk_band]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <p className="mt-2 text-xs text-ink-3">
            Bands: Very high = top 10% by rank, High = next 20%, Medium = next 30%, Low = remaining 40%. Total expected revenue at risk across
            all scored customers: {money(k.expected_revenue_at_risk_all_scored)} (scenario estimate).
          </p>
        </Panel>

        <Panel title="Dataset coverage and latest run">
          <dl className="grid grid-cols-1 gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
            <Item k="Source" v={`${s.dataset.source_name} (${s.dataset.licence})`} />
            <Item k="Period" v={`${dateOnly(s.dataset.date_min)} → ${dateOnly(s.dataset.date_max)}`} />
            <Item k="Raw transaction lines" v={count(s.dataset.raw_rows)} />
            <Item k="Qualifying purchase lines" v={count(s.dataset.purchase_lines)} />
            <Item k="Customers with purchases" v={count(s.dataset.purchase_customers)} />
            <Item k="Model" v={`${prettyModel(s.run.selected_model ?? "")} (${s.run.model_version})`} />
            <Item k="Run" v={<span className="font-mono">{s.run.run_id.slice(0, 8)}</span>} />
            <Item k="Finished" v={s.run.finished_at ? new Date(s.run.finished_at).toLocaleString("en-GB") : "n/a"} />
          </dl>
          {s.latest_attempt && (
            <p className="mt-4 rounded-md border border-warn/60 p-3 text-sm text-warn" role="status">
              The most recent analysis run ({s.latest_attempt.run_id.slice(0, 8)}) {s.latest_attempt.status}. These pages show the last successful run.
            </p>
          )}
          <p className="mt-4 text-xs text-ink-3">
            Churn here means <strong className="text-ink-2">no qualifying purchase in the next 90 days</strong> under a historical behavioural rule. It is
            not a contractual or permanent churn label.
          </p>
        </Panel>
      </div>
    </div>
  );
}

function Item({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-ink-3">{k}</dt>
      <dd className="tabular font-medium text-ink">{v}</dd>
    </div>
  );
}
