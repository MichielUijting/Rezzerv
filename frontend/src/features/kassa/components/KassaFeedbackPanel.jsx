import { useMemo } from 'react'
import Button from '../../../ui/Button'

function normalizeVariant(variant) {
  const value = String(variant || '').trim().toLowerCase()
  if (['error', 'warning', 'success', 'info', 'progress'].includes(value)) return value
  return 'info'
}

function classNameForVariant(variant) {
  if (variant === 'error') return 'rz-inline-feedback rz-inline-feedback--error'
  if (variant === 'warning') return 'rz-inline-feedback rz-inline-feedback--warning'
  if (variant === 'success' || variant === 'progress') return 'rz-inline-feedback rz-inline-feedback--success'
  return 'rz-inline-feedback'
}

function ariaLiveForVariant(variant) {
  return variant === 'error' || variant === 'warning' ? 'assertive' : 'polite'
}

export default function KassaFeedbackPanel({
  feedback,
  isTechnicalOpen = false,
  onToggleTechnical,
  onDismiss,
}) {
  const normalizedFeedback = useMemo(() => {
    if (!feedback) return null

    const variant = normalizeVariant(feedback.variant)
    const title = String(feedback.title || '').trim()
    const message = String(feedback.message || '').trim()
    const detail = String(feedback.detail || '').trim()
    const technicalDetail = String(feedback.technicalDetail || '').trim()

    if (!title && !message && !detail && !technicalDetail) return null

    return {
      ...feedback,
      variant,
      title,
      message,
      detail,
      technicalDetail,
      progress: Number.isFinite(Number(feedback.progress))
        ? Math.max(0, Math.min(100, Number(feedback.progress)))
        : null,
      dismissible: feedback.dismissible === true,
      showTechnicalToggle: Boolean(
        feedback.showTechnicalToggle &&
        technicalDetail &&
        typeof onToggleTechnical === 'function'
      ),
      testId: feedback.testId || `kassa-feedback-${variant}`,
    }
  }, [feedback, onToggleTechnical])

  if (!normalizedFeedback) return null

  const {
    variant,
    title,
    message,
    detail,
    progress,
    dismissible,
    showTechnicalToggle,
    technicalDetail,
    testId,
  } = normalizedFeedback

  return (
    <div
      className={classNameForVariant(variant)}
      data-testid={testId}
      aria-live={ariaLiveForVariant(variant)}
      style={{ display: 'grid', gap: '8px', fontWeight: 700 }}
    >
      <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start', justifyContent: 'space-between' }}>
        <div style={{ display: 'grid', gap: '4px' }}>
          {title ? <div>{title}</div> : null}
          {message ? <div style={{ fontWeight: title ? 500 : 700 }}>{message}</div> : null}
          {detail ? <div style={{ color: '#344054', fontSize: '13px', fontWeight: 500 }}>{detail}</div> : null}
        </div>

        {dismissible && typeof onDismiss === 'function' ? (
          <button
            type="button"
            onClick={onDismiss}
            aria-label="Melding sluiten"
            style={{
              border: '0',
              background: 'transparent',
              cursor: 'pointer',
              fontSize: '20px',
              lineHeight: '20px',
              color: '#344054',
              padding: '0 2px',
            }}
          >
            ×
          </button>
        ) : null}
      </div>

      {variant === 'progress' && progress !== null ? (
        <div style={{ display: 'grid', gap: '6px' }}>
          <div style={{ height: '8px', borderRadius: '999px', background: '#E4E7EC', overflow: 'hidden' }}>
            <div
              style={{
                height: '100%',
                width: `${progress}%`,
                borderRadius: '999px',
                background: '#2E7D32',
                transition: 'width 180ms ease',
              }}
            />
          </div>
          <div style={{ fontSize: '12px', color: '#344054', fontWeight: 500 }}>{progress}%</div>
        </div>
      ) : null}

      {showTechnicalToggle ? (
        <div style={{ display: 'grid', gap: '8px' }}>
          <Button
            type="button"
            variant="secondary"
            onClick={onToggleTechnical}
            data-testid="kassa-admin-technical-error-toggle"
            style={{ width: 'fit-content' }}
          >
            {isTechnicalOpen ? 'Verberg technische foutmelding' : 'Toon technische foutmelding'}
          </Button>

          {isTechnicalOpen ? (
            <pre
              data-testid="kassa-admin-technical-error-details"
              style={{
                whiteSpace: 'pre-wrap',
                margin: 0,
                padding: '12px',
                borderRadius: '10px',
                border: '1px solid #FDA29B',
                background: '#FFFBFA',
                color: '#7A271A',
                fontSize: '12px',
                maxHeight: '260px',
                overflow: 'auto',
                fontWeight: 500,
              }}
            >
              {technicalDetail}
            </pre>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
