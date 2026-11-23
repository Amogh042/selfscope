# Analysis engine — methods, reasons, limits, validation

Code: `web/src/python/enrich/` (enrichment) and `web/src/python/analysis/` (engine). Both are plain
Python + pandas / scipy / scikit-learn, so the same code runs in the browser (Pyodide) and in the tests.
Validation numbers below come from `ml/scripts/validate_analysis.py` (`ml/reports/analysis_validation.json`)
and `ml/scripts/eval_sentiment.py` (`ml/reports/sentiment_report.md`), on the synthetic demo year.

## 1. Enrichment — turning raw events into meaning

| Source | What we add | How | Demo coverage |
|---|---|---|---|
| YouTube | topic: study / music / comedy / podcast / tech / finance / other | curated channel → topic map (`web/public/data/youtube_channels.json`, 155 channels), then keyword rules on the title ("tutorial", "one shot" → study, "video song" → music, …) | 100% of non-ad videos (all demo channels are in the map). **Title rules alone** label 90% and agree with the map 87% of the time — the fairer estimate for unknown channels |
| Spotify | mood: romantic / sad / upbeat / unknown; language: hi / en / kn / other / unknown | curated song list (`song_moods.json`, 268 songs incl. every demo song) + artist → language map | 100% (by construction: the demo songs are on the list). Real libraries will have many "unknown" songs |
| WhatsApp | sentiment score −1..1 and pos / neu / neg | lexicon scorer (below) | every text message is scored |

**Why a curated song list?** Spotify no longer gives new apps its audio features (valence, energy, …), so
mood cannot be looked up. Unknown songs stay **unknown** and are **left out** of mood statistics — never
guessed — so the sad-song share is "share among songs whose mood we know".

**Sentiment scorer.** A VADER-style scorer (Hutto & Gilbert, 2014) re-implemented in ~100 lines so it runs
in the browser without extra downloads: VADER's English word list (MIT licence, vendored as JSON), plus a
hand-curated Hinglish list (*tension, pareshan, bakwas, thak gaya* → negative; *mast, badhiya, sahi hai,
mazaa* → positive) and emojis (😭😢😡 negative, 😂❤️🔥🙏 positive). Rules: boosters ("very", "bahut"),
negation before the word ("not good") **and after it** for Hindi word order ("accha nahi"), CAPS,
"but/lekin" contrast, exclamation marks; score = sum / √(sum² + 15). Every score can be explained by the
words it matched. Only **your own** messages feed your mood metrics; others' messages are kept separately.

*Evaluation* (`ml/reports/sentiment_report.md`): **accuracy 79.2%, macro-F1 0.79** on 19,532 demo messages
(always-neutral baseline: 47.0% / 0.21). On your own 8,025 messages: 78.9% / 0.79. Typical errors: VADER
reads "ok" and "free" as positive, Hindi *baad* ("later") is a false friend, "dead 💀" (= very funny) reads
negative, slang like "let's gooo" matches nothing. Optimistic: the demo uses a few hundred fixed phrases,
written by the same person who wrote the lexicon (the lexicon was not tuned on this evaluation).

## 2. Daily features

`daily_features` (SQL view) = `daily_activity` + topic minutes (study / comedy / music), sad and romantic
song share, your message mood and negative share, the mood of messages you receive, discretionary spend
(debits except transfers to people, ATM cash, subscriptions) and entertainment + shopping spend.
**NULL vs 0:** a source's columns are NULL outside its date range (no data ≠ "did nothing"), 0 for counts on
covered days without events, NULL for shares/means when there is nothing to average.

## 3. Cross-app correlations (`analysis/correlations.py`)

For every pair of daily metrics **from different apps**, inside the window where **all** apps have data
(∩ the date range you picked):

- **Spearman rank correlation**, at lag 0, 1 and 2 days ("YouTube today vs spending tomorrow"), both directions.
  - *Why Spearman, not Pearson?* Daily data is skewed (most days ₹0 food delivery, a few ₹400 days) and has
    outliers. Spearman uses ranks, so one extreme day can't create or hide a link, and it catches any
    "more X goes with more Y" pattern, not only straight lines.
- At least **30 days** with both values, otherwise the test is skipped.
- **Benjamini–Hochberg correction** at a false discovery rate of 5% over all tests (1,170 on the demo).
  - *Why?* Testing a thousand pairs at p < 0.05 would produce ~58 "findings" by pure chance. BH adjusts
    every p-value (→ *q*) so that, among the findings we report, at most about 5% are expected to be flukes.
    It is less strict than Bonferroni (which would hide real but modest effects).
- **Reported insights:** q < 0.05 **and** |rho| ≥ 0.2, and for each pair only its strongest lag.
- **Weaker signals:** q < 0.05 but 0.1 ≤ |rho| < 0.2, shown separately and labelled "may be chance".
  Kept because a correlation coefficient understates links with **rare events**: food delivery happens on
  13% of days, the 87% tied zeros cap rho, yet "3.2x as likely" is a large effect.
