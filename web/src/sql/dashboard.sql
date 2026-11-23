-- Read queries for the dashboard (#/dashboard). All take range_from / range_to (YYYY-MM-DD,
-- inclusive); the drill-down queries take `day`. Weeks start on Monday. Times shown to the user
-- are local (Asia/Kolkata = UTC+05:30, as in the parsers). Tested in src/python/tests/test_dashboard.py.

-- name: dash_sources
-- Per source: is it loaded at all, and how many events fall in the range.
SELECT s.source,
       c.events IS NOT NULL                                         AS loaded,
       coalesce(r.events, 0)                                        AS events_in_range,
       CAST(c.first_date AS VARCHAR)                                AS first_date,
       CAST(c.last_date AS VARCHAR)                                 AS last_date
FROM (VALUES ('spotify'), ('youtube'), ('whatsapp'), ('bank')) s(source)
LEFT JOIN source_coverage c ON c.source = s.source
LEFT JOIN (SELECT source, count(*) AS events FROM events
           WHERE local_date BETWEEN CAST(getvariable('range_from') AS DATE) AND CAST(getvariable('range_to') AS DATE)
           GROUP BY source) r ON r.source = s.source;

-- name: dash_kpis
-- Player stats for the range and for the previous period of the same length (NULL = no data).
WITH r AS (
    SELECT CAST(getvariable('range_from') AS DATE) AS f, CAST(getvariable('range_to') AS DATE) AS t
), p AS (
    SELECT f, t, f - CAST(date_diff('day', f, t) + 1 AS INTEGER) AS pf, f - 1 AS pt,
           date_diff('day', f, t) + 1 AS days FROM r
), agg AS (
    SELECT (local_date BETWEEN p.f AND p.t) AS cur,
           sum(spotify_minutes) / 60.0    AS listen_h,
           sum(youtube_est_minutes) / 60.0 AS youtube_h,
           sum(wa_sent)                   AS sent,
           sum(discretionary_spend)       AS discretionary,
           count(spotify_minutes)         AS days_spotify,
           count(youtube_est_minutes)     AS days_youtube,
           count(wa_sent)                 AS days_sent,
           count(discretionary_spend)     AS days_bank
    FROM daily_features, p
    WHERE local_date BETWEEN p.pf AND p.t
    GROUP BY ALL
)
SELECT (SELECT days FROM p) AS days,
       CAST((SELECT pf FROM p) AS VARCHAR) AS prev_from, CAST((SELECT pt FROM p) AS VARCHAR) AS prev_to,
       max(listen_h) FILTER (cur)          AS listen_h,      max(listen_h) FILTER (NOT cur)      AS listen_h_prev,
       max(youtube_h) FILTER (cur)         AS youtube_h,     max(youtube_h) FILTER (NOT cur)     AS youtube_h_prev,
       max(sent) FILTER (cur)              AS sent,          max(sent) FILTER (NOT cur)          AS sent_prev,
       max(discretionary) FILTER (cur)     AS discretionary, max(discretionary) FILTER (NOT cur) AS discretionary_prev,
       -- a delta is only shown when the previous period is fully covered by that source
       max(days_spotify) FILTER (NOT cur) = (SELECT days FROM p) AS listen_prev_full,
       max(days_youtube) FILTER (NOT cur) = (SELECT days FROM p) AS youtube_prev_full,
       max(days_sent) FILTER (NOT cur) = (SELECT days FROM p)    AS sent_prev_full,
       max(days_bank) FILTER (NOT cur) = (SELECT days FROM p)    AS bank_prev_full
FROM agg;

-- name: dash_top_category
-- Biggest discretionary spend category in the range, and the same category's spend in the previous period.
WITH r AS (
    SELECT CAST(getvariable('range_from') AS DATE) AS f, CAST(getvariable('range_to') AS DATE) AS t
), p AS (
    SELECT f, t, f - CAST(date_diff('day', f, t) + 1 AS INTEGER) AS pf, f - 1 AS pt FROM r
), d AS (
    SELECT category, local_date BETWEEN p.f AND p.t AS cur, -value AS spend
    FROM events, p
    WHERE source = 'bank' AND value < 0 AND category IS NOT NULL
      AND category NOT IN ('p2p_transfer', 'cash_atm', 'subscriptions')
      AND local_date BETWEEN p.pf AND p.t
), top AS (
    SELECT category, sum(spend) AS spend FROM d WHERE cur GROUP BY category ORDER BY spend DESC, category LIMIT 1
)
SELECT top.category, top.spend,
       (SELECT sum(spend) FROM d WHERE cur) AS discretionary,
       (SELECT sum(spend) FROM d WHERE NOT cur AND d.category = top.category) AS spend_prev
