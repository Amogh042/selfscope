import { useEffect, useMemo, useRef, useState, type DragEvent, type ReactNode } from 'react'
import { DataRows, Panel, Terminal } from '../components/pixel'
import { SourceIcon } from '../components/SourceIcon'
import { useApp, useStoreQuery } from '../lib/appState'
import { expandFiles, fetchDemoFiles, type Candidate } from '../lib/import/detect'
import { ingest } from '../lib/import/ingest'
import { pythonEngine, type StatusSnapshot } from '../lib/pythonEngine'
import { EVENT_COLUMNS, type EventRow } from '../lib/schema'
import { store, type Mode } from '../lib/store'

type ItemStatus = 'detected' | 'parsing' | 'done' | 'known' | 'error' | 'reexport' | 'unknown'

interface Item {
  c: Candidate
  mode: Mode
  status: ItemStatus
  /** Error / problem message, or the result line once done. */
  note?: string
}

const SOURCE_LABEL = { whatsapp: 'WHATSAPP', spotify: 'SPOTIFY', youtube: 'YOUTUBE', unknown: 'UNKNOWN' } as const

const STATUS_UI: Record<ItemStatus, { label: string; cls: string }> = {
  detected: { label: 'DETECTED', cls: 'border-orange-light text-orange-light' },
  parsing: { label: 'PARSING', cls: 'border-orange-light text-orange-light' },
  done: { label: 'DONE', cls: 'border-xp text-xp' },
  known: { label: 'KNOWN', cls: 'border-muted text-muted' },
  error: { label: 'ERROR', cls: 'border-danger text-danger' },
  reexport: { label: 'RE-EXPORT', cls: 'border-orange-light text-orange-light' },
  unknown: { label: '?', cls: 'border-muted text-muted' },
}

const fmt = new Intl.NumberFormat('en-IN')
const pct = (x: number | null | undefined) => (x == null ? '—' : `${(x * 100).toFixed(1)}%`)

