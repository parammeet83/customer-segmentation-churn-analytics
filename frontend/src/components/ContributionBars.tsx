import { num, prettyFeature } from "../lib/format";
import type { Contribution } from "../lib/types";

/**
 * Diverging bars for one customer's SHAP contributions: red raises predicted
 * inactivity risk, teal lowers it. Direction is also stated in words so the
 * meaning never depends on colour alone.
 */
export function ContributionBars({ items }: { items: Contribution[] }) {
  const max = Math.max(...items.map((i) => Math.abs(i.shap_value)), 1e-9);
  return (
    <ul className="space-y-2.5" aria-label="Feature contributions">
      {items.map((it) => {
        const up = it.shap_value > 0;
        const w = `${(Math.abs(it.shap_value) / max) * 50}%`;
        return (
          <li key={it.feature} title={it.explanation}>
            <div className="flex items-baseline justify-between gap-2 text-sm">
              <span className="text-ink">{prettyFeature(it.feature)}</span>
              <span className="tabular text-xs text-ink-3">
                value {it.feature_value === null ? "n/a" : num(it.feature_value, 2)} · {up ? "raises" : "lowers"} risk {up ? "+" : "−"}
                {num(Math.abs(it.shap_value), 3)}
              </span>
            </div>
            <div className="relative mt-1 h-2.5 rounded-full bg-navy-800" aria-hidden="true">
              <span className="absolute top-0 left-1/2 h-full w-px bg-ink-3/60" />
              <span
                className="absolute top-0 h-full rounded-full"
                style={{ width: w, left: up ? "50%" : undefined, right: up ? undefined : "50%", backgroundColor: up ? "#e0585e" : "#169c8f" }}
              />
            </div>
          </li>
        );
      })}
    </ul>
  );
}
