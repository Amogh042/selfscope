// App-wide state: current page, data mode (demo / my data) and the global date range.
// Everything is mirrored in the URL hash, e.g. "#/data?mode=demo&range=3m", so a link
// reproduces the view. The mode is also remembered in localStorage.

import { createContext, useCallback, useContext, useEffect, useMemo, useState, useSyncExternalStore, type ReactNode } from 'react'
import { ensureCategorised } from './categorise'
import { store, type Mode, type StoreState } from './store'

export type RangePreset = '30d' | '3m' | '6m' | '1y' | 'all' | 'custom'
export const RANGE_LABEL: Record<RangePreset, string> = {
  '30d': 'Last 30 days',
  '3m': 'Last 3 months',
  '6m': 'Last 6 months',
  '1y': 'Last 1 year',
  all: 'All',
  custom: 'Custom',
}

export interface DateRange {
  preset: RangePreset
  /** Only for preset "custom": YYYY-MM-DD. */
  from?: string
  to?: string
}

interface Bounds {
  first_date: string | null
  last_date: string | null
  events: number
}

interface AppState {
  path: string
  mode: Mode
  setMode: (m: Mode) => Promise<void>
  range: DateRange
  setRange: (r: DateRange) => void
  /** The range resolved to concrete dates (relative presets end at the newest stored day). */
  resolved: { from: string; to: string } | null
  bounds: Bounds | null
  storeState: StoreState
  /** Href for a page that keeps the current mode / range. */
  href: (path: string) => string
}

const Ctx = createContext<AppState | null>(null)
const MODE_KEY = 'selfscope.mode'

function readHash() {
  const [path, query = ''] = (window.location.hash.slice(1) || '/').split('?')
  return { path: path || '/', params: new URLSearchParams(query) }
}

function readMode(params: URLSearchParams): Mode {
  const p = params.get('mode')
  if (p === 'demo' || p === 'real') return p
  try {
    const s = localStorage.getItem(MODE_KEY)
    if (s === 'demo' || s === 'real') return s
  } catch {
    /* storage unavailable */
  }
  return 'real'
}

function readRange(params: URLSearchParams): DateRange {
  const p = params.get('range') as RangePreset | null
  if (p === 'custom') return { preset: 'custom', from: params.get('from') ?? undefined, to: params.get('to') ?? undefined }
  return { preset: p && p in RANGE_LABEL ? p : 'all' }
}

const toDate = (s: string) => new Date(`${s}T00:00:00Z`)
const fmtDate = (d: Date) => d.toISOString().slice(0, 10)

export function resolveRange(r: DateRange, bounds: Bounds | null): { from: string; to: string } | null {
  const today = fmtDate(new Date())
  const end = bounds?.last_date ?? today
  const e = toDate(end)
  const back = (months: number, days = 0) => {
    const d = new Date(e)
    d.setUTCMonth(d.getUTCMonth() - months)
    d.setUTCDate(d.getUTCDate() - days + (months ? 1 : 0))
    return fmtDate(d)
  }
  switch (r.preset) {
    case '30d':
      return { from: back(0, 29), to: end }
    case '3m':
      return { from: back(3), to: end }
    case '6m':
      return { from: back(6), to: end }
    case '1y':
      return { from: back(12), to: end }
    case 'all':
      return bounds?.first_date ? { from: bounds.first_date, to: end } : null
    case 'custom':
      return r.from && r.to ? { from: r.from <= r.to ? r.from : r.to, to: r.from <= r.to ? r.to : r.from } : null
  }
}

export function AppStateProvider({ children }: { children: ReactNode }) {
  const [route, setRoute] = useState(readHash)
  const storeState = useSyncExternalStore(store.subscribe, store.getState)
  const [bounds, setBounds] = useState<Bounds | null>(null)
  const mode = readMode(route.params)
  const range = readRange(route.params)

  useEffect(() => {
    const on = () => {
      setRoute(readHash())
      window.scrollTo(0, 0)
    }
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])

  // Keep the store on the mode in the URL.
  useEffect(() => {
    store.setMode(mode).catch(() => {})
    try {
      localStorage.setItem(MODE_KEY, mode)
    } catch {
      /* ignore */
    }
  }, [mode])

  // Bank rows without a category from the current model (new import, older data, new
  // model version) are categorised in the Python worker. No-op when everything is done.
  useEffect(() => {
    if (storeState.status !== 'ready' || !storeState.mode) return
    void ensureCategorised(storeState.mode)
  }, [storeState.status, storeState.version, storeState.mode])

  // Data bounds for resolving relative ranges; refetched whenever the data changes.
  useEffect(() => {
    if (storeState.status !== 'ready') return
    let live = true
    store.query<Bounds>('bounds').then(([b]) => live && setBounds(b ?? null), () => live && setBounds(null))
    return () => {
      live = false
    }
  }, [storeState.status, storeState.version])

  const replaceParams = useCallback((patch: Record<string, string | null>) => {
    const { path, params } = readHash()
    for (const [k, v] of Object.entries(patch)) {
      if (v === null) params.delete(k)
      else params.set(k, v)
    }
    window.history.replaceState(null, '', `#${path}?${params.toString()}`)
    setRoute(readHash())
  }, [])

  const setMode = useCallback(
    async (m: Mode) => {
      replaceParams({ mode: m })
      await store.setMode(m)
    },
    [replaceParams],
  )

  const setRange = useCallback(
    (r: DateRange) =>
      replaceParams({
        range: r.preset,
        from: r.preset === 'custom' ? (r.from ?? null) : null,
        to: r.preset === 'custom' ? (r.to ?? null) : null,
      }),
    [replaceParams],
  )

  const value = useMemo<AppState>(() => {
    const query = route.params.toString()
    return {
      path: route.path,
      mode,
      setMode,
      range,
      setRange,
      resolved: resolveRange(range, bounds),
      bounds,
      storeState,
      href: (path: string) => `#${path}${query ? `?${query}` : ''}`,
    }
  }, [route, mode, setMode, setRange, bounds, storeState]) // eslint-disable-line react-hooks/exhaustive-deps

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useApp(): AppState {
  const v = useContext(Ctx)
  if (!v) throw new Error('useApp outside AppStateProvider')
  return v
}

/** Run a store query and refetch when the data or mode changes. */
export function useStoreQuery<T>(name: string, vars?: Record<string, string | null>): { data: T[] | null; error: string | null } {
  const { storeState } = useApp()
  const [data, setData] = useState<T[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const key = JSON.stringify(vars ?? {})
  useEffect(() => {
    if (storeState.status !== 'ready') return
    let live = true
    store.query<T>(name, vars).then(
      (d) => {
        if (live) {
          setData(d)
          setError(null)
        }
      },
      (e) => live && setError(e instanceof Error ? e.message : String(e)),
    )
    return () => {
      live = false
    }
  }, [name, key, storeState.status, storeState.version, storeState.mode]) // eslint-disable-line react-hooks/exhaustive-deps
  return { data, error }
}
