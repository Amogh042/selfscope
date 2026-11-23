// HOW TO EXPORT YOUR DATA (#/guide): a few steps per source, linked from the landing and
// import screens. Menu names change between app versions; these match late 2026.

import type { ReactNode } from 'react'
import { Panel } from '../components/pixel'
import { SourceIcon } from '../components/SourceIcon'
import { useApp } from '../lib/appState'

interface Guide {
  source: 'whatsapp' | 'spotify' | 'youtube' | 'bank'
  title: string
  wait: string
  steps: ReactNode[]
  drop: string
}

const GUIDES: Guide[] = [
  {
    source: 'whatsapp',
    title: 'WHATSAPP',
    wait: 'instant, one chat at a time',
    steps: [
      'Open the chat (or group).',
      <>
        Android: <b>⋮ → More → Export chat</b>. iPhone: tap the chat name → <b>Export Chat</b>.
      </>,
      <>
        Choose <b>Without media</b>.
      </>,
      'Save or send the file to yourself (e.g. to your own laptop), then repeat for other chats.',
    ],
    drop: 'the .txt (Android) or the .zip (iPhone)',
  },
  {
    source: 'spotify',
    title: 'SPOTIFY',
    wait: 'Spotify emails a link, usually within a few days',
    steps: [
      <>
        On spotify.com, open your account → <b>Privacy settings</b>.
      </>,
      <>
        Under <b>Download your data</b>, tick <b>Account data</b> and request it (confirm the email).
      </>,
      'When the email arrives, download the zip.',
      <>
        Optional: <b>Extended streaming history</b> covers your whole history (takes longer); both formats work and overlaps are not
        counted twice.
      </>,
    ],
    drop: 'the zip, or the StreamingHistory*.json files inside it',
  },
  {
    source: 'youtube',
    title: 'YOUTUBE · GOOGLE TAKEOUT',
    wait: 'minutes to hours; Google emails a link',
    steps: [
      <>
        Go to takeout.google.com and click <b>Deselect all</b>.
      </>,
      <>
        Tick <b>YouTube and YouTube Music</b>. Under <b>All YouTube data included</b>, keep only <b>history</b>.
      </>,
      <>
        Under <b>Multiple formats</b>, set history to <b>JSON</b> (the default HTML can't be read).
      </>,
      <>
        <b>Next step → Export once → Create export</b>, then download the zip from the email.
      </>,
    ],
    drop: 'the Takeout .zip, or watch-history.json',
  },
  {
    source: 'bank',
    title: 'BANK · SBI',
    wait: 'instant',
    steps: [
      <>
        Log in to <b>OnlineSBI</b> (personal banking).
      </>,
      <>
        <b>My Accounts &amp; Profile → Account Statement</b>, pick the account.
      </>,
      <>
        Choose a date range of the <b>last 12 months</b> and download as <b>Excel</b>.
      </>,
      'SelfScope skips the statement header (name, address, account details) and masks long numbers.',
    ],
    drop: 'the .xls / .xlsx (not the PDF)',
  },
]

export default function ExportGuidePage() {
  const { href } = useApp()
  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-8 px-4 py-10 sm:px-6">
      <header className="flex flex-col gap-3">
        <h1 className="text-2xl text-orange [text-shadow:4px_4px_0_var(--color-orange-dark)] sm:text-3xl">EXPORT GUIDE</h1>
        <p className="font-pixel text-[10px] text-text">
          HOW TO GET YOUR DATA<span className="animate-pixel-blink text-orange">_</span>
        </p>
        <p className="max-w-2xl text-sm text-muted">
          Every app lets you download your own data. Request the exports below, then drop the files on the{' '}
          <a href={href('/import')} className="text-orange underline hover:text-orange-light">
            import screen
          </a>
          . You don't need all four; each panel unlocks on its own, and the cross-app insights need at least two. Menu names
          change between app versions, so look for similar wording.
        </p>
      </header>
      <div className="grid gap-6 md:grid-cols-2">
        {GUIDES.map((g) => (
          <Panel
            key={g.source}
            title={g.title}
            tag={
              <span className="flex size-8 items-center justify-center" aria-hidden>
                <SourceIcon source={g.source} size={28} />
              </span>
            }
          >
            <ol className="flex flex-col gap-2 text-sm leading-relaxed text-text">
              {g.steps.map((s, i) => (
                <li key={i} className="flex gap-3">
                  <span className="font-pixel text-[9px] leading-[1.9] text-orange">{i + 1}</span>
                  <span>{s}</span>
                </li>
              ))}
            </ol>
            <p className="font-mono text-[11px] text-muted">
              wait: {g.wait}
              <br />
              drop: <span className="text-orange-light">{g.drop}</span>
            </p>
          </Panel>
        ))}
      </div>
      <a href={href('/import')} className="pixel-btn self-start">
        ▶ GO TO IMPORT
      </a>
    </div>
  )
}
