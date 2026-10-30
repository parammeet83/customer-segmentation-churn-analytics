// Synthetic API responses for component and end-to-end tests.
// These are test fixtures only and are never displayed as project results.
import type { ChurnMetrics, CustomerList, Explanations, ModelMetrics, RetentionScenarios, RunInfo, SegmentsResponse, SimulatorData, Summary, DataQuality, SegmentDetail, CustomerDetail } from "../lib/types";

const run: RunInfo = {
  run_id: "11111111-2222-3333-4444-555555555555",
  status: "succeeded",
  started_at: "2026-01-01T00:00:00Z",
  finished_at: "2026-01-01T00:10:00Z",
  code_version: "abc",
  selected_k: 3,
  selected_model: "logistic_regression",
  model_version: "logistic_regression-11111111",
  scoring_cutoff: "2011-12-10",
  error_summary: null,
};

const profile = (id: number, name: string) => ({
  cluster_id: id,
  segment_name: name,
  recommended_action: `Action for ${name}`,
  customers: 100 * (id + 1),
  share: [0.2, 0.3, 0.5][id],
  revenue: 1000 * (3 - id),
  revenue_share: [0.6, 0.3, 0.1][id],
  levels: { recency: "recent", frequency: "high", monetary: "high", is_new: false },
  median: { recency_days: 10, frequency: 5, monetary: 500, tenure_days: 300 },
  mean: { recency_days: 12, frequency: 6, monetary: 600, tenure_days: 310 },
  quartiles: { recency_days: [5, 10, 20], frequency: [2, 5, 8], monetary: [100, 500, 900] },
  centroid: { recency_days: 11, frequency: 5.5, monetary: 550 },
});
const profiles = [profile(0, "Fixture Champions"), profile(1, "Fixture At Risk"), profile(2, "Fixture Hibernating")];

export const summary: Summary = {
  run,
  latest_attempt: null,
  dataset: { source_name: "Online Retail II", doi: "https://doi.org/10.24432/C5CG6D", licence: "CC BY 4.0", citation: "Chen (2012)", raw_rows: 1000, date_min: "2009-12-01T07:45:00", date_max: "2011-12-09T12:50:00", purchase_lines: 800, purchase_customers: 60 },
  kpis: {
    eligible_customers: 40,
    segmented_customers: 60,
    segment_count: 3,
    churn_rate_test: 0.4,
    churn_rate_overall_snapshots: 0.45,
    selected_model: "logistic_regression",
    test_roc_auc: 0.7123,
    test_pr_auc: 0.65,
    test_recall: 0.7,
    top_decile_customers: 4,
    top_decile_capture_rate_test: 0.2,
    top_decile_lift_test: 1.5,
    expected_revenue_at_risk_top_decile: 1234,
    expected_revenue_at_risk_all_scored: 5000,
    currency: "GBP",
  },
  segments: profiles,
  risk_bands: [
    { risk_band: "Very high", customers: 4, mean_probability: 0.8, expected_revenue_at_risk: 1234 },
    { risk_band: "High", customers: 8, mean_probability: 0.6, expected_revenue_at_risk: 1000 },
    { risk_band: "Medium", customers: 12, mean_probability: 0.4, expected_revenue_at_risk: 1500 },
    { risk_band: "Low", customers: 16, mean_probability: 0.2, expected_revenue_at_risk: 1266 },
  ],
  takeaway: "Fixture takeaway sentence.",
};

