import json
from pathlib import Path

import pandas as pd

import schema
from parsers.spotify import parse_spotify, summarize_spotify

FIXTURES = Path(__file__).parent / "fixtures" / "spotify"
ACCOUNT = ["StreamingHistory_music_0.json", "StreamingHistory_music_1.json", "StreamingHistory_podcast_0.json"]
EXTENDED = "Streaming_History_Audio_2025-2026_0.json"


def files(*names):
    return {n: (FIXTURES / n).read_text(encoding="utf-8") for n in names}


def metas(df):
    return [json.loads(m) for m in df[schema.META]]


def test_output_matches_shared_schema():
    df = parse_spotify(files(*ACCOUNT, EXTENDED))
    assert list(df.columns) == schema.COLUMNS
    assert str(df[schema.TS_UTC].dt.tz) == "UTC"
    assert set(df[schema.SOURCE]) == {"spotify"} and set(df[schema.EVENT_TYPE]) == {"play"}
    assert df[schema.TEXT].isna().all() and df[schema.CATEGORY].isna().all()
    assert df[schema.VALUE].dtype == "float64"


# ---------------------------------------------------------------- account data

def test_account_music_and_podcast_merge_and_dedupe():
    df = parse_spotify(files(*ACCOUNT))
    # 3 + 2 + 1 records, one exact duplicate across the two music files
    assert len(df) == 5
    assert df.attrs["duplicates_dropped"] == 1
    assert df.attrs["per_file"] == {"StreamingHistory_music_0.json": 3, "StreamingHistory_music_1.json": 2,
                                    "StreamingHistory_podcast_0.json": 1}
    assert df.attrs["formats"] == ["account"]
    first = df.iloc[0]
    assert (first[schema.ACTOR], first[schema.TITLE], first[schema.VALUE]) == ("Arijit Singh", "Kesariya", 268000.0)
    podcast = df[df[schema.ACTOR] == "Money Talks India"].iloc[0]
    assert podcast[schema.TITLE] == "Ep. 12: Budgeting as a Student"
    assert json.loads(podcast[schema.META])["kind"] == "podcast"


def test_account_times_are_utc_end_times_with_start_estimate():
    df = parse_spotify(files(*ACCOUNT))
    first = df.iloc[0]
    assert first[schema.TS_UTC] == pd.Timestamp("2025-11-17 16:15", tz="UTC")
    assert (first[schema.LOCAL_DATE], first[schema.LOCAL_HOUR]) == ("2025-11-17", 21)  # 21:45 IST
    assert json.loads(first[schema.META])["start_estimate"] == "2025-11-17T16:10:32.000Z"  # 16:15 - 268 s
    perfect = df[df[schema.TITLE] == "Perfect"].iloc[0]
    assert (perfect[schema.LOCAL_DATE], perfect[schema.LOCAL_HOUR]) == ("2025-11-18", 0)  # 00:05 IST


def test_skip_falls_back_to_30_second_rule():
    df = parse_spotify(files(*ACCOUNT))
    skipped = {t: json.loads(m)["skipped"] for t, m in zip(df[schema.TITLE], df[schema.META])}
    assert skipped["Raabta"] is True           # 12 s
    assert skipped["Mungaru Maleye"] is False  # exactly 30 s is not a skip
    assert skipped["Kesariya"] is False


# ---------------------------------------------------------------- extended history

def test_extended_format_fields_and_messy_records():
    df = parse_spotify(files(EXTENDED))
    assert df.attrs["formats"] == ["extended"]
    assert len(df) == 6                       # 9 entries: bad ts, a string, a non-play object dropped
    assert df.attrs["skipped_records"] == 3
    assert df.attrs["per_file"] == {EXTENDED: 6}   # rows with a valid timestamp
    m = {(t or "?"): x for t, x in zip(df[schema.TITLE], metas(df))}
    assert m["Kesariya"] == {"kind": "music", "format": "extended", "uri": "spotify:track:0000000000000000000001",
                             "album": "Brahmastra", "platform": "android", "shuffle": False,
                             "reason_start": "trackdone", "reason_end": "trackdone", "skipped": False,
                             "start_estimate": "2025-11-17T16:11:02.000Z"}
    assert m["Raabta"]["skipped"] is True     # field wins over the 30 s rule (45 s played)
    assert m["Tum Hi Ho"]["skipped"] is True  # field is null -> 30 s rule
    assert m["Perfect"]["kind"] == "music" and "album" not in m["Perfect"]   # sparse record is fine
    assert m["?"]["kind"] == "unknown"


def test_extended_podcast_maps_show_and_episode():
    df = parse_spotify(files(EXTENDED))
    row = df[df[schema.ACTOR] == "Startup Stories India"].iloc[0]
    assert row[schema.TITLE] == "Ep. 40: AI and Jobs"
    meta = json.loads(row[schema.META])
    assert meta["kind"] == "podcast" and meta["uri"] == "spotify:episode:0000000000000000000004"


def test_accepts_single_text_and_empty_input():
    text = (FIXTURES / "StreamingHistory_music_0.json").read_text(encoding="utf-8")
    assert len(parse_spotify(text)) == 3
    empty = parse_spotify({"x.json": "[]"})
    assert empty.empty and list(empty.columns) == schema.COLUMNS


# ---------------------------------------------------------------- summary

def test_summary():
    s = summarize_spotify(parse_spotify(files(*ACCOUNT)))
    assert s["plays"] == 5 and s["music_plays"] == 4 and s["podcast_plays"] == 1
    assert s["hours"] == round((268000 + 12000 + 263400 + 30000 + 1800000) / 3.6e6, 1)
    assert s["top_artists"][0] == {"name": "Arijit Singh", "plays": 2, "hours": 0.1}
    assert s["top_tracks"][0]["plays"] == 1 and len(s["top_tracks"]) == 4
    assert s["skip_rate"] == 0.2
    assert (s["first_date"], s["last_date"]) == ("2025-11-17", "2025-11-18")
    json.dumps(s)
