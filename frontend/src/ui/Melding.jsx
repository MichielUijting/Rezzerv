import Button from './Button.jsx'

const DEFAULT_TITLES = {
  info: 'Melding',
  success: 'Gelukt',
  warning: 'Let op',
  error: 'Foutmelding',
  technical: 'Technische melding',
}

export default function Melding({
  open = false,
  type = 'info',
  title = '',
  message = '',
  detail = '',
  okLabel = 'OK',
  onClose,
  children,
}) {
  if (!open) return null

  const normalizedType = ['info', 'success', 'warning', 'error', 'technical'].includes(type) ? type : 'info'
  const resolvedTitle = title || DEFAULT_TITLES[normalizedType] || DEFAULT_TITLES.info

  function handleBackdropClick(event) {
    if (event.target === event.currentTarget) onClose?.()
  }

  return (
    <div
      className="rz-message-overlay"
      data-testid="melding-overlay"
      data-type={normalizedType}
      role="presentation"
      onMouseDown={handleBackdropClick}
    >
      <section
        className={`rz-message-dialog rz-message-dialog--${normalizedType}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="rz-message-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="rz-message-content">
          <h2 id="rz-message-title" className="rz-message-title">{resolvedTitle}</h2>
          {message ? <p className="rz-message-text">{message}</p> : null}
          {children ? <div className="rz-message-body">{children}</div> : null}
          {detail ? <pre className="rz-message-detail">{detail}</pre> : null}
        </div>
        <div className="rz-message-actions">
          <Button type="button" onClick={onClose}>{okLabel}</Button>
        </div>
      </section>
    </div>
  )
}
