# ml/models

Exported model artefacts that the browser loads into Pyodide. Keep them small, and
only commit models trained on synthetic data — a model trained on real exports can
memorise personal details.

Models the browser fetches at runtime are written straight to `web/public/models/` so Vite serves them:

- `web/public/models/categoriser.json` — spend categoriser (plain JSON: TF-IDF vocabulary + idf, feature
  scaling, logistic-regression coefficients, class list, confidence threshold, version, training date,
  test macro-F1). Written by `ml/scripts/train_categoriser.py`. No pickle, so there is no scikit-learn
  version coupling with Pyodide.
