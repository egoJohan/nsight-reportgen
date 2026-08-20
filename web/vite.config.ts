import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'
import type { IncomingMessage } from 'http'

const backend = 'http://127.0.0.1:8200'

// Mirrors web/nginx.conf's $nsight_html_nav map: a browser navigating to a
// client-side route (e.g. a refresh on /customers/:id) asks for text/html —
// serve the SPA so the route resolves client-side. fetch/XHR calls (Accept:
// */*, application/json) fall through to the backend. Without this, adding
// the proxy below would silently break "refresh the page" on any route the
// SPA and the API share, in dev only (nginx already gets this right).
function bypassHtmlNav(req: IncomingMessage) {
  return /text\/html/i.test(req.headers.accept ?? '') ? '/index.html' : undefined
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [tailwindcss(), react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    // Same-origin in dev too (spec §5.4): a SameSite=Strict session cookie
    // is never sent cross-origin, and server.py's CORS deliberately does not
    // allow credentialed cross-origin requests either. Proxying here — not
    // relaxing either of those — is the fix. Mirrors the prefix list in
    // web/nginx.conf; add a prefix in both places when the API gains one.
    proxy: {
      '/cases': { target: backend, bypass: bypassHtmlNav },
      '/customers': { target: backend, bypass: bypassHtmlNav },
      '/settings': { target: backend, bypass: bypassHtmlNav },
      '/materials': backend,
      '/chart-types': backend,
      '/reports': backend,
      '/auth': backend,
    },
  },
})
