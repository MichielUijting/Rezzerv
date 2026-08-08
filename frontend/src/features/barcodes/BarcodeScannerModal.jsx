import Button from '../../ui/Button'

export default function BarcodeScannerModal({
  open,
  title = 'Barcode scannen',
  videoRef,
  cameraState,
  cameraMeta,
  availableCameras = [],
  onSwitchCamera,
  onClose,
}) {
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
          <Button type="button" variant="secondary" onClick={onClose}>Camera sluiten</Button>
        </div>
        <div className="rz-barcode-scanner-preview">
          <video ref={videoRef} autoPlay muted playsInline />
          <div className="rz-inline-feedback">
            Camera: {cameraMeta?.label || cameraMeta?.deviceId || 'onbekend'} · Decodepogingen: {cameraMeta?.decodeAttempts || 0}
          </div>
        </div>
        {cameraState?.message ? (
          <div className={cameraState.status === 'error' ? 'rz-inline-feedback rz-inline-feedback--error' : 'rz-inline-feedback rz-inline-feedback--success'} style={{ marginTop: 12 }}>
            {cameraState.message}
          </div>
        ) : null}
      </div>
    </div>
  )
}
