// Turns dropped files (and the contents of dropped .zip files) into import items,
// detecting the source from the file name and the first few KB of content.
// Everything happens in this tab; files are only read, never uploaded.

import JSZip from 'jszip'

export type DetectedSource = 'whatsapp' | 'spotify' | 'youtube' | 'unknown'

export interface Candidate {
  /** Stable id: zip name + inner path, or file name + size. */
  id: string
  /** Shown on the card. */
  name: string
  /** Where it came from, e.g. "inside Takeout.zip". */
  origin?: string
  /** Bytes; unknown for files inside a zip until read. */
  size?: number
  source: DetectedSource
  /** WhatsApp chat name from the file name (e.g. "Priya"). */
  chatName?: string
  readText: () => Promise<string>
}

const WA_ANDROID = /^‎?\d{1,2}[./-]\d{1,2}[./-]\d{2,4},?[   ]\d{1,2}[:.]\d{2}.{0,12}[   ][-–][   ]/m
const WA_IOS = /^‎?\[\d{1,2}[./-]\d{1,2}[./-]\d{2,4},?[   ]\d{1,2}[:.]\d{2}/m

const basename = (p: string) => p.split(/[\\/]/).pop() ?? p

export function chatNameFromFilename(name: string): string | undefined {
  const m = /^WhatsApp Chat (?:with|-)\s*(.+?)(?:\s*\(\d+\))?\.(?:txt|zip)$/i.exec(basename(name))
  return m?.[1].trim()
}

export function detectSource(name: string, head: string): DetectedSource {
  const base = basename(name).toLowerCase()
  if (base.endsWith('.txt')) {
    if (base.startsWith('whatsapp chat') || base === '_chat.txt' || WA_ANDROID.test(head) || WA_IOS.test(head)) {
      return 'whatsapp'
    }
    return 'unknown'
  }
  if (base.endsWith('.json')) {
    if (/^streaminghistory.*\.json$|^streaming_history_audio.*\.json$/.test(base)) return 'spotify'
    if (base === 'watch-history.json') return 'youtube'
    if (head.includes('"msPlayed"') || head.includes('"ms_played"')) return 'spotify'
    if (head.includes('"header"') && head.includes('youtube.com/watch')) return 'youtube'
  }
  return 'unknown'
}

const IGNORED_IN_ZIP = /(^|\/)(__MACOSX\/|\.DS_Store$)/

/** Expand dropped files into candidates. Zips are opened in memory with JSZip. */
export async function expandFiles(files: File[]): Promise<{ candidates: Candidate[]; ignoredInZips: number }> {
  const candidates: Candidate[] = []
  let ignoredInZips = 0

  for (const file of files) {
    if (!file.name.toLowerCase().endsWith('.zip')) {
      const head = await file.slice(0, 4096).text()
      const source = detectSource(file.name, head)
      candidates.push({
        id: `${file.name}:${file.size}`,
        name: file.name,
        size: file.size,
        source,
        chatName: source === 'whatsapp' ? chatNameFromFilename(file.name) ?? stripExt(file.name) : undefined,
        readText: () => file.text(),
      })
      continue
    }

    let zip: JSZip
    try {
      zip = await JSZip.loadAsync(file)
    } catch {
      candidates.push({ id: `${file.name}:${file.size}`, name: file.name, size: file.size, source: 'unknown', readText: async () => '' })
      continue
    }
    const entries = Object.values(zip.files).filter((e) => !e.dir && !IGNORED_IN_ZIP.test(e.name))

    // iOS WhatsApp export: a zip with _chat.txt (+ media). Treat the zip as one chat.
    const chat = entries.find((e) => basename(e.name) === '_chat.txt')
    if (chat) {
      candidates.push({
        id: `${file.name}:${file.size}`,
        name: file.name,
        size: file.size,
        source: 'whatsapp',
        chatName: chatNameFromFilename(file.name) ?? stripExt(file.name),
        readText: () => chat.async('string'),
      })
      ignoredInZips += entries.length - 1
      continue
    }

    let found = 0
    let skipped = 0
    for (const entry of entries) {
      // Name first; only decompress small-ish text entries when the name doesn't decide.
      let source = detectSource(entry.name, '')
      if (source === 'unknown' && /\.(txt|json)$/i.test(entry.name)) {
        source = detectSource(entry.name, (await entry.async('string')).slice(0, 4096))
      }
      if (source === 'unknown') {
        skipped++
        continue
      }
      found++
      candidates.push({
        id: `${file.name}/${entry.name}`,
        name: basename(entry.name),
        origin: `inside ${file.name}`,
        source,
        chatName: source === 'whatsapp' ? chatNameFromFilename(entry.name) ?? stripExt(basename(entry.name)) : undefined,
        readText: () => entry.async('string'),
      })
    }
    if (found > 0) ignoredInZips += skipped
    else candidates.push({ id: `${file.name}:${file.size}`, name: file.name, size: file.size, source: 'unknown', readText: async () => '' })
  }
  return { candidates, ignoredInZips }
}

function stripExt(name: string) {
  return basename(name).replace(/\.[^.]+$/, '')
}

/** Fetch the bundled synthetic demo files (copied from data/samples by scripts/copy-demo.mjs). */
export async function fetchDemoFiles(): Promise<File[]> {
  const base = `${import.meta.env.BASE_URL}demo/`
  const res = await fetch(`${base}manifest.json`)
  if (!res.ok) throw new Error('Demo data not found — run `npm run copy-demo` in web/')
  const { files } = (await res.json()) as { files: { path: string }[] }
  return Promise.all(
    files.map(async ({ path }) => {
      const r = await fetch(base + path.split('/').map(encodeURIComponent).join('/'))
      if (!r.ok) throw new Error(`Could not load demo file ${path}`)
      return new File([await r.blob()], basename(path))
    }),
  )
}
