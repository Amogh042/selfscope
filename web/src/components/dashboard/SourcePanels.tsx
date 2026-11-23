// SOURCE PANELS: Music / YouTube / Chats / Money, a 2x2 grid on wide screens and tabs on phones.
// Every chart title states the takeaway, computed from the rows dashboard.sql returns.

import { useMemo, useState, type ReactNode } from 'react'
import { useApp } from '../../lib/appState'
import { useRangeQuery, type SourceInfo } from '../../lib/dashboard'
import {
  colors,
  fmtDay,
  fmtDayShort,
  inr,
  int,
  language,
  minutes,
  one,
  pct,
  shade,
  SHADES,
  signed,
  SOURCE_NAME,
  sourceColor,
  catLabel,
  type Source,
} from '../../lib/sourceStyle'
import { Chart, tipRow } from '../charts/Chart'

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const hourLabel = (h: number) => `${String(h).padStart(2, '0')}:00`

// ---------------------------------------------------------------- chart builders

/** Horizontal bars, biggest on top. */
function hbar(items: { label: string; value: number; tip?: string }[], color: string, fmt: (v: number) => string, axis: string) {
  const rows = [...items].reverse()
  return {
    grid: { left: 4, right: 16, bottom: 22 },
    tooltip: {
      trigger: 'item',
      formatter: (p: { dataIndex: number }) => {
        const r = rows[p.dataIndex]
        return `<b>${r.label}</b>${tipRow(color, axis, fmt(r.value))}${r.tip ?? ''}`
      },
    },
    xAxis: { type: 'value', name: axis, nameLocation: 'middle', nameGap: 22, splitNumber: 4, axisLabel: { formatter: (v: number) => (v >= 1000 ? `${fmt(v / 1000).replace(/^₹/, '₹')}k`.replace('kk', 'k') : fmt(v)) } },
    yAxis: {
      type: 'category',
      data: rows.map((r) => r.label),
      axisLabel: { width: 120, overflow: 'truncate' },
    },
    series: [{ type: 'bar', data: rows.map((r) => r.value), itemStyle: { color }, barMaxWidth: 16 }],
  }
}

/** 100% stacked weekly bars. `cats` biggest first get the source colour's shades; the rest are "other". */
function stackedShare(
  rows: { week: string; cat: string; share: number; raw: number }[],
  base: string,
  rawFmt: (v: number) => string,
  maxCats = 4,
) {
  const totals = new Map<string, number>()
  for (const r of rows) totals.set(r.cat, (totals.get(r.cat) ?? 0) + r.raw)
  const ranked = [...totals.entries()].sort((a, b) => b[1] - a[1]).map(([k]) => k)
  const keep = ranked.slice(0, ranked.length > maxCats ? maxCats - 1 : maxCats)
  const cats = ranked.length > keep.length ? [...keep, 'other'] : keep
  const key = (c: string) => (keep.includes(c) ? c : 'other')
  const weeks = [...new Set(rows.map((r) => r.week))].sort()
  const grid = new Map<string, { share: number; raw: number }>()
  for (const r of rows) {
    const k = `${r.week}|${key(r.cat)}`
    const g = grid.get(k) ?? { share: 0, raw: 0 }
    grid.set(k, { share: g.share + r.share, raw: g.raw + r.raw })
  }
  const colorOf = (c: string, i: number) => (c === 'other' ? shade(colors().muted, 0.45) : shade(base, SHADES[i] ?? 0.2))
  return {
    legend: { data: cats.map(catLabel) },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (ps: { dataIndex: number }[]) => {
        const w = weeks[ps[0].dataIndex]
        return (
          `<b>Week of ${fmtDay(w)}</b>` +
          cats
            .map((c, i) => {
              const g = grid.get(`${w}|${c}`)
              return g ? tipRow(colorOf(c, i), catLabel(c), `${pct(g.share)} · ${rawFmt(g.raw)}`) : ''
            })
            .join('')
        )
      },
    },
    xAxis: { type: 'category', data: weeks, axisLabel: { formatter: fmtDayShort } },
    yAxis: { type: 'value', max: 100, name: '% of week', axisLabel: { formatter: '{value}%' } },
    series: cats.map((c, i) => ({
      name: catLabel(c),
      type: 'bar',
      stack: 'share',
      barCategoryGap: '15%',
      itemStyle: { color: colorOf(c, i), borderColor: colors().panel, borderWidth: 1 },
      data: weeks.map((w) => +(((grid.get(`${w}|${c}`)?.share ?? 0) * 100).toFixed(2))),
    })),
  }
}

