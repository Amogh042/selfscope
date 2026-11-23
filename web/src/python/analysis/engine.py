"""Run the whole analysis for one date range and return JSON for the app (and the cache).

Input (JSON): {range: {from, to}, overlap: {start_date, end_date}, features: [daily_features
rows], periods: [{label, start_date, end_date}], mood_by_hour: [...], heatmap: [...]}.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from . import ENGINE_VERSION
from . import anomalies, calendar_control, correlations, periods, trends
from .metrics import METRICS


def frame(features: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(features)
    if df.empty:
        return df
    df["local_date"] = pd.to_datetime(df["local_date"])
    df = df.set_index("local_date").sort_index()
    df = df.asfreq("D")  # every calendar day present, so shift(n) = n days
    for c in df.columns:
        if c != "is_weekend":
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def window(df: pd.DataFrame, start: str | None, end: str | None) -> pd.DataFrame:
    if start:
        df = df[df.index >= pd.Timestamp(start)]
    if end:
        df = df[df.index <= pd.Timestamp(end)]
    return df


def run(payload: dict) -> dict:
    df = frame(payload.get("features") or [])
    rng = payload.get("range") or {}
    ov = payload.get("overlap") or {}
    in_range = window(df, rng.get("from"), rng.get("to")) if not df.empty else df
    # correlations only where every source has data: overlap ∩ selected range
    starts = [s for s in (rng.get("from"), ov.get("start_date")) if s]
    ends = [e for e in (rng.get("to"), ov.get("end_date")) if e]
    corr_from, corr_to = (max(starts) if starts else None), (min(ends) if ends else None)
    overlap_ok = bool(ov.get("start_date")) and (corr_from is None or corr_to is None or corr_from <= corr_to)
    corr_df = window(df, corr_from, corr_to) if overlap_ok and not df.empty else df.iloc[0:0]

    tagged = payload.get("periods") or []
    if len(corr_df):
        tests = correlations.run_tests(corr_df)
        ins, summary, weak = correlations.insights(corr_df, tests=tests)
        controlled, tests_c = calendar_control.control(corr_df, tagged, ins, weak)
        corr_matrix = correlations.matrix(tests, tests_c)
    else:
        ins, summary, weak = [], {"tests": 0, "significant": 0, "weak_signals": 0}, []
        controlled = {"insights": [], "weak_signals": [], "tests": 0, "controls": []}
        corr_matrix = {"metrics": [], "cells": []}
    out = {
        "engine_version": ENGINE_VERSION,
        "range": {"from": rng.get("from"), "to": rng.get("to"), "days": int(len(in_range))},
        "correlation_window": {"from": corr_from, "to": corr_to, "days": int(len(corr_df)),
                               "reason": None if overlap_ok else "the sources do not overlap in time"},
        "insights": ins,
        "weak_signals": weak,
        "tests": summary,
        "calendar_controlled": controlled,
        "matrix": corr_matrix,
        "metrics": {m: {"source": v.source, "label": v.short, "unit": v.unit} for m, v in METRICS.items()},
        "song_mood_by_hour": trends.mood_by_hour(payload.get("mood_by_hour") or []),
        "periods": periods.compare(in_range, tagged) if len(in_range) else [],
        "anomalies": anomalies.detect(in_range) if len(in_range) else {"days": [], "per_metric": []},
        "trends": {**(trends.aggregates(in_range) if len(in_range) else {}),
                   "heatmaps": trends.heatmaps(payload.get("heatmap") or [])},
    }
    return out


def _clean(o):
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def run_json(payload_json: str) -> str:
    return json.dumps(_clean(run(json.loads(payload_json))), ensure_ascii=False)
