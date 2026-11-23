// Persistent local storage for parsed events (DuckDB-WASM + IndexedDB snapshots).
//
// Why snapshots: the installed duckdb-wasm (1.33.1-dev57.0) opens `opfs://` databases but
// does not persist writes in this browser (files stay 0 bytes; verified in step 4). So DuckDB
// runs in memory and, after every change, the tables are saved as Parquet snapshots in
// IndexedDB — one snapshot per mode ("selfscope_demo" / "selfscope_real"), restored on load.
// Demo and real data never share tables: switching mode drops everything and restores the
// other snapshot.
//
// All SQL lives in src/sql/*.sql (tested with the duckdb Python package).

import type { AsyncDuckDBConnection } from '@duckdb/duckdb-wasm'
import { initDuckDB } from './duckdb'
import { idbDelete, idbGet, idbPut } from './idb'
import categoriseSql from '../sql/categorise.sql?raw'
import importSql from '../sql/import.sql?raw'
import manageSql from '../sql/manage.sql?raw'
import queriesSql from '../sql/queries.sql?raw'
import schemaSql from '../sql/schema.sql?raw'
import stageCsvSql from '../sql/stage_csv.sql?raw'
import stageParquetSql from '../sql/stage_parquet.sql?raw'
import viewsSql from '../sql/views.sql?raw'

export type Mode = 'demo' | 'real'
export const DB_NAME: Record<Mode, string> = { demo: 'selfscope_demo', real: 'selfscope_real' }

const SNAPSHOT_TABLES = ['events', 'imports', 'settings', 'category_overrides'] as const
const SNAPSHOT_VERSION = 1

interface Snapshot {
  version: number
  savedAt: string
  /** Tables added in later versions (e.g. category_overrides) may be missing from old snapshots. */
  tables: Partial<Record<(typeof SNAPSHOT_TABLES)[number], Uint8Array>>
}

export interface StoreState {
  mode: Mode | null
  status: 'idle' | 'opening' | 'ready' | 'error'
  error?: string
  /** Increments after every change to the data, so views can refetch. */
  version: number
}

export interface ImportResult {
  import_id: string
  rows_added: number
  rows_skipped: number
  min_date: string | null
  max_date: string | null
  /** Timings in ms. */
  dbMs: number
  saveMs: number
}

/** Split "-- name: x" blocks into {x: sql}. */
function namedBlocks(text: string): Record<string, string> {
  const parts = text.split(/^-- name: (\w+)\s*$/m)
  const out: Record<string, string> = {}
  for (let i = 1; i < parts.length; i += 2) out[parts[i]] = parts[i + 1].trim()
  return out
}

export const QUERIES = namedBlocks(queriesSql)
const MANAGE = namedBlocks(manageSql)
const CATEGORISE = namedBlocks(categoriseSql)

function literal(v: string | number | null | undefined): string {
  if (v === null || v === undefined) return 'NULL'
  return `'${String(v).replace(/'/g, "''")}'`
}

function setVars(vars: Record<string, string | number | null | undefined>): string {
  return Object.entries(vars)
    .map(([k, v]) => `SET VARIABLE ${k} = ${literal(v)};`)
    .join('\n')
}

interface ArrowLike {
  schema: { fields: { name: string; type: { typeId: number; scale?: number } }[] }
  toArray(): { toJSON(): Record<string, unknown> }[]
}
const ARROW_DECIMAL = 7

/**
 * Arrow rows -> plain objects. BIGINT -> number when safe. DECIMAL (incl. HUGEINT, which
 * is what sum() of integers returns) arrives as an unscaled big number: apply the scale.
 */
function rows<T>(table: ArrowLike): T[] {
  const scale = new Map(
    table.schema.fields.filter((f) => f.type.typeId === ARROW_DECIMAL).map((f) => [f.name, f.type.scale ?? 0]),
  )
  return table.toArray().map((r) => {
    const o = r.toJSON()
    for (const k of Object.keys(o)) {
      const v = o[k]
      if (v === null || v === undefined) continue
      if (scale.has(k)) o[k] = Number(String(v)) / 10 ** scale.get(k)!
      else if (typeof v === 'bigint') o[k] = Number.isSafeInteger(Number(v)) ? Number(v) : v.toString()
    }
    return o as T
  })
}

