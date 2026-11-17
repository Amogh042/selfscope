"""SQL storage tests: web/src/sql/*.sql run with the duckdb Python package (same DuckDB
version as the browser) on the synthetic demo data in data/samples."""

import json
import re
from pathlib import Path

import pytest

from parsers.sbi import parse_sbi
from parsers.spotify import parse_spotify
from parsers.whatsapp import chat_name_from_filename, parse_whatsapp, read_export
from parsers.youtube import parse_youtube
from sqlkit import connect, import_df, named, scalar, set_vars, sql

SAMPLES = Path(__file__).resolve().parents[4] / "data" / "samples"
FIX = Path(__file__).parent / "fixtures" / "spotify"

# Expected from step 2/3 (see data/samples/README.md)
WA_EVENTS, WA_MESSAGES, SP_PLAYS, YT_ENTRIES, YT_VIDEOS = 20_780, 20_769, 11_761, 7_802, 7_378
BANK_TXNS = 2_629


def demo_frames():
    """[(source, file name, DataFrame)] for every demo file, parsed like the app does."""
    out = []
    for f in sorted((SAMPLES / "whatsapp").iterdir()):
        text = read_export(f.read_bytes(), f.name)
        out.append(("whatsapp", f.name, parse_whatsapp(text, chat_name=chat_name_from_filename(f.name))))
    for f in sorted((SAMPLES / "spotify").glob("*.json")):
        out.append(("spotify", f.name, parse_spotify({f.name: f.read_text(encoding="utf-8")})))
    yt = SAMPLES / "google" / "Takeout" / "YouTube and YouTube Music" / "history" / "watch-history.json"
    out.append(("youtube", yt.name, parse_youtube(yt.read_text(encoding="utf-8"))))
    bank = SAMPLES / "bank" / "SBI_statement_demo.xlsx"
    out.append(("bank", bank.name, parse_sbi(bank.read_bytes(), bank.name)))
    return out


@pytest.fixture(scope="module")
def frames():
    return demo_frames()


@pytest.fixture()
def demo(frames):
    con = connect()
    results = [import_df(con, df, src, name) for src, name, df in frames]
    return con, results


def count(con, source=None):
    if source is None:
        return scalar(con, "SELECT count(*) FROM events")
    return scalar(con, "SELECT count(*) FROM events WHERE source = ?", source)


# ---------------------------------------------------------------- import + dedupe

def test_demo_row_counts_match_step3(demo):
    con, results = demo
    assert count(con, "whatsapp") == WA_EVENTS
    assert count(con, "spotify") == SP_PLAYS
    assert count(con, "youtube") == YT_ENTRIES
    assert count(con, "bank") == BANK_TXNS
    assert sum(r["rows_added"] for r in results) == count(con)
    assert all(r["rows_skipped"] == 0 for r in results)
    assert scalar(con, "SELECT count(*) FROM imports") == 9
    assert scalar(con, "SELECT count(*) FROM events WHERE source = 'bank' AND local_hour IS NOT NULL") == 0
    assert scalar(con, "SELECT count(DISTINCT event_key) FROM events") == count(con)  # keys are unique


def test_reimporting_every_file_adds_zero_rows(demo, frames):
    con, _ = demo
    before = count(con)
    for src, name, df in frames:
        r = import_df(con, df, src, name)
        assert r["rows_added"] == 0 and r["rows_skipped"] == len(df), name
    assert count(con) == before


def test_newer_overlapping_whatsapp_export_adds_only_new_messages():
    f = SAMPLES / "whatsapp" / "WhatsApp Chat with Priya.txt"
    lines = f.read_text(encoding="utf-8").splitlines(keepends=True)
    # cut at a message header (continuation lines like "1. charger" also start with a digit)
    cut = next(i for i in range(int(len(lines) * 0.7), len(lines))
               if re.match(r"^\d{2}/\d{2}/\d{2}, \d{1,2}:\d{2}", lines[i]))
    old, new = "".join(lines[:cut]), "".join(lines)
    con = connect()
    first = import_df(con, parse_whatsapp(old, chat_name="Priya"), "whatsapp", "old.txt")
    full = parse_whatsapp(new, chat_name="Priya")
    second = import_df(con, full, "whatsapp", "new.txt")
    assert second["rows_added"] == len(full) - first["rows_added"]
    assert second["rows_skipped"] == first["rows_added"]
    assert count(con) == len(full)


