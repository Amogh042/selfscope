"""Train, compare and evaluate the spend categoriser, then export it for the browser.

  1. Load ml/data/training_set.csv (from make_training_set.py) and run every synthetic
     statement through the app's own SBI parser, so training sees exactly what the
     browser sees (truncated names, masked numbers, parsed channel / UPI ID / note).
  2. Compare three approaches with 5-fold GroupKFold by payee (a payee is never in both
     the training and the validation fold):
       a) rules only (keyword dictionary + channel rules, selfscope_ml/rules.py)
       b) text only (TF-IDF char n-grams + logistic regression)
       c) full model (text + rule flags + amount + payee behaviour + logistic regression)
  3. Pick the confidence threshold from out-of-fold predictions.
  4. Fit the final model on all training rows and test it ONCE on the demo statement
     (data/samples/bank/SBI_statement_demo.xlsx vs ml/data/demo_bank_truth.csv), which
     was never used for training or tuning.
  5. Export web/public/models/categoriser.json (no pickle) and check that the browser
     inference (web/src/python/categoriser.py) matches sklearn to within 1e-6.
  6. Write ml/reports/ (charts, results.json, categoriser_report.md).

Usage:  python ml/scripts/train_categoriser.py
"""

from __future__ import annotations

import csv
import io
import json
import os
import sys
import time
from collections import Counter
from datetime import date

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path[:0] = [os.path.join(ROOT, "ml"), os.path.join(ROOT, "web", "src", "python")]

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import sklearn  # noqa: E402
from scipy.sparse import csr_matrix, hstack  # noqa: E402
from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import (accuracy_score, classification_report, confusion_matrix,  # noqa: E402
                             f1_score)
from sklearn.model_selection import GroupKFold  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

import categoriser as browser_categoriser  # noqa: E402  (web/src/python/categoriser.py)
from parsers.sbi import parse_sbi  # noqa: E402
from selfscope_ml import features as F  # noqa: E402
from selfscope_ml import rules as R  # noqa: E402

DATA = os.path.join(ROOT, "ml", "data")
REPORTS = os.path.join(ROOT, "ml", "reports")
EXPORT = os.path.join(ROOT, "web", "public", "models", "categoriser.json")
DEMO = os.path.join(ROOT, "data", "samples", "bank", "SBI_statement_demo.xlsx")
TRUTH = os.path.join(DATA, "demo_bank_truth.csv")

MODEL_VERSION = "1.0"
MAX_FEATURES = 10000       # TF-IDF vocabulary size (keeps the browser JSON ~2 MB)
TARGET_PRECISION = 0.95    # threshold: keep predictions whose out-of-fold accuracy is >= this
GRID = [(c, cw) for c in (0.5, 2.0, 8.0) for cw in (None, "balanced")]
N_SPLITS = 5


# ---------------------------------------------------------------- data

