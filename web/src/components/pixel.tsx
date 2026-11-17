// Small set of pixel-UI primitives. See docs/design.md.
import type { ReactNode } from 'react'

export type Status = 'idle' | 'loading' | 'ready' | 'error'

export function Panel({ title, tag, children, className = '' }: {
  title: string
  tag?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section className={`pixel-panel flex flex-col ${className}`}>
      <header className="flex items-center justify-between gap-3 border-b-2 border-orange bg-bg/60 px-4 py-3">
        <h2 className="text-[11px] text-orange">{title}</h2>
        {tag}
      </header>
      <div className="flex flex-1 flex-col gap-4 p-4">{children}</div>
    </section>
  )
}

const STATUS_STYLE: Record<Status, string> = {
  idle: 'border-muted text-muted',
  loading: 'border-orange-light text-orange-light',
  ready: 'border-xp text-xp',
  error: 'border-danger text-danger',
}

export function StatusBadge({ status }: { status: Status }) {
  return (
    <span
      className={`inline-flex items-center gap-2 border-2 bg-bg px-2 py-1 font-pixel text-[9px] uppercase ${STATUS_STYLE[status]}`}
      role="status"
    >
      <span
        className={`inline-block size-2 bg-current ${status === 'loading' ? 'animate-pixel-blink' : ''}`}
        aria-hidden
      />
      {status}
    </span>
  )
}

/** Key/value rows for versions and metrics. */
export function DataRows({ rows }: { rows: [label: string, value: ReactNode][] }) {
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1.5 font-mono text-sm">
      {rows.map(([label, value]) => (
        <div key={label} className="contents">
          <dt className="text-muted uppercase">{label}</dt>
          <dd className="text-right text-text tabular-nums">{value}</dd>
        </div>
      ))}
    </dl>
  )
}

/** Segmented XP bar, Minecraft-style. */
export function XpBar({ value, max, label }: { value: number; max: number; label: string }) {
  const segments = 20
  const filled = Math.round((value / max) * segments)
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-baseline justify-between font-mono text-xs">
        <span className="text-muted uppercase">{label}</span>
        <span className="text-xp">
          {value}/{max}
        </span>
      </div>
      <div
        className="flex h-4 gap-[2px] border-2 border-bg bg-bg p-[2px] outline-2 outline-orange-dark"
        role="progressbar"
        aria-valuenow={value}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-label={label}
      >
        {Array.from({ length: segments }, (_, i) => (
          <div key={i} className={`flex-1 ${i < filled ? 'bg-xp' : 'bg-panel'}`} />
        ))}
      </div>
    </div>
  )
}

export function Terminal({ children, tone = 'text' }: { children: ReactNode; tone?: 'text' | 'error' | 'muted' }) {
  const color = tone === 'error' ? 'text-danger' : tone === 'muted' ? 'text-muted' : 'text-text'
  return (
    <pre
      className={`max-h-72 overflow-auto border-2 border-orange-dark bg-bg p-3 font-mono text-xs leading-relaxed whitespace-pre-wrap ${color}`}
    >
      {children}
    </pre>
  )
}
