import { useEffect, useState } from 'react'
import { RANGE_LABEL, useApp, type RangePreset } from '../lib/appState'

const NAV = [
  ['/dashboard', 'DASHBOARD'],
  ['/import', 'IMPORT'],
  ['/data', 'DATA'],
  ['/system', 'SYSTEM'],
] as const

const fmt = (s: string) =>
  new Date(`${s}T00:00:00Z`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' })

export function AppHeader() {
  const { path, mode, setMode, range, setRange, resolved, href, storeState, bounds } = useApp()
  // "/" shows the dashboard once there is data, else the import screen
  const current = path === '/' ? ((bounds?.events ?? 0) > 0 ? '/dashboard' : '/import') : path === '/insights' ? '/dashboard' : path
  const [from, setFrom] = useState(range.from ?? '')
  const [to, setTo] = useState(range.to ?? '')
  useEffect(() => {
    setFrom(range.from ?? resolved?.from ?? '')
    setTo(range.to ?? resolved?.to ?? '')
  }, [range.preset]) // eslint-disable-line react-hooks/exhaustive-deps

  const busy = storeState.status === 'opening'

  return (
    <header className="top-0 z-20 border-b-2 md:sticky border-orange bg-bg/95 backdrop-blur-none">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-3 px-4 py-3 sm:px-6">
        <a href={href('/')} className="font-pixel text-[11px] text-orange">
          SELFSCOPE
        </a>
        <nav className="flex gap-1" aria-label="Main">
          {NAV.map(([p, label]) => (
            <a
              key={p}
              href={href(p)}
              aria-current={current === p ? 'page' : undefined}
              className={`border-2 px-2 py-1 font-pixel text-[9px] ${current === p ? 'border-orange bg-orange text-bg' : 'border-transparent text-text hover:border-orange-dark'}`}
            >
              {label}
            </a>
          ))}
        </nav>

        <div className="ml-auto flex flex-wrap items-center gap-3">
          {/* Data mode toggle */}
          <div className="flex border-2 border-orange-dark" role="group" aria-label="Data mode">
            {(['demo', 'real'] as const).map((m) => (
              <button
                key={m}
                onClick={() => void setMode(m)}
                disabled={busy}
                aria-pressed={mode === m}
                className={`px-2 py-1 font-pixel text-[9px] ${mode === m ? (m === 'demo' ? 'bg-orange-light text-bg' : 'bg-xp text-bg') : 'text-muted hover:text-text'}`}
              >
                {m === 'demo' ? 'DEMO' : 'MY DATA'}
              </button>
            ))}
          </div>
          {mode === 'demo' && (
            <span className="border-2 border-orange-light bg-orange-light/15 px-2 py-1 font-pixel text-[9px] text-orange-light" role="status">
              ★ DEMO DATA
            </span>
          )}

          {/* Global date range */}
          <label className="flex items-center gap-2 font-mono text-xs text-muted">
            <span className="sr-only">Date range</span>
            <select
              value={range.preset}
              onChange={(e) => {
                const preset = e.target.value as RangePreset
                setRange(preset === 'custom' ? { preset, from: resolved?.from, to: resolved?.to } : { preset })
              }}
              className="border-2 border-orange-dark bg-bg px-2 py-1 font-mono text-xs text-text"
            >
              {(Object.keys(RANGE_LABEL) as RangePreset[]).map((p) => (
                <option key={p} value={p}>
                  {RANGE_LABEL[p]}
                </option>
              ))}
            </select>
          </label>
          {range.preset === 'custom' && (
            <span className="flex items-center gap-1 font-mono text-xs">
              <input
                type="date"
                value={from}
                onChange={(e) => setFrom(e.target.value)}
                onBlur={() => from && to && setRange({ preset: 'custom', from, to })}
                className="border-2 border-orange-dark bg-bg px-1 py-0.5 text-text [color-scheme:dark]"
                aria-label="From date"
              />
              <span className="text-muted">–</span>
              <input
                type="date"
                value={to}
                onChange={(e) => setTo(e.target.value)}
                onBlur={() => from && to && setRange({ preset: 'custom', from, to })}
                className="border-2 border-orange-dark bg-bg px-1 py-0.5 text-text [color-scheme:dark]"
                aria-label="To date"
              />
            </span>
          )}
          <span className="font-mono text-xs text-muted" aria-live="polite">
            {resolved ? `showing ${fmt(resolved.from)} – ${fmt(resolved.to)}` : 'no data yet'}
          </span>
        </div>
      </div>
    </header>
  )
}