def test_identical_messages_in_the_same_minute_are_kept():
    text = "17/11/25, 9:41 pm - Priya: ok\n17/11/25, 9:41 pm - Priya: ok\n17/11/25, 9:41 pm - Priya: ok\n"
    con = connect()
    assert import_df(con, parse_whatsapp(text, chat_name="Priya"), "whatsapp", "a.txt")["rows_added"] == 3
    assert import_df(con, parse_whatsapp(text, chat_name="Priya"), "whatsapp", "a.txt")["rows_added"] == 0


def test_csv_fallback_gives_identical_events(frames):
    a, b = connect(), connect()
    for src, name, df in frames[:3]:  # includes the iOS chat (multi-line, U+200E, emoji)
        import_df(a, df, src, name, fmt="parquet")
        import_df(b, df, src, name, fmt="csv")
    q = "SELECT * EXCLUDE (import_id) FROM events ORDER BY event_key"
    assert a.execute(q).fetchall() == b.execute(q).fetchall()


# ---------------------------------------------------------------- Spotify cross-format

def spotify_file(name):
    return parse_spotify({name: (FIX / name).read_text(encoding="utf-8")})


ACCOUNT = ["StreamingHistory_music_0.json", "StreamingHistory_music_1.json", "StreamingHistory_podcast_0.json"]
EXTENDED = "Streaming_History_Audio_2025-2026_0.json"


@pytest.mark.parametrize("extended_first", [False, True])
def test_spotify_cross_format_keeps_extended_row(extended_first):
    con = connect()
    order = [EXTENDED, *ACCOUNT] if extended_first else [*ACCOUNT, EXTENDED]
    for name in order:
        import_df(con, spotify_file(name), "spotify", name)
    # account: Kesariya, Raabta, Perfect, Mungaru Maleye, podcast (5 after exact-dup removal)
    # extended: Kesariya, Raabta, Tum Hi Ho, podcast, unknown, Perfect w/o artist (6)
    # Kesariya (30 s apart) and Raabta (20 s apart) exist in both -> 9 rows
    assert count(con, "spotify") == 9
    rows = con.execute("""SELECT title, json_extract_string(meta, '$.format') FROM events
                          WHERE title IN ('Kesariya', 'Raabta') ORDER BY title""").fetchall()
    assert rows == [("Kesariya", "extended"), ("Raabta", "extended")]


def test_spotify_cross_format_window_is_60_seconds():
    account = json.dumps([{"endTime": "2025-11-20 10:00", "artistName": "X", "trackName": "Y", "msPlayed": 200000},
                          {"endTime": "2025-11-21 10:00", "artistName": "X", "trackName": "Y", "msPlayed": 200000}])
    extended = json.dumps([{"ts": "2025-11-20T10:00:59Z", "ms_played": 200000, "master_metadata_track_name": "Y",
                            "master_metadata_album_artist_name": "X"},
                           {"ts": "2025-11-21T10:02:00Z", "ms_played": 200000, "master_metadata_track_name": "Y",
                            "master_metadata_album_artist_name": "X"}])
    con = connect()
    import_df(con, parse_spotify({"a.json": account}), "spotify", "a.json")
    import_df(con, parse_spotify({"e.json": extended}), "spotify", "e.json")
    # 59 s apart -> merged; 120 s apart -> both kept
    assert count(con, "spotify") == 3


# ---------------------------------------------------------------- views

def test_daily_activity_has_365_rows_for_the_demo_year(demo):
    con, _ = demo
    rows = con.execute("SELECT count(*), min(local_date)::VARCHAR, max(local_date)::VARCHAR, "
                       "sum(is_weekend::INT), sum(spotify_plays), sum(youtube_videos), "
                       "count(wa_sent) FROM daily_activity").fetchone()
    assert rows == (365, "2025-11-17", "2026-11-16", 104, SP_PLAYS, YT_VIDEOS, 0)  # wa_sent NULL until 'me' set


