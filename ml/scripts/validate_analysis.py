"""Validate the analysis engine on the demo data and write ml/reports/analysis_validation.{json,md}.

1. Build the demo database exactly like the app (import, categorise, enrich, tag exams).
2. Enrichment coverage (incl. YouTube with title rules only, as if no channel were known).
3. Run the engine on the whole demo year; check each planted pattern.
4. Null test: shuffle the dates of one source at a time (10 seeds x 4 sources) and count
   cross-source findings involving that source that still survive (all false positives).

Usage:  python ml/scripts/validate_analysis.py
"""

from __future__ import annotations

import json
import os
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path[:0] = [os.path.join(ROOT, "web", "src", "python", "tests"), os.path.join(ROOT, "web", "src", "python")]

import demo_pipeline as dp  # noqa: E402
from analysis import engine, validation  # noqa: E402
from enrich.youtube_topics import classify  # noqa: E402
from sqlkit import named  # noqa: E402

REPORTS = os.path.join(ROOT, "ml", "reports")


def main():
    t0 = time.time()
    con = dp.build()
    cov = {r[0]: {"rows": r[1], "labelled": r[2], "share": round(r[2] / r[1], 4)}
           for r in con.execute(named("queries")["enrichment_coverage"]).fetchall()}
    rows = con.execute("SELECT title, category FROM event_facts WHERE source='youtube' AND event_type='watch' "
                       "AND NOT is_ad").fetchall()
    by_title = [classify(None, t, {})[0] for t, _ in rows]
    cov["youtube_title_rules_only"] = {
        "labelled_share": round(sum(c != "other" for c in by_title) / len(rows), 4),
        "agrees_with_channel_map": round(sum(a == c for a, (_, c) in zip(by_title, rows)) / len(rows), 4)}
    yt_cats = dict(con.execute("SELECT category, count(*) FROM event_facts WHERE source='youtube' AND "
                               "event_type='watch' AND NOT is_ad GROUP BY 1").fetchall())
    sp_cats = dict(con.execute("SELECT category, count(*) FROM events WHERE source='spotify' GROUP BY 1").fetchall())
    sp_lang = dict(con.execute("SELECT json_extract_string(meta,'$.language'), count(*) FROM events "
                               "WHERE source='spotify' GROUP BY 1").fetchall())
    wa_cats = dict(con.execute("SELECT category, count(*) FROM events WHERE source='whatsapp' AND category IS NOT NULL "
                               "GROUP BY 1").fetchall())

    res = engine.run(dp.engine_payload(con))
    per = {(r["period"], r["metric"]): r for r in res["periods"]}

    def p(period, metric):
        r = per[(period, metric)]
        return {"sentence": r["sentence"], "q": r["q"], "significant": r["significant"], "direction": r["direction"]}

    pool = res["insights"] + res["weak_signals"]
    yt_fd = sorted([i for i in pool if {i["x"], i["y"]} & {"youtube_est_minutes", "youtube_videos"}
                    and "food_delivery_spend" in (i["x"], i["y"])], key=lambda i: -i["rho"])
    planted = {
        "a_youtube_food_delivery": [{"tier": "insight" if i in res["insights"] else "weaker signal",
                                     "sentence": i["sentence"], "stats": i["stats"]} for i in yt_fd],
        "b_exams": {m: p("Exams", m) for m in ("youtube_study_min", "wa_late_night_share", "spotify_late_night_share",
                                                "youtube_late_night_share", "spotify_sad_share", "wa_negative_share")},
        "c_weekends": {m: p("Weekends", m) for m in ("youtube_comedy_min", "entertainment_shopping_spend")},
        "d_late_night_sad": res["song_mood_by_hour"],
    }
    df = engine.frame(dp.engine_payload(con)["features"])
    runs = validation.null_test(df, ["spotify", "youtube", "whatsapp", "bank"], range(10))
    null = {"runs": len(runs),
            "false_insights_total": sum(r["false_insights"] for r in runs),
            "false_insights_per_run": round(sum(r["false_insights"] for r in runs) / len(runs), 3),
            "false_weak_per_run": round(sum(r["false_weak_signals"] for r in runs) / len(runs), 2),
            "by_source": {s: {"false_insights": sum(r["false_insights"] for r in runs if r["source"] == s),
                              "false_weak_signals": sum(r["false_weak_signals"] for r in runs if r["source"] == s)}
                          for s in ("spotify", "youtube", "whatsapp", "bank")},
            "real_insights_involving_each_source": {
                s: sum(s in i["sources"] for i in res["insights"]) for s in ("spotify", "youtube", "whatsapp", "bank")}}
    sentiment = json.load(open(os.path.join(REPORTS, "sentiment_results.json")))
    out = {"coverage": cov, "youtube_topics": yt_cats, "spotify_moods": sp_cats, "spotify_languages": sp_lang,
           "whatsapp_sentiment": wa_cats, "sentiment_eval": {k: sentiment[k] for k in ("all", "mine", "baseline_neutral")},
           "tests": res["tests"], "top_insights": [{"sentence": i["sentence"], "strength": i["strength"],
                                                   "stats": i["stats"]} for i in res["insights"][:10]],
           "planted": planted, "null_test": null, "anomalies": [d["sentence"] for d in res["anomalies"]["days"][:5]],
           "seconds": round(time.time() - t0)}
    with open(os.path.join(REPORTS, "analysis_validation.json"), "w", encoding="utf-8") as f:
        json.dump(engine._clean(out), f, indent=2, ensure_ascii=False)
    print(json.dumps(engine._clean({k: out[k] for k in ("coverage", "tests", "null_test")}), indent=1))
    for i in out["top_insights"]:
        print(" -", i["strength"], "|", i["sentence"], "|", i["stats"])
    for a in planted["a_youtube_food_delivery"]:
        print(" A", a["tier"], "|", a["sentence"], "|", a["stats"])


if __name__ == "__main__":
    main()
