import { useEffect, useRef, useState } from 'react'
import Header from '../ui/Header.jsx'
import Button from '../ui/Button.jsx'
import Melding from '../ui/Melding.jsx'

function getMessageTitle(type) {
  if (type === 'error') return 'Foutmelding'
  if (type === 'warning') return 'Let op'
  if (type === 'success') return 'Melding'
  if (type === 'technical') return 'Technische melding'
  return 'Melding'
}

function getLegacyMessageType(element) {
  const className = String(element?.className || '').toLowerCase()
  if (className.includes('error') || className.includes('alert')) return 'error'
  if (className.includes('warning')) return 'warning'
  if (className.includes('success')) return 'success'
  return 'info'
}

function ScreenMessageBridge() {
  const [melding, setMelding] = useState(null)
  const dismissedRef = useRef(new Set())

  useEffect(() => {
    function showMessage(detail = {}) {
      const message = String(detail.message || detail.text || '').trim()
      if (!message) return
      const type = String(detail.type || detail.variant || 'info').trim().toLowerCase()
      setMelding({
        type,
        title: detail.title || getMessageTitle(type),
        message,
        detail: detail.detail || '',
        signature: `${type}:${message}`,
      })
    }

    function handleMessageEvent(event) {
      showMessage(event?.detail || {})
    }

    function scanLegacyFeedback() {
      const candidates = Array.from(document.querySelectorAll('.rz-inline-feedback, .rz-store-inline-feedback, .alert'))
        .filter((element) => !element.closest('.rz-message-overlay'))
        .filter((element) => element.getAttribute('data-testid') !== 'receipt-upload-progress')
        .map((element) => ({ element, text: String(element.textContent || '').trim() }))
        .filter((item) => item.text.length > 0)

      const next = candidates[candidates.length - 1]
      if (!next) return
      const type = getLegacyMessageType(next.element)
      const signature = `${type}:${next.text}`
      if (dismissedRef.current.has(signature)) return
      showMessage({ type, message: next.text, title: getMessageTitle(type) })
    }

    window.addEventListener('rezzerv:melding', handleMessageEvent)
    const observer = new MutationObserver(scanLegacyFeedback)
    observer.observe(document.body, { childList: true, subtree: true, characterData: true })
    const intervalId = window.setInterval(scanLegacyFeedback, 300)
    window.setTimeout(scanLegacyFeedback, 0)

    return () => {
      window.removeEventListener('rezzerv:melding', handleMessageEvent)
      observer.disconnect()
      window.clearInterval(intervalId)
    }
  }, [])

  function closeMelding() {
    if (melding?.signature) dismissedRef.current.add(melding.signature)
    setMelding(null)
  }

  return (
    <Melding
      open={Boolean(melding)}
      type={melding?.type || 'info'}
      title={melding?.title || 'Melding'}
      message={melding?.message || ''}
      detail={melding?.detail || ''}
      onClose={closeMelding}
    />
  )
}

export default function AppShell({ title, children, showExit = true }) {
  return (
    <div className="rz-screen">
      <Header title={title} />
      <div className="rz-content">
        <div className="rz-content-inner">
          {children}
        </div>
      </div>

      <ScreenMessageBridge />

      {showExit && (
        <div className="rz-exitbar">
          <Button variant="secondary" onClick={() => window.close()}>
            Afsluiten
          </Button>
        </div>
      )}
    </div>
  )
}
