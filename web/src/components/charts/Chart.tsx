// ECharts wrapper in the pixel style (docs/design.md "Charts"): square bars, thin muted grid,
// JetBrains Mono, hard-shadow tooltip, a "save as PNG" button, and HTML loading / empty states.
// Charts are created only when scrolled into view and resize with their box.

import { BarChart, HeatmapChart, LineChart, ScatterChart } from 'echarts/charts'
import {
  CalendarComponent,
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkAreaComponent,
  MarkLineComponent,
  TitleComponent,
  ToolboxComponent,
  TooltipComponent,
  VisualMapComponent,
} from 'echarts/components'
import * as echarts from 'echarts/core'
import type { EChartsCoreOption, ECharts } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { colors } from '../../lib/sourceStyle'

echarts.use([
  BarChart, LineChart, ScatterChart, HeatmapChart, GridComponent, TooltipComponent, TitleComponent, LegendComponent,
  DataZoomComponent, MarkAreaComponent, MarkLineComponent, VisualMapComponent, CalendarComponent, ToolboxComponent,
  CanvasRenderer,
])

const MONO = "'JetBrains Mono', ui-monospace, monospace"
let themed = false
function registerTheme() {
  if (themed) return
  themed = true
  const c = colors()
  const axis = {
    axisLine: { lineStyle: { color: c.muted, width: 1 } },
    axisTick: { lineStyle: { color: c.muted } },
    axisLabel: { color: c.muted, fontFamily: MONO, fontSize: 10, hideOverlap: true },
    splitLine: { lineStyle: { color: c.grid, width: 1 } },
    nameTextStyle: { color: c.muted, fontFamily: MONO, fontSize: 10 },
  }
  echarts.registerTheme('selfscope', {
    backgroundColor: 'transparent',
    textStyle: { fontFamily: MONO, color: c.text },
    title: {
      textStyle: { fontFamily: MONO, fontSize: 12, fontWeight: 'bold', color: c.text },
      subtextStyle: { fontFamily: MONO, fontSize: 10, color: c.muted },
    },
    legend: { textStyle: { color: c.muted, fontFamily: MONO, fontSize: 10 }, icon: 'rect', itemWidth: 10, itemHeight: 10 },
    categoryAxis: { ...axis, splitLine: { show: false } },
    valueAxis: axis,
    timeAxis: { ...axis, splitLine: { show: false } },
    bar: { itemStyle: { borderRadius: 0 } },
    line: { symbol: 'rect', symbolSize: 5, lineStyle: { width: 2 } },
    tooltip: {
      backgroundColor: c.bg,
      borderColor: c.orange,
      borderWidth: 2,
      padding: [6, 8],
      textStyle: { color: c.text, fontFamily: MONO, fontSize: 11 },
      extraCssText: `border-radius:0;box-shadow:4px 4px 0 ${c.orangeDark};`,
      axisPointer: { lineStyle: { color: c.orangeLight, type: 'solid' }, shadowStyle: { color: 'rgba(255,122,0,0.08)' } },
    },
  })
}

/** Tooltip row helper: coloured square + label + value. */
export function tipRow(color: string, label: string, value: string) {
  return `<div style="display:flex;gap:8px;justify-content:space-between"><span><span style="display:inline-block;width:8px;height:8px;background:${color};margin-right:6px"></span>${label}</span><b>${value}</b></div>`
}

const SAVE_ICON = 'path://M2 2h12v9l-3 3H2z M4 2v4h7V2 M5 9h6v5H5z'

export interface ChartProps {
  /** The takeaway, e.g. "Sad songs peak at 1 am (52%)". Drawn in the chart so it is in the PNG. */
  title: string
  subtitle?: string
  /** Base option; title / toolbox / theme are added here. Null = still loading. */
  option: EChartsCoreOption | null
  empty?: boolean
  emptyText?: ReactNode
  height?: number
  /** File name for "save as PNG". */
  name: string
  onEvents?: Record<string, (params: any, chart: ECharts) => void> // eslint-disable-line @typescript-eslint/no-explicit-any
  /** Extra top space above the plot (rarely needed; legends are placed automatically). */
  top?: number
  /** Click anywhere on the canvas (pixel coordinates), e.g. to pick a day on a line chart. */
  zrClick?: (x: number, y: number, chart: ECharts) => void
}

