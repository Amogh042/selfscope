"""Build the full demo database in plain Python, mirroring the app: import every demo file,
categorise bank rows, enrich YouTube / Spotify / WhatsApp, set "me", tag the demo exam
periods, then assemble the analysis-engine input. Used by tests and ml/scripts/validate_analysis.py."""

from __future__ import annotations

import json
import tempfile
import uuid
from pathlib import Path

import categoriser
from enrich import ENRICH_VERSION
from enrich import runner as enrich_runner
from sqlkit import connect, import_df, named, set_vars
from test_storage import demo_frames

ROOT = Path(__file__).resolve().parents[4]
DATA = ROOT / "web" / "public" / "data"
MODEL = ROOT / "web" / "public" / "models" / "categoriser.json"
_TMP = Path(tempfile.mkdtemp(prefix="selfscope-demo-"))


def load_enrich_resources():
    enrich_runner.load_resources(*(json.loads((DATA / n).read_text(encoding="utf-8"))
                                   for n in ("youtube_channels.json", "song_moods.json", "sentiment_lexicon.json")))


def apply_file(con, block_sql: str, rows: list, **vars_) -> None:
    path = _TMP / f"{uuid.uuid4().hex}.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    set_vars(con, pred_file=str(path), **vars_)
    con.execute(block_sql)


def categorise_bank(con) -> None:
    df = con.execute(named("queries")["bank_rows_for_model"]).df()
    events = [{"event_key": k, "local_date": d, "weekday": int(w), "value": float(v), "meta": m}
              for k, d, w, v, m in df.itertuples(index=False)]
    out = json.loads(categoriser.categorise_events_json(json.dumps(events), MODEL.read_text(encoding="utf-8")))
    apply_file(con, named("categorise")["apply_predictions"], out["predictions"],
               model_version=out["model"]["version"], model_f1=str(out["model"]["test_macro_f1"]))
    con.execute(named("categorise")["refresh_categories"])


def enrich(con) -> None:
    load_enrich_resources()
    set_vars(con, enrich_version=ENRICH_VERSION)
    df = con.execute(named("queries")["enrich_pending"]).df()
    events = [dict(zip(df.columns, row)) for row in df.itertuples(index=False)]
    out = json.loads(enrich_runner.enrich_events_json(json.dumps(events, default=str)))
    apply_file(con, named("enrich")["apply_enrichment"], out["predictions"])


def tag_demo_periods(con) -> None:
    for p in json.loads((ROOT / "data" / "samples" / "periods.json").read_text())["periods"]:
        set_vars(con, period_id=uuid.uuid4().hex, label=p["label"], start_date=p["start"], end_date=p["end"],
                 origin="demo", created_at="2026-11-23 10:00:00")
        con.execute(named("manage")["add_period"])


def build(frames=None):
    con = connect()
    for src, name, df in frames or demo_frames():
        import_df(con, df, src, name)
    categorise_bank(con)
    enrich(con)
    set_vars(con, me="Amogh")
    con.execute(named("manage")["set_me"])
    tag_demo_periods(con)
    return con


def engine_payload(con, range_from=None, range_to=None) -> dict:
    q = named("queries")
    features = con.execute(q["features_for_engine"]).df()
    features = json.loads(features.to_json(orient="records"))
    set_vars(con, range_from=range_from, range_to=range_to)
    ov = con.execute(q["overlap"]).df().to_dict("records")[0]
    return {
        "range": {"from": range_from, "to": range_to},
        "overlap": {"start_date": ov["start_date"], "end_date": ov["end_date"]},
        "features": features,
        "periods": con.execute(q["periods_list"]).df().to_dict("records"),
        "mood_by_hour": con.execute(q["spotify_mood_by_hour"]).df().to_dict("records"),
        "heatmap": con.execute(q["heatmap_in_range"]).df().to_dict("records"),
    }
