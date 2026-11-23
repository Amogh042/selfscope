// Enriches stored YouTube / Spotify / WhatsApp rows in the Python worker
// (src/python/enrich/): video topic, song mood + language, message sentiment.
// Only rows not yet enriched by the current version are processed, so after an import
// just the new rows are done. Curated resources come from public/data/ (static files).

import { pythonEngine } from './pythonEngine'
import { ensurePythonModules } from './pythonModules'
import { store, type Mode } from './store'

/** Must match ENRICH_VERSION in src/python/enrich/__init__.py. */
export const ENRICH_VERSION = '1'

const FILES = ['youtube_channels.json', 'song_moods.json', 'sentiment_lexicon.json'] as const
let resources: Promise<string[]> | null = null
function loadResources() {
  resources ??= Promise.all(
    FILES.map((f) =>
      fetch(`${import.meta.env.BASE_URL}data/${f}`).then((r) => {
        if (!r.ok) throw new Error(`missing enrichment data: ${f}`)
        return r.text()
      }),
    ),
  ).catch((e) => {
    resources = null
    throw e
  })
  return resources
}

const CODE = `from enrich import runner
if not runner.loaded():
    runner.load_resources(channels_json, songs_json, lexicon_json)
runner.enrich_events_json(events_json)`

let inFlight: Promise<void> | null = null

export function ensureEnriched(mode: Mode): Promise<void> {
  inFlight ??= (async () => {
    try {
      const rows = await store.query('enrich_pending', { enrich_version: ENRICH_VERSION })
      if (!rows.length) return
      const [channels, songs, lexicon] = await loadResources()
      await ensurePythonModules()
      const { result } = await pythonEngine.runPython(CODE, {
        events_json: JSON.stringify(rows),
        channels_json: channels,
        songs_json: songs,
        lexicon_json: lexicon,
      })
      const out = JSON.parse(result as string) as { predictions: unknown[] }
      await store.applyEnrichment(mode, JSON.stringify(out.predictions))
    } catch (e) {
      console.warn('[enrich]', e)
    } finally {
      inFlight = null
    }
  })()
  return inFlight
}
