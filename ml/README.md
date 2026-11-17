# ml — offline training pipeline

Train models on **synthetic or your own local data** on your machine, then export
small artefacts that the browser app loads into Pyodide. Nothing here is deployed
and no user data is uploaded anywhere.

```bash
cd ml
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
jupyter lab
```

- `notebooks/` — exploration and experiments
- `scripts/` — reproducible training / export scripts
- `models/` — exported model artefacts consumed by `web/`

Keep scikit-learn's version matched to the one Pyodide ships (see `requirements.txt`),
otherwise pickled models may fail to load in the browser.
