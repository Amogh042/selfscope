# Privacy audit

**Claim:** your data never leaves the browser. Files are read, parsed, stored and analysed inside the tab; the
only network traffic is downloading code. This page shows how that was checked, what is stored where, and how to
delete it.

## 1. How it was tested (23 Nov 2026)

- **Build:** the production build (`npm run build`) served by `vite preview` on `http://localhost:4173`, with the
  same headers as the Vercel deploy (`web/vercel.json`).
- **Browser:** Google Chrome, headless, with a **fresh profile** (no cache, no cookies, no extensions), driven by a
  script.
- **Recording:** Chrome's own **NetLog** (`--log-net-log`). It records every request made by the browser: the page,
  the Python worker, the DuckDB worker, and Chrome's own background services. This is more than DevTools shows,
  because DevTools hides requests made inside workers.
- **Flow:** landing screen → export guide → **TRY THE DEMO** (imports 9 demo files, categorises, enriches, analyses
  the full year) → dashboard → day drill-down → calendar-control toggle → **import a test file into MY DATA** (a
  synthetic WhatsApp chat, 6,517 events) → MY DATA dashboard → **wipe MY DATA** → landing at phone width.
- **Result:** every step worked, with 0 console errors.

## 2. Every request

### Made by SelfScope (page and workers)