def test_daily_activity_whatsapp_after_choosing_me(demo):
    con, _ = demo
    set_vars(con, me="Amogh")
    con.execute(named("manage")["set_me"])
    sent, received, chats = con.execute(
        "SELECT sum(wa_sent), sum(wa_received), max(wa_active_chats) FROM daily_activity").fetchone()
    assert sent + received == WA_MESSAGES
    assert sent == scalar(con, "SELECT count(*) FROM events WHERE actor = 'Amogh' AND event_type = 'message'")
    assert chats == 5
    shares = con.execute("SELECT min(spotify_late_night_share), max(wa_late_night_share), "
                         "min(skip_rate), max(skip_rate) FROM daily_activity").fetchone()
    assert all(0 <= s <= 1 for s in shares)


def test_daily_activity_nulls_outside_a_sources_coverage():
    con = connect()
    sp = parse_spotify({"s.json": json.dumps([
        {"endTime": "2025-11-17 10:00", "artistName": "X", "trackName": "Y", "msPlayed": 60000},
        {"endTime": "2025-11-20 10:00", "artistName": "X", "trackName": "Y", "msPlayed": 60000}])})
    import_df(con, sp, "spotify", "s.json")
    yt = parse_youtube(json.dumps([{"header": "YouTube", "title": "Watched V", "time": "2025-11-22T10:00:00Z"}]))
    import_df(con, yt, "youtube", "y.json")
    rows = con.execute("SELECT local_date::VARCHAR, spotify_plays, youtube_videos FROM daily_activity").fetchall()
    assert rows == [("2025-11-17", 1, None), ("2025-11-18", 0, None), ("2025-11-19", 0, None),
                    ("2025-11-20", 1, None), ("2025-11-21", None, None), ("2025-11-22", None, 1)]


def test_overlap_window_and_coverage(demo):
    con, _ = demo
    assert con.execute("SELECT start_date::VARCHAR, end_date::VARCHAR, days, sources, source_list "
                       "FROM overlap_window").fetchone() == ("2025-11-17", "2026-11-16", 365, 4,
                                                             "bank,spotify,whatsapp,youtube")
    cov = {r[0]: r[1:] for r in con.execute("SELECT source, days_with_data, events FROM source_coverage").fetchall()}
    assert cov["spotify"] == (365, SP_PLAYS) and cov["youtube"][1] == YT_ENTRIES


def test_overlap_window_empty_when_ranges_do_not_meet():
    con = connect()
    import_df(con, parse_youtube(json.dumps([{"title": "Watched A", "time": "2025-01-01T10:00:00Z"}])), "youtube", "y")
    import_df(con, parse_spotify(json.dumps([{"endTime": "2025-03-01 10:00", "artistName": "X", "trackName": "Y",
                                              "msPlayed": 1}])), "spotify", "s")
    assert con.execute("SELECT start_date, end_date, days, sources FROM overlap_window").fetchone() == (None, None, 0, 2)


def test_hourly_heatmap_counts_all_non_system_events(demo):
    con, _ = demo
    total = scalar(con, "SELECT sum(events) FROM hourly_heatmap")
    assert total == scalar(con, "SELECT count(*) FROM events WHERE event_type <> 'system' AND source <> 'bank'")
    assert scalar(con, "SELECT count(*) FROM hourly_heatmap WHERE hour NOT BETWEEN 0 AND 23 "
                       "OR weekday NOT BETWEEN 0 AND 6") == 0


# ---------------------------------------------------------------- data manager

def test_remove_import_and_wipe(demo):
    con, results = demo
    priya = next(r for r in results if r["file_name"] == "WhatsApp Chat with Priya.txt")
    before = count(con, "whatsapp")
    set_vars(con, import_id=priya["import_id"])
    con.execute(named("manage")["remove_import"])
    assert count(con, "whatsapp") == before - priya["rows_added"]
    assert scalar(con, "SELECT count(*) FROM imports") == 8
    con.execute(named("manage")["wipe_all"])
    assert count(con) == 0 and scalar(con, "SELECT count(*) FROM daily_activity") == 0


