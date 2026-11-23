"""Cross-app correlations with honest statistics.

For every pair of daily metrics from DIFFERENT sources (e.g. YouTube x bank), inside the
analysis window (overlap of all sources ∩ the selected date range):
  - Spearman rank correlation at lags 0, 1 and 2 days ("X today vs Y on the same day /
    the next day / two days later"), both directions for lags > 0;
  - only tests with at least MIN_DAYS days where both values exist;
  - Benjamini–Hochberg correction over ALL tests run (false discovery rate FDR);
  - INSIGHTS: pairs with adjusted p (q) < FDR and |rho| >= MIN_RHO; per pair, the strongest lag;
  - WEAKER SIGNALS: also q < FDR but WEAK_RHO <= |rho| < MIN_RHO. Kept separately because a
    rank correlation understates links with rare events (e.g. food delivery on 13% of days):
    all the tied zeros cap rho, while the plain "x times as likely" can still be large.
Each kept pair becomes a plain-English sentence with the numbers behind it, phrased as an
association (never "causes"). See docs/analysis.md.
"""

from __future__ import annotations

import math
from itertools import combinations

import numpy as np
import pandas as pd
from scipy.stats import false_discovery_control, spearmanr

from .metrics import METRICS, fmt, label, source_of, strength, subject, unit

MIN_DAYS = 30
FDR = 0.05
MIN_RHO = 0.2
WEAK_RHO = 0.1
LAGS = (0, 1, 2)

NICE = {
    "min": [15, 30, 45, 60, 90, 120, 180, 240, 300, 360],
    "inr": [50, 100, 150, 200, 300, 500, 750, 1000, 1500, 2000, 3000, 5000],
    "share": [0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.6, 0.75],
    "score": [-0.2, -0.1, 0.0, 0.1, 0.2, 0.3, 0.4],
}


def metric_columns(df: pd.DataFrame) -> list[str]:
    """Metrics present with enough non-missing, non-constant values."""
    out = []
    for m in METRICS:
        if m in df.columns:
            s = df[m].dropna()
            if len(s) >= MIN_DAYS and s.nunique() > 2:
                out.append(m)
    return out


def run_tests(df: pd.DataFrame) -> pd.DataFrame:
    """All cross-source Spearman tests. df: one row per consecutive day (shift = days)."""
    cols = metric_columns(df)
    rows = []
    for a, b in combinations(cols, 2):
        if source_of(a) == source_of(b):
            continue
        for lag in LAGS:
            for x, y in ([(a, b)] if lag == 0 else [(a, b), (b, a)]):
                xs, ys = df[x], df[y].shift(-lag)
                mask = xs.notna() & ys.notna()
                n = int(mask.sum())
                if n < MIN_DAYS or xs[mask].nunique() < 3 or ys[mask].nunique() < 3:
                    continue
                rho, p = spearmanr(xs[mask], ys[mask])
                if np.isnan(rho):
                    continue
                rows.append({"x": x, "y": y, "lag": lag, "n": n, "rho": float(rho), "p": float(p)})
    t = pd.DataFrame(rows, columns=["x", "y", "lag", "n", "rho", "p"])
    t["q"] = false_discovery_control(t["p"].to_numpy(), method="bh") if len(t) else []
    return t


def significant(tests: pd.DataFrame, lo: float = MIN_RHO, hi: float = 1.01) -> pd.DataFrame:
    """Survivors of BH (q < FDR) with lo <= |rho| < hi; per unordered pair, its strongest lag."""
    s = tests[(tests["q"] < FDR) & (tests["rho"].abs() >= lo) & (tests["rho"].abs() < hi)].copy()
    if s.empty:
        return s
    s["pair"] = [tuple(sorted((x, y))) for x, y in zip(s["x"], s["y"])]
    s = s.sort_values(["pair", "q", "lag"]).groupby("pair", as_index=False).first()
    s["abs_rho"] = s["rho"].abs()
    return s.sort_values("abs_rho", ascending=False).drop(columns=["abs_rho"]).reset_index(drop=True)


# ---------------------------------------------------------------- plain-English insights

def _threshold(x: pd.Series, m: str) -> float | None:
    """A round threshold near the 70th percentile that leaves >= 10 days on each side."""
    target = float(x.quantile(0.7))
    cands = NICE.get(unit(m))
    if cands is None:  # counts: round integers
        cands = sorted({max(1, int(round(target * f))) for f in (0.5, 0.75, 1.0, 1.25, 1.5)})
    best = None
    for c in sorted(cands, key=lambda c: abs(c - target)):
        hi = (x >= c).sum()
        if hi >= 10 and (len(x) - hi) >= 10:
            best = c
            break
    return best


def _cond_phrase(m: str, t: float) -> str:
    u = unit(m)
    if u in ("min", "inr"):
        return f"with {fmt(m, t)}+ of {label(m)}"
    if u == "count":
        return f"with {fmt(m, t)}+ {label(m)}"
    return f"when the {label(m)} is {fmt(m, t)} or more" if u == "share" else f"when {label(m)} is {fmt(m, t)} or more"


