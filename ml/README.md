# ml — offline training pipeline

Train models on **synthetic or your own local data** on your machine, then export
small artefacts that the browser app loads into Pyodide. Nothing here is deployed
and no user data is uploaded anywhere.

```bash
# from the repo root
python3.14 -m venv .venv
.venv/bin/pip install -r ml/requirements.txt -r web/src/python/requirements-test.txt
```

- `data/` — merchant list, training set, demo answer key (see `data/README.md`)
- `selfscope_ml/` — feature + rule code shared with the browser (see `selfscope_ml/README.md`)
- `scripts/` — `generate_demo_data.py` (demo exports), `make_training_set.py`, `train_categoriser.py`
- `notebooks/` — `01_spend_categoriser.ipynb`: the categoriser story with charts
- `reports/` — `categoriser_report.md` + charts + `results.json` (written by `train_categoriser.py`)
- `tests/` — `cd ml && ../.venv/bin/python -m pytest`
- `models/` — see `models/README.md`

## Spend categoriser

```bash
.venv/bin/python ml/scripts/make_training_set.py   # -> ml/data/training_set.csv
.venv/bin/python ml/scripts/train_categoriser.py   # -> web/public/models/categoriser.json + ml/reports/
.venv/bin/jupyter nbconvert --to notebook --execute --inplace ml/notebooks/01_spend_categoriser.ipynb
```

The demo statement's answer key (`data/demo_bank_truth.csv`) is the **final test set**: it is used once,
at the end of `train_categoriser.py`, and never for training, feature design or tuning.
