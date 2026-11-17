# Backlog

Known gaps and open decisions. Newest step first within each group; move items out when done.

## Import & parsing

- **Non-English WhatsApp exports** (step 2). System lines and placeholders ("image omitted",
  "This message was deleted", "added", "left", …) are matched in English only. A phone set to
  Hindi/Kannada/etc. exports them translated, so they would be counted as normal text messages.
  Fix: per-language phrase tables, or detect the language from the encryption notice.
- **Non-English YouTube Takeout** (step 3). Titles with a non-English "Watched" prefix
  (e.g. "Visto …") are kept as-is and counted in `unrecognised_prefix`; "Viewed" in other
  languages is not recognised and those posts would be counted as watches if they link to a video.
- **YouTube watch time is an estimate** (step 3). Takeout has no duration; `est_watch_min`
  uses session gaps (30 min / cap 20 min / default 5 min, see `docs/schema.md`). Show the
  sensitivity to these constants in the dashboard, and consider using known video lengths if
  we ever have them (we won't fetch them — no external APIs on user data).
- **Spotify account + extended formats together double-count** (step 3). Only *exact*
  duplicates are dropped. The same play in both formats differs (minute vs second precision,
  different meta), so dropping both exports of the same period counts it twice.
  Fix: when both formats overlap in time, keep extended and drop account rows for that range.
- **Spotify extended video/podcast-only files** (step 3). `Streaming_History_Video_*.json` is
  not detected; audiobook rows map to `kind = "audiobook"` but are untested on real data.
- **YouTube HTML export** (step 3). `watch-history.html` is recognised and the card asks the user
  to re-export as JSON; we don't parse HTML.
- **Takeout search history, subscriptions, comments** are ignored (step 3). Only
  `watch-history.json` is read from a Takeout zip.

## App / architecture

- **Timezone override in the UI** (step 2). WhatsApp exports have no timezone; the parser
  assumes Asia/Kolkata (`parse_whatsapp(tz=…)` exists but the UI doesn't expose it). Spotify and
  YouTube are UTC in the export, so only the *local* fields depend on this choice.
- **Data lost on reload until DuckDB** (step 2). Parsed frames live in the Python worker's memory
  (`session.EVENTS`); a page reload, or leaving the Import screen, loses the UI state. Planned:
  persist the shared event table in DuckDB-WASM (OPFS), never on a server.
- **Zips are opened on the main thread** (step 2). JSZip runs in the UI thread; fine for chat and
  Spotify exports, but a multi-GB Takeout zip would freeze the tab. Move unzipping to a worker and
  stream only the entries we need. Large single JSON files are also read fully into memory.
- **Folder drop** (step 2). Dropping an unzipped Takeout / Spotify folder is not supported; only
  files and zips. Needs `DataTransferItem.webkitGetAsEntry()` traversal.
- **Large exports in Pyodide** (step 3). Parsers loop over records in Python; ~20k rows parse in
  well under a second, but a 10-year extended Spotify history (~200k+ rows) will take several
  seconds. Vectorise if it becomes a problem.
- **Re-merging on every drop** (step 3). Adding Spotify/YouTube files re-parses all files of that
  source (simple and correct, but O(total) each time).
- **Remove a file from the inventory** — not possible yet (`session.forget` exists for WhatsApp only).
