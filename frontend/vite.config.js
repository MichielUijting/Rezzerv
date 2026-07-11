import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const backendTarget = process.env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8001'

function rezzervTerminologyPlugin() {
  return {
    name: 'rezzerv-terminology-artikelgroep',
    enforce: 'pre',
    transform(code, id) {
      if (!id.includes('/src/') || !/\.(jsx?|tsx?)$/.test(id)) return null
      if (!code.includes('Mijn artikel') && !code.includes('mijn artikel')) return null

      return {
        code: code
          .replaceAll('Mijn artikel', 'Artikelgroep')
          .replaceAll('mijn artikel', 'artikelgroep'),
        map: null,
      }
    },
  }
}

export default defineConfig({
  plugins: [rezzervTerminologyPlugin(), react()],
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
