import { useCallback, useEffect, useState } from 'react'
import { DataRows, Panel, StatusBadge, Terminal, XpBar, type Status } from '../components/pixel'
import { useFps } from '../hooks/useFps'
import { pythonEngine, type EngineInfo, type RunResult, type StatusSnapshot } from '../lib/pythonEngine'
import { duckdbVersion, query } from '../lib/duckdb'

const PANDAS_TEST = `import pandas as pd

df = pd.DataFrame({
    "app":     ["UPI", "UPI", "Spotify", "Spotify", "YouTube"],
    "minutes": [12, 30, 45, 15, 60],
})
print(df.to_string(index=False))

{
    "mean_minutes": float(df["minutes"].mean()),
    "mean_by_app": df.groupby("app")["minutes"].mean().round(2).to_dict(),
}`

/** Ticks while `running` so the user can see the UI thread is alive. */
function useElapsed(running: boolean): number {
  const [start] = useState(() => performance.now())
  const [now, setNow] = useState(start)
  useEffect(() => {
    if (!running) return
    const id = setInterval(() => setNow(performance.now()), 100)
    return () => clearInterval(id)
  }, [running])
  return now - start
}

function PythonPanel({ snap, info, error }: { snap: StatusSnapshot; info: EngineInfo | null; error: string | null }) {
  const elapsed = useElapsed(snap.status === 'loading' || snap.status === 'idle')
  return (
    <Panel title="PYTHON ENGINE" tag={<StatusBadge status={snap.status} />}>
      <p className="font-mono text-xs text-muted">
        Pyodide · Web Worker ·{' '}
        {snap.status === 'ready' && info ? `loaded in ${(info.loadMs / 1000).toFixed(1)}s` : `${(elapsed / 1000).toFixed(1)}s`}
      </p>
      <DataRows
        rows={[
          ['pyodide', info?.pyodide ?? '—'],
          ['python', info?.python ?? '—'],
          ['pandas', info?.pandas ?? '—'],
          ['numpy', info?.numpy ?? '—'],
          ['scipy', info?.scipy ?? '—'],
          ['scikit-learn', info?.sklearn ?? '—'],
        ]}
      />
      <Terminal tone={error ? 'error' : 'muted'}>
        {error ?? `> ${snap.detail}`}
        {snap.status === 'loading' && <span className="animate-pixel-blink">_</span>}
      </Terminal>
    </Panel>
  )
}

function DuckPanel({ onReady }: { onReady: () => void }) {
  const [status, setStatus] = useState<Status>('loading')
  const [version, setVersion] = useState<string | null>(null)
  const [answer, setAnswer] = useState<string | null>(null)
  const [ms, setMs] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const t0 = performance.now()
        const v = await duckdbVersion()
        const rows = await query<{ answer: number }>('SELECT 42 AS answer')
        if (cancelled) return
        setVersion(v)
        setAnswer(String(rows[0]?.answer))
        setMs(Math.round(performance.now() - t0))
        setStatus('ready')
        onReady()
      } catch (err) {
        if (cancelled) return
        setError(err instanceof Error ? err.message : String(err))
        setStatus('error')
      }
    })()
    return () => {
      cancelled = true
    }
  }, [onReady])

  return (
    <Panel title="SQL ENGINE" tag={<StatusBadge status={status} />}>
      <p className="font-mono text-xs text-muted">DuckDB-WASM · own Web Worker · self-hosted .wasm</p>
      <DataRows
        rows={[
          ['duckdb', version ?? '—'],
          ['init + query', ms != null ? `${ms} ms` : '—'],
        ]}
      />
      <div className="flex items-center justify-between gap-4 border-2 border-orange-dark bg-bg p-3">
        <code className="font-mono text-xs text-orange-light">SELECT 42 AS answer</code>
        <span className="font-pixel text-lg text-xp">{answer ?? '··'}</span>
      </div>
      {error && <Terminal tone="error">{error}</Terminal>}
    </Panel>
  )
}