class Store {
  private chain: Promise<unknown> = Promise.resolve()
  private listeners = new Set<() => void>()
  private state: StoreState = { mode: null, status: 'idle', version: 0 }

  getState = (): StoreState => this.state
  subscribe = (fn: () => void): (() => void) => {
    this.listeners.add(fn)
    return () => this.listeners.delete(fn)
  }
  private set(patch: Partial<StoreState>) {
    this.state = { ...this.state, ...patch }
    for (const l of this.listeners) l()
  }

  /** Run `fn` with exclusive access (operations never interleave, e.g. a mode switch mid-import). */
  private exclusive<T>(fn: (c: AsyncDuckDBConnection) => Promise<T>): Promise<T> {
    const run = this.chain.then(async () => {
      const db = await initDuckDB()
      const c = await db.connect()
      try {
        return await fn(c)
      } finally {
        await c.close()
      }
    })
    this.chain = run.catch(() => {})
    return run
  }

  /** Open (or switch to) the database for `mode`: reset memory, create schema, restore snapshot. */
  setMode(mode: Mode): Promise<void> {
    if (this.state.mode === mode && this.state.status === 'ready') return Promise.resolve()
    this.set({ mode, status: 'opening', error: undefined })
    return this.exclusive(async (c) => {
      const db = await initDuckDB()
      await c.query(MANAGE.reset)
      await c.query(schemaSql)
      const snap = await idbGet<Snapshot>(DB_NAME[mode])
      if (snap && snap.version === SNAPSHOT_VERSION) {
        for (const t of SNAPSHOT_TABLES) {
          if (!snap.tables[t]) continue
          // Unique names: DuckDB-WASM caches file metadata by name, so reusing a name for a
          // different buffer (e.g. demo after real) fails with a Snappy size mismatch.
          const name = `restore_${t}_${crypto.randomUUID()}.parquet`
          await db.registerFileBuffer(name, snap.tables[t]!)
          await c.query(`INSERT INTO ${t} BY NAME SELECT * FROM read_parquet('${name}')`)
          await db.dropFile(name)
        }
      }
      await c.query(viewsSql)
    }).then(
      () => this.set({ status: 'ready', version: this.state.version + 1 }),
      (err) => {
        this.set({ status: 'error', error: err instanceof Error ? err.message : String(err) })
        throw err
      },
    )
  }

  /** Save the current tables as a Parquet snapshot in IndexedDB. */
  private async persist(c: AsyncDuckDBConnection) {
    const mode = this.state.mode
    if (!mode) throw new Error('no database open')
    const db = await initDuckDB()
    const tables = {} as Snapshot['tables']
    for (const t of SNAPSHOT_TABLES) {
      const name = `snap_${t}_${crypto.randomUUID()}.parquet` // unique: see setMode()
      await c.query(`COPY ${t} TO '${name}' (FORMAT parquet)`)
      tables[t] = await db.copyFileToBuffer(name)
      await db.dropFile(name)
    }
    await idbPut(DB_NAME[mode], { version: SNAPSHOT_VERSION, savedAt: new Date().toISOString(), tables } satisfies Snapshot)
  }

  private async ready(mode?: Mode) {
    if (mode && this.state.mode !== mode) await this.setMode(mode)
    if (this.state.status !== 'ready') {
      if (!this.state.mode) throw new Error('no database open')
      await this.setMode(this.state.mode)
    }
  }

  /** Run a named read query from src/sql/queries.sql (or raw SQL). */
  async query<T = Record<string, unknown>>(nameOrSql: string, vars: Record<string, string | null> = {}): Promise<T[]> {
    await this.ready()
    const sql = QUERIES[nameOrSql] ?? nameOrSql
    return this.exclusive(async (c) => {
      if (Object.keys(vars).length) await c.query(setVars(vars))
      return rows<T>(await c.query(sql))
    })
  }