// ---------------------------------------------------------------- frame

function SourcePanel({ source, info, children }: { source: Source; info: SourceInfo | undefined; children: ReactNode }) {
  const { href } = useApp()
  const col = sourceColor(source)
  return (
    <section className="pixel-panel flex min-w-0 flex-col" style={{ borderColor: col }}>
      <header className="flex items-center justify-between gap-3 border-b-2 bg-bg/60 px-4 py-3" style={{ borderColor: col }}>
        <h3 className="flex items-center gap-2 text-[11px]" style={{ color: col }}>
          <span className="inline-block size-2.5" style={{ background: col }} aria-hidden />
          {SOURCE_NAME[source].toUpperCase()}
        </h3>
        {info?.loaded && (
          <span className="font-mono text-[10px] text-muted">{int(info.events_in_range)} events in range</span>
        )}
      </header>
      <div className="flex flex-1 flex-col gap-6 p-4">
        {!info ? (
          <div className="h-40 animate-pixel-blink border-2 border-dashed border-grid" />
        ) : !info.loaded ? (
          <div className="flex min-h-48 flex-1 flex-col items-center justify-center gap-3 border-2 border-dashed p-6 text-center" style={{ borderColor: col }}>
            <span className="font-pixel text-[10px] leading-relaxed" style={{ color: col }}>
              🔒 LOCKED
            </span>
            <p className="font-mono text-xs text-muted">Import {SOURCE_NAME[source]} to unlock this panel.</p>
            <a href={href('/import')} className="pixel-btn">
              IMPORT
            </a>
          </div>
        ) : (
          children
        )}
      </div>
    </section>
  )
}

// ---------------------------------------------------------------- music