function formatBytes(n?: number) {
  if (n == null) return 'in zip'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

function errorText(err: unknown) {
  // Python tracebacks: the last line holds the actual error.
  return err instanceof Error ? err.message.trim().split('\n').slice(-1)[0] : String(err)
}

function SlotStatus({ status }: { status: ItemStatus }) {
  const s = STATUS_UI[status]
  return (
    <span className={`inline-flex items-center gap-1.5 border-2 bg-bg px-1.5 py-1 font-pixel text-[8px] ${s.cls}`}>
      <span className={`inline-block size-1.5 bg-current ${status === 'parsing' ? 'animate-pixel-blink' : ''}`} aria-hidden />
      {s.label}
    </span>
  )
}

function InventorySlot({ item }: { item: Item }) {
  const { c, status } = item
  const note =
    status === 'unknown'
      ? 'Not recognised. Expected a WhatsApp .txt/.zip, Spotify StreamingHistory*.json or Takeout watch-history.json.'
      : status === 'parsing'
        ? 'Parsing in Python worker, then storing…'
        : status === 'detected'
          ? 'Waiting…'
          : item.note
  const tone =
    status === 'error' ? 'text-danger' : status === 'reexport' ? 'text-orange-light' : status === 'done' ? 'text-xp' : 'text-muted'
  return (
    <li
      className={`flex gap-3 border-2 bg-panel p-3 shadow-block-sm ${status === 'unknown' || status === 'known' ? 'border-muted' : status === 'error' ? 'border-danger' : status === 'reexport' ? 'border-orange-light' : 'border-orange'}`}
    >
      <div className="flex size-14 shrink-0 items-center justify-center border-2 border-orange-dark bg-bg shadow-[inset_2px_2px_0_#000]">
        <SourceIcon source={c.source} />
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        <div className="flex items-start justify-between gap-2">
          <span className="font-pixel text-[8px] leading-relaxed text-muted">{SOURCE_LABEL[c.source]}</span>
          <SlotStatus status={status} />
        </div>
        <span className="truncate font-mono text-xs text-text" title={c.name}>
          {c.name}
        </span>
        <span className="font-mono text-[11px] text-muted">
          {formatBytes(c.size)}
          {c.origin ? ` · ${c.origin}` : ''}
        </span>
        <span className={`font-mono text-[11px] ${tone}`}>{note}</span>
      </div>
    </li>
  )
}

function useEngineStatus() {
  const [snap, setSnap] = useState<StatusSnapshot>(pythonEngine.status)
  useEffect(() => pythonEngine.onStatus(setSnap), [])
  return snap
}

/** Human result line for a finished import. */
function resultNote(o: Awaited<ReturnType<typeof ingest>>): string {
  if (o.kind === 'known') return `Already imported (${o.fileName}) · 0 new`
  const r = o.result
  const parts = [
    `+${fmt.format(r.rows_added)} new`,
    `${fmt.format(r.rows_skipped)} duplicates`,
    `${fmt.format(o.parseMs + r.dbMs + r.saveMs)} ms`,
  ]
  const info = o.staged.info
  if (typeof info.unrecognised_prefix === 'number' && info.unrecognised_prefix > 0) {
    parts.push(`${info.unrecognised_prefix} non-English titles kept as-is`)
  }
  if (typeof info.skipped_records === 'number' && info.skipped_records > 0) parts.push(`${info.skipped_records} unreadable records`)
  return parts.join(' · ')
}

export default function ImportPage() {
  const { mode, setMode, storeState } = useApp()
  const [items, setItems] = useState<Item[]>([])
  const itemsRef = useRef<Item[]>([])
  const [dragging, setDragging] = useState(false)
  const [busy, setBusy] = useState(false)
  const [ignored, setIgnored] = useState(0)
  const [notice, setNotice] = useState<{ text: string; tone: 'info' | 'error' } | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const engine = useEngineStatus()

  // Warm up Python while the user picks files (no-op if already loaded).
  useEffect(() => {
    pythonEngine.init().catch(() => {})
  }, [])

  function setAll(next: Item[]) {
    itemsRef.current = next
    setItems(next)
  }
  function update(id: string, target: Mode, patch: Partial<Item>) {
    setAll(itemsRef.current.map((it) => (it.c.id === id && it.mode === target ? { ...it, ...patch } : it)))
  }

  /** Add files to `target`: user files always go to MY DATA, demo files to DEMO. */
  async function addFiles(files: File[], target: Mode) {
    if (!files.length) return
    setBusy(true)
    setNotice(null)
    try {
      if (mode !== target) {
        await setMode(target)
        setNotice({
          text: target === 'real' ? 'Switched to MY DATA: your own files are never stored in the demo database.' : 'Switched to DEMO.',
          tone: 'info',
        })
      }
      const { candidates, ignoredInZips } = await expandFiles(files)
      setIgnored((n) => n + ignoredInZips)
      const known = new Set(itemsRef.current.filter((it) => it.mode === target).map((it) => it.c.id))
      const fresh = candidates.filter((c) => !known.has(c.id))
      const added: Item[] = fresh.map((c) =>
        c.problem
          ? { c, mode: target, status: 'reexport', note: c.problem }
          : { c, mode: target, status: c.source === 'unknown' ? 'unknown' : 'detected' },
      )
      setAll([...itemsRef.current, ...added])

      // One import per file, in order. Duplicates are filtered by DuckDB (event_key).
      for (const it of added.filter((a) => a.status === 'detected')) {
        update(it.c.id, target, { status: 'parsing' })
        try {
          const outcome = await ingest(target, it.c)
          update(it.c.id, target, { status: outcome.kind === 'known' ? 'known' : 'done', note: resultNote(outcome) })
        } catch (err) {
          update(it.c.id, target, { status: 'error', note: errorText(err) })
        }
      }
    } catch (err) {
      setNotice({ text: errorText(err), tone: 'error' })
    } finally {
      setBusy(false)
    }
  }

  async function loadDemo() {
    setBusy(true)
    try {
      await addFiles(await fetchDemoFiles(), 'demo')
    } catch (err) {
      setNotice({ text: errorText(err), tone: 'error' })
      setBusy(false)
    }
  }

  function onDrop(e: DragEvent) {
    e.preventDefault()
    setDragging(false)
    void addFiles(Array.from(e.dataTransfer.files), 'real')
  }

  const visible = items.filter((it) => it.mode === mode)
  const waiting = visible.some((it) => it.status === 'parsing')

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-8 px-4 py-10 sm:px-6">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="flex flex-col gap-3">
          <h1 className="text-2xl text-orange [text-shadow:4px_4px_0_var(--color-orange-dark)] sm:text-3xl">IMPORT</h1>
          <p className="font-pixel text-[11px] text-text">
            LOAD YOUR EXPORTS<span className="animate-pixel-blink text-orange">_</span>
          </p>
        </div>
        <p className="max-w-sm font-mono text-xs text-muted sm:text-right">
          Files are parsed inside this tab and stored only in this browser.
          <br />
          <span className="text-xp">Nothing is uploaded.</span>
          <br />
          <span>
            Python engine:{' '}
            <span className={engine.status === 'ready' ? 'text-xp' : engine.status === 'error' ? 'text-danger' : 'text-orange-light'}>
              {engine.status.toUpperCase()}
            </span>
            {' · '}Database:{' '}
            <span className={storeState.status === 'ready' ? 'text-xp' : 'text-orange-light'}>
              {mode === 'demo' ? 'DEMO' : 'MY DATA'} ({storeState.status.toUpperCase()})
            </span>
          </span>
        </p>
      </header>

      {/* Drop zone */}
      <div
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`flex flex-col items-center gap-5 border-2 border-dashed px-6 py-10 text-center shadow-block ${dragging ? 'border-xp bg-xp/10' : 'border-orange bg-panel'}`}
      >
        <p className="font-pixel text-[11px] leading-loose text-text">
          {dragging ? 'DROP TO ADD TO INVENTORY' : 'DRAG & DROP FILES OR .ZIP HERE'}
        </p>
        <p className="max-w-xl font-mono text-xs text-muted">
          WhatsApp chat .txt or iOS .zip · Spotify StreamingHistory*.json · Google Takeout watch-history.json or Takeout .zip ·
          files you add go to MY DATA; re-adding a file or a newer export only stores new events
        </p>
        <div className="flex flex-wrap justify-center gap-5">
          <button className="pixel-btn" onClick={() => inputRef.current?.click()} disabled={busy}>
            ▶ CHOOSE FILES
          </button>
          <button className="pixel-btn pixel-btn-secondary" onClick={loadDemo} disabled={busy}>
            ★ LOAD DEMO DATA
          </button>
        </div>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".txt,.zip,.json,.html"
          className="hidden"
          onChange={(e) => {
            void addFiles(Array.from(e.target.files ?? []), 'real')
            e.target.value = ''
          }}
        />
      </div>

      {notice && <Terminal tone={notice.tone === 'error' ? 'error' : 'muted'}>{notice.text}</Terminal>}

      {visible.length > 0 && (
        <Panel
          title="INVENTORY"
          tag={
            <span className="font-mono text-xs text-muted">
              {visible.length} slot{visible.length === 1 ? '' : 's'} this visit
              {ignored ? ` · ${ignored} unrelated file(s) in zips ignored` : ''}
            </span>
          }
        >
          {waiting && engine.status !== 'ready' && (
            <p className="font-mono text-xs text-orange-light">
              &gt; Waiting for the Python engine ({engine.detail})<span className="animate-pixel-blink">_</span>
            </p>
          )}
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {visible.map((it) => (
              <InventorySlot key={it.c.id} item={it} />
            ))}
          </ul>
        </Panel>
      )}

      <StoredData />
    </div>
  )
}

