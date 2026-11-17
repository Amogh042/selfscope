import json
from pathlib import Path

import pandas as pd
import pytest

import schema
from parsers.youtube import parse_youtube, summarize_youtube, video_id

FIXTURE = Path(__file__).parent / "fixtures" / "youtube" / "watch-history.json"


def load():
    return FIXTURE.read_text(encoding="utf-8")


def watches(df):
    w = df[df[schema.EVENT_TYPE] == "watch"].reset_index(drop=True)
    return w, [json.loads(m) for m in w[schema.META]]


def test_output_matches_shared_schema():
    df = parse_youtube(load())
    assert list(df.columns) == schema.COLUMNS
    assert str(df[schema.TS_UTC].dt.tz) == "UTC"
    assert set(df[schema.SOURCE]) == {"youtube"}
    assert set(df[schema.EVENT_TYPE]) == {"watch", "system"}
    assert df[schema.VALUE].isna().all() and df[schema.CATEGORY].isna().all()
    assert df[schema.TS_UTC].is_monotonic_increasing  # Takeout is newest-first; we sort


def test_basic_mapping():
    df = parse_youtube(load())
    w, m = watches(df)
    first = w.iloc[0]
    assert (first[schema.TITLE], first[schema.ACTOR]) == ("Python in One Shot", "CodeWithHarry")
    assert first[schema.TS_UTC] == pd.Timestamp("2026-03-02 10:00", tz="UTC")
    assert (first[schema.LOCAL_DATE], first[schema.LOCAL_HOUR], first[schema.WEEKDAY]) == ("2026-03-02", 15, 0)
    assert m[0]["video_id"] == "pyOneShot01" and m[0]["header"] == "YouTube"
    assert m[0]["channel_url"].startswith("https://www.youtube.com/channel/")
    assert m[0]["is_ad"] is False and m[0]["is_short"] is False


def test_ads_shorts_and_music():
    w, m = watches(parse_youtube(load()))
    by_title = dict(zip(w[schema.TITLE].fillna("?"), m))
    ad = by_title["Shoe Sale Ad"]
    assert ad["is_ad"] is True and ad["channel_url"] is None
    assert by_title["Funny Moments #shorts"]["is_short"] is True
    assert by_title["Funny Moments #shorts"]["video_id"] == "AbCdEfGhIjK"
    music = by_title["Kesariya | Full Video Song"]
    assert music["header"] == "YouTube Music" and music["video_id"] == "kesariya001"


def test_messy_entries():
    df = parse_youtube(load())
    w, m = watches(df)
    assert len(w) == 8
    removed = [x for x in m if x.get("removed")]
    assert len(removed) == 1 and removed[0]["video_id"] is None
    assert w[schema.ACTOR].isna().sum() == 3            # removed, ad, unavailable
    no_link = w[w[schema.TITLE] == "Some Video Without A Link"].iloc[0]
    assert no_link[schema.ACTOR] == "Telusko" and json.loads(no_link[schema.META])["video_id"] is None
    unavailable = [x for x in m if x.get("title_unavailable")]
    assert len(unavailable) == 1 and unavailable[0]["video_id"] == "privateVid1"
    # non-English prefix kept as-is and logged
    assert "Visto Tutorial de pandas en español" in set(w[schema.TITLE])
    assert df.attrs["unrecognised_prefix"] == 1 and df.attrs["prefix_examples"][0].startswith("Visto")
    # "Viewed" post -> system; missing / broken time -> skipped
    system = df[df[schema.EVENT_TYPE] == "system"]
    assert system[schema.TEXT].tolist() == ["Viewed Karthik's post"] and system[schema.ACTOR].isna().all()
    assert df.attrs["skipped_records"] == 2
    assert df.attrs["per_file"] == {"watch-history.json": 9}


def test_estimated_watch_minutes_and_sessions():
    df = parse_youtube(load())
    _, m = watches(df)
    # gaps: 12m, 5.123s, 38m (break), 30m (break), 35m (break), 25m (cap 20), 55s, last
    assert [x["est_watch_min"] for x in m] == [12.0, 0.09, 5.0, 5.0, 5.0, 20.0, 0.92, 5.0]
    assert [x["session"] for x in m] == [0, 0, 0, 1, 2, 3, 3, 3]
    assert df.attrs["sessions"] == 4
    system_meta = json.loads(df[df[schema.EVENT_TYPE] == "system"].iloc[0][schema.META])
    assert "est_watch_min" not in system_meta


def test_duplicate_entries_across_files_count_once():
    df = parse_youtube({"takeout-1/watch-history.json": load(), "takeout-2/watch-history.json": load()})
    assert len(df) == len(parse_youtube(load()))
    assert df.attrs["duplicates_dropped"] == 9


def test_empty_and_wrong_shape():
    empty = parse_youtube("[]")
    assert empty.empty and list(empty.columns) == schema.COLUMNS
    with pytest.raises(ValueError):
        parse_youtube('{"not": "a list"}')


@pytest.mark.parametrize("url, vid", [
    ("https://www.youtube.com/watch?v=abcDEF12345", "abcDEF12345"),
    ("https://www.youtube.com/watch?app=desktop&v=abcDEF12345&t=10", "abcDEF12345"),
    ("https://www.youtube.com/shorts/abcDEF12345", "abcDEF12345"),
    ("https://youtu.be/abcDEF12345", "abcDEF12345"),
    ("https://www.youtube.com/post/Ugkx", None),
    (None, None),
])
def test_video_id(url, vid):
    assert video_id(url) == vid


def test_summary():
    s = summarize_youtube(parse_youtube(load()))
    assert s["videos"] == 7 and s["ads"] == 1 and s["system"] == 1
    assert s["est_hours"] == round((12 + 5 + 5 + 5 + 20 + 0.92 + 5) / 60, 1)
    assert s["shorts"] == 1 and s["music"] == 1 and s["removed"] == 2 and s["sessions"] == 4
    assert len(s["top_channels"]) == 5 and all(c["videos"] == 1 for c in s["top_channels"])
    assert (s["first_date"], s["last_date"]) == ("2026-03-02", "2026-03-02")
    json.dumps(s)
