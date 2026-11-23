"""The training data must be independent of the demo statement (the final test set)."""

import csv
from pathlib import Path

import pytest

import generate_demo_data as demo

ML = Path(__file__).resolve().parents[1]
TRAIN = ML / "data" / "training_set.csv"
LABELS = ML / "data" / "merchant_labels.csv"

# Made-up people and small vendors of the demo bank statement and WhatsApp chats.
# (Real brands such as SWIGGY or RAPIDO legitimately appear in both, as in real life.)
DEMO_MADE_UP = (
    [v[0] for v in demo.BK_SNACKS + demo.BK_LUNCH + demo.BK_DINNER]
    + [a[0] for a in demo.BK_AUTO if a[0] != "RAPIDO"]
    + [f[0] for f in demo.BK_FRIENDS] + [demo.BK_PARENT[0], demo.BK_FREELANCE[0]]
    + [m for c in demo.WA_CHATS for m in c["members"]] + [demo.WA_ME]
)


@pytest.fixture(scope="module")
def training_rows():
    with open(TRAIN, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_no_demo_names_in_training_data(training_rows):
    payees = {r["description"].split("/")[3].upper() for r in training_rows if "/UPI/" in r["description"]
              or r["description"].startswith(("TO TRANSFER-UPI", "BY TRANSFER-UPI"))}
    text = " ".join(r["description"].upper() for r in training_rows)
    with open(LABELS, encoding="utf-8") as f:
        label_names = " ".join(r["name"].upper() for r in csv.DictReader(f))
    for name in DEMO_MADE_UP:
        full, cut = name.upper(), name.upper()[:8].rstrip()
        assert full not in text and full not in label_names, name
        if len(full.split()) > 1 or len(full) > 8:  # the 8-character form SBI would print
            assert cut not in payees, (name, cut)
    # and the demo's planted UPI IDs never appear either
    for v in demo.BK_SNACKS + demo.BK_LUNCH + demo.BK_DINNER + demo.BK_AUTO[1:] + demo.BK_FRIENDS:
        assert v[1][:10].lower() not in text.lower(), v[1]


def test_training_set_size_and_balance(training_rows):
    assert 15_000 <= len(training_rows) <= 25_000
    cats = {}
    for r in training_rows:
        cats[r["category"]] = cats.get(r["category"], 0) + 1
    assert set(cats) == {"tea_snacks", "meals", "food_delivery", "groceries_qcommerce", "transport", "shopping",
                         "entertainment", "bills_recharge", "subscriptions", "p2p_transfer", "cash_atm", "other"}
    shares = sorted(cats.values(), reverse=True)
    assert shares[0] / shares[-1] > 10   # realistic, not uniform
    assert {r["txn_date"][:4] for r in training_rows} == {"2024"}  # a different year from the demo


def test_merchant_labels():
    with open(LABELS, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert 400 <= len(rows) <= 600
    for r in rows:
        assert r["category"] and float(r["min"]) <= float(r["max"])
