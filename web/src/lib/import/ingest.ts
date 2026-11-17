// One file -> Python parser (worker) -> staging Parquet/CSV -> DuckDB merge (store).
// Real files stay in this tab: they are read, parsed in the worker and stored locally.

import { pythonEngine } from '../pythonEngine'
import { ensurePythonModules } from '../pythonModules'
import { store, type ImportResult, type Mode } from '../store'

export interface Staged {
  format: 'parquet' | 'csv'
  data: Uint8Array | string
  rows: number
  /** Parser attrs (platform, unrecognised_prefix, skipped_records, …). */
  info: Record<string, unknown>
}

// `import pyarrow` makes Pyodide fetch pyarrow (~10 MB, once) for Parquet staging.
// Pyodide loads packages named in `import` lines of the code it runs, so binary .xls
// statements get an extra `import xlrd`.
const PARQUET = `import pyarrow
import session
session.stage(source, text, chat_name, label, "parquet")`
const OLE2 = [0xd0, 0xcf, 0x11, 0xe0, 0xa1, 0xb1, 0x1a, 0xe1]
const CSV = `import session
session.stage(source, text, chat_name, label, "csv")`

let parquetOk = true

async function stageInWorker(
  source: string,
  text: string | Uint8Array,
  chatName: string | null,
  label: string,
): Promise<Staged> {
  await ensurePythonModules()
  const inputs = { source, text, chat_name: chatName, label }
  const xls = text instanceof Uint8Array && OLE2.every((b, i) => text[i] === b) ? 'import xlrd\n' : ''
  let out: { result: unknown }
  if (parquetOk) {
    try {
      out = await pythonEngine.runPython(xls + PARQUET, inputs)
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      if (!/pyarrow/i.test(msg)) throw err
      parquetOk = false // pyarrow could not be loaded: use CSV from now on
      out = await pythonEngine.runPython(xls + CSV, inputs)
    }
  } else {
    out = await pythonEngine.runPython(xls + CSV, inputs)
  }
  const r = out.result as { format: 'parquet' | 'csv'; data: Uint8Array | string; rows: number; info: string }
  return { ...r, info: JSON.parse(r.info) as Record<string, unknown> }
}

export async function sha256(data: string | Uint8Array): Promise<string> {
  const bytes = typeof data === 'string' ? new TextEncoder().encode(data) : data
  const buf = await crypto.subtle.digest('SHA-256', bytes as BufferSource)
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('')
}

export type IngestOutcome =
  | { kind: 'known'; fileName: string }
  | { kind: 'imported'; result: ImportResult; staged: Omit<Staged, 'data'>; parseMs: number }

/** Import one file into `mode`'s database. Files already imported (same SHA-256) are skipped. */
export async function ingest(
  mode: Mode,
  file: {
    source: string
    name: string
    chatName?: string
    readText: () => Promise<string>
    readBytes: () => Promise<Uint8Array>
  },
): Promise<IngestOutcome> {
  // Bank statements are binary (XLSX / XLS); everything else is text.
  const text = file.source === 'bank' ? await file.readBytes() : await file.readText()
  const hash = await sha256(text)
  await store.setMode(mode)
  const [known] = await store.query<{ file_name: string }>('import_by_hash', { file_hash: hash })
  if (known) return { kind: 'known', fileName: known.file_name }

  const t0 = performance.now()
  const staged = await stageInWorker(file.source, text, file.chatName ?? null, file.name)
  const parseMs = Math.round(performance.now() - t0)
  const result = await store.importStaged(mode, staged, { source: file.source, fileName: file.name, fileHash: hash })
  const { data: _data, ...rest } = staged // eslint-disable-line @typescript-eslint/no-unused-vars
  return { kind: 'imported', result, staged: rest, parseMs }
}