function MusicPanel() {
  const c = sourceColor('spotify')
  const artists = useRangeQuery<{ artist: string; plays: number; minutes: number }>('music_top_artists')
  const moods = useRangeQuery<{ week: string; mood: string; plays: number; share: number }>('music_mood_weekly')
  const langs = useRangeQuery<{ language: string; plays: number; share: number }>('music_language')
  const sad = useRangeQuery<{ hour: number; known_plays: number; sad_share: number }>('music_sad_by_hour')

  const a = useMemo(() => {
    if (!artists) return null
    const top = artists[0]
    return {
      title: top ? `${top.artist} is your most-played artist (${int(top.plays)} plays)` : 'Top artists',
      option: hbar(artists.map((r) => ({ label: r.artist, value: r.plays, tip: tipRow(c, 'listened', minutes(r.minutes)) })), c, int, 'plays'),
    }
  }, [artists, c])

  const m = useMemo(() => {
    if (!moods) return null
    const total = moods.reduce((s, r) => s + r.plays, 0)
    const sadPlays = moods.filter((r) => r.mood === 'sad').reduce((s, r) => s + r.plays, 0)
    const peak = moods.filter((r) => r.mood === 'sad').sort((x, y) => y.share - x.share)[0]
    return {
      title: total
        ? `Sad songs are ${pct(sadPlays / total)} of plays${peak ? `, peaking at ${pct(peak.share)} in the week of ${fmtDayShort(peak.week)}` : ''}`
        : 'Song mood per week',
      option: stackedShare(moods.map((r) => ({ week: r.week, cat: r.mood, share: r.share, raw: r.plays })), c, (v) => `${int(v)} plays`),
    }
  }, [moods, c])

  const l = useMemo(() => {
    if (!langs) return null
    const top = langs[0]
    return {
      title: top ? `${language(top.language)} makes up ${pct(top.share)} of your plays` : 'Languages',
      option: hbar(langs.map((r) => ({ label: language(r.language), value: r.share * 100, tip: tipRow(c, 'plays', int(r.plays)) })), c, (v) => `${v.toFixed(0)}%`, '% of plays'),
    }
  }, [langs, c])

  const s = useMemo(() => {
    if (!sad) return null
    const rows = Array.from({ length: 24 }, (_, h) => sad.find((r) => r.hour === h) ?? { hour: h, known_plays: 0, sad_share: null as number | null })
    const peak = sad.filter((r) => r.known_plays >= 20).sort((x, y) => y.sad_share - x.sad_share)[0]
    const late = new Set([23, 0, 1, 2])
    return {
      title: peak ? `Sad songs peak around ${hourLabel(peak.hour)} (${pct(peak.sad_share)} of known-mood plays)` : 'Sad-song share by hour',
      option: {
        tooltip: {
          trigger: 'item',
          formatter: (p: { dataIndex: number }) => {
            const r = rows[p.dataIndex]
            return `<b>${hourLabel(r.hour)}–${String(r.hour).padStart(2, '0')}:59</b>${tipRow(c, 'sad share', pct(r.sad_share))}${tipRow(c, 'known-mood plays', int(r.known_plays))}`
          },
        },
        xAxis: { type: 'category', data: rows.map((r) => String(r.hour).padStart(2, '0')), name: 'hour' },
        yAxis: { type: 'value', name: '% sad', axisLabel: { formatter: '{value}%' } },
        series: [
          {
            type: 'bar',
            barCategoryGap: '20%',
            data: rows.map((r) => ({
              value: r.sad_share == null ? null : +(r.sad_share * 100).toFixed(1),
              itemStyle: { color: late.has(r.hour) ? c : shade(c, 0.5) },
            })),
          },
        ],
      },
    }
  }, [sad, c])

  return (
    <>
      <Chart name="music-top-artists" title={a?.title ?? 'Top artists'} option={a?.option ?? null} empty={artists?.length === 0} height={300} />
      <Chart name="music-mood-weekly" title={m?.title ?? 'Song mood per week'} subtitle="share of plays with a known mood (unknown songs left out)" option={m?.option ?? null} empty={moods?.length === 0} />
      <div className="grid gap-6 lg:grid-cols-2">
        <Chart name="music-language" title={l?.title ?? 'Languages'} option={l?.option ?? null} empty={langs?.length === 0} height={220} />
        <Chart name="music-sad-by-hour" title={s?.title ?? 'Sad-song share by hour'} subtitle="bright = late night (23:00–02:59)" option={s?.option ?? null} empty={sad?.length === 0} height={220} />
      </div>
    </>
  )
}

// ---------------------------------------------------------------- youtube

