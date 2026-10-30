"""Static report figures in the CustomerPulse navy/gold theme.

Figures are generated from pipeline outputs only and are written to
``reports/figures`` for the README and methodology docs.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

NAVY = "#0b1a33"
PANEL = "#10244a"
GRID = "#1d3a6e"
TEXT = "#e8eefc"
MUTED = "#8ea3c7"
GOLD = "#f5c542"
RED = "#ef6b6b"
TEAL = "#3fd0c0"
BLUE = "#7f9cff"
CLUSTER_COLORS = [RED, GOLD, TEAL, BLUE, "#c38bff", "#ff9f5a", "#9be27a", "#f78fb3"]


def _style(ax, title: str, xlabel: str = "", ylabel: str = "") -> None:
    ax.set_facecolor(PANEL)
    ax.set_title(title, color=TEXT, fontsize=13, fontweight="bold", loc="left", pad=12)
    ax.set_xlabel(xlabel, color=MUTED)
    ax.set_ylabel(ylabel, color=MUTED)
    ax.tick_params(colors=MUTED)
    ax.grid(color=GRID, linewidth=0.6)
    for s in ax.spines.values():
        s.set_color(GRID)


def _fig(w: float = 8, h: float = 5):
    fig, ax = plt.subplots(figsize=(w, h), dpi=130)
    fig.patch.set_facecolor(NAVY)
    return fig, ax


def _save(fig, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, facecolor=fig.get_facecolor())
    plt.close(fig)


def silhouette_plot(k_table: list[dict], path: Path) -> None:
    fig, ax = _fig()
    ks = [r["k"] for r in k_table]
    sil = [r["silhouette"] for r in k_table]
    ax.plot(ks, sil, color=TEAL, marker="o", linewidth=2)
    sel = next(r for r in k_table if r.get("selected"))
    ax.scatter([sel["k"]], [sel["silhouette"]], s=180, color=GOLD, zorder=5, label=f"Selected K={sel['k']}")
    ax.legend(facecolor=PANEL, edgecolor=GRID, labelcolor=TEXT)
    _style(ax, "Silhouette score by K (log-scaled RFM)", "K (number of clusters)", "Silhouette score")
    _save(fig, path)


def segment_scatter(
    pca: np.ndarray, labels: np.ndarray, names: dict[int, str], variance: list[float], path: Path, seed: int
) -> None:
    fig, ax = _fig(8, 5.5)
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(pca), size=min(2500, len(pca)), replace=False)
    for c in sorted(names):
        m = labels[idx] == c
        ax.scatter(
            pca[idx][m, 0],
            pca[idx][m, 1],
            s=9,
            alpha=0.7,
            color=CLUSTER_COLORS[c % len(CLUSTER_COLORS)],
            label=names[c],
        )
    ax.legend(facecolor=PANEL, edgecolor=GRID, labelcolor=TEXT, markerscale=2, fontsize=9)
    _style(
        ax,
        "Customer segments (K-Means on scaled RFM)",
        f"Projection axis 1 (PCA, {variance[0]:.0%} of variance)",
        f"Projection axis 2 (PCA, {variance[1]:.0%} of variance)",
    )
    _save(fig, path)


def roc_pr_plot(test_curves: dict, selected: str, path: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), dpi=130)
    fig.patch.set_facecolor(NAVY)
    colors = {"logistic_regression": GOLD, "random_forest": RED, "hist_gradient_boosting": TEAL}
    for fam, c in test_curves.items():
        lw = 2.6 if fam == selected else 1.4
        for ax, key in ((axes[0], "roc"), (axes[1], "pr")):
            pts = c[key]
            ax.plot(
                [p["x"] for p in pts],
                [p["y"] for p in pts],
                color=colors.get(fam, BLUE),
                lw=lw,
                label=fam.replace("_", " "),
            )
    axes[0].plot([0, 1], [0, 1], color=MUTED, ls="--", lw=1)
    _style(axes[0], "ROC curve - held-out test", "False positive rate", "True positive rate")
    _style(axes[1], "Precision-recall - held-out test", "Recall", "Precision")
    for ax in axes:
        ax.legend(facecolor=PANEL, edgecolor=GRID, labelcolor=TEXT, fontsize=8)
    _save(fig, path)


def shap_bar(global_rows: list[dict], path: Path, top: int = 12) -> None:
    rows = global_rows[:top][::-1]
    fig, ax = _fig(8, 5.5)
    colors = [RED if "raise" in r["direction"] else TEAL if "lower" in r["direction"] else GOLD for r in rows]
    ax.barh([r["feature"] for r in rows], [r["mean_abs_shap"] for r in rows], color=colors)
    _style(ax, "Global churn drivers (mean |SHAP|, log-odds)", "Mean absolute SHAP value", "")
    _save(fig, path)


def decile_plot(deciles: list[dict], path: Path) -> None:
    fig, ax = _fig()
    xs = [d["decile"] for d in deciles]
    ax.bar(xs, [d["churn_rate"] for d in deciles], color=[GOLD if d["decile"] == 1 else BLUE for d in deciles])
    base = sum(d["churners"] for d in deciles) / sum(d["n"] for d in deciles)
    ax.axhline(base, color=RED, ls="--", lw=1.4, label=f"Overall churn rate {base:.0%}")
    ax.legend(facecolor=PANEL, edgecolor=GRID, labelcolor=TEXT)
    ax.set_xticks(xs)
    _style(
        ax,
        "Observed churn rate by predicted-risk decile (test)",
        "Risk decile (1 = highest risk)",
        "Observed churn rate",
    )
    _save(fig, path)
