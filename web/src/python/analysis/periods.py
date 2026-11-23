"""Tagged periods ("Exams", "Trip", …) and weekends: every metric inside vs outside.

For each label, days inside any of its ranges are compared with the other days of the
analysis window using the Mann-Whitney U test (no assumption of normal data), with a
Benjamini–Hochberg correction over all metric x period tests. Reported: means inside /
outside, % change, rank-biserial effect size, adjusted p. See docs/analysis.md.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import false_discovery_control, mannwhitneyu

from .metrics import METRICS, fmt, label, source_of, strength, subject, unit

MIN_DAYS = 5
FDR = 0.05
WEEKENDS = "Weekends"


def _masks(df: pd.DataFrame, periods: list[dict]) -> dict[str, pd.Series]:
    out: dict[str, pd.Series] = {}
    for p in periods:
        inside = (df.index >= pd.Timestamp(p["start_date"])) & (df.index <= pd.Timestamp(p["end_date"]))
        out[p["label"]] = out.get(p["label"], pd.Series(False, index=df.index)) | inside
    if "is_weekend" in df.columns:
        out[WEEKENDS] = df["is_weekend"].fillna(False).astype(bool)
    return {k: v for k, v in out.items() if v.sum() >= MIN_DAYS and (~v).sum() >= MIN_DAYS}


def compare(df: pd.DataFrame, periods: list[dict]) -> list[dict]:
    """-> one result per (period label, metric), sorted by label then effect size."""
    rows = []
    for name, inside in _masks(df, periods).items():
        for m in METRICS:
            if m not in df.columns:
                continue
            a, b = df.loc[inside, m].dropna(), df.loc[~inside, m].dropna()
            if len(a) < MIN_DAYS or len(b) < MIN_DAYS or (a.nunique() < 2 and b.nunique() < 2):
                continue
            u, p = mannwhitneyu(a, b, alternative="two-sided")
            effect = 1 - 2 * u / (len(a) * len(b))   # rank-biserial: >0 means lower inside
            effect = -effect                          # flip: >0 means higher inside
            rows.append({"period": name, "metric": m, "source": source_of(m), "n_in": int(len(a)),
                         "n_out": int(len(b)), "mean_in": float(a.mean()), "mean_out": float(b.mean()),
                         "effect": float(effect), "p": float(p)})
    if not rows:
        return []
    t = pd.DataFrame(rows)
    t["q"] = false_discovery_control(t["p"].to_numpy(), method="bh")
    out = []
    for r in t.itertuples():
        diff = r.mean_in - r.mean_out
        pct = (diff / r.mean_out) if r.mean_out not in (0, 0.0) else None
        up = diff > 0
        if unit(r.metric) in ("share", "score"):
            change = (f"{abs(diff) * 100:.0f} points {'higher' if up else 'lower'}" if unit(r.metric) == "share"
                      else f"{'higher' if up else 'lower'} ({fmt(r.metric, r.mean_in)} vs {fmt(r.metric, r.mean_out)})")
        else:
            change = (f"{abs(pct):.0%} {'higher' if up else 'lower'}" if pct is not None and np.isfinite(pct)
                      else ("higher" if up else "lower"))
        where = "on weekends" if r.period == WEEKENDS else f"during {r.period}"
        sig = r.q < FDR
        out.append({
            "period": r.period, "metric": r.metric, "source": r.source, "label": label(r.metric),
            "n_in": r.n_in, "n_out": r.n_out, "mean_in": round(r.mean_in, 4), "mean_out": round(r.mean_out, 4),
            "pct_change": round(float(pct), 4) if pct is not None and np.isfinite(pct) else None,
            "direction": "up" if up else "down", "effect": round(r.effect, 3), "strength": strength(r.effect),
            "p": r.p, "q": float(r.q), "significant": bool(sig),
            "sentence": (f"{where[0].upper() + where[1:]}, {subject(r.metric)} is {change}"
                         + (f" ({fmt(r.metric, r.mean_in)} vs {fmt(r.metric, r.mean_out)} a day)."
                            if unit(r.metric) not in ("share", "score") else
                            f" ({fmt(r.metric, r.mean_in)} vs {fmt(r.metric, r.mean_out)})."
                            if unit(r.metric) == "share" else ".")),
        })
    out.sort(key=lambda r: (r["period"] == WEEKENDS, r["period"], not r["significant"], -abs(r["effect"])))
    return out
