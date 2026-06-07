import { useEffect, useState } from 'react'
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

function ScreenMessageBridge() {
  const [melding, setMelding] = useState(null)

  useEffect(() => {
    function handleMessageEvent(event) {
      const detail = event?.detail || {}
      const message = String(detail.message || detail.text || '').trim()
      if (!message) return
      const type = String(detail.type || detail.variant || 'info').trim().toLowerCase()
      setMelding({
        type,
        title: detail.title || getMessageTitle(type),
        message,
        detail: detail.detail || '',
      })
    }

    window.addEventListener('rezzerv:melding', handleMessageEvent)
    return () => window.removeEventListener('rezzerv:melding', handleMessageEvent)
  }, [])

  return (
    <Melding
      open={Boolean(melding)}
      type={melding?.type || 'info'}
      title={melding?.title || 'Melding'}
      message={melding?.message || ''}
      detail={melding?.detail || ''}
      onClose={() => setMelding(null)}
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
