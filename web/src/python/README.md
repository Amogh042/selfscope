# src/python — in-browser analysis modules

Plain `.py` modules that run inside Pyodide (in `src/workers/python.worker.ts`).
Nothing here runs on a server.

Planned pattern (not wired up yet):

- Import a module's source with Vite's `?raw` suffix, e.g. `import src from './python/upi.py?raw'`.
- Write it into Pyodide's virtual filesystem and `import` it from Python.
- Only use packages that Pyodide ships (pandas, numpy, scipy, scikit-learn, …).
- Models trained offline in `ml/` are loaded here as small exported artefacts.
