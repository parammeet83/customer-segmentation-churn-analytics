import { useMemo, useState } from "react";
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Async, Banner, DataTable, PageHeader, Panel, SegmentSwatch, Stat, TooltipBox } from "../components/ui";
import { AXIS, GRID } from "../lib/chart";
import { useApi } from "../lib/api";
import { clusterColor, compactMoney, count, money, pct } from "../lib/format";
import { simulate, type Assumptions, type Ranking, type RiskRow } from "../lib/simulate";
import type { RetentionScenarios, SimulatorData } from "../lib/types";

const PRESETS: Record<string, Pick<Assumptions, "effectiveness" | "costPerContact">> = {
  conservative: { effectiveness: 0.05, costPerContact: 5 },
  base: { effectiveness: 0.1, costPerContact: 3 },
  optimistic: { effectiveness: 0.2, costPerContact: 2 },
};

export default function Simulator() {
  const data = useApi<SimulatorData>("/retention/simulator-data");
  const scen = useApi<RetentionScenarios>("/retention/scenarios");
  return (
    <>
      <PageHeader
        title="Retention simulator"
        subtitle="Choose who to contact and what you assume a campaign achieves. Every figure is a scenario estimate under the assumptions shown."
      />
      <Async state={data}>{(d) => <SimulatorBody d={d} scen={scen.data} />}</Async>
    </>
  );
}

function Slider({ id, label, value, min, max, step, onChange, display }: { id: string; label: string; value: number; min: number; max: number; step: number; onChange: (v: number) => void; display: string }) {
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <label htmlFor={id} className="text-sm text-ink-2">
          {label}
        </label>
        <output htmlFor={id} className="tabular text-sm font-bold text-gold">
          {display}
        </output>
      </div>
      <input id={id} type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} className="mt-1.5 w-full accent-[#f5c542]" />
    </div>
  );
}

