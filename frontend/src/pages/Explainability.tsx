import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from "recharts";
import { ContributionBars } from "../components/ContributionBars";
import { Async, Banner, DataTable, PageHeader, Panel, TooltipBox } from "../components/ui";
import { AXIS, GRID } from "../lib/chart";
import { useApi } from "../lib/api";
import { num, pct, prettyFeature, prettyModel } from "../lib/format";
import type { Explanations } from "../lib/types";

// Sequential single-hue ramp (gold) for feature-value percentile: dim = low, bright = high.
const ramp = (p: number | null) => {
  if (p === null) return "#4b5d80";
  const l = 28 + p * 44;
  return `hsl(44 88% ${l}%)`;
};

export default function Explainability() {
  const [customer, setCustomer] = useState<string | null>(null);
  const state = useApi<Explanations>("/churn/explanations", { customer_key: customer ?? undefined });
  return (
    <>
      <PageHeader title="Explain churn drivers with SHAP" subtitle="Which behaviours push a customer's predicted inactivity risk up or down, overall and for individual customers." />
      <Async state={state}>{(d) => <Body d={d} customer={customer} setCustomer={setCustomer} />}</Async>
    </>
  );
}

function Body({ d, customer, setCustomer }: { d: Explanations; customer: string | null; setCustomer: (k: string | null) => void }) {
  const top = d.global.slice(0, 12);
  const beeswarmFeatures = useMemo(() => Array.from(new Set(d.beeswarm.map((b) => b.feature))), [d.beeswarm]);
  const bees = useMemo(() => {
    // Deterministic vertical jitter so overlapping points stay visible.
    return d.beeswarm.map((b, i) => ({
      ...b,
      row: beeswarmFeatures.length - beeswarmFeatures.indexOf(b.feature) + (((i * 7919) % 100) / 100 - 0.5) * 0.55,
    }));
  }, [d.beeswarm, beeswarmFeatures]);
  const raise = d.global.filter((g) => g.direction.includes("raise")).slice(0, 2);
  const lower = d.global.filter((g) => g.direction.includes("lower")).slice(0, 2);
  const local = customer ? d.local : null;

  return (
    <div className="space-y-6">
      <Banner label="Reading SHAP">
        Strongest signals: higher {lower.map((g) => prettyFeature(g.feature)).join(" and ")} lower predicted risk; higher{" "}
        {raise.map((g) => prettyFeature(g.feature)).join(" and ")} raise it. These are associations the model learned, not proof that changing
        them would change behaviour.
      </Banner>

      <div className="grid gap-6 xl:grid-cols-2">
        <Panel
          title="Global feature importance"
          subtitle={`Mean |SHAP| in ${d.output_space === "log_odds" ? "log-odds" : "probability"} units across all scored customers. Colour = direction of association.`}
          table={
            <DataTable
              caption="Global SHAP ranking"
              columns={[
                { key: "rank", label: "#" },
                { key: "f", label: "Feature" },
                { key: "d", label: "Meaning" },
                { key: "v", label: "Mean |SHAP|", align: "right" },
                { key: "dir", label: "Direction" },
              ]}
              rows={d.global.map((g) => ({ rank: g.rank, f: prettyFeature(g.feature), d: g.description, v: num(g.mean_abs_shap, 3), dir: g.direction }))}
            />
          }
        >
          <div className="h-[420px]">
            <ResponsiveContainer>
              <BarChart data={top} layout="vertical" margin={{ left: 8, right: 16 }}>
                <CartesianGrid {...GRID} horizontal={false} vertical />
                <XAxis type="number" {...AXIS} tickFormatter={(v) => num(v, 2)} />
                <YAxis type="category" dataKey="feature" width={170} {...AXIS} tickFormatter={prettyFeature} interval={0} />
                <Tooltip
                  cursor={{ fill: "rgba(245,197,66,0.06)" }}
                  content={({ active, payload }) =>
                    active && payload?.length ? (
                      <TooltipBox
                        title={prettyFeature(payload[0].payload.feature)}
                        rows={[
                          ["Mean |SHAP|", num(payload[0].payload.mean_abs_shap, 3)],
                          ["Direction", payload[0].payload.direction],
                        ]}
                      />
                    ) : null
                  }
                />
                <Bar dataKey="mean_abs_shap" radius={[0, 4, 4, 0]} isAnimationActive={false}>
                  {top.map((g) => (
                    <Cell key={g.feature} fill={g.direction.includes("raise") ? "#e0585e" : g.direction.includes("lower") ? "#169c8f" : "#b88a10"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <p className="mt-2 flex flex-wrap gap-4 text-xs text-ink-3">
            <Key color="#e0585e" label="higher values raise risk" />
            <Key color="#169c8f" label="higher values lower risk" />
            <Key color="#b88a10" label="mixed / non-monotonic" />
          </p>
        </Panel>

        <Panel title="Impact distribution (beeswarm)" subtitle="Each dot is one customer. Horizontal position = SHAP value; brightness = the customer's feature value percentile.">
          <div className="h-[420px]">
            <ResponsiveContainer>
              <ScatterChart margin={{ left: 8, right: 16, top: 8, bottom: 16 }}>
                <CartesianGrid {...GRID} vertical horizontal={false} />
                <XAxis type="number" dataKey="shap" {...AXIS} tickFormatter={(v) => num(v, 1)}
                  label={{ value: "SHAP value (← lowers risk · raises risk →)", position: "insideBottom", offset: -8, fill: "#8ea3c7", fontSize: 12 }} />
                <YAxis type="number" dataKey="row" domain={[0.4, beeswarmFeatures.length + 0.6]} ticks={beeswarmFeatures.map((_, i) => beeswarmFeatures.length - i)}
                  tickFormatter={(v) => prettyFeature(beeswarmFeatures[beeswarmFeatures.length - v] ?? "")} width={170} {...AXIS} interval={0} />
                <ZAxis range={[14, 14]} />
                <ReferenceLine x={0} stroke="#8ea3c7" strokeDasharray="3 3" />
                <Tooltip
                  content={({ active, payload }) => {
                    if (!active || !payload?.length) return null;
                    const p = payload[0].payload;
                    return (
                      <TooltipBox
                        title={prettyFeature(p.feature)}
                        rows={[
                          ["SHAP", num(p.shap, 3)],
                          ["Value percentile", p.value_percentile === null ? "missing" : pct(p.value_percentile, 0)],
                        ]}
                      />
                    );
                  }}
                />
                <Scatter data={bees} isAnimationActive={false}>
                  {bees.map((b, i) => (
                    <Cell key={i} fill={ramp(b.value_percentile)} />
                  ))}
                </Scatter>
              </ScatterChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-2 flex items-center gap-2 text-xs text-ink-3" aria-hidden="true">
            low value
            <span className="h-2 w-28 rounded-full" style={{ background: "linear-gradient(90deg, hsl(44 88% 28%), hsl(44 88% 72%))" }} />
            high value
          </div>
        </Panel>
      </div>

      <Panel
        title="Individual explanation"
        subtitle="Pick one of the highest-risk customers. Stored for the top-10% cohort, which is where retention decisions are made."
      >
        <div className="mb-4 flex flex-wrap gap-2">
          {d.example_customers.map((k) => (
            <button
              key={k}
              type="button"
              aria-pressed={customer === k}
              onClick={() => setCustomer(customer === k ? null : k)}
              className={`rounded-md border px-2.5 py-1 font-mono text-xs ${customer === k ? "border-gold bg-gold font-bold text-gold-ink" : "border-line text-ink-2 hover:text-ink"}`}
            >
              {k}
            </button>
          ))}
        </div>
        {local ? (
          <div className="grid gap-6 lg:grid-cols-2">
            <ContributionBars items={local} />
            <div className="space-y-2 text-sm text-ink-2">
              <p className="font-bold text-ink">In plain language</p>
              <ul className="list-disc space-y-1.5 pl-5">
                {local.slice(0, 5).map((c) => (
                  <li key={c.feature}>{c.explanation}</li>
                ))}
              </ul>
              <p className="pt-2 text-ink-3">
                Worth investigating: has this customer's order cadence or returns changed, and is there a service issue? The model cannot say why.
              </p>
            </div>
          </div>
        ) : (
          <p className="text-sm text-ink-3">Select a customer above to see which features raised or lowered their score.</p>
        )}
      </Panel>

      <Panel title="Method and limits">
        <ul className="list-disc space-y-1.5 pl-5 text-sm text-ink-2">
          <li>
            Model: {prettyModel(d.model_family)}. Explainer: {d.explainer}; background: {d.background.rows} training-period snapshots (seed {d.background.seed}).
          </li>
          <li>
            Additivity check: base value + contributions reproduce every model score to within {d.additivity_max_abs_error.toExponential(1)} (
            {d.output_space === "log_odds" ? "log-odds" : "probability"}).
          </li>
          <li>Several features are correlated (e.g. lifetime and recent frequency), so credit can be shared between them; read groups of related features together.</li>
          <li>{d.caveat}</li>
        </ul>
      </Panel>
    </div>
  );
}

function Key({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="h-2.5 w-4 rounded-sm" style={{ backgroundColor: color }} aria-hidden="true" />
      {label}
    </span>
  );
}
