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
  const [now, setNow] = React.useState(Date.now())
  React.useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer) }, [])
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
      if (id === requestId.current) { setStatus({ ...data, restartUntil: Date.now() + Math.max(0, Number(data.restart_valid_for_seconds || 0)) * 1000 }); setError('') }
    } catch (e) { if (id === requestId.current) { setError(e.message); setStatus(current => current ? { ...current, restart_allowed: false } : current) } }
    finally { if (id === requestId.current) setBusy(false) }
  }
  React.useEffect(() => { request(); return () => { ++requestId.current } }, [])
  React.useEffect(() => { if (!status || status.state === 'normal') return; const timer = setInterval(() => { if (busy) return; if (status.state === 'draining' && status.active_operations === 0 && status.host_agent_ready) request('prepare'); else if (status.state === 'locked' && status.restart_detected) request('verify'); else request() }, 10000); return () => clearInterval(timer) }, [status?.state, busy])
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
        {!status.host_agent_ready && <p>De onderhoudsagent is nog niet gekoppeld of bereikbaar. Aankondigen en annuleren blijven mogelijk.</p>}
        <Button disabled={busy || !status.host_agent_ready} onClick={() => request('drain')}>Verwerkingen veilig stoppen</Button>
        <Button disabled={busy} variant="secondary" onClick={() => request('cancel')}>Aankondiging annuleren</Button>
      </>}
      {status.state === 'draining' && <Button disabled={busy || status.active_operations !== 0} onClick={() => request('prepare')}>Actuele veiligheidscontroles uitvoeren</Button>}
      {status.state === 'locked' && !status.restart_allowed && <p>Herstarttoestemming ontbreekt of is verlopen. Vernieuw de status en laat de onderhoudsagent controleren.</p>}
      {status.restart_allowed && now < status.restartUntil && <p role="status">Alle veiligheidscontroles zijn geslaagd. U kunt Windows nu zelf herstarten.</p>}
      {['locked', 'blocked', 'verifying'].includes(status.state) && <Button disabled={busy} onClick={() => request('verify')}>Omgeving na herstart controleren</Button>}
      {status.state === 'verifying' && <Button disabled={busy} onClick={() => request('release')}>Onderhoud beëindigen en gebruikers toelaten</Button>}
    </>}
    <Button variant="secondary" disabled={busy} onClick={() => request()}>Status vernieuwen</Button>
    <p>Bij een fout blijft onderhoud gesloten. Niet-opgeslagen invoer wordt niet automatisch verwerkt.</p>
  </Card>
}