// ---------------------------------------------------------------- stored data (from DuckDB)

interface SpotifySummary {
  plays: number
  music_plays: number
  podcast_plays: number
  hours: number | null
  skip_rate: number | null
  artists: number
  formats: string | null
  first_date: string | null
  last_date: string | null
}
interface YouTubeSummary {
  entries: number
  videos: number
  ads: number
  est_hours: number
  channels: number
  shorts: number
  removed: number
  system: number
  first_date: string | null
  last_date: string | null
}
interface ChatRow {
  chat: string
  platform: string | null
  messages: number
  media: number
  deleted: number
  system: number
  is_group: boolean
  first_date: string
  last_date: string
}
interface PersonRow {
  chat: string
  actor: string
  messages: number
}

function StoredData() {
  const sp = useStoreQuery<SpotifySummary>('spotify_summary').data?.[0]
  const yt = useStoreQuery<YouTubeSummary>('youtube_summary').data?.[0]
  const hasSp = !!sp && sp.plays > 0
  const hasYt = !!yt && yt.entries > 0
  return (
    <>
      {(hasSp || hasYt) && (
        <div className="grid gap-8 lg:grid-cols-2">
          {hasSp && <SpotifyPanel s={sp} />}
          {hasYt && <YouTubePanel s={yt} />}
        </div>
      )}
      {hasSp && <PreviewPanel title="SPOTIFY · FIRST 20 EVENTS" source="spotify" />}
      {hasYt && <PreviewPanel title="YOUTUBE · FIRST 20 EVENTS" source="youtube" />}
      <WhatsAppSection />
    </>
  )
}

