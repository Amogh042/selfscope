// Runs the analysis engine (src/python/analysis/engine.py) for the current database and
// date range, with a cache in DuckDB (table `insights`) keyed by range + data fingerprint,
// so returning to the page is instant until the data, periods or settings change.

import { ensureCategorised } from './categorise'
import { ensureEnriched } from './enrich'
import { pythonEngine } from './pythonEngine'
import { ensurePythonModules } from './pythonModules'
import { store, type Mode } from './store'

/** Must match ENGINE_VERSION in src/python/analysis/__init__.py. */
export const ENGINE_VERSION = '4'

export type CalendarStatus = 'holds' | 'borderline' | 'unconfirmed' | 'fades'

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
  /** raw (unadjusted) p-value */
  p?: number
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
  /** Same test after removing weekday + tagged periods (only on raw insights); q = BH over all partial tests (strict). */
  calendar?: { rho: number | null; p?: number | null; q: number | null; status: CalendarStatus; holds: boolean }
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
  calendar_controlled: {
    insights: Insight[]
    weak_signals: Insight[]
    /** 0.05 <= adjusted p < 0.10, |rho| >= 0.1 */
    borderline: Insight[]
    /** the smallest p-values, shown when nothing is significant */
    strongest: Insight[]
    tests: number
    controls: string[]
  }
  matrix: { metrics: string[]; cells: MatrixCell[] }
  metrics: Record<string, MetricMeta>
  trends: Record<string, unknown>
}

const CODE = `from analysis import engine
engine.run_json(payload_json)`

/** Steps of a first (uncached) analysis, for the progress bar. */
export type AnalysisStep = 'python' | 'reading' | 'patterns'
export const ANALYSIS_STEPS: { step: AnalysisStep; label: string }[] = [
  { step: 'python', label: 'Loading Python' },
  { step: 'reading', label: 'Reading data' },
  { step: 'patterns', label: 'Finding patterns' },
]

// Identical requests that arrive while one is running (e.g. the data version changed because
// enrichment finished) share the same Python run.
const running = new Map<string, Promise<string>>()

async function cacheKey(range: { from: string | null; to: string | null }) {
  const [{ fingerprint }] = await store.query<{ fingerprint: string }>('data_fingerprint', { engine_version: ENGINE_VERSION })
  return { fingerprint, key: `${range.from ?? '*'}|${range.to ?? '*'}|${fingerprint}` }
}

export async function computeInsights(
  mode: Mode,
  range: { from: string | null; to: string | null },
  onStep?: (step: AnalysisStep) => void,
): Promise<{ result: EngineResult; cached: boolean; ms: number }> {
  const t0 = performance.now()
  const ms = () => Math.round(performance.now() - t0)
  // a cache hit needs no Python at all
  let { fingerprint, key } = await cacheKey(range)
  const cached = async () => (await store.query<{ payload: string }>('insights_cached', { cache_key: key }))[0]
  let hit = await cached()
  if (hit) return { result: JSON.parse(hit.payload) as EngineResult, cached: true, ms: ms() }

  onStep?.('python')
  await ensurePythonModules()
  onStep?.('reading')
  // label anything not yet categorised / enriched first, so the analysis sees the final data
  await ensureCategorised(mode)
  await ensureEnriched(mode)
  ;({ fingerprint, key } = await cacheKey(range))
  hit = await cached()
  if (hit) return { result: JSON.parse(hit.payload) as EngineResult, cached: true, ms: ms() }

  let job = running.get(key)
  if (!job) {
    job = (async () => {
      const vars = { range_from: range.from, range_to: range.to }
      const [features, [overlap], periods, moodByHour, heatmap] = await Promise.all([
        store.query('features_for_engine'),
        store.query<{ start_date: string | null; end_date: string | null }>('overlap'),
        store.query('periods_list'),
        store.query('spotify_mood_by_hour', vars),
        store.query('heatmap_in_range', vars),
      ])
      onStep?.('patterns')
      const payload = JSON.stringify({ range, overlap: overlap ?? {}, features, periods, mood_by_hour: moodByHour, heatmap })
      const { result } = await pythonEngine.runPython(CODE, { payload_json: payload })
      await store.saveInsights(mode, key, range, fingerprint, result as string)
      return result as string
    })().finally(() => running.delete(key))
    running.set(key, job)
  } else onStep?.('patterns')
  return { result: JSON.parse(await job) as EngineResult, cached: false, ms: ms() }
}
