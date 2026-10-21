import React from 'react'
import { API_BASE_URL } from '../../lib/apiClient.js'
import './maintenanceNotice.css'

export default function MaintenanceNotice() {
  const [status, setStatus] = React.useState(null)
  React.useEffect(() => {
    let live = true
    const controller = new AbortController()
    async function refresh() {
      try {
        const response = await fetch(`${API_BASE_URL}/api/maintenance/status`, { credentials: 'include', cache: 'no-store', signal: controller.signal })
        const data = response.ok ? await response.json() : null
        if (live) setStatus(data)
      } catch { /* Admission stays server-authoritative when status is offline. */ }
    }
    refresh()
    const timer = setInterval(refresh, 15000)
    return () => { live = false; clearInterval(timer); controller.abort() }
  }, [])
  if (!status || status.state === 'normal') return null
  return <div className="rz-feedback rz-feedback--info rz-maintenance-notice" role="status" data-testid="maintenance-notice">
    <strong>{status.state === 'announced' ? status.announcement : 'Serveronderhoud: nieuwe verwerkingen zijn tijdelijk geblokkeerd. Niet-opgeslagen invoer is niet verwerkt.'}</strong>
  </div>
}
