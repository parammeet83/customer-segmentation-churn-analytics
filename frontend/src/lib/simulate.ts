// Client-side retention scenario maths. Mirrors backend
// `customerpulse.analytics.scenario_math.simulate_rows` so the simulator can
// recalculate instantly; the API's /retention/simulate endpoint is the
// reference implementation and a test checks the two agree on fixtures.

export type Ranking = "risk" | "value_at_risk";

export interface Assumptions {
  targetFraction: number; // 0-1
  effectiveness: number; // 0-1, share of expected at-risk revenue retained
  costPerContact: number; // GBP per targeted customer
  horizonDays: number; // revenue projection horizon
  margin: number; // 1 = revenue basis; <1 = gross-margin basis
  ranking: Ranking;
}

export interface RiskRow {
  p: number; // predicted 90-day inactivity probability
  rate: number; // capped daily revenue rate (GBP/day)
  cluster: number;
  order: number; // API risk rank order (tie-break, mirrors key ordering server-side for risk)
}

export interface Outcome {
  targeted: number;
  population: number;
  averageRisk: number;
  projectedRevenue: number;
  revenueAtRisk: number;
  retained: number;
  cost: number;
  net: number;
  breakEvenEffectiveness: number | null;
  segmentMix: Record<number, number>;
}

export const topK = (n: number, fraction: number) => (n === 0 ? 0 : Math.max(1, Math.ceil(Math.round(n * fraction * 1e9) / 1e9)));

export function simulate(rows: RiskRow[], a: Assumptions, season: number): Outcome {
  const ordered =
    a.ranking === "risk"
      ? rows // API delivers rows already in risk-rank order
      : [...rows].sort((x, y) => y.p * y.rate - x.p * x.rate || x.order - y.order);
  const top = ordered.slice(0, topK(rows.length, a.targetFraction));
  let projected = 0;
  let atRisk = 0;
  let riskSum = 0;
  const mix: Record<number, number> = {};
  for (const r of top) {
    const proj = r.rate * a.horizonDays * season;
    projected += proj;
    atRisk += r.p * proj;
    riskSum += r.p;
    mix[r.cluster] = (mix[r.cluster] ?? 0) + 1;
  }
  const retained = atRisk * a.effectiveness;
  const cost = top.length * a.costPerContact;
  return {
    targeted: top.length,
    population: rows.length,
    averageRisk: top.length ? riskSum / top.length : 0,
    projectedRevenue: projected,
    revenueAtRisk: atRisk,
    retained,
    cost,
    net: retained * a.margin - cost,
    breakEvenEffectiveness: atRisk > 0 ? cost / (atRisk * a.margin) : null,
    segmentMix: mix,
  };
}
