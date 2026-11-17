-- Merge stage_events (one parsed file) into events, adding only NEW events.
-- Variables: import_id, source, file_name, file_hash, imported_at (ISO UTC string).
-- Dedupe rules are documented in docs/schema.md ("Event identity and de-duplication").

-- 1. Identity key per source. WhatsApp exports have minute precision, so identical
--    messages in the same minute are numbered (occ) in file order to stay distinct.
CREATE OR REPLACE TEMP TABLE stage_keyed AS
WITH s AS (
    SELECT
        *,
        json_extract_string(meta, '$.chat')       AS k_chat,
        json_extract_string(meta, '$.kind')       AS k_kind,
        json_extract_string(meta, '$.media_type') AS k_media,
        json_extract_string(meta, '$.format')     AS k_format,
        json_extract_string(meta, '$.video_id')   AS k_video,
        coalesce(json_extract_string(meta, '$.upi_ref'), json_extract_string(meta, '$.ref_no')) AS k_ref,
        json_extract_string(meta, '$.direction')  AS k_dir,
        json_extract_string(meta, '$.balance')    AS k_balance,
        CAST(ts_utc AS VARCHAR)                   AS k_ts
    FROM stage_events
),
o AS (
    SELECT
        *,
        row_number() OVER (
            PARTITION BY source, k_chat, ts_utc, event_type, actor, text, k_kind, k_media
            ORDER BY seq
        ) - 1 AS k_occ
    FROM s
),
k AS (
    SELECT
        *,
        md5(to_json(CASE source
            WHEN 'whatsapp' THEN [source, k_chat, k_ts, event_type, actor, text, k_kind, k_media, CAST(k_occ AS VARCHAR)]
            WHEN 'spotify'  THEN [source, k_format, k_ts, actor, title, CAST(value AS VARCHAR), k_kind]
            WHEN 'youtube'  THEN [source, k_ts, event_type, k_video, title, text]
            -- bank: txn date + UPI ref (or Ref No.) + signed amount + direction + running balance
            WHEN 'bank'     THEN [source, CAST(local_date AS VARCHAR), k_ref, CAST(value AS VARCHAR), k_dir, k_balance]
            ELSE                 [source, k_ts, event_type, actor, title, text, CAST(value AS VARCHAR), meta]
        END)) AS event_key
    FROM o
)
SELECT * FROM k
QUALIFY row_number() OVER (PARTITION BY event_key ORDER BY seq) = 1;  -- duplicates inside the file

-- 2. Insert events whose key is not stored yet.
INSERT INTO events
SELECT source, ts_utc, local_date, local_hour, weekday, event_type, actor, title, text,
       value, category, meta, event_key, getvariable('import_id')
FROM stage_keyed k
WHERE NOT EXISTS (SELECT 1 FROM events e WHERE e.event_key = k.event_key)
ORDER BY ts_utc, seq;

-- 3. Spotify cross-format dedupe: the same play in account data (minute precision) and
--    extended history (second precision) -> keep the extended row (it has more fields).
--    Match = same track + artist, end times within 60 seconds.
DELETE FROM events
WHERE source = 'spotify'
  AND event_key IN (
      SELECT a.event_key
      FROM events a
      JOIN events b
        ON a.title IS NOT DISTINCT FROM b.title
       AND a.actor IS NOT DISTINCT FROM b.actor
      WHERE a.source = 'spotify' AND b.source = 'spotify'
        AND json_extract_string(a.meta, '$.format') = 'account'
        AND json_extract_string(b.meta, '$.format') = 'extended'
        AND abs(epoch(a.ts_utc) - epoch(b.ts_utc)) <= 60
  );

-- 4. Record the import.
INSERT INTO imports
SELECT
    getvariable('import_id'),
    getvariable('source'),
    getvariable('file_name'),
    getvariable('file_hash'),
    added.n,
    staged.n - added.n,
    staged.min_date,
    staged.max_date,
    CAST(getvariable('imported_at') AS TIMESTAMP)
FROM (SELECT count(*) AS n FROM events WHERE import_id = getvariable('import_id')) added,
     (SELECT count(*) AS n, min(local_date) AS min_date, max(local_date) AS max_date FROM stage_events) staged;

-- 5. Clean up scratch data.
DELETE FROM stage_events;
DROP TABLE stage_keyed;
