import math

import pytest

from selfscope_ml import features as F
from selfscope_ml import rules as R


def row(cp="", vpa="", note="UPI", amount=25.0, channel="UPI", bank="PYTM", d="2026-03-02", wd=0, debit=True):
    return {"counterparty": cp, "vpa_fragment": vpa, "note": note, "bank_code": bank, "channel": channel,
            "amount": amount, "is_debit": debit, "local_date": d, "weekday": wd}


# ---------------------------------------------------------------- features

def test_text_doc_and_analyzer():
    doc = F.text_doc(row("RAJ TEA", "paytmqr281", "UPI"))
    assert doc == "raj tea paytmqr000 upi\tbank:pytm ch:upi"   # digits -> 0, structural tokens after the tab
    grams = F.analyzer(doc)
    assert " r" in grams and "raj " in grams and " tea " in grams and "bank:pytm" in grams and "ch:upi" in grams
    assert all(len(g) <= 5 for g in grams if ":" not in g)
    assert F.analyzer("ab\t") == [" a", "ab", "b ", " ab", "ab ", " ab "]


def test_row_from_event_and_payee_key():
    r = F.row_from_event({"counterparty": "SWIGGY ", "vpa_fragment": "Swiggy.sto", "channel": "UPI"}, -349.0,
                         "2026-03-02", 0)
    assert r["amount"] == 349.0 and r["is_debit"] and r["note"] == "" and r["bank_code"] == ""
    assert F.payee_key(r) == "swiggy|swiggy.sto"


def test_payee_stats_behaviour():
    rows = [row("TEA", "q1", amount=25, d="2026-03-02", wd=0), row("TEA", "q1", amount=25, d="2026-03-02", wd=0),
            row("TEA", "q1", amount=30, d="2026-03-07", wd=5), row("FRIEND", "f@ok", amount=500, d="2026-03-03"),
            row("TEA", "q1", amount=999, debit=False)]                      # credits are ignored
    s = F.payee_stats(rows)
    tea = s["tea|q1"]
    assert (tea["count"], tea["active_days"], tea["median"]) == (3, 2, 25)
    assert tea["per_active_day"] == 1.5 and tea["weekend_share"] == pytest.approx(1 / 3)
    assert tea["density"] == pytest.approx(2 / 6)                          # 2 active days in a 6-day span
    assert s["friend|f@ok"]["count"] == 1


def test_dense_features_shape_and_values():
    rows = [row("TEA", "q1", amount=25)] * 4
    stats = F.payee_stats(rows)
    f = dict(zip(F.DENSE_NAMES, F.dense_features(rows[0], stats)))
    assert len(F.DENSE_NAMES) == len(F.dense_features(rows[0], stats))
    assert f["ch_upi"] == 1 and f["ch_atm"] == 0 and f["amt_le_30"] == 1 and f["kw_tea_snacks"] == 1
    assert f["log_amount"] == pytest.approx(math.log1p(25)) and f["payee_log_count"] == pytest.approx(math.log1p(4))
    assert f["amount_vs_payee_median"] == 0
    unseen = dict(zip(F.DENSE_NAMES, F.dense_features(row("NEW", "zz", amount=100), {})))  # unknown payee: defaults
    assert unseen["payee_log_count"] == pytest.approx(math.log1p(1)) and unseen["kw_none"] == 1


# ---------------------------------------------------------------- rule flags + baseline

@pytest.mark.parametrize("vpa, phone", [("XXXXXX2736", True), ("9845012736@ybl", True), ("paytmqr281", False),
                                        ("rohank98@o", False), ("", False)])
def test_phone_vpa(vpa, phone):
    assert R.is_phone_vpa(vpa) is phone


@pytest.mark.parametrize("vpa, qr", [("paytmqr281", True), ("qXXXXX1745", True), ("q839201745@ybl", True),
                                     ("bharatpe.9", True), ("quickride@", False), ("swiggy.sto", False)])
def test_merchant_qr(vpa, qr):
    assert R.is_merchant_qr(vpa) is qr


@pytest.mark.parametrize("cp, vpa, person", [
    ("ROHAN KU", "rohank98@o", True), ("BASAVARA", "XXXXXX4512", True), ("NEHA IYE", "neha.iyer@", True),
    ("SWIGGY", "swiggy.sto", False), ("GANESH T", "paytmqr1a2", False), ("AMMA MES", "ammamess@y", False),
])
def test_looks_like_person(cp, vpa, person):
    assert R.looks_like_person(cp, vpa) is person


@pytest.mark.parametrize("cp, vpa, cat", [
    ("SWIGGY", "swiggy.sto", "food_delivery"), ("SWIGGY I", "instamart.", "groceries_qcommerce"),  # longest wins
    ("STEAM GA", "steam.valv", "entertainment"),                                                  # not "tea"
    ("DMRC", "dmrc.smart", "transport"), ("JIOMART", "jiomart@sb", "groceries_qcommerce"),
    ("JIOSAAVN", "", "subscriptions"), ("RANDOM N", "random@ok", None),
])
def test_keyword_category(cp, vpa, cat):
    assert R.keyword_category(cp, vpa) == cat


def test_rules_baseline():
    assert R.rule_category(row(channel="ATM")) == "cash_atm"
    assert R.rule_category(row("NETFLIX", channel="MANDATE")) == "subscriptions"
    assert R.rule_category(row("SOMEAPP", channel="MANDATE")) == "subscriptions"
    assert R.rule_category(row("ZOMATO", "zomato.ord")) == "food_delivery"
    assert R.rule_category(row("ARJUN NA", "arjun.nair")) == "p2p_transfer"
    assert R.rule_category(row("KAVERI B", "qXXXXX1745", amount=20)) == "tea_snacks"    # small QR payment
    assert R.rule_category(row("KAVERI B", "qXXXXX1745", amount=400)) == "other"
