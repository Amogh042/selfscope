"""Browser-side spend categoriser: shipped model, decision rules, and SQL integration
(predictions + user overrides in DuckDB, via src/sql/categorise.sql)."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import categoriser
from parsers.sbi import parse_sbi
from selfscope_ml import features as F
from sqlkit import connect, import_df, named, scalar, set_vars

ROOT = Path(__file__).resolve().parents[4]
MODEL = ROOT / "web" / "public" / "models" / "categoriser.json"
RESULTS = ROOT / "ml" / "reports" / "results.json"
DEMO = ROOT / "data" / "samples" / "bank" / "SBI_statement_demo.xlsx"
TRUTH = ROOT / "ml" / "data" / "demo_bank_truth.csv"


def test_browser_copy_of_shared_ml_code_is_identical():
    src, copy = ROOT / "ml" / "selfscope_ml", ROOT / "web" / "src" / "python" / "selfscope_ml"
    names = sorted(p.name for p in src.glob("*.py"))
    assert names == sorted(p.name for p in copy.glob("*.py"))
    for n in names:
        assert (src / n).read_bytes() == (copy / n).read_bytes(), f"{n} differs: run `npm run sync-ml` in web/"


@pytest.fixture(scope="module")
def demo():
    categoriser.load_model(MODEL.read_text(encoding="utf-8"))
    ev = parse_sbi(DEMO.read_bytes(), DEMO.name)
    rows = [F.row_from_event(json.loads(m), v, d, w)
            for m, v, d, w in zip(ev["meta"], ev["value"], ev["local_date"], ev["weekday"])]
    return ev, rows, categoriser.categorise(rows)


def test_shipped_model_reproduces_the_reported_test_numbers(demo):
    _, rows, preds = demo
    truth = pd.read_csv(TRUTH)["category"].to_numpy()
    res = json.loads(RESULTS.read_text())
    debit = np.array([r["is_debit"] for r in rows])
    model_cat = np.array([p["model_category"] for p in preds])
    acc = float((model_cat[debit] == truth[debit]).mean())
    assert acc == pytest.approx(res["test"]["accuracy"], abs=1e-4)
    assert sum(p["source"] == "review" for p in preds) == res["test"]["review_count"]
    info = categoriser.model_info()
    assert info["version"] == res["model_version"] and info["test_macro_f1"] == res["test"]["macro_f1"]


def test_decision_rules(demo):
    _, rows, preds = demo
    for r, p in zip(rows, preds):
        assert p["model_category"] in F.CATEGORIES + ["income"]
        if not r["is_debit"]:
            assert (p["model_category"], p["source"]) == ("income", "rule")
        elif r["channel"] == "ATM":
            assert (p["model_category"], p["source"]) == ("cash_atm", "rule")
        else:
            assert p["source"] == ("model" if p["confidence"] >= categoriser._MODEL.threshold else "review")


def test_feature_version_mismatch_is_refused():
    d = json.loads(MODEL.read_text(encoding="utf-8"))
    d["feature_version"] = -1
    with pytest.raises(ValueError, match="different features"):
        categoriser.load_model(d)
    categoriser.load_model(MODEL.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- SQL integration

def categorise_db(con, tmp_path):
    """Mirror of web/src/lib/categorise.ts: all bank rows -> categoriser -> categorise.sql."""
    q = named("queries")["bank_rows_for_model"]
    df = con.execute(q).df()
    events = [{"event_key": k, "local_date": d, "weekday": int(w), "value": float(v), "meta": m}
              for k, d, w, v, m in df.itertuples(index=False)]
    out = json.loads(categoriser.categorise_events_json(json.dumps(events), MODEL.read_text(encoding="utf-8")))
    path = tmp_path / "pred.json"
    path.write_text(json.dumps(out["predictions"]))
    set_vars(con, pred_file=str(path), model_version=out["model"]["version"],
             model_f1=str(out["model"]["test_macro_f1"]))
    con.execute(named("categorise")["apply_predictions"])
    con.execute(named("categorise")["refresh_categories"])
    return out


def override(con, scope, target, category):
    set_vars(con, scope=scope, target=target, category=category, created_at="2026-11-23 10:00:00")
    con.execute(named("categorise")["set_override"])
    con.execute(named("categorise")["refresh_categories"])


@pytest.fixture()
def db(tmp_path):
    con = connect()
    df = parse_sbi(DEMO.read_bytes(), DEMO.name)
    import_df(con, df, "bank", DEMO.name)
    categorise_db(con, tmp_path)
    return con, df


def test_categories_written_and_food_delivery_fills_in(db):
    con, _ = db
    assert scalar(con, "SELECT count(*) FROM events WHERE source='bank' AND category IS NULL") == 0
    assert scalar(con, "SELECT count(*) FROM events WHERE category='income' AND value < 0") == 0
    fd, days = con.execute("SELECT sum(food_delivery_spend), count(food_delivery_spend) FROM daily_activity").fetchone()
    assert days == 365 and fd > 0
    assert fd == pytest.approx(-scalar(con, "SELECT sum(value) FROM events WHERE category='food_delivery'"))
    meta = json.loads(scalar(con, "SELECT meta FROM events WHERE source='bank' AND value < 0 LIMIT 1"))
    assert {"model_category", "category_confidence", "category_source", "model_version"} <= meta.keys()
    review = scalar(con, "SELECT count(*) FROM events WHERE json_extract_string(meta,'$.category_source')='review'")
    assert review == scalar(con, named("queries")["bank_review_count"]) > 0
    assert scalar(con, "SELECT count(*) FROM events WHERE json_extract_string(meta,'$.category_source')='review' "
                       "AND category <> 'other'") == 0
    version, f1 = con.execute(named("queries")["categoriser_info"]).fetchone()
    assert version == categoriser.model_info()["version"] and float(f1) > 0


def test_override_precedence(db):
    con, _ = db
    key = scalar(con, "SELECT payee_key(meta) FROM events WHERE actor = 'ANNAPOOR' LIMIT 1")
    n = scalar(con, "SELECT count(*) FROM events WHERE payee_key(meta) = ? AND value < 0", key)
    override(con, "payee", key, "meals")                       # payee-wide fix
    assert scalar(con, "SELECT count(*) FROM events WHERE payee_key(meta) = ? AND category = 'meals'", key) == n
    one = scalar(con, "SELECT event_key FROM events WHERE payee_key(meta) = ? LIMIT 1", key)
    override(con, "event", one, "entertainment")               # one transaction beats the payee rule
    assert scalar(con, "SELECT category FROM events WHERE event_key = ?", one) == "entertainment"
    assert scalar(con, "SELECT count(*) FROM events WHERE payee_key(meta) = ? AND category = 'meals'", key) == n - 1
    set_vars(con, scope="event", target=one)
    con.execute(named("categorise")["clear_override"])
    con.execute(named("categorise")["refresh_categories"])
    assert scalar(con, "SELECT category FROM events WHERE event_key = ?", one) == "meals"
    # a new payee-wide correction replaces earlier one-transaction corrections for that payee
    override(con, "event", one, "shopping")
    override(con, "payee", key, "tea_snacks")
    assert scalar(con, "SELECT count(DISTINCT category) FROM events WHERE payee_key(meta) = ?", key) == 1


def test_payee_override_leaves_credits_as_income(db):
    con, _ = db
    key = scalar(con, "SELECT payee_key(meta) FROM events WHERE actor = 'ROHAN KU' AND value > 0 LIMIT 1")
    override(con, "payee", key, "p2p_transfer")
    assert scalar(con, "SELECT count(*) FROM events WHERE payee_key(meta) = ? AND value > 0 AND category <> 'income'",
                  key) == 0


def test_overrides_survive_reimport_and_recategorising(db, tmp_path):
    con, df = db
    key = scalar(con, "SELECT payee_key(meta) FROM events WHERE actor = 'ANNAPOOR' LIMIT 1")
    override(con, "payee", key, "meals")
    imp = scalar(con, "SELECT import_id FROM imports")
    set_vars(con, import_id=imp)
    con.execute(named("manage")["remove_import"])                 # remove and import again
    import_df(con, df, "bank", DEMO.name)
    categorise_db(con, tmp_path)
    assert scalar(con, "SELECT count(*) FROM events WHERE payee_key(meta) = ? AND category <> 'meals' AND value < 0",
                  key) == 0
