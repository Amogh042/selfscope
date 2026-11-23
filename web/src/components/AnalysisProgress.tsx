// Step-by-step progress for a first (uncached) analysis: "Loading Python → Reading data →
// Finding patterns", with the Python loader's own message and the elapsed time, so a cold
// start is never a blank wait.

import { useEffect, useState } from 'react'
import { ANALYSIS_STEPS, type AnalysisStep } from '../lib/insights'
import { pythonEngine, type StatusSnapshot } from '../lib/pythonEngine'

export function usePythonStatus(): StatusSnapshot {
  const [snap, setSnap] = useState<StatusSnapshot>(pythonEngine.status)
  useEffect(() => pythonEngine.onStatus(setSnap), [])
  return snap
}

function useElapsed(active: boolean) {
  const [t0] = useState(() => performance.now())
  const [, tick] = useState(0)
  useEffect(() => {
    if (!active) return
    const id = setInterval(() => tick((n) => n + 1), 500)
    return () => clearInterval(id)
  }, [active])
  return Math.floor((performance.now() - t0) / 1000)
}

export function AnalysisProgress({ step }: { step: AnalysisStep }) {
  const py = usePythonStatus()
  const secs = useElapsed(true)
  const at = ANALYSIS_STEPS.findIndex((s) => s.step === step)
  const detail =
    step === 'python'
      ? py.status === 'ready'
        ? 'Installing the analysis modules'
        : py.detail
      : step === 'reading'
        ? 'Labelling songs, videos, messages and payments, then reading the daily features from DuckDB'
        : 'Correlations, calendar control, periods and unusual days (Python worker)'
  return (
    <div id="analysis-progress" className="flex flex-col gap-2 border-2 border-orange-dark bg-bg p-3" role="status" aria-live="polite">
      <div className="flex items-baseline justify-between gap-3 font-mono text-[11px]">
        <span className="font-pixel text-[9px] text-orange-light">FIRST ANALYSIS · STEP {at + 1}/3</span>
        <span className="text-muted tabular-nums">{secs}s</span>
      </div>
      <ol className="grid grid-cols-3 gap-[2px] border-2 border-bg bg-bg p-[2px] outline-2 outline-orange-dark">
        {ANALYSIS_STEPS.map((s, i) => (
          <li
            key={s.step}
            className={`truncate px-2 py-1 font-pixel text-[8px] leading-relaxed ${
              i < at ? 'bg-xp text-bg' : i === at ? 'animate-pixel-blink bg-orange text-bg' : 'bg-panel text-muted'
            }`}
          >
            {i < at ? '✓ ' : ''}
            {s.label.toUpperCase()}…
          </li>
        ))}
      </ol>
      <p className="truncate font-mono text-[10px] text-muted" title={detail}>
        &gt; {detail}
      </p>
      <p className="font-mono text-[10px] text-muted">
        Runs in this browser. The first time takes ~15–30 s (Python downloads once, then is cached); later visits use the saved result.
      </p>
    </div>
  )
}
