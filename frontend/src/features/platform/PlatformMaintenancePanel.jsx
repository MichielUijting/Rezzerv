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
  const [confirmSessionClose, setConfirmSessionClose] = React.useState(false)
  const [sessionCloseResult, setSessionCloseResult] = React.useState(null)
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
  async function closeRemainingSessions() {
    setBusy(true)
    setError('')
    try {
      const response = await fetch(`${API_BASE_URL}/api/platform/maintenance/sessions/close`, {
        credentials: 'include', cache: 'no-store', method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ expected_generation: status.generation, confirmed: true }),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Sessies beëindigen mislukt.')
      setSessionCloseResult(Number(data.sessions_revoked || 0))
      setConfirmSessionClose(false)
      await request()
    } catch (e) { setError(e.message || 'Sessies beëindigen mislukt.') }
    finally { setBusy(false) }
  }
  React.useEffect(() => { if (!status || status.state === 'normal') return; const timer = setInterval(() => { if (busy) return; if (status.state === 'draining' && status.active_operations === 0 && status.host_agent_ready) request('prepare'); else if (status.state === 'locked' && status.restart_detected) request('verify'); else request() }, 10000); return () => clearInterval(timer) }, [status?.state, busy])
  return <div data-testid="platform-maintenance-panel"><Card className="rz-card-home">
    <h2>Onderhoud aan Inhuis</h2>
    {error && <p role="alert">{error}</p>}
    {status && <>
      <p role="status">{LABELS[status.state] || 'Onbekend — geblokkeerd'}. Lopende verwerkingen: {status.active_operations}.</p>
      {status.retailer_import_registrations && <p data-testid="retailer-import-maintenance-status">
        Winkelkoppelingen: {status.retailer_import_registrations.open} openstaande importregistratie(s)
        ({status.retailer_import_registrations.ah_background} AH-achtergrond,
        {' '}{status.retailer_import_registrations.other_retailer} overige winkelimports).
        {' '}{status.retailer_import_registrations.new_imports_paused
          ? 'Nieuwe winkelimports zijn geblokkeerd; reeds begonnen werk wordt veilig afgerond.'
          : 'Winkelimports mogen automatisch starten.'}
        {' '}Een open registratie kan ook van een onderbroken oude import zijn; dit is geen telling van actieve gebruikerssessies.
      </p>}
      {status.announcement && <p>{status.announcement}</p>}
      {sessionCloseResult !== null && <p role="status">{sessionCloseResult} andere inlogsessie(s) beëindigd. Lopende verwerkingen zijn niet afgebroken.</p>}
      {status.state === 'normal' && <>
        <Input label="Onderhoudsvenster en verwachte duur" value={announcement} onChange={e => setAnnouncement(e.target.value)} maxLength={2000} placeholder="Datum, begintijd, tijdzone en verwachte duur" />
        <Button disabled={busy || !announcement.trim()} onClick={() => request('announce')}>Onderhoud aankondigen</Button>
      </>}
      {status.state === 'announced' && <>
        {!status.host_agent_ready && <p>De onderhoudsagent is nog niet gekoppeld of bereikbaar. Aankondigen en annuleren blijven mogelijk.</p>}
        <Button disabled={busy || !status.host_agent_ready} onClick={() => request('drain')}>Verwerkingen veilig stoppen</Button>
        <Button disabled={busy} variant="secondary" onClick={() => request('cancel')}>Aankondiging annuleren</Button>
      </>}
      {['announced', 'draining'].includes(status.state) && <>
        <p>Na minimaal twee minuten kunt u gebruikers die aangemeld blijven gecontroleerd afmelden. Dit voorkomt nieuwe handelingen, maar breekt geen lopende verwerking af. Een geldige sessie betekent niet noodzakelijk dat iemand nu actief werkt.</p>
        <Button variant="secondary" disabled={busy} onClick={() => setConfirmSessionClose(true)}>Resterende sessies beëindigen</Button>
      </>}
      {['announced', 'draining'].includes(status.state) && confirmSessionClose && <Card>
        <h3>Andere gebruikers afmelden?</h3>
        <p>Alle andere geldige inlogsessies worden ingetrokken. Uw beheersessie blijft bestaan. Niet-opgeslagen invoer van andere gebruikers kan verloren gaan. Reeds gestarte verwerkingen worden niet afgebroken. Deze handeling is pas twee minuten na de aankondiging toegestaan en vereist ook sessiebeheerrechten.</p>
        <Button disabled={busy} onClick={closeRemainingSessions}>Ja, andere sessies beëindigen</Button>
        <Button variant="secondary" disabled={busy} onClick={() => setConfirmSessionClose(false)}>Annuleren</Button>
      </Card>}
      {status.state === 'draining' && <Button disabled={busy || status.active_operations !== 0} onClick={() => request('prepare')}>Actuele veiligheidscontroles uitvoeren</Button>}
      {status.state === 'locked' && !status.restart_allowed && <p>Herstarttoestemming ontbreekt of is verlopen. Vernieuw de status en laat de onderhoudsagent controleren.</p>}
      {status.restart_allowed && now < status.restartUntil && <p role="status">Alle veiligheidscontroles zijn geslaagd. U kunt Windows nu zelf herstarten.</p>}
      {['locked', 'blocked', 'verifying'].includes(status.state) && <Button disabled={busy} onClick={() => request('verify')}>Omgeving na herstart controleren</Button>}
      {status.state === 'verifying' && <Button disabled={busy} onClick={() => request('release')}>Onderhoud beëindigen en gebruikers toelaten</Button>}
    </>}
    <Button variant="secondary" disabled={busy} onClick={() => request()}>Status vernieuwen</Button>
    <p>Bij een fout blijft onderhoud gesloten. Niet-opgeslagen invoer wordt niet automatisch verwerkt.</p>
  </Card></div>
}