function PandasTest({ ready }: { ready: boolean }) {
  const [running, setRunning] = useState(false)
  const [out, setOut] = useState<RunResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function run() {
    setRunning(true)
    setError(null)
    try {
      setOut(await pythonEngine.runPython(PANDAS_TEST))
    } catch (err) {
      setOut(null)
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setRunning(false)
    }
  }

  return (
    <Panel title="PANDAS TEST" tag={<span className="font-mono text-xs text-muted">runs in worker</span>}>
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="flex flex-col gap-3">
          <span className="font-mono text-xs text-muted uppercase">Input</span>
          <Terminal>
            <span className="text-orange-light">{PANDAS_TEST}</span>
          </Terminal>
        </div>
        <div className="flex flex-col gap-3">
          <span className="font-mono text-xs text-muted uppercase">
            Output{out ? ` · ${out.durationMs} ms` : ''}
          </span>
          {error ? (
            <Terminal tone="error">{error}</Terminal>
          ) : out ? (
            <Terminal>
              {out.stdout.join('\n')}
              {'\n\n'}
              <span className="text-xp">{'=> '}{JSON.stringify(out.result, null, 2)}</span>
            </Terminal>
          ) : (
            <Terminal tone="muted">{ready ? '> Press RUN to execute.' : '> Waiting for Python engine…'}</Terminal>
          )}
        </div>
      </div>
      <div>
        <button className="pixel-btn" onClick={run} disabled={!ready || running}>
          {running ? 'RUNNING…' : '▶ RUN PANDAS TEST'}
        </button>
      </div>
    </Panel>
  )
}

export default function SystemCheck() {
  const [snap, setSnap] = useState<StatusSnapshot>(pythonEngine.status)
  const [info, setInfo] = useState<EngineInfo | null>(null)
  const [pyError, setPyError] = useState<string | null>(null)
  const [duckReady, setDuckReady] = useState(false)
  const fps = useFps()

  useEffect(() => pythonEngine.onStatus(setSnap), [])
  useEffect(() => {
    pythonEngine.init().then(setInfo, (err) => setPyError(err instanceof Error ? err.message : String(err)))
  }, [])
  const onDuckReady = useCallback(() => setDuckReady(true), [])

  const pyReady = snap.status === 'ready' && info != null
  const readyCount = Number(pyReady) + Number(duckReady)

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-8 px-4 py-10 sm:px-6">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="flex flex-col gap-3">
          <h1 className="text-2xl text-orange [text-shadow:4px_4px_0_var(--color-orange-dark)] sm:text-3xl">
            SELFSCOPE
          </h1>
          <p className="font-pixel text-[11px] text-text">
            SYSTEM CHECK<span className="animate-pixel-blink text-orange">_</span>
          </p>
        </div>
        <div className="flex flex-col gap-4 sm:items-end">
          <p className="max-w-sm font-mono text-xs text-muted sm:text-right">
            All analysis runs in this browser tab.
            <br />
            <span className="text-xp">No data leaves this device.</span>
          </p>
          <a href="#/import" className="pixel-btn self-start sm:self-end">
            ▶ IMPORT DATA
          </a>
        </div>
      </header>

      <div className="pixel-panel p-4">
        <XpBar value={readyCount} max={2} label="Engines online" />
      </div>

      <div className="grid gap-8 md:grid-cols-2">
        <PythonPanel snap={snap} info={info} error={pyError} />
        <DuckPanel onReady={onDuckReady} />
      </div>

      <PandasTest ready={pyReady} />

      <footer className="flex flex-wrap items-center justify-between gap-3 border-t-2 border-orange-dark pt-4 font-mono text-xs text-muted">
        <span>
          UI THREAD <span className={fps >= 30 ? 'text-xp' : 'text-orange'}>■</span> {fps} FPS
        </span>
        <span>SelfScope v0.1 · engines check</span>
      </footer>
    </div>
  )
}
