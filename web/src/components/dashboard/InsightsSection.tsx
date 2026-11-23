// CROSS-APP INSIGHTS + CORRELATION MATRIX. Ranked engine insights as cards with a mini chart,
// a detail drawer (full scatter + stats), the calendar-control toggle, the weaker tier behind a
// toggle, and a heatmap of all same-day cross-source correlations (greyed = not significant).

import { useMemo, useState } from 'react'
import { useRangeQuery } from '../../lib/dashboard'
import type { CalendarStatus, EngineResult, Insight, MatrixCell, MetricMeta } from '../../lib/insights'
import { byUnit, colors, fmtDay, int, shade, signed, sourceColor, SOURCE_NAME, type Source } from '../../lib/sourceStyle'
import { Chart, tipRow } from '../charts/Chart'
import { Drawer } from './Drawer'

type Daily = Record<string, number | string | boolean | null> & { local_date: string }

const STRENGTH_CLS: Record<string, string> = {
  strong: 'border-xp text-xp',
  moderate: 'border-orange-light text-orange-light',
  weak: 'border-muted text-muted',
}
const LAG = ['same day', 'next day', 'two days later']
const pfmt = (q: number | null | undefined) => (q == null ? '—' : q < 0.001 ? '< 0.001' : q.toFixed(3))

function Badge({ children, cls }: { children: React.ReactNode; cls: string }) {
  return <span className={`border-2 px-1.5 py-0.5 font-pixel text-[7px] leading-relaxed uppercase ${cls}`}>{children}</span>
}

function SourceChips({ sources }: { sources: string[] }) {
  return (
    <span className="flex items-center gap-1">
      {sources.map((s) => (
        <span key={s} className="border-2 px-1 py-0.5 font-pixel text-[7px]" style={{ borderColor: sourceColor(s), color: sourceColor(s) }}>
          {SOURCE_NAME[s as Source]?.toUpperCase() ?? s}
        </span>
      ))}
    </span>
  )
}

/** Pairs (x on day d, y on day d + lag) for the scatter plots. */
function pairs(daily: Daily[] | null, x: string, y: string, lag: number, from?: string | null, to?: string | null) {
  if (!daily) return []
  const idx = new Map(daily.map((r, i) => [r.local_date, i]))
  const out: { d: string; x: number; y: number }[] = []
  for (const r of daily) {
    if ((from && r.local_date < from) || (to && r.local_date > to)) continue
    const t = new Date(`${r.local_date}T00:00:00Z`)
    t.setUTCDate(t.getUTCDate() + lag)
    const j = idx.get(t.toISOString().slice(0, 10))
    const xv = r[x]
    const yv = j == null ? null : daily[j][y]
    if (typeof xv === 'number' && typeof yv === 'number') out.push({ d: r.local_date, x: xv, y: yv })
  }
  return out
}

/** Least-squares line, only to draw the trend (the reported statistic is Spearman's rho). */
function trend(ps: { x: number; y: number }[]) {
  const n = ps.length
  if (n < 3) return null
  const mx = ps.reduce((s, p) => s + p.x, 0) / n
  const my = ps.reduce((s, p) => s + p.y, 0) / n
  const sxx = ps.reduce((s, p) => s + (p.x - mx) ** 2, 0)
  if (!sxx) return null
  const b = ps.reduce((s, p) => s + (p.x - mx) * (p.y - my), 0) / sxx
  const xs = ps.map((p) => p.x)
  const [x0, x1] = [Math.min(...xs), Math.max(...xs)]
  return [
    [x0, my + b * (x0 - mx)],
    [x1, my + b * (x1 - mx)],
  ]
}

const axisScale = (u: string) => (u === 'share' ? 100 : 1)

