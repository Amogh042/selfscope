// Runs the analysis engine (src/python/analysis/engine.py) for the current database and
// date range, with a cache in DuckDB (table `insights`) keyed by range + data fingerprint,
// so returning to the page is instant until the data, periods or settings change.

import { pythonEngine } from './pythonEngine'
import { ensurePythonModules } from './pythonModules'
import { store, type Mode } from './store'

/** Must match ENGINE_VERSION in src/python/analysis/__init__.py. */
export const ENGINE_VERSION = '3'

export interface Insight {
  x: string
  y: string
  lag: number
  n: number
  rho: number
  q: number
  strength: 'weak' | 'moderate' | 'strong'
  direction: 'positive' | 'negative'
  sources: string[]
  sentence: string
  stats: string
  note: string
  /** Conditional split behind the sentence (null = plain correlation). */
  detail: {
    kind: 'rate' | 'mean'
    high: number
    low: number
    ratio?: number
    threshold: number
    threshold_text: string
    high_text: string
    low_text: string
    n_high: number
    n_low: number
  } | null
  /** Same test after removing weekday + tagged-period effects (only on raw insights). */
  calendar?: { rho: number | null; p?: number; q: number | null; holds: boolean }
}
export interface MetricMeta {
  source: string
  label: string
  unit: 'min' | 'inr' | 'share' | 'score' | 'count'
}
export interface MatrixCell {
  x: string
  y: string
  n: number
  rho: number
  q: number
  significant: boolean
  rho_c: number | null
  q_c: number | null
  significant_c: boolean
}
export interface PeriodResult {
  period: string
  metric: string
  source: string
  label: string
  direction: 'up' | 'down'
  pct_change: number | null
  n_in: number
  n_out: number
  mean_in: number
  mean_out: number
  strength: string
  q: number
  significant: boolean
  sentence: string
}
export interface AnomalyDay {
  date: string
  sentence: string
  metrics: { metric: string; value: number | null; z: number }[]
}
export interface EngineResult {
  engine_version: string
  range: { from: string | null; to: string | null; days: number }
  correlation_window: { from: string | null; to: string | null; days: number; reason: string | null }
  insights: Insight[]
  weak_signals: Insight[]
  tests: { tests: number; significant: number; weak_signals: number; fdr?: number; min_rho?: number }
  song_mood_by_hour: { sentence: string | null; late_sad_share: number; other_sad_share: number; p: number } | null
  periods: PeriodResult[]
  anomalies: { days: AnomalyDay[]; per_metric: { date: string; metric: string; value: number; z: number }[] }
  calendar_controlled: { insights: Insight[]; weak_signals: Insight[]; tests: number; controls: string[] }
  matrix: { metrics: string[]; cells: MatrixCell[] }
  metrics: Record<string, MetricMeta>
  trends: Record<string, unknown>
}

const CODE = `from analysis import engine
engine.run_json(payload_json)`

export async function computeInsights(
  mode: Mode,
  range: { from: string | null; to: string | null },
): Promise<{ result: EngineResult; cached: boolean; ms: number }> {
  const t0 = performance.now()
  const [{ fingerprint }] = await store.query<{ fingerprint: string }>('data_fingerprint', { engine_version: ENGINE_VERSION })
  const key = `${range.from ?? '*'}|${range.to ?? '*'}|${fingerprint}`
  const [hit] = await store.query<{ payload: string }>('insights_cached', { cache_key: key })
  if (hit) return { result: JSON.parse(hit.payload) as EngineResult, cached: true, ms: Math.round(performance.now() - t0) }

  const vars = { range_from: range.from, range_to: range.to }
  const [features, [overlap], periods, moodByHour, heatmap] = await Promise.all([
    store.query('features_for_engine'),
    store.query<{ start_date: string | null; end_date: string | null }>('overlap'),
    store.query('periods_list'),
    store.query('spotify_mood_by_hour', vars),
    store.query('heatmap_in_range', vars),
  ])
  await ensurePythonModules()
  const payload = JSON.stringify({ range, overlap: overlap ?? {}, features, periods, mood_by_hour: moodByHour, heatmap })
  const { result } = await pythonEngine.runPython(CODE, { payload_json: payload })
  await store.saveInsights(mode, key, range, fingerprint, result as string)
  return { result: JSON.parse(result as string) as EngineResult, cached: false, ms: Math.round(performance.now() - t0) }
}
