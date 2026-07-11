import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const backendTarget = process.env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8001'

function rezzervArticleGroupTerminology() {
  const targetFiles = [
    '/src/features/stores/StoreBatchDetailPage.jsx',
    '/src/features/externalDatabases/ExternalDatabasesPage.jsx',
  ]

  return {
    name: 'rezzerv-article-group-terminology',
    enforce: 'pre',
    transform(code, id) {
      const normalizedId = String(id || '').replace(/\\/g, '/')
      if (!targetFiles.some((target) => normalizedId.endsWith(target))) return null

      const updated = code
        .replaceAll('Mijn artikel', 'Artikelgroep')
        .replaceAll('mijn artikel', 'artikelgroep')

      if (updated === code) return null
      return { code: updated, map: null }
    },
  }
}

export default defineConfig({
  plugins: [react(), rezzervArticleGroupTerminology()],
  server: {
    port: 5180,
    strictPort: true,
    host: true,
    proxy: {
      '/api': {
        target: backendTarget,
        changeOrigin: true,
      },
    },
  },
})
