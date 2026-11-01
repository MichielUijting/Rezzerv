import { useEffect, useRef } from 'react'
import Button from '../../ui/Button'
import BarcodeScannerModal from '../barcodes/BarcodeScannerModal'
import useBarcodeScanner from '../../lib/useBarcodeScanner'
import { useAppFeedback } from '../../ui/AppFeedbackProvider'

/** Camera-only input for the already-authorized ED2 manual barcode confirmation.
 * Never writes a receipt, catalog product or inventory record on detection. */
export default function Ed2BarcodeScanner({ receiptItemId, disabled = false, onScanned }) {
  const photoInputRef = useRef(null)
  const { showFeedback } = useAppFeedback()
  const {
    videoRef, isOpen, cameraState, cameraMeta, availableCameras,
    startScanner, stopScanner, switchCamera, scanImageFile,
  } = useBarcodeScanner({
    screenContext: 'Externe databases 2 bonartikelbarcode',
    onDetected: (detectedBarcode) => {
      const code = String(detectedBarcode || '').trim()
      if (!/^(?:\d{8}|\d{12,14})$/.test(code)) {
        showFeedback({ variant: 'error', message: 'Geen geldige EAN/GTIN gelezen. Probeer opnieuw of vul de barcode handmatig in.' })
        return
      }
      onScanned(code)
    },
  })

  // ED2 presents scanner errors and no-read warnings through the shared
  // Melding overlay, never as inline scanner-status banners.
  useEffect(() => {
    if ((cameraState.status !== 'error' && cameraState.status !== 'not_found') || !cameraState.message) return
    showFeedback({
      variant: cameraState.status === 'error' ? 'error' : 'warning',
      title: 'Melding',
      message: cameraState.message,
      testId: 'ed2-barcode-scanner-message',
    })
  }, [cameraState.status, cameraState.message, showFeedback])

  function choosePhoto() {
    if (disabled) return
    stopScanner()
    photoInputRef.current?.click()
  }

  async function handlePhotoChange(event) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file || disabled) return
    const recognized = await scanImageFile(file)
    if (!recognized) {
      showFeedback({ variant: 'warning', message: 'Geen barcode in de foto herkend. Probeer een scherpere foto of voer de barcode handmatig in.' })
    }
  }

  function openScanner() {
    if (disabled) return
    // Keep one predictable action: let the shared scanner explain a camera
    // failure inside its dialog rather than unexpectedly opening a file picker.
    void startScanner()
  }

  return (
    <>
      <Button type="button" variant="secondary" disabled={disabled} onClick={openScanner}
        data-testid="ed2-barcode-scan">Barcode scannen</Button>
      <input ref={photoInputRef} type="file" accept="image/*" capture="environment"
        aria-label="Foto van barcode kiezen" data-testid="ed2-barcode-photo-input"
        style={{ display: 'none' }} onChange={handlePhotoChange} />
      <BarcodeScannerModal open={isOpen || cameraState.status === 'error'}
        title="Barcode scannen voor bonartikel"
        videoRef={videoRef} cameraState={cameraState} cameraMeta={cameraMeta}
        availableCameras={availableCameras} onSwitchCamera={switchCamera}
        onRetry={() => void startScanner()}
        onChoosePhoto={cameraState.status === 'error' ? choosePhoto : undefined}
        hideInlineFeedback
        onClose={() => stopScanner()} />
    </>
  )
}
