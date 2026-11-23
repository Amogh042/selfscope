// TIMELINE: daily values + 7-day rolling mean for up to 3 metrics (two units at most -> dual
// axis), tagged periods as shaded bands, unusual days as square markers. Dragging the slider
// sets the global date range; clicking a day opens the day drill-down.

import { useMemo, useState } from 'react'
import { useApp, useStoreQuery } from '../../lib/appState'
import { useRangeQuery } from '../../lib/dashboard'
import type { EngineResult } from '../../lib/insights'
import { byUnit, colors, fmtDay, shade, sourceColor, SOURCE_NAME, SOURCES, UNIT_AXIS, type Source } from '../../lib/sourceStyle'
import { Chart, tipRow } from '../charts/Chart'

interface Row {
  local_date: string
  metric: string
  value: number | null
  rolling7: number | null
}
interface Period {
  label: string
  start_date: string
  end_date: string
}

const DEFAULT = ['spotify_minutes', 'youtube_est_minutes', 'discretionary_spend']
const MAX = 3

export function Timeline({ res, onDay }: { res: EngineResult | null; onDay: (d: string) => void }) {
  const { resolved, setRange } = useApp()
  const rows = useRangeQuery<Row>('dash_timeline')
  const periods = useStoreQuery<Period>('periods_list').data
  const [picked, setPicked] = useState<string[]>(DEFAULT)
  const meta = res?.metrics

  const byMetric = useMemo(() => {
    const m = new Map<string, Row[]>()
    for (const r of rows ?? []) m.set(r.metric, [...(m.get(r.metric) ?? []), r])
    return m
  }, [rows])
  const available = useMemo(
    () => (meta ? Object.keys(meta).filter((k) => (byMetric.get(k) ?? []).some((r) => r.value != null)) : []),
    [meta, byMetric],
  )
  const active = picked.filter((m) => available.includes(m))

  function toggle(m: string) {
    if (!meta) return
    setPicked((cur) => {
      if (cur.includes(m)) return cur.filter((x) => x !== m)
      let next = [...cur.filter((x) => available.includes(x)), m]
      // at most 3 metrics and 2 units: drop the oldest that breaks the rule
      while (next.length > MAX || new Set(next.map((x) => meta[x].unit)).size > 2) next = next.slice(1)
      return next
    })
  }

  const dates = useMemo(() => (byMetric.values().next().value ?? []).map((r: Row) => r.local_date), [byMetric])

  const { option, title } = useMemo(() => {
    if (!rows || !meta || !resolved) return { option: null, title: 'Timeline' }
    if (!active.length || !dates.length) return { option: {}, title: 'Timeline' }
    const c = colors()
    const units = [...new Set(active.map((m) => meta[m].unit))]
    const anomalies = new Map((res?.anomalies.days ?? []).map((d) => [d.date, d.sentence]))
    const seenSource = new Map<string, number>()
    const series: object[] = []
    active.forEach((m, i) => {
      const src = meta[m].source
      const nth = seenSource.get(src) ?? 0
      seenSource.set(src, nth + 1)
      const col = sourceColor(src)
      const yAxisIndex = units.indexOf(meta[m].unit)
      const data = byMetric.get(m) ?? []
      const scale = meta[m].unit === 'share' ? 100 : 1
      const val = (v: number | null) => (v == null ? null : v * scale)
      series.push({
        name: `${meta[m].label} (daily)`,
        type: 'line',
        yAxisIndex,
        data: data.map((r) => val(r.value)),
        showSymbol: false,
        lineStyle: { width: 1, color: shade(col, 0.45), type: nth ? 'dashed' : 'solid' },
        itemStyle: { color: shade(col, 0.45) },
        connectNulls: false,
        ...(i === 0 && periods?.length
          ? {
              markArea: {
                silent: true,
                itemStyle: { color: 'rgba(255,122,0,0.10)' },
                label: { color: c.orangeLight, fontFamily: 'JetBrains Mono', fontSize: 9, position: 'insideTop' },
                data: periods
                  .filter((p) => p.end_date >= dates[0] && p.start_date <= dates[dates.length - 1])
                  .map((p) => [
                    { name: p.label, xAxis: p.start_date < dates[0] ? dates[0] : p.start_date },
                    { xAxis: p.end_date > dates[dates.length - 1] ? dates[dates.length - 1] : p.end_date },
                  ]),
              },
            }
          : {}),
      })
      series.push({
        name: `${meta[m].label} (7-day mean)`,
        type: 'line',
        yAxisIndex,
        data: data.map((r) => val(r.rolling7)),
        showSymbol: false,
        lineStyle: { width: 2.5, color: col, type: nth ? 'dashed' : 'solid' },
        itemStyle: { color: col },
      })
    })
    // unusual days, drawn on the first metric's daily value
    const first = byMetric.get(active[0]) ?? []
    const scale0 = meta[active[0]].unit === 'share' ? 100 : 1
    series.push({
      name: 'Unusual day',
      type: 'scatter',
      yAxisIndex: 0,
      symbol: 'rect',
      symbolSize: 9,
      itemStyle: { color: c.bg, borderColor: c.orange, borderWidth: 2 },
      data: first.map((r) => (anomalies.has(r.local_date) ? (r.value ?? 0) * scale0 : null)),
      z: 10,
    })

    // takeaway: the first metric's average and its peak day
    const vals = first.filter((r) => r.value != null)
    const avg = vals.reduce((s, r) => s + (r.value ?? 0), 0) / Math.max(1, vals.length)
    const peak = vals.reduce((a, r) => ((r.value ?? -Infinity) > (a?.value ?? -Infinity) ? r : a), vals[0])
    const u0 = meta[active[0]].unit
    const title = peak
      ? `${meta[active[0]].label[0].toUpperCase()}${meta[active[0]].label.slice(1)}: ${byUnit(u0, avg)} a day on average, peak ${byUnit(u0, peak.value)} on ${fmtDay(peak.local_date)}`
      : 'Timeline'

    const option = {
      legend: { data: series.map((s) => (s as { name: string }).name).filter((n) => !n.endsWith('(daily)')) },
      grid: { bottom: 52 },
      tooltip: {
        trigger: 'axis',
        formatter: (ps: { dataIndex: number; seriesName: string; color: string; value: number | null }[]) => {
          const i = ps[0]?.dataIndex
          const d = dates[i]
          const per = periods?.filter((p) => p.start_date <= d && d <= p.end_date).map((p) => p.label)
          let html = `<b>${fmtDay(d)}</b>${per?.length ? ` · <span style="color:${c.orangeLight}">${per.join(', ')}</span>` : ''}`
          for (const m of active) {
            const r = (byMetric.get(m) ?? [])[i]
            html += tipRow(sourceColor(meta[m].source), meta[m].label, `${byUnit(meta[m].unit, r?.value)} · 7d ${byUnit(meta[m].unit, r?.rolling7)}`)
          }
          if (anomalies.has(d)) html += `<div style="max-width:280px;white-space:normal;color:${c.orangeLight};margin-top:4px">■ ${anomalies.get(d)}</div>`
          return html + `<div style="color:${c.muted};margin-top:4px">click for the full day</div>`
        },
      },
      xAxis: { type: 'category', data: dates, boundaryGap: false, axisLabel: { formatter: (d: string) => fmtDay(d).replace(/ \d{4}$/, '') } },
      yAxis: units.map((u, i) => ({
        type: 'value',
        name: UNIT_AXIS[u],
        position: i ? 'right' : 'left',
        splitLine: { show: i === 0 },
        axisLabel: { formatter: (v: number) => (u === 'inr' ? `₹${v >= 1000 ? `${v / 1000}k` : v}` : u === 'share' ? `${v}%` : `${v}`) },
      })),
      dataZoom: [
        {
          type: 'slider',
          realtime: false,
          bottom: 6,
          height: 22,
          borderColor: c.orangeDark,
          fillerColor: 'rgba(255,122,0,0.15)',
          handleStyle: { color: c.orange, borderColor: c.orange },
          moveHandleStyle: { color: c.orangeDark },
          textStyle: { color: c.muted, fontFamily: 'JetBrains Mono', fontSize: 9 },
          dataBackground: { lineStyle: { color: c.muted }, areaStyle: { color: c.grid } },
          labelFormatter: (_: number, v: string) => fmtDay(v),
        },
      ],
      series,
    }
    return { option, title }
  }, [rows, meta, resolved, active.join(','), dates, periods, res, byMetric]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2" role="group" aria-label="Timeline metrics">
        {meta &&
          SOURCES.map((s: Source) => {
            const ms = available.filter((m) => meta[m].source === s)
            if (!ms.length) return null
            return (
              <div key={s} className="flex flex-wrap items-center gap-1">
                <span className="mr-1 font-pixel text-[8px]" style={{ color: sourceColor(s) }}>
                  {SOURCE_NAME[s].toUpperCase()}
                </span>
                {ms.map((m) => {
                  const on = active.includes(m)
                  return (
                    <button
                      key={m}
                      onClick={() => toggle(m)}
                      aria-pressed={on}
                      className="border-2 px-1.5 py-0.5 font-mono text-[10px]"
                      style={on ? { borderColor: sourceColor(s), background: sourceColor(s), color: colors().bg } : { borderColor: colors().grid, color: colors().muted }}
                    >
                      {meta[m].label}
                    </button>
                  )
                })}
              </div>
            )
          })}
      </div>
      <p className="font-mono text-[10px] text-muted">
        Pick up to {MAX} metrics (2 units at most). Thin line = each day, thick = 7-day mean, shaded = tagged periods, ■ = unusual
        day. Drag the slider ends to set the date range; click a day to open it.
      </p>
      <Chart
        name="timeline"
        title={title}
        height={380}
        option={option}
        empty={!!option && (!active.length || !dates.length)}
        emptyText={!active.length ? 'Pick a metric above' : 'No data in this range'}
        onEvents={{
          datazoom: (_p: unknown, chart) => {
            const dz = (chart.getOption() as { dataZoom: { startValue: number; endValue: number }[] }).dataZoom[0]
            const from = dates[dz.startValue]
            const to = dates[dz.endValue]
            if (from && to && (from !== dates[0] || to !== dates[dates.length - 1])) setRange({ preset: 'custom', from, to })
          },
        }}
        zrClick={(x, y, chart) => {
          if (!chart.containPixel('grid', [x, y])) return
          const [i] = chart.convertFromPixel({ gridIndex: 0 }, [x, y]) as number[]
          const d = dates[Math.round(i)]
          if (d) onDay(d)
        }}
      />
    </div>
  )
}
