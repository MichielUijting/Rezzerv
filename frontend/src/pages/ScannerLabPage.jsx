import { useMemo, useState } from 'react'
import AppShell from '../app/AppShell.jsx'
import Card from '../ui/Card.jsx'
import Button from '../ui/Button.jsx'
import Input from '../ui/Input.jsx'
import useBarcodeScanner from '../lib/useBarcodeScanner.js'

function getScannerLogBuffer() {
  if (typeof window === 'undefined' || !Array.isArray(window.__rezzervScannerLog)) return []
  return window.__rezzervScannerLog
}

export default function ScannerLabPage() {
  const [barcodeValue, setBarcodeValue] = useState('')
  const [lastDetected, setLastDetected] = useState('')
  const [manualMessage, setManualMessage] = useState('')
  const [, forceRefresh] = useState(0)

  const {
    videoRef,
    isOpen,
    cameraState,
    cameraMeta,
    availableCameras,
    startScanner,
    stopScanner,
    switchCamera,
  } = useBarcodeScanner({
    screenContext: 'ScannerLab',
    onDetected: async (detectedBarcode, { logEvent }) => {
      const normalized = String(detectedBarcode || '').trim()
      logEvent('BARCODE_NORMALIZED', { value: normalized })
      logEvent('BARCODE_FIELD_BEFORE_UPDATE', { value: barcodeValue })
      setBarcodeValue(normalized)
      setLastDetected(normalized)
      setManualMessage(`Barcode gedetecteerd: ${normalized}`)
      logEvent('BARCODE_FIELD_UPDATED', { value: normalized, source: 'scanner-lab' })
      window.setTimeout(() => {
        logEvent('BARCODE_FIELD_AFTER_UPDATE', { value: normalized, source: 'scanner-lab' })
        forceRefresh((value) => value + 1)
      }, 0)
    },
  })

  const scannerLog = useMemo(() => getScannerLogBuffer(), [barcodeValue, cameraState.status, cameraMeta.decodeAttempts, isOpen, manualMessage])

  function refreshLogView() {
    forceRefresh((value) => value + 1)
  }

  function clearLog() {
    if (typeof window !== 'undefined') {
      window.__rezzervScannerLog = []
    }
    forceRefresh((value) => value + 1)
  }

  function handleManualChange(event) {
    const nextValue = event.target.value
    setBarcodeValue(nextValue)
    setManualMessage('Barcode handmatig bijgewerkt.')
  }

  return (
    <AppShell title="Scanner Lab" showExit={false}>
      <Card>
        <div style={{ display: 'grid', gap: '16px' }}>
          <div>
            <strong>Doel</strong>
            <div>Geïsoleerde scanner-test zonder automation, enrich of overige backend-afhankelijkheid.</div>
          </div>

          <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
            <Button onClick={() => startScanner(cameraMeta.deviceId || '')}>Barcode scannen</Button>
            <Button variant="secondary" onClick={() => stopScanner(false, 'scanner-lab-stop')}>Scanner stoppen</Button>
            <Button variant="secondary" onClick={switchCamera} disabled={availableCameras.length < 2}>Camera wisselen</Button>
            <Button variant="secondary" onClick={refreshLogView}>Log verversen</Button>
            <Button variant="secondary" onClick={clearLog}>Log wissen</Button>
          </div>

          <div style={{ display: 'grid', gap: '8px' }}>
            <div><strong>Status:</strong> {cameraState.status || '-'}</div>
            <div><strong>Melding:</strong> {cameraState.message || '-'}</div>
            <div><strong>Camera:</strong> {cameraMeta.label || '-'} {cameraMeta.deviceId ? `(${cameraMeta.deviceId})` : ''}</div>
            <div><strong>Decodepogingen:</strong> {cameraMeta.decodeAttempts}</div>
            <div><strong>Beschikbare camera’s:</strong> {availableCameras.length}</div>
            <div><strong>Laatst gedetecteerd:</strong> {lastDetected || '-'}</div>
          </div>

          <div style={{ display: 'grid', gap: '8px' }}>
            <label htmlFor="scanner-lab-barcode"><strong>Barcodeveld</strong></label>
            <Input id="scanner-lab-barcode" value={barcodeValue} onChange={handleManualChange} placeholder="Barcode verschijnt hier na detectie" />
            <div>{manualMessage || 'Nog geen barcode gedetecteerd.'}</div>
          </div>

          <div style={{ display: isOpen ? 'block' : 'none' }}>
            <video
              ref={videoRef}
              autoPlay
              muted
              playsInline
              style={{ width: '100%', maxWidth: '420px', background: '#000', borderRadius: '12px' }}
            />
          </div>

          <div>
            <strong>Scannerlog ({scannerLog.length})</strong>
            <pre style={{ maxHeight: '360px', overflow: 'auto', padding: '12px', background: '#f6f6f6', borderRadius: '12px', whiteSpace: 'pre-wrap' }}>
              {JSON.stringify(scannerLog, null, 2)}
            </pre>
          </div>
        </div>
      </Card>
    </AppShell>
  )
}