function MiniBars({ i, meta }: { i: Insight; meta: Record<string, MetricMeta> }) {
  const d = i.detail!
  const col = sourceColor(meta[i.y].source)
  const max = Math.max(Math.abs(d.high), Math.abs(d.low), 1e-9)
  const rows = [
    { k: `≥ ${d.threshold_text}`, v: d.high, t: d.high_text, n: d.n_high, c: col },
    { k: `< ${d.threshold_text}`, v: d.low, t: d.low_text, n: d.n_low, c: shade(col, 0.45) },
  ]
  return (
    <div className="flex flex-col gap-1 border-2 border-grid bg-bg p-2 font-mono text-[10px]">
      <span className="text-muted">
        {meta[i.y].label} {d.kind === 'rate' ? '(share of days)' : '(average)'} by {meta[i.x].label}
        {i.lag ? `, ${LAG[i.lag]}` : ''}
      </span>
      {rows.map((r) => (
        <div key={r.k} className="grid grid-cols-[72px_1fr_56px] items-center gap-2">
          <span className="truncate text-muted" title={`${r.n} days`}>
            {r.k}
          </span>
          <span className="h-3 bg-panel">
            <span className="block h-3" style={{ width: `${Math.max(2, (Math.abs(r.v) / max) * 100)}%`, background: r.c }} />
          </span>
          <span className="text-right text-text tabular-nums">{r.t}</span>
        </div>
      ))}
    </div>
  )
}

function MiniScatter({ i, daily }: { i: Insight; daily: Daily[] | null }) {
  const ps = pairs(daily, i.x, i.y, i.lag)
  const t = trend(ps)
  if (ps.length < 3) return <div className="h-20 border-2 border-grid bg-bg" />
  const xs = ps.map((p) => p.x)
  const ys = ps.map((p) => p.y)
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)]
  const X = (v: number) => 4 + ((v - x0) / (x1 - x0 || 1)) * 192
  const Y = (v: number) => 76 - ((v - y0) / (y1 - y0 || 1)) * 72
  return (
    <svg viewBox="0 0 200 80" className="h-20 w-full border-2 border-grid bg-bg" aria-hidden shapeRendering="crispEdges">
      {ps.map((p) => (
        <rect key={p.d} x={X(p.x) - 1} y={Y(p.y) - 1} width={2} height={2} fill={shade(sourceColor(i.sources[1]), 0.7)} />
      ))}
      {t && <line x1={X(t[0][0])} y1={Y(t[0][1])} x2={X(t[1][0])} y2={Y(t[1][1])} stroke={colors().orange} strokeWidth={2} />}
    </svg>
  )
}

const CAL_BADGE: Record<CalendarStatus, [string, string]> = {
  holds: ['border-xp text-xp', '✓ holds after controlling for calendar'],
  borderline: ['border-orange-light text-orange-light', '~ borderline after controlling for calendar'],
  unconfirmed: ['border-muted text-muted', 'similar size without the calendar, but not significant'],
  fades: ['border-muted text-muted', 'fades when calendar is removed'],
}

function calendarStatus(rho: number | null, rhoC: number | null, q: number | null): CalendarStatus {
  if (rho == null || rhoC == null || q == null || Math.sign(rhoC) !== Math.sign(rho) || Math.abs(rhoC) < 0.1) return 'fades'
  return q < 0.05 ? 'holds' : q < 0.1 ? 'borderline' : 'unconfirmed'
}

function CalendarBadge({ c, cls = '' }: { c: NonNullable<Insight['calendar']>; cls?: string }) {
  const [style, text] = CAL_BADGE[c.status ?? (c.holds ? 'holds' : 'fades')]
  return <Badge cls={`${cls} ${style}`}>{text}</Badge>
}

function InsightCard({ i, rank, meta, daily, controlled, onOpen }: {
  i: Insight
  rank: number
  meta: Record<string, MetricMeta>
  daily: Daily[] | null
  controlled: boolean
  onOpen: () => void
}) {
  return (
    <li>
      <button
        onClick={onOpen}
        className="flex h-full w-full flex-col gap-2 border-2 border-orange bg-panel p-3 text-left shadow-block-sm hover:border-orange-light"
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="font-pixel text-[9px] text-orange">#{rank}</span>
          <span className="flex flex-wrap items-center gap-1.5">
            <SourceChips sources={i.sources} />
            <Badge cls={STRENGTH_CLS[i.strength] ?? STRENGTH_CLS.weak}>{i.strength}</Badge>
          </span>
        </div>
        <p className="text-sm leading-snug text-text">{i.sentence}</p>
        {i.detail && !controlled ? <MiniBars i={i} meta={meta} /> : <MiniScatter i={i} daily={daily} />}
        <p className="font-mono text-[10px] text-muted">{i.stats}</p>
        {!controlled && i.calendar && i.calendar.status !== 'fades' && i.calendar.status !== 'unconfirmed' && (
          <CalendarBadge c={i.calendar} cls="self-start" />
        )}
        {controlled && <Badge cls="self-start border-orange-light text-orange-light">weekday + periods removed</Badge>}
      </button>
    </li>
  )
}

