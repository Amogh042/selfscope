// Installs the .py modules from src/python into Pyodide's in-memory filesystem
// (once per page load) so worker code can `import schema`, `from parsers.whatsapp import …`.

import { pythonEngine } from './pythonEngine'

// Bundled as raw text at build time. Tests are not shipped.
const SOURCES = import.meta.glob(
  [
    '../python/*.py',
    '../python/parsers/*.py',
    '../python/selfscope_ml/*.py',
    '../python/enrich/*.py',
    '../python/analysis/*.py',
  ],
  {
    query: '?raw',
    import: 'default',
    eager: true,
  },
) as Record<string, string>

const ROOT = '/home/pyodide/selfscope'

// \`import tzdata\` makes Pyodide fetch its tz database (it ships without one), so
// zoneinfo.ZoneInfo("Asia/Kolkata") works instead of schema.py's fixed-offset fallback.
const INSTALL = `
import importlib, pathlib, sys
import tzdata
root = pathlib.Path(${JSON.stringify(ROOT)})
for rel, src in files.items():
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(src, encoding="utf-8")
    # drop stale copies (dev hot reload) so the next import picks up the new source
    sys.modules.pop(rel[:-3].replace("/", ".").removesuffix(".__init__"), None)
if str(root) not in sys.path:
    sys.path.insert(0, str(root))
importlib.invalidate_caches()
len(files)
`

let installed: Promise<void> | null = null

export function ensurePythonModules(): Promise<void> {
  installed ??= (async () => {
    const files: Record<string, string> = {}
    for (const [key, src] of Object.entries(SOURCES)) files[key.replace('../python/', '')] = src
    await pythonEngine.runPython(INSTALL, { files })
  })().catch((err) => {
    installed = null
    throw err
  })
  return installed
}
