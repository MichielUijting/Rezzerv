import { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react'
import Button from './Button'

const AppFeedbackContext = createContext(null)

function normalizeVariant(variant) {
  const value = String(variant || '').trim().toLowerCase()
  if (['success', 'warning', 'error', 'info', 'progress'].includes(value)) return value
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

function normalizeFeedback(input) {
  if (!input) return null
  const variant = normalizeVariant(input.variant)
  const message = String(input.message || '').trim()
  const detail = String(input.detail || '').trim()
  const technicalDetail = String(input.technicalDetail || '').trim()
  const title = String(input.title || titleForVariant(variant)).trim()
  if (!title && !message && !detail && !technicalDetail) return null

  return {
    ...input,
    id: input.id || `${Date.now()}-${Math.random().toString(36).slice(2)}`,
    variant,
    title,
    message,
    detail,
    technicalDetail,
    dismissMode: input.dismissMode || (variant === 'progress' ? 'blocked' : 'outside-or-ok'),
    testId: input.testId || `app-feedback-${variant}`,
    progress: Number.isFinite(Number(input.progress))
      ? Math.max(0, Math.min(100, Number(input.progress)))
      : null,
    showTechnicalToggle: Boolean(input.showTechnicalToggle && technicalDetail),
  }
}

export function AppFeedbackProvider({ children }) {
  const [feedback, setFeedback] = useState(null)
  const [isTechnicalOpen, setIsTechnicalOpen] = useState(false)
  const lastFeedbackRef = useRef({ signature: '', at: 0 })

  const dismissFeedback = useCallback(() => {
    setFeedback(null)
    setIsTechnicalOpen(false)
  }, [])

  const showFeedback = useCallback((nextFeedback) => {
    const normalized = normalizeFeedback(nextFeedback)
    if (!normalized) return

    const dedupeMs = Number.isFinite(Number(nextFeedback?.dedupeMs))
      ? Number(nextFeedback.dedupeMs)
      : 1500
    const signature = String(
      nextFeedback?.key
      || [
        normalized.variant,
        normalized.title,
        normalized.message,
        normalized.detail,
        normalized.technicalDetail,
      ].join('|')
    )
    const now = Date.now()
    const last = lastFeedbackRef.current || { signature: '', at: 0 }

    if (last.signature === signature && now - Number(last.at || 0) < dedupeMs) return

    lastFeedbackRef.current = { signature, at: now }
    setIsTechnicalOpen(false)
    setFeedback({ ...normalized, signature })
  }, [])

  const value = useMemo(() => ({
    feedback,
    showFeedback,
    dismissFeedback,
  }), [feedback, showFeedback, dismissFeedback])

  return (
    <AppFeedbackContext.Provider value={value}>
      {children}
      <AppFeedbackDialog
        feedback={feedback}
        isTechnicalOpen={isTechnicalOpen}
        onToggleTechnical={() => setIsTechnicalOpen((current) => !current)}
        onDismiss={dismissFeedback}
      />
    </AppFeedbackContext.Provider>
  )
}

export function useAppFeedback() {
  const context = useContext(AppFeedbackContext)
  if (!context) {
    throw new Error('useAppFeedback moet binnen AppFeedbackProvider worden gebruikt.')
  }
  return context
}

function AppFeedbackDialog({ feedback, isTechnicalOpen = false, onToggleTechnical, onDismiss }) {
  if (!feedback) return null

  const {
    variant,
    title,
    message,
    detail,
    technicalDetail,
    dismissMode,
    testId,
    progress,
    showTechnicalToggle,
  } = feedback

  const canDismissWithOk = dismissMode !== 'blocked'
  const canDismissOutside = dismissMode === 'outside-or-ok'

  function dismiss() {
    if (dismissMode === 'blocked') return
    onDismiss?.()
  }

  function handleOverlayMouseDown(event) {
    // Voorkomt dat de browser focus uit het onderliggende invoerveld trekt
    // voordat de gebruiker bewust op OK klikt.
    if (event.target === event.currentTarget) event.preventDefault()
  }

  return (
    <div
      data-testid={`${testId}-overlay`}
      aria-live={ariaLiveForVariant(variant)}
      role="presentation"
      onMouseDown={handleOverlayMouseDown}
      onClick={() => { if (canDismissOutside) dismiss() }}
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
        onMouseDown={(event) => event.stopPropagation()}
        onClick={(event) => event.stopPropagation()}
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
              data-testid="app-feedback-technical-toggle"
              style={{ width: 'fit-content' }}
            >
              {isTechnicalOpen ? 'Verberg technische foutmelding' : 'Toon technische foutmelding'}
            </Button>

            {isTechnicalOpen ? (
              <pre
                data-testid="app-feedback-technical-details"
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
              onClick={dismiss}
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