// ---------------------------------------------------------------- detail drawer

export interface Detail {
  insight: Insight
  controlled: boolean
}

function DetailPanel({ d, res, daily, onClose, onDay }: { d: Detail; res: EngineResult; daily: Daily[] | null; onClose: () => void; onDay: (day: string) => void }) {
  const i = d.insight
  const meta = res.metrics
  const mx = meta[i.x]
  const my = meta[i.y]
  const win = res.correlation_window
  const ps = pairs(daily, i.x, i.y, i.lag, win.from, win.to)
  const t = trend(ps.map((p) => ({ x: p.x * axisScale(mx.unit), y: p.y * axisScale(my.unit) })))
  const c = colors()
  const col = sourceColor(my.source)
  const option = {
    grid: { left: 8, right: 16, bottom: 28 },
    tooltip: {
      trigger: 'item',
      formatter: (p: { dataIndex: number; seriesIndex: number }) => {
        if (p.seriesIndex) return ''
        const r = ps[p.dataIndex]
        return `<b>${fmtDay(r.d)}</b>${tipRow(sourceColor(mx.source), mx.label, byUnit(mx.unit, r.x))}${tipRow(col, `${my.label}${i.lag ? ` (+${i.lag}d)` : ''}`, byUnit(my.unit, r.y))}<div style="color:${c.muted}">click for the full day</div>`
      },
    },
    xAxis: { type: 'value', name: mx.label, nameLocation: 'middle', nameGap: 22, scale: true },
    yAxis: { type: 'value', name: my.label, scale: true },
    series: [
      { type: 'scatter', symbol: 'rect', symbolSize: 5, itemStyle: { color: shade(col, 0.75) }, data: ps.map((p) => [p.x * axisScale(mx.unit), p.y * axisScale(my.unit)]) },
      ...(t ? [{ type: 'line', data: t, showSymbol: false, silent: true, lineStyle: { color: c.orange, width: 2 } }] : []),
    ],
  }
  const rows: [string, string][] = [
    ['Spearman rho', signed(i.rho)],
    ['days (n)', int(i.n)],
    ['adjusted p (BH)', pfmt(i.q)],
    ['lag', LAG[i.lag]],
    ['strength', i.strength],
  ]
  if (i.calendar && !d.controlled)
    rows.push(
      ['partial rho, calendar removed', signed(i.calendar.rho)],
      ['adjusted p, calendar removed (BH, all tests)', pfmt(i.calendar.q)],
    )
  return (
    <Drawer title={d.controlled ? 'LINK · CALENDAR REMOVED' : 'LINK DETAIL'} onClose={onClose}>
      <p className="text-base leading-snug text-text">{i.sentence}</p>
      <div className="flex flex-wrap gap-1.5">
        <SourceChips sources={i.sources} />
        <Badge cls={STRENGTH_CLS[i.strength] ?? STRENGTH_CLS.weak}>{i.strength}</Badge>
        {i.q >= 0.05 && <Badge cls="border-muted text-muted">not significant</Badge>}
        {!d.controlled && i.calendar && <CalendarBadge c={i.calendar} />}
      </div>
      {i.detail && <MiniBars i={i} meta={meta} />}
      <Chart
        name={`scatter-${i.x}-${i.y}`}
        title={`${ps.length} days: ${mx.label} vs ${my.label}${i.lag ? ` ${LAG[i.lag]}` : ''}`}
        subtitle="each square = one day (raw values) · orange = straight-line trend"
        option={daily ? option : null}
        empty={!!daily && ps.length < 3}
        height={320}
        onEvents={{ click: (p: { seriesIndex: number; dataIndex: number }) => p.seriesIndex === 0 && ps[p.dataIndex] && onDay(ps[p.dataIndex].d) }}
      />
      <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1 font-mono text-xs">
        {rows.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-muted">{k}</dt>
            <dd className="text-right text-text tabular-nums">{v}</dd>
          </div>
        ))}
      </dl>
      <p className="border-l-2 border-orange-light pl-3 text-xs leading-relaxed text-orange-light">
        Association, not causation. Both may be driven by something else (exams, weekends, holidays).
        {d.controlled
          ? ' Here weekday and tagged-period effects were removed first, so those cannot explain it, but untagged ones (semester breaks, start of month) still can.'
          : ' The adjusted p accounts for all the pairs tested at once.'}
      </p>
      <p className="font-mono text-[10px] text-muted">
        window {fmtDay(win.from)} – {fmtDay(win.to)} (days where every app has data ∩ the selected range)
      </p>
    </Drawer>
  )
}

