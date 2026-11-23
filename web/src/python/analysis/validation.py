"""Null test for the correlation engine: shuffle the dates of ONE source (which breaks any
real link between that source and the others, but keeps its own values and distribution),
re-run the cross-source tests, and count how many findings involving that source still
"survive". Every one of them is a false positive. See docs/analysis.md."""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import correlations
from .metrics import METRICS


def shuffle_source(df: pd.DataFrame, source: str, seed: int) -> pd.DataFrame:
    cols = [m for m, meta in METRICS.items() if meta.source == source and m in df.columns]
    out = df.copy()
    perm = np.random.default_rng(seed).permutation(len(df))
    out[cols] = df[cols].to_numpy()[perm]  # the whole day of that source moves together
    return out


def null_test(df: pd.DataFrame, sources: list[str], seeds: range) -> list[dict]:
    runs = []
    for source in sources:
        for seed in seeds:
            ins, summary, weak = correlations.insights(shuffle_source(df, source, seed))
            runs.append({"source": source, "seed": seed, "tests": summary["tests"],
                         "false_insights": correlations.count_involving(ins, source),
                         "false_weak_signals": correlations.count_involving(weak, source)})
    return runs