function TopList({ title, rows }: { title: string; rows: { label: string; sub?: string; n: number }[] }) {
  const max = Math.max(...rows.map((r) => r.n), 1)
  return (
    <div className="flex flex-col gap-2">
      <span className="font-pixel text-[9px] text-orange-light">{title}</span>
      <ol className="flex flex-col gap-2">
        {rows.map((r, i) => (
          <li key={`${r.label}-${i}`} className="flex flex-col gap-1 font-mono text-xs">
            <div className="flex justify-between gap-3">
              <span className="min-w-0 truncate text-text" title={r.sub ? `${r.label} — ${r.sub}` : r.label}>
                <span className="text-muted">{i + 1}.</span> {r.label}
                {r.sub && <span className="text-muted"> · {r.sub}</span>}
              </span>
              <span className="shrink-0 tabular-nums text-muted">{fmt.format(r.n)}</span>
            </div>
            <div className="h-2 bg-bg">
              <div className="h-full bg-orange" style={{ width: `${(r.n / max) * 100}%` }} />
            </div>
          </li>
        ))}
      </ol>
    </div>
  )
}

function SpotifyPanel({ s }: { s: SpotifySummary }) {
  const artists = useStoreQuery<{ name: string; plays: number; hours: number }>('spotify_top_artists').data ?? []
  const tracks = useStoreQuery<{ title: string; artist: string; plays: number }>('spotify_top_tracks').data ?? []
  const mixed = (s.formats ?? '').includes('+')
  return (
    <Panel title="SPOTIFY" tag={<span className="font-mono text-[11px] text-muted">{(s.formats ?? '').toUpperCase()} FORMAT</span>}>
      <DataRows
        rows={[
          ['plays', fmt.format(s.plays)],
          ['hours listened', fmt.format(s.hours ?? 0)],
          ['skip rate', pct(s.skip_rate)],
          ['artists', fmt.format(s.artists)],
          ['podcast plays', fmt.format(s.podcast_plays)],
          ['from', s.first_date ?? '—'],
          ['to', s.last_date ?? '—'],
        ]}
      />
      {mixed && (
        <p className="font-mono text-[11px] text-muted">
          Both export formats loaded: plays found in both (same track, ends within 60 s) are kept once, from the extended history.
        </p>
      )}
      <TopList title="TOP ARTISTS · PLAYS" rows={artists.map((a) => ({ label: a.name, sub: `${a.hours} h`, n: a.plays }))} />
      <TopList title="TOP TRACKS · PLAYS" rows={tracks.map((t) => ({ label: t.title, sub: t.artist, n: t.plays }))} />
    </Panel>
  )
}

