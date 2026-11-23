"""The browser inference (web/src/python/categoriser.py, pure numpy, reads the exported JSON)
must match sklearn's predict_proba to within 1e-6. Trains a small model from scratch."""

import json

import numpy as np
import pytest

import categoriser as browser
import train_categoriser as T
from selfscope_ml import features as F


@pytest.fixture(scope="module")
def data():
    rows, stats_list, y, groups, stmts = T.load_training()
    return rows, stats_list, np.array(y), np.array(stmts)


@pytest.mark.parametrize("class_weight", [None, "balanced"])
def test_json_inference_matches_sklearn(data, class_weight):
    rows, stats_list, y, stmts = data
    tr = np.where(np.isin(stmts, ["S00", "S01", "S02", "S03"]))[0]
    te = np.where(stmts == "S07")[0][:1000]
    docs = [F.text_doc(r) for r in rows]
    dense = T.dense_matrix(rows, stats_list)
    m = T.FullModel(C=2.0, class_weight=class_weight, max_features=3000).fit([docs[i] for i in tr], dense[tr], y[tr])
    sk = m.predict_proba([docs[i] for i in te], dense[te])

    exported = json.loads(json.dumps(T.export_model(m, 0.6, {"trained_at": "test"})))  # through real JSON
    browser.load_model(exported)
    js = browser.predict_proba([rows[i] for i in te], stats_list[te[0]])
    assert len(te) == 1000
    assert np.abs(js - sk).max() < 1e-6
    assert (js.argmax(1) == sk.argmax(1)).all()


def test_shipped_model_is_plain_json():
    with open(T.EXPORT, encoding="utf-8") as f:
        d = json.load(f)
    assert d["feature_version"] == F.FEATURE_VERSION and d["dense"]["names"] == F.DENSE_NAMES
    assert len(d["coef"]) == len(d["classes"]) == len(d["intercept"])
    assert len(d["coef"][0]) == len(d["text"]["vocabulary"]) + len(F.DENSE_NAMES)
    assert 0 < d["threshold"] < 1 and d["test_macro_f1"] > 0
