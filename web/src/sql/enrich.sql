-- Enrichment results (src/python/enrich/runner.py): YouTube topic, Spotify mood + language,
-- WhatsApp sentiment. Named blocks.

-- name: apply_enrichment
-- Variables: pred_file (JSON array of {event_key, category, patch}). Sets category and merges
-- the patch (incl. enrich_version) into meta. Never touches bank rows.
CREATE OR REPLACE TEMP TABLE enrichment AS
SELECT *
FROM read_json(getvariable('pred_file'), format = 'array',
               columns = {event_key: 'VARCHAR', category: 'VARCHAR', patch: 'VARCHAR'});
UPDATE events
SET category = p.category,
    meta = CAST(json_merge_patch(events.meta, p.patch) AS VARCHAR)
FROM enrichment p
WHERE events.event_key = p.event_key AND events.source <> 'bank';
DROP TABLE enrichment;
