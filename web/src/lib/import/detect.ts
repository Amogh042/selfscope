// Turns dropped files (and the contents of dropped .zip files) into import items,
// detecting the source from the file name and the first few KB of content.
// Everything happens in this tab; files are only read, never uploaded.

import JSZip from 'jszip'

export type DetectedSource = 'whatsapp' | 'spotify' | 'youtube' | 'bank' | 'unknown'

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
  /** Recognised but not parseable as-is; shown on the card instead of parsing. */
  problem?: string
  readText: () => Promise<string>
  /** Raw bytes (bank statements are binary: XLSX / XLS). */
  readBytes: () => Promise<Uint8Array>
}

export const HTML_TAKEOUT_PROBLEM = 'Re-export from Google Takeout with History format set to JSON.'
export const PDF_STATEMENT_PROBLEM = 'Please download the statement as Excel from OnlineSBI (PDF not supported yet)'

const OLE2 = [0xd0, 0xcf, 0x11, 0xe0, 0xa1, 0xb1, 0x1a, 0xe1]
const TXN_DATE = /txn\s*date/i

/**
 * Bank statements: OnlineSBI ".xls" files may really be binary XLS, XLSX, HTML or
 * tab-separated text, so look at the bytes. A statement has a "Txn Date" header row.
 */
async function looksLikeStatement(name: string, blob: Blob): Promise<boolean> {
  const lower = name.toLowerCase()
  if (!/\.(xlsx?|csv|txt)$/.test(lower)) return false
  const head = new Uint8Array(await blob.slice(0, 8).arrayBuffer())
  if (OLE2.every((b, i) => head[i] === b)) return true // binary .xls: can't peek inside cheaply
  if (head[0] === 0x50 && head[1] === 0x4b) {
    // XLSX: look for "Txn Date" in the shared strings / first sheet
    try {
      const zip = await JSZip.loadAsync(blob)
      for (const path of ['xl/sharedStrings.xml', 'xl/worksheets/sheet1.xml']) {
        const f = zip.file(path)
        if (f && TXN_DATE.test(await f.async('string'))) return true
      }
    } catch {
      return false
    }
    return false
  }
  return TXN_DATE.test(await blob.slice(0, 65536).text())
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
  // Takeout's default HTML history: recognised so the card can say how to get JSON instead.
  if (base === 'watch-history.html') return 'youtube'
  if (base.endsWith('.pdf')) return 'bank' // shown with PDF_STATEMENT_PROBLEM
  if (base.endsWith('.json')) {
    if (/^streaminghistory.*\.json$|^streaming_history_audio.*\.json$|^endsong_\d+\.json$/.test(base)) return 'spotify'
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
      let source = detectSource(file.name, head)
      if ((source === 'unknown' || /\.(xlsx?|csv)$/i.test(file.name)) && (await looksLikeStatement(file.name, file))) {
        source = 'bank'
      }
      candidates.push({
        id: `${file.name}:${file.size}`,
        name: file.name,
        size: file.size,
        source,
        chatName: source === 'whatsapp' ? chatNameFromFilename(file.name) ?? stripExt(file.name) : undefined,
        problem: problemFor(file.name),
        readText: () => file.text(),
        readBytes: async () => new Uint8Array(await file.arrayBuffer()),
      })
      continue
    }

    let zip: JSZip
    try {
      zip = await JSZip.loadAsync(file)
    } catch {
      candidates.push(unknownCandidate(file))
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
        readBytes: () => chat.async('uint8array'),
      })
      ignoredInZips += entries.length - 1
      continue
    }

    let found = 0
    let skipped = 0
    for (const entry of entries) {
      // Inside zips (e.g. a whole Takeout) match by file name only, so unrelated
      // entries are ignored without being decompressed.
      let source = detectSource(entry.name, '')
      if (source === 'unknown' && /\.xlsx?$/i.test(entry.name) && /statement|sbi|account/i.test(entry.name)) {
        source = 'bank'
      }
      if (source === 'unknown' || (source === 'bank' && /\.pdf$/i.test(entry.name))) {
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
        problem: problemFor(entry.name),
        readText: () => entry.async('string'),
        readBytes: () => entry.async('uint8array'),
      })
    }
    if (found > 0) ignoredInZips += skipped
    else candidates.push(unknownCandidate(file))
  }
  return { candidates, ignoredInZips }
}

function problemFor(name: string): string | undefined {
  const lower = basename(name).toLowerCase()
  if (lower.endsWith('.html')) return HTML_TAKEOUT_PROBLEM
  if (lower.endsWith('.pdf')) return PDF_STATEMENT_PROBLEM
  return undefined
}

function unknownCandidate(file: File): Candidate {
  return {
    id: `${file.name}:${file.size}`,
    name: file.name,
    size: file.size,
    source: 'unknown',
    readText: async () => '',
    readBytes: async () => new Uint8Array(),
  }
}

function stripExt(name: string) {
  return basename(name).replace(/\.[^.]+$/, '')
}

/** Exam periods that come pre-tagged with the demo data (data/samples/periods.json). */
export async function fetchDemoPeriods(): Promise<{ label: string; start: string; end: string }[]> {
  const r = await fetch(`${import.meta.env.BASE_URL}demo/periods.json`)
  if (!r.ok) return []
  return ((await r.json()) as { periods: { label: string; start: string; end: string }[] }).periods
}

/** Fetch the bundled synthetic demo files (copied from data/samples by scripts/copy-demo.mjs). */
export async function fetchDemoFiles(): Promise<File[]> {
  const base = `${import.meta.env.BASE_URL}demo/`
  const res = await fetch(`${base}manifest.json`)
  if (!res.ok) throw new Error('Demo data not found — run `npm run copy-demo` in web/')
  const { files } = (await res.json()) as { files: { path: string }[] }
  return Promise.all(
    files.filter(({ path }) => path !== 'periods.json').map(async ({ path }) => {
      const r = await fetch(base + path.split('/').map(encodeURIComponent).join('/'))
      if (!r.ok) throw new Error(`Could not load demo file ${path}`)
      return new File([await r.blob()], basename(path))
    }),
  )
}
