// Response types for the CustomerPulse read-only API (/api/v1).

export interface RunInfo {
  run_id: string;
  status: "running" | "succeeded" | "failed";
  started_at: string;
  finished_at: string | null;
  code_version: string | null;
  selected_k: number | null;
  selected_model: string | null;
  model_version: string | null;
  scoring_cutoff: string | null;
  error_summary: string | null;
}

export interface SegmentProfile {
  cluster_id: number;
  segment_name: string;
  recommended_action: string;
  customers: number;
  share: number;
  revenue: number;
  revenue_share: number;
  levels: { recency: string; frequency: string; monetary: string; is_new: boolean };
  median: Record<string, number>;
  mean: Record<string, number>;
  quartiles: Record<string, number[]>;
  centroid: Record<string, number>;
}

export interface Summary {
  run: RunInfo;
  latest_attempt: RunInfo | null;
  dataset: {
    source_name: string;
    doi: string;
    licence: string;
    citation: string;
    raw_rows: number;
    date_min: string;
    date_max: string;
    purchase_lines: number;
    purchase_customers: number;
  };
  kpis: {
    eligible_customers: number;
    segmented_customers: number;
    segment_count: number;
    churn_rate_test: number;
    churn_rate_overall_snapshots: number;
    selected_model: string;
    test_roc_auc: number;
    test_pr_auc: number;
    test_recall: number;
    top_decile_customers: number;
    top_decile_capture_rate_test: number;
    top_decile_lift_test: number;
    expected_revenue_at_risk_top_decile: number;
    expected_revenue_at_risk_all_scored: number;
    currency: string;
  };
  segments: SegmentProfile[];
  risk_bands: { risk_band: string; customers: number; mean_probability: number; expected_revenue_at_risk: number }[];
  takeaway: string;
}

export interface KRow {
  k: number;
  silhouette: number;
  inertia: number;
  min_cluster_share: number;
  max_cluster_share: number;
  stability_ari: number;
  in_selectable_range: boolean;
  passes_guards: boolean;
  selected: boolean;
}

export interface ScatterPoint {
  cluster_id: number;
  x: number;
  y: number;
  recency_days: number;
  frequency: number;
  monetary: number;
}

export interface SegmentsResponse {
  run_id: string;
  selected_k: number;
  silhouette: number;
  selection_rule: string;
  transform: string;
  population: string;
  k_table: KRow[];
  pca_explained_variance: number[];
  profiles: SegmentProfile[];
  scatter: ScatterPoint[];
  population_quantiles: Record<string, Record<string, number>>;
}

export interface Bin {
  bin_start: number;
  bin_end: number;
  customers: number;
}

export interface SegmentDetail {
  profile: SegmentProfile;
  distributions: Record<"recency_days" | "frequency" | "monetary", Bin[]>;
  scored_customers: number;
  mean_churn_probability: number | null;
  top_decile_customers: number;
}

export interface CustomerRow {
  customer_key: string;
  cluster_id: number;
  segment_name: string;
  churn_probability: number;
  risk_rank: number;
  risk_percentile: number;
  risk_band: "Very high" | "High" | "Medium" | "Low";
  in_top_decile: boolean;
  above_threshold: boolean;
  recency_days: number;
  frequency: number;
  monetary: number;
  projected_revenue: number;
  expected_revenue_at_risk: number;
}

export interface CustomerList {
  meta: { page: number; page_size: number; total: number; pages: number };
  items: CustomerRow[];
}

export interface Contribution {
  feature: string;
  description?: string;
  feature_value: number | null;
  shap_value: number;
  rank: number;
  explanation: string;
}

export interface CustomerDetail {
  customer: CustomerRow;
  features: Record<string, number | null>;
  observation_date: string;
  explanation: Contribution[];
  explanation_available: boolean;
  note: string;
}

export interface ClassificationMetrics {
  n: number;
  positives: number;
  positive_rate: number;
  threshold: number;
  recall: number;
  precision: number;
  f1: number;
  roc_auc: number;
  pr_auc: number;
  brier: number;
  tp: number;
  fp: number;
  tn: number;
  fn: number;
  top_precision: number;
  top_capture_rate: number;
  top_lift: number;
}

