// Runs the spend categoriser (src/python/categoriser.py) in the Python worker over ALL
// stored bank rows of the current database and writes the result into DuckDB
// (src/sql/categorise.sql). Payee behaviour needs the whole history, so it is never
// run on one file alone. User overrides live in their own table and always win.
//
// Triggered automatically (see appState.tsx) whenever the open database has bank rows
// that were not categorised by the current model version: after a bank import, once for
// rows stored before this feature existed, and after a model update.

import { pythonEngine } from './pythonEngine'
import { ensurePythonModules } from './pythonModules'
import { store, type Mode } from './store'

const MODEL_URL = `${import.meta.env.BASE_URL}models/categoriser.json`

export interface CategoriseState {
  running: boolean
  error: string | null
  lastRun: { rows: number; ms: number } | null
}

let state: CategoriseState = { running: false, error: null, lastRun: null }
const listeners = new Set<() => void>()
const set = (patch: Partial<CategoriseState>) => {
  state = { ...state, ...patch }
  for (const l of listeners) l()
}
export const categoriseState = {
  get: () => state,
  subscribe: (fn: () => void) => {
    listeners.add(fn)
    return () => listeners.delete(fn)
  },
}

let model: Promise<{ text: string; version: string }> | null = null
function loadModel() {
  model ??= fetch(MODEL_URL)
    .then((r) => {
      if (!r.ok) throw new Error(`categoriser model not found (${MODEL_URL})`)
      return r.text()
    })
    .then((text) => ({ text, version: String((JSON.parse(text) as { version: string }).version) }))
    .catch((e) => {
      model = null
      throw e
    })
  return model
}

const CODE = `import categoriser
if categoriser._MODEL is None or categoriser._MODEL.version != model_version:
    categoriser.load_model(model_json)
categoriser.categorise_events_json(events_json)`

interface ModelRow {
  event_key: string
  local_date: string
  weekday: number
  value: number
  meta: string
}

/** Categorise every stored bank row of `mode`'s database. */
export async function categoriseBank(mode: Mode): Promise<void> {
  const t0 = performance.now()
  const rows = await store.query<ModelRow>('bank_rows_for_model')
  if (!rows.length) return
  const { text, version } = await loadModel()
  await ensurePythonModules()
  const { result } = await pythonEngine.runPython(CODE, {
    events_json: JSON.stringify(rows),
    model_json: text,
    model_version: version,
  })
  const out = JSON.parse(result as string) as {
    model: { version: string; test_macro_f1: number }
    predictions: unknown[]
  }
  await store.applyPredictions(mode, JSON.stringify(out.predictions), out.model.version, String(out.model.test_macro_f1))
  set({ lastRun: { rows: rows.length, ms: Math.round(performance.now() - t0) } })
}

let inFlight: Promise<void> | null = null

/** Categorise if any bank row lacks a prediction from the current model version. */
export function ensureCategorised(mode: Mode): Promise<void> {
  inFlight ??= (async () => {
    try {
      const { version } = await loadModel()
      const [{ n }] = await store.query<{ n: number }>('bank_uncategorised', { model_version: version })
      if (!n) return
      set({ running: true, error: null })
      await categoriseBank(mode)
    } catch (e) {
      set({ error: e instanceof Error ? e.message.trim().split('\n').slice(-1)[0] : String(e) })
    } finally {
      set({ running: false })
      inFlight = null
    }
  })()
  return inFlight
}
