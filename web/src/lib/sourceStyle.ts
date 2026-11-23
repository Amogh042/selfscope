// One fixed colour + name per data source (docs/design.md "Data colours"), and the value
// formatters shared by the dashboard. Colours are read from the CSS theme tokens so
// index.css stays the single source of truth (ECharts draws on a canvas and needs hex values).

export type Source = 'spotify' | 'youtube' | 'whatsapp' | 'bank'
export const SOURCES: Source[] = ['spotify', 'youtube', 'whatsapp', 'bank']

export const SOURCE_NAME: Record<Source, string> = {
  spotify: 'Music',
  youtube: 'YouTube',
  whatsapp: 'Chats',
  bank: 'Money',
}
const TOKEN: Record<Source, string> = {
  spotify: '--color-music',
  youtube: '--color-youtube',
  whatsapp: '--color-chats',
  bank: '--color-money',
}

let cache: Record<string, string> | null = null
/** Theme colours as hex (read once from :root). */
export function colors() {
  if (!cache) {
    const cs = getComputedStyle(document.documentElement)
    const v = (n: string) => cs.getPropertyValue(n).trim()
    cache = {
      bg: v('--color-bg'),
      panel: v('--color-panel'),
      orange: v('--color-orange'),
      orangeDark: v('--color-orange-dark'),
      orangeLight: v('--color-orange-light'),
      text: v('--color-text'),
      muted: v('--color-muted'),
      grid: v('--color-grid'),
      danger: v('--color-danger'),
      xp: v('--color-xp'),
      spotify: v(TOKEN.spotify),
      youtube: v(TOKEN.youtube),
      whatsapp: v(TOKEN.whatsapp),
      bank: v(TOKEN.bank),
    }
  }
  return cache
}
export const sourceColor = (s: Source | string) => colors()[s as Source] ?? colors().muted

/** Mix a hex colour with the panel background: t = 1 keeps the colour, t = 0 is the panel. */
export function shade(hex: string, t: number) {
  const p = colors().panel
  const c = (h: string, i: number) => parseInt(h.slice(1 + 2 * i, 3 + 2 * i), 16)
  const mix = [0, 1, 2].map((i) => Math.round(c(p, i) + (c(hex, i) - c(p, i)) * t))
  return `#${mix.map((x) => x.toString(16).padStart(2, '0')).join('')}`
}
/** Lightness steps of one source colour for categories inside a chart (biggest first). */
export const SHADES = [1, 0.62, 0.38, 0.22]

// ---------------------------------------------------------------- formatting

const nf0 = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 })
const nf1 = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 1, minimumFractionDigits: 1 })

export const inr = (v: number | null | undefined) => (v == null ? '—' : `₹${nf0.format(v)}`)
export const int = (v: number | null | undefined) => (v == null ? '—' : nf0.format(v))
export const one = (v: number | null | undefined) => (v == null ? '—' : nf1.format(v))
export const pct = (v: number | null | undefined, digits = 0) => (v == null ? '—' : `${(v * 100).toFixed(digits)}%`)
export const signed = (v: number | null | undefined, digits = 2) =>
  v == null ? '—' : `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(digits)}`
export const minutes = (v: number | null | undefined) =>
  v == null ? '—' : v >= 90 ? `${nf1.format(v / 60)}h` : `${nf0.format(v)} min`

/** Format a value by the engine's unit (analysis/metrics.py): min | inr | share | score | count. */
export function byUnit(unit: string, v: number | null | undefined) {
  if (unit === 'min') return minutes(v)
  if (unit === 'inr') return inr(v)
  if (unit === 'share') return pct(v)
  if (unit === 'score') return signed(v)
  return v == null ? '—' : Math.abs(v) >= 10 ? int(v) : one(v)
}
export const UNIT_AXIS: Record<string, string> = { min: 'min', inr: '₹', share: '%', score: 'mood −1…1', count: 'count' }

export const titleCase = (s: string | null | undefined) =>
  s ? s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()) : '—'

const CATEGORY: Record<string, string> = {
  tea_snacks: 'Tea & snacks',
  groceries_qcommerce: 'Groceries',
  bills_recharge: 'Bills & recharge',
  p2p_transfer: 'Transfers to people',
  cash_atm: 'ATM cash',
  food_delivery: 'Food delivery',
}
/** Display name for a bank category / topic / mood. */
export const catLabel = (c: string | null | undefined) => (c && CATEGORY[c]) || titleCase(c)

const LANG: Record<string, string> = { hi: 'Hindi', en: 'English', kn: 'Kannada', ta: 'Tamil', te: 'Telugu', pa: 'Punjabi', ml: 'Malayalam', mr: 'Marathi', bn: 'Bengali' }
export const language = (c: string) => LANG[c] ?? (c === 'unknown' ? 'Unknown' : c.toUpperCase())

export const fmtDay = (s: string | null | undefined) =>
  s ? new Date(`${s}T00:00:00Z`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }) : '—'
export const fmtDayShort = (s: string) =>
  new Date(`${s}T00:00:00Z`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' })
export const weekdayName = (s: string) =>
  new Date(`${s}T00:00:00Z`).toLocaleDateString('en-GB', { weekday: 'long', timeZone: 'UTC' })
