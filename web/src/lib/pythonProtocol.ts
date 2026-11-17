// Message protocol shared by the Python worker and its main-thread wrapper.
// Kept dependency-free so both the DOM and WebWorker tsconfigs can include it.

export type EngineStatus = 'idle' | 'loading' | 'ready' | 'error'

export interface EngineInfo {
  pyodide: string
  python: string
  pandas: string
  numpy: string
  scipy: string
  sklearn: string
  /** Wall-clock time from worker init to ready, in ms. */
  loadMs: number
}

export interface RunResult {
  /** Value of the last expression, converted to plain JS (null if none). */
  result: unknown
  /** Everything the code printed to stdout/stderr, in order. */
  stdout: string[]
  durationMs: number
}

// main thread -> worker
export type WorkerRequest =
  | { id: number; type: 'init' }
  /** `inputs` become Python globals for this run only (then deleted). */
  | { id: number; type: 'run'; code: string; inputs?: Record<string, unknown> }

// worker -> main thread
export type WorkerResponse =
  | { type: 'status'; status: EngineStatus; detail: string }
  | { type: 'result'; id: number; ok: true; value: EngineInfo | RunResult }
  | { type: 'result'; id: number; ok: false; error: string }
