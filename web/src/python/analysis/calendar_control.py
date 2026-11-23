"""Calendar control: do cross-app links survive once weekday and tagged periods are removed?

Many links in daily data are "calendar-driven": exams raise study videos AND sad songs AND
negative messages, so those metrics correlate even if they never affect each other. To check,
we compute PARTIAL Spearman correlations:

  1. rank each daily metric (ties get the average rank, as in Spearman);
  2. replace each rank by its RESIDUAL from a small linear model on its own day's calendar:
         rank ~ weekday (7 means) + one in/out dummy per tagged period label (e.g. "Exams")
     (ordinary least squares, per metric, on the days it has data). The residual says "how
     much higher or lower than usual for this weekday and period";
  3. correlate the residuals (Pearson) for every cross-source pair at lags 0/1/2, with a
     t-test on n - 2 - (number of calendar terms) degrees of freedom, and Benjamini–Hochberg
     over all tests, exactly like the raw tests.

Why rank first: mostly-zero metrics (food delivery) have many tied zeros. Ranking the residuals
of the raw values would give those zeros different ranks per weekday group and put the
weekday pattern straight back in; residuals of ranks are already free of it.

An insight "holds after controlling for calendar" when, at the same lag, the partial
correlation has the same sign, |rho| >= WEAK_RHO and adjusted p < FDR, where this p is adjusted
(BH) over the reported links being re-checked (insights + weaker signals), because the check is a
re-test of those links, not a new search. The separate "calendar removed" ranking is a new search
and is adjusted over all tests, like the raw one. Calendar effects that
are NOT tagged (semester breaks, start of month) are not removed. See docs/analysis.md.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from itertools import combinations

from scipy.stats import false_discovery_control
from scipy.stats import t as t_dist

from .correlations import FDR, LAGS, MIN_DAYS, MIN_RHO, WEAK_RHO, metric_columns, significant
from .metrics import label, source_of, strength


def period_labels(periods: list[dict]) -> list[str]:
    return sorted({p["label"] for p in periods})


def design(index: pd.DatetimeIndex, periods: list[dict]) -> pd.DataFrame:
    """Intercept + 6 weekday dummies (Monday = baseline) + one dummy per period label."""
    X = pd.DataFrame({"intercept": 1.0}, index=index)
    for d in range(1, 7):
        X[f"weekday_{d}"] = (index.weekday == d).astype(float)
    for lab in period_labels(periods):
        inside = np.zeros(len(index), dtype=bool)
        for p in periods:
            if p["label"] == lab:
                inside |= (index >= pd.Timestamp(p["start_date"])) & (index <= pd.Timestamp(p["end_date"]))
        if 0 < inside.sum() < len(index):  # a period covering no day / every day can't be separated
            X[f"period_{lab}"] = inside.astype(float)
    return X


def residualize(df: pd.DataFrame, periods: list[dict]) -> pd.DataFrame:
    """Each metric's RANKS minus their fitted weekday + period means (NaN where the metric is NaN)."""
    X = design(df.index, periods)
    out = pd.DataFrame(index=df.index)
    for m in metric_columns(df):
        y = df[m].astype(float)
        ok = y.notna().to_numpy()
        Xo, yo = X.to_numpy()[ok], y[ok].rank().to_numpy()
        beta, *_ = np.linalg.lstsq(Xo, yo, rcond=None)
        r = np.full(len(y), np.nan)
        r[ok] = yo - Xo @ beta
        out[m] = r
    return out


def run_partial_tests(res: pd.DataFrame, n_terms: int) -> pd.DataFrame:
    """Pearson correlation of rank residuals (= partial Spearman) for all cross-source pairs."""
    from .metrics import source_of as src
    rows = []
    for a, b in combinations(list(res.columns), 2):
        if src(a) == src(b):
            continue
        for lag in LAGS:
            for x, y in ([(a, b)] if lag == 0 else [(a, b), (b, a)]):
                xs, ys = res[x], res[y].shift(-lag)
                mask = xs.notna() & ys.notna()
                n = int(mask.sum())
                dof = n - 2 - (n_terms - 1)
                if n < MIN_DAYS or dof < 3:
                    continue
                r = float(np.corrcoef(xs[mask], ys[mask])[0, 1])
                if np.isnan(r):
                    continue
                r = max(-0.999999, min(0.999999, r))
                p = float(2 * t_dist.sf(abs(r) * np.sqrt(dof / (1 - r * r)), dof))
                rows.append({"x": x, "y": y, "lag": lag, "n": n, "rho": r, "p": p})
    t = pd.DataFrame(rows, columns=["x", "y", "lag", "n", "rho", "p"])
    t["q"] = false_discovery_control(t["p"].to_numpy(), method="bh") if len(t) else []
    return t


def _sentence(r) -> str:
    when = {0: "On the same day", 1: "On the next day", 2: "Two days later"}[int(r.lag)]
    return (f"{when}, after removing weekday and tagged-period effects, more {label(r.x)} than usual goes with "
            f"{'more' if r.rho > 0 else 'less'} {label(r.y)} than usual.")


def _describe(sig: pd.DataFrame) -> list[dict]:
    lag_txt = {0: "same day", 1: "next day", 2: "two days later"}
    return [{
        "x": r.x, "y": r.y, "lag": int(r.lag), "n": int(r.n), "rho": round(float(r.rho), 3), "p": float(r.p),
        "q": float(r.q), "strength": strength(r.rho), "direction": "positive" if r.rho > 0 else "negative",
        "sources": [source_of(r.x), source_of(r.y)], "sentence": _sentence(r), "detail": None,
        "stats": f"partial rho {r.rho:+.2f} (calendar removed) · n {r.n} days · adjusted p "
                 f"{'< 0.001' if r.q < 0.001 else f'{r.q:.3f}'} · {lag_txt[int(r.lag)]}",
        "note": "Association, not causation, even after removing weekday and tagged periods.",
    } for r in sig.itertuples()]


def control(df: pd.DataFrame, periods: list[dict], insights: list[dict], weak: list[dict]) -> tuple[dict, pd.DataFrame]:
    """Annotate raw insights / weak signals with `calendar` (in place) and return the controlled
    ranking: ({insights, weak_signals, tests, controls}, controlled tests)."""
    res = residualize(df, periods)
    tests = run_partial_tests(res, design(df.index, periods).shape[1])
    by_key = {(r.x, r.y, r.lag): r for r in tests.itertuples()}
    checked = [(item, by_key.get((item["x"], item["y"], item["lag"]))) for item in insights + weak]
    found = [r for _, r in checked if r is not None]
    q_check = iter(false_discovery_control([r.p for r in found], method="bh") if found else [])
    for item, r in checked:
        if r is None:
            item["calendar"] = {"rho": None, "p": None, "q": None, "q_all": None, "holds": False}
            continue
        q = float(next(q_check))
        holds = bool(q < FDR and abs(r.rho) >= WEAK_RHO and np.sign(r.rho) == np.sign(item["rho"]))
        item["calendar"] = {"rho": round(float(r.rho), 3), "p": float(r.p), "q": q, "q_all": float(r.q), "holds": holds}
    out = {
        "insights": _describe(significant(tests)),
        "weak_signals": _describe(significant(tests, lo=WEAK_RHO, hi=MIN_RHO)),
        "tests": int(len(tests)),
        "controls": ["weekday"] + [c.removeprefix("period_") for c in design(df.index, periods).columns
                                   if c.startswith("period_")],
    }
    return out, tests
