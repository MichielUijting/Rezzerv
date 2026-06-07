import { useEffect, useRef, useState } from 'react'
import Header from '../ui/Header.jsx'
import Button from '../ui/Button.jsx'
import Melding from '../ui/Melding.jsx'

function getFeedbackType(element) {
  const className = String(element?.className || '')
  if (className.includes('--error') || className.includes('error') || className.includes('alert')) return 'error'
  if (className.includes('--warning') || className.includes('warning')) return 'warning'
  if (className.includes('--success') || className.includes('success')) return 'success'
  return 'info'
}

function getFeedbackTitle(type) {
  if (type === 'error') return 'Foutmelding'
  if (type === 'warning') return 'Let op'
  if (type === 'success') return 'Melding'
  return 'Melding'
}

function ScreenMessageBridge() {
  const [melding, setMelding] = useState(null)
  const dismissedSignaturesRef = useRef(new Set())

  useEffect(() => {
    function scanForFeedback() {
      const candidates = Array.from(document.querySelectorAll('.rz-inline-feedback, .rz-store-inline-feedback, .alert'))
        .filter((element) => !element.closest('.rz-message-overlay'))
        .filter((element) => element.getAttribute('data-testid') !== 'receipt-upload-progress')
        .map((element) => ({ element, text: String(element.textContent || '').trim() }))
        .filter((item) => item.text.length > 0)

      const next = candidates[candidates.length - 1]
      if (!next) return

      const type = getFeedbackType(next.element)
      const signature = `${type}:${next.text}`
      if (dismissedSignaturesRef.current.has(signature)) return

      setMelding({ type, title: getFeedbackTitle(type), message: next.text, signature })
    }

    scanForFeedback()
    const observer = new MutationObserver(scanForFeedback)
    observer.observe(document.body, { childList: true, subtree: true, characterData: true })
    return () => observer.disconnect()
  }, [])

  function closeMelding() {
    if (melding?.signature) dismissedSignaturesRef.current.add(melding.signature)
    setMelding(null)
  }

  return (
    <Melding
      open={Boolean(melding)}
      type={melding?.type || 'info'}
      title={melding?.title || 'Melding'}
      message={melding?.message || ''}
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