| Host | Requests | Methods | Request bodies | What |
|---|---|---|---|---|
| `localhost:4173` = the site itself (on Vercel: your deploy's domain) | 70 | GET only | none | the app (HTML, JS, CSS, bundled fonts), the DuckDB engine (`duckdb-eh.wasm`) and its `json` + `parquet` extensions (`/duckdb-ext/`), curated lists (`/data/*.json`), the categoriser model (`/models/categoriser.json`), and the **synthetic** demo files (`/demo/…`, only on TRY THE DEMO) |
| `cdn.jsdelivr.net` | 36 | GET only | none | the Python runtime: `pyodide.mjs`, `pyodide.asm.wasm`, `python_stdlib.zip`, `pyodide-lock.json`, and package wheels (numpy, pandas, scipy, scikit-learn, pyarrow, joblib, threadpoolctl, python-dateutil, pytz, six, tzdata, pyodide_unix_timezones). The file names are fixed, with no query strings. |

**Nothing else.** In particular:
- Importing the test file caused **no request at all**. The file is read by the browser from disk (`File` API) and
  passed to the worker in memory.
- No requests to fonts.googleapis.com / fonts.gstatic.com: the fonts are bundled since this audit.
- No requests to `extensions.duckdb.org`. See "found and fixed" below.
- No analytics, telemetry, error reporting, cookies or third-party scripts.

### Not made by SelfScope

| Host | Why it appears | Contains app data? |
|---|---|---|
| `a.nel.cloudflare.com` (2 POST + 2 preflight) | **Network Error Logging.** jsDelivr is served by Cloudflare, whose responses carry `NEL` / `Report-To` headers. Because of those headers, the *browser* reports failed fetches and 1% of successful fetches *from jsDelivr* to Cloudflare. | No. A report describes the jsDelivr fetch itself (its URL, status, timing, server IP). The app has no control over it, and the CSP doesn't apply to it. |
| `update.googleapis.com`, `edgedl.me.gvt1.com`, `clients2.google.com`, `accounts.google.com`, `content-autofill.googleapis.com`, `www.google.com`, `www.gstatic.com` | Chrome's own background services (component updates, sign-in check, autofill), started by the fresh profile. NetLog marks them as browser-initiated (no page origin). | No. They happen with any website, or none. |

### Found and fixed during the audit

1. **DuckDB-WASM downloaded extensions from `extensions.duckdb.org`.** It does this silently whenever SQL first
   needs `json` (our `json_extract_string`) or `parquet` (import staging and the saved snapshots). These downloads
   carried no user data (fixed file names), but they meant a third host the app didn't control. The same official,
   signed binaries are now served from the site (`web/public/duckdb-ext/`, SHA-256 checksums listed there), and
   `src/lib/duckdb.ts` points DuckDB at them.
2. **Google Fonts.** The fonts now ship with the app (`@fontsource` packages), so loading the page no longer tells
   Google which page you opened.

## 3. Enforced by the browser: Content-Security-Policy

```
default-src 'self'; script-src 'self' 'wasm-unsafe-eval' https://cdn.jsdelivr.net; worker-src 'self' blob:;
connect-src 'self' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline'; font-src 'self' data:;
img-src 'self' data: blob:; object-src 'none'; base-uri 'self'; form-action 'none'; frame-ancestors 'none'
```

`connect-src` and `script-src` mean the page and its workers **cannot** send a request to any other host, even if
some code (ours or a library's) tried. The browser blocks it and logs an error. This is how the DuckDB extension
downloads were caught.

- **Vercel:** sent as a real header on every file, so it also covers the workers. Other headers sent:
  `Referrer-Policy: no-referrer`, `X-Content-Type-Options: nosniff`, and a `Permissions-Policy` that turns off
  camera, microphone, location, payment and USB.
- **GitHub Pages:** can't set headers, so the build includes the same policy as a `<meta>` tag (minus
  `frame-ancestors`, which only works as a header). That covers the page but not the workers.

## 4. What is stored where

All of it lives in **this browser, for this site only**. Other sites can't read it, and it is not synced anywhere.

| What | Where | Contents |
|---|---|---|
| Your events (messages incl. text, plays, videos, transactions), imports, tagged periods, category corrections, "which one is you", cached analysis results | **IndexedDB** database `selfscope`, store `snapshots`, key `selfscope_real` (MY DATA) / `selfscope_demo` (DEMO) | a Parquet snapshot of each DuckDB table, rewritten after every change. While the tab is open, the same data is also in DuckDB's memory (in its worker). |
| Which database you last used | **localStorage** `selfscope.mode` | `demo` or `real` |
| Downloaded code (Python runtime, app files) | the browser's HTTP cache | code only, no data |

**Not stored:** the original files you dropped (only the parsed events), bank statement header blocks (never read
into the database), full account or card numbers (9+ digit numbers are masked, except the 12-digit UPI reference
used to avoid double counting).

WhatsApp message **text is stored** locally: sentiment needs it, and re-imports use it to recognise duplicates.
The dashboard never displays it (counts and mood only).

## 5. How to wipe everything

1. **In the app:** DATA → **✖ WIPE ALL DATA** → CONFIRM. This deletes every event, import and setting of the current
   database (MY DATA or DEMO) from memory and from IndexedDB. Switch to the other database and repeat to wipe both.
   (Checked in the audit: after wiping MY DATA, its snapshot key was gone and the landing screen came back.)
2. **Everything, including the mode setting and cached code:** browser settings → site data for this site → delete
   (Chrome: the lock icon in the address bar → Site settings → Delete data). Or use a private window, which
   forgets everything when closed.

## 6. What could be improved

- **Self-host Pyodide** (runtime + the ~15 wheels used, roughly 30–40 MB). Then the only host would be the site
  itself, there'd be no Cloudflare NEL reports, and the CSP could drop jsDelivr. The cost is a bigger deploy and
  updating the files when Pyodide is upgraded.
- **Subresource Integrity** for the Pyodide files (pin hashes) so a compromised CDN couldn't serve other code; today
  the version is pinned but the content is trusted.
- **Encrypt the snapshot at rest** with a passphrase (WebCrypto) for shared computers.
- **An "I'm on a shared computer" mode** that keeps data in memory only and never writes IndexedDB.
- **Headers on GitHub Pages** need a proxy in front (e.g. Cloudflare); otherwise prefer Vercel for the full CSP.
- **Re-run this audit** after any dependency upgrade: `npm run build && npm run preview`, then repeat the flow in a
  fresh profile and check the console for CSP errors.
