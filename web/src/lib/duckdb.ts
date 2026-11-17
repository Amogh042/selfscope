// DuckDB-WASM: in-browser SQL engine.
// The .wasm binaries and DuckDB's own worker are bundled by Vite from node_modules
// (self-hosted, no CDN), and DuckDB runs in that worker off the main thread.

import * as duckdb from '@duckdb/duckdb-wasm'
import mvpWasm from '@duckdb/duckdb-wasm/dist/duckdb-mvp.wasm?url'
import mvpWorker from '@duckdb/duckdb-wasm/dist/duckdb-browser-mvp.worker.js?url'
import ehWasm from '@duckdb/duckdb-wasm/dist/duckdb-eh.wasm?url'
import ehWorker from '@duckdb/duckdb-wasm/dist/duckdb-browser-eh.worker.js?url'

const BUNDLES: duckdb.DuckDBBundles = {
  mvp: { mainModule: mvpWasm, mainWorker: mvpWorker },
  eh: { mainModule: ehWasm, mainWorker: ehWorker },
}

let dbPromise: Promise<duckdb.AsyncDuckDB> | null = null

/** Initialise DuckDB once (picks the best bundle for this browser). */
export function initDuckDB(): Promise<duckdb.AsyncDuckDB> {
  dbPromise ??= (async () => {
    const bundle = await duckdb.selectBundle(BUNDLES)
    const worker = new Worker(bundle.mainWorker!)
    const db = new duckdb.AsyncDuckDB(new duckdb.ConsoleLogger(duckdb.LogLevel.WARNING), worker)
    await db.instantiate(bundle.mainModule, bundle.pthreadWorker)
    return db
  })().catch((err) => {
    dbPromise = null // allow retry
    throw err
  })
  return dbPromise
}

/** DuckDB library version string, e.g. "v1.4.1". */
export async function duckdbVersion(): Promise<string> {
  const db = await initDuckDB()
  return db.getVersion()
}

/** Arrow values -> plain JS. BIGINTs become numbers when they fit safely. */
function normalise(v: unknown): unknown {
  if (typeof v === 'bigint') {
    return v <= BigInt(Number.MAX_SAFE_INTEGER) && v >= BigInt(Number.MIN_SAFE_INTEGER) ? Number(v) : v.toString()
  }
  return v
}

/** Run a SQL query and return rows as plain objects. */
export async function query<T = Record<string, unknown>>(sql: string): Promise<T[]> {
  const db = await initDuckDB()
  const conn = await db.connect()
  try {
    const table = await conn.query(sql)
    return table.toArray().map((row) => {
      const obj = row.toJSON() as Record<string, unknown>
      for (const k of Object.keys(obj)) obj[k] = normalise(obj[k])
      return obj as T
    })
  } finally {
    await conn.close()
  }
}
