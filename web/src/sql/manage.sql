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

-- name: set_me
-- me: the user's own WhatsApp name (used by daily_activity wa_sent / wa_received).
INSERT OR REPLACE INTO settings VALUES ('me', getvariable('me'));

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
DROP TABLE IF EXISTS stage_events;