function YouTubePanel({ s }: { s: YouTubeSummary }) {
  const channels = useStoreQuery<{ name: string; videos: number }>('youtube_top_channels').data ?? []
  return (
    <Panel title="YOUTUBE" tag={<span className="font-mono text-[11px] text-muted">TAKEOUT</span>}>
      <DataRows
        rows={[
          ['videos watched', fmt.format(s.videos)],
          ['est. hours', fmt.format(s.est_hours)],
          ['ads', `${fmt.format(s.ads)} (${pct(s.entries ? s.ads / s.entries : null)})`],
          ['channels', fmt.format(s.channels)],
          ['shorts', fmt.format(s.shorts)],
          ['from', s.first_date ?? '—'],
          ['to', s.last_date ?? '—'],
          ...(s.removed ? [['removed / private', fmt.format(s.removed)] as [string, string]] : []),
        ]}
      />
      <p className="font-mono text-[11px] text-muted">
        Takeout has no watch duration: hours are estimated from gaps between videos (see docs/schema.md).
      </p>
      <TopList title="TOP CHANNELS · VIDEOS" rows={channels.map((c) => ({ label: c.name, n: c.videos }))} />
    </Panel>
  )
}

function WhatsAppSection() {
  const chats = useStoreQuery<ChatRow>('whatsapp_chats').data ?? []
  const people = useStoreQuery<PersonRow>('whatsapp_people').data ?? []
  const me = useStoreQuery<{ me: string | null }>('me').data?.[0]?.me ?? null
  const [previewChat, setPreviewChat] = useState<string | null>(null)

  const perChat = useMemo(() => {
    const m = new Map<string, PersonRow[]>()
    for (const p of people) m.set(p.chat, [...(m.get(p.chat) ?? []), p])
    return m
  }, [people])

  // Everyone who sent a message, with how many chats they appear in.
  const everyone = useMemo(() => {
    const map = new Map<string, { chats: number; messages: number }>()
    for (const p of people) {
      const v = map.get(p.actor) ?? { chats: 0, messages: 0 }
      map.set(p.actor, { chats: v.chats + 1, messages: v.messages + p.messages })
    }
    return [...map.entries()]
      .map(([name, v]) => ({ name, ...v }))
      .sort((a, b) => b.chats - a.chats || b.messages - a.messages || a.name.localeCompare(b.name))
  }, [people])
  const suggested = everyone.length > 1 && chats.length > 1 && everyone[0].chats > everyone[1].chats ? everyone[0].name : null

  if (!chats.length) return null
  const shownChat = chats.find((c) => c.chat === previewChat)?.chat ?? chats[0].chat

  return (
    <>
      <Panel title="WHICH ONE IS YOU?" tag={<span className="font-mono text-xs text-muted">{everyone.length} people</span>}>
        <p className="font-mono text-xs text-muted">
          Pick your own name so SelfScope can tell your messages from everyone else's (saved in this database).
          {suggested && ` "${suggested}" appears in the most chats.`}
        </p>
        <div className="flex flex-wrap gap-3">
          {everyone.map((p) => {
            const selected = me === p.name
            return (
              <button
                key={p.name}
                onClick={() => void store.setMe(p.name)}
                aria-pressed={selected}
                className={`flex flex-col items-start gap-1 border-2 px-3 py-2 text-left font-mono text-xs ${selected ? 'border-xp bg-xp/10 text-xp shadow-block-xp' : 'border-orange-dark bg-bg text-text hover:border-orange'}`}
              >
                <span className="font-pixel text-[9px]">
                  {selected ? '► ' : ''}
                  {p.name}
                  {p.name === suggested && !selected && <span className="text-orange-light"> ★</span>}
                </span>
                <span className="text-muted">
                  {p.chats} chat{p.chats === 1 ? '' : 's'} · {fmt.format(p.messages)} msgs
                </span>
              </button>
            )
          })}
        </div>
      </Panel>

      {me && (
        <>
          <div className="grid gap-8 md:grid-cols-2 xl:grid-cols-3">
            {chats.map((c) => (
              <ChatCard key={c.chat} chat={c} people={perChat.get(c.chat) ?? []} me={me} />
            ))}
          </div>
          <PreviewPanel
            title="WHATSAPP · FIRST 20 EVENTS"
            source="whatsapp"
            chat={shownChat}
            tabs={
              <div className="flex flex-wrap gap-2">
                {chats.map((c) => (
                  <button
                    key={c.chat}
                    onClick={() => setPreviewChat(c.chat)}
                    className={`border-2 px-2 py-1 font-mono text-xs ${c.chat === shownChat ? 'border-orange bg-orange text-bg' : 'border-orange-dark bg-bg text-text hover:border-orange'}`}
                  >
                    {c.chat}
                  </button>
                ))}
              </div>
            }
          />
        </>
      )}
    </>
  )
}

