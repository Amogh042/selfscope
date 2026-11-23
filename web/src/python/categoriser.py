"""Spend categoriser — inference only, pure Python + numpy (no scikit-learn, no pickle).

Loads the model exported by ml/scripts/train_categoriser.py (web/public/models/
categoriser.json) and reproduces sklearn's TfidfVectorizer + StandardScaler +
LogisticRegression.predict_proba exactly (checked to 1e-6 at export time and in tests).
Features come from selfscope_ml/features.py, a byte-identical copy of ml/selfscope_ml/.

Decision rules, in order:
  credit                      -> income         (source "rule")
  channel ATM                 -> cash_atm       (source "rule")
  model confidence >= threshold -> model class  (source "model")
  otherwise                   -> shown as other, flagged for REVIEW (source "review");
                                 the model's best guess is kept in model_category
User overrides are applied afterwards in SQL (src/sql/categorise.sql) and always win.
"""

from __future__ import annotations

import json
import math
from collections import Counter

import numpy as np

from selfscope_ml import features as F

_MODEL: "_Model | None" = None


class _Model:
    def __init__(self, d: dict):
        if d.get("feature_version") != F.FEATURE_VERSION or d["dense"]["names"] != F.DENSE_NAMES:
            raise ValueError("categoriser.json was trained with different features; retrain or update the app")
        self.version = d["version"]
        self.classes = list(d["classes"])
        self.threshold = float(d["threshold"])
        self.meta = {k: d.get(k) for k in ("version", "trained_at", "test_macro_f1", "test_accuracy", "threshold")}
        vocab = d["text"]["vocabulary"]
        self.index = {g: i for i, g in enumerate(vocab)}
        self.idf = np.asarray(d["text"]["idf"], dtype=np.float64)
        self.sublinear = bool(d["text"]["sublinear_tf"])
        self.mean = np.asarray(d["dense"]["mean"], dtype=np.float64)
        self.scale = np.asarray(d["dense"]["scale"], dtype=np.float64)
        coef = np.asarray(d["coef"], dtype=np.float64)
        self.coef_text, self.coef_dense = coef[:, :len(vocab)], coef[:, len(vocab):]
        self.intercept = np.asarray(d["intercept"], dtype=np.float64)

    def logits(self, row: dict, stats: dict) -> np.ndarray:
        counts = Counter(g for g in F.analyzer(F.text_doc(row)) if g in self.index)
        z = self.intercept.copy()
        if counts:
            idx = np.fromiter((self.index[g] for g in counts), dtype=np.int64, count=len(counts))
            tf = np.fromiter(counts.values(), dtype=np.float64, count=len(counts))
            if self.sublinear:
                tf = 1.0 + np.log(tf)
            v = tf * self.idf[idx]
            norm = math.sqrt(float(v @ v))
            if norm > 0:
                z += self.coef_text[:, idx] @ (v / norm)
        dense = (np.asarray(F.dense_features(row, stats), dtype=np.float64) - self.mean) / self.scale
        return z + self.coef_dense @ dense


def load_model(model) -> None:
    """Load from a dict or JSON text. Cached for the rest of the worker's life."""
    global _MODEL
    _MODEL = _Model(json.loads(model) if isinstance(model, (str, bytes)) else model)


def model_info() -> dict | None:
    return _MODEL.meta if _MODEL else None


def predict_proba(rows: list[dict], stats: dict) -> np.ndarray:
    """Class probabilities (columns = model classes) — same as sklearn predict_proba."""
    if _MODEL is None:
        raise RuntimeError("categoriser model not loaded")
    z = np.vstack([_MODEL.logits(r, stats) for r in rows]) if rows else np.zeros((0, len(_MODEL.classes)))
    z -= z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def categorise(rows: list[dict], stats: dict | None = None) -> list[dict]:
    """-> one {model_category, confidence, source} per row (see module docstring)."""
    stats = stats if stats is not None else F.payee_stats(rows)
    debit_idx = [i for i, r in enumerate(rows) if r["is_debit"] and r["channel"] != "ATM"]
    proba = predict_proba([rows[i] for i in debit_idx], stats)
    out: list[dict] = []
    for r in rows:
        if not r["is_debit"]:
            out.append({"model_category": "income", "confidence": 1.0, "source": "rule"})
        elif r["channel"] == "ATM":
            out.append({"model_category": "cash_atm", "confidence": 1.0, "source": "rule"})
        else:
            out.append(None)  # filled below
    for k, i in enumerate(debit_idx):
        j = int(proba[k].argmax())
        conf = float(proba[k, j])
        out[i] = {"model_category": _MODEL.classes[j], "confidence": round(conf, 4),
                  "source": "model" if conf >= _MODEL.threshold else "review"}
    return out


def categorise_events_json(events_json: str, model_json: str | None = None) -> str:
    """Worker entry point. events: [{event_key, local_date, weekday, value, meta}] for ALL stored
    bank rows (payee behaviour is computed over the whole statement history)."""
    if model_json:
        load_model(model_json)
    events = json.loads(events_json)
    rows = [F.row_from_event(json.loads(e["meta"]) if isinstance(e["meta"], str) else e["meta"],
                             e["value"], e["local_date"], e["weekday"]) for e in events]
    preds = categorise(rows)
    return json.dumps({
        "model": _MODEL.meta,
        "predictions": [{"event_key": e["event_key"], **p, "model_version": _MODEL.version}
                        for e, p in zip(events, preds)],
    })
