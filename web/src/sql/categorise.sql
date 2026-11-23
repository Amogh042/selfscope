-- Bank categories: write model predictions, apply user overrides. Named blocks.
-- Final category = one-transaction override > payee override (debits only) > model;
-- low-confidence ("review") predictions are shown as 'other'. See docs/schema.md.

-- name: apply_predictions
-- Variables: pred_file (JSON array from categoriser.categorise_events_json "predictions"),
--            model_version, model_f1. Stores the model's output in meta; does not touch overrides.
CREATE OR REPLACE TEMP TABLE predictions AS
SELECT *
FROM read_json(getvariable('pred_file'), format = 'array',
               columns = {event_key: 'VARCHAR', model_category: 'VARCHAR', confidence: 'DOUBLE',
                          source: 'VARCHAR', model_version: 'VARCHAR'});
UPDATE events
SET meta = CAST(json_merge_patch(events.meta, json_object(
        'model_category', p.model_category,
        'category_confidence', p.confidence,
        'category_source', p.source,
        'model_version', p.model_version)) AS VARCHAR)
FROM predictions p
WHERE events.event_key = p.event_key;
DROP TABLE predictions;
INSERT OR REPLACE INTO settings VALUES
    ('categoriser_version', getvariable('model_version')),
    ('categoriser_test_macro_f1', getvariable('model_f1'));

-- name: refresh_categories
-- Recompute the final category of every bank row from meta + overrides.
UPDATE events
SET category = r.final
FROM (
    SELECT e.event_key,
           coalesce(oe.category,
                    CASE WHEN e.value < 0 THEN op.category END,
                    CASE WHEN json_extract_string(e.meta, '$.category_source') = 'review' THEN 'other'
                         ELSE json_extract_string(e.meta, '$.model_category') END) AS final
    FROM events e
    LEFT JOIN category_overrides oe ON oe.scope = 'event' AND oe.target = e.event_key
    LEFT JOIN category_overrides op ON op.scope = 'payee' AND op.target = payee_key(e.meta)
    WHERE e.source = 'bank'
) r
WHERE events.event_key = r.event_key
  AND events.category IS DISTINCT FROM r.final;

-- name: set_override
-- Variables: scope ('event' | 'payee'), target, category, created_at.
-- A payee-wide correction replaces earlier one-transaction corrections for that payee's debits.
DELETE FROM category_overrides
WHERE getvariable('scope') = 'payee' AND scope = 'event'
  AND target IN (SELECT event_key FROM events
                 WHERE source = 'bank' AND value < 0 AND payee_key(meta) = getvariable('target'));
INSERT OR REPLACE INTO category_overrides
VALUES (getvariable('scope'), getvariable('target'), getvariable('category'),
        CAST(getvariable('created_at') AS TIMESTAMP));

-- name: clear_override
-- Variables: scope, target. Back to the payee override / the model.
DELETE FROM category_overrides WHERE scope = getvariable('scope') AND target = getvariable('target');