// ---------------------------------------------------------------- matrix

function Matrix({ res, controlled, onCell }: { res: EngineResult; controlled: boolean; onCell: (c: MatrixCell) => void }) {
  const { metrics, cells } = res.matrix
  const meta = res.metrics
  const option = useMemo(() => {
    if (!metrics.length) return {}
    const c = colors()
    const pos = new Map(metrics.map((m, i) => [m, i]))
    const sig: [number, number, number, number][] = []
    const non: [number, number, number, number][] = []
    cells.forEach((cell, k) => {
      const rho = controlled ? cell.rho_c : cell.rho
      const s = controlled ? cell.significant_c : cell.significant
      if (rho == null) return
      const a = pos.get(cell.x)!
      const b = pos.get(cell.y)!
      for (const [x, y] of [
        [a, b],
        [b, a],
      ])
        (s ? sig : non).push([x, y, +rho.toFixed(2), k])
    })
    const labels = metrics.map((m) => meta[m]?.label ?? m)
    const tip = (p: { value: [number, number, number, number] }) => {
      const cell = cells[p.value[3]]
      const rho = controlled ? cell.rho_c : cell.rho
      const q = controlled ? cell.q_c : cell.q
      return `<b>${meta[cell.x].label} × ${meta[cell.y].label}</b>${tipRow(c.orange, 'rho (same day)', signed(rho))}${tipRow(c.muted, 'adjusted p', pfmt(q))}${tipRow(c.muted, 'days', int(cell.n))}<div style="color:${c.muted}">click for the scatter</div>`
    }
    return {
      grid: { left: 4, right: 8, bottom: 50 },
      tooltip: { formatter: tip },
      xAxis: { type: 'category', data: labels, axisLabel: { rotate: 55, fontSize: 9, width: 130, overflow: 'truncate' }, splitArea: { show: false } },
      yAxis: { type: 'category', data: labels, inverse: true, axisLabel: { fontSize: 9, width: 150, overflow: 'truncate' } },
      visualMap: [
        {
        seriesIndex: 0,
        min: -0.5,
        max: 0.5,
        orient: 'horizontal',
        left: 'center',
        bottom: 0,
        itemHeight: 160,
        itemWidth: 10,
        calculable: false,
        precision: 1,
        inRange: { color: [c.text, shade(c.text, 0.25), c.panel, shade(c.orange, 0.35), c.orange] },
        text: ['+0.5', '−0.5'],
        textStyle: { color: c.muted, fontFamily: 'JetBrains Mono', fontSize: 9 },
        },
        // not significant: one flat grey (a heatmap series always needs a visual map)
        { seriesIndex: 1, show: false, min: -1, max: 1, inRange: { color: [c.grid, c.grid] } },
      ],
      series: [
        {
          type: 'heatmap',
          data: sig,
          label: { show: true, fontSize: 8, fontFamily: 'JetBrains Mono', color: c.bg, formatter: (p: { value: number[] }) => (Math.abs(p.value[2]) >= 0.2 ? p.value[2].toFixed(1).replace('0.', '.') : '') },
          itemStyle: { borderColor: c.bg, borderWidth: 1 },
        },
        { type: 'heatmap', data: non, itemStyle: { borderColor: c.bg, borderWidth: 1 } },
      ],
    }
  }, [metrics, cells, meta, controlled])
  const nSig = cells.filter((x) => (controlled ? x.significant_c : x.significant)).length
  return (
    <div className="overflow-x-auto">
      <div className="min-w-[760px]">
        <Chart
          name={controlled ? 'correlation-matrix-calendar-removed' : 'correlation-matrix'}
          title={metrics.length ? `${nSig} of ${cells.length} same-day cross-app pairs are significant${controlled ? ' after removing the calendar' : ''}` : 'Correlation matrix'}
          subtitle="Spearman rho · orange = rise together, white = move opposite · grey = not significant (BH, 5%) · blank = same app"
          option={option}
          empty={!metrics.length}
          emptyText="Needs at least 30 days where every app has data"
          height={Math.max(360, 120 + metrics.length * 22)}
          onEvents={{ click: (p: { value: number[] }) => p.value && onCell(cells[p.value[3]]) }}
        />
      </div>
    </div>
  )
}

