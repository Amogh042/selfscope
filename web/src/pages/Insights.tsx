import { useEffect, useMemo, useState } from 'react'
import { Panel, Terminal } from '../components/pixel'
import { SourceIcon } from '../components/SourceIcon'
import { useApp, useStoreQuery } from '../lib/appState'
import { computeInsights, type EngineResult, type Insight, type PeriodResult } from '../lib/insights'
import { store } from '../lib/store'

const fmtDate = (s: string | null) =>
  s ? new Date(`${s}T00:00:00Z`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }) : '—'

const STRENGTH_CLS: Record<string, string> = {
  strong: 'border-xp text-xp',
  moderate: 'border-orange-light text-orange-light',
  weak: 'border-muted text-muted',
}

function Strength({ s }: { s: string }) {
  return <span className={`border-2 px-1.5 py-0.5 font-pixel text-[8px] uppercase ${STRENGTH_CLS[s] ?? STRENGTH_CLS.weak}`}>{s}</span>
}

function Sources({ sources }: { sources: string[] }) {
  return (
    <span className="flex items-center gap-1">
      {sources.map((s) => (
        <span key={s} className="flex size-6 items-center justify-center border-2 border-orange-dark bg-bg" title={s}>
          <SourceIcon source={s === 'bank' || s === 'youtube' || s === 'spotify' || s === 'whatsapp' ? s : 'unknown'} size={14} />
        </span>
      ))}
    </span>
  )
}

function InsightCard({ i, rank }: { i: Insight; rank: number }) {
  return (
    <li className="flex flex-col gap-2 border-2 border-orange bg-panel p-3 shadow-block-sm">
      <div className="flex items-center justify-between gap-2">
        <span className="font-pixel text-[9px] text-orange">#{rank}</span>
        <span className="flex items-center gap-2">
          <Sources sources={i.sources} />
          <Strength s={i.strength} />
        </span>
      </div>
      <p className="text-sm leading-snug text-text">{i.sentence}</p>
      <p className="font-mono text-[11px] text-muted">{i.stats}</p>
    </li>
  )
}