FROM top;

-- name: dash_spark
-- Sparkline points: daily for ranges up to 92 days, weekly sums otherwise.
WITH r AS (
    SELECT CAST(getvariable('range_from') AS DATE) AS f, CAST(getvariable('range_to') AS DATE) AS t
)
SELECT CAST(CASE WHEN date_diff('day', r.f, r.t) < 92 THEN local_date ELSE date_trunc('week', local_date) END AS DATE)::VARCHAR AS bucket,
       sum(spotify_minutes) / 60.0     AS listen_h,
       sum(youtube_est_minutes) / 60.0 AS youtube_h,
       sum(wa_sent)                    AS sent,
       sum(discretionary_spend)        AS discretionary
FROM daily_features, r
WHERE local_date BETWEEN r.f AND r.t
GROUP BY bucket
ORDER BY bucket;

-- name: dash_timeline
-- Long format: one row per day x metric, with the 7-day rolling mean (days before the range
-- count towards the first rolling values). NULL values = no data for that source that day.
WITH long AS (
    UNPIVOT (SELECT local_date, * EXCLUDE (local_date, is_weekend) FROM daily_features)
    ON COLUMNS(* EXCLUDE (local_date)) INTO NAME metric VALUE value
), rolled AS (
    SELECT local_date, metric, value,
           avg(value) OVER (PARTITION BY metric ORDER BY local_date
                            RANGE BETWEEN INTERVAL 6 DAYS PRECEDING AND CURRENT ROW) AS rolling7
    FROM long
)
SELECT CAST(local_date AS VARCHAR) AS local_date, metric, CAST(value AS DOUBLE) AS value, rolling7
FROM rolled
WHERE local_date BETWEEN CAST(getvariable('range_from') AS DATE) AND CAST(getvariable('range_to') AS DATE)
ORDER BY metric, local_date;

-- name: dash_daily
-- daily_features rows in the range (wide) + 2 days after it (for lagged pairs), for scatter
-- plots and the day summary.
SELECT CAST(local_date AS VARCHAR) AS local_date, * EXCLUDE (local_date)
FROM daily_features
WHERE local_date BETWEEN CAST(getvariable('range_from') AS DATE) AND CAST(getvariable('range_to') AS DATE) + 2
ORDER BY local_date;

-- ---------------------------------------------------------------- music

-- name: music_top_artists
SELECT actor AS artist, count(*) AS plays, sum(value) / 60000.0 AS minutes
FROM events
WHERE source = 'spotify' AND actor IS NOT NULL
  AND local_date BETWEEN CAST(getvariable('range_from') AS DATE) AND CAST(getvariable('range_to') AS DATE)
GROUP BY actor
ORDER BY plays DESC, artist
LIMIT 10;

-- name: music_mood_weekly
-- Share of plays per mood per week, among plays with a KNOWN mood (unknown is never guessed).
SELECT CAST(wk AS VARCHAR) AS week, mood, plays, plays / sum(plays) OVER (PARTITION BY wk) AS share
FROM (SELECT CAST(date_trunc('week', local_date) AS DATE) AS wk, category AS mood, count(*) AS plays
      FROM events
      WHERE source = 'spotify' AND category IN ('romantic', 'sad', 'upbeat')
        AND local_date BETWEEN CAST(getvariable('range_from') AS DATE) AND CAST(getvariable('range_to') AS DATE)
      GROUP BY wk, mood)
ORDER BY week, mood;

-- name: music_language
SELECT coalesce(json_extract_string(meta, '$.language'), 'unknown') AS language, count(*) AS plays,
       count(*) / sum(count(*)) OVER () AS share
FROM events
WHERE source = 'spotify'
  AND local_date BETWEEN CAST(getvariable('range_from') AS DATE) AND CAST(getvariable('range_to') AS DATE)
GROUP BY language
ORDER BY plays DESC;

