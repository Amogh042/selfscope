// Landing screen (#/ while this database is empty, or #/welcome): the pitch, the privacy
// promise and two ways in. Python starts loading here, so the first analysis is quicker.

import { useEffect } from 'react'
import { usePythonStatus } from '../components/AnalysisProgress'
import { Panel } from '../components/pixel'
import { SourceIcon } from '../components/SourceIcon'
import { useApp } from '../lib/appState'
import { pythonEngine } from '../lib/pythonEngine'
import { ensurePythonModules } from '../lib/pythonModules'

const SOURCES = [
  ['spotify', 'SPOTIFY', 'what you listen to, and its mood'],
  ['youtube', 'YOUTUBE', 'what you watch, by topic'],
  ['whatsapp', 'WHATSAPP', 'how much you chat, and its mood (never the text)'],
  ['bank', 'BANK · SBI', 'where your money goes, by category'],
] as const

export default function LandingPage() {
  const { href } = useApp()
  const py = usePythonStatus()

  // Start the Python runtime now (tens of MB, cached by the browser afterwards).
  useEffect(() => {
    pythonEngine
      .init()
      .then(() => ensurePythonModules())
      .catch(() => {})
  }, [])

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-10 px-4 py-12 sm:px-6 sm:py-16">
      <section className="flex flex-col gap-5">
        <h1 className="text-3xl text-orange [text-shadow:4px_4px_0_var(--color-orange-dark)] sm:text-5xl">SELFSCOPE</h1>
        <p className="max-w-3xl text-lg leading-snug text-text sm:text-xl">
          One dashboard for your music, videos, chats and spending, with the patterns <em>across</em> them, from the export files the
          apps already give you.
        </p>
        <p className="font-pixel text-[10px] text-muted">
          PRESS START<span className="animate-pixel-blink text-orange">_</span>
        </p>
      </section>

      <div className="grid gap-5 sm:grid-cols-2">
        <a href="#/import?mode=demo&range=all&demo=load" className="pixel-btn flex flex-col items-start gap-3 py-6 text-left">
          <span className="text-[14px]">★ TRY THE DEMO</span>
          <span className="font-mono text-xs leading-relaxed">One synthetic year of data, loaded into a separate demo database.</span>
        </a>
        <a href="#/import?mode=real" className="pixel-btn pixel-btn-secondary flex flex-col items-start gap-3 py-6 text-left">
          <span className="text-[14px]">▶ IMPORT MY DATA</span>
          <span className="font-mono text-xs leading-relaxed text-text">Drop your own exports. Not sure how to get them?</span>
        </a>
      </div>
      <p className="-mt-6 font-mono text-xs text-muted">
        <a href={href('/guide')} className="text-orange underline hover:text-orange-light">
          How to export your data
        </a>{' '}
        · WhatsApp, Spotify, Google Takeout, SBI, a few steps each.
      </p>

      <Panel title="YOUR DATA NEVER LEAVES THIS BROWSER">
        <ul className="flex flex-col gap-2 text-sm leading-relaxed text-text">
          <li>■ Files are read and analysed inside this tab (Python and SQL running in your browser). There is no server.</li>
          <li>■ Nothing is uploaded, no analytics, no tracking. The only downloads are the app itself and the Python runtime.</li>
          <li>■ Everything is saved in this browser's own storage. DATA → WIPE ALL DATA deletes it.</li>
        </ul>
        <p className="font-mono text-[11px] text-muted">
          Python engine:{' '}
          <span className={py.status === 'ready' ? 'text-xp' : py.status === 'error' ? 'text-danger' : 'text-orange-light'}>
            {py.status === 'ready' ? 'READY' : py.status === 'error' ? 'ERROR' : 'LOADING'}
            {py.status !== 'ready' && py.status !== 'error' && <span className="animate-pixel-blink">_</span>}
          </span>{' '}
          · {py.status === 'ready' ? 'loaded in the background while you read this' : py.detail}
        </p>
      </Panel>

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {SOURCES.map(([src, name, what]) => (
          <div key={src} className="flex items-center gap-3 border-2 border-orange-dark bg-panel p-3">
            <div className="flex size-12 shrink-0 items-center justify-center border-2 border-orange-dark bg-bg">
              <SourceIcon source={src} />
            </div>
            <div className="flex min-w-0 flex-col gap-1">
              <span className="font-pixel text-[8px] text-muted">{name}</span>
              <span className="text-xs leading-snug text-text">{what}</span>
            </div>
          </div>
        ))}
      </section>
    </div>
  )
}
