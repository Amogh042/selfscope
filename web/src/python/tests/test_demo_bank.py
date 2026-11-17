"""Sanity checks: the demo SBI statement follows the documented routine and planted
patterns (data/samples/README.md). Uses the hidden answer key ml/data/demo_bank_truth.csv,
which the app never reads."""

import csv
import json
from datetime import date, timedelta
from pathlib import Path

import pytest

import schema
from parsers.sbi import parse_sbi

ROOT = Path(__file__).resolve().parents[4]
STATEMENT = ROOT / "data" / "samples" / "bank" / "SBI_statement_demo.xlsx"
TRUTH = ROOT / "ml" / "data" / "demo_bank_truth.csv"
EXAM_WEEKS = [(date(2025, 12, 8), date(2025, 12, 20)), (date(2026, 5, 11), date(2026, 5, 25)),
              (date(2026, 11, 2), date(2026, 11, 14))]
DAYS = 365

pytestmark = pytest.mark.skipif(not TRUTH.exists(), reason="answer key not generated")


@pytest.fixture(scope="module")
def rows():
    df = parse_sbi(STATEMENT.read_bytes(), STATEMENT.name)
    truth = list(csv.DictReader(TRUTH.open(encoding="utf-8")))
    assert len(truth) == len(df)
    out = []
    for (_, r), t in zip(df.iterrows(), truth):
        # the answer key lines up row-for-row with the parsed statement
        assert r[schema.LOCAL_DATE] == t["txn_date"]
        assert r[schema.VALUE] == pytest.approx(float(t["credit"] or 0) - float(t["debit"] or 0))
        out.append({"date": date.fromisoformat(t["txn_date"]), "value": r[schema.VALUE], "cat": t["category"],
                    "actor": r[schema.ACTOR], "meta": json.loads(r[schema.META])})
    return out


def in_exam(d):
    return any(a <= d <= b for a, b in EXAM_WEEKS)


def test_routine(rows):
    snacks = [r for r in rows if r["cat"] == "tea_snacks"]
    assert 3.5 <= len(snacks) / DAYS <= 4.2                         # ~4 snack payments a day
    assert {r["value"] for r in snacks} <= {-20, -25, -30, -40}
    assert sum(r["value"] == -25 for r in snacks) / len(snacks) > 0.8
    assert len({r["actor"] for r in snacks}) == 6                     # six repeat vendors
    meals = -sum(r["value"] for r in rows if r["cat"] == "meals") / DAYS
    assert 210 <= meals <= 250                                         # ~₹240/day (delivery replaces some dinners)
    auto_days = {r["date"] for r in rows if r["cat"] == "transport" and r["value"] == -20}
    assert 0.55 <= len(auto_days) / DAYS <= 0.75                      # autos on ~2/3 of days
    by_dow = {}
    for r in snacks:
        by_dow.setdefault(r["date"].weekday() == 6, []).append(r)
    sundays = sum(1 for i in range(DAYS) if (date(2025, 11, 17) + timedelta(i)).weekday() == 6)
    assert len(by_dow[True]) / sundays < len(by_dow[False]) / (DAYS - sundays)  # fewer snacks on Sundays


def test_budget_and_income(rows):
    spent = -sum(r["value"] for r in rows if r["value"] < 0) / 12
    parent = [r for r in rows if r["actor"] == "SURESH K"]
    assert len(parent) == 12 and all(r["value"] == 15000 for r in parent)
    assert 13_000 <= spent <= 20_000                                   # roughly in line with ₹15k/month income
    assert min(r["meta"]["balance"] for r in rows) >= 0
    assert 2 <= sum(r["meta"]["channel"] == "NEFT" for r in rows) <= 4
    assert sum(r["meta"]["channel"] == "INTEREST" for r in rows) == 4
    assert 2_500 <= len(rows) <= 3_000
    delivery = sum(r["cat"] == "food_delivery" for r in rows) / 12
    assert 3 <= delivery <= 6


def test_planted_patterns(rows):
    def rate(pred, cat):
        days = [date(2025, 11, 17) + timedelta(i) for i in range(DAYS)]
        hit = {r["date"] for r in rows if r["cat"] == cat}
        sel = [d for d in days if pred(d)]
        return sum(d in hit for d in sel) / len(sel)
    # 2) weekends: more entertainment + shopping
    fun = {True: 0.0, False: 0.0}
    for r in rows:
        if r["cat"] in ("entertainment", "shopping"):
            fun[r["date"].weekday() >= 5] += -r["value"]
    assert fun[True] / 104 > 1.5 * fun[False] / 261
    # 1) food delivery more likely in exam weeks
    assert rate(in_exam, "food_delivery") > 1.4 * rate(lambda d: not in_exam(d), "food_delivery")
    # 4) more transfers to the classmate (Varun) in exam weeks
    varun = [r for r in rows if r["actor"] == "VARUN RA" and r["value"] < 0]
    exam_days = sum(in_exam(date(2025, 11, 17) + timedelta(i)) for i in range(DAYS))
    assert sum(in_exam(r["date"]) for r in varun) / exam_days > 5 * sum(not in_exam(r["date"]) for r in varun) / (DAYS - exam_days)
    # 3) first week after the parent credit: more extras
    credits = [r["date"] for r in rows if r["actor"] == "SURESH K"]
    post = lambda d: any(0 <= (d - c).days < 7 for c in credits)  # noqa: E731
    extras = {True: 0.0, False: 0.0}
    for r in rows:
        if r["cat"] in ("food_delivery", "groceries_qcommerce", "shopping", "entertainment"):
            extras[post(r["date"])] += -r["value"]
    n_post = sum(post(date(2025, 11, 17) + timedelta(i)) for i in range(DAYS))
    assert extras[True] / n_post > 1.2 * extras[False] / (DAYS - n_post)
