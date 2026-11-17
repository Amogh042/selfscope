/// <reference lib="webworker" />
// Python engine: Pyodide running inside a dedicated Web Worker so the multi-second
// runtime + package load never blocks the UI thread.
//
// Privacy: the CDN below serves only the Python runtime and package wheels.
// User data is never sent anywhere — it is passed to this worker via postMessage
// and stays in browser memory.

import type { PyodideAPI } from 'pyodide'
import type {
  EngineInfo,
  EngineStatus,
  RunResult,
  WorkerRequest,
  WorkerResponse,
} from '../lib/pythonProtocol'

declare const self: DedicatedWorkerGlobalScope

// Pinned on purpose: bump deliberately and re-run the SYSTEM CHECK page.
const PYODIDE_VERSION = '314.0.8'
const INDEX_URL = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`
const PACKAGES = ['pandas', 'numpy', 'scipy', 'scikit-learn']

let pyodide: PyodideAPI | null = null
let initPromise: Promise<EngineInfo> | null = null
// Serialise runs so concurrent requests can't interleave stdout or globals.
let queue: Promise<unknown> = Promise.resolve()
let stdoutSink: string[] = []

function post(msg: WorkerResponse) {
  self.postMessage(msg)
}

function setStatus(status: EngineStatus, detail: string) {
  post({ type: 'status', status, detail })
}

async function init(): Promise<EngineInfo> {
  const t0 = performance.now()
  setStatus('loading', `Fetching Pyodide v${PYODIDE_VERSION} runtime`)

  const { loadPyodide } = (await import(
    /* @vite-ignore */ `${INDEX_URL}pyodide.mjs`
  )) as typeof import('pyodide')

  const py = await loadPyodide({ indexURL: INDEX_URL })
  py.setStdout({ batched: (line) => stdoutSink.push(line) })
  py.setStderr({ batched: (line) => stdoutSink.push(line) })

  setStatus('loading', `Loading ${PACKAGES.join(', ')}`)
  await py.loadPackage(PACKAGES, {
    messageCallback: (m) => setStatus('loading', m),
    errorCallback: (m) => setStatus('loading', m),
  })

  setStatus('loading', 'Importing packages')
  const versions = py.runPython(`
import sys, pandas, numpy, scipy, sklearn
{
    "python": sys.version.split()[0],
    "pandas": pandas.__version__,
    "numpy": numpy.__version__,
    "scipy": scipy.__version__,
    "sklearn": sklearn.__version__,
}
`)
  const v = versions.toJs({ dict_converter: Object.fromEntries }) as Record<string, string>
  versions.destroy()

  pyodide = py
  const info: EngineInfo = {
    pyodide: py.version,
    python: v.python,
    pandas: v.pandas,
    numpy: v.numpy,
    scipy: v.scipy,
    sklearn: v.sklearn,
    loadMs: Math.round(performance.now() - t0),
  }
  setStatus('ready', `Python ${info.python} ready`)
  return info
}

/** Convert a Pyodide return value into something postMessage can clone. */
function toPlain(value: unknown): unknown {
  if (value === undefined || value === null) return null
  const maybeProxy = value as { toJs?: (o: object) => unknown; destroy?: () => void; toString(): string }
  if (typeof maybeProxy.toJs === 'function') {
    try {
      const converted = maybeProxy.toJs({ dict_converter: Object.fromEntries, create_pyproxies: false })
      structuredClone(converted)
      return converted
    } catch {
      return maybeProxy.toString() // fall back to Python's str()
    } finally {
      maybeProxy.destroy?.()
    }
  }
  return value
}

async function run(code: string): Promise<RunResult> {
  const py = pyodide ?? (await (initPromise ??= init()), pyodide)
  if (!py) throw new Error('Python engine failed to initialise')

  const t0 = performance.now()
  stdoutSink = []
  try {
    // Auto-load any extra Pyodide packages the code imports; keep loader chatter out of stdout.
    await py.loadPackagesFromImports(code, { messageCallback: () => {} })
    const raw = await py.runPythonAsync(code)
    return { result: toPlain(raw), stdout: stdoutSink, durationMs: Math.round(performance.now() - t0) }
  } finally {
    stdoutSink = []
  }
}

self.onmessage = (event: MessageEvent<WorkerRequest>) => {
  const req = event.data
  let job: Promise<EngineInfo | RunResult>
  if (req.type === 'init') {
    job = initPromise ??= init().catch((err) => {
      initPromise = null
      setStatus('error', String(err))
      throw err
    })
  } else {
    const runJob = queue.catch(() => {}).then(() => run(req.code))
    queue = runJob
    job = runJob
  }

  job.then(
    (value) => post({ type: 'result', id: req.id, ok: true, value }),
    (err: unknown) =>
      post({
        type: 'result',
        id: req.id,
        ok: false,
        // PythonError messages already contain the full Python traceback.
        error: err instanceof Error ? err.message : String(err),
      }),
  )
}