function ChatCard({ chat: s, people, me }: { chat: ChatRow; people: PersonRow[]; me: string }) {
  const max = Math.max(...people.map((p) => p.messages), 1)
  return (
    <Panel
      title={s.chat.toUpperCase()}
      tag={
        <span className="font-mono text-[11px] text-muted">
          {s.is_group ? 'GROUP' : '1:1'} · {s.platform?.toUpperCase()}
        </span>
      }
    >
      <DataRows
        rows={[
          ['messages', fmt.format(s.messages)],
          ['from', s.first_date],
          ['to', s.last_date],
          ['media', fmt.format(s.media)],
          ['deleted', fmt.format(s.deleted)],
          ['system', fmt.format(s.system)],
        ]}
      />
      <ul className="flex flex-col gap-2">
        {people.map(({ actor, messages }) => (
          <li key={actor} className="flex flex-col gap-1 font-mono text-xs">
            <div className="flex justify-between gap-2">
              <span className={actor === me ? 'text-xp' : 'text-text'}>
                {actor}
                {actor === me && <span className="ml-2 font-pixel text-[8px]">YOU</span>}
              </span>
              <span className="tabular-nums text-muted">{fmt.format(messages)}</span>
            </div>
            <div className="h-2 bg-bg">
              <div className={`h-full ${actor === me ? 'bg-xp' : 'bg-orange'}`} style={{ width: `${(messages / max) * 100}%` }} />
            </div>
          </li>
        ))}
      </ul>
    </Panel>
  )
}

function PreviewPanel({ title, source, chat, tabs }: { title: string; source: string; chat?: string; tabs?: ReactNode }) {
  const rows = useStoreQuery<EventRow>('preview', { preview_source: source, preview_chat: chat ?? null }).data ?? []
  return (
    <Panel title={title} tag={<span className="font-mono text-xs text-muted">stored · shared schema</span>}>
      {tabs}
      <PreviewTable rows={rows} />
    </Panel>
  )
}

function PreviewTable({ rows }: { rows: EventRow[] }) {
  const show = (v: unknown) => (v === null || v === undefined ? <span className="text-muted">null</span> : String(v))
  return (
    <div className="max-h-[28rem] overflow-auto border-2 border-orange-dark bg-bg">
      <table className="w-full border-collapse font-mono text-[11px]">
        <thead className="sticky top-0 bg-panel">
          <tr>
            {EVENT_COLUMNS.map((c) => (
              <th key={c} className="border-b-2 border-orange-dark px-2 py-2 text-left font-normal whitespace-nowrap text-orange-light uppercase">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="odd:bg-panel/40 align-top">
              {EVENT_COLUMNS.map((c) => (
                <td
                  key={c}
                  className={`px-2 py-1.5 ${c === 'text' || c === 'meta' ? 'max-w-72 truncate' : 'whitespace-nowrap'} ${r.event_type === 'system' ? 'text-muted' : 'text-text'}`}
                  title={r[c] == null ? undefined : String(r[c])}
                >
                  {show(r[c])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
