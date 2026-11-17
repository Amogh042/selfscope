import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  // The Pyodide worker is an ES module worker (it dynamically imports pyodide.mjs).
  worker: { format: 'es' },
  // DuckDB-WASM ships its own worker + .wasm files; don't let the dep optimizer rewrite them.
  optimizeDeps: { exclude: ['@duckdb/duckdb-wasm'] },
})
