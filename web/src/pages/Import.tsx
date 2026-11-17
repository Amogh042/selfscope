import { useEffect, useMemo, useRef, useState, type DragEvent } from 'react'
import { DataRows, Panel, Terminal } from '../components/pixel'
import { SourceIcon } from '../components/SourceIcon'
import { expandFiles, fetchDemoFiles, type Candidate } from '../lib/import/detect'
import { parseSpotify, parseYouTube, type SpotifySummary, type YouTubeSummary } from '../lib/import/media'
import { parseWhatsApp, type ChatSummary } from '../lib/import/whatsapp'
import { pythonEngine, type StatusSnapshot } from '../lib/pythonEngine'
import { EVENT_COLUMNS } from '../lib/schema'

type ItemStatus = 'detected' | 'parsing' | 'done' | 'error' | 'reexport' | 'unknown'

interface Item {
  c: Candidate
  status: ItemStatus
  error?: string
  summary?: ChatSummary
  /** Spotify / YouTube: rows parsed from this file (before de-duplication). */
  rows?: number
  ms?: number
}

const SOURCE_LABEL = { whatsapp: 'WHATSAPP', spotify: 'SPOTIFY', youtube: 'YOUTUBE', unknown: 'UNKNOWN' } as const

const STATUS_UI: Record<ItemStatus, { label: string; cls: string }> = {
  detected: { label: 'DETECTED', cls: 'border-orange-light text-orange-light' },
  parsing: { label: 'PARSING', cls: 'border-orange-light text-orange-light' },
  done: { label: 'DONE', cls: 'border-xp text-xp' },
  error: { label: 'ERROR', cls: 'border-danger text-danger' },
  reexport: { label: 'RE-EXPORT', cls: 'border-orange-light text-orange-light' },
  unknown: { label: '?', cls: 'border-muted text-muted' },
}

const fmt = new Intl.NumberFormat('en-IN')

function formatBytes(n?: number) {
  if (n == null) return 'in zip'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
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
      : status === 'error' || status === 'reexport'
        ? item.error
        : status === 'done'
          ? item.summary
            ? `${fmt.format(item.summary.messages)} messages · ${item.ms} ms`
            : `${fmt.format(item.rows ?? 0)} ${c.source === 'spotify' ? 'plays' : 'entries'} · merged · ${item.ms} ms`
          : status === 'parsing'
              ? 'Running parser in Python worker…'
              : 'Waiting to parse…'
  return (
    <li
      className={`flex gap-3 border-2 bg-panel p-3 shadow-block-sm ${status === 'unknown' ? 'border-muted' : status === 'error' ? 'border-danger' : status === 'reexport' ? 'border-orange-light' : 'border-orange'}`}
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
        <span
          className={`font-mono text-[11px] ${status === 'error' ? 'text-danger' : status === 'reexport' ? 'text-orange-light' : status === 'done' ? 'text-xp' : 'text-muted'}`}
        >
          {note}
        </span>
      </div>
    </li>
  )
}

function useEngineStatus() {
  const [snap, setSnap] = useState<StatusSnapshot>(pythonEngine.status)
  useEffect(() => pythonEngine.onStatus(setSnap), [])
  return snap
}

