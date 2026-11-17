-- Fallback when pyarrow is unavailable: load one parsed file written as CSV by
-- src/python/stage.py into stage_events. Quoted fields may contain newlines (chat messages).
-- Variables: stage_file = path / registered file name of the CSV file.
DELETE FROM stage_events;
INSERT INTO stage_events
SELECT *
FROM read_csv(
    getvariable('stage_file'),
    header = true,
    delim = ',',
    quote = '"',
    escape = '"',
    auto_detect = false,
    columns = {
        'seq': 'BIGINT', 'source': 'VARCHAR', 'ts_utc': 'TIMESTAMP', 'local_date': 'DATE',
        'local_hour': 'INTEGER', 'weekday': 'INTEGER', 'event_type': 'VARCHAR', 'actor': 'VARCHAR',
        'title': 'VARCHAR', 'text': 'VARCHAR', 'value': 'DOUBLE', 'category': 'VARCHAR', 'meta': 'VARCHAR'
    }
);
