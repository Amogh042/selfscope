// Runs the Python Spotify / YouTube parsers (src/python/parsers/) in the worker.
// All files of a source are merged into one frame kept in worker memory
// (session.EVENTS["spotify" | "youtube"]); only a summary + preview come back.

import { pythonEngine } from '../pythonEngine'
import { ensurePythonModules } from '../pythonModules'
import type { EventRow } from '../schema'

interface Common {
  first_date: string | null
  last_date: string | null
  /** Rows parsed from each file, keyed by file id (before de-duplication). */
  per_file: Record<string, number>
  duplicates_dropped: number
  skipped_records: number
  preview: EventRow[]
}

export interface SpotifySummary extends Common {
  plays: number
  music_plays: number
  podcast_plays: number
  hours: number
  skip_rate: number | null
  artists: number
  top_artists: { name: string; plays: number; hours: number }[]
  top_tracks: { title: string; artist: string; plays: number }[]
  formats: string[]
}

export interface YouTubeSummary extends Common {
  entries: number
  videos: number
  ads: number
  est_hours: number
  channels: number
  top_channels: { name: string; videos: number }[]
  shorts: number
  music: number
  removed: number
  system: number
  sessions: number
  unrecognised_prefix: number
  prefix_examples: string[]
}

const CODE = `
import session
session.import_files(source, files)
`

async function run<T>(source: 'spotify' | 'youtube', files: Record<string, string>): Promise<T> {
  await ensurePythonModules()
  const { result } = await pythonEngine.runPython(CODE, { source, files })
  return JSON.parse(result as string) as T
}

/** files: {file id: JSON text} */
export const parseSpotify = (files: Record<string, string>) => run<SpotifySummary>('spotify', files)
export const parseYouTube = (files: Record<string, string>) => run<YouTubeSummary>('youtube', files)
