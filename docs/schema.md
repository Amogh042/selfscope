# Shared event schema

Every source (WhatsApp, Spotify, YouTube, bank) is parsed into the same table:
**one row = one event.** Cross-app insights are then plain group-bys / joins on
`local_date`, `local_hour` and `weekday`.

Code mirrors of this doc — keep all three in sync:

- Python: `web/src/python/schema.py` (column constants, `finalize_events()`)
- TypeScript: `web/src/lib/schema.ts` (`EventRow`, `EVENT_COLUMNS`)

## Columns

| # | Column | Type (pandas / TS) | Null? | Meaning |
|---|---|---|---|---|
| 1 | `source` | str / `Source` | no | `whatsapp` · `spotify` · `youtube` · `bank` |
| 2 | `ts_utc` | `datetime64[ns, UTC]` / ISO-8601 string ending in `Z` | no | When the event happened, **always UTC** |
| 3 | `local_date` | str `YYYY-MM-DD` | no | Calendar date in `Asia/Kolkata` |
| 4 | `local_hour` | int 0–23 | no | Hour in `Asia/Kolkata` |
| 5 | `weekday` | int 0–6 | no | **0 = Monday … 6 = Sunday** (pandas convention; DuckDB's `dayofweek` uses 0 = Sunday, so use `isodow - 1` there) |
| 6 | `event_type` | str / `EventType` | no | `message` · `play` · `watch` · `transaction` · `system` |
| 7 | `actor` | str | yes | Who did it: message sender, track artist, video channel, bank counterparty. Null for system events |
| 8 | `title` | str | yes | Track / video title. Null for chats |
| 9 | `text` | str | yes | Message text (or system notice text). Null otherwise, and null for media / deleted messages |
| 10 | `value` | float | yes | Numeric measure: ms played (Spotify), amount in INR (bank, signed: debit < 0). Null otherwise |
| 11 | `category` | str | yes | Reserved for later classification (e.g. spend category, video topic). Null for now |
| 12 | `meta` | str (JSON object) | no | Source-specific extras, always a JSON object string (`"{}"` if empty) |

## Time rules

- Store **only UTC** in `ts_utc`. Parsers convert from whatever the export uses.
- `local_date`, `local_hour`, `weekday` are always derived from `ts_utc` in
  **Asia/Kolkata** (`schema.LOCAL_TZ`) by `finalize_events()` — parsers never compute them.
- Exports that store naive local times (WhatsApp) are assumed to be in Asia/Kolkata
  unless the caller passes another zone.
- Exports already in UTC: Spotify `endTime` (UTC, minute precision), Takeout `time` (UTC, `Z`).

## Per-source mapping

| Source | event_type | actor | title | text | value | meta keys |
|---|---|---|---|---|---|---|
| whatsapp | `message` / `system` | sender | null | message text | null | `chat`, `platform` (`android`/`ios`), `kind` (`text`/`media`/`deleted`), `media_type`, `edited` |
| spotify | `play` | artist (show for podcasts) | track (episode) | null | ms played | `kind`, `format`, `skipped`, `start_estimate`, + `album`, `uri`, `platform`, `shuffle`, `reason_start`, `reason_end` when the export has them |
| youtube | `watch` / `system` | channel | video title | null (system: the entry title) | null | `header`, `video_id`, `channel_url`, `is_ad`, `is_short`, `est_watch_min`, `session`, + `removed` / `title_unavailable` |
| bank | `transaction` | counterparty | null | narration | INR (signed) | (later) |

### WhatsApp details

- `kind = "media"`: `<Media omitted>` (Android) or `image omitted` / `<attached: …>` (iOS). `text` is null, `meta.media_type` is `image` / `video` / `audio` / `sticker` / `gif` / `document` / `contact` / `location` / `media`.
- `kind = "deleted"`: "This message was deleted" / "You deleted this message". `text` is null.
- `meta.edited = true` when the line carried `<This message was edited>` (the marker is stripped from `text`).
- `system` rows: encryption notice, "X added Y", "X left", group subject/icon changes, etc. `actor` is null, `text` holds the notice.

### Spotify details

Both export types are supported and can be mixed; files from one export are merged and
exact duplicate rows dropped.

| | Account data | Extended streaming history |
|---|---|---|
| Files | `StreamingHistory_music_N.json`, `StreamingHistory_podcast_N.json` | `Streaming_History_Audio_*.json` (older: `endsong_N.json`) |
| Time | `endTime`, `YYYY-MM-DD HH:MM`, UTC (minute precision) | `ts`, ISO-8601 UTC |
| Music | `artistName`, `trackName`, `msPlayed` | `master_metadata_album_artist_name`, `master_metadata_track_name`, `ms_played` |
| Podcast | `podcastName`, `episodeName` | `episode_show_name`, `episode_name` |

- **`ts_utc` is when playback ENDED** (that is what Spotify records). `meta.start_estimate`
  = end − ms played, as an ISO UTC string. For hour-of-day analysis of short plays the
  difference is negligible; for long podcast plays use `start_estimate`.
- `meta.kind`: `music` · `podcast` · `audiobook` · `unknown` (extended rows with no metadata).
- `meta.skipped`: Spotify's own `skipped` field when present (extended format), otherwise
  **ms played < 30,000** (the account-data format has no skip field). Exactly 30 s is not a skip.
- `meta.format`: `account` or `extended`.

### YouTube details (Google Takeout `watch-history.json`)

- `title` = the entry title without the `"Watched "` prefix. `actor` = `subtitles[0].name` (channel).
- `meta.video_id` from `titleUrl` (`watch?v=`, `/shorts/`, `youtu.be/`, `/live/`); `meta.is_short`
  if the URL has `/shorts/`; `meta.is_ad` if `details` contains `"From Google Ads"`;
  `meta.header` is `YouTube` or `YouTube Music`.
- "Watched a video that has been removed" → `title` null, `meta.removed = true`.
  A title that is just a URL (private video) → `title` null, `meta.title_unavailable = true`.
- Entries starting with `"Viewed "` (posts) and other non-video entries → `event_type = "system"`,
  `text` = the entry title.
- Non-English Takeout prefixes (e.g. "Visto …") on video URLs: kept as-is as the title and
  counted in the parser's `unrecognised_prefix` log (shown on the import screen).
- The same entry appearing in two files (time + video id + title) is kept once.

#### YouTube watch time (`meta.est_watch_min`) — an estimate, not a measurement

Takeout records **when** a video was opened, never **how long** it was watched. We estimate it:

1. Sort all watch events (ads included) by time.
2. **Sessions:** a gap of **30 minutes or more** to the next watch ends the session.
3. **Estimate** for each watch = minutes until the next watch in the same session,
   **capped at 20 minutes**.
4. The **last watch of a session** (no next watch within 30 min) gets a default of **5 minutes**.

`meta.session` numbers the sessions (0, 1, 2, …). Estimated hours on the import screen
exclude ads.

Why these numbers: most videos people open are under ~20 min; a 30-min silence almost
always means the person stopped; 5 min is a conservative guess when there is no next video.
Known biases: it under-counts long videos watched to the end (cap) and the last video of
each session; it over-counts when a video was opened and abandoned while the tab stayed
idle. The constants live in `parsers/youtube.py` (`SESSION_GAP_MIN`, `MAX_WATCH_MIN`,
`LAST_IN_SESSION_MIN`) so the sensitivity can be shown in the dashboard later.

## Storage (DuckDB, step 4)

All SQL lives in `web/src/sql/` and is run unchanged by the browser (`src/lib/store.ts`,
DuckDB-WASM v1.5.4) and by the tests (`src/python/tests/test_storage.py`, duckdb 1.5.4).

| File | What |
|---|---|
| `schema.sql` | tables `events`, `imports`, `settings`, `stage_events` |
| `stage_parquet.sql` / `stage_csv.sql` | load one parsed file into `stage_events` |
| `import.sql` | merge `stage_events` into `events` (dedupe), record the import |
| `views.sql` | `event_facts`, `daily_activity`, `hourly_heatmap`, `source_coverage`, `overlap_window` |
| `manage.sql` | `remove_import`, `wipe_all`, `set_me`, `reset` |
| `queries.sql` | read queries for the Import and Data screens |

### Tables

- **`events`** — the shared columns above (`ts_utc` is a naive `TIMESTAMP` holding UTC,
  `local_date` a `DATE`) + **`event_key`** (identity hash, below) + **`import_id`** (the import
  that first added the event).
- **`imports`** — `import_id`, `source`, `file_name`, `file_hash` (SHA-256 of the file text),
  `rows_added`, `rows_skipped` (parsed rows already stored), `min_date`, `max_date`, `imported_at` (UTC).
- **`settings`** — key/value; `me` = the user's own WhatsApp name (needed for sent/received).

### Getting rows from Python into DuckDB

The parser runs in the Pyodide worker; `src/python/stage.py` writes the frame (+ a `seq`
column = row order) as **Parquet via pyarrow** (pyarrow 22 is fetched by Pyodide on the first
import, ~10 MB). If pyarrow cannot load, it falls back to **CSV** (`stage_csv.sql` reads quoted
multi-line fields). The bytes are registered as an in-memory file in DuckDB and read with
`read_parquet` / `read_csv`. Tests check both paths give identical events.

### Event identity and de-duplication (`import.sql`)

`event_key = md5(to_json([...]))` over the fields that identify a real event:

| Source | Key fields | Why |
|---|---|---|
| whatsapp | source, `meta.chat`, ts_utc, event_type, actor, text, `meta.kind`, `meta.media_type`, **occurrence** | Exports have minute precision, so two identical "ok"s in the same minute are both real; they are numbered 0, 1, … in file order. A newer export of the same chat reproduces the same numbering. |
| spotify | source, `meta.format`, ts_utc, actor, title, value (ms), `meta.kind` | An exact replay of the same play is the same event. |
| youtube | source, ts_utc, event_type, `meta.video_id`, title, text | Same as step 3's cross-file rule. |
| other | source, ts_utc, event_type, actor, title, text, value, meta | Conservative default. |

Rules:

1. Rows with the same key inside one file are kept once.
2. A row is inserted only if its key is not stored yet (`NOT EXISTS`). So re-importing a file —
   or a newer export that overlaps an old one — only adds new events. The UI also skips a file
   whose SHA-256 is already in `imports` without parsing it ("KNOWN").
3. **Spotify cross-format:** after each import, an *account-format* play is deleted when an
   *extended-format* play has the same track + artist and an end time within **60 seconds**
   (account `endTime` is truncated to the minute). The extended row is kept because it has more
   fields. This works in either import order.
4. `rows_added` = rows of this import still stored after rule 3; `rows_skipped` = parsed rows − added.

**Removing an import** deletes the events it *first added*. If a later, overlapping import
contained the same events they were skipped there, so they disappear too — re-import the later
file to restore them (it will then add them).

### Views (`views.sql`)

"Late night" everywhere = local **23:00–02:59**. Days are calendar days in Asia/Kolkata, so
00:00–02:59 belongs to the *next* date.

- **`daily_activity`** — one row per date from the first to the last stored event (any source):
  `spotify_minutes` (Σ ms/60000), `spotify_plays`, `skip_rate` (share of plays with
  `meta.skipped`), `spotify_late_night_share`, `youtube_est_minutes` (Σ `est_watch_min`, ads
  excluded), `youtube_videos` (ads excluded), `youtube_late_night_share`, `wa_sent` /
  `wa_received` (messages by / not by `settings.me`; NULL until it is set),
  `wa_late_night_share` (all messages), `wa_active_chats`, `is_weekend` (Sat/Sun).
  A source's columns are **NULL outside its own first..last date** (no data ≠ zero activity),
  counts are **0** on in-range days with no events, and shares/rates are NULL when there were
  no events that day (undefined, not 0).
- **`hourly_heatmap`** — `source × weekday (0 = Mon) × hour → events` (system notices excluded,
  ads included).
- **`source_coverage`** — per source: `first_date`, `last_date`, `days_with_data`, `events`,
  `last_import`.
- **`overlap_window`** — `start_date` = latest first date, `end_date` = earliest last date across
  all sources with data (NULL if they do not overlap), `days`, `sources`, `source_list`.
  Cross-app correlations are computed only inside this window.

### Persistence and the two databases

Demo and real data are two separate databases, **`selfscope_demo`** and **`selfscope_real`**,
never mixed: LOAD DEMO DATA only writes to the demo one and files the user adds always go to
the real one (the UI switches mode when needed).

The installed duckdb-wasm (`1.33.1-dev57.0`) opens `opfs://` database files but writes never
reach them in this browser (0-byte files after `CHECKPOINT`; tested in step 4), so we use the
planned fallback: DuckDB runs **in memory** and after every change `events`, `imports` and
`settings` are written as **Parquet snapshots to IndexedDB** under the database's name. On load
(or when switching mode) the tables are dropped and the snapshot is restored. Everything stays
in this browser profile.
