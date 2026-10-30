import { useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceDot,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import { Async, Banner, DataTable, PageHeader, Panel, Pill, SegmentSwatch, TooltipBox } from "../components/ui";
import { AXIS, GRID } from "../lib/chart";
import { useApi } from "../lib/api";
import { clusterColor, count, money, num, pct } from "../lib/format";
import type { SegmentsResponse } from "../lib/types";

type View = "pca" | "rfm";

export default function Segmentation() {
  const state = useApi<SegmentsResponse>("/segments", { scatter_points: 1500 });
  return (
    <>
      <PageHeader title="Customer segmentation" subtitle="RFM features, log-scaled and standardised, clustered with K-Means. K is chosen by silhouette, not by eye." />
      <Async state={state}>{(d) => <Body d={d} />}</Async>
    </>
  );
}

function Body({ d }: { d: SegmentsResponse }) {
  const [view, setView] = useState<View>("pca");
  const [hidden, setHidden] = useState<Set<number>>(new Set());
  const names = useMemo(() => Object.fromEntries(d.profiles.map((p) => [p.cluster_id, p.segment_name])), [d.profiles]);
  const byCluster = useMemo(() => {
    const m = new Map<number, typeof d.scatter>();
    for (const p of d.scatter) m.set(p.cluster_id, [...(m.get(p.cluster_id) ?? []), p]);
    return m;
  }, [d.scatter]);
  const k2 = d.k_table.find((r) => r.k === 2);
  const champions = d.profiles[0];

  const toggle = (id: number) =>
    setHidden((h) => {
      const n = new Set(h);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });

  return (
    <div className="space-y-6">
      <Banner>
        {champions.segment_name} are {pct(champions.share, 0)} of customers but {pct(champions.revenue_share, 0)} of lifetime revenue, so protecting
        them matters more than anything else in this customer base.
      </Banner>

      <div className="grid gap-6 xl:grid-cols-3">
        <Panel
          className="xl:col-span-2"
          title={view === "pca" ? "Segments in a 2-D projection" : "Recency vs monetary value"}
          subtitle={
            view === "pca"
              ? `Axes are principal components of the scaled log-RFM space (${pct(d.pca_explained_variance[0], 0)} and ${pct(d.pca_explained_variance[1], 0)} of variance), not original RFM features. Deterministic sample of ${count(d.scatter.length)} customers.`
              : "Original units on log scales. Each dot is a customer; colour is the K-Means segment."
          }
          actions={
            <div role="group" aria-label="Scatter view" className="flex overflow-hidden rounded-md border border-line text-xs">
              {(["pca", "rfm"] as View[]).map((v) => (
                <button
                  key={v}
                  type="button"
                  aria-pressed={view === v}
                  onClick={() => setView(v)}
                  className={`px-2.5 py-1 ${view === v ? "bg-gold font-bold text-gold-ink" : "text-ink-2 hover:text-ink"}`}
                >
                  {v === "pca" ? "Projection" : "R vs M"}
                </button>
              ))}
            </div>
          }
        >
          <div className="mb-3 flex flex-wrap gap-2" role="group" aria-label="Show or hide segments">
            {d.profiles.map((p) => (
              <button
                key={p.cluster_id}
                type="button"
                aria-pressed={!hidden.has(p.cluster_id)}
                onClick={() => toggle(p.cluster_id)}
                className={`rounded-full border px-2.5 py-1 text-xs ${hidden.has(p.cluster_id) ? "border-line text-ink-3 line-through" : "border-line text-ink"}`}
              >
                <SegmentSwatch color={clusterColor(p.cluster_id)} name={p.segment_name} />
              </button>
            ))}
          </div>
          <div className="h-[380px]">
            <ResponsiveContainer>
              <ScatterChart margin={{ left: 4, right: 12, top: 8, bottom: 16 }}>
                <CartesianGrid {...GRID} vertical />
                {view === "pca" ? (
                  <>
                    <XAxis type="number" dataKey="x" name="Projection axis 1" {...AXIS} tickFormatter={(v) => num(v, 1)}
                      label={{ value: "Projection axis 1 (PCA)", position: "insideBottom", offset: -8, fill: "#8ea3c7", fontSize: 12 }} />
                    <YAxis type="number" dataKey="y" name="Projection axis 2" {...AXIS} tickFormatter={(v) => num(v, 1)} width={44}
                      label={{ value: "Projection axis 2", angle: -90, position: "insideLeft", fill: "#8ea3c7", fontSize: 12 }} />
                  </>
                ) : (
                  <>
                    <XAxis type="number" dataKey="recency_days" scale="log" domain={[1, 800]} allowDataOverflow {...AXIS}
                      ticks={[1, 7, 30, 90, 365, 730]}
                      label={{ value: "Days since last purchase (log)", position: "insideBottom", offset: -8, fill: "#8ea3c7", fontSize: 12 }} />
                    <YAxis type="number" dataKey="monetary" scale="log" domain={[1, "auto"]} allowDataOverflow {...AXIS} width={60}
                      tickFormatter={(v) => (v >= 1000 ? `£${v / 1000}k` : `£${v}`)} ticks={[10, 100, 1000, 10000, 100000]} />
                  </>
                )}
                <ZAxis range={[22, 22]} />
                <Tooltip
                  cursor={{ strokeDasharray: "3 3", stroke: "#8ea3c7" }}
                  content={({ active, payload }) => {
                    if (!active || !payload?.length) return null;
                    const p = payload[0].payload;
                    return (
                      <TooltipBox
                        title={names[p.cluster_id]}
                        rows={[
                          ["Recency", `${num(p.recency_days, 0)} days`],
                          ["Frequency", `${p.frequency} invoices`],
                          ["Monetary", money(p.monetary)],
                        ]}
                      />
                    );
                  }}
                />
                {d.profiles
                  .filter((p) => !hidden.has(p.cluster_id))
                  .map((p) => (
                    <Scatter
                      key={p.cluster_id}
                      name={p.segment_name}
                      data={byCluster.get(p.cluster_id) ?? []}
                      fill={clusterColor(p.cluster_id)}
                      fillOpacity={0.72}
                      isAnimationActive={false}
                    />
                  ))}
              </ScatterChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        <Panel
          title="Choosing K with silhouette"
          subtitle={`Selected K = ${d.selected_k}, silhouette ${num(d.silhouette, 3)}`}
          table={
            <DataTable
              caption="K selection"
              columns={[
                { key: "k", label: "K" },
                { key: "s", label: "Silhouette", align: "right" },
                { key: "min", label: "Smallest cluster", align: "right" },
                { key: "ari", label: "Stability ARI", align: "right" },
                { key: "ok", label: "Eligible" },
              ]}
              rows={d.k_table.map((r) => ({
                k: r.selected ? <strong className="text-gold">{r.k} ✓</strong> : r.k,
                s: num(r.silhouette, 3),
                min: pct(r.min_cluster_share),
                ari: num(r.stability_ari, 3),
                ok: r.passes_guards ? "yes" : r.in_selectable_range ? "fails guard" : "outside range",
              }))}
            />
          }
        >
          <div className="h-56">
            <ResponsiveContainer>
              <LineChart data={d.k_table} margin={{ left: 0, right: 12, top: 8 }}>
                <CartesianGrid {...GRID} />
                <XAxis dataKey="k" {...AXIS} />
                <YAxis {...AXIS} domain={["auto", "auto"]} tickFormatter={(v) => num(v, 2)} width={44} />
                <Tooltip
                  content={({ active, payload }) =>
                    active && payload?.length ? (
                      <TooltipBox
                        title={`K = ${payload[0].payload.k}`}
                        rows={[
                          ["Silhouette", num(payload[0].payload.silhouette, 3)],
                          ["Stability ARI", num(payload[0].payload.stability_ari, 3)],
                          ["Smallest cluster", pct(payload[0].payload.min_cluster_share)],
                        ]}
                      />
                    ) : null
                  }
                />
                <Line dataKey="silhouette" stroke="#169c8f" strokeWidth={2} dot={{ r: 4, fill: "#169c8f", stroke: "#10244a", strokeWidth: 2 }} isAnimationActive={false} />
                <ReferenceDot x={d.selected_k} y={d.silhouette} r={8} fill="#f5c542" stroke="#10244a" strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <p className="mt-3 text-xs leading-relaxed text-ink-3">
            <strong className="text-ink-2">Rule:</strong> {d.selection_rule}.
            {k2 && <> K = 2 scores higher ({num(k2.silhouette, 3)}) but only splits customers into two groups, which is too coarse for differentiated actions, so it is reported but not eligible.</>}
          </p>
        </Panel>
      </div>

      <Panel title="Segment sizes and centroids" subtitle="Centroids are back-transformed from the scaled log space to original units.">
        <DataTable
          caption="Segment centroids"
          columns={[
            { key: "name", label: "Segment" },
            { key: "n", label: "Customers", align: "right" },
            { key: "share", label: "Share", align: "right" },
            { key: "r", label: "Centroid recency (days)", align: "right" },
            { key: "f", label: "Centroid frequency", align: "right" },
            { key: "m", label: "Centroid monetary", align: "right" },
            { key: "rev", label: "Revenue share", align: "right" },
            { key: "lv", label: "R / F / M level" },
          ]}
          rows={d.profiles.map((p) => ({
            name: <SegmentSwatch color={clusterColor(p.cluster_id)} name={p.segment_name} />,
            n: count(p.customers),
            share: pct(p.share),
            r: num(p.centroid.recency_days, 0),
            f: num(p.centroid.frequency, 1),
            m: money(p.centroid.monetary),
            rev: pct(p.revenue_share),
            lv: (
              <span className="flex flex-wrap gap-1">
                <Pill>{p.levels.recency}</Pill>
                <Pill>{p.levels.frequency} F</Pill>
                <Pill>{p.levels.monetary} M</Pill>
              </span>
            ),
          }))}
        />
      </Panel>

      <Panel title="Recommended actions" subtitle="Derived from each segment's actual profile by a tested rule set; see Data & Methodology.">
        <ul className="grid gap-3 md:grid-cols-2">
          {d.profiles.map((p) => (
            <li key={p.cluster_id} className="rounded-lg border border-line p-4" style={{ borderLeft: `4px solid ${clusterColor(p.cluster_id)}` }}>
              <p className="font-bold text-ink">{p.segment_name}</p>
              <p className="mt-1 text-sm text-ink-2">{p.recommended_action}</p>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}
