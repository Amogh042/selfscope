# src/python — in-browser analysis modules

Plain Python + pandas modules that run inside Pyodide (`src/workers/python.worker.ts`)
**and** under normal CPython for tests. No browser-specific code here, and nothing
here runs on a server.

- `schema.py` — shared event format (see `docs/schema.md`): column names, `finalize_events()`
- `parsers/whatsapp.py` — WhatsApp export → shared format (Android + iOS, auto date order)
- `parsers/spotify.py`, `parsers/youtube.py` — Spotify (both formats) and Takeout watch history
- `parsers/sbi.py` — SBI statements (XLSX / HTML / text .xls / CSV; binary .xls via xlrd)
- `categoriser.py` — spend categoriser inference (pure numpy; loads `web/public/models/categoriser.json`)
- `selfscope_ml/` — **copy** of `ml/selfscope_ml/` (features + rules), synced by `web/scripts/sync-ml.mjs`;
  edit the original in `ml/`, never this copy
- `enrich/` — video topic (`youtube_topics.py`), song mood + language (`music_moods.py`),
  message sentiment (`sentiment.py`, VADER-style + Hinglish/emoji); `runner.py` is the worker entry point.
  Curated resources are in `web/public/data/`
- `analysis/` — the analysis engine: `trends.py`, `correlations.py` (Spearman lags 0–2, BH FDR),
  `periods.py` (Mann-Whitney), `anomalies.py` (robust z + IsolationForest), `engine.py` (entry point),
  `validation.py` (null test), `metrics.py` (metric names and plain-English phrases). Methods: `docs/analysis.md`
- `stage.py` — parsed frame → Parquet (pyarrow) / CSV staging file for DuckDB
- `session.py` — worker entry point: parse one file and stage it
- `tests/` — pytest tests with small fixture exports in `tests/fixtures/`; `test_storage.py`
  runs `web/src/sql/*.sql` with the duckdb Python package on the demo data (`tests/sqlkit.py`);
  `test_analysis.py` checks the planted demo patterns are rediscovered and runs the null test (`tests/demo_pipeline.py`)

How they get into Pyodide: `src/lib/pythonModules.ts` bundles every `*.py` here, in
`parsers/`, `selfscope_ml/`, `enrich/` and `analysis/` as raw text, writes them into Pyodide's virtual filesystem and adds that folder
to `sys.path`. Only use packages Pyodide ships (pandas, numpy, scipy, scikit-learn, …).

## Run the tests with normal Python

Use Python 3.14 to match Pyodide 314 (from the repo root):

```bash
python3.14 -m venv .venv && .venv/bin/pip install -r web/src/python/requirements-test.txt
cd web/src/python && ../../../.venv/bin/python -m pytest
```
