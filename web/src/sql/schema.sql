-- SelfScope storage schema (DuckDB). Idempotent: run every time a database is opened.
-- Same file runs in DuckDB-WASM (browser) and the duckdb Python package (tests).
-- See docs/schema.md "Storage".

-- One row per event, in the shared format + identity/provenance columns.
CREATE TABLE IF NOT EXISTS events (
    source      VARCHAR   NOT NULL,   -- whatsapp | spotify | youtube | bank
    ts_utc      TIMESTAMP NOT NULL,   -- UTC (naive TIMESTAMP, always UTC by convention)
    local_date  DATE      NOT NULL,   -- Asia/Kolkata
    local_hour  INTEGER,              -- 0-23, Asia/Kolkata; NULL for date-only sources (bank)
    weekday     INTEGER   NOT NULL,   -- 0 = Monday ... 6 = Sunday
    event_type  VARCHAR   NOT NULL,   -- message | play | watch | transaction | system
    actor       VARCHAR,
    title       VARCHAR,
    text        VARCHAR,
    value       DOUBLE,
    category    VARCHAR,
    meta        VARCHAR   NOT NULL,   -- JSON object string
    event_key   VARCHAR   NOT NULL,   -- md5 of the fields that identify a real event (import.sql)
    import_id   VARCHAR   NOT NULL    -- the import that first added this event
);

-- One row per imported file.
CREATE TABLE IF NOT EXISTS imports (
    import_id    VARCHAR PRIMARY KEY,
    source       VARCHAR NOT NULL,
    file_name    VARCHAR NOT NULL,
    file_hash    VARCHAR,             -- SHA-256 of the file bytes
    rows_added   BIGINT  NOT NULL,    -- new events this import added
    rows_skipped BIGINT  NOT NULL,    -- parsed rows that were already stored (duplicates)
    min_date     DATE,                -- local date range of the parsed file
    max_date     DATE,
    imported_at  TIMESTAMP NOT NULL   -- UTC
);

-- Small key/value settings, e.g. ('me', 'Amogh') = the user's WhatsApp name.
CREATE TABLE IF NOT EXISTS settings (
    key   VARCHAR PRIMARY KEY,
    value VARCHAR
);

-- User corrections to bank categories. They always win over the model and survive
-- re-imports and model retraining (applied by categorise.sql refresh_categories).
CREATE TABLE IF NOT EXISTS category_overrides (
    scope      VARCHAR   NOT NULL,   -- 'event' = one transaction | 'payee' = all debits to this payee
    target     VARCHAR   NOT NULL,   -- event_key, or payee_key(meta) (see views.sql)
    category   VARCHAR   NOT NULL,
    created_at TIMESTAMP NOT NULL,   -- UTC
    PRIMARY KEY (scope, target)
);

-- Scratch table one parsed file is loaded into before import.sql merges it. Not persisted.
CREATE TABLE IF NOT EXISTS stage_events (
    seq         BIGINT,               -- row order within the parsed file
    source      VARCHAR,
    ts_utc      TIMESTAMP,
    local_date  DATE,
    local_hour  INTEGER,
    weekday     INTEGER,
    event_type  VARCHAR,
    actor       VARCHAR,
    title       VARCHAR,
    text        VARCHAR,
    value       DOUBLE,
    category    VARCHAR,
    meta        VARCHAR
);
