# ml/selfscope_ml — shared ML code

`features.py` (feature extraction) and `rules.py` (keyword dictionary, rule flags, rules-only baseline)
are pure Python (standard library only), so the same code runs in offline training and in the browser.

- **Source of truth:** this folder. Training (`ml/scripts/train_categoriser.py`) imports it from here.
- **Browser copy:** `web/src/python/selfscope_ml/`, a byte-identical copy written by
  `web/scripts/sync-ml.mjs` (run automatically before `npm run dev` / `npm run build`, or with
  `npm run sync-ml`). Pyodide imports it from there (`web/src/lib/pythonModules.ts`).
- `web/src/python/tests/test_categoriser.py` fails if the two copies differ.

Changing features: edit here, bump `FEATURE_VERSION`, run `npm run sync-ml`, retrain. The exported
model records the feature version; the browser refuses a model trained with different features.
