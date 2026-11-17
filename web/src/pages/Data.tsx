import { useMemo, useState } from 'react'
import { Panel, Terminal } from '../components/pixel'
import { SourceIcon } from '../components/SourceIcon'
import { useApp, useStoreQuery } from '../lib/appState'
import type { DetectedSource } from '../lib/import/detect'
import { store } from '../lib/store'

interface Coverage {
  source: string
  first_date: string
  last_date: string
  days_with_data: number
  events: number
  last_import: string | null
}
interface Overlap {
  start_date: string | null
  end_date: string | null
  days: number
  sources: number
  source_list: string | null
}
interface Week {
  source: string
  week: string
  events: number
}
interface ImportRow {
  import_id: string
  source: string
  file_name: string
  rows_added: number
  rows_skipped: number
  min_date: string | null
  max_date: string | null
  imported_at: string
  events_now: number
}

const fmt = new Intl.NumberFormat('en-IN')
const STALE_DAYS = 30
const DAY = 86_400_000

const iconFor = (s: string): DetectedSource => (s === 'whatsapp' || s === 'spotify' || s === 'youtube' ? s : 'unknown')
const toDate = (s: string) => new Date(`${s.slice(0, 10)}T00:00:00Z`)
const nice = (s: string | null) =>
  s ? toDate(s).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }) : '—'
const mondayOf = (s: string) => {
  const d = toDate(s)
  d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7))
  return d.toISOString().slice(0, 10)
}
function daysAgo(iso: string | null): number | null {
  if (!iso) return null
  return Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / DAY))
}

