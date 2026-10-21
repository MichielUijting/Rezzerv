import React from 'react'
import Card from '../../ui/Card.jsx'
import Button from '../../ui/Button.jsx'
import Input from '../../ui/Input.jsx'
import { API_BASE_URL } from '../../lib/apiClient.js'

const LABELS = { normal: 'Beschikbaar', announced: 'Onderhoud aangekondigd', draining: 'Lopende verwerkingen afronden', locked: 'Verwerkingen geblokkeerd', verifying: 'Herstel gecontroleerd', blocked: 'Onderzoek nodig' }

export default function PlatformMaintenancePanel() {
  const [status, setStatus] = React.useState(null)
  const [announcement, setAnnouncement] = React.useState('')
  const [error, setError] = React.useState('')
  const [busy, setBusy] = React.useState(false)
  const requestId = React.useRef(0)
  async function request(action) {
    const id = ++requestId.current
    setBusy(true)
    try {
      const response = await fetch(`${API_BASE_URL}/api/platform/maintenance`, {
        credentials: 'include', cache: 'no-store', method: action ? 'POST' : 'GET',
        headers: { 'Content-Type': 'application/json' },
        ...(action ? { body: JSON.stringify({ action, expected_generation: status.generation, announcement }) } : {}),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Onderhoudscontrole mislukt.')
      if (id === requestId.current) { setStatus(data); setError('') }
    } catch (e) { if (id === requestId.current) setError(e.message) }
    finally { if (id === requestId.current) setBusy(false) }
  }
  React.useEffect(() => { request(); return () => { ++requestId.current } }, [])
  return <Card className="rz-card-home" data-testid="platform-maintenance-panel">
    <h2>Serveronderhoud</h2>
    {error && <p role="alert">{error}</p>}
    {status && <>
      <p role="status">{LABELS[status.state] || 'Onbekend — geblokkeerd'}. Lopende verwerkingen: {status.active_operations}.</p>
      {status.announcement && <p>{status.announcement}</p>}
      {status.state === 'normal' && <>
        <Input label="Onderhoudsvenster en verwachte duur" value={announcement} onChange={e => setAnnouncement(e.target.value)} maxLength={2000} placeholder="Datum, begintijd, tijdzone en verwachte duur" />
        <Button disabled={busy || !announcement.trim()} onClick={() => request('announce')}>Onderhoud aankondigen</Button>
      </>}
      {status.state === 'announced' && <>
        <Button disabled={busy} onClick={() => request('drain')}>Verwerkingen veilig stoppen</Button>
        <Button disabled={busy} variant="secondary" onClick={() => request('cancel')}>Aankondiging annuleren</Button>
      </>}
      {['draining', 'locked'].includes(status.state) && <Button disabled={busy || status.active_operations !== 0} onClick={() => request('prepare')}>Actuele veiligheidscontroles uitvoeren</Button>}
      {status.runtime_checks_passed && <p>Database- en verwerkingscontroles geslaagd. Host-, opslag- en back-upbewijs ontbreken nog. Er is geen toestemming voor een Windows-herstart.</p>}
      {status.restart_allowed && <p role="status">Alle veiligheidscontroles zijn geslaagd. U kunt Windows nu zelf herstarten.</p>}
      {['locked', 'blocked', 'verifying'].includes(status.state) && <Button disabled={busy} onClick={() => request('verify')}>Omgeving na herstart controleren</Button>}
      {status.state === 'verifying' && <Button disabled={busy} onClick={() => request('release')}>Onderhoud beëindigen en gebruikers toelaten</Button>}
    </>}
    <Button variant="secondary" disabled={busy} onClick={() => request()}>Status vernieuwen</Button>
    <p>Bij een fout blijft onderhoud gesloten. Niet-opgeslagen invoer wordt niet automatisch verwerkt.</p>
  </Card>
}