function YouTubePanel() {
  const c = sourceColor('youtube')
  const topics = useRangeQuery<{ week: string; topic: string; minutes: number; share: number }>('yt_topic_weekly')
  const heat = useRangeQuery<{ weekday: number; hour: number; videos: number }>('yt_heatmap')
  const chans = useRangeQuery<{ channel: string; videos: number; minutes: number; topic: string }>('yt_top_channels')

  const t = useMemo(() => {
    if (!topics) return null
    const tot = new Map<string, number>()
    for (const r of topics) tot.set(r.topic, (tot.get(r.topic) ?? 0) + r.minutes)
    const all = [...tot.values()].reduce((s, v) => s + v, 0)
    const [top] = [...tot.entries()].sort((a, b) => b[1] - a[1])
    return {
      title: top ? `${catLabel(top[0])} is your top topic (${pct(top[1] / all)} of estimated watch time)` : 'Topics per week',
      option: stackedShare(topics.map((r) => ({ week: r.week, cat: r.topic, share: r.share, raw: r.minutes })), c, minutes),
    }
  }, [topics, c])

  const h = useMemo(() => {
    if (!heat) return null
    const max = Math.max(1, ...heat.map((r) => r.videos))
    const top = [...heat].sort((a, b) => b.videos - a.videos)[0]
    return {
      title: top ? `You watch most on ${WEEKDAYS[top.weekday]} around ${hourLabel(top.hour)} (${int(top.videos)} videos)` : 'When you watch',
      option: {
        grid: { bottom: 44 },
        tooltip: {
          formatter: (p: { value: [number, number, number] }) =>
            `<b>${WEEKDAYS[p.value[1]]} ${hourLabel(p.value[0])}</b>${tipRow(c, 'videos', int(p.value[2]))}`,
        },
        xAxis: { type: 'category', data: Array.from({ length: 24 }, (_, i) => String(i).padStart(2, '0')), name: 'hour', splitArea: { show: false } },
        yAxis: { type: 'category', data: WEEKDAYS, inverse: true },
        visualMap: {
          min: 0,
          max,
          orient: 'horizontal',
          left: 'center',
          bottom: 0,
          itemHeight: 120,
          itemWidth: 10,
          calculable: false,
          inRange: { color: [colors().panel, c] },
          textStyle: { color: colors().muted, fontFamily: 'JetBrains Mono', fontSize: 9 },
          text: [`${max} videos`, '0'],
        },
        series: [{ type: 'heatmap', data: heat.map((r) => [r.hour, r.weekday, r.videos]), itemStyle: { borderColor: colors().bg, borderWidth: 1 } }],
      },
    }
  }, [heat, c])

  const ch = useMemo(() => {
    if (!chans) return null
    const top = chans[0]
    return {
      title: top ? `${top.channel} leads your watch time (${minutes(top.minutes)})` : 'Top channels',
      option: hbar(
        chans.map((r) => ({ label: r.channel, value: r.minutes, tip: tipRow(c, 'videos', int(r.videos)) + tipRow(c, 'topic', catLabel(r.topic)) })),
        c,
        (v) => `${Math.round(v)}`,
        'est. min',
      ),
    }
  }, [chans, c])

  return (
    <>
      <Chart name="youtube-topics-weekly" title={t?.title ?? 'Topics per week'} subtitle="share of estimated watch time, ads excluded" option={t?.option ?? null} empty={topics?.length === 0} />
      <Chart name="youtube-heatmap" title={h?.title ?? 'When you watch'} option={h?.option ?? null} empty={heat?.length === 0} height={280} />
      <Chart name="youtube-top-channels" title={ch?.title ?? 'Top channels'} option={ch?.option ?? null} empty={chans?.length === 0} height={300} />
    </>
  )
}

// ---------------------------------------------------------------- chats