export default function InsightsPage() {
  const { mode, resolved, storeState } = useApp()
  const [res, setRes] = useState<EngineResult | null>(null)
  const [meta, setMeta] = useState<{ cached: boolean; ms: number } | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showAll, setShowAll] = useState(false)
  const range = useMemo(() => ({ from: resolved?.from ?? null, to: resolved?.to ?? null }), [resolved?.from, resolved?.to])
  const me = useStoreQuery<{ me: string | null }>('me').data?.[0]?.me ?? null
  const hasChats = (useStoreQuery<{ chat: string }>('whatsapp_chats').data ?? []).length > 0

  useEffect(() => {
    if (storeState.status !== 'ready' || !storeState.mode || !resolved) {
      // No data to analyse (e.g. switched to an empty database): drop the previous result.
      setRes(null)
      setMeta(null)
      setBusy(false)
      return
    }
    let live = true
    setBusy(true)
    setError(null)
    computeInsights(storeState.mode, range)
      .then((r) => {
        if (!live) return
        setRes(r.result)
        setMeta({ cached: r.cached, ms: r.ms })
      })
      .catch((e) => live && setError(e instanceof Error ? e.message.trim().split('\n').slice(-1)[0] : String(e)))
      .finally(() => live && setBusy(false))
    return () => {
      live = false
    }
  }, [storeState.status, storeState.version, storeState.mode, range, resolved])

  const insights = res?.insights ?? []
  const shown = showAll ? insights : insights.slice(0, 12)

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-8 px-4 py-10 sm:px-6">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="flex flex-col gap-3">
          <h1 className="text-2xl text-orange [text-shadow:4px_4px_0_var(--color-orange-dark)] sm:text-3xl">INSIGHTS</h1>
          <p className="font-pixel text-[11px] text-text">
            WHAT GOES TOGETHER<span className="animate-pixel-blink text-orange">_</span>
          </p>
        </div>
        <p className="max-w-md font-mono text-xs text-muted sm:text-right">
          {mode === 'demo' ? 'Demo data' : 'Your data'} · {fmtDate(range.from)} – {fmtDate(range.to)}
          <br />
          {busy
            ? 'Analysing in the Python worker…'
            : meta
              ? `${meta.cached ? 'from cache' : 'computed'} in ${meta.ms.toLocaleString('en-IN')} ms`
              : ''}
          {res && (
            <>
              <br />
              {res.correlation_window.days
                ? `cross-app links: ${res.correlation_window.days} days where all apps have data · ${res.tests.tests.toLocaleString('en-IN')} tests, false-discovery rate 5%`
                : `no cross-app links: ${res.correlation_window.reason ?? 'not enough overlapping data'}`}
            </>
          )}
        </p>
      </header>

      {!resolved && <Terminal tone="muted">No data in this database yet — load data on the import screen.</Terminal>}
      {resolved && hasChats && !me && (
        <Terminal tone="muted">
          Tip: pick your own name under "Which one is you?" on the import screen to include the messages you send and their
          mood in the analysis.
        </Terminal>
      )}
      {error && <Terminal tone="error">{error}</Terminal>}

      {res && (
        <>
          <Panel
            title="WHAT GOES TOGETHER"
            tag={<span className="font-mono text-[11px] text-muted">{insights.length} FOUND · RANKED BY STRENGTH</span>}
          >
            <p className="font-mono text-[11px] text-muted">
              Associations between different apps on the same or following days, after correcting for testing many pairs at
              once. <span className="text-orange-light">Association is not causation</span>: both things may be driven by
              something else (exams, weekends, holidays).
            </p>
            {insights.length === 0 ? (
              <p className="font-mono text-xs text-muted">No cross-app association passed the bar for this date range.</p>
            ) : (
              <ul className="grid gap-4 md:grid-cols-2">
                {shown.map((i, k) => (
                  <InsightCard key={`${i.x}-${i.y}-${i.lag}`} i={i} rank={k + 1} />
                ))}
              </ul>
            )}
            {insights.length > 12 && (
              <button className="self-start font-pixel text-[9px] text-orange hover:underline" onClick={() => setShowAll((v) => !v)}>
                {showAll ? '▲ SHOW TOP 12' : `▼ SHOW ALL ${insights.length}`}
              </button>
            )}
            {res.weak_signals.length > 0 && (
              <details className="border-2 border-orange-dark bg-bg p-3">
                <summary className="cursor-pointer font-pixel text-[9px] text-muted">
                  WEAKER SIGNALS · {res.weak_signals.length} · MAY BE CHANCE
                </summary>
                <p className="mt-2 font-mono text-[11px] text-muted">
                  Statistically significant but weak (|rho| 0.1–0.2). In our null test (dates shuffled, so no real link
                  exists) about 1–2 of these still appeared per run, so treat them as hints. Rare events like food delivery
                  can show a large "x times as likely" with only a weak correlation.
                </p>
                <ul className="mt-3 flex flex-col gap-2">
                  {res.weak_signals.map((w) => (
                    <li key={`${w.x}-${w.y}-${w.lag}`} className="flex flex-col gap-0.5 border-l-2 border-orange-dark pl-3">
                      <span className="text-xs text-text">{w.sentence}</span>
                      <span className="font-mono text-[10px] text-muted">{w.stats}</span>
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </Panel>

          {res.song_mood_by_hour?.sentence && (
            <Panel title="SONG MOOD BY HOUR" tag={<span className="font-mono text-[11px] text-muted">SPOTIFY · KNOWN MOODS ONLY</span>}>
              <p className="text-sm text-text">{res.song_mood_by_hour.sentence}</p>
              <p className="font-mono text-[11px] text-muted">
                chi-square test, p {res.song_mood_by_hour.p < 0.001 ? '< 0.001' : res.song_mood_by_hour.p.toFixed(3)} · songs not on
                the curated mood list are left out
              </p>
            </Panel>
          )}

          <PeriodsPanel results={res.periods} />
          <AnomaliesPanel res={res} />
        </>
      )}
    </div>
  )
}

function PeriodsPanel({ results }: { results: PeriodResult[] }) {
  const periods = useStoreQuery<{ period_id: string; label: string; start_date: string; end_date: string; origin: string }>(
    'periods_list',
  ).data ?? []
  const [label, setLabel] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const byPeriod = useMemo(() => {
    const m = new Map<string, PeriodResult[]>()
    for (const r of results) m.set(r.period, [...(m.get(r.period) ?? []), r])
    return m
  }, [results])

  async function add() {
    setErr(null)
    if (!label.trim() || !from || !to) {
      setErr('Give the period a name and both dates.')
      return
    }
    try {
      await store.addPeriod(label.trim(), from, to)
      setLabel('')
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    }
  }

  return (
    <Panel title="PERIODS" tag={<span className="font-mono text-[11px] text-muted">INSIDE VS OUTSIDE · MANN-WHITNEY + FDR</span>}>
      <div className="flex flex-col gap-3">
        <span className="font-pixel text-[9px] text-orange-light">TAGGED DATE RANGES</span>
        <ul className="flex flex-wrap gap-2">
          {periods.map((p) => (
            <li key={p.period_id} className="flex items-center gap-2 border-2 border-orange-dark bg-bg px-2 py-1 font-mono text-xs text-text">
              <span className="text-orange-light">{p.label}</span>
              <span className="text-muted">
                {fmtDate(p.start_date)} – {fmtDate(p.end_date)}
                {p.origin === 'demo' && ' · demo'}
              </span>
              <button
                className="text-muted hover:text-danger"
                aria-label={`Delete ${p.label} ${p.start_date}`}
                onClick={() => void store.deletePeriod(p.period_id)}
              >
                ✖
              </button>
            </li>
          ))}
          {periods.length === 0 && <li className="font-mono text-xs text-muted">None yet. Weekends are always compared.</li>}
        </ul>
        <div className="flex flex-wrap items-end gap-2 font-mono text-xs">
          <label className="flex flex-col gap-1 text-muted">
            name
            <input
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="Exams, Trip, …"
              className="w-36 border-2 border-orange-dark bg-bg px-2 py-1 text-text"
            />
          </label>
          <label className="flex flex-col gap-1 text-muted">
            from
            <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="border-2 border-orange-dark bg-bg px-1 py-0.5 text-text [color-scheme:dark]" />
          </label>
          <label className="flex flex-col gap-1 text-muted">
            to
            <input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="border-2 border-orange-dark bg-bg px-1 py-0.5 text-text [color-scheme:dark]" />
          </label>
          <button className="pixel-btn" onClick={() => void add()}>
            + TAG
          </button>
        </div>
        {err && <p className="font-mono text-xs text-danger">{err}</p>}
      </div>

      {[...byPeriod.entries()].map(([name, rows]) => {
        const sig = rows.filter((r) => r.significant)
        return (
          <div key={name} className="flex flex-col gap-2">
            <span className="font-pixel text-[9px] text-orange-light">
              {name.toUpperCase()} · {sig.length} CLEAR DIFFERENCE{sig.length === 1 ? '' : 'S'} OF {rows.length} METRICS
            </span>
            <ul className="flex flex-col gap-1.5">
              {sig.slice(0, 10).map((r) => (
                <li key={r.metric} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-l-2 border-orange pl-3">
                  <span className={r.direction === 'up' ? 'text-xp' : 'text-orange-light'}>{r.direction === 'up' ? '▲' : '▼'}</span>
                  <span className="text-sm text-text">{r.sentence}</span>
                  <span className="font-mono text-[10px] text-muted">
                    {r.strength} · adjusted p {r.q < 0.001 ? '< 0.001' : r.q.toFixed(3)}
                  </span>
                </li>
              ))}
              {sig.length === 0 && <li className="font-mono text-xs text-muted">No clear differences.</li>}
            </ul>
          </div>
        )
      })}
    </Panel>
  )
}

function AnomaliesPanel({ res }: { res: EngineResult }) {
  const days = res.anomalies.days ?? []
  return (
    <Panel title="UNUSUAL DAYS" tag={<span className="font-mono text-[11px] text-muted">ISOLATION FOREST + ROBUST Z</span>}>
      {days.length === 0 ? (
        <p className="font-mono text-xs text-muted">Nothing unusual in this range (needs at least 30 days).</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {days.map((d) => (
            <li key={d.date} className="flex flex-col gap-0.5 border-l-2 border-orange pl-3">
              <span className="text-sm text-text">{d.sentence}</span>
              <span className="font-mono text-[10px] text-muted">
                {d.metrics.map((m) => `${m.metric} z ${m.z > 0 ? '+' : ''}${m.z}`).join(' · ')}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  )
}