// ---------------------------------------------------------------- section

export function InsightsSection({ res, busy, onDay }: { res: EngineResult | null; busy: boolean; onDay: (d: string) => void }) {
  const [controlled, setControlled] = useState(false)
  const [showWeak, setShowWeak] = useState(false)
  const [showAll, setShowAll] = useState(false)
  const [detail, setDetail] = useState<Detail | null>(null)
  const daily = useRangeQuery<Daily>('dash_daily')

  if (!res)
    return (
      <div className="flex h-48 items-center justify-center border-2 border-dashed border-grid font-mono text-xs">
        <span className={busy ? 'animate-pixel-blink text-orange-light' : 'text-muted'}>{busy ? 'ANALYSING IN THE PYTHON WORKER…' : 'No data in this range'}</span>
      </div>
    )

  const list = controlled ? res.calendar_controlled.insights : res.insights
  const weak = controlled ? [...res.calendar_controlled.weak_signals, ...res.calendar_controlled.borderline] : res.weak_signals
  const shown = showAll ? list : list.slice(0, 12)
  const holds = res.insights.filter((i) => i.calendar?.status === 'holds').length
  const border = res.insights.filter((i) => i.calendar?.status === 'borderline').length
  const cc = res.calendar_controlled
  const open = (insight: Insight) => setDetail({ insight, controlled })

  function openCell(cell: MatrixCell) {
    const pool = controlled ? [...res!.calendar_controlled.insights, ...res!.calendar_controlled.weak_signals] : [...res!.insights, ...res!.weak_signals]
    const hit = pool.find((i) => i.lag === 0 && ((i.x === cell.x && i.y === cell.y) || (i.x === cell.y && i.y === cell.x)))
    if (hit) return open(hit)
    const m = res!.metrics
    const rho = (controlled ? cell.rho_c : cell.rho) ?? 0
    const q = (controlled ? cell.q_c : cell.q) ?? 1
    const a = Math.abs(rho)
    open({
      x: cell.x,
      y: cell.y,
      lag: 0,
      n: cell.n,
      rho,
      q,
      strength: a >= 0.5 ? 'strong' : a >= 0.3 ? 'moderate' : 'weak',
      direction: rho > 0 ? 'positive' : 'negative',
      sources: [m[cell.x].source, m[cell.y].source],
      sentence: `${m[cell.x].label[0].toUpperCase()}${m[cell.x].label.slice(1)} and ${m[cell.y].label} on the same day: rho ${signed(rho)}${(controlled ? cell.significant_c : cell.significant) ? '' : ', which is not significant after correcting for the number of pairs tested'}.`,
      stats: '',
      note: '',
      detail: null,
      calendar: controlled ? undefined : (() => {
        const status = calendarStatus(cell.rho, cell.rho_c, cell.q_c)
        return { rho: cell.rho_c, q: cell.q_c, status, holds: status === 'holds' }
      })(),
    })
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <p className="max-w-2xl font-mono text-[11px] leading-relaxed text-muted">
          Associations between different apps on the same or following days, after correcting for {int(res.tests.tests)} tests at
          once (false-discovery rate 5%). <span className="text-orange-light">Association is not causation.</span>{' '}
          {res.insights.length > 0 &&
            `${holds} of ${res.insights.length} still hold after removing weekday and tagged-period effects${border ? `, ${border} borderline` : ''}.`}
        </p>
        <label className="flex shrink-0 cursor-pointer items-center gap-2 border-2 border-orange-dark bg-bg px-2 py-1.5 font-mono text-[11px] text-text">
          <input type="checkbox" checked={controlled} onChange={(e) => setControlled(e.target.checked)} className="accent-orange" />
          Control for weekday + tagged periods
        </label>
      </div>
      {controlled && (
        <p className="border-l-2 border-orange-light pl-3 font-mono text-[11px] text-orange-light">
          Partial Spearman: each metric's ranks minus their weekday and in/out-of-period means ({res.calendar_controlled.controls.join(', ')}),
          then the same tests over all pairs, with the strict correction (BH over all {int(cc.tests)} tests). What is left is not explained
          by those; untagged changes (holidays, start of month) can still show up, often similarly at every lag.
        </p>
      )}
      {controlled && list.length === 0 && cc.strongest.length > 0 && (
        <div className="flex flex-col gap-2 border-2 border-orange-dark bg-bg p-3">
          <p className="font-pixel text-[9px] text-orange-light">STRONGEST REMAINING LINKS · NOT SIGNIFICANT</p>
          <p className="font-mono text-[11px] text-muted">
            Nothing passes after removing the calendar. These are the smallest p-values left; with {int(cc.tests)} tests, a few this small
            are expected by chance, so none is a finding on its own.
          </p>
          <ul className="flex flex-col gap-1.5">
            {cc.strongest.map((w) => (
              <li key={`${w.x}-${w.y}-${w.lag}`}>
                <button onClick={() => open(w)} className="flex w-full flex-col gap-0.5 border-l-2 border-orange-dark pl-3 text-left hover:border-orange">
                  <span className="text-xs text-text">{w.sentence}</span>
                  <span className="font-mono text-[10px] text-muted">
                    {w.stats} · raw p {pfmt(w.p ?? null)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
      {list.length === 0 ? (
        controlled && cc.strongest.length > 0 ? null : <p className="font-mono text-xs text-muted">
          {res.correlation_window.days ? 'No cross-app association passed the bar for this date range.' : `No cross-app links: ${res.correlation_window.reason ?? 'needs at least 30 days where every app has data'}.`}
        </p>
      ) : (
        <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {shown.map((i, k) => (
            <InsightCard key={`${i.x}-${i.y}-${i.lag}`} i={i} rank={k + 1} meta={res.metrics} daily={daily} controlled={controlled} onOpen={() => open(i)} />
          ))}
        </ul>
      )}
      <div className="flex flex-wrap gap-3">
        {list.length > 12 && (
          <button className="font-pixel text-[9px] text-orange hover:underline" onClick={() => setShowAll((v) => !v)}>
            {showAll ? '▲ SHOW TOP 12' : `▼ SHOW ALL ${list.length}`}
          </button>
        )}
        {weak.length > 0 && (
          <button className="font-pixel text-[9px] text-muted hover:text-text" onClick={() => setShowWeak((v) => !v)} aria-expanded={showWeak}>
            {showWeak ? '▲ HIDE WEAKER SIGNALS' : `▼ SHOW WEAKER SIGNALS (MAY BE CHANCE) · ${weak.length}`}
          </button>
        )}
      </div>
      {showWeak && (
        <div className="flex flex-col gap-2 border-2 border-orange-dark bg-bg p-3">
          <p className="font-mono text-[11px] text-muted">
            Significant but weak (|rho| 0.1–0.2). In the null test (dates shuffled, so no real link exists) about 1–2 of these still
            appeared per run, so treat them as hints. Rare events like food delivery can show a large "x times as likely" with only a
            weak correlation.{controlled && ' Borderline = adjusted p between 0.05 and 0.10.'}
          </p>
          <ul className="flex flex-col gap-1.5">
            {weak.map((w) => (
              <li key={`${w.x}-${w.y}-${w.lag}`}>
                <button onClick={() => open(w)} className="flex w-full flex-col gap-0.5 border-l-2 border-orange-dark pl-3 text-left hover:border-orange">
                  <span className="text-xs text-text">{w.sentence}</span>
                  <span className="font-mono text-[10px] text-muted">
                    {w.stats}
                    {controlled && w.q >= 0.05 && <span className="text-orange-light"> · borderline</span>}
                    {!controlled && w.calendar?.status === 'holds' && <span className="text-xp"> · holds after controlling for calendar</span>}
                    {!controlled && w.calendar?.status === 'borderline' && <span className="text-orange-light"> · borderline after controlling for calendar</span>}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <h3 className="mt-4 text-[11px] text-orange">CORRELATION MATRIX</h3>
      <Matrix res={res} controlled={controlled} onCell={openCell} />

      {detail && (
        <DetailPanel
          d={detail}
          res={res}
          daily={daily}
          onClose={() => setDetail(null)}
          onDay={(day) => {
            setDetail(null)
            onDay(day)
          }}
        />
      )}
    </div>
  )
}
