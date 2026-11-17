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
