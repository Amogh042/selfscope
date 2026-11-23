-- Data-manager mutations. Named statements: the app runs one block at a time.
-- Variables as noted per block.

-- name: remove_import
-- import_id: the import whose events are removed (events first added by that import).
DELETE FROM events WHERE import_id = getvariable('import_id');
DELETE FROM imports WHERE import_id = getvariable('import_id');

-- name: wipe_all
DELETE FROM events;
DELETE FROM imports;
DELETE FROM settings;
DELETE FROM category_overrides;
DELETE FROM periods;
DELETE FROM insights;

-- name: set_me
-- me: the user's own WhatsApp name (used by daily_activity wa_sent / wa_received).
INSERT OR REPLACE INTO settings VALUES ('me', getvariable('me'));

-- name: add_period
-- Variables: period_id, label, start_date, end_date, origin, created_at.
INSERT OR REPLACE INTO periods VALUES (getvariable('period_id'), getvariable('label'),
    CAST(getvariable('start_date') AS DATE), CAST(getvariable('end_date') AS DATE),
    getvariable('origin'), CAST(getvariable('created_at') AS TIMESTAMP));

-- name: delete_period
DELETE FROM periods WHERE period_id = getvariable('period_id');

-- name: save_insights
-- Variables: cache_key, range_from, range_to, fingerprint, created_at, payload_file (JSON text file).
-- Older results for the same range are dropped (they belong to older data).
DELETE FROM insights
WHERE range_from IS NOT DISTINCT FROM CAST(getvariable('range_from') AS DATE)
  AND range_to IS NOT DISTINCT FROM CAST(getvariable('range_to') AS DATE);
INSERT OR REPLACE INTO insights
SELECT getvariable('cache_key'), CAST(getvariable('range_from') AS DATE), CAST(getvariable('range_to') AS DATE),
       getvariable('fingerprint'), CAST(getvariable('created_at') AS TIMESTAMP), content
FROM read_text(getvariable('payload_file'));

-- name: reset
-- Drop everything (used before restoring a different database snapshot into memory).
DROP VIEW IF EXISTS overlap_window;
DROP VIEW IF EXISTS source_coverage;
DROP VIEW IF EXISTS hourly_heatmap;
DROP VIEW IF EXISTS daily_activity;
DROP VIEW IF EXISTS event_facts;
DROP TABLE IF EXISTS events;
DROP TABLE IF EXISTS imports;
DROP TABLE IF EXISTS settings;
DROP TABLE IF EXISTS category_overrides;
DROP TABLE IF EXISTS periods;
DROP TABLE IF EXISTS insights;
DROP VIEW IF EXISTS daily_features;
DROP TABLE IF EXISTS stage_events;
