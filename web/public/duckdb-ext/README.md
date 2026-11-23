# Self-hosted DuckDB extensions

DuckDB-WASM loads two extensions on demand: `json` (our SQL uses `json_extract_string`, …) and
`parquet` (import staging and the IndexedDB snapshots).
By default it downloads it from `extensions.duckdb.org`; we serve the same official, signed
binaries from this folder instead, so the app never contacts DuckDB's servers
(`src/lib/duckdb.ts` sets `custom_extension_repository`; the CSP blocks any other host).

Downloaded unchanged from `https://extensions.duckdb.org/v1.5.4/<platform>/<name>.duckdb_extension.wasm`
(DuckDB v1.5.4 = `@duckdb/duckdb-wasm` 1.33.1-dev57.0). Update both when the DuckDB-WASM version changes.

| File | SHA-256 |
|---|---|
| `v1.5.4/wasm_eh/json.duckdb_extension.wasm` | `993b19f7929cc305b2529c548f2842e8e7a5b112d1c88f31c84798b51901ca16` |
| `v1.5.4/wasm_mvp/json.duckdb_extension.wasm` | `15a89d3fd0fa3449c0d8981e6cb1ca6be8df4bcaf0dfdd6660c17bcc3bdf0af8` |
| `v1.5.4/wasm_eh/parquet.duckdb_extension.wasm` | `4845705bbd69fc9ad52878d96a505c73cae4a6c509822079cc2413e5eb437f95` |
| `v1.5.4/wasm_mvp/parquet.duckdb_extension.wasm` | `b64c255a7f7d06cc234535b2f0ecab345fda91bffff5509d3179004bc13aa19a` |

If DuckDB needs another extension, the CSP blocks the download and the console shows
"Extension … could not be loaded"; add it here the same way.
