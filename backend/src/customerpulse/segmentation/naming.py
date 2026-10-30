"""Rule-based business names for K-Means clusters.

Each cluster's median recency, frequency, monetary value and tenure are
compared with population tertiles (quartile/median for tenure). The resulting
levels feed an ordered rule list; the first rule that matches names the
cluster. A cluster that matches no rule gets a neutral descriptive name, so
a label is only used when the profile actually supports it.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

ACTIONS: dict[str, str] = {
    "Champions": "Protect and reward: early access, loyalty perks and referral asks. Avoid discount-led contact that erodes margin.",
    "Loyal Customers": "Deepen the relationship with cross-sell bundles and replenishment reminders timed to their usual purchase gap.",
    "New Customers": "Onboard: a second-purchase incentive and product discovery within their first 60 days.",
    "Promising Customers": "Nurture toward a repeat cadence with personalised recommendations and modest incentives.",
    "At Risk": "Prioritise win-back: high historical value but purchases have slowed. Contact personally before the gap widens further.",
    "Needs Attention": "Re-engage with targeted reminders and time-limited offers based on past categories.",
    "Hibernating Customers": "Low-cost reactivation only (email). Do not spend heavily: low frequency and long inactivity.",
}
NEUTRAL_ACTION = "Profile does not match a standard RFM archetype; review before assigning a campaign."


@dataclass(frozen=True)
class Levels:
    recency: str  # recent | lapsing | lapsed
    frequency: str  # low | mid | high
    monetary: str  # low | mid | high
    is_new: bool
    established: bool = False  # tenure at or above the population median


def _tertile_level(value: float, q33: float, q67: float) -> str:
    if value >= q67:
        return "high"
    if value <= q33:
        return "low"
    return "mid"


def cluster_levels(cluster: pd.Series, population: pd.DataFrame) -> Levels:
    r33, r67 = population["recency_days"].quantile([1 / 3, 2 / 3])
    if cluster["recency_days"] <= r33:
        recency = "recent"
    elif cluster["recency_days"] <= r67:
        recency = "lapsing"
    else:
        recency = "lapsed"
    f33, f67 = population["frequency"].quantile([1 / 3, 2 / 3])
    m33, m67 = population["monetary"].quantile([1 / 3, 2 / 3])
    t25, t50 = population["tenure_days"].quantile([0.25, 0.5])
    freq = _tertile_level(cluster["frequency"], f33, f67)
    mon = _tertile_level(cluster["monetary"], m33, m67)
    return Levels(
        recency,
        freq,
        mon,
        is_new=bool(cluster["tenure_days"] <= t25 and freq == "low"),
        established=bool(cluster["tenure_days"] >= t50),
    )


def name_from_levels(lv: Levels) -> str:
    r, f, m = lv.recency, lv.frequency, lv.monetary
    if r == "recent" and f == "high" and m == "high":
        return "Champions"
    # Loyalty needs a sustained relationship, not just one recent order.
    if r == "recent" and m != "low" and (f == "high" or (f == "mid" and lv.established)):
        return "Loyal Customers"
    if r == "recent" and lv.is_new:
        return "New Customers"
    if r == "recent":
        return "Promising Customers"
    if r != "recent" and (f == "high" or m == "high"):
        return "At Risk"
    if r == "lapsing":
        return "Needs Attention"
    if r == "lapsed" and f == "low":
        return "Hibernating Customers"
    return f"{r.capitalize()}, {f}-frequency, {m}-spend customers"


def name_clusters(profiles: pd.DataFrame, population: pd.DataFrame) -> pd.DataFrame:
    """Add ``segment_name``, level columns and ``recommended_action``.

    ``profiles`` is indexed by cluster id and holds median recency_days,
    frequency, monetary and tenure_days. Duplicate names are disambiguated by
    spend so every cluster's name is unique.
    """
    out = profiles.copy()
    levels = {cid: cluster_levels(row, population) for cid, row in profiles.iterrows()}
    out["recency_level"] = [levels[c].recency for c in out.index]
    out["frequency_level"] = [levels[c].frequency for c in out.index]
    out["monetary_level"] = [levels[c].monetary for c in out.index]
    out["is_new"] = [levels[c].is_new for c in out.index]
    out["base_name"] = [name_from_levels(levels[c]) for c in out.index]
    out["recommended_action"] = out["base_name"].map(ACTIONS).fillna(NEUTRAL_ACTION)

    names = out["base_name"].copy()
    for base, grp in out.groupby("base_name"):
        if len(grp) == 1:
            continue
        ordered = grp.sort_values("monetary", ascending=False).index
        suffixes = (
            ["higher spend", "lower spend"]
            if len(ordered) == 2
            else [f"spend tier {i + 1}" for i in range(len(ordered))]
        )
        for cid, suf in zip(ordered, suffixes, strict=True):
            names[cid] = f"{base} ({suf})"
    out["segment_name"] = names
    return out
