"""Unusual days.

1. Per metric: robust z-score (Iglewicz & Hoaglin's modified z): z = 0.6745 (x - median) / MAD.
   |z| > 3.5 = unusual. Median/MAD are not dragged around by the outliers themselves,
   unlike mean/std.
2. Whole day: IsolationForest on the standardised daily feature vector (contamination 2%)
   finds days that are unusual as a COMBINATION, even if no single metric is extreme.
Each unusual day is explained by its 2-3 metrics with the largest robust z.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from .metrics import METRICS, fmt, label, unit

Z_LIMIT = 3.5
CONTAMINATION = 0.02


def robust_z(df: pd.DataFrame) -> pd.DataFrame:
    z = pd.DataFrame(index=df.index)
    for m in METRICS:
        if m not in df.columns:
            continue
        s = df[m].astype(float)
        med = s.median()
        mad = (s - med).abs().median()
        if not np.isfinite(mad) or mad == 0:
            mad = 1.2533 * (s - med).abs().mean() / 0.6745  # fallback for mostly-constant metrics (e.g. many zeros)
        if not np.isfinite(mad) or mad == 0:
            continue
        z[m] = 0.6745 * (s - med) / mad
    return z


def _describe(day: pd.Timestamp, row: pd.Series, zrow: pd.Series, k: int = 3) -> dict:
    top = zrow.dropna().abs().sort_values(ascending=False)
    top = top[top >= 2.0].index[:k].tolist() or zrow.dropna().abs().sort_values(ascending=False).index[:2].tolist()
    parts, dirs = [], []
    for m in top:
        v = row[m]
        dirs.append("above" if zrow[m] > 0 else "below")
        if unit(m) in ("min",):
            parts.append(f"{fmt(m, v)} of {label(m)}")
        elif unit(m) == "inr":
            parts.append(f"{fmt(m, v)} {label(m)}")
        else:
            parts.append(f"{label(m)} {fmt(m, v)}")
    if len(set(dirs)) == 1:
        both = {1: "", 2: "both ", 3: "all "}.get(len(parts), "")
        tail = f", {both}far {dirs[0]} your usual" if parts else ""
        body = " and ".join([", ".join(parts[:-1]), parts[-1]]) if len(parts) > 1 else (parts[0] if parts else "")
    else:
        body = ", ".join(f"{p} ({d} usual)" for p, d in zip(parts, dirs))
        tail = ""
    date_txt = f"{day.day} {day.strftime('%b %Y')}"
    return {"date": day.strftime("%Y-%m-%d"), "metrics": [{"metric": m, "value": None if pd.isna(row[m]) else float(row[m]),
                                                            "z": round(float(zrow[m]), 2)} for m in top],
            "sentence": f"{date_txt}: {body}{tail}."}


def detect(df: pd.DataFrame, top: int = 10) -> dict:
    cols = [m for m in METRICS if m in df.columns and df[m].notna().mean() >= 0.8 and df[m].nunique() > 2]
    if len(df) < 30 or not cols:
        return {"days": [], "per_metric": [], "method": {}}
    z = robust_z(df[cols])
    # per-metric extremes
    per_metric = []
    for m in z.columns:
        hits = z[m][z[m].abs() > Z_LIMIT].sort_values(key=abs, ascending=False).head(3)
        for day, val in hits.items():
            per_metric.append({"date": day.strftime("%Y-%m-%d"), "metric": m, "value": float(df.at[day, m]),
                               "z": round(float(val), 2)})
    per_metric.sort(key=lambda r: -abs(r["z"]))
    # whole-day anomalies
    x = df[cols].astype(float)
    x = x.fillna(x.median())
    xs = (x - x.mean()) / x.std(ddof=0).replace(0, 1)
    forest = IsolationForest(n_estimators=200, contamination=CONTAMINATION, random_state=0).fit(xs)
    score = pd.Series(forest.decision_function(xs), index=df.index)  # lower = more unusual
    flagged = score[forest.predict(xs) == -1].sort_values()
    days = [{**_describe(d, df.loc[d], z.loc[d]), "if_score": round(float(score[d]), 4),
             "robust_z_hits": int((z.loc[d].abs() > Z_LIMIT).sum())} for d in flagged.index[:top]]
    return {"days": days, "per_metric": per_metric[:top * 2],
            "method": {"z_limit": Z_LIMIT, "contamination": CONTAMINATION, "features": cols, "n_days": int(len(df))}}