function ChatsPanel({ me }: { me: string | null }) {
  const c = sourceColor('whatsapp')
  const { href } = useApp()
  const chats = useRangeQuery<{ week: string; chat: string; messages: number }>('chat_weekly_top5')
  const mood = useRangeQuery<{ week: string; messages: number; mean: number; lo: number | null; hi: number | null }>('chat_sentiment_weekly')
  const late = useRangeQuery<{ week: string; messages: number; late_share: number }>('chat_late_weekly')

  const pc = useMemo(() => {
    if (!chats) return null
    const tot = new Map<string, number>()
    for (const r of chats) tot.set(r.chat, (tot.get(r.chat) ?? 0) + r.messages)
    const names = [...tot.entries()].sort((a, b) => b[1] - a[1]).map(([k]) => k)
    const weeks = [...new Set(chats.map((r) => r.week))].sort()
    const v = new Map(chats.map((r) => [`${r.week}|${r.chat}`, r.messages]))
    const dashes = ['solid', 'solid', 'dashed', 'dotted', 'dashed'] as const
    return {
      title: names.length ? `${names[0]} is your busiest chat (${int(tot.get(names[0]))} messages)` : 'Messages per chat',
      option: {
        legend: { data: names },
        tooltip: { trigger: 'axis', formatter: (ps: { dataIndex: number; color: string; seriesName: string; value: number }[]) => `<b>Week of ${fmtDay(weeks[ps[0].dataIndex])}</b>` + ps.map((p) => tipRow(p.color, p.seriesName, int(p.value))).join('') },
        xAxis: { type: 'category', data: weeks, boundaryGap: false, axisLabel: { formatter: fmtDayShort } },
        yAxis: { type: 'value', name: 'messages / week', nameTextStyle: { align: 'left' } },
        series: names.map((n, i) => ({
          name: n,
          type: 'line',
          showSymbol: false,
          data: weeks.map((w) => v.get(`${w}|${n}`) ?? 0),
          lineStyle: { width: 2, type: dashes[i] },
          itemStyle: { color: shade(c, [1, 0.75, 0.55, 0.4, 0.3][i]) },
        })),
      },
    }
  }, [chats, c])

  const md = useMemo(() => {
    if (!mood) return null
    const weeks = mood.map((r) => r.week)
    const all = mood.reduce((s, r) => s + r.messages, 0)
    const avg = mood.reduce((s, r) => s + r.mean * r.messages, 0) / Math.max(1, all)
    const low = mood.filter((r) => r.messages >= 10).sort((a, b) => a.mean - b.mean)[0]
    return {
      title: low ? `Your messages average ${signed(avg)}; lowest in the week of ${fmtDayShort(low.week)} (${signed(low.mean)})` : 'Your message mood',
      option: {
        tooltip: {
          trigger: 'axis',
          formatter: (ps: { dataIndex: number }[]) => {
            const r = mood[ps[0].dataIndex]
            return `<b>Week of ${fmtDay(r.week)}</b>${tipRow(c, 'mean mood', signed(r.mean))}${tipRow(shade(c, 0.4), '95% band', `${signed(r.lo)} … ${signed(r.hi)}`)}${tipRow(c, 'your messages', int(r.messages))}`
          },
        },
        xAxis: { type: 'category', data: weeks, boundaryGap: false, axisLabel: { formatter: fmtDayShort } },
        yAxis: { type: 'value', name: 'mood −1…1', scale: true },
        series: [
          { name: 'lo', type: 'line', stack: 'band', data: mood.map((r) => r.lo ?? r.mean), lineStyle: { opacity: 0 }, showSymbol: false, silent: true },
          {
            name: 'band',
            type: 'line',
            stack: 'band',
            data: mood.map((r) => (r.hi ?? r.mean) - (r.lo ?? r.mean)),
            lineStyle: { opacity: 0 },
            areaStyle: { color: shade(c, 0.35) },
            showSymbol: false,
            silent: true,
          },
          {
            name: 'mean',
            type: 'line',
            data: mood.map((r) => r.mean),
            showSymbol: false,
            lineStyle: { width: 2, color: c },
            itemStyle: { color: c },
            markLine: { silent: true, symbol: 'none', label: { show: false }, lineStyle: { color: colors().muted, type: 'dashed', width: 1 }, data: [{ yAxis: 0 }] },
          },
        ],
      },
    }
  }, [mood, c])

  const lt = useMemo(() => {
    if (!late) return null
    const all = late.reduce((s, r) => s + r.messages, 0)
    const share = late.reduce((s, r) => s + r.late_share * r.messages, 0) / Math.max(1, all)
    const peak = late.filter((r) => r.messages >= 20).sort((a, b) => b.late_share - a.late_share)[0]
    return {
      title: peak ? `${pct(share)} of messages are late at night; peak ${pct(peak.late_share)} in the week of ${fmtDayShort(peak.week)}` : 'Late-night chatting',
      option: {
        tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: (ps: { dataIndex: number }[]) => { const r = late[ps[0].dataIndex]; return `<b>Week of ${fmtDay(r.week)}</b>${tipRow(c, 'late night (23–03)', pct(r.late_share))}${tipRow(c, 'messages', int(r.messages))}` } },
        xAxis: { type: 'category', data: late.map((r) => r.week), axisLabel: { formatter: fmtDayShort } },
        yAxis: { type: 'value', name: '% late night', axisLabel: { formatter: '{value}%' } },
        series: [{ type: 'bar', barCategoryGap: '20%', data: late.map((r) => +(r.late_share * 100).toFixed(1)), itemStyle: { color: c } }],
      },
    }
  }, [late, c])

  return (
    <>
      <Chart name="chats-per-chat" title={pc?.title ?? 'Messages per chat'} subtitle="the 5 busiest chats · counts only, no message text" option={pc?.option ?? null} empty={chats?.length === 0} />
      <Chart
        name="chats-mood"
        title={me ? (md?.title ?? 'Your message mood') : 'Your message mood'}
        subtitle="weekly mean of your own messages ± 95% band · lexicon scorer (~79% accurate on the demo)"
        option={me ? (md?.option ?? null) : {}}
        empty={!me || mood?.length === 0}
        emptyText={
          !me ? (
            <span>
              Pick your own name on the <a className="text-orange underline" href={href('/import')}>import screen</a> to see your mood.
            </span>
          ) : undefined
        }
      />
      <Chart name="chats-late-night" title={lt?.title ?? 'Late-night chatting'} option={lt?.option ?? null} empty={late?.length === 0} height={240} />
    </>
  )
}

