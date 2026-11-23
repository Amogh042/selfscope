// PERIODS: inside vs outside each tagged period (and weekends), one table per period, plus the
// tag editor. Numbers come from analysis/periods.py (Mann-Whitney U + BH correction).

import { useMemo, useState } from 'react'
import { useStoreQuery } from '../../lib/appState'
import type { EngineResult, PeriodResult } from '../../lib/insights'
import { store } from '../../lib/store'
import { byUnit, colors, fmtDay, sourceColor } from '../../lib/sourceStyle'

interface Period {
  period_id: string
  label: string
  start_date: string
  end_date: string
  origin: string
}

function change(r: PeriodResult, unit: string) {
  if (unit === 'share') {
    const d = (r.mean_in - r.mean_out) * 100
    return `${d > 0 ? '+' : d < 0 ? '−' : ''}${Math.abs(d).toFixed(0)} pts`
  }
  if (unit === 'score') {
    const d = r.mean_in - r.mean_out
    return `${d > 0 ? '+' : d < 0 ? '−' : ''}${Math.abs(d).toFixed(2)}`
  }
  return r.pct_change == null ? '—' : `${r.pct_change > 0 ? '+' : r.pct_change < 0 ? '−' : ''}${Math.abs(r.pct_change * 100).toFixed(0)}%`
}

export function PeriodsSection({ res }: { res: EngineResult | null }) {
  const periods = useStoreQuery<Period>('periods_list').data ?? []
  const byPeriod = useMemo(() => {
    const m = new Map<string, PeriodResult[]>()
    for (const r of res?.periods ?? []) m.set(r.period, [...(m.get(r.period) ?? []), r])
    return m
  }, [res])
  const names = [...byPeriod.keys()]
  const [tab, setTab] = useState<string | null>(null)
  const [showAll, setShowAll] = useState(false)
  const active = tab && byPeriod.has(tab) ? tab : names[0]
  const rows = active ? (byPeriod.get(active) ?? []) : []
  const sig = rows.filter((r) => r.significant)
  const shown = showAll ? rows : rows.slice(0, Math.max(10, sig.length))

  return (
    <div className="flex flex-col gap-5">
      <TagEditor periods={periods} />
      {!res ? null : names.length === 0 ? (
        <p className="font-mono text-xs text-muted">Nothing to compare in this range (each side needs at least 5 days).</p>
      ) : (
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap gap-1" role="tablist" aria-label="Periods">
            {names.map((n) => (
              <button
                key={n}
                role="tab"
                aria-selected={n === active}
                onClick={() => setTab(n)}
                className={`border-2 px-2 py-1 font-pixel text-[8px] ${n === active ? 'border-orange bg-orange text-bg' : 'border-orange-dark text-muted hover:text-text'}`}
              >
                {n.toUpperCase()} · {(byPeriod.get(n) ?? []).filter((r) => r.significant).length}
              </button>
            ))}
          </div>
          <p className="font-mono text-xs font-bold text-text">
            {active === 'Weekends' ? 'Weekends' : active}: {sig.length} of {rows.length} metrics differ clearly from the other days
            {rows[0] && ` (${rows[0].n_in} days inside, ${rows[0].n_out} outside)`}
          </p>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] font-mono text-[11px] tabular-nums">
              <thead>
                <tr className="text-left text-muted">
                  <th className="py-1 pr-2 font-normal">metric</th>
                  <th className="py-1 pr-2 text-right font-normal">inside (avg/day)</th>
                  <th className="py-1 pr-2 text-right font-normal">outside</th>
                  <th className="py-1 pr-2 text-right font-normal">change</th>
                  <th className="py-1 pr-2 text-right font-normal">adj. p</th>
                  <th className="py-1 font-normal">significant</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((r) => {
                  const unit = res.metrics[r.metric]?.unit ?? 'count'
                  return (
                    <tr key={r.metric} className={`border-t border-grid ${r.significant ? 'text-text' : 'text-muted'}`} title={r.sentence}>
                      <td className="py-1 pr-2">
                        <span className="mr-2 inline-block size-2" style={{ background: sourceColor(r.source) }} aria-hidden />
                        {r.label}
                      </td>
                      <td className="py-1 pr-2 text-right">{byUnit(unit, r.mean_in)}</td>
                      <td className="py-1 pr-2 text-right">{byUnit(unit, r.mean_out)}</td>
                      <td className="py-1 pr-2 text-right" style={{ color: r.significant ? colors().orangeLight : undefined }}>
                        {r.direction === 'up' ? '▲' : '▼'} {change(r, unit)}
                      </td>
                      <td className="py-1 pr-2 text-right">{r.q < 0.001 ? '< 0.001' : r.q.toFixed(3)}</td>
                      <td className="py-1">{r.significant ? <span className="text-xp">YES</span> : 'no'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          {rows.length > shown.length || showAll ? (
            <button className="self-start font-pixel text-[9px] text-orange hover:underline" onClick={() => setShowAll((v) => !v)}>
              {showAll ? '▲ SHOW FEWER' : `▼ SHOW ALL ${rows.length} METRICS`}
            </button>
          ) : null}
          <p className="font-mono text-[10px] text-muted">
            Mann-Whitney U test per metric, adjusted for all period × metric tests (BH, 5%). Shares change in percentage points.
          </p>
        </div>
      )}
    </div>
  )
}

function TagEditor({ periods }: { periods: Period[] }) {
  const [label, setLabel] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [err, setErr] = useState<string | null>(null)
  async function add() {
    setErr(null)
    if (!label.trim() || !from || !to) return setErr('Give the period a name and both dates.')
    try {
      await store.addPeriod(label.trim(), from, to)
      setLabel('')
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    }
  }
  return (
    <div className="flex flex-col gap-3 border-2 border-orange-dark bg-bg p-3">
      <span className="font-pixel text-[9px] text-orange-light">TAGGED DATE RANGES</span>
      <ul className="flex flex-wrap gap-2">
        {periods.map((p) => (
          <li key={p.period_id} className="flex items-center gap-2 border-2 border-orange-dark bg-panel px-2 py-1 font-mono text-xs text-text">
            <span className="text-orange-light">{p.label}</span>
            <span className="text-muted">
              {fmtDay(p.start_date)} – {fmtDay(p.end_date)}
              {p.origin === 'demo' && ' · demo'}
            </span>
            <button className="text-muted hover:text-danger" aria-label={`Delete ${p.label} ${p.start_date}`} onClick={() => void store.deletePeriod(p.period_id)}>
              ✖
            </button>
          </li>
        ))}
        {periods.length === 0 && <li className="font-mono text-xs text-muted">None yet. Weekends are always compared.</li>}
      </ul>
      <div className="flex flex-wrap items-end gap-2 font-mono text-xs">
        <label className="flex flex-col gap-1 text-muted">
          name
          <input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Exams, Trip, …" className="w-36 border-2 border-orange-dark bg-panel px-2 py-1 text-text" />
        </label>
        <label className="flex flex-col gap-1 text-muted">
          from
          <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="border-2 border-orange-dark bg-panel px-1 py-0.5 text-text [color-scheme:dark]" />
        </label>
        <label className="flex flex-col gap-1 text-muted">
          to
          <input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="border-2 border-orange-dark bg-panel px-1 py-0.5 text-text [color-scheme:dark]" />
        </label>
        <button className="pixel-btn" onClick={() => void add()}>
          + TAG
        </button>
      </div>
      {err && <p className="font-mono text-xs text-danger">{err}</p>}
    </div>
  )
}
