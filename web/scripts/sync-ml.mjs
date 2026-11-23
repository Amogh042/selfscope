// Copies the shared ML feature code from ml/selfscope_ml/ (the source of truth) into
// web/src/python/selfscope_ml/ so Pyodide can import it. Runs before `npm run dev` and
// `npm run build`; a pytest (test_categoriser.py) fails if the two copies ever differ.
// Edit ml/selfscope_ml/, never the copy.

import { copyFileSync, mkdirSync, readdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const webDir = join(dirname(fileURLToPath(import.meta.url)), '..')
const src = join(webDir, '..', 'ml', 'selfscope_ml')
const dest = join(webDir, 'src', 'python', 'selfscope_ml')

mkdirSync(dest, { recursive: true })
const files = readdirSync(src).filter((f) => f.endsWith('.py'))
for (const f of files) copyFileSync(join(src, f), join(dest, f))
console.log(`[sync-ml] ${files.length} files: ml/selfscope_ml -> web/src/python/selfscope_ml`)
