import type { ReactNode } from "react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Async, DataTable, PageHeader, Panel, TooltipBox } from "../components/ui";
import { AXIS, GRID } from "../lib/chart";
import { useApi } from "../lib/api";
import { compactMoney, count, dateOnly, money, num, pct } from "../lib/format";
import type { ChurnMetrics, DataQuality } from "../lib/types";

export default function Methodology() {
  const dq = useApi<DataQuality>("/data-quality");
  const churn = useApi<ChurnMetrics>("/churn/metrics");
  return (
    <>
      <PageHeader title="Data and methodology" subtitle="Where the numbers come from, how they were built, and what they cannot tell you." />
      <Async state={dq}>{(d) => <Body d={d} c={churn.data} />}</Async>
    </>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Panel title={title}>
      <div className="space-y-2 text-sm leading-relaxed text-ink-2">{children}</div>
    </Panel>
  );
}

function Body({ d, c }: { d: DataQuality; c: ChurnMetrics | null }) {
  const ds = d.dataset;
  const out = d.output;
  return (
    <div className="space-y-6">
      <div className="grid gap-6 xl:grid-cols-2">
        <Section title="Dataset source and attribution">
          <p>
            <strong className="text-ink">{ds.citation}</strong>
          </p>
          <p>
            Licence: {ds.licence}. Source:{" "}
            <a className="text-gold underline" href={ds.doi}>
              {ds.doi}
            </a>
            . Archive SHA-256 <span className="font-mono text-xs break-all">{ds.zip_sha256}</span>.
          </p>
          <p>
            Coverage: {dateOnly(ds.date_min)} to {dateOnly(ds.date_max)}, {count(ds.raw_rows)} raw transaction lines from one UK-based online retailer
            (mostly wholesale gift-ware buyers). {pct(Number(out.uk_share_of_purchase_lines ?? 0), 0)} of qualifying purchase lines are from UK customers.
          </p>
          {ds.details.sheets && (
            <DataTable
              columns={[
                { key: "s", label: "Workbook sheet" },
                { key: "r", label: "Rows", align: "right" },
                { key: "d", label: "Dates" },
              ]}
              rows={Object.entries(ds.details.sheets).map(([s, v]) => ({ s, r: count(v.rows), d: `${dateOnly(v.date_min)} → ${dateOnly(v.date_max)}` }))}
            />
          )}
        </Section>

        <Panel title="Qualifying purchase value by month" subtitle="After cleaning. Strong Q4 seasonality matters for churn labels and revenue projection.">
          <div className="h-64">
            <ResponsiveContainer>
              <AreaChart data={d.monthly_purchase_value} margin={{ left: 8, right: 8 }}>
                <CartesianGrid {...GRID} />
                <XAxis dataKey="month" tickFormatter={(v) => String(v).slice(0, 7)} {...AXIS} minTickGap={24} />
                <YAxis tickFormatter={(v) => compactMoney(v)} width={64} {...AXIS} />
                <Tooltip content={({ active, payload }) => (active && payload?.length ? <TooltipBox title={String(payload[0].payload.month).slice(0, 7)} rows={[["Purchase value", money(payload[0].payload.value)]]} /> : null)} />
                <Area dataKey="value" stroke="#f5c542" strokeWidth={2} fill="#f5c542" fillOpacity={0.12} isAnimationActive={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      </div>

      <Panel title="Cleaning policy and excluded rows" subtitle="Rules are applied in this order; each row is excluded for its first matching reason. Counts are from the actual run.">
        <div className="grid gap-6 lg:grid-cols-2">
          <DataTable
            caption="Exclusions"
            columns={[
              { key: "r", label: "Reason" },
              { key: "n", label: "Rows", align: "right" },
              { key: "s", label: "Share of raw", align: "right" },
            ]}
            rows={d.exclusions.map((e) => ({ r: e.reason.replace(/_/g, " "), n: count(e.rows), s: pct(e.share_of_raw, 2) }))}
          />
          <div className="space-y-2 text-sm text-ink-2">
            <p>
              Result: <strong className="text-ink">{count(Number(out.purchase_lines))}</strong> qualifying purchase lines on {count(Number(out.purchase_invoices))} invoices from{" "}
              {count(Number(out.purchase_customers))} customers ({money(Number(out.gross_purchase_value))} gross), plus {count(Number(out.return_lines))} cancellation lines (
              {money(Number(out.return_value))}) tracked separately as returns.
            </p>
            <ul className="list-disc space-y-1 pl-5">
              <li>Dec 1–9 2010 appears in both workbook sheets; the copy in the second sheet is removed after confirming the rows are identical.</li>
              <li>Exact duplicate lines are treated as data-entry duplicates.</li>
              <li>Lines without a customer ID cannot be attributed and are excluded (the largest exclusion).</li>
              <li>Postage, fees, manual adjustments and test codes are not merchandise and do not count towards spend.</li>
              <li>Cancellations (invoice prefix C) never count as purchases; their value is kept as a separate return feature.</li>
            </ul>
          </div>
        </div>
      </Panel>

      <div className="grid gap-6 xl:grid-cols-2">
        <Section title="RFM and customer features">
          <p>
            <strong className="text-ink">Recency</strong> = days from the last qualifying purchase to the observation date. <strong className="text-ink">Frequency</strong> = distinct
            qualifying invoices (never invoice lines). <strong className="text-ink">Monetary</strong> = gross merchandise spend; returns are a separate feature.
          </p>
          <p>
            Segmentation uses lifetime RFM for every customer at the scoring date ({d.features.scoring_cutoff}). The churn model uses 23 point-in-time features from a 180-day
            lookback plus lifetime history, such as purchase gaps, recent vs previous 90-day spend and returns.
          </p>
          <p>
            {pct(d.features.single_purchase_day_share)} of training rows have a single purchase day, so gap features are missing for them; the linear model imputes the training
            median and adds a missing-value indicator.
          </p>
        </Section>
        <Section title="K-Means and segment naming">
          <p>log1p then standard scaling on recency, frequency and monetary; K from 2 to 10 evaluated; K chosen by silhouette among 3–8 with minimum cluster size and bootstrap stability guards.</p>
          <p>
            Names come from rules on each cluster's median R, F, M and tenure relative to population tertiles (e.g. recent + high F + high M = Champions). If no rule fits, a
            neutral descriptive name is used. Loyalty additionally requires above-median tenure.
          </p>
        </Section>
      </div>

      {c && (
        <div className="grid gap-6 xl:grid-cols-2">
          <Section title="Behavioural churn definition">
            <p className="rounded-md border border-gold/60 p-3 text-ink">{c.definition.rule}</p>
            <p>
              Snapshots: {c.definition.snapshot_frequency}, {d.features.training_cutoffs.length} with complete future windows ({d.features.training_cutoffs[0]} to{" "}
              {d.features.training_cutoffs[d.features.training_cutoffs.length - 1]}), {count(d.features.training_rows)} customer-snapshot rows.
            </p>
            <p>
              The 90-day horizon was chosen because the median gap between purchase days is {num(d.features.interpurchase_gap_quantiles["0.5"], 0)} days and the 75th percentile{" "}
              {num(d.features.interpurchase_gap_quantiles["0.75"], 0)} days: 90 days without an order is unusual for an active customer, while 60 days would flag many routine gaps.
            </p>
            <p className="text-gold">{c.definition.disclaimer}</p>
          </Section>
          <Section title="Leakage prevention">
            <ul className="list-disc space-y-1 pl-5">
              <li>Features use only transactions strictly before the cutoff; labels use only the {c.definition.horizon_days} days from the cutoff.</li>
              <li>Chronological train → validation → test, with purged months so no label window crosses into a later partition.</li>
              <li>Imputation and scaling are fitted inside the model pipeline on training rows only.</li>
              <li>Model, hyper-parameters and threshold are chosen on validation; test is scored once afterwards. A test asserts selection is unchanged when test labels are shuffled.</li>
              <li>Customer identifiers are never model features; public keys are HMAC pseudonyms.</li>
            </ul>
          </Section>
        </div>
      )}

      <div className="grid gap-6 xl:grid-cols-2">
        <Section title="Model evaluation and SHAP">
          <p>Metrics: recall, precision, F1, ROC-AUC, PR-AUC, Brier score, confusion matrix, calibration, and top-10% precision, capture rate and lift (top 10% chosen within each month).</p>
          <p>SHAP explains the selected model in its own output space with an additivity check. Explanations show how the model scored a customer, not what caused their behaviour.</p>
        </Section>
        <Section title="Revenue projection and retention scenarios">
          <p>
            Projected revenue = 180-day gross spend ÷ 180 (capped at the 99.5th percentile) × horizon × a seasonal factor from the same calendar window one year earlier. It ignores
            margin unless a margin assumption is set.
          </p>
          <p>
            Expected revenue at risk = probability × projected revenue. Retained = at risk × assumed effectiveness. The dataset contains no campaign or intervention, so retained
            revenue is never observed; measuring it would need a controlled experiment or a suitable causal design.
          </p>
        </Section>
      </div>

      <Section title="Limitations">
        <ul className="list-disc space-y-1 pl-5">
          <li>One historical UK retailer (2009–2011), mostly business buyers; not representative of current, Indian or global consumer behaviour.</li>
          <li>About a fifth of raw lines lack a customer ID, so some customers' activity is under-counted.</li>
          <li>"Churn" is purchase inactivity under a fixed rule; seasonal buyers can be labelled inactive and later return.</li>
          <li>Only one test period of three months exists after purging; performance on unseen customers is lower than on returning ones.</li>
          <li>Tenure is left-censored at December 2009; customers active before then look newer than they are.</li>
          <li>Revenue figures are scenario estimates: revenue, not profit, unless a margin is applied.</li>
        </ul>
      </Section>
    </div>
  );
}
