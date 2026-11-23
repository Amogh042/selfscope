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
  sent to friends and ATM cash; categories now exist (step 6), so a "real spend" column excluding
  `p2p_transfer` / `cash_atm` can be added when the dashboard needs it.
- **Categoriser v2: shops whose shop word is cut off** (step 6). The largest error on the demo test is a
  canteen whose UPI ID `annapoornamess@…` is printed as `annapoorna`; it looks like a person and is
  predicted as transport (an auto driver). The training data has few long-named shops whose keyword is
  truncated. Fix in the training generator, then evaluate on a **new** unseen statement (the demo test set
  has now been looked at, so improving against it would be tuning on the test set).
- **Categoriser real-world accuracy is unknown** (step 6). Both training and test data are synthetic.
  A small, consented, hand-labelled real statement (kept in `data/private/`, never committed) would give
  an honest estimate.
- **Autos vs friends** (step 6). Auto drivers paid to phone-number UPI IDs look like friends; only the
  small fixed fare separates them. Time of day would help, but SBI statements have no times.
- **Categoriser speed on long histories** (step 6). All bank rows are re-categorised after every bank import
  (payee behaviour needs the whole history): ~2.6k rows take well under a second, 100k+ rows will take
  seconds. Re-categorise only affected payees if needed.
- **Categories for other banks' narrations** (step 6). Features assume SBI's parsed fields.
- **Takeout search history, subscriptions, comments** are ignored (step 3). Only
  `watch-history.json` is read from a Takeout zip.

## Analysis (step 7)

- **Rare events and Spearman** (step 7). Food delivery happens on ~13% of days, so its rho with
  YouTube is only 0.17–0.19 even though delivery is 3x as likely on heavy-YouTube days. It shows up
  in the "weaker signals" tier, not as a main insight. A test made for rare outcomes (logistic
  regression / point-biserial on "any delivery") would rank it better.
- **Weak-signal tier admits chance findings** (step 7). The null test shows ~1.5 false weak signals
  per run (0 false main insights). The UI labels them "may be chance"; keep it that way.
- **Exam late-night YouTube not detected** (step 7). Planted, but only +4 points and not
  significant after correction; the generator's effect is smaller than its README suggests.
- **Time-series dependence** (step 7). Spearman/Mann-Whitney assume independent days; daily habits
  are autocorrelated, so p-values are optimistic. Block bootstrap or effective-n correction would be
  more honest.
- **Sentiment on real chats is untested** (step 7). 79% accuracy is on demo messages written from
  the same vocabulary as the lexicon. Known errors: "ok"/"free" read as positive, Hindi *baad*
  ("later") vs English "bad", sarcasm, "dead 💀" (= very funny) read as negative.
- **Curated lists cover the demo 100% by construction** (step 7). On real data many channels and
  songs will be "unknown" (moods are never guessed). The dashboard should show coverage, and
  the user could label their top unknown channels/songs.
- **Insights need `me`** (step 7). Without "Which one is you?" the user's own message mood metrics
  are NULL; the page shows a tip.
- **Cross-app links are mostly calendar-driven** (step 7). Most strong associations come from exams /
  weekends moving several habits together. Partial correlation controlling for weekend + tagged
  periods would separate "direct" links.

## Dashboard (step 8)

- **First analysis after a cold start is slow** (step 8). Booting Pyodide + the engine (now with the calendar
  control) took ~15 s on the full demo year in the browser; after that the result is cached per range + data
  version (warm runs ~2 s for 30 days). Runs in the worker, so the UI stays usable. Could precompute the
  "All" range right after an import.
- **Weekly charts start on Monday** (step 8): the first bar of a custom range can be a partial week
  (labelled "week of …"). Could normalise per day instead.
- **Scatter plots show raw daily values** (step 8), also for calendar-controlled links, whose statistic is
  computed on residuals. A residual scatter would match the number better.
- **Timeline metric list = all daily metrics** (step 8); it may need grouping on real data with more sources.
- **Demo `me`** (step 8): LOAD DEMO DATA now also sets "Which one is you?" to the demo user (from
  `data/samples/periods.json`) unless a name is already set.

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

- Step 8: dashboard (player stats, timeline, source panels, insights + matrix, periods, day drill-down) and calendar-controlled correlations.

- Step 7: video topics, song moods and message sentiment; cross-app insights, periods and unusual days on the Insights page (cached per range + data version).

- Step 6: bank debits are categorised (in-browser model + rules), with user corrections that survive re-imports.
- Step 4: data survives reloads (DuckDB + IndexedDB snapshots, separate demo/real databases).
- Step 4: Spotify account + extended formats no longer double-count (60 s cross-format rule).
- Step 4: imports append only new events (event_key) instead of re-parsing everything; exact
  same file is skipped by SHA-256.
- Step 4: imports can be removed (Data screen), plus wipe-all per database.