export function Chart({ title, subtitle, option, empty, emptyText, height = 260, name, onEvents, top = 0, zrClick }: ChartProps) {
  const box = useRef<HTMLDivElement>(null)
  const chart = useRef<ECharts | null>(null)
  const [visible, setVisible] = useState(false)
  const handlers = useRef(onEvents)
  handlers.current = onEvents
  const zr = useRef(zrClick)
  zr.current = zrClick

  // create lazily when the box scrolls near the viewport
  useEffect(() => {
    const el = box.current
    if (!el || visible) return
    const io = new IntersectionObserver((es) => es.some((e) => e.isIntersecting) && setVisible(true), { rootMargin: '300px' })
    io.observe(el)
    return () => io.disconnect()
  }, [visible])

  useEffect(() => {
    if (!visible || !box.current || !option || empty) return
    registerTheme()
    const c = colors()
    const inst = chart.current ?? echarts.init(box.current, 'selfscope', { renderer: 'canvas' })
    chart.current = inst
    // stack title, subtitle, legend and the y-axis name above the plot without overlaps
    const o = option as { legend?: object; yAxis?: { name?: string } | { name?: string }[]; grid?: { top?: number } }
    const yAxes = Array.isArray(o.yAxis) ? o.yAxis : o.yAxis ? [o.yAxis] : []
    // approximate wrapping of the title (12px bold mono) and subtitle (10px mono) in the box width
    const w = Math.max(160, (box.current.clientWidth || 400) - 44)
    const titleLines = Math.max(1, Math.ceil((title.length * 7.4) / w))
    const subLines = subtitle ? Math.max(1, Math.ceil((subtitle.length * 6.4) / (w + 34))) : 0
    const subTop = titleLines * 17 + 2
    const head = subTop + subLines * 14 + 2
    const legendTop = head + 4
    const gridTop = head + (o.legend ? 26 : 8) + (yAxes.some((y) => y.name) ? 16 : 0) + top
    inst.setOption(
      {
        ...option,
        ...(o.legend ? { legend: { ...o.legend, top: legendTop, left: 0 } } : {}),
        title: [
          { text: title, left: 0, top: 0, textStyle: { width: w, overflow: 'break', lineHeight: 17 } },
          ...(subtitle
            ? [{ text: subtitle, left: 0, top: subTop, textStyle: { width: w + 34, overflow: 'break', lineHeight: 14, fontSize: 10, fontWeight: 'normal', color: c.muted } }]
            : []),
        ],
        toolbox: {
          right: 0,
          top: 0,
          itemSize: 14,
          iconStyle: { borderColor: c.muted, borderWidth: 1.5 },
          emphasis: { iconStyle: { borderColor: c.orange, textFill: c.orange, textFontFamily: MONO } },
          feature: { saveAsImage: { name: `selfscope-${name}`, title: 'Save PNG', icon: SAVE_ICON, backgroundColor: c.panel, pixelRatio: 2 } },
        },
        animation: false,
        grid: { left: 8, right: 12, bottom: 8, containLabel: true, ...o.grid, top: o.grid?.top ?? gridTop },
      },
      { notMerge: true },
    )
    inst.off('click')
    inst.off('datazoom')
    for (const [ev, fn] of Object.entries(handlers.current ?? {})) inst.on(ev, (p: unknown) => fn(p, inst))
    inst.getZr().off('click')
    if (zr.current) inst.getZr().on('click', (e: { offsetX: number; offsetY: number }) => zr.current?.(e.offsetX, e.offsetY, inst))
  }, [visible, option, empty, title, subtitle, top])

  useEffect(() => {
    const el = box.current
    if (!el) return
    const ro = new ResizeObserver(() => chart.current?.resize())
    ro.observe(el)
    return () => {
      ro.disconnect()
      chart.current?.dispose()
      chart.current = null
    }
  }, [])

  // dispose when switching to an empty / loading state, so the next data re-creates it cleanly
  useEffect(() => {
    if ((empty || !option) && chart.current) {
      chart.current.dispose()
      chart.current = null
    }
  }, [empty, option])

  const overlay = !option ? (
    <ChartState title={title}>
      <span className="animate-pixel-blink text-orange-light">LOADING…</span>
    </ChartState>
  ) : empty ? (
    <ChartState title={title}>{emptyText ?? 'No data in this range'}</ChartState>
  ) : null

  return (
    <div className="relative min-w-0" style={{ height }}>
      <div ref={box} className={`absolute inset-0 ${overlay ? 'invisible' : ''}`} role="img" aria-label={title} />
      {overlay}
    </div>
  )
}

function ChartState({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="absolute inset-0 flex flex-col gap-3">
      <p className="font-mono text-xs font-bold text-text">{title}</p>
      <div className="flex flex-1 items-center justify-center border-2 border-dashed border-grid font-mono text-xs text-muted">
        {children}
      </div>
    </div>
  )
}
