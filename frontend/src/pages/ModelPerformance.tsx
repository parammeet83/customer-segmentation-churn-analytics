import { Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Async, Banner, DataTable, PageHeader, Panel, Pill, TooltipBox } from "../components/ui";
import { AXIS, GRID } from "../lib/chart";
import { useApi } from "../lib/api";
import { count, num, pct, prettyModel } from "../lib/format";
import type { ChurnMetrics, ModelMetricRow, ModelMetrics } from "../lib/types";

// Fixed identity colours per model family (validated palette slots).
const MODEL_COLORS: Record<string, string> = { logistic_regression: "#e0585e", hist_gradient_boosting: "#169c8f", random_forest: "#7b83ec" };
const FAMILIES = ["logistic_regression", "hist_gradient_boosting", "random_forest"];

export default function ModelPerformance() {
  const models = useApi<ModelMetrics>("/models/metrics");
  const churn = useApi<ChurnMetrics>("/churn/metrics");
  return (
    <>
      <PageHeader title="Model performance" subtitle="Fix class imbalance, judge by recall and ROC-AUC, and evaluate once on future months the model never saw." />
      <Async state={churn}>{(c) => <Async state={models}>{(m) => <Body m={m} c={c} />}</Async>}</Async>
    </>
  );
}

function curveData(m: ModelMetrics, type: "roc" | "pr" | "calibration") {
  return FAMILIES.map((f) => ({ family: f, points: m.curves.find((c) => c.model_name === f && c.curve_type === type)?.points ?? [] }));
}