  /** Merge one staged file into the current mode's database (src/sql/import.sql) and save. */
  async importStaged(
    mode: Mode,
    stage: { format: 'parquet' | 'csv'; data: Uint8Array | string },
    meta: { source: string; fileName: string; fileHash: string | null },
  ): Promise<ImportResult> {
    await this.ready(mode)
    if (this.state.mode !== mode) throw new Error(`database switched away from ${mode}`)
    const importId = crypto.randomUUID()
    const result = await this.exclusive(async (c) => {
      const db = await initDuckDB()
      const t0 = performance.now()
      const file = `stage_${importId}.${stage.format}`
      if (stage.format === 'parquet') await db.registerFileBuffer(file, stage.data as Uint8Array)
      else await db.registerFileText(file, stage.data as string)
      try {
        await c.query(
          setVars({
            stage_file: file,
            import_id: importId,
            source: meta.source,
            file_name: meta.fileName,
            file_hash: meta.fileHash,
            imported_at: new Date().toISOString().replace('T', ' ').replace('Z', ''),
          }),
        )
        await c.query(stage.format === 'parquet' ? stageParquetSql : stageCsvSql)
        await c.query(importSql)
      } finally {
        await db.dropFile(file)
      }
      const [row] = rows<Omit<ImportResult, 'dbMs' | 'saveMs'>>(
        await c.query(
          `SELECT import_id, rows_added, rows_skipped, CAST(min_date AS VARCHAR) min_date, CAST(max_date AS VARCHAR) max_date
           FROM imports WHERE import_id = ${literal(importId)}`,
        ),
      )
      const t1 = performance.now()
      await this.persist(c)
      return { ...row, dbMs: Math.round(t1 - t0), saveMs: Math.round(performance.now() - t1) }
    })
    this.set({ version: this.state.version + 1 })
    return result
  }

  private async mutate(block: string, vars: Record<string, string | null> = {}) {
    await this.runBlocks([MANAGE[block]], vars)
  }

  private async runBlocks(sqls: string[], vars: Record<string, string | null> = {}) {
    await this.ready()
    await this.exclusive(async (c) => {
      if (Object.keys(vars).length) await c.query(setVars(vars))
      for (const sql of sqls) await c.query(sql)
      await this.persist(c)
    })
    this.set({ version: this.state.version + 1 })
  }

  /** Store categoriser output (src/sql/categorise.sql) and recompute final categories. */
  async applyPredictions(mode: Mode, predictionsJson: string, modelVersion: string, modelF1: string) {
    await this.ready(mode)
    if (this.state.mode !== mode) throw new Error(`database switched away from ${mode}`)
    const db = await initDuckDB()
    const file = `pred_${crypto.randomUUID()}.json`
    await db.registerFileText(file, predictionsJson)
    try {
      await this.runBlocks([CATEGORISE.apply_predictions, CATEGORISE.refresh_categories], {
        pred_file: file,
        model_version: modelVersion,
        model_f1: modelF1,
      })
    } finally {
      await db.dropFile(file)
    }
  }

  /** User correction: one transaction ('event', event_key) or all debits to a payee ('payee', payee_key). */
  setOverride = (scope: 'event' | 'payee', target: string, category: string) =>
    this.runBlocks([CATEGORISE.set_override, CATEGORISE.refresh_categories], {
      scope,
      target,
      category,
      created_at: new Date().toISOString().replace('T', ' ').replace('Z', ''),
    })

  /** Remove a correction: back to the payee correction / the model. */
  clearOverride = (scope: 'event' | 'payee', target: string) =>
    this.runBlocks([CATEGORISE.clear_override, CATEGORISE.refresh_categories], { scope, target })

  removeImport = (importId: string) => this.mutate('remove_import', { import_id: importId })
  setMe = (name: string) => this.mutate('set_me', { me: name })

  /** Delete every event, import and setting of the current mode (and its saved snapshot). */
  async wipe() {
    await this.mutate('wipe_all')
    if (this.state.mode) await idbDelete(DB_NAME[this.state.mode])
  }
}

export const store = new Store()