// ---------------------------------------------------------------- money

interface CatRow {
  category: string
  spend: number
  txns: number
  share: number
  discretionary: boolean
}

function MoneyPanel({ onDay }: { onDay: (d: string) => void }) {
  const c = sourceColor('bank')
  const { resolved } = useApp()
  const monthly = useRangeQuery<{ month: string; category: string; spend: number }>('money_monthly_category')
  const table = useRangeQuery<CatRow>('money_category_table')
  const daily = useRangeQuery<{ local_date: string; spend: number }>('money_daily_discretionary')
  const payees = useRangeQuery<{ payee: string; category: string; spend: number; txns: number }>('money_top_payees')

  const mo = useMemo(() => {
    if (!monthly) return null
    const tot = new Map<string, number>()
    for (const r of monthly) tot.set(r.category, (tot.get(r.category) ?? 0) + r.spend)
    const ranked = [...tot.entries()].sort((a, b) => b[1] - a[1]).map(([k]) => k)
    const keep = ranked.slice(0, ranked.length > 6 ? 5 : 6)
    const cats = ranked.length > keep.length ? [...keep, 'rest'] : keep
    const key = (x: string) => (keep.includes(x) ? x : 'rest')
    const months = [...new Set(monthly.map((r) => r.month))].sort()
    const v = new Map<string, number>()
    for (const r of monthly) v.set(`${r.month}|${key(r.category)}`, (v.get(`${r.month}|${key(r.category)}`) ?? 0) + r.spend)
    const all = [...tot.values()].reduce((s, x) => s + x, 0)
    const colorOf = (x: string, i: number) => (x === 'rest' ? shade(colors().muted, 0.45) : shade(c, [1, 0.72, 0.52, 0.36, 0.24, 0.16][i]))
    const mLabel = (m: string) => new Date(`${m}T00:00:00Z`).toLocaleDateString('en-GB', { month: 'short', year: '2-digit', timeZone: 'UTC' })
    return {
      title: ranked.length ? `${inr(all)} went out in ${months.length} month${months.length === 1 ? '' : 's'}; ${catLabel(ranked[0])} is the largest (${pct(tot.get(ranked[0])! / all)})` : 'Monthly spend',
      option: {
        legend: { data: cats.map((x) => (x === 'rest' ? 'Rest' : catLabel(x))) },
        tooltip: {
          trigger: 'axis',
          axisPointer: { type: 'shadow' },
          formatter: (ps: { dataIndex: number }[]) => {
            const m = months[ps[0].dataIndex]
            const sum = cats.reduce((s, x) => s + (v.get(`${m}|${x}`) ?? 0), 0)
            return `<b>${mLabel(m)} · ${inr(sum)}</b>` + cats.map((x, i) => tipRow(colorOf(x, i), x === 'rest' ? 'Rest' : catLabel(x), inr(v.get(`${m}|${x}`) ?? 0))).join('')
          },
        },
        xAxis: { type: 'category', data: months, axisLabel: { formatter: mLabel } },
        yAxis: { type: 'value', name: '₹ / month', axisLabel: { formatter: (x: number) => `₹${x >= 1000 ? `${x / 1000}k` : x}` } },
        series: cats.map((x, i) => ({
          name: x === 'rest' ? 'Rest' : catLabel(x),
          type: 'bar',
          stack: 'spend',
          barCategoryGap: '25%',
          itemStyle: { color: colorOf(x, i), borderColor: colors().panel, borderWidth: 1 },
          data: months.map((m) => Math.round(v.get(`${m}|${x}`) ?? 0)),
        })),
      },
    }
  }, [monthly, c])

  const cal = useMemo(() => {
    if (!daily || !resolved) return null
    const top = [...daily].sort((a, b) => b.spend - a.spend)[0]
    const sorted = daily.map((r) => r.spend).sort((a, b) => a - b)
    const p95 = sorted[Math.floor(sorted.length * 0.95)] ?? 1
    const days = Math.round((Date.parse(resolved.to) - Date.parse(resolved.from)) / 864e5) + 1
    return {
      title: top ? `Biggest discretionary day: ${fmtDay(top.local_date)} (${inr(top.spend)})` : 'Daily discretionary spend',
      height: days > 200 ? 210 : days > 60 ? 230 : 250,
      option: {
        tooltip: { formatter: (p: { value: [string, number] }) => `<b>${fmtDay(p.value[0])}</b>${tipRow(c, 'discretionary', inr(p.value[1]))}<div style="color:${colors().muted}">click for the full day</div>` },
        visualMap: {
          min: 0,
          max: Math.max(100, Math.round(p95)),
          orient: 'horizontal',
          left: 'center',
          bottom: 0,
          itemHeight: 120,
          itemWidth: 10,
          inRange: { color: [shade(c, 0.12), c] },
          textStyle: { color: colors().muted, fontFamily: 'JetBrains Mono', fontSize: 9 },
          text: [`₹${Math.round(p95)}+`, '₹0'],
        },
        calendar: {
          top: 64,
          left: 30,
          right: 8,
          bottom: 40,
          range: [resolved.from, resolved.to],
          cellSize: ['auto', 'auto'],
          splitLine: { show: false },
          itemStyle: { color: colors().bg, borderColor: colors().panel, borderWidth: 1 },
          yearLabel: { show: false },
          dayLabel: { firstDay: 1, nameMap: ['S', 'M', 'T', 'W', 'T', 'F', 'S'], color: colors().muted, fontFamily: 'JetBrains Mono', fontSize: 9 },
          monthLabel: { color: colors().muted, fontFamily: 'JetBrains Mono', fontSize: 9 },
        },
        series: [{ type: 'heatmap', coordinateSystem: 'calendar', data: daily.map((r) => [r.local_date, Math.round(r.spend)]) }],
      },
    }
  }, [daily, resolved, c])

  const py = useMemo(() => {
    if (!payees) return null
    const top = payees[0]
    return {
      title: top ? `${top.payee} received the most (${inr(top.spend)} in ${int(top.txns)} payments)` : 'Top payees',
      option: hbar(payees.map((r) => ({ label: r.payee, value: r.spend, tip: tipRow(c, 'payments', int(r.txns)) + tipRow(c, 'category', catLabel(r.category)) })), c, (v) => `₹${v >= 1000 ? `${(v / 1000).toFixed(1)}k` : Math.round(v)}`, '₹'),
    }
  }, [payees, c])

  return (
    <>
      <Chart name="money-monthly" title={mo?.title ?? 'Monthly spend'} subtitle="all money out by category, incl. transfers and ATM cash" option={mo?.option ?? null} empty={monthly?.length === 0} height={300} />
      <CategoryTable rows={table} />
      <Chart
        name="money-calendar"
        title={cal?.title ?? 'Daily discretionary spend'}
        subtitle="excludes transfers to people, ATM cash and subscriptions"
        option={cal?.option ?? null}
        empty={daily?.length === 0}
        height={cal?.height ?? 230}
        onEvents={{ click: (p: { value: [string, number] }) => p.value && onDay(p.value[0]) }}
      />
      <Chart name="money-top-payees" title={py?.title ?? 'Top payees'} option={py?.option ?? null} empty={payees?.length === 0} height={300} />
    </>
  )
}

