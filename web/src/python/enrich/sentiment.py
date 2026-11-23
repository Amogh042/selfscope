"""Lightweight, explainable sentiment scorer for WhatsApp messages (English + Hinglish + emoji).

VADER-style rules (Hutto & Gilbert, 2014) re-implemented in a few lines of pure Python so
they run in Pyodide without extra packages:
  - word valences from VADER's lexicon (-4..+4) plus a curated Hinglish lexicon
    (single words and phrases such as "thak gaya", "sahi hai", "mood off") and emojis,
  - boosters / dampeners in the 3 words before ("very", "bahut", "thoda"),
  - negation in the 3 words before ("not", "never") AND, for Hindi word order, in the
    2 words after ("accha nahi", "mazaa nahi aaya"): valence * -0.74,
  - ALL-CAPS emphasis, "but" / "lekin" contrast (before x0.5, after x1.5),
  - exclamation marks (up to 4) push the score further in its direction,
  - compound = sum / sqrt(sum^2 + 15) in [-1, 1]; label pos >= 0.05, neg <= -0.05, else neu
    (VADER's standard thresholds).
Every score can be explained by listing the matched words (see explain()).
"""

from __future__ import annotations

import math
import re

ALPHA = 15.0
NEG_SCALAR = -0.74
CAPS_INCR = 0.733
EXCL_INCR = 0.292
POS_T, NEG_T = 0.05, -0.05

_TOKEN = re.compile(r"[a-z0-9']+", re.I)


class Scorer:
    def __init__(self, lexicon: dict):
        self.words: dict[str, float] = {k.lower(): float(v) for k, v in lexicon["vader"].items()}
        self.phrases: dict[tuple[str, ...], float] = {}
        for k, v in lexicon["hinglish"].items():
            toks = tuple(k.lower().split())
            if len(toks) == 1:
                self.words[toks[0]] = float(v)  # Hinglish single words extend / override VADER
            else:
                self.phrases[toks] = float(v)
        self.max_phrase = max((len(p) for p in self.phrases), default=1)
        self.emoji = {k: float(v) for k, v in lexicon["emoji"].items()}
        self.negations = {n for n in lexicon["negations"] if " " not in n}
        self.boosters = {k: float(v) for k, v in lexicon["boosters"].items() if " " not in k}
        self.contrast = set(lexicon["contrast"])

    def _valence(self, w: str) -> float | None:
        if w in self.words:
            return self.words[w]
        squeezed = re.sub(r"(.)\1{2,}", r"\1\1", w)       # "sooo" -> "soo", "yesss" -> "yess"
        once = re.sub(r"(.)\1+", r"\1", w)                 # "lmaooo" -> "lmao"
        for cand in (squeezed, once):
            if cand in self.words:
                return self.words[cand]
        for suf, rep in (("ing", ""), ("ing", "e"), ("ed", ""), ("ed", "e"), ("s", ""), ("ly", "")):
            if w.endswith(suf) and len(w) > len(suf) + 2 and w[: -len(suf)] + rep in self.words:
                return self.words[w[: -len(suf)] + rep]
        return None

    def explain(self, text: str | None) -> tuple[float, str, list[tuple[str, float]]]:
        """-> (compound, label, [(matched word / phrase / emoji, valence used)])."""
        text = text or ""
        raw = _TOKEN.findall(text)
        toks = [t.lower() for t in raw]
        mixed_case = any(t.isupper() for t in raw) and not all(t.isupper() for t in raw)
        items: list[tuple[int, str, float]] = []  # (token position, label, valence)
        i = 0
        while i < len(toks):
            hit = None
            for n in range(min(self.max_phrase, len(toks) - i), 1, -1):
                if tuple(toks[i:i + n]) in self.phrases:
                    hit = (n, self.phrases[tuple(toks[i:i + n])])
                    break
            if hit:
                n, v = hit
                items.append((i, " ".join(toks[i:i + n]), self._shift(v, toks, i, i + n, raw, mixed_case)))
                i += n
                continue
            v = self._valence(toks[i])
            if v is not None and toks[i] not in self.boosters and toks[i] not in self.negations:
                items.append((i, toks[i], self._shift(v, toks, i, i + 1, raw, mixed_case)))
            i += 1
        # contrast words: what comes after "but" matters more
        for ci, t in enumerate(toks):
            if t in self.contrast:
                items = [(p, w, v * (0.5 if p < ci else 1.5)) for p, w, v in items]
                break
        found = [(w, round(v, 3)) for _, w, v in items]
        for ch, v in self.emoji.items():
            c = text.count(ch)
            if c:
                found += [(ch, v)] * min(c, 3)
        total = sum(v for _, v in found)
        if total:
            total += math.copysign(min(text.count("!"), 4) * EXCL_INCR, total)
        compound = max(-1.0, min(1.0, total / math.sqrt(total * total + ALPHA))) if total else 0.0
        label = "pos" if compound >= POS_T else "neg" if compound <= NEG_T else "neu"
        return round(compound, 4), label, found

    def _shift(self, v: float, toks: list[str], start: int, end: int, raw: list[str], mixed_case: bool) -> float:
        # emphasis: an ALL-CAPS word in a mixed-case message
        if mixed_case and all(raw[k].isupper() and len(raw[k]) > 1 for k in range(start, end)):
            v += math.copysign(CAPS_INCR, v)
        # boosters / dampeners up to 3 words before, weaker further away
        for dist, k in enumerate(range(start - 1, max(start - 4, -1), -1)):
            b = self.boosters.get(toks[k])
            if b is not None:
                v += math.copysign(b, v) * (1.0, 0.95, 0.9)[dist]
        # negation: 3 words before, or 2 words after (Hindi puts "nahi" after the word)
        before = toks[max(0, start - 3):start]
        after = toks[end:end + 2]
        if any(t in self.negations or t.endswith("n't") for t in before + after):
            v *= NEG_SCALAR
        return v

    def score(self, text: str | None) -> tuple[float, str]:
        c, label, _ = self.explain(text)
        return c, label
