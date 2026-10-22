import { useEffect, useState } from 'react'
import { useMobileAppViewport } from '../../app/mobileViewport.js'
import DesktopKassaPage from '../receipts/KassaPage.jsx'
import { fetchJson } from '../stores/storeImportShared.jsx'
import MobileKassa from './MobileKassa.jsx'

export default function KassaPage() {
  const isMobile = useMobileAppViewport()
  const [syncRevision, setSyncRevision] = useState(0)
  const [scannerProvider, setScannerProvider] = useState('inhuis')

  useEffect(() => {
    let cancelled = false
    fetchJson('/api/household/store-import-settings')
      .then((settings) => {
        if (!cancelled) setScannerProvider(settings?.receipt_scanner_provider || 'inhuis')
      })
      .catch(() => {
        if (!cancelled) setScannerProvider('inhuis')
      })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    let cancelled = false
    let inFlight = false
    let lastAttempt = 0
    const minimumInterval = 15 * 60 * 1000

    async function syncAlbertHeijn() {
      // The existing session-scoped AH import only runs while Kassa is open.
      // Hidden pages cannot safely promise permanent/background syncing.
      if (cancelled || inFlight || document.visibilityState === 'hidden') return
      const now = Date.now()
      if (now - lastAttempt < minimumInterval) return
      lastAttempt = now
      inFlight = true
      try {
        const status = await fetchJson('/api/receipts/retailers/ah/status')
        if (!status?.connected || cancelled) return
        const result = await fetchJson('/api/receipts/retailers/ah/sync', {
          method: 'POST',
          body: JSON.stringify({ limit: 100 }),
        })
        if (!cancelled && Number(result?.receipts_processed || 0) > 0) {
          setSyncRevision((value) => value + 1)
        }
      } catch {
        // Other receipt sources and Kassa stay available when AH is offline.
        // Failed AH receipts remain retryable through the existing service.
      } finally {
        inFlight = false
      }
    }

    const onVisible = () => {
      if (document.visibilityState === 'visible') syncAlbertHeijn()
    }
    syncAlbertHeijn()
    const interval = window.setInterval(syncAlbertHeijn, minimumInterval)
    document.addEventListener('visibilitychange', onVisible)
    window.addEventListener('focus', onVisible)
    return () => {
      cancelled = true
      window.clearInterval(interval)
      document.removeEventListener('visibilitychange', onVisible)
      window.removeEventListener('focus', onVisible)
    }
  }, [])

  return isMobile
    ? <MobileKassa key={`mobile-${syncRevision}`} scannerProvider={scannerProvider} />
    : <DesktopKassaPage key={`desktop-${syncRevision}`} scannerProvider={scannerProvider} />
}