function CategoryTable({ rows }: { rows: CatRow[] | null }) {
  const c = sourceColor('bank')
  if (!rows) return <div className="h-40 animate-pixel-blink border-2 border-dashed border-grid" />
  if (!rows.length) return null
  const total = rows.reduce((s, r) => s + r.spend, 0)
  return (
    <div className="flex flex-col gap-2">
      <p className="font-mono text-xs font-bold text-text">
        {catLabel(rows[0].category)} takes the biggest share of money out ({pct(rows[0].share)} of {inr(total)})
      </p>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[320px] font-mono text-[11px] tabular-nums">
          <thead>
            <tr className="text-left text-muted">
              <th className="py-1 pr-2 font-normal">category</th>
              <th className="py-1 pr-2 text-right font-normal">₹ out</th>
              <th className="py-1 pr-2 text-right font-normal">payments</th>
              <th className="w-[38%] py-1 font-normal">share</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.category} className="border-t border-grid">
                <td className={`py-1 pr-2 ${r.discretionary ? 'text-text' : 'text-muted'}`}>
                  {catLabel(r.category)}
                  {!r.discretionary && <span className="text-muted"> ·</span>}
                </td>
                <td className="py-1 pr-2 text-right text-text">{inr(r.spend)}</td>
                <td className="py-1 pr-2 text-right text-muted">{int(r.txns)}</td>
                <td className="py-1">
                  <span className="flex items-center gap-2">
                    <span className="h-2.5" style={{ width: `${Math.max(1, r.share * 100)}%`, background: r.discretionary ? c : shade(c, 0.35) }} />
                    <span className="text-muted">{one(r.share * 100)}%</span>
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="font-mono text-[10px] text-muted">· = not discretionary (transfers to people, ATM cash, subscriptions)</p>
    </div>
  )
}

