"""Chronological train / validation / test partitions with a purge gap.

A snapshot at cutoff ``c`` has a label window ``[c, c + H)``. To prevent a
training label from observing the period a later partition is evaluated on,
every snapshot in an earlier partition must satisfy
``c + H <= first cutoff of the next partition``. Snapshots that violate this
are purged (dropped) rather than moved.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

DAY = pd.Timedelta(days=1)


@dataclass(frozen=True)
class TemporalSplit:
    train: list[pd.Timestamp]
    validation: list[pd.Timestamp]
    test: list[pd.Timestamp]
    purged: list[pd.Timestamp]
    horizon_days: int

    def partition_of(self, cutoff: pd.Timestamp) -> str | None:
        for name in ("train", "validation", "test"):
            if cutoff in getattr(self, name):
                return name
        return None

    def to_dict(self) -> dict:
        def fmt(xs: list[pd.Timestamp]) -> list[str]:
            return [str(x.date()) for x in xs]

        return {
            "train": fmt(self.train),
            "validation": fmt(self.validation),
            "test": fmt(self.test),
            "purged": fmt(self.purged),
            "horizon_days": self.horizon_days,
        }


def temporal_split(cutoffs: list[pd.Timestamp], n_test: int, n_val: int, horizon_days: int) -> TemporalSplit:
    cs = sorted(pd.Timestamp(c) for c in cutoffs)
    if len(cs) < n_test + n_val + 1:
        raise ValueError("Not enough snapshots for the requested partitions")
    h = horizon_days * DAY
    test = cs[-n_test:]
    remaining = cs[:-n_test]
    val_pool = [c for c in remaining if c + h <= test[0]]
    purged = [c for c in remaining if c + h > test[0]]
    if len(val_pool) < n_val + 1:
        raise ValueError("Not enough snapshots before the test purge gap")
    validation = val_pool[-n_val:]
    train_pool = val_pool[:-n_val]
    train = [c for c in train_pool if c + h <= validation[0]]
    purged += [c for c in train_pool if c + h > validation[0]]
    if not train:
        raise ValueError("No training snapshots remain after purging")
    split = TemporalSplit(train, validation, test, sorted(purged), horizon_days)
    assert_no_label_overlap(split)
    return split


def assert_no_label_overlap(split: TemporalSplit) -> None:
    """Raise if any label window crosses into a later partition."""
    h = split.horizon_days * DAY
    if max(split.train) + h > min(split.validation):
        raise AssertionError("Training label windows overlap the validation period")
    if max(split.validation) + h > min(split.test):
        raise AssertionError("Validation label windows overlap the test period")
