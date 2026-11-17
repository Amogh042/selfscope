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
