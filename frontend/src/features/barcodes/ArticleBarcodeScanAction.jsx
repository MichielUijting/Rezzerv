import { useRef, useState } from 'react'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'
import Button from '../../ui/Button.jsx'
import { useMobileAppViewport } from '../../app/mobileViewport.js'
import useBarcodeScanner from '../../lib/useBarcodeScanner.js'
import BarcodeScannerModal from './BarcodeScannerModal.jsx'

/**
 * Shared, mobile-only barcode action for one *known* article.
 * A scan never changes any identity. The parent's existing authorized writer
 * receives the scanned value only after the user explicitly confirms.
 *
 * onConfirm(barcode, { replace, expectedOldBarcode }) must be fail-closed on
 * outdated/conflicting ownership and must not mutate receipt/stock quantities.
 */
export default function ArticleBarcodeScanAction({
  articleName, currentBarcode = '', onConfirm, prepareConfirmation = null, disabled = false,
  testId = 'article-barcode-scan', title = 'Barcode scannen',
}) {
  const mobile = useMobileAppViewport()
  const { showFeedback } = useAppFeedback()
  const photoRef = useRef(null)
  const [saving, setSaving] = useState(false)
  const name = String(articleName || 'Dit artikel').trim()
  const existing = String(currentBarcode || '').trim()
  const {
    videoRef, isOpen, cameraState, cameraMeta, availableCameras,
    startScanner, startCompatibleCamera, stopScanner, switchCamera, scanImageFile,
  } = useBarcodeScanner({
    timeoutMs: 0,
    screenContext: 'Barcode voor ' + name,
    onDetected: async (rawBarcode) => {
      const barcode = String(rawBarcode || '').trim()
      if (!/^(?:\d{8}|\d{12,14})$/.test(barcode)) {
        showFeedback({ variant: 'warning', message: 'Geen geldige barcode gelezen. Probeer opnieuw.' })
        return
      }
      if (barcode === existing) {
        showFeedback({
          variant: 'info',
          title: 'Barcode is al bekend',
          message: name + ' heeft al barcode ' + barcode + '. Er is niets gewijzigd.',
        })
        return
      }
      const replace = Boolean(existing)
      let prepared = null
      if (typeof prepareConfirmation === 'function') {
        try {
          prepared = await prepareConfirmation(barcode, {
            replace, expectedOldBarcode: existing,
          })
        } catch (error) {
          showFeedback({
            variant: 'warning',
            title: 'Barcode niet te vervangen',
            message: error?.message || 'De bestaande identiteit kon niet veilig worden gecontroleerd.',
          })
          return
        }
      }
      showFeedback({
        variant: 'warning',
        title: 'Barcode voor ' + name,
        message: replace
          ? 'Bestaande barcode ' + existing + ' vervangen door ' + barcode + '?'
          : 'Barcode ' + barcode + ' opslaan bij ' + name + '?',
        detail: ['Deze wijziging geldt alleen voor het hierboven genoemde artikel. De identiteit wordt vóór opslaan gecontroleerd. Je voorraad en aankopen worden niet door het scannen gewijzigd.', prepared?.detail].filter(Boolean).join(' '),
        dismissMode: 'blocked',
        primaryActionLabel: replace ? 'Vervangen' : 'Opslaan',
        secondaryActionLabel: 'Annuleren',
        testId: 'article-barcode-confirm',
        onPrimaryAction: async () => {
          if (saving) return false
          setSaving(true)
          try {
            await onConfirm(barcode, { replace, expectedOldBarcode: existing, prepared })
            showFeedback({
              variant: 'success',
              message: 'Barcode ' + barcode + (replace ? ' vervangen' : ' opgeslagen') + ' bij ' + name + '.',
            })
            return true
          } catch (error) {
            showFeedback({
              variant: 'error',
              title: 'Barcode niet gewijzigd',
              message: String(error?.message || 'Barcode kon niet veilig worden opgeslagen.'),
            })
            return false
          } finally {
            setSaving(false)
          }
        },
      })
    },
  })

  async function choosePhoto(event) {
    const photo = event.target.files?.[0]
    event.target.value = ''
    if (!photo) return
    stopScanner()
    const detected = await scanImageFile(photo)
    if (!detected) showFeedback({ variant: 'warning', message: 'Geen barcode gevonden in deze foto.' })
  }

  if (!mobile || disabled || typeof onConfirm !== 'function') return null
  return (
    <>
      <Button type="button" variant="secondary" onClick={() => void startScanner()} disabled={saving}
        data-testid={testId}>
        {title}
      </Button>
      <input ref={photoRef} type="file" accept="image/*" capture="environment" style={{ display: 'none' }}
        aria-label={'Barcodefoto voor ' + name} onChange={choosePhoto} />
      <BarcodeScannerModal open={isOpen || cameraState.status === 'error'}
        title={'Barcode voor ' + name} videoRef={videoRef} cameraState={cameraState}
        cameraMeta={cameraMeta} availableCameras={availableCameras}
        onSwitchCamera={switchCamera} onRetry={() => void startScanner()}
        onTryCompatibility={() => void startCompatibleCamera()}
        onChoosePhoto={() => { stopScanner(); photoRef.current?.click() }}
        onClose={() => stopScanner()} />
    </>
  )
}