export default function ImportPage() {
  const [items, setItems] = useState<Item[]>([])
  const itemsRef = useRef<Item[]>([])
  const [dragging, setDragging] = useState(false)
  const [busy, setBusy] = useState(false)
  const [ignored, setIgnored] = useState(0)
  const [notice, setNotice] = useState<string | null>(null)
  const [me, setMe] = useState<string | null>(null)
  const [previewId, setPreviewId] = useState<string | null>(null)
  const [spotify, setSpotify] = useState<SpotifySummary | null>(null)
  const [youtube, setYouTube] = useState<YouTubeSummary | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const engine = useEngineStatus()

  // Warm up Python while the user picks files (no-op if System Check already loaded it).
  useEffect(() => {
    pythonEngine.init().catch(() => {})
  }, [])

  function setAll(next: Item[]) {
    itemsRef.current = next
    setItems(next)
  }
  function update(id: string, patch: Partial<Item>) {
    setAll(itemsRef.current.map((it) => (it.c.id === id ? { ...it, ...patch } : it)))
  }

  async function addFiles(files: File[]) {
    if (!files.length) return
    setBusy(true)
    setNotice(null)
    try {
      const { candidates, ignoredInZips } = await expandFiles(files)
      setIgnored((n) => n + ignoredInZips)
      const known = new Set(itemsRef.current.map((it) => it.c.id))
      const fresh = candidates.filter((c) => !known.has(c.id))
      if (fresh.length < candidates.length) setNotice(`${candidates.length - fresh.length} file(s) already added — skipped.`)
      const added: Item[] = fresh.map((c) =>
        c.problem
          ? { c, status: 'reexport', error: c.problem }
          : { c, status: c.source === 'unknown' ? 'unknown' : 'detected' },
      )
      setAll([...itemsRef.current, ...added])

      // Parse WhatsApp chats one by one in the Python worker.
      for (const it of added.filter((a) => a.c.source === 'whatsapp')) {
        update(it.c.id, { status: 'parsing' })
        try {
          const t0 = performance.now()
          const summary = await parseWhatsApp(it.c.id, await it.c.readText(), it.c.chatName)
          update(it.c.id, { status: 'done', summary, ms: Math.round(performance.now() - t0) })
          setPreviewId((p) => p ?? it.c.id)
        } catch (err) {
          update(it.c.id, { status: 'error', error: errorText(err) })
        }
      }

      // Spotify / YouTube: all files of a source are parsed together into one merged frame.
      for (const source of ['spotify', 'youtube'] as const) {
        const batch = added.filter((a) => a.c.source === source && a.status === 'detected')
        if (!batch.length) continue
        for (const it of batch) update(it.c.id, { status: 'parsing' })
        const t0 = performance.now()
        try {
          const texts: Record<string, string> = {}
          for (const it of batch) texts[it.c.id] = await it.c.readText()
          const summary = source === 'spotify' ? await parseSpotify(texts) : await parseYouTube(texts)
          const ms = Math.round(performance.now() - t0)
          for (const it of batch) update(it.c.id, { status: 'done', rows: summary.per_file[it.c.id] ?? 0, ms })
          if (source === 'spotify') setSpotify(summary as SpotifySummary)
          else setYouTube(summary as YouTubeSummary)
        } catch (err) {
          for (const it of batch) update(it.c.id, { status: 'error', error: errorText(err) })
        }
      }
    } catch (err) {
      setNotice(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  async function loadDemo() {
    setBusy(true)
    try {
      await addFiles(await fetchDemoFiles())
    } catch (err) {
      setNotice(err instanceof Error ? err.message : String(err))
      setBusy(false)
    }
  }

  function onDrop(e: DragEvent) {
    e.preventDefault()
    setDragging(false)
    void addFiles(Array.from(e.dataTransfer.files))
  }

  const chats = items.filter((it) => it.status === 'done' && it.c.source === 'whatsapp' && it.summary)

  // Everyone who sent a message, with how many chats they appear in.
  const people = useMemo(() => {
    const map = new Map<string, { chats: number; messages: number }>()
    for (const it of chats) {
      for (const [name, n] of Object.entries(it.summary!.per_person)) {
        const p = map.get(name) ?? { chats: 0, messages: 0 }
        map.set(name, { chats: p.chats + 1, messages: p.messages + n })
      }
    }
    return [...map.entries()]
      .map(([name, v]) => ({ name, ...v }))
      .sort((a, b) => b.chats - a.chats || b.messages - a.messages || a.name.localeCompare(b.name))
  }, [chats])
  const suggested = people.length > 1 && chats.length > 1 && people[0].chats > people[1].chats ? people[0].name : null

  const waiting = items.some((it) => it.status === 'detected' || it.status === 'parsing')
  const preview = chats.find((it) => it.c.id === previewId) ?? chats[0]

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-8 px-4 py-10 sm:px-6">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="flex flex-col gap-3">
          <a href="#/" className="font-mono text-xs text-muted hover:text-orange">
            ◀ SYSTEM CHECK
          </a>
          <h1 className="text-2xl text-orange [text-shadow:4px_4px_0_var(--color-orange-dark)] sm:text-3xl">IMPORT</h1>
          <p className="font-pixel text-[11px] text-text">
            LOAD YOUR EXPORTS<span className="animate-pixel-blink text-orange">_</span>
          </p>
        </div>
        <p className="max-w-sm font-mono text-xs text-muted sm:text-right">
          Files are read and parsed inside this tab.
          <br />
          <span className="text-xp">Nothing is uploaded. Nothing is saved.</span>
          <br />
          <span>
            Python engine:{' '}
            <span className={engine.status === 'ready' ? 'text-xp' : engine.status === 'error' ? 'text-danger' : 'text-orange-light'}>
              {engine.status.toUpperCase()}
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
          WhatsApp chat .txt or iOS .zip · Spotify StreamingHistory*.json · Google Takeout watch-history.json ·
          multiple files and zips welcome
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
          accept=".txt,.zip,.json"
          className="hidden"
          onChange={(e) => {
            void addFiles(Array.from(e.target.files ?? []))
            e.target.value = ''
          }}
        />
      </div>

      {notice && <Terminal tone="error">{notice}</Terminal>}

      {/* Inventory */}
      {items.length > 0 && (
        <Panel
          title="INVENTORY"
          tag={
            <span className="font-mono text-xs text-muted">
              {items.length} slot{items.length === 1 ? '' : 's'}
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
            {items.map((it) => (
              <InventorySlot key={it.c.id} item={it} />
            ))}
          </ul>
        </Panel>
      )}

      {/* Spotify + YouTube summaries */}
      {(spotify || youtube) && (
        <div className="grid gap-8 lg:grid-cols-2">
          {spotify && <SpotifyPanel s={spotify} />}
          {youtube && <YouTubePanel s={youtube} />}
        </div>
      )}
      {spotify && (
        <Panel title="SPOTIFY · FIRST 20 EVENTS" tag={<span className="font-mono text-xs text-muted">shared schema</span>}>
          <PreviewTable rows={spotify.preview} />
        </Panel>
      )}
      {youtube && (
        <Panel title="YOUTUBE · FIRST 20 EVENTS" tag={<span className="font-mono text-xs text-muted">shared schema</span>}>
          <PreviewTable rows={youtube.preview} />
        </Panel>
      )}

      {/* Which one is you? */}
      {people.length > 0 && (
        <Panel title="WHICH ONE IS YOU?" tag={<span className="font-mono text-xs text-muted">{people.length} people</span>}>
          <p className="font-mono text-xs text-muted">
            Pick your own name so SelfScope can tell your messages from everyone else's.
            {suggested && ` "${suggested}" appears in the most chats.`}
          </p>
          <div className="flex flex-wrap gap-3">
            {people.map((p) => {
              const selected = me === p.name
              return (
                <button
                  key={p.name}
                  onClick={() => setMe(p.name)}
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
      )}

      {/* Per-chat summaries + preview (after picking "you") */}
      {me && chats.length > 0 && (
        <>
          <div className="grid gap-8 md:grid-cols-2 xl:grid-cols-3">
            {chats.map((it) => (
              <ChatCard key={it.c.id} item={it} me={me} />
            ))}
          </div>
          {preview && (
            <Panel title="WHATSAPP · FIRST 20 EVENTS" tag={<span className="font-mono text-xs text-muted">shared schema</span>}>
              <div className="flex flex-wrap gap-2">
                {chats.map((it) => (
                  <button
                    key={it.c.id}
                    onClick={() => setPreviewId(it.c.id)}
                    className={`border-2 px-2 py-1 font-mono text-xs ${it === preview ? 'border-orange bg-orange text-bg' : 'border-orange-dark bg-bg text-text hover:border-orange'}`}
                  >
                    {it.summary!.chat ?? it.c.name}
                  </button>
                ))}
              </div>
              <PreviewTable rows={preview.summary!.preview} />
            </Panel>
          )}
        </>
      )}
    </div>
  )
}

function ChatCard({ item, me }: { item: Item; me: string }) {
  const s = item.summary!
  const max = Math.max(...Object.values(s.per_person), 1)
  return (
    <Panel
      title={(s.chat ?? item.c.name).toUpperCase()}
      tag={
        <span className="font-mono text-[11px] text-muted">
          {s.is_group ? 'GROUP' : '1:1'} · {s.platform?.toUpperCase()}
        </span>
      }
    >
      <DataRows
        rows={[
          ['messages', fmt.format(s.messages)],
          ['from', s.first_date ?? '—'],
          ['to', s.last_date ?? '—'],
          ['media', fmt.format(s.media)],
          ['deleted', fmt.format(s.deleted)],
          ['system', fmt.format(s.system)],
        ]}
      />
      <ul className="flex flex-col gap-2">
        {Object.entries(s.per_person).map(([name, n]) => (
          <li key={name} className="flex flex-col gap-1 font-mono text-xs">
            <div className="flex justify-between gap-2">
              <span className={name === me ? 'text-xp' : 'text-text'}>
                {name}
                {name === me && <span className="ml-2 font-pixel text-[8px]">YOU</span>}
              </span>
              <span className="tabular-nums text-muted">{fmt.format(n)}</span>
            </div>
            <div className="h-2 bg-bg">
              <div className={`h-full ${name === me ? 'bg-xp' : 'bg-orange'}`} style={{ width: `${(n / max) * 100}%` }} />
            </div>
          </li>
        ))}
      </ul>
    </Panel>
  )
}

function errorText(err: unknown) {
  // Python tracebacks: the last line holds the actual error.
  return err instanceof Error ? err.message.trim().split('\n').slice(-1)[0] : String(err)
}

const pct = (x: number | null) => (x == null ? '—' : `${(x * 100).toFixed(1)}%`)

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
  return (
    <Panel
      title="SPOTIFY"
      tag={<span className="font-mono text-[11px] text-muted">{s.formats.join(' + ').toUpperCase()} FORMAT</span>}
    >
      <DataRows
        rows={[
          ['plays', fmt.format(s.plays)],
          ['hours listened', fmt.format(s.hours)],
          ['skip rate', pct(s.skip_rate)],
          ['artists', fmt.format(s.artists)],
          ['podcast plays', fmt.format(s.podcast_plays)],
          ['from', s.first_date ?? '—'],
          ['to', s.last_date ?? '—'],
          ...(s.duplicates_dropped ? [['duplicates dropped', fmt.format(s.duplicates_dropped)] as [string, string]] : []),
        ]}
      />
      {s.formats.length > 1 && (
        <p className="font-mono text-[11px] text-orange-light">
          Both Spotify export formats are loaded. Plays from a period covered by both are counted twice.
        </p>
      )}
      <TopList title="TOP ARTISTS · PLAYS" rows={s.top_artists.map((a) => ({ label: a.name, sub: `${a.hours} h`, n: a.plays }))} />
      <TopList title="TOP TRACKS · PLAYS" rows={s.top_tracks.map((t) => ({ label: t.title, sub: t.artist, n: t.plays }))} />
    </Panel>
  )
}

function YouTubePanel({ s }: { s: YouTubeSummary }) {
  return (
    <Panel title="YOUTUBE" tag={<span className="font-mono text-[11px] text-muted">TAKEOUT · {fmt.format(s.sessions)} SESSIONS</span>}>
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
      {s.unrecognised_prefix > 0 && (
        <p className="font-mono text-[11px] text-orange-light">
          {fmt.format(s.unrecognised_prefix)} {s.unrecognised_prefix === 1 ? 'entry' : 'entries'} had a non-English
          prefix and {s.unrecognised_prefix === 1 ? 'was' : 'were'} kept as-is (e.g. "
          {s.prefix_examples[0]}").
        </p>
      )}
      <TopList title="TOP CHANNELS · VIDEOS" rows={s.top_channels.map((c) => ({ label: c.name, n: c.videos }))} />
    </Panel>
  )
}

function PreviewTable({ rows }: { rows: ChatSummary['preview'] }) {
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
