-- Load one parsed file (Parquet written by src/python/stage.py) into stage_events.
-- Variables: stage_file = path / registered file name of the Parquet file.
DELETE FROM stage_events;
INSERT INTO stage_events
SELECT
    seq,
    source,
    CAST(ts_utc AS TIMESTAMP),
    CAST(local_date AS DATE),
    local_hour,
    weekday,
    event_type,
    actor,
    title,
    text,
    CASE WHEN isnan(CAST(value AS DOUBLE)) THEN NULL ELSE CAST(value AS DOUBLE) END,  -- pandas NaN -> NULL
    CAST(category AS VARCHAR),
    meta
FROM read_parquet(getvariable('stage_file'));
