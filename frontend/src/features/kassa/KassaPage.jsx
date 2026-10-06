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

    async function syncAlbertHeijn() {
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
        // AH is an optional source. Kassa remains usable when the upstream
        // service is unavailable; the user can retry from Winkelkoppelingen.
      }
    }

    syncAlbertHeijn()
    return () => {
      cancelled = true
    }
  }, [])

  return isMobile
    ? <MobileKassa key={`mobile-${syncRevision}`} scannerProvider={scannerProvider} />
    : <DesktopKassaPage key={`desktop-${syncRevision}`} scannerProvider={scannerProvider} />
}