export const segments: SegmentsResponse = {
  run_id: run.run_id,
  selected_k: 3,
  silhouette: 0.41,
  selection_rule: "Fixture rule",
  transform: "log1p then StandardScaler",
  population: "fixture",
  k_table: [2, 3, 4].map((k) => ({ k, silhouette: k === 3 ? 0.41 : 0.35, inertia: 10, min_cluster_share: 0.2, max_cluster_share: 0.5, stability_ari: 0.9, in_selectable_range: k > 2, passes_guards: k > 2, selected: k === 3 })),
  pca_explained_variance: [0.7, 0.2],
  profiles,
  scatter: Array.from({ length: 30 }, (_, i) => ({ cluster_id: i % 3, x: i / 10, y: (i % 5) / 3, recency_days: 10 + i, frequency: 1 + (i % 7), monetary: 100 + i * 10 })),
  population_quantiles: { recency_days: { "0.5": 50 }, frequency: { "0.5": 3 }, monetary: { "0.5": 400 }, tenure_days: { "0.5": 300 } },
};

export const segmentDetail: SegmentDetail = {
  profile: profiles[0],
  distributions: {
    recency_days: [{ bin_start: 0, bin_end: 30, customers: 80 }, { bin_start: 30, bin_end: 60, customers: 20 }],
    frequency: [{ bin_start: 1, bin_end: 2, customers: 50 }, { bin_start: 2, bin_end: 3, customers: 50 }],
    monetary: [{ bin_start: 0, bin_end: 250, customers: 40 }, { bin_start: 250, bin_end: 500, customers: 60 }],
  },
  scored_customers: 90,
  mean_churn_probability: 0.3,
  top_decile_customers: 2,
};

const customer = (i: number) => ({
  customer_key: `C-${i.toString(16).padStart(12, "0")}`,
  cluster_id: i % 3,
  segment_name: profiles[i % 3].segment_name,
  churn_probability: 0.95 - i * 0.02,
  risk_rank: i + 1,
  risk_percentile: 1 - i / 40,
  risk_band: (i < 4 ? "Very high" : i < 12 ? "High" : i < 24 ? "Medium" : "Low") as "Very high" | "High" | "Medium" | "Low",
  in_top_decile: i < 4,
  above_threshold: i < 20,
  recency_days: 20 + i,
  frequency: 3,
  monetary: 300 + i,
  projected_revenue: 150,
  expected_revenue_at_risk: 100 - i,
});

export function customerList(page = 1, size = 25, filter?: (c: ReturnType<typeof customer>) => boolean): CustomerList {
  const all = Array.from({ length: 40 }, (_, i) => customer(i)).filter(filter ?? (() => true));
  return { meta: { page, page_size: size, total: all.length, pages: Math.max(1, Math.ceil(all.length / size)) }, items: all.slice((page - 1) * size, page * size) };
}

export const customerDetail: CustomerDetail = {
  customer: customer(0),
  features: { recency_days: 20, frequency: 3, monetary: 300, frequency_lifetime: 10, tenure_days: 400, mean_gap_days: null, spend_trend: -0.5, frequency_trend: -1, return_rate: 0 },
  observation_date: "2011-12-10",
  explanation: [
    { feature: "frequency_lifetime", description: "x", feature_value: 1, shap_value: 0.8, rank: 1, explanation: "Lifetime invoices = 1; this raised the predicted inactivity risk." },
    { feature: "recency_days", description: "x", feature_value: 20, shap_value: -0.3, rank: 2, explanation: "Recency = 20; this lowered the predicted inactivity risk." },
  ],
  explanation_available: true,
  note: "Fixture note",
};

const metric = (name: string, split: "validation" | "test", selected: boolean) => ({
  model_name: name, model_version: `${name}-v`, config_index: 0, evaluation_split: split, period_start: "2011-07-01", period_end: "2011-09-01", is_selected: selected, is_family_best: true, params: { C: 0.1 },
  n: 100, positives: 40, positive_rate: 0.4, threshold: 0.4, recall: 0.7, precision: 0.6, f1: 0.646, roc_auc: name === "logistic_regression" ? 0.7123 : 0.70, pr_auc: 0.6, brier: 0.2,
  tp: 28, fp: 18, tn: 42, fn: 12, top_precision: 0.8, top_capture_rate: 0.2, top_lift: 2, extra: {},
});
const fams = ["logistic_regression", "hist_gradient_boosting", "random_forest"];
const line = [{ x: 0, y: 0 }, { x: 0.5, y: 0.7 }, { x: 1, y: 1 }];

