"""The dashboard's SQL (web/src/sql/dashboard.sql) on the full demo database: every block runs,
and the numbers agree with the underlying tables (shares sum to 1, KPIs = sums of daily rows, ...)."""

import pytest

import demo_pipeline as dp
from sqlkit import named, set_vars

Q = named("dashboard")
FULL = ("2025-11-17", "2026-11-16")


@pytest.fixture(scope="module")
def con():
    return dp.build()


def run(con, name, frm=FULL[0], to=FULL[1], **extra):
    set_vars(con, range_from=frm, range_to=to, **extra)
    cur = con.execute(Q[name])
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


@pytest.mark.parametrize("name", [n for n in Q if not n.startswith("day_")])
def test_every_block_runs(con, name):
    run(con, name)


@pytest.mark.parametrize("name", [n for n in Q if n.startswith("day_")])
def test_day_blocks_run(con, name):
    assert run(con, name, day="2026-05-12")


def test_kpis_match_daily_rows(con):
    k = run(con, "dash_kpis", "2026-05-01", "2026-05-30")[0]
    assert k["days"] == 30 and k["prev_from"] == "2026-04-01" and k["prev_to"] == "2026-04-30"
    total = con.execute("SELECT sum(spotify_minutes)/60, sum(wa_sent), sum(discretionary_spend) FROM daily_features "
                        "WHERE local_date BETWEEN '2026-05-01' AND '2026-05-30'").fetchone()
    assert k["listen_h"] == pytest.approx(total[0]) and k["sent"] == total[1]
    assert k["discretionary"] == pytest.approx(total[2])
    assert k["listen_prev_full"] and k["bank_prev_full"]
    # the period before the first day has no data -> no delta
    first = run(con, "dash_kpis")[0]
    assert first["listen_h_prev"] is None and not first["listen_prev_full"]


def test_top_category_and_spark(con):
    t = run(con, "dash_top_category")[0]
    table = run(con, "money_category_table")
    disc = [r for r in table if r["discretionary"]]
    assert t["category"] == max(disc, key=lambda r: r["spend"])["category"]
    assert t["discretionary"] == pytest.approx(sum(r["spend"] for r in disc))
    assert sum(r["share"] for r in table) == pytest.approx(1)
    assert len(run(con, "dash_spark", "2026-05-01", "2026-05-30")) == 30          # daily
    assert len(run(con, "dash_spark")) <= 54                                    # weekly


def test_shares_sum_to_one(con):
    for name, key in [("music_mood_weekly", "week"), ("yt_topic_weekly", "week")]:
        rows = run(con, name)
        by = {}
        for r in rows:
            by[r[key]] = by.get(r[key], 0) + r["share"]
        assert all(v == pytest.approx(1) for v in by.values()), name
    assert sum(r["share"] for r in run(con, "music_language")) == pytest.approx(1)


def test_timeline_rolling_mean(con):
    rows = [r for r in run(con, "dash_timeline", "2026-05-01", "2026-05-30") if r["metric"] == "spotify_minutes"]
    assert len(rows) == 30
    vals = con.execute("SELECT spotify_minutes FROM daily_features WHERE local_date BETWEEN '2026-04-24' AND "
                       "'2026-04-30' OR local_date = '2026-05-01' ORDER BY local_date").fetchall()
    assert rows[0]["rolling7"] == pytest.approx(sum(v[0] for v in vals[-7:]) / 7)


def test_chats_top5_and_no_text(con):
    rows = run(con, "chat_weekly_top5")
    assert len({r["chat"] for r in rows}) == 5
    day = run(con, "day_chats", day="2026-05-12")
    assert day and all("text" not in r for r in day)
    assert all(r["sent"] + r["received"] == r["messages"] for r in day)
    sent = sum(r["sent"] for r in day)
    assert sent == con.execute("SELECT wa_sent FROM daily_features WHERE local_date = '2026-05-12'").fetchone()[0]
    s = run(con, "chat_sentiment_weekly")
    assert s and all(r["lo"] <= r["mean"] <= r["hi"] for r in s)


def test_sources_and_empty_range(con):
    src = {r["source"]: r for r in run(con, "dash_sources")}
    assert all(src[s]["loaded"] and src[s]["events_in_range"] > 0 for s in ("spotify", "youtube", "whatsapp", "bank"))
    empty = {r["source"]: r for r in run(con, "dash_sources", "2030-01-01", "2030-01-31")}
    assert all(r["events_in_range"] == 0 for r in empty.values())
    assert run(con, "music_top_artists", "2030-01-01", "2030-01-31") == []
