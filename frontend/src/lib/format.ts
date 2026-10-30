export const CLUSTER_COLORS = ["var(--color-c0)", "var(--color-c1)", "var(--color-c2)", "var(--color-c3)"] as const;
// Hex values (validated palette) for places where CSS variables are not resolved, e.g. SVG exports.
export const CLUSTER_HEX = ["#e0585e", "#169c8f", "#b88a10", "#7b83ec"] as const;

export const clusterColor = (id: number) => CLUSTER_HEX[id % CLUSTER_HEX.length];

const gbp0 = new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP", maximumFractionDigits: 0 });
const gbp2 = new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP", maximumFractionDigits: 2 });
const int = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 0 });

export const money = (v: number, precise = false) => (precise ? gbp2 : gbp0).format(v);
export const count = (v: number) => int.format(v);
export const pct = (v: number, digits = 1) => `${(v * 100).toFixed(digits)}%`;
export const num = (v: number, digits = 2) => v.toFixed(digits);

export function compactMoney(v: number): string {
  const a = Math.abs(v);
  if (a >= 1_000_000) return `£${(v / 1_000_000).toFixed(2)}m`;
  if (a >= 10_000) return `£${(v / 1000).toFixed(1)}k`;
  return gbp0.format(v);
}

export const prettyModel = (name: string) =>
  ({
    logistic_regression: "Logistic regression",
    random_forest: "Random forest",
    hist_gradient_boosting: "HistGradientBoosting",
  })[name] ?? name;

export const prettyFeature = (f: string) => f.replace(/_/g, " ");

export const dateOnly = (iso: string) => iso.slice(0, 10);
