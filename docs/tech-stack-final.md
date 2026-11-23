# Tech stack: planned vs actually used

The proposal text itself is not in this repository. Rows marked † come from the changes you named (ECharts
instead of Plotly/D3, lexicon instead of Transformers.js); the others are plan changes recorded during the build
(`docs/backlog.md`, `docs/analysis.md`). **Check the "Planned" column against your proposal before submitting.**

## Changed

| Area | Planned | Actually used | Why it changed |
|---|---|---|---|
| Charts † | Plotly / D3 | **Apache ECharts 6.1** (modular import, custom pixel theme) | One library covers every chart we need (calendar heatmap, dual axis, brush/zoom, matrix heatmap) with canvas speed, built-in PNG export and full theming; D3 would mean hand-building each chart, Plotly is heavier and harder to restyle. |
| Sentiment † | Transformers.js (a small transformer model in the browser) | **VADER-style lexicon scorer** in Python (English + Hinglish words + emojis) | A transformer adds tens of MB of download and is slow per message in WASM, and English models don't understand Hinglish; the lexicon is tiny, explainable and reaches 79% (vs 47% baseline) on the demo. |
| Browser storage | OPFS (DuckDB writing straight to the browser's private file system) | **DuckDB in memory + Parquet snapshots in IndexedDB** after every change | The installed duckdb-wasm build did not persist `opfs://` databases; snapshots work everywhere and are small at this data size. |
| Song mood | Spotify audio features (valence, energy) | **Curated song → mood list** (268 songs); unknown songs stay "unknown" | Spotify no longer gives new apps audio features, and the app must not send user data to an API anyway. |
| Bank statements | PDF statements | **SBI Excel/HTML/CSV** download; PDFs are recognised and the user is asked for Excel | Reliable column parsing from PDF needs pdf.js + layout reconstruction (and passwords); Excel has the columns directly. |
| Spend categories | Keyword rules | **Logistic regression** (scikit-learn) on text + rule flags + amount + payee behaviour, trained offline, exported as JSON and run in Pyodide | SBI truncates names and most payees are local shops/people; rules alone reach macro-F1 0.84 on the test statement, the model 0.97. |
| Insight statistics | Correlations between apps | **Spearman + Benjamini–Hochberg** over all tests, lags 0–2, plus **partial correlation** (calendar control), Mann–Whitney for periods, robust z + IsolationForest for anomalies | Plain correlations over hundreds of pairs produce dozens of chance findings; the null test and the calendar control show which findings are real. |
| Fonts | Google Fonts | **Self-hosted** (`@fontsource`, bundled) | Removes the requests to fonts.googleapis.com / fonts.gstatic.com (privacy audit). |
| DuckDB extensions | (not planned) | **Self-hosted `json` + `parquet` extensions** in `web/public/duckdb-ext/` | DuckDB-WASM silently fetched them from `extensions.duckdb.org`; found by the privacy audit. |

## Kept as planned

| Area | Used |
|---|---|
| App | Vite 8 + React 19 + TypeScript 7 + Tailwind CSS 4 (static site, hash routing, no backend) |
| Python in the browser | Pyodide 314.0.8 (CPython 3.14 in WebAssembly) in a Web Worker: pandas 3, NumPy, SciPy 1.18, scikit-learn 1.8 |
| SQL in the browser | DuckDB-WASM 1.33.1-dev57.0 (DuckDB v1.5.4), in its own worker; all SQL in `web/src/sql/*.sql` |
| Zip handling | JSZip |
| Offline ML | pandas + scikit-learn + Jupyter on the developer's machine (`ml/`), versions matched to Pyodide |
| Tests | pytest (parsers, SQL via the DuckDB Python package, enrichment, analysis, dashboard SQL, ML pipeline) |
| Hosting | static site: Vercel or GitHub Pages (`web/vercel.json`, `.github/workflows/pages.yml`) |