export const modelMetrics: ModelMetrics = {
  run_id: run.run_id,
  selected_model: "logistic_regression",
  metrics: fams.flatMap((f) => [metric(f, "validation", f === "logistic_regression"), metric(f, "test", f === "logistic_regression")]),
  curves: fams.flatMap((f) => (["roc", "pr", "calibration"] as const).map((t) => ({ model_name: f, curve_type: t, points: line }))),
};

export const churnMetrics: ChurnMetrics = {
  run_id: run.run_id,
  definition: { rule: "Fixture churn rule", lookback_days: 180, horizon_days: 90, snapshot_frequency: "monthly", disclaimer: "Fixture disclaimer" },
  split: { train: ["2010-06-01"], validation: ["2011-02-01"], test: ["2011-07-01", "2011-08-01"], purged: ["2010-12-01"], horizon_days: 90 },
  class_balance: ["train", "validation", "test"].map((p) => ({ partition: p, rows: 100, customers: 50, snapshots: 1, churn_rate: 0.4, first_cutoff: "2010-06-01", last_cutoff: "2010-06-01" })),
  selection_metric: "validation ROC-AUC",
  threshold_rule: "recall >= 0.75",
  threshold: 0.4,
  selected_family: "logistic_regression",
  selected_params: { C: 0.1 },
  test_per_snapshot: [{ ...metric("logistic_regression", "test", true), cutoff: "2011-07-01" }],
  test_top_fraction: { fraction: 0.1, selected: 10, population: 100, true_churners_selected: 8, precision: 0.8, capture_rate: 0.2, lift: 2, base_rate: 0.4 },
  test_deciles: Array.from({ length: 10 }, (_, i) => ({ decile: i + 1, n: 10, churners: 9 - i, churn_rate: (9 - i) / 10, mean_score: 0.9 - i / 10 })),
  seen_vs_unseen: [{ ...metric("logistic_regression", "test", true), group: "unseen_customers" }],
  horizon_sensitivity: [60, 90, 120].map((h) => ({ horizon_days: h, n_snapshots: 10, n_observations: 1000, mean_churn_rate: 0.5, min_churn_rate: 0.4, max_churn_rate: 0.6 })),
  repeated_customers: { train_rows_per_customer: 2, note: "x" },
};

export const explanations: Explanations = {
  run_id: run.run_id,
  explainer: "LinearExplainer",
  model_family: "logistic_regression",
  output_space: "log_odds",
  base_value: 0,
  additivity_max_abs_error: 1e-15,
  background: { rows: 500, source: "train", seed: 42 },
  caveat: "Fixture caveat: associations, not causes.",
  global: [
    { feature: "frequency_lifetime", rank: 1, description: "Lifetime invoices", mean_abs_shap: 0.7, mean_shap: 0, value_shap_correlation: -0.8, direction: "higher values lower risk" },
    { feature: "mean_gap_days", rank: 2, description: "Gap", mean_abs_shap: 0.3, mean_shap: 0, value_shap_correlation: 0.7, direction: "higher values raise risk" },
  ],
  beeswarm: [{ feature: "frequency_lifetime", shap: 0.2, value_percentile: 0.1 }, { feature: "mean_gap_days", shap: -0.1, value_percentile: null }],
  example_customers: [customer(0).customer_key],
  local: null,
};

export const scenarios: RetentionScenarios = {
  run_id: run.run_id,
  currency: "GBP",
  season_factor: { factor: 0.8, available: true, reference_horizon: ["2010-12-10", "2011-03-10"] },
  projection: { horizon_days: 90, method: "x", daily_rate_cap: 100, capped_customers: 1 },
  cohort: { customers: 1, share_of_scored: 0.25, min_risk: 0.9, mean_risk: 0.9, max_risk: 0.9, projected_revenue: 72, expected_revenue_at_risk: 64.8, all_scored_expected_revenue_at_risk: 1000, segment_mix: [], risk_histogram: [], tie_policy: "x" },
  scenarios: [],
  disclaimer: "Fixture disclaimer: scenario estimates only.",
};

