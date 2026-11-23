// Data hooks for the dashboard: range-scoped DuckDB queries (src/sql/dashboard.sql) and the
// cached analysis-engine result (src/lib/insights.ts). Both follow the global date range and
// the DEMO / MY DATA mode, and refetch whenever the stored data changes.

import { useEffect, useMemo, useState } from 'react'
import { useApp } from './appState'
import { computeInsights, type AnalysisStep, type EngineResult } from './insights'
import { store } from './store'

/** Run a named query with range_from / range_to (+ extra vars); null while loading. */
export function useRangeQuery<T>(name: string, extra?: Record<string, string | null>): T[] | null {
  const { storeState, resolved } = useApp()
  const [data, setData] = useState<{ key: string; rows: T[] } | null>(null)
  const vars = useMemo(
    () => (resolved ? { range_from: resolved.from, range_to: resolved.to, ...extra } : null),
    [resolved?.from, resolved?.to, JSON.stringify(extra ?? {})], // eslint-disable-line react-hooks/exhaustive-deps
  )
  const key = `${storeState.mode}|${storeState.version}|${JSON.stringify(vars)}`
  useEffect(() => {
    if (storeState.status !== 'ready' || !vars) return
    let live = true
    store.query<T>(name, vars).then(
      (rows) => live && setData({ key, rows }),
      (e) => {
        console.warn(`[dashboard] ${name}`, e)
        if (live) setData({ key, rows: [] })
      },
    )
    return () => {
      live = false
    }
  }, [name, key]) // eslint-disable-line react-hooks/exhaustive-deps
  // keep showing the previous rows while the next ones load (no flashing), but never another mode's
  if (!data || !vars) return null
  if (data.key.split('|')[0] !== String(storeState.mode)) return null
  return data.rows
}

/** Run one query for a single day (drill-down). */
export function useDayQuery<T>(name: string, day: string | null): T[] | null {
  const { storeState } = useApp()
  const [data, setData] = useState<{ day: string; rows: T[] } | null>(null)
  useEffect(() => {
    if (storeState.status !== 'ready' || !day) return
    let live = true
    store.query<T>(name, { day }).then((rows) => live && setData({ day, rows }), () => live && setData({ day, rows: [] }))
    return () => {
      live = false
    }
  }, [name, day, storeState.status, storeState.version, storeState.mode])
  return data && data.day === day ? data.rows : null
}

export interface EngineState {
  res: EngineResult | null
  busy: boolean
  error: string | null
  meta: { cached: boolean; ms: number } | null
  /** Current step of an uncached run (null when idle or served from the cache). */
  step: AnalysisStep | null
}

/** The analysis engine for the current range (cached in DuckDB by range + data fingerprint). */
export function useEngine(): EngineState {
  const { resolved, storeState } = useApp()
  const [state, setState] = useState<EngineState>({ res: null, busy: false, error: null, meta: null, step: null })
  const range = useMemo(() => ({ from: resolved?.from ?? null, to: resolved?.to ?? null }), [resolved?.from, resolved?.to])
  useEffect(() => {
    if (storeState.status !== 'ready' || !storeState.mode || !resolved) {
      setState({ res: null, busy: false, error: null, meta: null, step: null })
      return
    }
    let live = true
    setState((s) => ({ ...s, busy: true, error: null, step: null }))
    computeInsights(storeState.mode, range, (step) => live && setState((s) => ({ ...s, step })))
      .then((r) => live && setState({ res: r.result, busy: false, error: null, meta: { cached: r.cached, ms: r.ms }, step: null }))
      .catch(
        (e) =>
          live &&
          setState((s) => ({ ...s, busy: false, step: null, error: e instanceof Error ? e.message.trim().split('\n').slice(-1)[0] : String(e) })),
      )
    return () => {
      live = false
    }
  }, [storeState.status, storeState.version, storeState.mode, range, resolved])
  return state
}

export interface SourceInfo {
  source: 'spotify' | 'youtube' | 'whatsapp' | 'bank'
  loaded: boolean
  events_in_range: number
  first_date: string | null
  last_date: string | null
}
