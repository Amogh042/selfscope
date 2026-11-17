// Shared event format — TypeScript mirror of docs/schema.md and src/python/schema.py.
// One row = one event, from any source.

export const LOCAL_TZ = 'Asia/Kolkata'

export type Source = 'whatsapp' | 'spotify' | 'youtube' | 'bank'
export type EventType = 'message' | 'play' | 'watch' | 'transaction' | 'system'

export interface EventRow {
  source: Source
  /** ISO-8601 UTC timestamp, e.g. "2025-11-17T16:11:00.000Z". */
  ts_utc: string
  /** YYYY-MM-DD in Asia/Kolkata. */
  local_date: string
  /** 0–23 in Asia/Kolkata. */
  local_hour: number
  /** 0 = Monday … 6 = Sunday. */
  weekday: number
  event_type: EventType
  actor: string | null
  title: string | null
  text: string | null
  /** ms played, INR amount (signed), or null. */
  value: number | null
  category: string | null
  /** JSON object string with source-specific extras. */
  meta: string
}

export const EVENT_COLUMNS = [
  'source',
  'ts_utc',
  'local_date',
  'local_hour',
  'weekday',
  'event_type',
  'actor',
  'title',
  'text',
  'value',
  'category',
  'meta',
] as const satisfies readonly (keyof EventRow)[]
