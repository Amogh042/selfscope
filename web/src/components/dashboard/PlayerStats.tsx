// PLAYER STATS: KPI tiles styled as game stat blocks, each with the change vs the previous
// period of the same length and a tiny sparkline. All numbers come from dashboard.sql.

import { useRangeQuery } from '../../lib/dashboard'
import { colors, fmtDay, inr, int, one, sourceColor, catLabel, type Source } from '../../lib/sourceStyle'

interface Kpis {
  days: number
  prev_from: string
  prev_to: string
  listen_h: number | null
  listen_h_prev: number | null
  youtube_h: number | null
  youtube_h_prev: number | null
  sent: number | null
  sent_prev: number | null
  discretionary: number | null
  discretionary_prev: number | null
  listen_prev_full: boolean | null
  youtube_prev_full: boolean | null
  sent_prev_full: boolean | null
  bank_prev_full: boolean | null
}
interface Spark {
  bucket: string
  listen_h: number | null
  youtube_h: number | null
  sent: number | null
  discretionary: number | null
}
interface TopCat {
  category: string
  spend: number
  discretionary: number
  spend_prev: number | null
}

function Sparkline({ values, color }: { values: (number | null)[]; color: string }) {
  const v = values.map((x) => x ?? 0)
  if (v.length < 2 || values.every((x) => x == null)) return <div className="h-7" />
  const max = Math.max(...v, 1e-9)
  const w = 100
  const h = 28
  const pts = v.map((x, i) => `${((i / (v.length - 1)) * w).toFixed(1)},${(h - 2 - (x / max) * (h - 4)).toFixed(1)}`)
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className="h-7 w-full" aria-hidden>
      <polyline points={pts.join(' ')} fill="none" stroke={color} strokeWidth={1.5} vectorEffect="non-scaling-stroke" shapeRendering="crispEdges" />
    </svg>
  )
}

function Delta({ cur, prev, full, prevText }: { cur: number | null; prev: number | null; full: boolean | null; prevText: string }) {
  if (cur == null || prev == null || !full)
    return <span className="font-mono text-[10px] text-muted">no earlier period to compare</span>
  if (prev === 0) return <span className="font-mono text-[10px] text-muted">was 0 {prevText}</span>
  const d = cur / prev - 1
  const flat = Math.abs(d) < 0.005
  return (
    <span className="font-mono text-[10px] text-muted" title={prevText}>
      <span className={flat ? 'text-muted' : d > 0 ? 'text-orange-light' : 'text-text'}>
        {flat ? '■' : d > 0 ? '▲' : '▼'} {Math.abs(d * 100).toFixed(0)}%
      </span>{' '}
      vs prev. {prevText.split(' ')[0]}
    </span>
  )
}

function Tile({
  label,
  source,
  value,
  unit,
  children,
  spark,
}: {
  label: string
  source: Source
  value: string
  unit?: string
  children: React.ReactNode
  spark?: (number | null)[]
}) {
  const col = sourceColor(source)
  return (
    <div className="flex min-w-0 flex-col gap-1.5 border-2 bg-bg p-3" style={{ borderColor: col, boxShadow: `4px 4px 0 0 ${colors().orangeDark}` }}>
      <div className="flex items-center gap-2">
        <span className="inline-block size-2" style={{ background: col }} aria-hidden />
        <span className="truncate font-pixel text-[8px] leading-relaxed text-muted">{label}</span>
      </div>
      <div className="flex items-baseline gap-1 font-mono tabular-nums">
        <span className="truncate text-2xl font-bold text-text">{value}</span>
        {unit && <span className="text-xs text-muted">{unit}</span>}
      </div>
      {children}
      {spark && <Sparkline values={spark} color={col} />}
    </div>
  )
}

export function PlayerStats({ me }: { me: string | null }) {
  const k = useRangeQuery<Kpis>('dash_kpis')?.[0]
  const spark = useRangeQuery<Spark>('dash_spark')
  const top = useRangeQuery<TopCat>('dash_top_category')
  if (!k || !spark || !top)
    return (
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-5">
        {Array.from({ length: 5 }, (_, i) => (
          <div key={i} className="h-[136px] animate-pixel-blink border-2 border-orange-dark bg-bg" />
        ))}
      </div>
    )
  const prevText = `${k.days} days (${fmtDay(k.prev_from)} – ${fmtDay(k.prev_to)})`
  const t = top[0]
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-5">
      <Tile label="HOURS LISTENED" source="spotify" value={one(k.listen_h)} unit="h" spark={spark.map((s) => s.listen_h)}>
        <Delta cur={k.listen_h} prev={k.listen_h_prev} full={k.listen_prev_full} prevText={prevText} />
      </Tile>
      <Tile label="YOUTUBE HOURS" source="youtube" value={one(k.youtube_h)} unit="h est." spark={spark.map((s) => s.youtube_h)}>
        <Delta cur={k.youtube_h} prev={k.youtube_h_prev} full={k.youtube_prev_full} prevText={prevText} />
      </Tile>
      <Tile label="MESSAGES SENT" source="whatsapp" value={me ? int(k.sent) : '—'} spark={me ? spark.map((s) => s.sent) : undefined}>
        {me ? (
          <Delta cur={k.sent} prev={k.sent_prev} full={k.sent_prev_full} prevText={prevText} />
        ) : (
          <span className="font-mono text-[10px] text-muted">pick your name on the import screen</span>
        )}
      </Tile>
      <Tile label="DISCRETIONARY" source="bank" value={inr(k.discretionary)} spark={spark.map((s) => s.discretionary)}>
        <Delta cur={k.discretionary} prev={k.discretionary_prev} full={k.bank_prev_full} prevText={prevText} />
      </Tile>
      <Tile label="TOP CATEGORY" source="bank" value={t ? catLabel(t.category) : '—'}>
        {t ? (
          <>
            <span className="font-mono text-[11px] text-text tabular-nums">
              {inr(t.spend)} · {((t.spend / t.discretionary) * 100).toFixed(0)}% of discretionary
            </span>
            <Delta cur={t.spend} prev={t.spend_prev} full={k.bank_prev_full} prevText={prevText} />
          </>
        ) : (
          <span className="font-mono text-[10px] text-muted">no categorised spend in range</span>
        )}
      </Tile>
    </div>
  )
}