// Same four customers as the backend parity test (tests/test_db_api.py).
export const simulatorData: SimulatorData = {
  run_id: run.run_id,
  currency: "GBP",
  season_factor: 0.8,
  churn_horizon_days: 90,
  columns: ["churn_probability", "daily_revenue_rate", "cluster_id"],
  rows: [
    [0.9, 1.0, 0],
    [0.9, 3.0, 1],
    [0.5, 2.0, 2],
    [0.2, 50.0, 2],
  ],
  segments: { "0": "Fixture Champions", "1": "Fixture At Risk", "2": "Fixture Hibernating" },
  defaults: { base: { effectiveness: 0.1, cost_per_contact: 3 } },
};

export const dataQuality: DataQuality = {
  run_id: run.run_id,
  dataset: { source_name: "Online Retail II", source_url: "x", doi: "https://doi.org/10.24432/C5CG6D", licence: "CC BY 4.0", citation: "Chen, D. (2012). Online Retail II.", zip_sha256: "a".repeat(64), raw_rows: 1000, date_min: "2009-12-01T00:00:00", date_max: "2011-12-09T00:00:00", details: {} },
  validation: { status: "passed", rows: 1000 },
  profile: { raw_rows: 1000 },
  exclusions: [{ reason: "missing_customer_id", rows: 200, share_of_raw: 0.2 }],
  output: { purchase_lines: 800, purchase_invoices: 100, purchase_customers: 60, gross_purchase_value: 10000, return_lines: 10, return_value: 100, uk_share_of_purchase_lines: 0.9 },
  monthly_purchase_value: [{ month: "2011-01-01", value: 100 }],
  features: { scoring_cutoff: "2011-12-10", training_cutoffs: ["2010-06-01", "2011-09-01"], training_rows: 1000, scoring_customers: 40, interpurchase_gap_quantiles: { "0.5": 40, "0.75": 80 }, single_purchase_day_share: 0.3 },
  config: {},
};

export const runs: RunInfo[] = [run];

/** Route table used by both the vitest fetch mock and Playwright route mocks. */
export function respond(url: string): { status: number; body: unknown } {
  const u = new URL(url, "http://localhost");
  const p = u.pathname.replace(/^\/api\/v1/, "");
  const q = u.searchParams;
  if (p === "/summary") return { status: 200, body: summary };
  if (p === "/analysis-runs") return { status: 200, body: runs };
  if (p === "/segments") return { status: 200, body: segments };
  if (p.startsWith("/segments/")) return { status: 200, body: segmentDetail };
  if (p === "/customers") {
    const seg = q.get("segment");
    const band = q.get("risk_band");
    const top = q.get("top_decile");
    return {
      status: 200,
      body: customerList(Number(q.get("page") ?? 1), Number(q.get("page_size") ?? 25), (c) => (seg === null || c.cluster_id === Number(seg)) && (band === null || c.risk_band === band) && (top === null || c.in_top_decile)),
    };
  }
  if (p.startsWith("/customers/")) return { status: 200, body: customerDetail };
  if (p === "/churn/metrics") return { status: 200, body: churnMetrics };
  if (p === "/models/metrics") return { status: 200, body: modelMetrics };
  if (p === "/churn/explanations") {
    const k = q.get("customer_key");
    return { status: 200, body: k ? { ...explanations, local: customerDetail.explanation.map((e) => ({ ...e, customer_key: k })) } : explanations };
  }
  if (p === "/retention/scenarios") return { status: 200, body: scenarios };
  if (p === "/retention/simulator-data") return { status: 200, body: simulatorData };
  if (p === "/data-quality") return { status: 200, body: dataQuality };
  return { status: 404, body: { detail: "Not found" } };
}
