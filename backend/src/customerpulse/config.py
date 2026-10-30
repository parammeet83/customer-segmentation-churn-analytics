"""Central configuration for the CustomerPulse analysis pipeline.

All analytical assumptions (windows, seeds, candidate K values, scenario
defaults) live here so that a run is fully described by this module plus the
dataset checksum. Values are recorded in each analysis run's metadata.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"
ARTIFACTS_DIR = REPO_ROOT / "artifacts"
REPORTS_DIR = REPO_ROOT / "reports"

RANDOM_SEED = 42


@dataclass(frozen=True)
class DatasetSource:
    """The single permitted data source. Download URLs are never user-supplied."""

    name: str = "Online Retail II"
    url: str = "https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip"
    landing_page: str = "https://archive.ics.uci.edu/dataset/502/online+retail+ii"
    doi: str = "https://doi.org/10.24432/C5CG6D"
    licence: str = "CC BY 4.0"
    citation: str = (
        "Chen, D. (2012). Online Retail II [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C5CG6D"
    )
    zip_filename: str = "online_retail_ii.zip"
    xlsx_filename: str = "online_retail_II.xlsx"
    # SHA-256 of the archive downloaded from UCI on 2026-10-30. A mismatch is
    # reported (the source may have been re-packaged) but never silently ignored.
    expected_zip_sha256: str = "572e36277c2390fbfde10664750731e0a86f55e33470d91919085f0408e67bfb"
    sheets: tuple[str, ...] = ("Year 2009-2010", "Year 2010-2011")


@dataclass(frozen=True)
class ChurnConfig:
    """Behavioural inactivity definition and temporal evaluation design."""

    lookback_days: int = 180
    horizon_days: int = 90
    candidate_horizons: tuple[int, ...] = (60, 90, 120)
    # Monthly observation dates (first day of month, 00:00). Features use
    # transactions strictly before the cutoff; labels use [cutoff, cutoff+H).
    first_snapshot: str = "2010-06-01"
    n_test_snapshots: int = 3
    n_val_snapshots: int = 3
    # Fraction of the population treated as the "top decile" retention cohort.
    top_fraction: float = 0.10
    # Operating threshold: the highest validation threshold that still reaches
    # this recall. (Maximising F-beta degenerates to "flag everyone" when the
    # churn rate is close to 50%, so a recall target is used instead.)
    target_recall: float = 0.75


@dataclass(frozen=True)
class SegmentationConfig:
    k_min: int = 2
    k_max: int = 10
    # K values eligible for selection; K=2 is reported but is too coarse to
    # support differentiated retention actions.
    selectable_k_min: int = 3
    selectable_k_max: int = 8
    min_cluster_share: float = 0.03
    min_stability_ari: float = 0.75
    n_init: int = 20
    silhouette_sample_size: int = 10_000
    stability_bootstrap_rounds: int = 10
    stability_sample_fraction: float = 0.8


@dataclass(frozen=True)
class RetentionConfig:
    """Scenario assumptions. These are illustrative inputs, not observed outcomes."""

    currency: str = "GBP"
    projection_horizon_days: int = 90
    projection_cap_quantile: float = 0.995
    scenarios: dict[str, dict[str, float]] = field(
        default_factory=lambda: {
            "conservative": {"effectiveness": 0.05, "cost_per_contact": 5.0},
            "base": {"effectiveness": 0.10, "cost_per_contact": 3.0},
            "optimistic": {"effectiveness": 0.20, "cost_per_contact": 2.0},
        }
    )


@dataclass(frozen=True)
class PipelineConfig:
    dataset: DatasetSource = field(default_factory=DatasetSource)
    churn: ChurnConfig = field(default_factory=ChurnConfig)
    segmentation: SegmentationConfig = field(default_factory=SegmentationConfig)
    retention: RetentionConfig = field(default_factory=RetentionConfig)
    random_seed: int = RANDOM_SEED
    feature_version: str = "fv1"

    def to_dict(self) -> dict:
        return asdict(self)


DEFAULT_CONFIG = PipelineConfig()
