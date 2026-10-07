import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import Button from '../../ui/Button'
import Card from '../../ui/Card'
import Input from '../../ui/Input'
import { fetchAuthContext, readStoredAuthContext } from '../../lib/authSession'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'
import {
  createAdditionalHousehold,
  deleteAdditionalHousehold,
  fetchMyHouseholds,
} from './services/householdLifecycleService'

function deletionExplanation(reason) {
  if (reason === 'active_household') return 'Actief huishouden — wissel eerst naar een ander huishouden.'
  if (reason === 'other_members') return 'Verwijderen kan pas wanneer alleen jij als Beheerder overblijft.'
  if (reason === 'not_admin') return 'Alleen een Beheerder van dit huishouden kan het verwijderen.'
  return ''
}

export default function SettingsMyHouseholdsPage() {
  const navigate = useNavigate()
  const { showFeedback } = useAppFeedback()
  const context = readStoredAuthContext()
  const [payload, setPayload] = useState({ items: [], can_create_household: false })
  const [loading, setLoading] = useState(true)
  const [newName, setNewName] = useState('')
  const [creating, setCreating] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [deleteConfirmation, setDeleteConfirmation] = useState('')
  const [deleting, setDeleting] = useState(false)

  async function refresh() {
    const next = await fetchMyHouseholds()
    setPayload({
      items: Array.isArray(next?.items) ? next.items : [],
      can_create_household: next?.can_create_household === true,
    })
    return next
  }

  useEffect(() => {
    let active = true
    setLoading(true)
    fetchMyHouseholds()
      .then((next) => {
        if (!active) return
        setPayload({
          items: Array.isArray(next?.items) ? next.items : [],
          can_create_household: next?.can_create_household === true,
        })
      })
      .catch((error) => {
        if (active) {
          showFeedback({
            variant: 'error',
            title: 'Huishoudens niet geladen',
            message: error?.message || 'Huishoudens konden niet worden geladen.',
          })
        }
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => { active = false }
  }, [showFeedback])

  async function handleCreate(event) {
    event.preventDefault()
    const name = String(newName || '').trim()
    if (!name || creating) return

    setCreating(true)
    try {
      await createAdditionalHousehold(name)
      await fetchAuthContext({ force: true })
      navigate('/onboarding', { replace: true })
    } catch (error) {
      showFeedback({
        variant: 'error',
        title: 'Huishouden niet gemaakt',
        message: error?.message || 'Nieuw huishouden kon niet worden gemaakt.',
      })
    } finally {
      setCreating(false)
    }
  }

  function openDelete(item) {
    setDeleteTarget(item)
    setDeleteConfirmation('')
  }

  async function confirmDelete() {
    if (!deleteTarget?.household_id || deleting) return
    const expected = `VERWIJDER ${deleteTarget.household_id}`
    if (deleteConfirmation.trim() !== expected) return

    setDeleting(true)
    try {
      await deleteAdditionalHousehold(deleteTarget.household_id, expected)
      setDeleteTarget(null)
      setDeleteConfirmation('')
      await refresh()
      showFeedback({
        variant: 'success',
        message: `${deleteTarget.household_name || 'Het huishouden'} is verwijderd.`,
      })
    } catch (error) {
      showFeedback({
        variant: 'error',
        title: 'Huishouden niet verwijderd',
        message: error?.message || 'Huishouden kon niet worden verwijderd.',
      })
    } finally {
      setDeleting(false)
    }
  }

  const expectedDeleteText = deleteTarget ? `VERWIJDER ${deleteTarget.household_id}` : ''

  return (
    <AppShell title="Mijn huishoudens" showExit={false}>
      <div style={{ display: 'grid', gap: 16 }} data-testid="my-households-page">
        <Card>
          <h2>Mijn huishoudens</h2>
          <p>
            Je account kan bij meerdere huishoudens horen. De rol en instellingen gelden per huishouden afzonderlijk.
          </p>

          {loading ? <p>Huishoudens laden…</p> : (
            <div style={{ display: 'grid', gap: 12 }} data-testid="my-households-list">
              {payload.items.map((item) => (
                <div
                  key={item.household_id}
                  style={{ border: '1px solid #dfe4ea', borderRadius: 12, padding: 14 }}
                  data-testid={`my-household-${item.household_id}`}
                >
                  <strong>{item.household_name || 'Huishouden'}</strong>
                  <div>Rol: {item.role === 'admin' ? 'Beheerder' : 'Gebruiker'}</div>
                  {item.active ? <div>Actief huishouden</div> : null}
                  {!item.active && item.can_delete ? (
                    <Button
                      type="button"
                      variant="secondary"
                      onClick={() => openDelete(item)}
                      data-testid={`delete-household-${item.household_id}`}
                    >
                      Huishouden verwijderen
                    </Button>
                  ) : null}
                  {!item.can_delete && deletionExplanation(item.delete_reason) ? (
                    <small>{deletionExplanation(item.delete_reason)}</small>
                  ) : null}
                </div>
              ))}
            </div>
          )}
        </Card>

        {payload.can_create_household ? (
          <Card>
            <h2>Nieuw huishouden maken</h2>
            <p>
              Je wordt Beheerder van het nieuwe huishouden. Daarna doorloop je alleen voor dit huishouden de initiële Inhuis-inrichting.
            </p>
            <form onSubmit={handleCreate} className="rz-form">
              <Input
                label="Naam nieuw huishouden"
                value={newName}
                onChange={(event) => setNewName(event.target.value)}
                required
                maxLength={120}
                disabled={creating}
                placeholder="Bijvoorbeeld Nieuwe woning"
                data-testid="new-household-name"
              />
              <Button
                type="submit"
                disabled={creating || !String(newName || '').trim()}
                data-testid="create-household-submit"
              >
                {creating ? 'Aanmaken…' : 'Nieuw huishouden maken'}
              </Button>
            </form>
          </Card>
        ) : null}

        {deleteTarget ? (
          <div className="rz-modal-backdrop" role="presentation">
            <div
              className="rz-modal-card"
              role="dialog"
              aria-modal="true"
              aria-labelledby="delete-household-title"
              data-testid="delete-household-confirmation"
            >
              <h3 id="delete-household-title">Huishouden definitief verwijderen</h3>
              <p>
                Je verwijdert <strong>{deleteTarget.household_name}</strong> en alle gegevens van dit huishouden permanent.
                Je Inhuis-account en je andere huishoudens blijven bestaan.
              </p>
              <p>
                Typ exact <strong>{expectedDeleteText}</strong> om te bevestigen.
              </p>
              <Input
                label="Bevestiging"
                value={deleteConfirmation}
                onChange={(event) => setDeleteConfirmation(event.target.value)}
                disabled={deleting}
                data-testid="delete-household-confirmation-input"
              />
              <div className="rz-modal-actions">
                <Button
                  type="button"
                  variant="secondary"
                  disabled={deleting}
                  onClick={() => {
                    setDeleteTarget(null)
                    setDeleteConfirmation('')
                  }}
                >
                  Annuleren
                </Button>
                <Button
                  type="button"
                  disabled={deleting || deleteConfirmation.trim() !== expectedDeleteText}
                  onClick={confirmDelete}
                  data-testid="delete-household-confirm"
                >
                  {deleting ? 'Verwijderen…' : 'Definitief verwijderen'}
                </Button>
              </div>
            </div>
          </div>
        ) : null}

        <small>Actief account: {context?.email || ''}</small>
      </div>
    </AppShell>
  )
}