export default function DataPage() {
  const { mode, storeState, href } = useApp()
  const coverage = useStoreQuery<Coverage>('coverage').data ?? []
  const overlap = useStoreQuery<Overlap>('overlap').data?.[0] ?? null
  const weekly = useStoreQuery<Week>('weekly').data ?? []
  const imports = useStoreQuery<ImportRow>('imports').data ?? []
  const [error, setError] = useState<string | null>(null)
  const [confirmWipe, setConfirmWipe] = useState(false)
  const [busy, setBusy] = useState(false)

  const totalEvents = coverage.reduce((n, c) => n + c.events, 0)

  // Shared weekly timeline across all sources.
  const timeline = useMemo(() => {
    if (!weekly.length) return null
    const weeks: string[] = []
    const first = weekly.reduce((m, w) => (w.week < m ? w.week : m), weekly[0].week)
    const last = weekly.reduce((m, w) => (w.week > m ? w.week : m), weekly[0].week)
    for (let d = toDate(first); d <= toDate(last); d = new Date(d.getTime() + 7 * DAY)) weeks.push(d.toISOString().slice(0, 10))
    const index = new Map(weeks.map((w, i) => [w, i]))
    const bySource = new Map<string, number[]>()
    for (const w of weekly) {
      const arr = bySource.get(w.source) ?? new Array(weeks.length).fill(0)
      arr[index.get(w.week) ?? 0] = w.events
      bySource.set(w.source, arr)
    }
    const band =
      overlap?.start_date && overlap.end_date
        ? { from: index.get(mondayOf(overlap.start_date)) ?? 0, to: index.get(mondayOf(overlap.end_date)) ?? weeks.length - 1 }
        : null
    return { weeks, bySource, band }
  }, [weekly, overlap])

  async function run(fn: () => Promise<void>) {
    setBusy(true)
    setError(null)
    try {
      await fn()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const bySource = useMemo(() => {
    const m = new Map<string, ImportRow[]>()
    for (const i of imports) m.set(i.source, [...(m.get(i.source) ?? []), i])
    return m
  }, [imports])

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-8 px-4 py-10 sm:px-6">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="flex flex-col gap-3">
          <h1 className="text-2xl text-orange [text-shadow:4px_4px_0_var(--color-orange-dark)] sm:text-3xl">DATA</h1>
          <p className="font-pixel text-[11px] text-text">
            {mode === 'demo' ? 'DEMO DATABASE' : 'MY DATABASE'}
            <span className="animate-pixel-blink text-orange">_</span>
          </p>
        </div>
        <p className="max-w-sm font-mono text-xs text-muted sm:text-right">
          Stored only in this browser ({mode === 'demo' ? 'selfscope_demo' : 'selfscope_real'}).
          <br />
          {storeState.status === 'ready' ? `${fmt.format(totalEvents)} events · ${imports.length} imports` : `database ${storeState.status}`}
        </p>
      </header>

      {error && <Terminal tone="error">{error}</Terminal>}

      <Panel
        title="COVERAGE"
        tag={
          <span className="font-mono text-[11px] text-muted">
            {overlap?.start_date
              ? `OVERLAP ${nice(overlap.start_date)} – ${nice(overlap.end_date)} · ${fmt.format(overlap.days)} DAYS · ${overlap.sources} SOURCES`
              : coverage.length > 1
                ? 'NO OVERLAP BETWEEN SOURCES'
                : 'WEEKLY'}
          </span>
        }
      >
        {!timeline ? (
          <p className="font-mono text-xs text-muted">
            No data in this database yet. Add files on the{' '}
            <a className="text-orange underline" href={href('/import')}>
              import screen
            </a>
            .
          </p>
        ) : (
          <>
            <ul className="flex flex-col gap-5">
              {coverage.map((c) => {
                const cells = timeline.bySource.get(c.source) ?? []
                const max = Math.max(...cells, 1)
                const ago = daysAgo(c.last_import)
                const stale = ago != null && ago > STALE_DAYS
                return (
                  <li key={c.source} className="grid gap-x-4 gap-y-2 sm:grid-cols-[8.5rem_1fr]">
                    <div className="flex items-center gap-2">
                      <div className="flex size-9 items-center justify-center border-2 border-orange-dark bg-bg">
                        <SourceIcon source={iconFor(c.source)} size={24} />
                      </div>
                      <span className="font-pixel text-[9px] text-text uppercase">{c.source}</span>
                    </div>
                    <div className="flex flex-col gap-1.5">
                      <div className="relative">
                        <div
                          className="grid h-6 gap-px border-2 border-orange-dark bg-bg p-px"
                          style={{ gridTemplateColumns: `repeat(${timeline.weeks.length}, minmax(0, 1fr))` }}
                          role="img"
                          aria-label={`${c.source}: data from ${c.first_date} to ${c.last_date}`}
                        >
                          {cells.map((n, i) => (
                            <div
                              key={i}
                              title={`${timeline.weeks[i]}: ${n} events`}
                              className={n === 0 ? 'bg-panel' : n / max < 0.34 ? 'bg-orange-dark' : n / max < 0.67 ? 'bg-orange' : 'bg-orange-light'}
                            />
                          ))}
                        </div>
                        {timeline.band && (
                          <div
                            className="pointer-events-none absolute -inset-y-1 border-2 border-xp bg-xp/15"
                            style={{
                              left: `${(timeline.band.from / timeline.weeks.length) * 100}%`,
                              width: `${((timeline.band.to - timeline.band.from + 1) / timeline.weeks.length) * 100}%`,
                            }}
                            aria-hidden
                          />
                        )}
                      </div>
                      <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-[11px] text-muted">
                        <span>
                          {nice(c.first_date)} – {nice(c.last_date)}
                        </span>
                        <span>{fmt.format(c.events)} events</span>
                        <span>{fmt.format(c.days_with_data)} days with data</span>
                        <span className={stale ? 'text-orange' : 'text-muted'}>
                          {stale && '▲ '}last updated {ago === null ? '—' : ago === 0 ? 'today' : `${ago} day${ago === 1 ? '' : 's'} ago`}
                          {stale && ' · re-export for newer data'}
                        </span>
                      </div>
                    </div>
                  </li>
                )
              })}
            </ul>
            <div className="flex flex-wrap items-center gap-x-5 gap-y-2 font-mono text-[11px] text-muted">
              <span className="flex items-center gap-1.5">
                <span className="inline-block size-3 border-2 border-xp bg-xp/15" /> overlap window (all sources have data) —
                cross-app comparisons use only this range
              </span>
              <span className="flex items-center gap-1">
                <span className="inline-block size-3 bg-orange-dark" />
                <span className="inline-block size-3 bg-orange" />
                <span className="inline-block size-3 bg-orange-light" /> events per week (low → high)
              </span>
            </div>
          </>
        )}
      </Panel>

      <Panel title="IMPORTS" tag={<span className="font-mono text-[11px] text-muted">REMOVE DELETES THE EVENTS THAT IMPORT ADDED</span>}>
        {!imports.length && <p className="font-mono text-xs text-muted">No imports yet.</p>}
        {[...bySource.entries()].map(([source, rows]) => (
          <section key={source} className="flex flex-col gap-2">
            <h3 className="flex items-center gap-2 text-[9px] text-orange-light uppercase">
              <SourceIcon source={iconFor(source)} size={14} /> {source}
            </h3>
            <ul className="flex flex-col divide-y-2 divide-panel border-2 border-orange-dark bg-bg">
              {rows.map((r) => (
                <ImportLine key={r.import_id} r={r} disabled={busy} onRemove={() => run(() => store.removeImport(r.import_id))} />
              ))}
            </ul>
          </section>
        ))}
      </Panel>

      <Panel title="DANGER ZONE" tag={<span className="font-mono text-[11px] text-muted">{mode === 'demo' ? 'DEMO' : 'MY DATA'} ONLY</span>}>
        {!confirmWipe ? (
          <div className="flex flex-wrap items-center gap-4">
            <button
              className="pixel-btn border-danger bg-danger text-bg hover:bg-danger disabled:border-muted disabled:bg-panel disabled:text-muted"
              onClick={() => setConfirmWipe(true)}
              disabled={busy || !imports.length}
            >
              ✖ WIPE ALL DATA
            </button>
            <span className="font-mono text-xs text-muted">
              Deletes every event, import and setting in the {mode === 'demo' ? 'demo' : 'MY DATA'} database. The other database is not touched.
            </span>
          </div>
        ) : (
          <div className="flex flex-col gap-4 border-2 border-danger bg-danger/10 p-4">
            <p className="font-mono text-xs text-text">
              Delete all {fmt.format(totalEvents)} events from {imports.length} imports in{' '}
              <strong className="text-danger">{mode === 'demo' ? 'DEMO' : 'MY DATA'}</strong>? This cannot be undone (you can re-import the files).
            </p>
            <div className="flex flex-wrap gap-4">
              <button
                className="pixel-btn border-danger bg-danger text-bg hover:bg-danger"
                disabled={busy}
                onClick={() => run(async () => {
                  await store.wipe()
                  setConfirmWipe(false)
                })}
              >
                CONFIRM WIPE
              </button>
              <button className="pixel-btn pixel-btn-secondary" onClick={() => setConfirmWipe(false)} disabled={busy}>
                CANCEL
              </button>
            </div>
          </div>
        )}
      </Panel>
    </div>
  )
}

function ImportLine({ r, onRemove, disabled }: { r: ImportRow; onRemove: () => void; disabled: boolean }) {
  const [confirm, setConfirm] = useState(false)
  const ago = daysAgo(r.imported_at)
  return (
    <li className="flex flex-wrap items-center gap-x-4 gap-y-2 px-3 py-2 font-mono text-xs">
      <span className="min-w-0 flex-1 truncate text-text" title={r.file_name}>
        {r.file_name}
      </span>
      <span className="text-muted">
        {r.min_date ?? '—'} → {r.max_date ?? '—'}
      </span>
      <span className="text-muted" title="new events this import added · duplicates it skipped · events from it still stored">
        +{fmt.format(r.rows_added)} · {fmt.format(r.rows_skipped)} dup · <span className="text-text">{fmt.format(r.events_now)} now</span>
      </span>
      <span className="text-muted">{ago === 0 ? 'today' : `${ago}d ago`}</span>
      {!confirm ? (
        <button
          className="border-2 border-orange-dark px-2 py-1 font-pixel text-[8px] text-orange hover:border-orange"
          onClick={() => setConfirm(true)}
          disabled={disabled}
        >
          REMOVE
        </button>
      ) : (
        <span className="flex gap-2">
          <button
            className="border-2 border-danger bg-danger px-2 py-1 font-pixel text-[8px] text-bg"
            onClick={() => {
              setConfirm(false)
              onRemove()
            }}
            disabled={disabled}
          >
            REMOVE {fmt.format(r.events_now)}?
          </button>
          <button className="border-2 border-muted px-2 py-1 font-pixel text-[8px] text-muted" onClick={() => setConfirm(false)}>
            NO
          </button>
        </span>
      )}
    </li>
  )
}