- Each finding becomes a sentence with the numbers behind it: a round threshold near the 70th percentile
  splits days into "high X" and "low X" and compares Y — how often it happens (rate ratio) or its average.
  Strength: |rho| < 0.3 weak, < 0.5 moderate, ≥ 0.5 strong.
- **Association, not causation.** "On days with lots of YouTube you order food more often" does not mean
  YouTube makes you order food. Both can be driven by a third thing — in the demo, **exams** push up YouTube,
  late nights, sad songs, negative messages *and* food delivery together. Every insight is phrased as
  "on days with…, … is higher" and carries that note.

## 4. Periods (`analysis/periods.py`)

You tag date ranges ("Exams", "Trip"); weekends are compared automatically. For every metric, days inside
vs outside are compared with the **Mann–Whitney U test** (ranks again: no normality assumption), with
**BH correction** over all metric × period tests, and reported as % change of the daily average plus the
rank-biserial effect size. The DEMO database comes with its 3 exam periods pre-tagged.

## 5. Unusual days (`analysis/anomalies.py`)

- **Robust z-score per metric:** z = 0.6745 × (x − median) / MAD, flag |z| > 3.5 (Iglewicz & Hoaglin).
  *Why not the usual mean/std z?* A few extreme days inflate the std and hide themselves; the median and the
  median absolute deviation (MAD) are not moved by the outliers.
- **IsolationForest** on the standardised daily feature vector (2% contamination) finds days that are odd as
  a *combination* (e.g. lots of study videos + negative messages + late-night music), even if no single
  number is extreme.
- Each flagged day is explained by its 2–3 most extreme metrics: "18 Dec 2025: ₹1,554 discretionary spend,
  ₹1,764 total spend and ₹1,199 entertainment & shopping spend, all far above your usual."

## 6. Validation on the demo year (the planted patterns)

The demo generator planted patterns on purpose; the engine must find them without being told.

| Planted pattern | Result |
|---|---|
| a) YouTube time ↔ food delivery | **Found, as a weaker signal**: "On days with 24+ YouTube videos, you're 3.2x as likely to order food delivery (24% vs 8% of days)" — rho +0.19, q = 0.003. Significant after BH but just under the 0.2 bar, because delivery is a rare event (49 of 365 days). |
| b) Exams: study videos ↑ | **Found**: +166% (70 vs 26 min a day), q < 0.001 |
| b) Exams: late-night activity ↑ | **Found** for WhatsApp (+23 points, 30% vs 8%) and Spotify (+9 points); YouTube only +4 points, **not significant** (the planted YouTube effect is small) |
| b) Exams: sad-song share ↑ | **Found**: 51% vs 25%, q < 0.001 |
| b) Exams: negative messages ↑ | **Found**: 34% vs 12% of your messages, q < 0.001 |
| c) Weekends: comedy ↑ | **Found**: +71% (62 vs 36 min a day) |
| c) Weekends: entertainment/shopping spend ↑ | **Found**: +105% (₹120 vs ₹59 a day) |
| d) Late night ↔ sad songs | **Found**: songs played 11pm–3am are sad 48% of the time vs 22% at other hours (2.2x, chi-square p < 10⁻¹³⁰) |

**Null test** (does it invent things?). Shuffle the dates of one app's data — this breaks every real link
between that app and the others but keeps its values — and re-run. Anything involving that app that still
"survives" is a false positive. 40 runs (4 apps × 10 shuffles): **0 false insights** in the reported tier;
**1.5 false weaker signals per run** on average (34 of the 60 came from shuffling bank, whose spend metrics
move together, so one chance link shows up several times). This is why the reported insights use the 0.2
bar and why weaker signals are labelled "may be chance".

## 7. Limits

- **Synthetic data.** The patterns found are the patterns planted; real life is noisier.
- **Confounding.** Most cross-app links in the demo come from the exam calendar. Tag your exams/trips and
  compare periods to see the common cause directly.
- **Time-series dependence.** Neighbouring days are similar, which makes p-values a bit optimistic; the null
  test (which keeps each app's own day-to-day pattern) is the practical check.
- **Enrichment quality caps everything:** unknown songs and channels, lexicon-based sentiment (~79% on the
  demo, likely lower on real chats), and the spend categories from step 6.
- **Bank rows have no time of day**, so late-night analysis uses Spotify, YouTube and WhatsApp only.
- Daily granularity: effects within a day ("after a late-night chat you open YouTube") are not tested.

Re-run everything: `python ml/scripts/eval_sentiment.py && python ml/scripts/validate_analysis.py`;
tests: `cd web/src/python && ../../../.venv/bin/python -m pytest tests/test_analysis.py`.
