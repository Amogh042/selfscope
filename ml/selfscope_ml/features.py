"""Features for the spend categoriser — shared by training (ml/) and the browser (Pyodide).

Pure Python (standard library only, no scikit-learn), so the browser computes EXACTLY the same
features the model was trained on. The source of truth is ml/selfscope_ml/; the browser
gets a byte-identical copy in web/src/python/selfscope_ml/ (web/scripts/sync-ml.mjs,
run before `npm run dev` / `build`; a test fails if the copies differ).

A "row" is one bank debit as stored in the app (shared schema + meta), see row_from_event.

Feature groups
  text      char n-grams (2-5, within words) of counterparty + UPI ID + note, digits -> 0,
            plus whole tokens "bank:<code>" and "ch:<channel>"              (TF-IDF in the model)
  rules     channel one-hot, person-like UPI ID, phone-number UPI ID, merchant QR handle,
            user note, keyword-dictionary category one-hot                  (from rules.py)
  amount    log amount, round-number flags, amount buckets
  payee     behaviour of this payee over the whole statement: how many payments, payments
            per active day, median/std amount, share on weekends, how regular, and how this
            amount compares with the payee's usual amount
"""

from __future__ import annotations

import math
import re
from datetime import date

from .rules import (is_merchant_qr, is_phone_vpa, keyword_category, looks_like_person)

FEATURE_VERSION = 1

# The categories the model predicts for DEBITS. Credits are always "income" (rule).
CATEGORIES = ["tea_snacks", "meals", "food_delivery", "groceries_qcommerce", "transport", "shopping",
              "entertainment", "bills_recharge", "subscriptions", "p2p_transfer", "cash_atm", "other"]
CHANNELS = ["UPI", "NEFT", "IMPS", "ATM", "MANDATE", "OTHER"]
AMOUNT_BUCKETS = [30, 60, 150, 300, 700, 1500, 5000]  # upper edges; last bucket is "> 5000"
GENERIC_NOTES = {"", "upi", "payment", "pay", "paid", "txn", "order", "purchase", "bill"}

NGRAM_MIN, NGRAM_MAX = 2, 5


# ---------------------------------------------------------------- rows

def row_from_event(meta: dict, value: float, local_date: str, weekday: int) -> dict:
    """One stored bank event -> the fields the features use."""
    return {
        "counterparty": meta.get("counterparty") or "",
        "vpa_fragment": meta.get("vpa_fragment") or "",
        "note": meta.get("note") or "",
        "bank_code": meta.get("bank_code") or "",
        "channel": meta.get("channel") or "OTHER",
        "amount": abs(float(value)),
        "is_debit": float(value) < 0,
        "local_date": local_date,
        "weekday": int(weekday),
    }


def payee_key(row: dict) -> str:
    """Who was paid: normalised counterparty + UPI ID (same rule as SQL macro payee_key)."""
    return f"{row['counterparty'].strip().lower()}|{row['vpa_fragment'].strip().lower()}"


# ---------------------------------------------------------------- text

def _norm_text(s: str) -> str:
    s = s.lower()
    s = re.sub(r"\d", "0", s)  # reference-like digits carry no meaning; masked 'x' stays
    return re.sub(r"\s+", " ", s).strip()


def text_doc(row: dict) -> str:
    """The text the TF-IDF part sees: 'counterparty vpa note' + tab + structural tokens."""
    words = " ".join(_norm_text(x) for x in (row["counterparty"], row["vpa_fragment"], row["note"]) if x)
    return f"{words}\tbank:{row['bank_code'].lower() or 'none'} ch:{row['channel'].lower()}"


def analyzer(doc: str) -> list[str]:
    """Char n-grams (NGRAM_MIN..NGRAM_MAX) inside space-padded words + whole structural tokens.
    Used by sklearn's TfidfVectorizer at training time and by the browser at inference."""
    words, _, tokens = doc.partition("\t")
    grams = []
    for w in words.split():
        w = f" {w} "
        for n in range(NGRAM_MIN, NGRAM_MAX + 1):
            grams.extend(w[i:i + n] for i in range(len(w) - n + 1))
    grams.extend(tokens.split())
    return grams


# ---------------------------------------------------------------- payee behaviour

def payee_stats(rows: list[dict]) -> dict[str, dict]:
    """Behaviour of every payee over the whole statement (debits only)."""
    groups: dict[str, list[dict]] = {}
    for r in rows:
        if r["is_debit"]:
            groups.setdefault(payee_key(r), []).append(r)
    out = {}
    for key, rs in groups.items():
        amounts = sorted(r["amount"] for r in rs)
        n = len(amounts)
        mid = n // 2
        median = amounts[mid] if n % 2 else (amounts[mid - 1] + amounts[mid]) / 2
        mean = sum(amounts) / n
        std = math.sqrt(sum((a - mean) ** 2 for a in amounts) / n)
        days = sorted({r["local_date"] for r in rs})
        span = (date.fromisoformat(days[-1]) - date.fromisoformat(days[0])).days + 1
        out[key] = {
            "count": n,
            "active_days": len(days),
            "per_active_day": n / len(days),
            "median": median,
            "std": std,
            "weekend_share": sum(r["weekday"] >= 5 for r in rs) / n,
            "density": len(days) / span,  # how regularly: share of days in the payee's span with a payment
        }
    return out


# ---------------------------------------------------------------- dense features

DENSE_NAMES = (
    [f"ch_{c.lower()}" for c in CHANNELS]
    + ["person_vpa", "phone_vpa", "merchant_qr", "user_note"]
    + [f"kw_{c}" for c in CATEGORIES] + ["kw_none"]
    + ["log_amount", "round_10", "round_50", "round_100"]
    + [f"amt_le_{b}" for b in AMOUNT_BUCKETS] + ["amt_gt_5000"]
    + ["payee_log_count", "payee_per_active_day", "payee_log_median", "payee_log_std", "payee_cv",
       "payee_weekend_share", "payee_density", "payee_log_active_days", "amount_vs_payee_median"]
)


def dense_features(row: dict, stats: dict[str, dict]) -> list[float]:
    cp, vpa, amt = row["counterparty"], row["vpa_fragment"], row["amount"]
    f = [1.0 if row["channel"] == c else 0.0 for c in CHANNELS]
    f += [float(looks_like_person(cp, vpa)), float(is_phone_vpa(vpa)), float(is_merchant_qr(vpa)),
          float(row["note"].strip().lower() not in GENERIC_NOTES)]
    kw = keyword_category(cp, vpa)
    f += [1.0 if kw == c else 0.0 for c in CATEGORIES] + [1.0 if kw is None else 0.0]
    cents = round(amt * 100)
    f += [math.log1p(amt), float(cents % 1000 == 0), float(cents % 5000 == 0), float(cents % 10000 == 0)]
    bucket = next((i for i, b in enumerate(AMOUNT_BUCKETS) if amt <= b), len(AMOUNT_BUCKETS))
    f += [1.0 if i == bucket else 0.0 for i in range(len(AMOUNT_BUCKETS) + 1)]
    s = stats.get(payee_key(row)) or {"count": 1, "active_days": 1, "per_active_day": 1.0, "median": amt,
                                      "std": 0.0, "weekend_share": float(row["weekday"] >= 5), "density": 1.0}
    f += [math.log1p(s["count"]), s["per_active_day"], math.log1p(s["median"]), math.log1p(s["std"]),
          s["std"] / s["median"] if s["median"] > 0 else 0.0, s["weekend_share"], s["density"],
          math.log1p(s["active_days"]), math.log((amt + 1) / (s["median"] + 1))]
    return f