def conditional(df: pd.DataFrame, x: str, y: str, lag: int, rho: float) -> dict | None:
    """Turn one correlation into "On days with <X high>, <Y> is ..." with the numbers behind it."""
    xs, ys = df[x], df[y].shift(-lag)
    mask = xs.notna() & ys.notna()
    xs, ys = xs[mask], ys[mask]
    t = _threshold(xs, x)
    if t is None:
        return None
    hi, lo = ys[xs >= t], ys[xs < t]
    when = {0: "On days", 1: "The day after days", 2: "Two days after days"}[lag]
    cond = _cond_phrase(x, t)
    event = METRICS[y][3]
    zero_share = float((ys == 0).mean())
    if event and zero_share >= 0.3:  # Y is "did it happen?" -> compare how often
        r_hi, r_lo = float((hi > 0).mean()), float((lo > 0).mean())
        if r_lo == 0 or r_hi == 0:
            return None
        ratio = r_hi / r_lo
        if ratio >= 1:
            outcome = f"you're {ratio:.1f}x as likely to {event} ({r_hi:.0%} vs {r_lo:.0%} of days)"
        else:
            outcome = f"you're {1 / ratio:.1f}x less likely to {event} ({r_hi:.0%} vs {r_lo:.0%} of days)"
        groups = {"kind": "rate", "high": round(r_hi, 4), "low": round(r_lo, 4), "ratio": round(ratio, 2)}
    else:
        m_hi, m_lo = float(hi.mean()), float(lo.mean())
        if unit(y) in ("share", "score"):
            diff = m_hi - m_lo
            word = "higher" if diff > 0 else "lower"
            if unit(y) == "share":
                outcome = f"{subject(y)} is {abs(diff) * 100:.0f} points {word} ({fmt(y, m_hi)} vs {fmt(y, m_lo)})"
            else:
                outcome = f"{subject(y)} is {word} ({fmt(y, m_hi)} vs {fmt(y, m_lo)} on average)"
        else:
            if m_lo <= 0:
                return None
            change = m_hi / m_lo - 1
            outcome = (f"{subject(y)} is {abs(change):.0%} {'higher' if change > 0 else 'lower'} "
                       f"({fmt(y, m_hi)} vs {fmt(y, m_lo)} on average)")
        groups = {"kind": "mean", "high": round(m_hi, 4), "low": round(m_lo, 4)}
    if (groups["high"] > groups["low"]) != (rho > 0):
        return None  # the simple split disagrees with the rank correlation: don't oversimplify
    return {"sentence": f"{when} {cond}, {outcome}.", "threshold": t, "n_high": int(len(hi)), "n_low": int(len(lo)),
            **groups}


def _describe(df: pd.DataFrame, sig: pd.DataFrame) -> list[dict]:
    out = []
    for r in sig.itertuples():
        c = conditional(df, r.x, r.y, int(r.lag), r.rho)
        lag_txt = {0: "same day", 1: "next day", 2: "two days later"}[int(r.lag)]
        generic = (f"{label(r.x).capitalize()} and {label(r.y)} {'rise' if r.rho > 0 else 'move opposite'} "
                   f"together ({lag_txt}).")
        out.append({
            "x": r.x, "y": r.y, "lag": int(r.lag), "n": int(r.n), "rho": round(float(r.rho), 3),
            "p": float(r.p), "q": float(r.q), "strength": strength(r.rho),
            "direction": "positive" if r.rho > 0 else "negative",
            "sources": [source_of(r.x), source_of(r.y)],
            "sentence": (c["sentence"] if c else generic),
            "detail": c,
            "stats": f"rho {r.rho:+.2f} · n {r.n} days · adjusted p {_p(r.q)} · {lag_txt}",
            "note": "Association, not causation: both may be driven by something else (e.g. exams).",
        })
    return out


def insights(df: pd.DataFrame, top: int | None = None) -> tuple[list[dict], dict, list[dict]]:
    """-> (ranked insights, summary of the tests run, weaker signals)."""
    tests = run_tests(df)
    sig = significant(tests)
    weak = significant(tests, lo=WEAK_RHO, hi=MIN_RHO)
    out, weak_out = _describe(df, sig), _describe(df, weak)
    summary = {"tests": int(len(tests)), "significant": int(len(sig)), "weak_signals": int(len(weak)),
               "fdr": FDR, "min_rho": MIN_RHO, "weak_rho": WEAK_RHO, "min_days": MIN_DAYS, "lags": list(LAGS),
               "metrics": metric_columns(df)}
    return (out[:top] if top else out), summary, weak_out


def _p(q: float) -> str:
    return "< 0.001" if q < 0.001 else f"{q:.3f}"


def count_involving(insight_list: list[dict], source: str) -> int:
    return sum(source in i["sources"] for i in insight_list)


def nan_to_none(x):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else x
