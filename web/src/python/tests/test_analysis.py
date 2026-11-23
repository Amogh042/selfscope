"""Validation of the enrichment + analysis engine on the demo data: it must REDISCOVER the
patterns planted by ml/scripts/generate_demo_data.py, and a null test must find (almost)
nothing. Numbers are written up in docs/analysis.md (ml/scripts/validate_analysis.py)."""

import json

import pytest

import demo_pipeline as dp
from analysis import correlations, engine, validation
from analysis.metrics import METRICS
from enrich.youtube_topics import classify
from sqlkit import named, scalar


@pytest.fixture(scope="module")
def con():
    return dp.build()


@pytest.fixture(scope="module")
def res(con):
    return engine.run(dp.engine_payload(con))


def find_period(res, period, metric):
    return next(r for r in res["periods"] if r["period"] == period and r["metric"] == metric)


# ---------------------------------------------------------------- enrichment

def test_enrichment_coverage(con):
    cov = {r[0]: r[2] / r[1] for r in con.execute(named("queries")["enrichment_coverage"]).fetchall()}
    assert cov["youtube"] >= 0.95 and cov["spotify"] == 1.0 and cov["whatsapp"] == 1.0
    assert scalar(con, "SELECT count(*) FROM events WHERE source IN ('youtube','spotify','whatsapp') AND "
                       "json_extract_string(meta,'$.enrich_version') IS NULL") == 0
    # re-running enrichment finds nothing left to do
    from enrich import ENRICH_VERSION
    from sqlkit import set_vars
    set_vars(con, enrich_version=ENRICH_VERSION)
    assert con.execute(named("queries")["enrich_pending"]).fetchall() == []


def test_youtube_title_rules_alone_cover_most_demo_videos(con):
    rows = con.execute("SELECT actor, title, category FROM event_facts WHERE source='youtube' AND event_type='watch' "
                       "AND NOT is_ad").fetchall()
    by_title = [classify(None, t, {})[0] for _, t, _ in rows]          # as if no channel were known
    labelled = sum(c != "other" for c in by_title) / len(rows)
    agree = sum(a == c for a, (_, _, c) in zip(by_title, rows)) / len(rows)
    assert labelled >= 0.6 and agree >= 0.6


def test_unknown_moods_are_never_guessed(con):
    assert scalar(con, "SELECT count(*) FROM events WHERE source='spotify' AND category NOT IN "
                       "('romantic','sad','upbeat','unknown')") == 0


# ---------------------------------------------------------------- planted patterns

def test_a_youtube_time_and_food_delivery(res):
    pool = res["insights"] + res["weak_signals"]
    hits = [i for i in pool if {i["x"], i["y"]} & {"youtube_est_minutes", "youtube_videos"}
            and "food_delivery_spend" in (i["x"], i["y"]) and i["rho"] > 0 and i["q"] < 0.05]
    assert hits, "YouTube time <-> food delivery not found"
    best = max(hits, key=lambda i: i["rho"])
    assert best["detail"]["kind"] == "rate" and best["detail"]["ratio"] >= 1.5


@pytest.mark.parametrize("metric", ["youtube_study_min", "wa_late_night_share", "spotify_late_night_share",
                                    "spotify_sad_share", "wa_negative_share"])
def test_b_exam_periods(res, metric):
    r = find_period(res, "Exams", metric)
    assert r["significant"] and r["direction"] == "up", r["sentence"]


def test_b_exam_youtube_late_night_is_up_but_weak(res):
    # planted, but small (+4 points over 39 exam days): found in the right direction, NOT significant
    r = find_period(res, "Exams", "youtube_late_night_share")
    assert r["direction"] == "up"


@pytest.mark.parametrize("metric", ["youtube_comedy_min", "entertainment_shopping_spend"])
def test_c_weekends(res, metric):
    r = find_period(res, "Weekends", metric)
    assert r["significant"] and r["direction"] == "up", r["sentence"]


def test_d_late_night_sad_songs(res):
    m = res["song_mood_by_hour"]
    assert m["late_sad_share"] > 1.5 * m["other_sad_share"] and m["p"] < 1e-6


# ---------------------------------------------------------------- engine guarantees

def test_insights_follow_the_rules(res):
    assert res["insights"], "no insights at all"
    for i in res["insights"]:
        assert i["q"] < 0.05 and abs(i["rho"]) >= 0.2 and i["n"] >= 30
        assert METRICS[i["x"]].source != METRICS[i["y"]].source
        assert i["strength"] in ("weak", "moderate", "strong")
        assert "cause" not in i["sentence"].lower()
    for w in res["weak_signals"]:
        assert w["q"] < 0.05 and 0.1 <= abs(w["rho"]) < 0.2
    assert res["correlation_window"]["days"] == 365


def test_anomalies_and_trends(res):
    days = res["anomalies"]["days"]
    assert 1 <= len(days) <= 10 and all(d["sentence"][0].isdigit() and len(d["metrics"]) >= 2 for d in days)
    assert len(res["trends"]["monthly"]) == 13 and set(res["trends"]["heatmaps"]) == {"spotify", "whatsapp", "youtube"}


def test_date_range_is_respected(con):
    r = engine.run(dp.engine_payload(con, "2026-05-01", "2026-06-30"))
    assert r["range"]["days"] == 61 and r["correlation_window"]["days"] == 61
    assert {p["period"] for p in r["periods"]} <= {"Exams", "Weekends"}


def test_json_round_trip(con):
    out = json.loads(engine.run_json(json.dumps(dp.engine_payload(con, "2026-01-01", "2026-03-31"))))
    assert out["engine_version"] and isinstance(out["insights"], list)


# ---------------------------------------------------------------- null test

def test_null_test_finds_almost_nothing(con):
    df = engine.frame(dp.engine_payload(con)["features"])
    runs = validation.null_test(df, ["youtube", "bank"], range(3))
    # the reported insights (|rho| >= 0.2) survive the null test ...
    assert sum(r["false_insights"] for r in runs) <= 1
    # ... the "weaker signals" tier lets a few chance findings through (why it is labelled "may be chance")
    assert sum(r["false_weak_signals"] for r in runs) / len(runs) <= 8