def statement_csv(rows: pd.DataFrame) -> str:
    """Rows of one synthetic statement -> SBI-style CSV text (what parse_sbi reads)."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["Txn Date", "Value Date", "Description", "Ref No./Cheque No.", "Debit", "Credit", "Balance"])
    bal = 1_000_000.0
    for r in rows.itertuples():
        bal -= r.debit
        d = date.fromisoformat(r.txn_date).strftime("%d %b %Y")
        w.writerow([d, d, r.description, r.ref, f"{r.debit:.2f}", " ", f"{bal:.2f}"])
    return buf.getvalue()


def events_to_rows(ev: pd.DataFrame) -> list[dict]:
    return [F.row_from_event(json.loads(m), v, d, wd)
            for m, v, d, wd in zip(ev["meta"], ev["value"], ev["local_date"], ev["weekday"])]


def load_training():
    df = pd.read_csv(os.path.join(DATA, "training_set.csv"), dtype={"ref": str}, keep_default_na=False)
    df["debit"] = df["debit"].astype(float)
    rows, stats_list, y, groups, stmts = [], [], [], [], []
    for sid, part in df.groupby("statement_id", sort=True):
        ev = parse_sbi(statement_csv(part), f"{sid}.csv")
        assert len(ev) == len(part), sid
        assert np.allclose(-ev["value"].to_numpy(), part["debit"].to_numpy()), f"row order mismatch in {sid}"
        r = events_to_rows(ev)
        stats = F.payee_stats(r)
        rows += r
        stats_list += [stats] * len(r)
        y += part["category"].tolist()
        groups += part["payee_group"].tolist()
        stmts += [sid] * len(r)
    return rows, stats_list, np.array(y), np.array(groups), np.array(stmts)


def load_demo():
    with open(DEMO, "rb") as f:
        ev = parse_sbi(f.read(), os.path.basename(DEMO))
    truth = pd.read_csv(TRUTH)
    assert len(truth) == len(ev)
    assert np.allclose(ev["value"].to_numpy(), truth["credit"].fillna(0).to_numpy() - truth["debit"].fillna(0).to_numpy())
    rows = events_to_rows(ev)
    stats = F.payee_stats(rows)
    return rows, [stats] * len(rows), truth["category"].to_numpy(), ev


# ---------------------------------------------------------------- models

def dense_matrix(rows, stats_list):
    return np.array([F.dense_features(r, s) for r, s in zip(rows, stats_list)], dtype=np.float64)


class FullModel:
    """TF-IDF(char n-grams) + standardised dense features -> multinomial logistic regression."""

    def __init__(self, C=2.0, class_weight=None, use_dense=True, max_features=MAX_FEATURES):
        self.C, self.class_weight, self.use_dense, self.max_features = C, class_weight, use_dense, max_features

    def _x(self, docs, dense, fit=False):
        xt = self.vec.fit_transform(docs) if fit else self.vec.transform(docs)
        if not self.use_dense:
            return xt.tocsr()
        xd = self.scaler.fit_transform(dense) if fit else self.scaler.transform(dense)
        return hstack([xt, csr_matrix(xd)]).tocsr()

    def fit(self, docs, dense, y):
        self.vec = TfidfVectorizer(analyzer=F.analyzer, sublinear_tf=True, min_df=2, max_features=self.max_features,
                                   dtype=np.float64)
        self.scaler = StandardScaler()
        self.clf = LogisticRegression(C=self.C, class_weight=self.class_weight, max_iter=5000)
        self.clf.fit(self._x(docs, dense, fit=True), y)
        return self

    def predict_proba(self, docs, dense):
        return self.clf.predict_proba(self._x(docs, dense))

    @property
    def classes_(self):
        return self.clf.classes_


def apply_hard_rules(rows, pred, conf):
    """Rules that always win: ATM withdrawals are cash. (Credits are 'income' elsewhere.)"""
    pred, conf = pred.copy(), conf.copy()
    for i, r in enumerate(rows):
        if r["channel"] == "ATM":
            pred[i], conf[i] = "cash_atm", 1.0
    return pred, conf


def macro_f1(y, p):
    return f1_score(y, p, labels=sorted(set(y)), average="macro", zero_division=0)


def cross_validate(rows, stats_list, y, groups, docs, dense):
    folds = list(GroupKFold(n_splits=N_SPLITS).split(docs, y, groups))
    out = {}

    def run(name, make):
        accs, f1s, oof_p = [], [], np.empty(len(y), dtype=object)
        oof_proba = np.zeros((len(y), len(F.CATEGORIES)))
        for tr, va in folds:
            m = make().fit([docs[i] for i in tr], dense[tr], y[tr])
            proba = m.predict_proba([docs[i] for i in va], dense[va])
            cols = [list(m.classes_).index(c) if c in m.classes_ else None for c in F.CATEGORIES]
            full = np.column_stack([proba[:, j] if j is not None else np.zeros(len(va)) for j in cols])
            pred = np.array(F.CATEGORIES)[full.argmax(1)]
            pred, _ = apply_hard_rules([rows[i] for i in va], pred, full.max(1))
            oof_p[va], oof_proba[va] = pred, full
            accs.append(accuracy_score(y[va], pred))
            f1s.append(macro_f1(y[va], pred))
        out[name] = {"acc": float(np.mean(accs)), "acc_std": float(np.std(accs)), "macro_f1": float(np.mean(f1s)),
                     "macro_f1_std": float(np.std(f1s)), "oof_pred": oof_p, "oof_proba": oof_proba}
        print(f"  {name:28s} acc {out[name]['acc']:.3f}  macro-F1 {out[name]['macro_f1']:.3f} ± {out[name]['macro_f1_std']:.3f}")

    # a) rules only (no training)
    accs, f1s = [], []
    rule_pred = np.array([R.rule_category(r) for r in rows])
    for _, va in folds:
        accs.append(accuracy_score(y[va], rule_pred[va]))
        f1s.append(macro_f1(y[va], rule_pred[va]))
    out["rules"] = {"acc": float(np.mean(accs)), "acc_std": float(np.std(accs)), "macro_f1": float(np.mean(f1s)),
                    "macro_f1_std": float(np.std(f1s)), "oof_pred": rule_pred}
    print(f"  {'rules':28s} acc {out['rules']['acc']:.3f}  macro-F1 {out['rules']['macro_f1']:.3f}")
    # b) text only, c) full model over a small grid
    for C, cw in GRID:
        run(f"text C={C} cw={cw}", lambda C=C, cw=cw: FullModel(C, cw, use_dense=False))
        run(f"full C={C} cw={cw}", lambda C=C, cw=cw: FullModel(C, cw, use_dense=True))
    return out


def pick_threshold(y, proba, pred):
    conf = proba.max(1)
    correct = pred == y
    curve = []
    for t in np.round(np.arange(0.0, 1.0001, 0.01), 2):
        keep = conf >= t
        curve.append({"t": float(t), "coverage": float(keep.mean()),
                      "acc": float(correct[keep].mean()) if keep.any() else 1.0})
    ok = [c for c in curve if c["acc"] >= TARGET_PRECISION]
    return (ok[0]["t"] if ok else 0.5), curve


def reliability(y, proba, pred, bins=10):
    conf, correct = proba.max(1), (pred == y)
    out = []
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        m = (conf >= lo) & ((conf < hi) if b < bins - 1 else (conf <= hi))
        if m.any():
            out.append({"bin": f"{lo:.1f}-{hi:.1f}", "conf": float(conf[m].mean()), "acc": float(correct[m].mean()),
                        "n": int(m.sum())})
    return out


# ---------------------------------------------------------------- export

def _f(x):
    return float(f"{x:.9g}")


def export_model(m: FullModel, threshold, meta) -> dict:
    vocab = sorted(m.vec.vocabulary_, key=m.vec.vocabulary_.get)
    return {
        "model": "selfscope-spend-categoriser",
        "version": MODEL_VERSION,
        "feature_version": F.FEATURE_VERSION,
        "classes": list(m.classes_),
        "threshold": threshold,
        "text": {"vocabulary": vocab, "idf": [_f(v) for v in m.vec.idf_], "sublinear_tf": True, "norm": "l2",
                 "ngram_range": [F.NGRAM_MIN, F.NGRAM_MAX]},
        "dense": {"names": F.DENSE_NAMES, "mean": [_f(v) for v in m.scaler.mean_],
                  "scale": [_f(v) for v in m.scaler.scale_]},
        "coef": [[_f(v) for v in row] for row in m.clf.coef_],
        "intercept": [_f(v) for v in m.clf.intercept_],
        "hard_rules": {"credit": "income", "channel=ATM": "cash_atm",
                       "confidence<threshold": "other (flagged for REVIEW)"},
        **meta,
    }


# ---------------------------------------------------------------- error analysis

def mistake_reason(r, true, pred, s):
    kw = R.keyword_category(r["counterparty"], r["vpa_fragment"])
    name, vpa = r["counterparty"] or "(no name)", r["vpa_fragment"]
    how = f"{s['count']} payments, median ₹{s['median']:.0f}, {s['per_active_day']:.1f} per active day"
    person = R.looks_like_person(r["counterparty"], vpa)
    if kw and kw != true:
        return f"keyword in '{name}' points to {kw}; behaviour ({how}) did not outweigh it"
    if true == "p2p_transfer":
        return (f"a friend paid repeatedly ({how}); the amounts look like a {pred.replace('_', ' ')} payee's and "
                "nothing in the name says 'person'")
    if person and pred in ("transport", "p2p_transfer"):
        return (f"UPI ID '{vpa}' has no shop word (SBI keeps only 10 characters), so it looks like a person's name, "
                f"like the auto drivers paid to name-like IDs in training; {how}")
    if pair_is(true, pred, "entertainment", "meals"):
        return f"cafe vs. restaurant is a labelling convention (cafe = entertainment); ₹{r['amount']:.0f} fits both"
    if pair_is(true, pred, "tea_snacks", "meals"):
        return f"unknown small eatery '{name}' ({how}); its price range overlaps snacks and meals"
    return f"unknown name '{name}' with no keyword; behaviour ({how}) resembles {pred}"


def pair_is(a, b, x, y):
    return {a, b} == {x, y}


# ---------------------------------------------------------------- charts

def save_charts(res, labels, cm):
    os.makedirs(REPORTS, exist_ok=True)
    plt.rcParams.update({"figure.dpi": 130, "font.size": 9})

    # model comparison
    names = ["rules", "text", "full"]
    fig, ax = plt.subplots(figsize=(6.4, 3.2))
    x = np.arange(len(names))
    cvv = [res["comparison"][n]["cv_macro_f1"] for n in names]
    cve = [res["comparison"][n]["cv_macro_f1_std"] for n in names]
    tst = [res["comparison"][n]["test_macro_f1"] for n in names]
    ax.bar(x - 0.18, cvv, 0.36, yerr=cve, label="cross-validation (training set)", color="#a84e00")
    ax.bar(x + 0.18, tst, 0.36, label="final test (demo statement)", color="#ff7a00")
    ax.set_xticks(x, ["Rules only", "Text only", "Full model"])
    ax.set_ylim(0, 1)
    ax.set_ylabel("macro-F1")
    ax.legend(loc="lower right", fontsize=8)
    ax.set_title("Model comparison")
    fig.tight_layout()
    fig.savefig(os.path.join(REPORTS, "model_comparison.png"))
    plt.close(fig)

    # confusion matrix (rows normalised)
    cmn = cm / np.maximum(cm.sum(1, keepdims=True), 1)
    fig, ax = plt.subplots(figsize=(7.5, 6.2))
    im = ax.imshow(cmn, cmap="Oranges", vmin=0, vmax=1)
    ax.set_xticks(range(len(labels)), labels, rotation=45, ha="right")
    ax.set_yticks(range(len(labels)), labels)
    for i in range(len(labels)):
        for j in range(len(labels)):
            if cm[i, j]:
                ax.text(j, i, str(cm[i, j]), ha="center", va="center", fontsize=7,
                        color="white" if cmn[i, j] > 0.6 else "black")
    ax.set_xlabel("predicted")
    ax.set_ylabel("true")
    ax.set_title("Confusion matrix on the demo statement (counts; colour = row share)")
    fig.colorbar(im, fraction=0.046)
    fig.tight_layout()
    fig.savefig(os.path.join(REPORTS, "confusion_matrix.png"))
    plt.close(fig)

    # reliability + threshold
    fig, axes = plt.subplots(1, 2, figsize=(8.5, 3.3))
    rel = res["threshold"]["reliability"]
    axes[0].plot([0, 1], [0, 1], "--", color="#9a9a9a", lw=1)
    axes[0].plot([b["conf"] for b in rel], [b["acc"] for b in rel], "o-", color="#ff7a00")
    axes[0].set_xlabel("mean confidence")
    axes[0].set_ylabel("accuracy")
    axes[0].set_title("Reliability (out-of-fold, training)")
    curve = res["threshold"]["curve"]
    axes[1].plot([c["t"] for c in curve], [c["acc"] for c in curve], color="#ff7a00", label="accuracy kept")
    axes[1].plot([c["t"] for c in curve], [c["coverage"] for c in curve], color="#5fd35f", label="share kept")
    axes[1].axvline(res["threshold"]["value"], color="#a84e00", ls="--", lw=1)
    axes[1].set_xlabel("confidence threshold")
    axes[1].set_title(f"Threshold = {res['threshold']['value']:.2f}")
    axes[1].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(REPORTS, "threshold.png"))
    plt.close(fig)

    # class balance
    fig, ax = plt.subplots(figsize=(7.5, 3.2))
    cats = [c for c in F.CATEGORIES]
    tr = [res["data"]["train_class_share"].get(c, 0) for c in cats]
    te = [res["data"]["test_class_share"].get(c, 0) for c in cats]
    x = np.arange(len(cats))
    ax.bar(x - 0.2, tr, 0.4, label="training set", color="#a84e00")
    ax.bar(x + 0.2, te, 0.4, label="demo test set (debits)", color="#ff7a00")
    ax.set_xticks(x, cats, rotation=40, ha="right")
    ax.set_ylabel("share of debits")
    ax.legend(fontsize=8)
    ax.set_title("Class balance")
    fig.tight_layout()
    fig.savefig(os.path.join(REPORTS, "class_balance.png"))
    plt.close(fig)


# ---------------------------------------------------------------- main

def main():
    t0 = time.time()
    print("loading training set (parsed with the app's SBI parser)…")
    rows, stats_list, y, groups, stmts = load_training()
    docs = [F.text_doc(r) for r in rows]
    dense = dense_matrix(rows, stats_list)
    print(f"  {len(rows):,} debits, {len(set(groups))} payees, {len(set(stmts))} statements")

    print(f"cross-validation ({N_SPLITS}-fold GroupKFold by payee)…")
    cv = cross_validate(rows, stats_list, y, groups, docs, dense)
    best_text = max((k for k in cv if k.startswith("text")), key=lambda k: cv[k]["macro_f1"])
    best_full = max((k for k in cv if k.startswith("full")), key=lambda k: cv[k]["macro_f1"])
    C, cw = GRID[[f"full C={c} cw={w}" for c, w in GRID].index(best_full)]
    tC, tcw = GRID[[f"text C={c} cw={w}" for c, w in GRID].index(best_text)]
    print(f"  best text: {best_text} | best full: {best_full}")

    threshold, curve = pick_threshold(y, cv[best_full]["oof_proba"], cv[best_full]["oof_pred"])
    rel = reliability(y, cv[best_full]["oof_proba"], cv[best_full]["oof_pred"])
    oof_cov = next(c["coverage"] for c in curve if c["t"] == threshold)
    print(f"  threshold {threshold:.2f} keeps {oof_cov:.1%} of out-of-fold predictions at >= {TARGET_PRECISION:.0%} accuracy")

    print("final fit on all training rows…")
    full = FullModel(C, cw, use_dense=True).fit(docs, dense, y)
    text = FullModel(tC, tcw, use_dense=False).fit(docs, dense, y)

    print("FINAL TEST on the demo statement (never used for training or tuning)…")
    drows, dstats, dtruth, dev = load_demo()
    deb = np.array([r["is_debit"] for r in drows])
    trows = [r for r, d in zip(drows, deb) if d]
    tdocs = [F.text_doc(r) for r in trows]
    tdense = dense_matrix(trows, [s for s, d in zip(dstats, deb) if d])
    ytest = dtruth[deb]
    credits_ok = float((dtruth[~deb] == "income").mean())

    def test_pred(m):
        p = m.predict_proba(tdocs, tdense)
        pred = np.array(m.classes_)[p.argmax(1)]
        return (*apply_hard_rules(trows, pred, p.max(1)), p)

    full_pred, full_conf, full_proba = test_pred(full)
    text_pred, _, _ = test_pred(text)
    rules_pred = np.array([R.rule_category(r) for r in trows])
    final_pred = np.where(full_conf >= threshold, full_pred, "other")
    review = full_conf < threshold

    labels = sorted(set(ytest))
    report = classification_report(ytest, full_pred, labels=labels, output_dict=True, zero_division=0)
    cm = confusion_matrix(ytest, full_pred, labels=labels)
    pairs = Counter((t, p) for t, p in zip(ytest, full_pred) if t != p).most_common()

    # known brands vs unknown local payees
    with open(os.path.join(DATA, "merchant_labels.csv"), encoding="utf-8") as f:
        brand_names = {r["name"][:8] for r in csv.DictReader(f) if r["kind"] == "merchant"}
    known = np.array([r["counterparty"][:8] in brand_names or R.keyword_category(r["counterparty"], r["vpa_fragment"])
                      is not None for r in trows])

    # 15 mistakes: first one per (confusion pair, payee) so every kind of error is shown,
    # most confident first; then fill up with further examples of the same payees
    err = [i for i in np.argsort(-full_conf) if ytest[i] != full_pred[i]]
    seen, chosen = set(), []
    for i in err:
        key = (ytest[i], full_pred[i], F.payee_key(trows[i]))
        if key not in seen:
            seen.add(key)
            chosen.append(i)
    per_payee = Counter(F.payee_key(trows[i]) for i in chosen)
    for i in err:  # then at most 2 examples per payee, then anything
        if i not in chosen and per_payee[F.payee_key(trows[i])] < 2:
            chosen.append(i)
            per_payee[F.payee_key(trows[i])] += 1
    chosen += [i for i in err if i not in chosen]
    mistakes = []
    for i in chosen[:15]:
        t, p = ytest[i], full_pred[i]
        r, s = trows[i], dstats[0][F.payee_key(trows[i])]
        mistakes.append({"date": r["local_date"], "payee": r["counterparty"], "upi_id": r["vpa_fragment"],
                         "amount": r["amount"], "true": t, "pred": p, "confidence": round(float(full_conf[i]), 3),
                         "reason": mistake_reason(r, t, p, s)})
    payee_errors = Counter(F.payee_key(trows[i]) for i in err)

    print("exporting for the browser + parity check…")
    today = date.today().isoformat()
    test_metrics = {"accuracy": round(float(accuracy_score(ytest, full_pred)), 4),
                    "macro_f1": round(float(macro_f1(ytest, full_pred)), 4),
                    "accuracy_with_threshold": round(float(accuracy_score(ytest, final_pred)), 4),
                    "macro_f1_with_threshold": round(float(macro_f1(ytest, final_pred)), 4),
                    "review_count": int(review.sum()), "review_share": round(float(review.mean()), 4),
                    "debits": int(len(ytest)), "credits": int((~deb).sum()), "credits_income_rule_accuracy": credits_ok}
    exported = export_model(full, threshold, {
        "trained_at": today, "training_rows": len(rows), "sklearn_version": sklearn.__version__,
        "cv_macro_f1": round(cv[best_full]["macro_f1"], 4), "test_macro_f1": test_metrics["macro_f1"],
        "test_accuracy": test_metrics["accuracy"], "hyperparameters": {"C": C, "class_weight": cw,
                                                                         "max_features": MAX_FEATURES}})
    browser_categoriser.load_model(exported)
    jp = browser_categoriser.predict_proba(trows, dstats[0])
    order = [list(full.classes_).index(c) for c in exported["classes"]]
    parity = float(np.abs(jp - full_proba[:, order]).max())
    assert parity < 1e-6, f"browser inference differs from sklearn by {parity}"
    os.makedirs(os.path.dirname(EXPORT), exist_ok=True)
    with open(EXPORT, "w", encoding="utf-8") as f:
        json.dump(exported, f, separators=(",", ":"))
    size_kb = os.path.getsize(EXPORT) / 1024
    print(f"  max |browser - sklearn| probability difference on {len(trows):,} rows: {parity:.2e}")
    print(f"  wrote {os.path.relpath(EXPORT, ROOT)} ({size_kb:,.0f} KB)")

    def cmp(name, cvk, test_p):
        return {"cv_acc": round(cv[cvk]["acc"], 4), "cv_macro_f1": round(cv[cvk]["macro_f1"], 4),
                "cv_macro_f1_std": round(cv[cvk]["macro_f1_std"], 4),
                "test_acc": round(float(accuracy_score(ytest, test_p)), 4),
                "test_macro_f1": round(float(macro_f1(ytest, test_p)), 4), "config": cvk}

    res = {
        "model_version": MODEL_VERSION, "trained_at": today, "seconds": None,
        "versions": {"sklearn": sklearn.__version__, "numpy": np.__version__, "pandas": pd.__version__},
        "data": {"train_rows": len(rows), "train_payees": int(len(set(groups))), "train_statements": int(len(set(stmts))),
                 "train_class_share": {k: round(v / len(y), 4) for k, v in Counter(y).items()},
                 "test_debits": int(len(ytest)),
                 "test_class_share": {k: round(v / len(ytest), 4) for k, v in Counter(ytest).items()}},
        "comparison": {"rules": cmp("rules", "rules", rules_pred), "text": cmp("text", best_text, text_pred),
                       "full": cmp("full", best_full, full_pred)},
        "grid": {k: {"cv_macro_f1": round(v["macro_f1"], 4), "cv_acc": round(v["acc"], 4)} for k, v in cv.items()
                 if k != "rules"},
        "threshold": {"value": threshold, "target_precision": TARGET_PRECISION, "oof_coverage": oof_cov,
                      "curve": curve, "reliability": rel},
        "test": test_metrics,
        "test_known_vs_unknown": {
            "known_share": round(float(known.mean()), 4),
            "known_acc": round(float((full_pred[known] == ytest[known]).mean()), 4),
            "unknown_acc": round(float((full_pred[~known] == ytest[~known]).mean()), 4)},
        "per_class": {k: {m: round(v[m], 4) for m in ("precision", "recall", "f1-score", "support")}
                      for k, v in report.items() if k in labels},
        "confusion": {"labels": labels, "matrix": cm.tolist()},
        "top_confusions": [{"true": t, "pred": p, "count": n} for (t, p), n in pairs[:10]],
        "mistakes": mistakes,
        "errors_by_payee": [{"payee": k, "errors": n} for k, n in payee_errors.most_common(8)],
        "review_by_true_class": dict(Counter(ytest[review])),
        "parity_max_abs_diff": parity, "export_kb": round(size_kb),
    }
    res["seconds"] = round(time.time() - t0)
    save_charts(res, labels, cm)
    with open(os.path.join(REPORTS, "results.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2)
    write_report(res)
    print(f"done in {res['seconds']} s -> ml/reports/")
    print(json.dumps({k: res["comparison"][k] for k in res["comparison"]}, indent=1))
    print(json.dumps(test_metrics, indent=1))


# ---------------------------------------------------------------- report

def write_report(res):
    c, t, th = res["comparison"], res["test"], res["threshold"]
    pc = res["per_class"]
    lines = []
    w = lines.append
    w("# Spend categoriser — report")
    w("")
    w(f"Model v{res['model_version']} · trained {res['trained_at']} · scikit-learn {res['versions']['sklearn']} · "
      f"generated by `ml/scripts/train_categoriser.py` (numbers below are filled in automatically).")
    w("")
    w("## 1. What it does")
    w("")
    w("Every **debit** in a bank statement gets one of 12 categories: tea_snacks, meals, food_delivery, "
      "groceries_qcommerce, transport, shopping, entertainment, bills_recharge, subscriptions, p2p_transfer, "
      "cash_atm, other. **Credits** are always `income` (a rule, not the model). ATM withdrawals are always "
      "`cash_atm` (rule). Everything runs in the browser; no transaction leaves the device.")
    w("")
    w("The hard part: SBI cuts payee names to ~8 characters (`MAIN CAN`, `SRI LAKS`) and most small vendors "
      "and people have names the model has never seen. So besides the text, the model looks at **behaviour**: "
      "a payee you pay ₹25 several times a day is almost certainly a tea stall, whatever its name.")
    w("")
    w("## 2. Data — training and test are independent")
    w("")
    d = res["data"]
    w(f"- **Training set:** {d['train_rows']:,} synthetic debits from {d['train_statements']} synthetic users "
      f"({d['train_payees']} distinct payees), made by `ml/scripts/make_training_set.py` from a hand-written list of "
      "434 real Indian merchants/brands plus 20 UPI handle patterns (`ml/data/merchant_labels.csv`), and synthetic "
      "tea stalls, canteens, auto drivers and friends with **their own name lists, random stream and year (2024)**.")
    w(f"- **Test set:** the demo SBI statement (`data/samples/bank/SBI_statement_demo.xlsx`, {d['test_debits']:,} debits) "
      "with its answer key `ml/data/demo_bank_truth.csv`. It was **never** used for training, feature design or "
      "choosing hyper-parameters — only for the final numbers below. A test checks that no demo vendor or person "
      "name appears in the training data. Real brands (Swiggy, Zomato, …) appear in both, as they would in real life.")
    w("- Both are realistic, not balanced: tea/snack and meal payments dominate (see chart).")
    w("")
    w("![class balance](class_balance.png)")
    w("")
    w("## 3. Features (`ml/selfscope_ml/features.py`, shared with the browser)")
    w("")
    w("| Group | What | Why |")
    w("|---|---|---|")
    w("| Text | character 2–5-grams of payee name + UPI ID + note (digits → 0), bank code and channel as tokens; TF-IDF | handles truncated names (`SWIGGY`, `swiggy.sto`) |")
    w("| Rule flags | channel one-hot, person-like UPI ID, phone-number UPI ID, shop QR handle (`paytmqr…`, `q…@ybl`), keyword-dictionary category | cheap, strong signals |")
    w("| Amount | log amount, round-number flags, amount buckets | ₹25 vs ₹450 vs ₹2,000 |")
    w("| Payee behaviour | over the whole statement, per payee: number of payments, payments per active day, median and spread of the amount, weekend share, regularity, this amount vs. the payee's usual | recognises routines when the name is unknown |")
    w("")
    w("## 4. Models compared")
    w("")
    w(f"Cross-validation: {N_SPLITS}-fold **GroupKFold by payee** on the training set, so a payee is never seen in "
      "training and validation at the same time (this measures how well the model handles *new* payees). "
      "Logistic regression; C and class weighting picked by cross-validated macro-F1 only.")
    w("")
    w("| Model | CV accuracy | CV macro-F1 | Test accuracy | Test macro-F1 |")
    w("|---|---|---|---|---|")
    for key, label in (("rules", "a) Rules only (keyword dictionary + channel rules)"),
                       ("text", "b) Text only (TF-IDF + logistic regression)"),
                       ("full", "c) **Full model** (text + rule flags + amount + payee behaviour)")):
        x = c[key]
        w(f"| {label} | {x['cv_acc']:.3f} | {x['cv_macro_f1']:.3f} ± {x['cv_macro_f1_std']:.3f} | "
          f"{x['test_acc']:.3f} | {x['test_macro_f1']:.3f} |")
    w("")
    w(f"Chosen settings: `{c['full']['config']}` (full), `{c['text']['config']}` (text only).")
    w("")
    w("![model comparison](model_comparison.png)")
    w("")
    w("## 5. Final test on the demo statement")
    w("")
    w(f"- **Accuracy {t['accuracy']:.1%}**, **macro-F1 {t['macro_f1']:.3f}** on {t['debits']:,} debits "
      "(macro-F1 averages the F1 of every category equally, so small categories count as much as tea).")
    w(f"- Credits: {t['credits']} rows, all `income` by rule ({t['credits_income_rule_accuracy']:.0%} correct).")
    k = res["test_known_vs_unknown"]
    w(f"- Payees with a known brand/keyword ({k['known_share']:.0%} of debits): accuracy {k['known_acc']:.1%}. "
      f"Unknown local payees and people: {k['unknown_acc']:.1%}.")
    w(f"- With the confidence threshold applied (low-confidence → `other` + REVIEW): accuracy "
      f"{t['accuracy_with_threshold']:.1%}, macro-F1 {t['macro_f1_with_threshold']:.3f}.")
    w("")
    w("| Category | Precision | Recall | F1 | Support |")
    w("|---|---|---|---|---|")
    for cat, v in pc.items():
        w(f"| {cat} | {v['precision']:.2f} | {v['recall']:.2f} | {v['f1-score']:.2f} | {int(v['support'])} |")
    w("")
    w("![confusion matrix](confusion_matrix.png)")
    w("")
    w("**Most common confusions** (true → predicted):")
    w("")
    for x in res["top_confusions"][:5]:
        w(f"- {x['true']} → {x['pred']}: {x['count']}")
    w("")
    w("**Errors by payee** — most mistakes come from very few payees, because the model decides per payee "
      "pattern (all payments to one canteen look alike):")
    w("")
    for x in res["errors_by_payee"][:5]:
        w(f"- `{x['payee']}`: {x['errors']} wrong")
    w("")
    w("The largest one is a canteen whose UPI ID (`annapoornamess@…`) is cut by SBI to `annapoorna`: without the "
      "word *mess* it looks like a person's name, and in the training data name-like IDs with small, regular, "
      "fixed amounts were mostly auto drivers. The training data has few shops with long names whose shop word "
      "gets cut off. **We did not change the training data after seeing this**, because that would tune the model "
      "on the test set and make the test number dishonest. In the app, one correction with \"apply to all payments "
      "to this payee\" fixes every such row; the next model version should add such shops to the training data and "
      "be evaluated on a new, unseen test statement (see `docs/backlog.md`).")
    w("")
    w("## 6. Confidence threshold and REVIEW")
    w("")
    w(f"The model's top probability is used as its confidence. On out-of-fold predictions (training set), the "
      f"smallest threshold where the kept predictions are at least {th['target_precision']:.0%} accurate is "
      f"**{th['value']:.2f}**; it keeps {th['oof_coverage']:.1%} of them. Below it, the app shows the category as "
      "`other` and lists the transaction under **REVIEW** for the user to fix.")
    w(f"On the demo statement **{t['review_count']} of {t['debits']:,} debits ({t['review_share']:.1%})** fall below "
      f"the threshold. By true category: {', '.join(f'{k} {v}' for k, v in sorted(res['review_by_true_class'].items(), key=lambda x: -x[1]))}.")
    w("")
    w("![reliability and threshold](threshold.png)")
    w("")
    w("## 7. Error analysis — 15 mistakes")
    w("")
    w("| Date | Payee | UPI ID | ₹ | True | Predicted | Conf. | Why it went wrong |")
    w("|---|---|---|---|---|---|---|---|")
    for m in res["mistakes"]:
        w(f"| {m['date']} | `{m['payee']}` | `{m['upi_id']}` | {m['amount']:.0f} | {m['true']} | {m['pred']} | "
          f"{m['confidence']:.2f} | {m['reason']} |")
    w("")
    w("## 8. Limitations")
    w("")
    w("- **Synthetic data on both sides.** Training rows are generated from a merchant list and simulated habits; the "
      "test statement is also generated (from a real student routine). Real-world accuracy on real statements is "
      "**unknown** and probably lower — real narrations are messier and real people's habits vary more.")
    w("- **Truncated names.** SBI keeps ~8 characters of the payee; different shops can collide, and a brand the "
      "model never saw is only recognised by its behaviour.")
    w("- **Labelling conventions** decide some 'errors': sit-down cafe chains are `entertainment`, a canteen is "
      "`meals`, a tea stall is `tea_snacks`, friends paying back are `income`. Someone else might label differently.")
    w("- **Autos paid to phone numbers** look exactly like friends; only the fixed small fare separates them.")
    w("- **Behaviour features need history.** A payee seen once has no routine to learn from.")
    w("- **Test score is higher than cross-validation** because the demo statement is a tidy, regular routine with "
      "many well-known brands, while cross-validation holds out whole payees (including brands) the model has "
      "never seen. The cross-validation number is the more cautious estimate for a new user.")
    w("- Only SBI narrations are handled (see `docs/backlog.md`).")
    w("")
    w("## 9. How to retrain")
    w("")
    w("```bash")
    w("# from the repo root, with the venv from web/src/python/README.md + ml/requirements.txt")
    w(".venv/bin/python ml/scripts/make_training_set.py     # ml/data/training_set.csv")
    w(".venv/bin/python ml/scripts/train_categoriser.py     # CV, test, export, this report")
    w("cd ml && ../.venv/bin/python -m pytest                # pipeline + parity tests")
    w("```")
    w("")
    w("To change the categories or features: edit `ml/selfscope_ml/` (the browser copy is synced by "
      "`web/scripts/sync-ml.mjs`), bump `FEATURE_VERSION` / `MODEL_VERSION`, retrain. The app re-categorises stored "
      "bank rows automatically when the model version changes; user overrides are kept.")
    w("")
    w("## 10. Reproducibility")
    w("")
    w(f"- Seeds: training set `train:2027`; demo data `--seed 42` (separate bank stream).")
    w(f"- Versions: scikit-learn {res['versions']['sklearn']}, numpy {res['versions']['numpy']}, pandas "
      f"{res['versions']['pandas']} (same as Pyodide 314.0.8).")
    w(f"- Export: `web/public/models/categoriser.json` ({res['export_kb']:,} KB, plain JSON, no pickle). The browser "
      f"inference (`web/src/python/categoriser.py`) matches sklearn's `predict_proba` to "
      f"**{res['parity_max_abs_diff']:.1e}** (max absolute difference) on every demo debit.")
    w(f"- Full pipeline run time: {res['seconds']} s.")
    with open(os.path.join(REPORTS, "categoriser_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
