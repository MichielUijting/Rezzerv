import { useEffect, useState } from 'react'
import Card from '../../ui/Card'
import Button from '../../ui/Button'
import Input from '../../ui/Input'
import { API_BASE_URL } from '../../lib/apiClient.js'
import { clearAuthSession } from '../../lib/authSession.js'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'

const CONFIRMATION = 'VERWIJDER MIJN ACCOUNT'

export default function AccountDeletionPanel() {
  const [preview, setPreview] = useState(null)
  const [error, setError] = useState('')
  const [expanded, setExpanded] = useState(false)
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [busy, setBusy] = useState(false)
  const { showFeedback } = useAppFeedback()

  useEffect(() => {
    if (!expanded) return undefined
    let active = true
    fetch(API_BASE_URL + '/api/account/deletion-preview', {
      credentials: 'include',
      headers: { Accept: 'application/json' },
    }).then(async (response) => {
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload.detail || 'Verwijdervoorbeeld kon niet worden geladen.')
      if (active) { setPreview(payload); setError('') }
    }).catch((reason) => {
      if (active) { setPreview(null); setError(reason.message || 'Verwijderen is niet beschikbaar.') }
    })
    return () => { active = false }
  }, [expanded])

  async function deleteAccount(event) {
    event.preventDefault()
    if (!preview || busy || confirmation !== CONFIRMATION || !password) return
    setBusy(true)
    try {
      const response = await fetch(API_BASE_URL + '/api/account', {
        method: 'DELETE',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ current_password: password, confirmation }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload.detail || 'Account verwijderen is niet gelukt.')
      clearAuthSession('Je account is verwijderd.')
      window.location.replace('/login')
    } catch (reason) {
      showFeedback({ variant: 'error', message: reason?.message || 'Account verwijderen is niet gelukt.' })
      setBusy(false)
    }
  }

  return (
    <Card>
      <section aria-labelledby="account-delete-title" data-testid="account-deletion-panel">
        <h3 id="account-delete-title">Mijn account verwijderen</h3>
        <p>
          Je account, wachtwoord en persoonlijke toegangsgegevens worden definitief verwijderd.
          Een huishouden met andere leden en alle bijbehorende huishoudgegevens blijven bestaan.
          Ben je daarvan Beheerder, dan wordt het oudste overblijvende account Beheerder.
          Een huishouden zonder andere leden wordt met zijn gegevens verwijderd.
        </p>
        {!expanded ? (
          <Button type="button" variant="secondary" onClick={() => setExpanded(true)} data-testid="account-delete-open">
            Accountverwijdering bekijken
          </Button>
        ) : (
          <form onSubmit={deleteAccount} style={{ display: 'grid', gap: 12 }} data-testid="account-delete-form">
            {error ? <p role="alert">{error}</p> : null}
            {preview ? (
              <p data-testid="account-deletion-preview">
                {preview.households_to_keep} huishouden(s) blijven behouden;{' '}
                {preview.households_to_delete} huishouden(s) zonder andere leden worden verwijderd.
                Dit kan niet ongedaan worden gemaakt.
              </p>
            ) : null}
            <Input
              label="Huidig wachtwoord"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              disabled={!preview || busy}
              required
              data-testid="account-delete-password"
            />
            <Input
              label={'Typ exact: ' + CONFIRMATION}
              value={confirmation}
              onChange={(event) => setConfirmation(event.target.value)}
              disabled={!preview || busy}
              required
              autoComplete="off"
              data-testid="account-delete-confirmation"
            />
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12, flexWrap: 'wrap' }}>
              <Button type="button" variant="secondary" disabled={busy} onClick={() => {
                setExpanded(false)
                setPassword('')
                setConfirmation('')
                setPreview(null)
              }}>Annuleren</Button>
              <Button
                type="submit"
                disabled={!preview || busy || !password || confirmation !== CONFIRMATION}
                data-testid="account-delete-submit"
              >
                {busy ? 'Verwijderen…' : 'Mijn account definitief verwijderen'}
              </Button>
            </div>
          </form>
        )}
      </section>
    </Card>
  )
}
