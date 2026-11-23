-- Read-only queries used by the Import and Data screens. Named blocks ("-- name: x").
-- Dates are returned as VARCHAR (YYYY-MM-DD) so the UI gets plain strings.

-- name: bounds
SELECT CAST(min(local_date) AS VARCHAR) AS first_date, CAST(max(local_date) AS VARCHAR) AS last_date,
       count(*) AS events
FROM events;

-- name: me
SELECT max(value) AS me FROM settings WHERE key = 'me';

-- name: whatsapp_chats
SELECT
    chat,
    any_value(json_extract_string(meta, '$.platform'))                          AS platform,
    count(*) FILTER (WHERE event_type = 'message')                              AS messages,
    count(*) FILTER (WHERE kind = 'media')                                      AS media,
    count(*) FILTER (WHERE kind = 'deleted')                                    AS deleted,
    count(*) FILTER (WHERE event_type = 'system')                               AS system,
    count(DISTINCT actor) FILTER (WHERE event_type = 'message') > 2
        OR bool_or(event_type = 'system' AND text LIKE '%created group%')       AS is_group,
    CAST(min(local_date) AS VARCHAR)                                            AS first_date,
    CAST(max(local_date) AS VARCHAR)                                            AS last_date
FROM event_facts
WHERE source = 'whatsapp'
GROUP BY chat
ORDER BY messages DESC;

-- name: whatsapp_people
SELECT chat, actor, count(*) AS messages
FROM event_facts
WHERE source = 'whatsapp' AND event_type = 'message'
GROUP BY chat, actor
ORDER BY chat, messages DESC, actor;

-- name: spotify_summary
SELECT
    count(*)                                                         AS plays,
    count(*) FILTER (WHERE kind = 'music')                           AS music_plays,
    count(*) FILTER (WHERE kind = 'podcast')                         AS podcast_plays,
    round(sum(value) / 3.6e6, 1)                                     AS hours,
    avg(CASE WHEN skipped THEN 1.0 WHEN NOT skipped THEN 0.0 END)    AS skip_rate,
    count(DISTINCT actor) FILTER (WHERE kind = 'music')              AS artists,
    string_agg(DISTINCT json_extract_string(meta, '$.format'), ' + ') AS formats,
    CAST(min(local_date) AS VARCHAR)                                 AS first_date,
    CAST(max(local_date) AS VARCHAR)                                 AS last_date
FROM event_facts
WHERE source = 'spotify';

-- name: spotify_top_artists
SELECT actor AS name, count(*) AS plays, round(sum(value) / 3.6e6, 1) AS hours
FROM event_facts
WHERE source = 'spotify' AND kind = 'music' AND actor IS NOT NULL
GROUP BY actor
ORDER BY plays DESC, hours DESC, name
LIMIT 5;

-- name: spotify_top_tracks
SELECT title, actor AS artist, count(*) AS plays
FROM event_facts
WHERE source = 'spotify' AND kind = 'music' AND title IS NOT NULL
GROUP BY title, actor
ORDER BY plays DESC, title
LIMIT 5;

-- name: youtube_summary
SELECT
    count(*)                                                                    AS entries,
    count(*) FILTER (WHERE event_type = 'watch' AND NOT is_ad)                  AS videos,
    count(*) FILTER (WHERE event_type = 'watch' AND is_ad)                      AS ads,
    round(coalesce(sum(est_watch_min) FILTER (WHERE event_type = 'watch' AND NOT is_ad), 0) / 60, 1) AS est_hours,
    count(DISTINCT actor) FILTER (WHERE event_type = 'watch' AND NOT is_ad)     AS channels,
    count(*) FILTER (WHERE json_extract_string(meta, '$.is_short') = 'true' AND NOT is_ad) AS shorts,
    count(*) FILTER (WHERE json_extract_string(meta, '$.removed') = 'true'
                        OR json_extract_string(meta, '$.title_unavailable') = 'true') AS removed,
    count(*) FILTER (WHERE event_type = 'system')                               AS system,
    CAST(min(local_date) AS VARCHAR)                                            AS first_date,
    CAST(max(local_date) AS VARCHAR)                                            AS last_date
FROM event_facts
WHERE source = 'youtube';

