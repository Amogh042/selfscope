# Backlog

Known gaps and open decisions. Move items to "Done" when fixed.

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
- **Spotify extended video/podcast-only files** (step 3). `Streaming_History_Video_*.json` is
  not detected; audiobook rows map to `kind = "audiobook"` but are untested on real data.
- **YouTube HTML export** (step 3). `watch-history.html` is recognised and the card asks the user
  to re-export as JSON; we don't parse HTML.
- **PDF bank statements** (step 5). SBI PDFs are recognised and the card asks for the Excel
  download instead. Supporting them needs PDF text extraction in the browser (e.g. pdf.js) plus
  column reconstruction; password-protected PDFs (common for e-statements) need a password prompt.
- **Binary .xls statements are untested on a real file** (step 5). The xlrd path exists and
  Pyodide loads xlrd on demand, but there is no real OLE2 SBI fixture (we have no real statement).
  XLSX, HTML-as-.xls, tab-separated .xls and CSV are tested.
- **Other banks** (step 5). Only SBI's layout and narrations are handled; other banks' files
  fail the "Txn Date" header check. Unknown SBI narrations become `channel = OTHER`.
- **Several accounts** (step 5). Two different SBI accounts are stored together as one "bank"
  source (account numbers are deliberately not kept). A user-chosen per-account label would
  separate them without storing the number.
- **Bank spend includes transfers** (step 5). `spend_total` counts every debit, including money
  sent to friends and ATM cash; the categoriser (next step) will let views separate real spend.
- **Takeout search history, subscriptions, comments** are ignored (step 3). Only
  `watch-history.json` is read from a Takeout zip.

## App / architecture

- **Timezone override in the UI** (step 2). WhatsApp exports have no timezone; the parser
  assumes Asia/Kolkata (`parse_whatsapp(tz=…)` exists but the UI doesn't expose it). Spotify and
  YouTube are UTC in the export, so only the *local* fields depend on this choice.
- **Zips are opened on the main thread** (step 2). JSZip runs in the UI thread; fine for chat and
  Spotify exports, but a multi-GB Takeout zip would freeze the tab. Move unzipping to a worker and
  stream only the entries we need. Large single JSON files are also read fully into memory.
- **Folder drop** (step 2). Dropping an unzipped Takeout / Spotify folder is not supported; only
  files and zips. Needs `DataTransferItem.webkitGetAsEntry()` traversal.
- **Large exports in Pyodide** (step 3). Parsers loop over records in Python; ~20k rows parse in
  well under a second, but a 10-year extended Spotify history (~200k+ rows) will take several
  seconds. Vectorise if it becomes a problem.
- **OPFS persistence** (step 4). duckdb-wasm `1.33.1-dev57.0` (npm's `latest` tag is a dev
  build) does not persist `opfs://` databases here, so we save Parquet snapshots to IndexedDB
  after every change. That rewrites the whole database each time (fine at ~40k events, ~0.1 s;
  slow at millions). Retry OPFS with the last stable release (1.32.0) or a newer build.
- **Two open tabs** (step 4). Each tab has its own in-memory DuckDB; the last tab to save wins
  the IndexedDB snapshot, so an import done in another tab can be overwritten. Add a
  BroadcastChannel lock or reload-on-change.
- **Removing an import** (step 4) deletes the events it first added, including ones a later
  overlapping import skipped as duplicates. Re-import the later file to get them back.
  A many-to-many event↔import table would fix it.
- **Spotify cross-format edge cases** (step 4). Two account plays of the same track within 60 s
  of one extended play are both dropped. Account rows deleted by the rule do not come back if
  the extended import is later removed (their file is still "KNOWN" by hash; remove and
  re-import the account file).
- **WhatsApp edited messages** (step 4). If a message was edited between two exports, the newer
  export's text differs, so it is stored as a new event next to the old text.
- **YouTube `est_watch_min` across exports** (step 4). It is computed per file; the last video
  of an older export gets the 5-min default even if a newer export continues the session.
- **First import downloads pyarrow** (~10 MB, step 4); CSV fallback is used if that fails.

## Done

- Step 4: data survives reloads (DuckDB + IndexedDB snapshots, separate demo/real databases).
- Step 4: Spotify account + extended formats no longer double-count (60 s cross-format rule).
- Step 4: imports append only new events (event_key) instead of re-parsing everything; exact
  same file is skipped by SHA-256.
- Step 4: imports can be removed (Data screen), plus wipe-all per database.