export interface ChurnMetrics {
  run_id: string;
  definition: { rule: string; lookback_days: number; horizon_days: number; snapshot_frequency: string; disclaimer: string };
  split: { train: string[]; validation: string[]; test: string[]; purged: string[]; horizon_days: number };
  class_balance: { partition: string; rows: number; customers: number; snapshots: number; churn_rate: number; first_cutoff: string; last_cutoff: string }[];
  selection_metric: string;
  threshold_rule: string;
  threshold: number;
  selected_family: string;
  selected_params: Record<string, unknown>;
  test_per_snapshot: (ClassificationMetrics & { cutoff: string })[];
  test_top_fraction: {
    fraction: number;
    selected: number;
    population: number;
    true_churners_selected: number;
    precision: number;
    capture_rate: number;
    lift: number;
    base_rate: number;
  };
  test_deciles: { decile: number; n: number; churners: number; churn_rate: number; mean_score: number }[];
  seen_vs_unseen: (ClassificationMetrics & { group: string })[];
  horizon_sensitivity: {
    horizon_days: number;
    n_snapshots: number;
    n_observations: number;
    mean_churn_rate: number;
    min_churn_rate: number;
    max_churn_rate: number;
  }[];
  repeated_customers: { train_rows_per_customer: number; note: string };
}

export interface ModelMetricRow extends ClassificationMetrics {
  model_name: string;
  model_version: string;
  config_index: number;
  evaluation_split: "validation" | "test";
  period_start: string;
  period_end: string;
  is_selected: boolean;
  is_family_best: boolean;
  params: Record<string, unknown>;
  extra: Record<string, unknown>;
}

export interface ModelMetrics {
  run_id: string;
  selected_model: string;
  metrics: ModelMetricRow[];
  curves: { model_name: string; curve_type: "roc" | "pr" | "calibration"; points: { x: number; y: number }[] }[];
}

export interface ShapGlobalRow {
  feature: string;
  rank: number;
  description: string;
  mean_abs_shap: number;
  mean_shap: number;
  value_shap_correlation: number;
  direction: string;
}

export interface Explanations {
  run_id: string;
  explainer: string;
  model_family: string;
  output_space: string;
  base_value: number;
  additivity_max_abs_error: number;
  background: { rows: number; source: string; seed: number };
  caveat: string;
  global: ShapGlobalRow[];
  beeswarm: { feature: string; shap: number; value_percentile: number | null }[];
  example_customers: string[];
  local: (Contribution & { customer_key: string })[] | null;
}

export interface ScenarioResult {
  assumptions: {
    target_fraction: number;
    effectiveness: number;
    cost_per_contact: number;
    horizon_days: number;
    margin: number;
    ranking: "risk" | "value_at_risk";
  };
  targeted_customers: number;
  population: number;
  average_risk: number;
  projected_revenue: number;
  expected_revenue_at_risk: number;
  scenario_revenue_retained: number;
  campaign_cost: number;
  net_impact: number;
  net_impact_basis: string;
  break_even_effectiveness: number | null;
  label: string;
}

export interface RetentionScenarios {
  run_id: string;
  currency: string;
  season_factor: { factor: number; available: boolean; reference_lookback?: string[]; reference_horizon?: string[] };
  projection: { horizon_days: number; method: string; daily_rate_cap: number; capped_customers: number };
  cohort: {
    customers: number;
    share_of_scored: number;
    min_risk: number;
    mean_risk: number;
    max_risk: number;
    projected_revenue: number;
    expected_revenue_at_risk: number;
    all_scored_expected_revenue_at_risk: number;
    segment_mix: { cluster_id: number; segment_name: string; customers: number }[];
    risk_histogram: { bin_start: number; customers: number }[];
    tie_policy: string;
  };
  scenarios: { name: string; assumptions: ScenarioResult["assumptions"]; results: Omit<ScenarioResult, "assumptions"> }[];
  disclaimer: string;
}

export interface SimulatorData {
  run_id: string;
  currency: string;
  season_factor: number;
  churn_horizon_days: number;
  columns: ["churn_probability", "daily_revenue_rate", "cluster_id"];
  rows: [number, number, number][];
  segments: Record<string, string>;
  defaults: Record<string, { effectiveness: number; cost_per_contact: number }>;
}

export interface DataQuality {
  run_id: string;
  dataset: {
    source_name: string;
    source_url: string;
    doi: string;
    licence: string;
    citation: string;
    zip_sha256: string;
    raw_rows: number;
    date_min: string;
    date_max: string;
    details: { sheets?: Record<string, { rows: number; date_min: string; date_max: string }> };
  };
  validation: { status: string; rows: number; distinct_customers?: number; countries?: number };
  profile: Record<string, number>;
  exclusions: { reason: string; rows: number; share_of_raw: number }[];
  output: Record<string, number | string>;
  monthly_purchase_value: { month: string; value: number }[];
  features: {
    scoring_cutoff: string;
    training_cutoffs: string[];
    training_rows: number;
    scoring_customers: number;
    interpurchase_gap_quantiles: Record<string, number>;
    single_purchase_day_share: number;
  };
  config: Record<string, unknown>;
}
