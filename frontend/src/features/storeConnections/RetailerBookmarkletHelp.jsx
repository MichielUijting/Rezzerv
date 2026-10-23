import { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import Button from '../../ui/Button'

/**
 * Shared, OK-only setup dialog for the two browser-assisted receipt sources.
 * Opening this dialog never creates a browser favorite or imports a receipt.
 */
export default function RetailerBookmarkletHelp({
  provider,
  retailer,
  open,
  onClose,
  bookmarklet,
  valid = true,
  instructions,
}) {
  const dialogRef = useRef(null)

  useEffect(() => {
    if (!open) return undefined
    const previousFocus = document.activeElement
    const dialog = dialogRef.current
    dialog?.querySelector('[data-testid="' + provider + '-help-ok"]')?.focus()

    const keepDialogOpen = (event) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        event.stopPropagation()
        return
      }
      if (event.key !== 'Tab' || !dialog) return
      const interactive = [...dialog.querySelectorAll('a[href], button:not([disabled])')]
      if (!interactive.length) {
        event.preventDefault()
        return
      }
      const first = interactive[0]
      const last = interactive[interactive.length - 1]
      if (event.shiftKey && (document.activeElement === first || !dialog.contains(document.activeElement))) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && (document.activeElement === last || !dialog.contains(document.activeElement))) {
        event.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', keepDialogOpen, true)
    return () => {
      document.removeEventListener('keydown', keepDialogOpen, true)
      previousFocus?.focus?.()
    }
  }, [open, provider])

  if (!open) return null

  const titleId = provider + '-bookmarklet-help-title'
  const linkTestId = provider === 'jumbo' ? 'jumbo-poc-bookmarklet' : 'lidl-web-bookmarklet'
  return createPortal(
    <div
      data-testid={provider + '-bookmarklet-help'}
      style={{
        position: 'fixed', inset: 0, zIndex: 3000,
        display: 'grid', placeItems: 'center', padding: '16px',
        background: 'rgba(0, 0, 0, 0.55)',
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        data-testid={provider + '-bookmarklet-dialog'}
        style={{
          width: 'min(100%, 520px)',
          maxHeight: 'calc(100vh - 32px)',
          overflowY: 'auto',
          padding: '24px',
          borderRadius: 'var(--radius-md)',
          background: '#fff',
          boxShadow: '0 16px 48px rgba(0,0,0,0.24)',
          display: 'grid',
          gap: '14px',
        }}
      >
        <h3 id={titleId} style={{ margin: 0 }}>Eerste keer koppelen met {retailer}?</h3>
        <p style={{ margin: 0 }}>
          Sleep de knop hieronder naar de favorietenbalk van je browser.
          Heb je al een oude {retailer}-favoriet? Vervang die eerst.
        </p>
        <a
          href={valid ? bookmarklet : undefined}
          data-testid={linkTestId}
          draggable={valid}
          aria-disabled={!valid}
          style={{
            display: 'inline-flex',
            width: 'fit-content',
            minHeight: '40px',
            alignItems: 'center',
            padding: '8px 12px',
            borderRadius: 'var(--radius-md)',
            border: '1px solid var(--color-ui-primary)',
            color: 'var(--color-ui-primary)',
            fontWeight: 400,
            textDecoration: 'none',
          }}
          onClick={(event) => event.preventDefault()}
        >
          {retailer}-bonnen ophalen
        </a>
        <p style={{ margin: 0 }}>
          Klik op <strong>OK</strong> nadat je de favoriet hebt opgeslagen.
          {instructions}
        </p>
        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <Button
            type="button"
            onClick={onClose}
            data-testid={provider + '-help-ok'}
          >OK</Button>
        </div>
      </div>
    </div>,
    document.body,
  )
}
