import { useEffect } from 'react'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'
import Button from '../../ui/Button'

export default function BarcodeScannerModal({
  open,
  title = 'Barcode scannen',
  videoRef,
  cameraState,
  cameraMeta,
  availableCameras = [],
  onSwitchCamera,
  onRetry,
  onTryCompatibility,
  onChoosePhoto,
  onClose,
  hideInlineFeedback = false,
}) {
  const { showFeedback } = useAppFeedback()
  useEffect(() => {
    if (open && cameraState?.status === 'error' && cameraState.message) {
      showFeedback({ variant: 'error', message: cameraState.message })
    }
  }, [open, cameraState?.status, cameraState?.message, showFeedback])
  function requestTemporaryCameraMode() {
    if (!cameraState?.recovery?.canTryCompatibility || !onTryCompatibility) return
    showFeedback({
      variant: 'warning',
      title: 'Camera tijdelijk anders proberen?',
      message: 'Inhuis kan één keer een eenvoudige camera-instelling aanvragen.',
      detail: 'De browser kan opnieuw om cameratoegang vragen. Alleen de video-instellingen van deze scansessie veranderen. Bij sluiten worden de camerabeelden gestopt en verdwijnen deze tijdelijke instellingen. Windows- en browserprivacyrechten worden niet gewijzigd.',
      dismissMode: 'blocked',
      primaryActionLabel: 'Ja, tijdelijk proberen',
      secondaryActionLabel: 'Annuleren',
      testId: 'barcode-camera-temporary-consent',
      onPrimaryAction: () => { onTryCompatibility(); return true },
    })
  }

  if (!open) return null

  return (
    <div className="rz-modal-backdrop" role="presentation" data-testid="barcode-scanner-backdrop">
      <div
        className="rz-modal-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="barcode-scanner-title"
        onClick={(event) => event.stopPropagation()}
        style={{ width: 'min(760px, calc(100vw - 32px))' }}
      >
        <h3 id="barcode-scanner-title" className="rz-modal-title">{title}</h3>
        <p className="rz-modal-text">Richt de barcode horizontaal en scherp in beeld. De gevonden code wordt alleen gecontroleerd en veroorzaakt geen voorraadmutatie.</p>
        <div className="rz-modal-actions" style={{ justifyContent: 'flex-start' }}>
          <Button type="button" variant="secondary" onClick={onSwitchCamera} disabled={availableCameras.length < 2}>Camera wisselen</Button>
          {cameraState?.status === 'error' && cameraState?.recovery?.canTryCompatibility && onTryCompatibility
            ? <Button type="button" variant="secondary" onClick={requestTemporaryCameraMode} data-testid="barcode-camera-temporary-mode">Tijdelijke camera-instellingen proberen</Button> : null}
          {cameraState?.status === 'error' && onRetry
            ? <Button type="button" variant="secondary" onClick={onRetry}>Camera opnieuw proberen</Button> : null}
          {cameraState?.status === 'error' && onChoosePhoto
            ? <Button type="button" variant="secondary" onClick={onChoosePhoto}>Barcode uit foto</Button> : null}
          <Button type="button" variant="secondary" onClick={onClose}>Camera sluiten</Button>
        </div>
        <div className="rz-barcode-scanner-preview">
          <video ref={videoRef} autoPlay muted playsInline />
          {!hideInlineFeedback ? (
            <div className="rz-barcode-camera-metadata">
              Camera: {cameraMeta?.label || cameraMeta?.deviceId || 'onbekend'} · Decodepogingen: {cameraMeta?.decodeAttempts || 0}
            </div>
          ) : null}
        </div>
        {cameraState?.status === 'error' && cameraState.recovery ? (
          <div className="rz-modal-text" role="status" data-testid="barcode-camera-recovery-help">
            <p><strong>{cameraState.message}</strong></p>
            <p>{cameraState.recovery.advice}</p>
            {cameraState.recovery.deviceAdvice ? <p>{cameraState.recovery.deviceAdvice}</p> : null}
            <p>Inhuis kan de privacyinstellingen van je laptop of browser niet zelf aanpassen.</p>
          </div>
        ) : null}
        {cameraState?.status === 'error' && onChoosePhoto
          ? <p className="rz-modal-text">Geen werkende camera? Kies Barcode uit foto of vul de barcode handmatig in. Er wordt zonder bevestiging niets opgeslagen.</p>
          : null}

      </div>
    </div>
  )
}
