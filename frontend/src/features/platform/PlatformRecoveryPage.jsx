import React from 'react'
import Header from '../../ui/Header.jsx'
import Card from '../../ui/Card.jsx'
import Button from '../../ui/Button.jsx'
import { API_BASE_URL } from '../../lib/apiClient.js'

const PURGE_ENDPOINT = '/api/admin/receipts/purge-archived'
const RESET_HOUSEHOLD_ENDPOINT = '/api/platform/recovery/reset-household'

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


async function resetHousehold(householdId, confirmation) {
  const response = await fetch(`${API_BASE_URL}${RESET_HOUSEHOLD_ENDPOINT}`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    cache: 'no-store',
    body: JSON.stringify({ household_id: householdId, confirmation }),
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(payload?.detail || `Huishoudreset is mislukt (${response.status}).`)
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
  const [resetHouseholdId, setResetHouseholdId] = React.useState('')
  const [resetConfirmationTarget, setResetConfirmationTarget] = React.useState('')
  const [resetConfirmationText, setResetConfirmationText] = React.useState('')
  const [resetRunning, setResetRunning] = React.useState(false)
  const [resetResult, setResetResult] = React.useState(null)
  const [resetError, setResetError] = React.useState('')

  const normalizedHouseholdId = householdId.trim()
  const confirmationMatches = confirmationTarget !== '' && confirmationText.trim() === confirmationTarget
  const normalizedResetHouseholdId = resetHouseholdId.trim()
  const resetConfirmationPhrase = resetConfirmationTarget ? `RESET ${resetConfirmationTarget}` : ''
  const resetConfirmationMatches = resetConfirmationTarget !== ''
    && resetConfirmationText.trim() === resetConfirmationPhrase

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

  function openResetConfirmation() {
    if (!normalizedResetHouseholdId || resetRunning) return
    setResetConfirmationTarget(normalizedResetHouseholdId)
    setResetConfirmationText('')
    setResetResult(null)
    setResetError('')
  }

  function cancelResetConfirmation() {
    if (resetRunning) return
    setResetConfirmationTarget('')
    setResetConfirmationText('')
  }

  async function executeHouseholdReset() {
    if (!resetConfirmationMatches || resetRunning) return
    const target = resetConfirmationTarget
    const confirmation = resetConfirmationPhrase
    setResetRunning(true)
    setResetError('')
    setResetResult(null)
    try {
      const payload = await resetHousehold(target, confirmation)
      setResetResult(payload)
      setResetConfirmationTarget('')
      setResetConfirmationText('')
    } catch (requestError) {
      setResetError(requestError?.message || 'Huishoudreset is mislukt.')
    } finally {
      setResetRunning(false)
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

            <Card className="rz-card-home">
              <h3>Huishouden volledig resetten</h3>
              <p>
                Verwijdert alle huishoudspecifieke inhoud en instellingen. Het huishoudrecord,
                de leden, hun rollen, accounts, wachtwoord-/inloggegevens en de auditgeschiedenis
                blijven behouden.
              </p>
              <p>
                Actieve sessies van dit huishouden worden ingetrokken. Gebruikers kunnen daarna
                met hun bestaande inloggegevens opnieuw inloggen in het lege huishouden.
              </p>
              <p>
                Systeemhuishouden 0 is uitgesloten. Deze actie is permanent en wordt volledig
                transactioneel uitgevoerd: bij een onvolledige reset wordt alles teruggedraaid.
              </p>

              <label htmlFor="platform-reset-household-id">Household ID</label>
              <input
                id="platform-reset-household-id"
                data-testid="platform-reset-household-id"
                type="text"
                value={resetHouseholdId}
                onChange={(event) => setResetHouseholdId(event.target.value)}
                disabled={resetRunning || Boolean(resetConfirmationTarget)}
                autoComplete="off"
              />

              {resetError ? <p role="alert">{resetError}</p> : null}
              {resetResult ? (
                <div data-testid="platform-reset-household-result">
                  <p>Huishouden <strong>{resetResult.household_id}</strong> is volledig gereset.</p>
                  <p>
                    {Number(resetResult.deleted_row_count || 0)} huishoudrecord(s) verwijderd;
                    {Number(resetResult.preserved_member_count || 0)} lidmaatschap(pen) behouden;
                    {Number(resetResult.sessions_revoked || 0)} sessie(s) ingetrokken.
                  </p>
                  <p>Audit-ID: {resetResult.audit_id}</p>
                </div>
              ) : null}

              {resetConfirmationTarget ? (
                <div data-testid="platform-reset-household-confirmation">
                  <p>
                    Je staat op het punt alle huishoudspecifieke gegevens van huishouden
                    <strong> {resetConfirmationTarget}</strong> permanent te verwijderen.
                  </p>
                  <p>
                    Typ exact <strong>{resetConfirmationPhrase}</strong> om de reset vrij te geven.
                  </p>
                  <label htmlFor="platform-reset-household-confirmation-text">Bevestiging</label>
                  <input
                    id="platform-reset-household-confirmation-text"
                    data-testid="platform-reset-household-confirmation-text"
                    type="text"
                    value={resetConfirmationText}
                    onChange={(event) => setResetConfirmationText(event.target.value)}
                    disabled={resetRunning}
                    autoComplete="off"
                  />
                  <Button
                    type="button"
                    onClick={executeHouseholdReset}
                    disabled={!resetConfirmationMatches || resetRunning}
                  >
                    {resetRunning ? 'Reset uitvoeren…' : 'Huishouden definitief resetten'}
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={cancelResetConfirmation}
                    disabled={resetRunning}
                  >
                    Annuleren
                  </Button>
                </div>
              ) : (
                <Button
                  type="button"
                  variant="secondary"
                  onClick={openResetConfirmation}
                  disabled={!normalizedResetHouseholdId || resetRunning}
                >
                  Huishouden volledig resetten
                </Button>
              )}
            </Card>
          </Card>
        </div>
      </div>
    </div>
  )
}
