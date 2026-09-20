import { useEffect, useState } from 'react'
import './tableLoadingOverlay.css'

const DEFAULT_DELAY_MS = 1000

export default function DelayedTableLoadingOverlay({
  active,
  delayMs = DEFAULT_DELAY_MS,
  label = 'Gegevens worden geladen',
}) {
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    setVisible(false)
    if (!active) return undefined

    const timer = window.setTimeout(() => {
      setVisible(true)
    }, delayMs)

    return () => window.clearTimeout(timer)
  }, [active, delayMs])

  if (!active || !visible) return null

  return (
    <div
      className="rz-table-loading-overlay"
      role="status"
      aria-live="polite"
      aria-label={label}
      aria-busy="true"
      data-testid="table-loading-overlay"
    >
      <img
        className="rz-table-loading-logo"
        src="/inhuis-app-icon.png"
        alt=""
        aria-hidden="true"
        data-testid="table-loading-logo"
      />
    </div>
  )
}
