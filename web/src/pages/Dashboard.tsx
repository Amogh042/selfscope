// DASHBOARD (#/dashboard, the home page once data exists): player stats, timeline, source
// panels, cross-app insights + correlation matrix, periods, and the day drill-down.
// Everything follows the global date range and the DEMO / MY DATA mode.

import { useCallback, useState, type ReactNode } from 'react'
import { DayDrawer } from '../components/dashboard/DayDrawer'
import { InsightsSection } from '../components/dashboard/InsightsSection'
import { PeriodsSection } from '../components/dashboard/PeriodsSection'
import { PlayerStats } from '../components/dashboard/PlayerStats'
import { SourcePanels } from '../components/dashboard/SourcePanels'
import { Timeline } from '../components/dashboard/Timeline'
import { Panel, PanelBoundary, Terminal } from '../components/pixel'
import { useApp, useStoreQuery } from '../lib/appState'
import { useEngine } from '../lib/dashboard'
import { fmtDay, int } from '../lib/sourceStyle'

function Section({ id, title, tag, children }: { id: string; title: string; tag?: ReactNode; children: ReactNode }) {
  return (
    <section id={id} className="flex scroll-mt-28 flex-col gap-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2 border-b-2 border-orange-dark pb-2">
        <h2 className="text-[12px] text-orange">{title}</h2>
        {tag}
      </div>
      <PanelBoundary name={title}>{children}</PanelBoundary>
    </section>
  )
}

export default function DashboardPage() {
  const { mode, resolved, href, storeState } = useApp()
  const engine = useEngine()
  const res = engine.res
  const [day, setDay] = useState<string | null>(null)
  const onDay = useCallback((d: string) => setDay(d), [])
  const me = useStoreQuery<{ me: string | null }>('me').data?.[0]?.me ?? null
  const hasChats = (useStoreQuery<{ chat: string }>('whatsapp_chats').data ?? []).length > 0

  if (storeState.status === 'ready' && !resolved)
    return (
      <div className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-10 sm:px-6">
        <h1 className="text-2xl text-orange [text-shadow:4px_4px_0_var(--color-orange-dark)] sm:text-3xl">DASHBOARD</h1>
        <Panel title="NO SAVE FILE">
          <p className="font-mono text-sm text-muted">
            {mode === 'demo' ? 'The demo database is empty.' : 'No data in this database yet.'} Import your exports, or load the synthetic
            demo year, to start.
          </p>
          <a href={href('/import')} className="pixel-btn self-start">
            ▶ GO TO IMPORT
          </a>
        </Panel>
      </div>
    )

  const anomalies = res?.anomalies.days ?? []
  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-10 px-4 py-8 sm:px-6">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="flex flex-col gap-3">
          <h1 className="text-2xl text-orange [text-shadow:4px_4px_0_var(--color-orange-dark)] sm:text-3xl">DASHBOARD</h1>
          <p className="font-pixel text-[10px] text-text">
            PLAYER 1 · {mode === 'demo' ? 'DEMO SAVE' : 'YOUR SAVE'}
            <span className="animate-pixel-blink text-orange">_</span>
          </p>
        </div>
        <p className="font-mono text-xs text-muted sm:text-right">
          {resolved ? `${fmtDay(resolved.from)} – ${fmtDay(resolved.to)}` : '…'}
          {res && ` · ${int(res.range.days)} days`}
          <br />
          {engine.busy ? (
            <span className="animate-pixel-blink text-orange-light">analysing in the Python worker…</span>
          ) : engine.meta ? (
            `analysis ${engine.meta.cached ? 'from cache' : 'computed'} in ${engine.meta.ms.toLocaleString('en-IN')} ms · runs in your browser`
          ) : (
            ''
          )}
        </p>
      </header>

      {engine.error && <Terminal tone="error">{engine.error}</Terminal>}
      {hasChats && !me && (
        <Terminal tone="muted">
          Tip: pick your own name under "Which one is you?" on the import screen to include the messages you send and their mood.
        </Terminal>
      )}

      <Section id="stats" title="PLAYER STATS" tag={<span className="font-mono text-[10px] text-muted">vs the previous period of the same length</span>}>
        <PlayerStats me={me} />
      </Section>

      <Section id="timeline" title="TIMELINE">
        <div className="pixel-panel flex flex-col gap-4 p-4">
          <Timeline res={res} onDay={onDay} />
          {anomalies.length > 0 && (
            <details className="border-2 border-orange-dark bg-bg p-3">
              <summary className="cursor-pointer font-pixel text-[9px] text-orange-light">■ UNUSUAL DAYS · {anomalies.length}</summary>
              <ul className="mt-3 flex flex-col gap-1.5">
                {anomalies.map((d) => (
                  <li key={d.date}>
                    <button onClick={() => setDay(d.date)} className="w-full border-l-2 border-orange pl-3 text-left text-xs text-text hover:text-orange-light">
                      {d.sentence}
                    </button>
                  </li>
                ))}
              </ul>
              <p className="mt-2 font-mono text-[10px] text-muted">Isolation forest (2% of days) + robust z-score (|z| &gt; 3.5) per metric.</p>
            </details>
          )}
        </div>
      </Section>

      <Section id="sources" title="SOURCES">
        <SourcePanels me={me} onDay={onDay} />
      </Section>

      <Section
        id="insights"
        title="CROSS-APP INSIGHTS"
        tag={
          res && (
            <span className="font-mono text-[10px] text-muted">
              {res.correlation_window.days ? `${int(res.correlation_window.days)} days where every app has data` : 'no overlap between apps'}
            </span>
          )
        }
      >
        <InsightsSection res={res} busy={engine.busy} onDay={onDay} />
      </Section>

      <Section id="periods" title="PERIODS" tag={<span className="font-mono text-[10px] text-muted">inside vs outside · Mann-Whitney + FDR</span>}>
        <div className="pixel-panel p-4">
          <PeriodsSection res={res} />
        </div>
      </Section>

      {day && <DayDrawer day={day} res={res} onClose={() => setDay(null)} />}
    </div>
  )
}