-- name: youtube_top_channels
SELECT actor AS name, count(*) AS videos
FROM event_facts
WHERE source = 'youtube' AND event_type = 'watch' AND NOT is_ad AND actor IS NOT NULL
GROUP BY actor
ORDER BY videos DESC, name
LIMIT 5;

-- name: bank_summary
SELECT
    count(*)                                                         AS transactions,
    round(coalesce(sum(-value) FILTER (WHERE value < 0), 0), 2)      AS spent,
    round(coalesce(sum(value) FILTER (WHERE value > 0), 0), 2)       AS received,
    count(*) FILTER (WHERE value < 0)                                AS debits,
    count(*) FILTER (WHERE value > 0)                                AS credits,
    round(coalesce(sum(-value) FILTER (WHERE value < 0), 0)
          / nullif(date_diff('day', min(local_date), max(local_date)) + 1, 0), 2) AS avg_daily_spend,
    CAST(min(local_date) AS VARCHAR)                                 AS first_date,
    CAST(max(local_date) AS VARCHAR)                                 AS last_date
FROM events
WHERE source = 'bank';

-- name: bank_top_spend
SELECT actor AS name, round(sum(-value), 2) AS spent, count(*) AS txns
FROM events
WHERE source = 'bank' AND value < 0
GROUP BY actor
ORDER BY spent DESC, name
LIMIT 10;

-- name: bank_top_count
SELECT actor AS name, count(*) AS txns, round(sum(-value), 2) AS spent
FROM events
WHERE source = 'bank' AND value < 0
GROUP BY actor
ORDER BY txns DESC, name
LIMIT 10;

-- name: bank_by_channel
SELECT json_extract_string(meta, '$.channel') AS channel,
       round(sum(-value) FILTER (WHERE value < 0), 2) AS spent,
       count(*) FILTER (WHERE value < 0) AS debits,
       round(sum(value) FILTER (WHERE value > 0), 2) AS received,
       count(*) FILTER (WHERE value > 0) AS credits
FROM events
WHERE source = 'bank'
GROUP BY channel
ORDER BY spent DESC NULLS LAST, channel;

-- name: bank_by_month
SELECT strftime(local_date, '%Y-%m') AS month,
       round(coalesce(sum(-value) FILTER (WHERE value < 0), 0), 2) AS spent,
       round(coalesce(sum(value) FILTER (WHERE value > 0), 0), 2)  AS received,
       count(*) AS txns
FROM events
WHERE source = 'bank'
GROUP BY month
ORDER BY month;

-- name: bank_rows_for_model
-- Every stored bank row: the categoriser needs the whole history for payee behaviour.
SELECT event_key, CAST(local_date AS VARCHAR) AS local_date, weekday, value, meta
FROM events
WHERE source = 'bank'
ORDER BY ts_utc, event_key;

-- name: bank_uncategorised
-- Variables: model_version. Rows never categorised, or by an older model version.
SELECT count(*) AS n
FROM events
WHERE source = 'bank'
  AND json_extract_string(meta, '$.model_version') IS DISTINCT FROM getvariable('model_version');

-- name: categoriser_info
SELECT max(value) FILTER (WHERE key = 'categoriser_version')      AS version,
       max(value) FILTER (WHERE key = 'categoriser_test_macro_f1') AS test_macro_f1
FROM settings;

-- name: bank_by_category
WITH d AS (
    SELECT coalesce(category, 'uncategorised') AS category, -value AS spent
    FROM events WHERE source = 'bank' AND value < 0
)
SELECT category, round(sum(spent), 2) AS spent, count(*) AS txns,
       round(sum(spent) / nullif(sum(sum(spent)) OVER (), 0), 4) AS share
FROM d
GROUP BY category
ORDER BY spent DESC, category;

-- name: bank_review
-- Low-confidence predictions (shown as 'other') the user has not corrected yet.
SELECT e.event_key, payee_key(e.meta) AS payee_key, CAST(e.local_date AS VARCHAR) AS local_date,
       e.actor, e.title, -e.value AS amount,
       json_extract_string(e.meta, '$.model_category') AS model_category,
       TRY_CAST(json_extract_string(e.meta, '$.category_confidence') AS DOUBLE) AS confidence
FROM events e
WHERE e.source = 'bank' AND e.value < 0
  AND json_extract_string(e.meta, '$.category_source') = 'review'
  AND NOT EXISTS (SELECT 1 FROM category_overrides o
                  WHERE (o.scope = 'event' AND o.target = e.event_key)
                     OR (o.scope = 'payee' AND o.target = payee_key(e.meta)))
