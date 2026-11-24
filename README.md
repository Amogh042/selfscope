# SelfScope

**Live: https://selfscope-psi.vercel.app** (try the demo; it runs entirely in your browser)

**A privacy-first personal data dashboard.** Drop in your own exports — UPI/SBI bank statements,
WhatsApp chats, Spotify listening history, YouTube watch history (Google Takeout) — and get one
interactive dashboard with insights *across* apps: "on days with 24+ YouTube videos you're 3.2x as likely
to order food delivery", "sad songs peak around 2 am", "during exams your negative messages triple".

**Everything runs in your browser. Your data never leaves your device**: no server, no uploads, no
analytics. Apart from the site itself, the only network requests download the Python runtime from the jsDelivr CDN,
and a Content-Security-Policy makes the browser block every other destination. See the privacy audit in
[`docs/privacy.md`](docs/privacy.md).

![Dashboard](docs/screenshots/dashboard-full.png)

*(Data Science & Visualisation course project. All screenshots use the synthetic demo data.)*

## Architecture

```
your export files ──► Import screen (detects the source, unzips)
                        │
                        ▼
   Pyodide (Python in a Web Worker): parsers → one shared event table
                        │                     (docs/schema.md)
                        ▼
   DuckDB-WASM (SQL in the browser): events + views, saved as Parquet in IndexedDB
                        │
        ┌───────────────┼──────────────────────────────┐
        ▼               ▼                              ▼
  spend categoriser   enrichment                 analysis engine
  (ML model trained   (video topics, song moods,  (Spearman + FDR, calendar control,
   offline, run in     message sentiment)          periods, anomalies)
   the browser)                                     │
                                                    ▼
                         Dashboard (React + Apache ECharts)
```

- `web/` — Vite + React + TypeScript + Tailwind. Python modules in `web/src/python/`, all SQL in `web/src/sql/`.
- `ml/` — offline training and evaluation (spend categoriser, sentiment evaluation, analysis validation).
- `data/samples/` — a synthetic demo year in the real export formats; `data/private/` — your real exports
  (git-ignored, never committed).
- `docs/` — design system (`design.md`), event schema (`schema.md`), analysis methods (`analysis.md`),
  privacy audit (`privacy.md`), viva notes (`viva.md`), planned vs used stack (`tech-stack-final.md`),
  known gaps (`backlog.md`).

## Run it

Needs Node 22 (LTS) or newer.

```bash
cd web
npm install
npm run dev
```

Open http://localhost:5173. Production build: `npm run build` (output in `web/dist/`, a static site);
check it with `npm run preview` (http://localhost:4173, served with the same security headers as on Vercel).

### Load the demo

1. On the landing screen click **★ TRY THE DEMO** (or **IMPORT** → **★ LOAD DEMO DATA**). This switches to the
   separate **DEMO** database and imports one synthetic year (Spotify, YouTube, 5 WhatsApp chats, an SBI statement),
   tags the three exam periods and two semester breaks, and picks the demo user's chat name.
2. The Python runtime starts downloading as soon as the landing screen opens (tens of MB from the jsDelivr CDN,
   cached afterwards). The first analysis shows its steps (Loading Python → Reading data → Finding patterns) and
   takes ~15–30 s; after that results are cached.
3. On the **DASHBOARD**, use the date-range picker (or drag the timeline slider), click any day for the
   drill-down, click an insight card for its scatter plot, and try **Control for weekday + tagged periods**.

Your own files go in **MY DATA**, a separate database that never mixes with the demo. **How to export your data**
(WhatsApp, Spotify, Google Takeout, SBI) is linked from the landing and import screens (`#/guide`).

### Deploy (static site)

The build is a plain static folder with a relative base path and hash routing, so it works at a domain root and
under a sub-path. No cross-origin isolation headers are needed (DuckDB-WASM runs single-threaded; Pyodide doesn't
use SharedArrayBuffer).

- **Vercel** (live at https://selfscope-psi.vercel.app): the project's *Root Directory* is `web`, with source files
  outside it included (the build copies `data/samples/` and `ml/selfscope_ml/`). `web/vercel.json` sets the build
  and the security headers (CSP, no referrer, …). It is deployed from the CLI, uploading only committed files
  (never `data/private/` or other ignored files). To redeploy, run this from the repo root after `vercel login`:

  ```bash
  D=$(mktemp -d) && git archive HEAD web data/samples ml/selfscope_ml | tar -x -C "$D" && mkdir "$D/.vercel" && cp .vercel/project.json "$D/.vercel/" && (cd "$D" && vercel deploy --prod)
  ```

  (`.vercel/project.json` is created by `vercel link --project selfscope`; it is git-ignored.)
- **GitHub Pages:** Settings → Pages → Source: *GitHub Actions*, then run the *Deploy to GitHub Pages* workflow
  (`.github/workflows/pages.yml`, manual). Pages can't set headers, so the CSP comes from a `<meta>` tag in the
  built `index.html` (covers the page, not the workers; see `docs/privacy.md`).

## Tests and reports

```bash
cd web/src/python && ../../../.venv/bin/python -m pytest   # parsers, SQL, enrichment, analysis, dashboard SQL
cd ml && ../.venv/bin/python -m pytest                     # ML pipeline
```

(Python setup: `web/src/python/README.md`.)

| Report | What |
|---|---|
| `docs/viva.md` | 1-minute pitch, architecture diagram, methods, key numbers, limitations, likely questions |
| `docs/analysis.md` | how the insights are computed, why, validation on the demo, limits |
| `docs/privacy.md` | network audit (every request the app makes), what is stored where, how to wipe it |
| `docs/tech-stack-final.md` | what the proposal planned vs what was used, and why |
| `ml/reports/` | spend categoriser evaluation, sentiment accuracy (`sentiment_report.md`), analysis validation (`analysis_validation.json`) |
| `ml/notebooks/01_spend_categoriser.ipynb` | categoriser training walkthrough |
| `docs/screenshots/` | dashboard screenshots (demo data) |