// ---------------------------------------------------------------- grid / tabs

export function SourcePanels({ me, onDay }: { me: string | null; onDay: (d: string) => void }) {
  const info = useRangeQuery<SourceInfo>('dash_sources')
  const [tab, setTab] = useState<Source>('spotify')
  const get = (s: Source) => info?.find((r) => r.source === s)
  const panels: [Source, ReactNode][] = [
    ['spotify', <MusicPanel key="m" />],
    ['youtube', <YouTubePanel key="y" />],
    ['whatsapp', <ChatsPanel key="c" me={me} />],
    ['bank', <MoneyPanel key="b" onDay={onDay} />],
  ]
  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-4 gap-1 md:hidden" role="tablist" aria-label="Source panels">
        {panels.map(([s]) => (
          <button
            key={s}
            role="tab"
            aria-selected={tab === s}
            onClick={() => setTab(s)}
            className="border-2 px-1 py-2 font-pixel text-[8px]"
            style={tab === s ? { borderColor: sourceColor(s), background: sourceColor(s), color: colors().bg } : { borderColor: colors().grid, color: sourceColor(s) }}
          >
            {SOURCE_NAME[s].toUpperCase()}
          </button>
        ))}
      </div>
      <div className="grid gap-6 md:grid-cols-2">
        {panels.map(([s, node]) => (
          <div key={s} className={`${tab === s ? 'flex' : 'hidden'} min-w-0 flex-col md:flex`}>
            <SourcePanel source={s} info={get(s)}>
              {node}
            </SourcePanel>
          </div>
        ))}
      </div>
    </div>
  )
}
