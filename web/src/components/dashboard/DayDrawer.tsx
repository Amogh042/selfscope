// DAY DRILL-DOWN: one day across all four sources. Songs (with mood), videos (with topic),
// per-chat message counts and mood (never message text), and transactions with categories.

import { useStoreQuery } from '../../lib/appState'
import { useDayQuery } from '../../lib/dashboard'
import type { EngineResult } from '../../lib/insights'
import { fmtDay, inr, int, language, minutes, signed, SOURCE_NAME, sourceColor, catLabel, weekdayName, type Source } from '../../lib/sourceStyle'
import { Drawer } from './Drawer'

interface Song { time: string; title: string; artist: string; mood: string; language: string | null; minutes: number }
interface Video { time: string; title: string; channel: string; topic: string; minutes: number | null }
interface ChatRow { chat: string; messages: number; sent: number; received: number; late_night: number; mean_sentiment: number | null; positive: number; negative: number }
interface Txn { payee: string | null; amount: number; category: string; channel: string | null }

function Section({ source, title, summary, children }: { source: Source; title?: string; summary: string; children: React.ReactNode }) {
  const col = sourceColor(source)
  return (
    <section className="flex flex-col gap-2">
      <div className="flex items-baseline justify-between gap-3 border-b-2 pb-1" style={{ borderColor: col }}>
        <h3 className="text-[10px]" style={{ color: col }}>
          {title ?? SOURCE_NAME[source].toUpperCase()}
        </h3>
        <span className="font-mono text-[10px] text-muted">{summary}</span>
      </div>
      {children}
    </section>
  )
}

const Empty = ({ what }: { what: string }) => <p className="font-mono text-[11px] text-muted">No {what} this day.</p>
const Loading = () => <p className="animate-pixel-blink font-mono text-[11px] text-orange-light">LOADING…</p>

export function DayDrawer({ day, res, onClose }: { day: string; res: EngineResult | null; onClose: () => void }) {
  const songs = useDayQuery<Song>('day_songs', day)
  const videos = useDayQuery<Video>('day_videos', day)
  const chats = useDayQuery<ChatRow>('day_chats', day)
  const txns = useDayQuery<Txn>('day_txns', day)
  const me = useStoreQuery<{ me: string | null }>('me').data?.[0]?.me ?? null
  const periods = (useStoreQuery<{ label: string; start_date: string; end_date: string }>('periods_list').data ?? []).filter(
    (p) => p.start_date <= day && day <= p.end_date,
  )
  const anomaly = res?.anomalies.days.find((d) => d.date === day)
  const out = (txns ?? []).filter((t) => t.amount < 0).reduce((s, t) => s - t.amount, 0)
  const inn = (txns ?? []).filter((t) => t.amount > 0).reduce((s, t) => s + t.amount, 0)

  return (
    <Drawer title={fmtDay(day).toUpperCase()} onClose={onClose}>
      <div className="flex flex-wrap items-center gap-2 font-mono text-xs text-muted">
        <span>{weekdayName(day)}</span>
        {periods.map((p) => (
          <span key={p.start_date} className="border-2 border-orange-light px-1.5 py-0.5 text-orange-light">
            {p.label}
          </span>
        ))}
      </div>
      {anomaly && (
        <p className="border-l-2 border-orange pl-3 text-sm text-text">
          <span className="font-pixel text-[8px] text-orange">UNUSUAL DAY · </span>
          {anomaly.sentence}
        </p>
      )}

      <Section source="spotify" summary={songs ? `${int(songs.length)} plays · ${minutes(songs.reduce((s, r) => s + r.minutes, 0))}` : ''}>
        {!songs ? <Loading /> : !songs.length ? <Empty what="songs" /> : (
          <ul className="flex max-h-56 flex-col gap-0.5 overflow-y-auto font-mono text-[11px]">
            {songs.map((s, i) => (
              <li key={i} className="grid grid-cols-[40px_1fr_auto] gap-2">
                <span className="text-muted">{s.time}</span>
                <span className="truncate text-text" title={`${s.title} · ${s.artist}`}>
                  {s.title} <span className="text-muted">· {s.artist}</span>
                </span>
                <span className="text-muted">
                  {s.mood === 'unknown' ? '?' : s.mood}
                  {s.language ? ` · ${language(s.language)}` : ''}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section source="youtube" summary={videos ? `${int(videos.filter((v) => v.topic !== 'ad').length)} videos · ~${minutes(videos.reduce((s, r) => s + (r.minutes ?? 0), 0))}` : ''}>
        {!videos ? <Loading /> : !videos.length ? <Empty what="videos" /> : (
          <ul className="flex max-h-56 flex-col gap-0.5 overflow-y-auto font-mono text-[11px]">
            {videos.map((v, i) => (
              <li key={i} className={`grid grid-cols-[40px_1fr_auto] gap-2 ${v.topic === 'ad' ? 'opacity-50' : ''}`}>
                <span className="text-muted">{v.time}</span>
                <span className="truncate text-text" title={`${v.title} · ${v.channel}`}>
                  {v.title} <span className="text-muted">· {v.channel}</span>
                </span>
                <span className="text-muted">{v.topic}</span>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section source="whatsapp" summary={chats ? `${int(chats.reduce((s, r) => s + r.messages, 0))} messages · counts only` : ''}>
        {!chats ? <Loading /> : !chats.length ? <Empty what="messages" /> : (
          <table className="w-full font-mono text-[11px] tabular-nums">
            <thead>
              <tr className="text-left text-muted">
                <th className="font-normal">chat</th>
                <th className="text-right font-normal">msgs</th>
                {me && <th className="text-right font-normal">sent</th>}
                <th className="text-right font-normal">late</th>
                <th className="text-right font-normal">mood</th>
                <th className="text-right font-normal">+ / −</th>
              </tr>
            </thead>
            <tbody>
              {chats.map((c) => (
                <tr key={c.chat} className="border-t border-grid text-text">
                  <td className="max-w-40 truncate py-0.5">{c.chat}</td>
                  <td className="text-right">{int(c.messages)}</td>
                  {me && <td className="text-right">{int(c.sent)}</td>}
                  <td className="text-right text-muted">{int(c.late_night)}</td>
                  <td className="text-right">{signed(c.mean_sentiment)}</td>
                  <td className="text-right text-muted">
                    {int(c.positive)} / {int(c.negative)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>

      <Section source="bank" summary={txns ? `${inr(out)} out · ${inr(inn)} in` : ''}>
        {!txns ? <Loading /> : !txns.length ? <Empty what="transactions" /> : (
          <ul className="flex flex-col gap-0.5 font-mono text-[11px]">
            {txns.map((t, i) => (
              <li key={i} className="grid grid-cols-[1fr_auto_80px] gap-2">
                <span className="truncate text-text">{t.payee ?? t.channel ?? '—'}</span>
                <span className="text-muted">{catLabel(t.category)}</span>
                <span className={`text-right tabular-nums ${t.amount > 0 ? 'text-xp' : 'text-text'}`}>
                  {t.amount > 0 ? '+' : '−'}
                  {inr(Math.abs(t.amount))}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Section>
      <p className="font-mono text-[10px] text-muted">
        Times are local (IST). Bank statements have dates only. Message text is never shown here: only counts, and mood from
        the lexicon scorer (−1…1).
      </p>
    </Drawer>
  )
}
