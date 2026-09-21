import Button from '../../ui/Button'

export default function CatalogCameraModal({
  open,
  videoRef,
  cameraState,
  onVideoReady,
  onCapture,
  onClose,
}) {
  if (!open) return null

  const status = String(cameraState?.status || 'starting')
  const message = String(cameraState?.message || '').trim()
  const canCapture = status === 'ready'

  return (
    <div
      className="rz-modal-backdrop"
      role="presentation"
      data-testid="catalog-camera-backdrop"
    >
      <div
        className="rz-modal-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="catalog-camera-title"
        data-testid="catalog-camera-modal"
        onClick={(event) => event.stopPropagation()}
        style={{ width: 'min(760px, calc(100vw - 32px))' }}
      >
        <h3 id="catalog-camera-title" className="rz-modal-title">Productfoto maken</h3>
        <p className="rz-modal-text">
          Richt de camera op het product en zorg dat het product volledig in beeld staat.
        </p>

        <div
          style={{
            width: '100%',
            minHeight: '240px',
            maxHeight: '60vh',
            display: 'grid',
            placeItems: 'center',
            overflow: 'hidden',
            borderRadius: 'var(--radius-md)',
            background: '#111827',
          }}
        >
          <video
            ref={videoRef}
            autoPlay
            muted
            playsInline
            onLoadedMetadata={onVideoReady}
            aria-label="Live camerabeeld voor productfoto"
            data-testid="catalog-camera-preview"
            style={{
              display: 'block',
              width: '100%',
              height: '100%',
              maxHeight: '60vh',
              objectFit: 'contain',
              background: '#111827',
            }}
          />
        </div>

        {message ? (
          <div
            className={status === 'error'
              ? 'rz-inline-feedback rz-inline-feedback--error'
              : 'rz-inline-feedback'}
            data-testid="catalog-camera-state"
          >
            {message}
          </div>
        ) : null}

        <div className="rz-modal-actions">
          <Button
            type="button"
            variant="primary"
            onClick={onCapture}
            disabled={!canCapture}
            data-testid="catalog-camera-capture"
          >
            Foto maken
          </Button>
          <Button
            type="button"
            variant="secondary"
            onClick={onClose}
            data-testid="catalog-camera-close"
          >
            Annuleren
          </Button>
        </div>
      </div>
    </div>
  )
}
