import React from 'react'
import Header from '../../ui/Header.jsx'
import Card from '../../ui/Card.jsx'
import Button from '../../ui/Button.jsx'
import { API_BASE_URL } from '../../lib/apiClient.js'

const PURGE_ENDPOINT = '/api/admin/receipts/purge-archived'

async function purgeArchivedReceipts(householdId) {
  const response = await fetch(`${API_BASE_URL}${PURGE_ENDPOINT}`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    cache: 'no-store',
    body: JSON.stringify({ household_id: householdId }),
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(payload?.detail || `Herstelactie is mislukt (${response.status}).`)
  }
  return payload
}

export default function PlatformRecoveryPage() {
  const [householdId, setHouseholdId] = React.useState('')
  const [confirmationTarget, setConfirmationTarget] = React.useState('')
  const [confirmationText, setConfirmationText] = React.useState('')
  const [running, setRunning] = React.useState(false)
  const [result, setResult] = React.useState(null)
  const [error, setError] = React.useState('')

  const normalizedHouseholdId = householdId.trim()
  const confirmationMatches = confirmationTarget !== '' && confirmationText.trim() === confirmationTarget

  function openConfirmation() {
    if (!normalizedHouseholdId || running) return
    setConfirmationTarget(normalizedHouseholdId)
    setConfirmationText('')
    setResult(null)
    setError('')
  }

  function cancelConfirmation() {
    if (running) return
    setConfirmationTarget('')
    setConfirmationText('')
  }

  async function executePurge() {
    if (!confirmationMatches || running) return
    const target = confirmationTarget
    setRunning(true)
    setError('')
    setResult(null)
    try {
      const payload = await purgeArchivedReceipts(target)
      setResult({ householdId: target, payload })
      setConfirmationTarget('')
      setConfirmationText('')
    } catch (requestError) {
      setError(requestError?.message || 'Herstelactie is mislukt.')
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="rz-screen" data-testid="platform-recovery-page">
      <Header title="Herstel" />
      <div className="rz-content">
        <div className="rz-content-inner">
          <Card className="rz-card-home">
            <h2>Platformherstel</h2>
            <p>Voer uitsluitend expliciet geautoriseerde herstelacties uit.</p>
            <p>Deze actie gebruikt geen actief huishouden en valt nooit terug op huishouden 0. Het doelhuishouden wordt uitsluitend uit het hieronder ingevoerde ID bepaald.</p>
            <p>Gearchiveerde bonnen worden permanent verwijderd uit de bijbehorende bon- en importgegevens. Deze verwijdering kan niet via deze pagina ongedaan worden gemaakt.</p>

            <Card className="rz-card-home">
              <h3>Gearchiveerde bonnen definitief verwijderen</h3>
              <p>Voer het exacte household ID in waarvan de reeds gearchiveerde bongegevens definitief mogen worden verwijderd.</p>

              <label htmlFor="platform-recovery-household-id">Household ID</label>
              <input
                id="platform-recovery-household-id"
                data-testid="platform-recovery-household-id"
                type="text"
                value={householdId}
                onChange={(event) => setHouseholdId(event.target.value)}
                disabled={running || Boolean(confirmationTarget)}
                autoComplete="off"
              />

              {error ? <p role="alert">{error}</p> : null}
              {result ? (
                <div data-testid="platform-recovery-result">
                  <p>Herstelactie afgerond voor huishouden: {result.householdId}</p>
                  <p>De server heeft de definitieve verwijdering succesvol verwerkt.</p>
                </div>
              ) : null}

              {confirmationTarget ? (
                <div data-testid="platform-recovery-confirmation">
                  <p>Je staat op het punt gearchiveerde bongegevens permanent te verwijderen voor huishouden <strong>{confirmationTarget}</strong>.</p>
                  <p>Typ het household ID hieronder opnieuw exact in om deze destructieve actie vrij te geven.</p>
                  <label htmlFor="platform-recovery-confirm-household-id">Household ID opnieuw</label>
                  <input
                    id="platform-recovery-confirm-household-id"
                    data-testid="platform-recovery-confirm-household-id"
                    type="text"
                    value={confirmationText}
                    onChange={(event) => setConfirmationText(event.target.value)}
                    disabled={running}
                    autoComplete="off"
                  />
                  <Button type="button" onClick={executePurge} disabled={!confirmationMatches || running}>
                    {running ? 'Bezig…' : 'Definitieve verwijdering bevestigen'}
                  </Button>
                  <Button type="button" variant="secondary" onClick={cancelConfirmation} disabled={running}>
                    Annuleren
                  </Button>
                </div>
              ) : (
                <Button
                  type="button"
                  variant="secondary"
                  onClick={openConfirmation}
                  disabled={!normalizedHouseholdId || running}
                >
                  Gearchiveerde bonnen definitief verwijderen
                </Button>
              )}
            </Card>
          </Card>
        </div>
      </div>
    </div>
  )
}
