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
| spotify | `play` | artist | track | null | ms played | (later) |
| youtube | `watch` | channel | video title | null | null | (later) `url`, `is_ad` |
| bank | `transaction` | counterparty | null | narration | INR (signed) | (later) |

### WhatsApp details

- `kind = "media"`: `<Media omitted>` (Android) or `image omitted` / `<attached: …>` (iOS). `text` is null, `meta.media_type` is `image` / `video` / `audio` / `sticker` / `gif` / `document` / `contact` / `location` / `media`.
- `kind = "deleted"`: "This message was deleted" / "You deleted this message". `text` is null.
- `meta.edited = true` when the line carried `<This message was edited>` (the marker is stripped from `text`).
- `system` rows: encryption notice, "X added Y", "X left", group subject/icon changes, etc. `actor` is null, `text` holds the notice.
