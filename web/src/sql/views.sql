-- Analysis-ready views over events. Idempotent (CREATE OR REPLACE).
-- "Late night" = local 23:00-02:59 everywhere. Days are calendar days in Asia/Kolkata.

-- Helper: events with the meta fields the views need pulled out of the JSON.
CREATE OR REPLACE VIEW event_facts AS
SELECT
    e.*,
    e.local_hour IN (23, 0, 1, 2)                                            AS is_late_night,
    json_extract_string(e.meta, '$.chat')                                    AS chat,
    json_extract_string(e.meta, '$.kind')                                    AS kind,
    TRY_CAST(json_extract_string(e.meta, '$.skipped') AS BOOLEAN)            AS skipped,
    coalesce(TRY_CAST(json_extract_string(e.meta, '$.is_ad') AS BOOLEAN), false) AS is_ad,
    TRY_CAST(json_extract_string(e.meta, '$.est_watch_min') AS DOUBLE)       AS est_watch_min
FROM events e;

-- Per source: coverage of the stored data.
CREATE OR REPLACE VIEW source_coverage AS
SELECT
    e.source,
    min(e.local_date)              AS first_date,
    max(e.local_date)              AS last_date,
    count(DISTINCT e.local_date)   AS days_with_data,
    count(*)                       AS events,
    max(i.last_import)             AS last_import
FROM events e
LEFT JOIN (SELECT source, max(imported_at) AS last_import FROM imports GROUP BY source) i
       ON i.source = e.source
GROUP BY e.source;

-- The date range covered by EVERY loaded source (intersection of first..last ranges).
-- Cross-app correlations are only computed inside this window. NULL dates = no overlap.
CREATE OR REPLACE VIEW overlap_window AS
SELECT
    CASE WHEN max(first_date) <= min(last_date) THEN max(first_date) END            AS start_date,
    CASE WHEN max(first_date) <= min(last_date) THEN min(last_date) END             AS end_date,
    CASE WHEN max(first_date) <= min(last_date)
         THEN date_diff('day', max(first_date), min(last_date)) + 1 ELSE 0 END     AS days,
    count(*)                                                                         AS sources,
    string_agg(source, ',' ORDER BY source)                                          AS source_list
FROM source_coverage;

-- Events per source x weekday x hour (system notices and date-only rows, i.e. bank, excluded).
CREATE OR REPLACE VIEW hourly_heatmap AS
SELECT source, weekday, local_hour AS hour, count(*) AS events
FROM events
WHERE event_type <> 'system' AND local_hour IS NOT NULL
GROUP BY source, weekday, local_hour;