ORDER BY e.ts_utc DESC, e.event_key
LIMIT 50;

-- name: bank_review_count
SELECT count(*) AS n
FROM events e
WHERE e.source = 'bank' AND e.value < 0
  AND json_extract_string(e.meta, '$.category_source') = 'review'
  AND NOT EXISTS (SELECT 1 FROM category_overrides o
                  WHERE (o.scope = 'event' AND o.target = e.event_key)
                     OR (o.scope = 'payee' AND o.target = payee_key(e.meta)));

-- name: bank_txns
-- Variables: txn_category (NULL = all), txn_offset. 25 rows per page, newest first.
SELECT e.event_key, payee_key(e.meta) AS payee_key, CAST(e.local_date AS VARCHAR) AS local_date,
       e.actor, e.title, e.value, e.category,
       json_extract_string(e.meta, '$.model_category') AS model_category,
       TRY_CAST(json_extract_string(e.meta, '$.category_confidence') AS DOUBLE) AS confidence,
       CASE WHEN oe.target IS NOT NULL THEN 'override'
            WHEN op.target IS NOT NULL AND e.value < 0 THEN 'payee override'
            ELSE json_extract_string(e.meta, '$.category_source') END AS source
FROM events e
LEFT JOIN category_overrides oe ON oe.scope = 'event' AND oe.target = e.event_key
LEFT JOIN category_overrides op ON op.scope = 'payee' AND op.target = payee_key(e.meta)
WHERE e.source = 'bank'
  AND (getvariable('txn_category') IS NULL OR e.category = getvariable('txn_category'))
ORDER BY e.ts_utc DESC, e.event_key
LIMIT 25 OFFSET CAST(getvariable('txn_offset') AS INTEGER);

-- name: bank_txn_count
-- Variables: txn_category (NULL = all).
SELECT count(*) AS n FROM events
WHERE source = 'bank' AND (getvariable('txn_category') IS NULL OR category = getvariable('txn_category'));

-- name: preview
-- Variables: preview_source, preview_chat (NULL = any chat).
SELECT source, strftime(ts_utc, '%Y-%m-%dT%H:%M:%SZ') AS ts_utc, CAST(local_date AS VARCHAR) AS local_date,
       local_hour, weekday, event_type, actor, title, text, value, category, meta
FROM events
WHERE source = getvariable('preview_source')
  AND (getvariable('preview_chat') IS NULL OR json_extract_string(meta, '$.chat') = getvariable('preview_chat'))
ORDER BY ts_utc
LIMIT 20;

-- name: coverage
SELECT source, CAST(first_date AS VARCHAR) AS first_date, CAST(last_date AS VARCHAR) AS last_date,
       days_with_data, events, strftime(last_import, '%Y-%m-%dT%H:%M:%SZ') AS last_import
FROM source_coverage
ORDER BY source;

-- name: overlap
SELECT CAST(start_date AS VARCHAR) AS start_date, CAST(end_date AS VARCHAR) AS end_date, days, sources, source_list
FROM overlap_window;

-- name: weekly
-- Events per source per ISO week (Monday start), for the coverage bars.
SELECT source, CAST(date_trunc('week', local_date) AS DATE)::VARCHAR AS week, count(*) AS events
FROM events
GROUP BY source, week
ORDER BY source, week;

-- name: imports
-- Live event counts per import (an import can lose rows later, e.g. to the Spotify cross-format rule).
SELECT i.import_id, i.source, i.file_name, i.file_hash, i.rows_added, i.rows_skipped,
       CAST(i.min_date AS VARCHAR) AS min_date, CAST(i.max_date AS VARCHAR) AS max_date,
       strftime(i.imported_at, '%Y-%m-%dT%H:%M:%SZ') AS imported_at,
       count(e.event_key) AS events_now
FROM imports i
LEFT JOIN events e ON e.import_id = i.import_id
GROUP BY i.import_id, i.source, i.file_name, i.file_hash, i.rows_added, i.rows_skipped,
         i.min_date, i.max_date, i.imported_at
ORDER BY i.source, i.imported_at, i.file_name;

-- name: import_by_hash
-- Variables: file_hash.
SELECT import_id, file_name FROM imports WHERE file_hash = getvariable('file_hash') LIMIT 1;
