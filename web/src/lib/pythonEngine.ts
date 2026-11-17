// Typed main-thread wrapper around the Pyodide Web Worker.
//
//   await pythonEngine.init()                 -> EngineInfo (versions)
//   await pythonEngine.runPython('1 + 1')     -> RunResult
//   pythonEngine.status / onStatus(listener)  -> 'idle' | 'loading' | 'ready' | 'error'

import type {
  EngineInfo,
  EngineStatus,
  RunResult,
  WorkerRequest,
  WorkerResponse,
} from './pythonProtocol'

export type { EngineInfo, EngineStatus, RunResult } from './pythonProtocol'

export interface StatusSnapshot {
  status: EngineStatus
  detail: string
}

// Distributive Omit: strips `id` from each variant of the request union.
type RequestBody = WorkerRequest extends infer R ? (R extends unknown ? Omit<R, 'id'> : never) : never
type Pending = { resolve: (v: never) => void; reject: (e: Error) => void }
type Listener = (s: StatusSnapshot) => void

class PythonEngine {
  private worker: Worker | null = null
  private nextId = 1
  private pending = new Map<number, Pending>()
  private listeners = new Set<Listener>()
  private initPromise: Promise<EngineInfo> | null = null
  private snapshot: StatusSnapshot = { status: 'idle', detail: 'Not started' }

  get status(): StatusSnapshot {
    return this.snapshot
  }

  /** Subscribe to status changes. Returns an unsubscribe function. */
  onStatus(listener: Listener): () => void {
    this.listeners.add(listener)
    listener(this.snapshot)
    return () => this.listeners.delete(listener)
  }

  /** Start the worker and load Pyodide + packages. Safe to call repeatedly. */
  init(): Promise<EngineInfo> {
    this.initPromise ??= this.request<EngineInfo>({ type: 'init' }).catch((err) => {
      this.initPromise = null // allow retry
      throw err
    })
    return this.initPromise
  }

  /**
   * Run Python code in the worker. Resolves with the last expression's value + stdout.
   * `inputs` are exposed to the code as Python globals for this run only.
   */
  async runPython(code: string, inputs?: Record<string, unknown>): Promise<RunResult> {
    await this.init()
    return this.request<RunResult>({ type: 'run', code, inputs })
  }

  private ensureWorker(): Worker {
    if (this.worker) return this.worker
    const worker = new Worker(new URL('../workers/python.worker.ts', import.meta.url), {
      type: 'module',
      name: 'selfscope-python',
    })
    worker.onmessage = (e: MessageEvent<WorkerResponse>) => this.handle(e.data)
    worker.onerror = (e) => {
      const msg = e.message || 'Python worker crashed'
      this.setStatus({ status: 'error', detail: msg })
      for (const p of this.pending.values()) p.reject(new Error(msg))
      this.pending.clear()
    }
    this.worker = worker
    return worker
  }

  private request<T>(msg: RequestBody): Promise<T> {
    const worker = this.ensureWorker()
    const id = this.nextId++
    return new Promise<T>((resolve, reject) => {
      this.pending.set(id, { resolve: resolve as (v: never) => void, reject })
      worker.postMessage({ ...msg, id } as WorkerRequest)
    })
  }

  private handle(msg: WorkerResponse) {
    if (msg.type === 'status') {
      this.setStatus({ status: msg.status, detail: msg.detail })
      return
    }
    const p = this.pending.get(msg.id)
    if (!p) return
    this.pending.delete(msg.id)
    if (msg.ok) p.resolve(msg.value as never)
    else p.reject(new Error(msg.error))
  }

  private setStatus(s: StatusSnapshot) {
    this.snapshot = s
    for (const l of this.listeners) l(s)
  }
}

/** App-wide singleton: one Python runtime per tab. */
export const pythonEngine = new PythonEngine()