-- One row per calendar day from the first to the last stored event (any source).
-- A source's columns are NULL on days outside its first..last coverage, and 0 (counts)
-- or NULL (shares/rates, which are undefined with no events) inside it on days with no events.
-- wa_sent / wa_received need settings 'me'; they are NULL until the user picks their name.
-- Bank: spend_total = sum of all debits (money out, incl. transfers and ATM cash),
-- received_total = sum of credits. food_delivery_spend stays NULL until bank categories exist.
CREATE OR REPLACE VIEW daily_activity AS
WITH
me AS (SELECT max(value) AS name FROM settings WHERE key = 'me'),
cov AS (SELECT source, first_date, last_date FROM source_coverage),
days AS (
    SELECT CAST(d AS DATE) AS local_date
    FROM (SELECT min(local_date) AS lo, max(local_date) AS hi FROM events) b,
         generate_series(b.lo, b.hi, INTERVAL 1 DAY) AS t(d)
    WHERE b.lo IS NOT NULL
),
sp AS (
    SELECT local_date,
           sum(value) / 60000.0                                      AS minutes,
           count(*)                                                  AS plays,
           avg(CASE WHEN skipped THEN 1.0 WHEN NOT skipped THEN 0.0 END) AS skip_rate,
           avg(CASE WHEN is_late_night THEN 1.0 ELSE 0.0 END)        AS late
    FROM event_facts
    WHERE source = 'spotify' AND event_type = 'play'
    GROUP BY local_date
),
yt AS (
    SELECT local_date,
           sum(est_watch_min)                                        AS minutes,
           count(*)                                                  AS videos,
           avg(CASE WHEN is_late_night THEN 1.0 ELSE 0.0 END)        AS late
    FROM event_facts
    WHERE source = 'youtube' AND event_type = 'watch' AND NOT is_ad
    GROUP BY local_date
),
bk AS (
    SELECT local_date,
           sum(-value) FILTER (WHERE value < 0)                      AS spend,
           count(*) FILTER (WHERE value < 0)                         AS spend_n,
           sum(value) FILTER (WHERE value > 0)                       AS received,
           sum(-value) FILTER (WHERE value < 0 AND category = 'food_delivery') AS food_delivery
    FROM events
    WHERE source = 'bank' AND event_type = 'transaction'
    GROUP BY local_date
),
bank_categorised AS (
    SELECT count(*) > 0 AS yes FROM events WHERE source = 'bank' AND category IS NOT NULL
),
wa AS (
    SELECT f.local_date,
           count(*) FILTER (WHERE f.actor = me.name)                 AS sent,
           count(*) FILTER (WHERE f.actor <> me.name)                AS received,
           avg(CASE WHEN f.is_late_night THEN 1.0 ELSE 0.0 END)      AS late,
           count(DISTINCT f.chat)                                    AS chats
    FROM event_facts f, me
    WHERE f.source = 'whatsapp' AND f.event_type = 'message'
    GROUP BY f.local_date
)
SELECT
    d.local_date,
    CASE WHEN d.local_date BETWEEN csp.first_date AND csp.last_date THEN coalesce(sp.minutes, 0) END AS spotify_minutes,
    CASE WHEN d.local_date BETWEEN csp.first_date AND csp.last_date THEN coalesce(sp.plays, 0) END   AS spotify_plays,
    sp.skip_rate                                                                                     AS skip_rate,
    sp.late                                                                                          AS spotify_late_night_share,
    CASE WHEN d.local_date BETWEEN cyt.first_date AND cyt.last_date THEN coalesce(yt.minutes, 0) END AS youtube_est_minutes,
    CASE WHEN d.local_date BETWEEN cyt.first_date AND cyt.last_date THEN coalesce(yt.videos, 0) END  AS youtube_videos,
    yt.late                                                                                          AS youtube_late_night_share,
    CASE WHEN d.local_date BETWEEN cwa.first_date AND cwa.last_date AND me.name IS NOT NULL
         THEN coalesce(wa.sent, 0) END                                                               AS wa_sent,
    CASE WHEN d.local_date BETWEEN cwa.first_date AND cwa.last_date AND me.name IS NOT NULL
         THEN coalesce(wa.received, 0) END                                                           AS wa_received,
    wa.late                                                                                          AS wa_late_night_share,
    CASE WHEN d.local_date BETWEEN cwa.first_date AND cwa.last_date THEN coalesce(wa.chats, 0) END   AS wa_active_chats,
    CASE WHEN d.local_date BETWEEN cbk.first_date AND cbk.last_date THEN coalesce(bk.spend, 0) END   AS spend_total,
    CASE WHEN d.local_date BETWEEN cbk.first_date AND cbk.last_date THEN coalesce(bk.spend_n, 0) END AS spend_txn_count,
    CASE WHEN d.local_date BETWEEN cbk.first_date AND cbk.last_date THEN coalesce(bk.received, 0) END AS received_total,
    CASE WHEN d.local_date BETWEEN cbk.first_date AND cbk.last_date AND bc.yes
         THEN coalesce(bk.food_delivery, 0) END                                                      AS food_delivery_spend,
    isodow(d.local_date) >= 6                                                                        AS is_weekend
FROM days d
CROSS JOIN me
CROSS JOIN bank_categorised bc
LEFT JOIN cov csp ON csp.source = 'spotify'
LEFT JOIN cov cyt ON cyt.source = 'youtube'
LEFT JOIN cov cwa ON cwa.source = 'whatsapp'
LEFT JOIN cov cbk ON cbk.source = 'bank'
LEFT JOIN sp ON sp.local_date = d.local_date
LEFT JOIN yt ON yt.local_date = d.local_date
LEFT JOIN wa ON wa.local_date = d.local_date
LEFT JOIN bk ON bk.local_date = d.local_date
ORDER BY d.local_date;
