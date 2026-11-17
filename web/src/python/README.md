# src/python — in-browser analysis modules

Plain Python + pandas modules that run inside Pyodide (`src/workers/python.worker.ts`)
**and** under normal CPython for tests. No browser-specific code here, and nothing
here runs on a server.

- `schema.py` — shared event format (see `docs/schema.md`): column names, `finalize_events()`
- `parsers/whatsapp.py` — WhatsApp export → shared format (Android + iOS, auto date order)
- `session.py` — in-memory store of parsed frames + JSON summaries for the import screen
- `tests/` — pytest tests with small fixture exports in `tests/fixtures/`

How they get into Pyodide: `src/lib/pythonModules.ts` bundles every `*.py` here and in
`parsers/` as raw text, writes them into Pyodide's virtual filesystem and adds that folder
to `sys.path`. Only use packages Pyodide ships (pandas, numpy, scipy, scikit-learn, …).

## Run the tests with normal Python

Use Python 3.14 to match Pyodide 314 (from the repo root):

```bash
python3.14 -m venv .venv && .venv/bin/pip install -r web/src/python/requirements-test.txt
cd web/src/python && ../../../.venv/bin/python -m pytest
```
