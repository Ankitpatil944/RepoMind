import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// In dev the UI runs on :5173 and proxies API calls to the FastAPI server, so
// the backend needs no CORS configuration. In production the API serves ui/dist.
const API = process.env.REPOMIND_API ?? 'http://127.0.0.1:8000'
const proxied = ['/repos', '/ask', '/search', '/explain', '/ingest', '/health']

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: Object.fromEntries(proxied.map((p) => [p, { target: API, changeOrigin: true }])),
  },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