export function SimulatorBody({ d, scen }: { d: SimulatorData; scen: RetentionScenarios | null }) {
  const rows: RiskRow[] = useMemo(() => d.rows.map(([p, rate, cluster], order) => ({ p, rate, cluster, order })), [d.rows]);
  const [a, setA] = useState<Assumptions>({ targetFraction: 0.1, effectiveness: 0.1, costPerContact: 3, horizonDays: d.churn_horizon_days, margin: 1, ranking: "risk" });
  const [useMargin, setUseMargin] = useState(false);
  const eff: Assumptions = { ...a, margin: useMargin ? a.margin : 1 };
  const set = (patch: Partial<Assumptions>) => setA((x) => ({ ...x, ...patch }));

  const out = simulate(rows, eff, d.season_factor);
  const other = simulate(rows, { ...eff, ranking: eff.ranking === "risk" ? "value_at_risk" : "risk" }, d.season_factor);
  const presets = Object.entries(PRESETS).map(([name, p]) => ({ name, out: simulate(rows, { ...eff, ...p }, d.season_factor) }));
  // 41 cheap passes over a few thousand rows; recomputed on every change.
  const curve = Array.from({ length: 41 }, (_, i) => {
    const e = i / 100;
    return { e, net: simulate(rows, { ...eff, effectiveness: e }, d.season_factor).net };
  });
  const basis = useMargin ? "gross-margin" : "revenue";

  return (
    <div className="space-y-6">
      <Banner label="Decision">
        Targeting {count(out.targeted)} customers by {eff.ranking === "risk" ? "risk alone" : "risk × value"} puts an estimated {money(out.revenueAtRisk)} of
        revenue at risk in scope; ranking by {eff.ranking === "risk" ? "risk × value" : "risk alone"} instead would cover {money(other.revenueAtRisk)}. Break-even
        effectiveness: {out.breakEvenEffectiveness === null ? "n/a" : pct(out.breakEvenEffectiveness)}.
      </Banner>

      <div className="grid gap-6 xl:grid-cols-3">
        <Panel title="Assumptions" subtitle="Change any input; results recalculate immediately.">
          <div className="space-y-5">
            <fieldset>
              <legend className="mb-1.5 text-sm text-ink-2">Who to target</legend>
              <div role="radiogroup" className="flex overflow-hidden rounded-md border border-line text-sm">
                {(["risk", "value_at_risk"] as Ranking[]).map((r) => (
                  <button
                    key={r}
                    type="button"
                    role="radio"
                    aria-checked={a.ranking === r}
                    onClick={() => set({ ranking: r })}
                    className={`flex-1 px-3 py-1.5 ${a.ranking === r ? "bg-gold font-bold text-gold-ink" : "text-ink-2 hover:text-ink"}`}
                  >
                    {r === "risk" ? "Highest risk" : "Highest risk × value"}
                  </button>
                ))}
              </div>
            </fieldset>
            <Slider id="target" label="Customers targeted (% of scored)" value={a.targetFraction * 100} min={1} max={50} step={1} onChange={(v) => set({ targetFraction: v / 100 })} display={`${Math.round(a.targetFraction * 100)}% · ${count(out.targeted)}`} />
            <Slider id="eff" label="Campaign effectiveness" value={a.effectiveness * 100} min={0} max={50} step={1} onChange={(v) => set({ effectiveness: v / 100 })} display={pct(a.effectiveness, 0)} />
            <Slider id="cost" label="Cost per contacted customer" value={a.costPerContact} min={0} max={20} step={0.5} onChange={(v) => set({ costPerContact: v })} display={money(a.costPerContact, true)} />
            <Slider id="horizon" label="Revenue horizon (days)" value={a.horizonDays} min={30} max={180} step={15} onChange={(v) => set({ horizonDays: v })} display={`${a.horizonDays} d`} />
            <div>
              <label className="flex items-center gap-2 text-sm text-ink-2">
                <input type="checkbox" checked={useMargin} onChange={(e) => setUseMargin(e.target.checked)} className="h-4 w-4 accent-[#f5c542]" />
                Apply a gross-margin assumption
              </label>
              {useMargin && (
                <div className="mt-3">
                  <Slider id="margin" label="Gross margin" value={a.margin * 100} min={5} max={100} step={5} onChange={(v) => set({ margin: v / 100 })} display={pct(a.margin, 0)} />
                </div>
              )}
            </div>
            <div className="flex flex-wrap gap-2">
              {Object.entries(PRESETS).map(([name, p]) => (
                <button key={name} type="button" onClick={() => set(p)} className="rounded-md border border-line px-3 py-1.5 text-xs text-ink-2 capitalize hover:border-gold hover:text-gold">
                  {name} preset
                </button>
              ))}
            </div>
          </div>
        </Panel>

        <div className="space-y-6 xl:col-span-2">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
            <Stat label="Customers targeted" value={count(out.targeted)} hint={`avg risk ${pct(out.averageRisk)}`} />
            <Stat label="Expected revenue at risk" value={compactMoney(out.revenueAtRisk)} hint={`of ${compactMoney(out.projectedRevenue)} projected`} />
            <Stat label="Scenario revenue retained" value={compactMoney(out.retained)} hint={`at ${pct(eff.effectiveness, 0)} effectiveness`} accent />
            <Stat label="Campaign cost" value={compactMoney(out.cost)} hint={`${money(eff.costPerContact, true)} × ${count(out.targeted)}`} />
            <Stat
              label={`Net impact (${basis} basis)`}
              value={<span className={out.net >= 0 ? "text-good" : "text-bad"}>{(out.net >= 0 ? "+" : "−") + compactMoney(Math.abs(out.net))}</span>}
              hint={useMargin ? "retained × margin − cost" : "retained − cost; not profit"}
            />
            <Stat label="Break-even effectiveness" value={out.breakEvenEffectiveness === null ? "n/a" : pct(out.breakEvenEffectiveness)} hint="effectiveness where net = 0" />
          </div>

          <Panel
            title="Net impact vs campaign effectiveness"
            subtitle="Holding every other assumption fixed. The gold line marks your chosen effectiveness."
            table={<DataTable columns={[{ key: "e", label: "Effectiveness" }, { key: "n", label: "Net impact", align: "right" }]} rows={curve.filter((_, i) => i % 5 === 0).map((c) => ({ e: pct(c.e, 0), n: money(c.net) }))} />}
          >
            <div className="h-64">
              <ResponsiveContainer>
                <LineChart data={curve} margin={{ left: 8, right: 16, top: 8, bottom: 12 }}>
                  <CartesianGrid {...GRID} />
                  <XAxis dataKey="e" type="number" domain={[0, 0.4]} tickFormatter={(v) => pct(v, 0)} {...AXIS}
                    label={{ value: "Campaign effectiveness", position: "insideBottom", offset: -6, fill: "#8ea3c7", fontSize: 12 }} />
                  <YAxis tickFormatter={(v) => compactMoney(v)} width={72} {...AXIS} />
                  <ReferenceLine y={0} stroke="#8ea3c7" />
                  <ReferenceLine x={Math.min(eff.effectiveness, 0.4)} stroke="#f5c542" strokeWidth={2} />
                  <Tooltip
                    content={({ active, payload }) =>
                      active && payload?.length ? <TooltipBox title={`Effectiveness ${pct(payload[0].payload.e, 0)}`} rows={[["Net impact", money(payload[0].payload.net)]]} /> : null
                    }
                  />
                  <Line dataKey="net" stroke="#169c8f" strokeWidth={2} dot={false} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </Panel>
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Panel title="Scenario comparison" subtitle={`Presets at your current targeting (${pct(eff.targetFraction, 0)}, ${eff.ranking === "risk" ? "risk" : "risk × value"}), horizon and basis.`}>
          <DataTable
            caption="Scenario comparison"
            columns={[
              { key: "s", label: "Scenario" },
              { key: "a", label: "Effectiveness / cost", align: "right" },
              { key: "r", label: "Retained", align: "right" },
              { key: "c", label: "Cost", align: "right" },
              { key: "n", label: "Net", align: "right" },
            ]}
            rows={presets.map(({ name, out: o }) => ({
              s: <span className="capitalize">{name}</span>,
              a: `${pct(PRESETS[name].effectiveness, 0)} / ${money(PRESETS[name].costPerContact)}`,
              r: money(o.retained),
              c: money(o.cost),
              n: <span className={o.net >= 0 ? "text-good" : "text-bad"}>{money(o.net)}</span>,
            }))}
          />
        </Panel>
        <Panel title="Who is in the targeted cohort" subtitle="Segment mix of the customers selected under the current assumptions.">
          <ul className="space-y-2">
            {Object.entries(out.segmentMix)
              .sort((x, y) => y[1] - x[1])
              .map(([cid, n]) => (
                <li key={cid} className="flex items-center gap-3 text-sm">
                  <span className="w-48 shrink-0 text-ink-2">
                    <SegmentSwatch color={clusterColor(Number(cid))} name={d.segments[cid] ?? `Segment ${cid}`} />
                  </span>
                  <span className="h-2.5 flex-1 overflow-hidden rounded-full bg-navy-800" aria-hidden="true">
                    <span className="block h-full rounded-full" style={{ width: `${(n / out.targeted) * 100}%`, backgroundColor: clusterColor(Number(cid)) }} />
                  </span>
                  <span className="tabular w-24 text-right text-ink">
                    {count(n)} ({pct(n / out.targeted, 0)})
                  </span>
                </li>
              ))}
          </ul>
        </Panel>
      </div>

      <Panel title="Assumptions and method (always shown)">
        <ul className="list-disc space-y-1.5 pl-5 text-sm text-ink-2">
          <li>Population: {count(out.population)} customers who bought in the 180 days before the scoring date; ties broken deterministically.</li>
          <li>Risk = the model's probability of no purchase in the next {d.churn_horizon_days} days. Changing the revenue horizon does not change this probability.</li>
          <li>
            Projected revenue = 180-day gross spend ÷ 180 (capped at the 99.5th percentile) × horizon × seasonal factor {d.season_factor.toFixed(2)}
            {scen?.season_factor.reference_horizon ? ` (same calendar window a year earlier: ${scen.season_factor.reference_horizon.join(" → ")})` : ""}.
          </li>
          <li>Expected revenue at risk = Σ probability × projected revenue. Retained = at risk × effectiveness. Cost = targeted × cost per contact.</li>
          <li>
            Net impact is on a {basis} basis{useMargin ? ` with ${pct(eff.margin, 0)} margin` : "; it ignores product cost, so it is not profit"}.
          </li>
          <li className="text-gold">{scen?.disclaimer ?? "Scenario estimates under stated assumptions. No intervention outcomes are observed in this dataset."}</li>
        </ul>
      </Panel>
    </div>
  );
}