-- name: music_sad_by_hour
SELECT local_hour AS hour, count(*) AS known_plays,
       count(*) FILTER (WHERE category = 'sad') / count(*) AS sad_share
FROM events
WHERE source = 'spotify' AND category IN ('romantic', 'sad', 'upbeat')
  AND local_date BETWEEN CAST(getvariable('range_from') AS DATE) AND CAST(getvariable('range_to') AS DATE)
GROUP BY local_hour
ORDER BY hour;

-- ---------------------------------------------------------------- youtube

-- name: yt_topic_weekly
-- Share of estimated watch time per topic per week (ads excluded).
SELECT CAST(wk AS VARCHAR) AS week, topic, minutes, minutes / nullif(sum(minutes) OVER (PARTITION BY wk), 0) AS share
FROM (SELECT CAST(date_trunc('week', local_date) AS DATE) AS wk, coalesce(category, 'other') AS topic,
             sum(est_watch_min) AS minutes
      FROM event_facts
      WHERE source = 'youtube' AND event_type = 'watch' AND NOT is_ad
        AND local_date BETWEEN CAST(getvariable('range_from') AS DATE) AND CAST(getvariable('range_to') AS DATE)
      GROUP BY wk, topic)
ORDER BY week, topic;

-- name: yt_heatmap
SELECT weekday, local_hour AS hour, count(*) AS videos
FROM event_facts
WHERE source = 'youtube' AND event_type = 'watch' AND NOT is_ad
  AND local_date BETWEEN CAST(getvariable('range_from') AS DATE) AND CAST(getvariable('range_to') AS DATE)
GROUP BY weekday, hour
ORDER BY weekday, hour;

-- name: yt_top_channels
SELECT actor AS channel, count(*) AS videos, sum(est_watch_min) AS minutes, mode(category) AS topic
FROM event_facts
WHERE source = 'youtube' AND event_type = 'watch' AND NOT is_ad AND actor IS NOT NULL
  AND local_date BETWEEN CAST(getvariable('range_from') AS DATE) AND CAST(getvariable('range_to') AS DATE)
GROUP BY actor
ORDER BY minutes DESC, channel
LIMIT 10;

-- ---------------------------------------------------------------- chats

-- name: chat_weekly_top5
-- Messages per week for the 5 busiest chats in the range (counts only).
WITH m AS (
    SELECT chat, local_date FROM event_facts
    WHERE source = 'whatsapp' AND event_type = 'message'
      AND local_date BETWEEN CAST(getvariable('range_from') AS DATE) AND CAST(getvariable('range_to') AS DATE)
), top AS (
    SELECT chat FROM m GROUP BY chat ORDER BY count(*) DESC, chat LIMIT 5
)
SELECT CAST(date_trunc('week', local_date) AS DATE)::VARCHAR AS week, chat, count(*) AS messages
FROM m WHERE chat IN (SELECT chat FROM top)
GROUP BY ALL
ORDER BY week, chat;

-- name: chat_sentiment_weekly
-- The user's own messages: weekly mean sentiment with a 95% confidence band (mean ± 1.96 SE).
-- Empty until the user has picked their name (settings 'me').
SELECT CAST(date_trunc('week', local_date) AS DATE)::VARCHAR AS week, count(*) AS messages,
       avg(s) AS mean, avg(s) - 1.96 * stddev_samp(s) / sqrt(count(*)) AS lo,
       avg(s) + 1.96 * stddev_samp(s) / sqrt(count(*)) AS hi
FROM (SELECT local_date, TRY_CAST(json_extract_string(meta, '$.sentiment') AS DOUBLE) AS s
      FROM events
      WHERE source = 'whatsapp' AND event_type = 'message'
        AND actor = (SELECT value FROM settings WHERE key = 'me')
        AND local_date BETWEEN CAST(getvariable('range_from') AS DATE) AND CAST(getvariable('range_to') AS DATE))
WHERE s IS NOT NULL
GROUP BY week
ORDER BY week;

-- name: chat_late_weekly
SELECT CAST(date_trunc('week', local_date) AS DATE)::VARCHAR AS week, count(*) AS messages,
       avg(CASE WHEN is_late_night THEN 1.0 ELSE 0.0 END) AS late_share
