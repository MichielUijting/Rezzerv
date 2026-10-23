import { useEffect, useState } from 'react'
import Card from '../../ui/Card'
import Button from '../../ui/Button'
import Input from '../../ui/Input'
import { useMobileAppViewport } from '../../app/mobileViewport.js'

async function picnicRequest(path, options = {}) {
  const response = await fetch('/api/receipts/retailers/picnic/' + path, {
    credentials: 'include',
    ...options,
    headers: options.body ? { 'Content-Type': 'application/json' } : undefined,
  })
  if (!response.ok) {
    // Never present raw provider responses or any credentials in UI.
    throw new Error('Picnic-verzoek kon niet worden voltooid. Controleer de koppeling en probeer opnieuw.')
  }
  return response.json()
}

export default function PicnicAccountResearchPanel() {
  const isMobileViewport = useMobileAppViewport()
  const [account, setAccount] = useState({ connected: false, verification_required: false })
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [deliveries, setDeliveries] = useState([])
  const [preview, setPreview] = useState(null)

  useEffect(() => {
    let active = true
    picnicRequest('status').then(value => {
      if (active) setAccount(value)
    }).catch(() => {
      if (active) setNotice('Picnic-onderzoeksfunctie is momenteel niet beschikbaar.')
    })
    return () => { active = false }
  }, [])

  async function run(task, message) {
    if (busy) return
    setBusy(true)
    setNotice('')
    try {
      const result = await task()
      setNotice(message)
      return result
    } catch {
      setNotice('De actie is niet gelukt. Er zijn geen Picnic-bestellingen gewijzigd.')
      return null
    } finally {
      setBusy(false)
    }
  }

  const connected = Boolean(account.connected)
  const requiresSms = Boolean(account.verification_required)

  return (
    <Card>
      <div
        data-testid="picnic-account-research"
        className={isMobileViewport ? 'rz-store-receipt-panel--mobile' : undefined}
        style={{ display: 'grid', rowGap: '12px' }}
      >
        <h3 style={{ margin: 0 }}>Picnic — accountkoppeling (proef)</h3>
        <p style={{ margin: 0 }}>
          Deze proef kan alleen bestellingen uitlezen en toont nog geen digitale kassabonnen in Kassa.
          Picnic biedt hiervoor geen officieel ondersteunde API. Aanmelden is daarom experimenteel.
        </p>
        <div role="status" data-testid="picnic-account-status">
          {connected ? 'Account gekoppeld (alleen lezen)' : requiresSms ? 'Sms-verificatie nodig' : 'Niet gekoppeld'}
        </div>
        {!connected && !requiresSms ? (
          <>
            <Input label="Picnic-gebruikersnaam" value={username} onChange={event => setUsername(event.target.value)} autoComplete="username" />
            <Input label="Picnic-wachtwoord" type="password" value={password} onChange={event => setPassword(event.target.value)} autoComplete="current-password" />
            <Button
              type="button"
              disabled={busy || !username.trim() || !password}
              onClick={async () => {
                const credentials = { username: username.trim(), password }
                setPassword('')
                const result = await run(
                  () => picnicRequest('connect', { method: 'POST', body: JSON.stringify(credentials) }),
                  'Picnic heeft de aanmelding ontvangen.',
                )
                if (result) setAccount(result)
              }}
            >
              Picnic verbinden
            </Button>
          </>
        ) : null}
        {requiresSms ? (
          <>
            <Button type="button" disabled={busy} onClick={() => run(
              () => picnicRequest('request-sms', { method: 'POST' }),
              'Picnic-sms-code aangevraagd.',
            )}>Sms-code aanvragen</Button>
            <Input label="Picnic-sms-code" value={code} onChange={event => setCode(event.target.value)} />
            <Button
              type="button"
              disabled={busy || !/^\d{4,10}$/.test(code)}
              onClick={async () => {
                const otp = code
                setCode('')
                const result = await run(
                  () => picnicRequest('verify-sms', { method: 'POST', body: JSON.stringify({ code: otp }) }),
                  'Picnic-verificatie afgerond.',
                )
                if (result) setAccount(result)
              }}
            >Sms-code verifiëren</Button>
          </>
        ) : null}
        {connected ? (
          <Button type="button" disabled={busy} onClick={async () => {
            const result = await run(() => picnicRequest('deliveries'), 'Bezorggeschiedenis alleen-lezen opgehaald.')
            if (result) setDeliveries(result.deliveries || [])
          }}>Toon mijn bezorgingen (alleen lezen)</Button>
        ) : null}
        {deliveries.slice(0, 40).map((delivery, i) => (
          <div key={String(delivery.delivery_id || i)} style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
            <span>Bezorging {i + 1} — {String(delivery.status || 'Status onbekend')}</span>
            <Button type="button" disabled={busy || !delivery.delivery_id} onClick={async () => {
              const result = await run(
                () => picnicRequest('deliveries/' + encodeURIComponent(delivery.delivery_id)),
                'Bestelling opgehaald ter controle; niet geïmporteerd.',
              )
              if (result) setPreview(result)
            }}>Bekijk details</Button>
          </div>
        ))}
        {preview ? (
          <div data-testid="picnic-readonly-preview">
            Bezorging met {preview.orders?.length || 0} bestelling(en) opgehaald.
            Importeren naar Kassa is nog niet beschikbaar.
          </div>
        ) : null}
        {(connected || requiresSms) ? (
          <Button type="button" variant="secondary" disabled={busy} onClick={async () => {
            const result = await run(() => picnicRequest('connect', { method: 'DELETE' }), 'Picnic-account ontkoppeld.')
            if (result) {
              setAccount(result)
              setDeliveries([])
              setPreview(null)
            }
          }}>Picnic ontkoppelen</Button>
        ) : null}
        {notice ? <div role="status" data-testid="picnic-research-feedback">{notice}</div> : null}
      </div>
    </Card>
  )
}