function Body({ m, c }: { m: ModelMetrics; c: ChurnMetrics }) {
  const test = FAMILIES.map((f) => m.metrics.find((x) => x.model_name === f && x.evaluation_split === "test")).filter(Boolean) as ModelMetricRow[];
  const val = m.metrics.filter((x) => x.evaluation_split === "validation");
  const sel = test.find((t) => t.is_selected)!;
  const tf = c.test_top_fraction;
  const testBal = c.class_balance.find((b) => b.partition === "test")!;

  return (
    <div className="space-y-6">
      <Banner>
        On held-out months ({c.split.test[0]} to {c.split.test[c.split.test.length - 1]}), the selected {prettyModel(sel.model_name).toLowerCase()} model ranks a random churner above a
        random non-churner {pct(sel.roc_auc, 0)} of the time. Contacting its top 10% each month reaches {pct(tf.capture_rate)} of churners at {pct(tf.precision)} precision,{" "}
        {num(tf.lift, 2)}× the {pct(tf.base_rate)} base rate.
      </Banner>

      <Panel title="Model comparison on the held-out test period" subtitle={`Selection used validation only (${c.selection_metric}); test was scored once afterwards.`}>
        <DataTable
          caption="Test metrics by model"
          columns={[
            { key: "m", label: "Model" },
            { key: "roc", label: "ROC-AUC", align: "right" },
            { key: "pr", label: "PR-AUC", align: "right" },
            { key: "rec", label: "Recall", align: "right" },
            { key: "prec", label: "Precision", align: "right" },
            { key: "f1", label: "F1", align: "right" },
            { key: "brier", label: "Brier", align: "right" },
            { key: "tp", label: "Top-10% precision", align: "right" },
            { key: "lift", label: "Top-10% lift", align: "right" },
          ]}
          rows={test.map((t) => ({
            m: (
              <span className="inline-flex items-center gap-2">
                <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: MODEL_COLORS[t.model_name] }} aria-hidden="true" />
                {prettyModel(t.model_name)} {t.is_selected && <Pill tone="gold">selected</Pill>}
              </span>
            ),
            roc: num(t.roc_auc, 3),
            pr: num(t.pr_auc, 3),
            rec: num(t.recall, 3),
            prec: num(t.precision, 3),
            f1: num(t.f1, 3),
            brier: num(t.brier, 3),
            tp: pct(t.top_precision),
            lift: `${num(t.top_lift, 2)}×`,
          }))}
        />
        <p className="mt-3 text-xs text-ink-3">
          Recall/precision/F1 use each model's validation-chosen threshold ({c.threshold_rule}). Test ROC-AUC spread across models:{" "}
          {num(Math.max(...test.map((t) => t.roc_auc)) - Math.min(...test.map((t) => t.roc_auc)), 3)}. The selection itself was made on validation, preferring the
          simpler model when validation ROC-AUC was within 0.002.
        </p>
      </Panel>

      <div className="grid gap-6 xl:grid-cols-2">
        <CurvePanel title="ROC curve (test)" data={curveData(m, "roc")} x="False positive rate" y="True positive rate" diagonal selected={sel.model_name} />
        <CurvePanel title="Precision–recall curve (test)" data={curveData(m, "pr")} x="Recall" y="Precision" baseline={testBal.churn_rate} selected={sel.model_name} />
      </div>

      <div className="grid gap-6 xl:grid-cols-3">
        <Panel title="Confusion matrix (test)" subtitle={`${prettyModel(sel.model_name)} at threshold ${num(sel.threshold, 3)}`}>
          <ConfusionMatrix t={sel} />
          <p className="mt-3 text-xs leading-relaxed text-ink-3">
            A <strong className="text-ink-2">false negative</strong> is a customer who goes quiet without being flagged: lost revenue with no chance to act. A{" "}
            <strong className="text-ink-2">false positive</strong> costs one unnecessary contact. That asymmetry is why the threshold targets recall.
          </p>
        </Panel>
        <Panel
          title="Observed churn by risk decile (test)"
          subtitle="Customers ranked within each test month; decile 1 = highest predicted risk."
          table={<DataTable columns={[{ key: "d", label: "Decile" }, { key: "n", label: "Customers", align: "right" }, { key: "r", label: "Observed churn", align: "right" }]} rows={c.test_deciles.map((d) => ({ d: d.decile, n: count(d.n), r: pct(d.churn_rate) }))} />}
          className="xl:col-span-2"
        >
          <div className="h-60">
            <ResponsiveContainer>
              <BarChart data={c.test_deciles} margin={{ left: 0, right: 8 }}>
                <CartesianGrid {...GRID} />
                <XAxis dataKey="decile" {...AXIS} />
                <YAxis {...AXIS} tickFormatter={(v) => pct(v, 0)} domain={[0, 1]} width={44} />
                <ReferenceLine y={tf.base_rate} stroke="#f5c542" strokeDasharray="4 4" label={{ value: `base ${pct(tf.base_rate, 0)}`, fill: "#f5c542", fontSize: 11, position: "insideTopRight" }} />
                <Tooltip
                  cursor={{ fill: "rgba(245,197,66,0.06)" }}
                  content={({ active, payload }) =>
                    active && payload?.length ? (
                      <TooltipBox title={`Decile ${payload[0].payload.decile}`} rows={[["Observed churn", pct(payload[0].payload.churn_rate)], ["Customers", count(payload[0].payload.n)], ["Mean score", num(payload[0].payload.mean_score, 3)]]} />
                    ) : null
                  }
                />
                <Bar dataKey="churn_rate" radius={[4, 4, 0, 0]} isAnimationActive={false}>
                  {c.test_deciles.map((d) => (
                    <Cell key={d.decile} fill={d.decile === 1 ? "#f5c542" : "#3b5687"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      </div>

      <Panel title="Temporal evaluation design" subtitle={`Monthly snapshots; label window ${c.definition.horizon_days} days. Purged months stop label windows crossing a partition boundary.`}>
        <Timeline c={c} />
        <div className="mt-4 overflow-x-auto">
          <DataTable
            caption="Class balance by partition"
            columns={[
              { key: "p", label: "Partition" },
              { key: "s", label: "Snapshots", align: "right" },
              { key: "r", label: "Rows", align: "right" },
              { key: "c", label: "Customers", align: "right" },
              { key: "rate", label: "Churn rate", align: "right" },
              { key: "range", label: "Cutoffs" },
            ]}
            rows={c.class_balance.map((b) => ({ p: b.partition, s: b.snapshots, r: count(b.rows), c: count(b.customers), rate: pct(b.churn_rate), range: `${b.first_cutoff} → ${b.last_cutoff}` }))}
          />
        </div>
        <p className="mt-3 text-xs leading-relaxed text-ink-3">
          {(() => {
            const h = c.horizon_sensitivity.find((x) => x.horizon_days === c.definition.horizon_days);
            return h ? `Imbalance is mild (churn ${pct(h.min_churn_rate, 0)}–${pct(h.max_churn_rate, 0)} by month), ` : "Imbalance is mild, ";
          })()}
          so class-weighted training is used and SMOTE is not: features are discrete counts and the same customer
          appears in several monthly snapshots ({num(c.repeated_customers.train_rows_per_customer, 1)} training rows per customer on average).
        </p>
      </Panel>

      <div className="grid gap-6 xl:grid-cols-2">
        <Panel title="Stability across test months">
          <DataTable
            caption="Per-snapshot test metrics"
            columns={[
              { key: "c", label: "Cutoff" },
              { key: "n", label: "Customers", align: "right" },
              { key: "rate", label: "Churn rate", align: "right" },
              { key: "roc", label: "ROC-AUC", align: "right" },
              { key: "rec", label: "Recall", align: "right" },
              { key: "top", label: "Top-10% precision", align: "right" },
            ]}
            rows={c.test_per_snapshot.map((s) => ({ c: <span className="whitespace-nowrap">{s.cutoff}</span>, n: count(s.n), rate: pct(s.positive_rate), roc: num(s.roc_auc, 3), rec: num(s.recall, 3), top: pct(s.top_precision) }))}
          />
          <h3 className="mt-5 mb-2 text-sm font-bold text-ink">Seen vs previously unseen customers</h3>
          <DataTable
            caption="Seen vs unseen"
            columns={[
              { key: "g", label: "Test customers" },
              { key: "n", label: "Rows", align: "right" },
              { key: "roc", label: "ROC-AUC", align: "right" },
              { key: "rec", label: "Recall", align: "right" },
            ]}
            rows={c.seen_vs_unseen.map((s) => ({ g: s.group.replace(/_/g, " "), n: count(s.n), roc: num(s.roc_auc, 3), rec: num(s.recall, 3) }))}
          />
          <p className="mt-2 text-xs text-ink-3">Customers with no earlier snapshot have less history, and the model ranks them noticeably less well.</p>
        </Panel>

        <Panel title="Calibration (test)" subtitle="Mean predicted probability vs observed churn rate, 10 quantile bins. On the diagonal = well calibrated.">
          <CurveChart data={curveData(m, "calibration")} x="Mean predicted probability" y="Observed churn rate" diagonal selected={sel.model_name} height={260} />
        </Panel>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Panel title="Inactivity-horizon sensitivity" subtitle="How the churn definition changes with the label window (same 180-day lookback).">
          <DataTable
            caption="Horizon sensitivity"
            columns={[
              { key: "h", label: "Horizon" },
              { key: "s", label: "Snapshots", align: "right" },
              { key: "o", label: "Observations", align: "right" },
              { key: "m", label: "Mean churn", align: "right" },
              { key: "r", label: "Range", align: "right" },
            ]}
            rows={c.horizon_sensitivity.map((h) => ({
              h: h.horizon_days === c.definition.horizon_days ? <strong className="text-gold">{h.horizon_days} days (used)</strong> : `${h.horizon_days} days`,
              s: h.n_snapshots,
              o: count(h.n_observations),
              m: pct(h.mean_churn_rate),
              r: `${pct(h.min_churn_rate, 0)}–${pct(h.max_churn_rate, 0)}`,
            }))}
          />
        </Panel>
        <Panel title="All validation configurations" subtitle="Every hyper-parameter setting tried, scored on the validation months only.">
          <div className="max-h-72 overflow-y-auto">
            <DataTable
              caption="Validation results"
              columns={[
                { key: "m", label: "Model" },
                { key: "p", label: "Parameters" },
                { key: "roc", label: "ROC-AUC", align: "right" },
                { key: "pr", label: "PR-AUC", align: "right" },
              ]}
              rows={val.map((v) => ({
                m: (
                  <span>
                    {prettyModel(v.model_name)} {v.is_family_best && <Pill tone={v.is_selected ? "gold" : "neutral"}>{v.is_selected ? "selected" : "family best"}</Pill>}
                  </span>
                ),
                p: <span className="font-mono text-xs break-all">{Object.entries(v.params).map(([k, x]) => `${k}=${x}`).join(", ")}</span>,
                roc: num(v.roc_auc, 4),
                pr: num(v.pr_auc, 4),
              }))}
            />
          </div>
        </Panel>
      </div>
    </div>
  );
}

function ConfusionMatrix({ t }: { t: ModelMetricRow }) {
  const cells = [
    { label: "True negative", v: t.tn, note: "stayed, not flagged" },
    { label: "False positive", v: t.fp, note: "stayed, flagged" },
    { label: "False negative", v: t.fn, note: "went quiet, missed" },
    { label: "True positive", v: t.tp, note: "went quiet, flagged" },
  ];
  const total = t.tn + t.fp + t.fn + t.tp;
  return (
    <div>
      <div className="mb-1 grid grid-cols-[auto_1fr_1fr] gap-1 text-center text-[11px] text-ink-3">
        <span />
        <span>Predicted active</span>
        <span>Predicted inactive</span>
      </div>
      <div className="grid grid-cols-[auto_1fr_1fr] gap-1">
        {["Actually active", "Actually inactive"].map((row, r) => (
          <div key={row} className="contents">
            <span className="flex items-center pr-1 text-[11px] text-ink-3 [writing-mode:vertical-rl] rotate-180">{row}</span>
            {cells.slice(r * 2, r * 2 + 2).map((c) => {
              const good = c.label.startsWith("True");
              return (
                <div key={c.label} className={`rounded-lg border p-3 ${good ? "border-good/50 bg-good/10" : "border-bad/50 bg-bad/10"}`}>
                  <p className="text-[11px] text-ink-3">{c.label}</p>
                  <p className="tabular text-xl font-extrabold text-ink">{count(c.v)}</p>
                  <p className="text-[11px] text-ink-3">
                    {pct(c.v / total)} · {c.note}
                  </p>
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

function Timeline({ c }: { c: ChurnMetrics }) {
  const all = [...c.split.train.map((d) => ({ d, p: "train" })), ...c.split.validation.map((d) => ({ d, p: "validation" })), ...c.split.test.map((d) => ({ d, p: "test" })), ...c.split.purged.map((d) => ({ d, p: "purged" }))].sort((a, b) => a.d.localeCompare(b.d));
  const style: Record<string, string> = {
    train: "bg-[#7b83ec] text-navy-950",
    validation: "bg-[#169c8f] text-navy-950",
    test: "bg-gold text-gold-ink",
    purged: "border border-dashed border-ink-3 text-ink-3",
  };
  return (
    <div>
      <ol className="flex flex-wrap gap-1" aria-label="Monthly snapshots by partition">
        {all.map((s) => (
          <li key={s.d} className={`rounded px-1.5 py-1 text-[11px] font-semibold ${style[s.p]}`} title={`${s.d}: ${s.p}`}>
            {s.d.slice(0, 7)}
            <span className="sr-only"> {s.p}</span>
          </li>
        ))}
      </ol>
      <p className="mt-2 flex flex-wrap gap-3 text-xs text-ink-3">
        {Object.keys(style).map((k) => (
          <span key={k} className="inline-flex items-center gap-1.5">
            <span className={`h-3 w-5 rounded ${style[k]}`} aria-hidden="true" /> {k}
          </span>
        ))}
      </p>
    </div>
  );
}

function CurvePanel(props: { title: string; data: ReturnType<typeof curveData>; x: string; y: string; diagonal?: boolean; baseline?: number; selected: string }) {
  return (
    <Panel title={props.title} subtitle="Selected model drawn thicker.">
      <CurveChart {...props} height={300} />
    </Panel>
  );
}

function CurveChart({ data, x, y, diagonal, baseline, selected, height }: { data: ReturnType<typeof curveData>; x: string; y: string; diagonal?: boolean; baseline?: number; selected: string; height: number }) {
  return (
    <div style={{ height }}>
      <ResponsiveContainer>
        <LineChart margin={{ left: 0, right: 12, top: 8, bottom: 16 }}>
          <CartesianGrid {...GRID} vertical />
          <XAxis type="number" dataKey="x" domain={[0, 1]} ticks={[0, 0.2, 0.4, 0.6, 0.8, 1]} tickFormatter={(v) => num(v, 1)} {...AXIS} label={{ value: x, position: "insideBottom", offset: -8, fill: "#8ea3c7", fontSize: 12 }} allowDuplicatedCategory={false} />
          <YAxis type="number" domain={[0, 1]} ticks={[0, 0.2, 0.4, 0.6, 0.8, 1]} tickFormatter={(v) => num(v, 1)} width={40} {...AXIS} label={{ value: y, angle: -90, position: "insideLeft", fill: "#8ea3c7", fontSize: 12 }} />
          {diagonal && <ReferenceLine segment={[{ x: 0, y: 0 }, { x: 1, y: 1 }]} stroke="#8ea3c7" strokeDasharray="4 4" />}
          {baseline !== undefined && <ReferenceLine y={baseline} stroke="#8ea3c7" strokeDasharray="4 4" />}
          <Tooltip
            content={({ active, payload }) =>
              active && payload?.length ? (
                <TooltipBox rows={payload.map((p) => [prettyModel(String(p.name)), `(${num(Number(p.payload.x), 2)}, ${num(Number(p.payload.y), 2)})`] as [string, string])} />
              ) : null
            }
          />
          <Legend verticalAlign="top" height={28} formatter={(v) => <span className="text-xs text-ink-2">{prettyModel(String(v))}</span>} />
          {data.map((s) => (
            <Line key={s.family} name={s.family} data={s.points} dataKey="y" stroke={MODEL_COLORS[s.family]} strokeWidth={s.family === selected ? 3 : 1.5} dot={false} isAnimationActive={false} />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