def test_all_named_queries_run(demo):
    con, _ = demo
    set_vars(con, preview_source="whatsapp", preview_chat="Priya", file_hash="x")
    for name, q in named("queries").items():
        con.execute(q).fetchall()
    preview = con.execute(named("queries")["preview"]).fetchall()
    assert len(preview) == 20
    assert len(con.execute(named("queries")["bank_top_spend"]).fetchall()) == 10
    chats = con.execute(named("queries")["whatsapp_chats"]).fetchall()
    assert len(chats) == 5 and sum(c[2] for c in chats) == WA_MESSAGES


def test_reset_then_schema_is_idempotent(demo):
    con, _ = demo
    con.execute(named("manage")["reset"])
    con.execute(sql("schema"))
    con.execute(sql("schema"))
    con.execute(sql("views"))
    assert count(con) == 0


# ---------------------------------------------------------------- bank

def test_bank_columns_in_daily_activity(demo):
    con, _ = demo
    spent, received, n, fd, nulls = con.execute(
        "SELECT sum(spend_total), sum(received_total), sum(spend_txn_count), count(food_delivery_spend), "
        "count(*) FILTER (WHERE spend_total IS NULL) FROM daily_activity").fetchone()
    assert spent == pytest.approx(-scalar(con, "SELECT sum(value) FROM events WHERE source='bank' AND value < 0"))
    assert received == pytest.approx(scalar(con, "SELECT sum(value) FROM events WHERE source='bank' AND value > 0"))
    assert n == scalar(con, "SELECT count(*) FROM events WHERE source='bank' AND value < 0")
    assert fd == 0 and nulls == 0  # no categories yet -> NULL; bank covers every demo day
    # once any bank row is categorised, food_delivery_spend becomes a number (0 on days without)
    con.execute("UPDATE events SET category = 'food_delivery' WHERE source = 'bank' AND actor IN ('SWIGGY', 'ZOMATO')")
    total, filled = con.execute("SELECT sum(food_delivery_spend), count(food_delivery_spend) FROM daily_activity").fetchone()
    assert filled == 365 and total == pytest.approx(
        -scalar(con, "SELECT sum(value) FROM events WHERE actor IN ('SWIGGY', 'ZOMATO')"))


def test_bank_spend_null_outside_coverage():
    con = connect()
    text = ("Txn Date,Value Date,Description,Ref No./Cheque No.,Debit,Credit,Balance\n"
            "3 Mar 2026,3 Mar 2026,TO TRANSFER-UPI/DR/512345678901/RAJU TEA/PYTM/paytmqr1y7/UPI-, ,25.00, ,975.00\n"
            "5 Mar 2026,5 Mar 2026,BY TRANSFER-UPI/CR/512345678902/SURESH K/SBIN/sureshkuma/UPI-, , ,100.00,1075.00\n")
    import_df(con, parse_sbi(text, "s.csv"), "bank", "s.csv")
    yt = parse_youtube(json.dumps([{"title": "Watched V", "time": "2026-03-06T10:00:00Z"}]))
    import_df(con, yt, "youtube", "y.json")
    rows = con.execute("SELECT local_date::VARCHAR, spend_total, spend_txn_count, received_total "
                       "FROM daily_activity").fetchall()
    assert rows == [("2026-03-03", 25.0, 1, 0.0), ("2026-03-04", 0.0, 0, 0.0),
                    ("2026-03-05", 0.0, 0, 100.0), ("2026-03-06", None, None, None)]


def test_bank_reimport_and_overlapping_statement(frames):
    con = connect()
    _, name, df = next(f for f in frames if f[0] == "bank")
    first = import_df(con, df.iloc[:1500], "bank", "older.xlsx")
    second = import_df(con, df, "bank", name)
    assert (first["rows_added"], second["rows_added"], second["rows_skipped"]) == (1500, BANK_TXNS - 1500, 1500)
    assert import_df(con, df, "bank", name)["rows_added"] == 0
    assert count(con, "bank") == BANK_TXNS
