import { describe, expect, it } from "vitest";
import { simulate, topK, type Assumptions, type RiskRow } from "./simulate";

// Same customers and expected values as backend
// tests/test_db_api.py::test_pure_simulation_parity_without_db (keys a, b, c, d -> risk order a, b, d, c).
const rows: RiskRow[] = [
  { p: 0.9, rate: 1, cluster: 0, order: 0 },
  { p: 0.9, rate: 3, cluster: 1, order: 1 },
  { p: 0.5, rate: 2, cluster: 2, order: 2 },
  { p: 0.2, rate: 50, cluster: 2, order: 3 },
];
const base: Assumptions = { targetFraction: 0.5, effectiveness: 0.1, costPerContact: 1, horizonDays: 90, margin: 0.5, ranking: "risk" };

describe("topK", () => {
  it("rounds up, with a minimum of one, and is robust to float error", () => {
    expect(topK(100, 0.1)).toBe(10);
    expect(topK(101, 0.1)).toBe(11);
    expect(topK(30, 0.1)).toBe(3);
    expect(topK(5, 0.1)).toBe(1);
    expect(topK(0, 0.1)).toBe(0);
  });
});

describe("simulate", () => {
  it("matches the backend formulas for risk ranking", () => {
    const o = simulate(rows, base, 0.8);
    expect(o.targeted).toBe(2);
    expect(o.revenueAtRisk).toBeCloseTo(259.2, 6);
    expect(o.retained).toBeCloseTo(25.92, 6);
    expect(o.cost).toBe(2);
    expect(o.net).toBeCloseTo(10.96, 6);
    expect(o.breakEvenEffectiveness).toBeCloseTo(2 / (259.2 * 0.5), 9);
  });

  it("matches the backend formulas for value-at-risk ranking", () => {
    const o = simulate(rows, { ...base, ranking: "value_at_risk" }, 0.8);
    expect(o.revenueAtRisk).toBeCloseTo(914.4, 6);
    expect(o.net).toBeCloseTo(43.72, 6);
    expect(o.segmentMix).toEqual({ 1: 1, 2: 1 });
  });

  it("responds to every assumption", () => {
    const o = simulate(rows, base, 1);
    expect(simulate(rows, { ...base, effectiveness: 0.2 }, 1).retained).toBeCloseTo(o.retained * 2);
    expect(simulate(rows, { ...base, costPerContact: 5 }, 1).cost).toBe(10);
    expect(simulate(rows, { ...base, horizonDays: 45 }, 1).revenueAtRisk).toBeCloseTo(o.revenueAtRisk / 2);
    expect(simulate(rows, { ...base, targetFraction: 1 }, 1).targeted).toBe(4);
    expect(simulate(rows, { ...base, margin: 1 }, 1).net).toBeGreaterThan(o.net);
  });

  it("has no break-even when nothing is at risk", () => {
    const o = simulate([{ p: 0, rate: 0, cluster: 0, order: 0 }], base, 1);
    expect(o.breakEvenEffectiveness).toBeNull();
  });
});
