"""Trends: weekly and monthly aggregates, 7-day rolling means, weekday x hour heatmaps, and
the time-of-day mood pattern of songs."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency

from .metrics import METRICS, unit


def _agg(m: str) -> str:
    # minutes, money and counts add up over a week; shares and scores are averaged
    return "sum" if unit(m) in ("min", "inr", "count") else "mean"


def aggregates(df: pd.DataFrame) -> dict:
    """df: daily features with a DatetimeIndex. -> weekly / monthly tables + 7-day rolling means."""
    cols = [m for m in METRICS if m in df.columns]
    how = {m: _agg(m) for m in cols}
    # min_count=1: a week with no data stays NULL instead of becoming 0
    weekly = df[cols].resample("W-MON", label="left", closed="left").agg(
        {m: (lambda s, h=h: s.sum(min_count=1) if h == "sum" else s.mean()) for m, h in how.items()})
    monthly = df[cols].resample("MS").agg(
        {m: (lambda s, h=h: s.sum(min_count=1) if h == "sum" else s.mean()) for m, h in how.items()})
    rolling = df[cols].rolling(7, min_periods=4).mean()

    def table(t, freq):
        t = t.round(4).replace({np.nan: None})
        return [{"period": i.strftime(freq), **{k: v for k, v in r.items()}} for i, r in t.iterrows()]

    return {"weekly": table(weekly, "%Y-%m-%d"), "monthly": table(monthly, "%Y-%m"),
            "rolling_7d": table(rolling, "%Y-%m-%d")}


def heatmaps(rows: list[dict]) -> dict:
    """rows: {source, weekday, hour, events} -> {source: 7x24 matrix (Mon..Sun x 0..23)}."""
    out: dict[str, list[list[int]]] = {}
    for r in rows:
        grid = out.setdefault(r["source"], [[0] * 24 for _ in range(7)])
        grid[int(r["weekday"])][int(r["hour"])] += int(r["events"])
    return out


LATE = {23, 0, 1, 2}


def mood_by_hour(rows: list[dict]) -> dict | None:
    """rows: {hour, mood, plays} (known moods only). Is a song played late at night (23:00-02:59)
    more often sad than one played at other hours? Chi-square test on the 2x2 table."""
    if not rows:
        return None
    d = pd.DataFrame(rows)
    late = d["hour"].isin(LATE)
    sad = d["mood"] == "sad"
    a, b = int(d.loc[late & sad, "plays"].sum()), int(d.loc[late & ~sad, "plays"].sum())
    c, e = int(d.loc[~late & sad, "plays"].sum()), int(d.loc[~late & ~sad, "plays"].sum())
    if min(a + b, c + e) < 30:
        return None
    late_share, other_share = a / (a + b), c / (c + e)
    _, p, _, _ = chi2_contingency([[a, b], [c, e]])
    by_hour = (d.assign(sad=sad * d["plays"]).groupby("hour")[["sad", "plays"]].sum())
    return {
        "late_sad_share": round(late_share, 4), "other_sad_share": round(other_share, 4),
        "ratio": round(late_share / other_share, 2) if other_share else None,
        "late_plays": a + b, "other_plays": c + e, "p": float(p),
        "sad_share_by_hour": {int(h): round(r.sad / r.plays, 4) for h, r in by_hour.iterrows() if r.plays},
        "sentence": (f"Songs you play late at night (11pm–3am) are sad {late_share:.0%} of the time, vs "
                     f"{other_share:.0%} at other hours ({late_share / other_share:.1f}x)."
                     if other_share else None),
    }
