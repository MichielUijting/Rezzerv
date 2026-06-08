import { useEffect, useMemo, useState } from 'react'
import Button from '../../../ui/Button'

function normalizeVariant(variant) {
  const value = String(variant || '').trim().toLowerCase()
  if (['error', 'warning', 'success', 'info', 'progress'].includes(value)) return value
  return 'info'
}

function titleForVariant(variant) {
  if (variant === 'success') return 'Gelukt'
  if (variant === 'warning') return 'Let op'
  if (variant === 'error') return 'Melding'
  if (variant === 'progress') return 'Bezig met verwerken'
  return 'Informatie'
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

function normalizeDismissMode(feedback, variant) {
  const explicitMode = String(feedback?.dismissMode || '').trim().toLowerCase()
  if (['outside-or-ok', 'ok-only', 'blocked'].includes(explicitMode)) return explicitMode

  if (feedback?.requiresDecision) return 'blocked'
  if (variant === 'progress') return 'blocked'
  if (feedback?.dismissible === false) return 'blocked'

  return 'outside-or-ok'
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
    const title = String(feedback.title || titleForVariant(variant)).trim()
    const message = String(feedback.message || '').trim()
    const detail = String(feedback.detail || '').trim()
    const technicalDetail = String(feedback.technicalDetail || '').trim()
    const dismissMode = normalizeDismissMode(feedback, variant)

    if (!title && !message && !detail && !technicalDetail) return null

    return {
      ...feedback,
      variant,
      title,
      message,
      detail,
      technicalDetail,
      dismissMode,
      progress: Number.isFinite(Number(feedback.progress))
        ? Math.max(0, Math.min(100, Number(feedback.progress)))
        : null,
      showTechnicalToggle: Boolean(
        feedback.showTechnicalToggle &&
        technicalDetail &&
        typeof onToggleTechnical === 'function'
      ),
      testId: feedback.testId || `kassa-feedback-${variant}`,
    }
  }, [feedback, onToggleTechnical])

  const feedbackSignature = useMemo(() => {
    if (!normalizedFeedback) return ''
    return [
      normalizedFeedback.variant,
      normalizedFeedback.title,
      normalizedFeedback.message,
      normalizedFeedback.detail,
      normalizedFeedback.technicalDetail,
      normalizedFeedback.progress,
      normalizedFeedback.testId,
    ].join('|')
  }, [normalizedFeedback])

  const [isLocallyDismissed, setIsLocallyDismissed] = useState(false)

  useEffect(() => {
    setIsLocallyDismissed(false)
  }, [feedbackSignature])

  if (!normalizedFeedback || isLocallyDismissed) return null

  const {
    variant,
    title,
    message,
    detail,
    progress,
    dismissMode,
    showTechnicalToggle,
    technicalDetail,
    testId,
  } = normalizedFeedback

  const canDismissWithOk = dismissMode !== 'blocked'
  const canDismissOutside = dismissMode === 'outside-or-ok'

  function dismissFeedback() {
    if (dismissMode === 'blocked') return

    if (typeof onDismiss === 'function') {
      onDismiss()
      return
    }

    setIsLocallyDismissed(true)
  }

  function handleOverlayClick() {
    if (canDismissOutside) dismissFeedback()
  }

  function handleDialogClick(event) {
    event.stopPropagation()
  }

  return (
    <div
      data-testid={`${testId}-overlay`}
      aria-live={ariaLiveForVariant(variant)}
      role="presentation"
      onClick={handleOverlayClick}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 10000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '24px',
        background: 'rgba(16, 24, 40, 0.38)',
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={`${testId}-title`}
        className={classNameForVariant(variant)}
        data-testid={testId}
        onClick={handleDialogClick}
        style={{
          width: 'min(560px, 100%)',
          maxHeight: 'calc(100vh - 48px)',
          overflow: 'auto',
          display: 'grid',
          gap: '14px',
          boxShadow: '0 24px 64px rgba(16, 24, 40, 0.28)',
          fontWeight: 700,
        }}
      >
        <div style={{ display: 'grid', gap: '8px' }}>
          {title ? <div id={`${testId}-title`} style={{ fontSize: '18px', fontWeight: 800 }}>{title}</div> : null}
          {message ? <div style={{ fontWeight: 600 }}>{message}</div> : null}
          {detail ? <div style={{ color: '#344054', fontSize: '13px', fontWeight: 500 }}>{detail}</div> : null}
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

        {canDismissWithOk ? (
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
            <Button
              type="button"
              variant="primary"
              onClick={dismissFeedback}
              data-testid={`${testId}-ok-button`}
            >
              OK
            </Button>
          </div>
        ) : null}
      </div>
    </div>
  )
}