FROM event_facts
WHERE source = 'whatsapp' AND event_type = 'message'
  AND local_date BETWEEN CAST(getvariable('range_from') AS DATE) AND CAST(getvariable('range_to') AS DATE)
GROUP BY week
ORDER BY week;

-- ---------------------------------------------------------------- money

-- name: money_monthly_category
-- Money out (debits, INR) per month and category; uncategorised rows count as 'other'.
SELECT CAST(date_trunc('month', local_date) AS DATE)::VARCHAR AS month, coalesce(category, 'other') AS category,
       sum(-value) AS spend
FROM events
WHERE source = 'bank' AND value < 0
  AND local_date BETWEEN CAST(getvariable('range_from') AS DATE) AND CAST(getvariable('range_to') AS DATE)
GROUP BY ALL
ORDER BY month, category;

-- name: money_category_table
SELECT coalesce(category, 'other') AS category, sum(-value) AS spend, count(*) AS txns,
       sum(-value) / sum(sum(-value)) OVER () AS share,
       coalesce(category, 'other') NOT IN ('p2p_transfer', 'cash_atm', 'subscriptions') AS discretionary
FROM events
WHERE source = 'bank' AND value < 0
  AND local_date BETWEEN CAST(getvariable('range_from') AS DATE) AND CAST(getvariable('range_to') AS DATE)
GROUP BY ALL
ORDER BY spend DESC;

-- name: money_daily_discretionary
SELECT CAST(local_date AS VARCHAR) AS local_date, discretionary_spend AS spend
FROM daily_features
WHERE discretionary_spend IS NOT NULL
  AND local_date BETWEEN CAST(getvariable('range_from') AS DATE) AND CAST(getvariable('range_to') AS DATE)
ORDER BY local_date;

-- name: money_top_payees
SELECT actor AS payee, mode(category) AS category, sum(-value) AS spend, count(*) AS txns
FROM events
WHERE source = 'bank' AND value < 0 AND actor IS NOT NULL
  AND local_date BETWEEN CAST(getvariable('range_from') AS DATE) AND CAST(getvariable('range_to') AS DATE)
GROUP BY actor
ORDER BY spend DESC, payee
LIMIT 10;

-- ---------------------------------------------------------------- day drill-down (variable: day)

-- name: day_songs
SELECT strftime(ts_utc + INTERVAL 330 MINUTE, '%H:%M') AS time, title, actor AS artist,
       coalesce(category, 'unknown') AS mood, json_extract_string(meta, '$.language') AS language,
       value / 60000.0 AS minutes
FROM events
WHERE source = 'spotify' AND local_date = CAST(getvariable('day') AS DATE)
ORDER BY ts_utc;

-- name: day_videos
SELECT strftime(ts_utc + INTERVAL 330 MINUTE, '%H:%M') AS time, title, actor AS channel,
       CASE WHEN is_ad THEN 'ad' ELSE coalesce(category, 'other') END AS topic, est_watch_min AS minutes
FROM event_facts
WHERE source = 'youtube' AND event_type = 'watch' AND local_date = CAST(getvariable('day') AS DATE)
ORDER BY ts_utc;

-- name: day_chats
-- Counts and mood per chat only: message text is never returned here.
SELECT chat, count(*) AS messages,
       count(*) FILTER (WHERE actor = (SELECT value FROM settings WHERE key = 'me')) AS sent,
       count(*) FILTER (WHERE actor <> (SELECT value FROM settings WHERE key = 'me')) AS received,
       count(*) FILTER (WHERE is_late_night) AS late_night,
       avg(TRY_CAST(json_extract_string(meta, '$.sentiment') AS DOUBLE)) AS mean_sentiment,
       count(*) FILTER (WHERE category = 'pos') AS positive,
       count(*) FILTER (WHERE category = 'neg') AS negative
FROM event_facts
WHERE source = 'whatsapp' AND event_type = 'message' AND local_date = CAST(getvariable('day') AS DATE)
GROUP BY chat
ORDER BY messages DESC, chat;

-- name: day_txns
SELECT actor AS payee, value AS amount, coalesce(category, 'other') AS category,
       json_extract_string(meta, '$.channel') AS channel
FROM events
WHERE source = 'bank' AND local_date = CAST(getvariable('day') AS DATE)
ORDER BY value, payee;
