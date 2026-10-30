import { describe, expect, it } from "vitest";
import { clusterColor, compactMoney, money, pct, prettyModel } from "./format";

describe("format", () => {
  it("formats money and percentages", () => {
    expect(money(1234.5)).toBe("£1,235");
    expect(money(3, true)).toBe("£3.00");
    expect(compactMoney(81035)).toBe("£81.0k");
    expect(compactMoney(2_500_000)).toBe("£2.50m");
    expect(pct(0.1823)).toBe("18.2%");
  });

  it("keeps colour attached to the cluster id, not its rank", () => {
    expect(clusterColor(0)).toBe("#e0585e");
    expect(clusterColor(4)).toBe(clusterColor(0));
  });

  it("names models", () => {
    expect(prettyModel("logistic_regression")).toBe("Logistic regression");
    expect(prettyModel("other")).toBe("other");
  });
});
