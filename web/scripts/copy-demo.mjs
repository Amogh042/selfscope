// Copies the SYNTHETIC demo data (data/samples) into web/public/demo so Vite can
// serve it for the "LOAD DEMO DATA" button, and writes a manifest of the files.
// Runs automatically before `npm run dev` and `npm run build`.
// It only ever reads data/samples — never data/private.

import { cpSync, existsSync, readdirSync, rmSync, statSync, writeFileSync } from 'node:fs'
import { dirname, join, relative, sep } from 'node:path'
import { fileURLToPath } from 'node:url'

const webDir = join(dirname(fileURLToPath(import.meta.url)), '..')
const src = join(webDir, '..', 'data', 'samples')
const dest = join(webDir, 'public', 'demo')

if (!existsSync(src)) {
  console.warn(`[copy-demo] ${src} not found, skipping`)
  process.exit(0)
}

rmSync(dest, { recursive: true, force: true })
cpSync(src, dest, {
  recursive: true,
  filter: (p) => !/(^|[\\/])(README\.md|\.DS_Store)$/.test(p),
})

const files = []
const walk = (dir) => {
  for (const name of readdirSync(dir).sort()) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) walk(p)
    else files.push({ path: relative(dest, p).split(sep).join('/'), size: statSync(p).size })
  }
}
walk(dest)
writeFileSync(join(dest, 'manifest.json'), JSON.stringify({ files }, null, 2))
console.log(`[copy-demo] ${files.length} demo files -> public/demo`)
