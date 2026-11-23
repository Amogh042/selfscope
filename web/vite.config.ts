import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { readFileSync } from 'node:fs'
import { defineConfig, type Plugin } from 'vite'

// Security headers live in vercel.json (one source of truth). `vite preview` serves the build
// with the same headers, and the build also gets the CSP as a <meta> tag for hosts that can't
// set headers (GitHub Pages). The CSP is what makes "no data leaves the browser" enforced by
// the browser itself: scripts and requests may only go to this origin and the Pyodide CDN.
const vercel = JSON.parse(readFileSync(new URL('./vercel.json', import.meta.url), 'utf8')) as {
  headers: { headers: { key: string; value: string }[] }[]
}
const HEADERS = Object.fromEntries(vercel.headers[0].headers.map((h) => [h.key, h.value]))
// frame-ancestors is not allowed in a <meta> CSP (browsers ignore it there)
const META_CSP = HEADERS['Content-Security-Policy']
  .split(';')
  .map((d) => d.trim())
  .filter((d) => d && !d.startsWith('frame-ancestors'))
  .join('; ')

function cspMeta(): Plugin {
  return {
    name: 'selfscope-csp-meta',
    apply: 'build', // the dev server needs inline HMR scripts + websockets, so dev runs without it
    transformIndexHtml: (html) =>
      html.replace('<meta charset="UTF-8" />', `<meta charset="UTF-8" />\n    <meta http-equiv="Content-Security-Policy" content="${META_CSP}" />`),
  }
}

// https://vite.dev/config/
export default defineConfig({
  // Relative base: the same build works at a domain root (Vercel) and under a sub-path
  // (GitHub Pages: /<repo>/). Routing is in the URL hash, so no server rewrites are needed.
  base: './',
  plugins: [react(), tailwindcss(), cspMeta()],
  // The Pyodide worker is an ES module worker (it dynamically imports pyodide.mjs).
  worker: { format: 'es' },
  // DuckDB-WASM ships its own worker + .wasm files; don't let the dep optimizer rewrite them.
  optimizeDeps: { exclude: ['@duckdb/duckdb-wasm'] },
  preview: { headers: HEADERS },
})
