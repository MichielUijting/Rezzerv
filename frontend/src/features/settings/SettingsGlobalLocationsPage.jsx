import { useEffect, useMemo, useState } from 'react'
import AppShell from '../../app/AppShell'
import Card from '../../ui/Card'
import Button from '../../ui/Button'
import { buildTableWidth } from '../../ui/resizableTable'
import Table from '../../ui/Table'
import { canCurrentUserPerform, fetchJsonWithAuth, readStoredAuthContext } from '../../lib/authSession.js'

const globalLocationColumnWidths = {
  naam: 420,
  actief: 140,
}

function draftMap(items) {
  return Object.fromEntries(
    items.map((item) => [String(item.id), {
      naam: String(item.naam || ''),
      active: Boolean(item.active),
    }]),
  )
}

export default function SettingsGlobalLocationsPage() {
  const context = readStoredAuthContext()
  const canManage = canCurrentUserPerform('locations.manage', context)
  const [locations, setLocations] = useState([])
  const [drafts, setDrafts] = useState({})
  const [newName, setNewName] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  async function loadLocations() {
    setIsLoading(true)
    setError('')
    try {
      const response = await fetchJsonWithAuth('/api/spaces')
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload?.detail || 'Locaties konden niet worden geladen.')
      const items = Array.isArray(payload?.items) ? payload.items : []
      setLocations(items)
      setDrafts(draftMap(items))
    } catch (loadError) {
      setError(loadError?.message || 'Locaties konden niet worden geladen.')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    if (canManage) loadLocations()
    else setIsLoading(false)
  }, [canManage])

  const sortedLocations = useMemo(
    () => [...locations].sort((a, b) => String(a?.naam || '').localeCompare(String(b?.naam || ''), 'nl')),
    [locations],
  )

  const dirtyLocations = useMemo(() => sortedLocations.filter((item) => {
    const draft = drafts[String(item.id)]
    if (!draft) return false
    return String(draft.naam || '').trim() !== String(item.naam || '').trim()
      || Boolean(draft.active) !== Boolean(item.active)
  }), [sortedLocations, drafts])

  function updateDraft(id, patch) {
    setMessage('')
    setError('')
    setDrafts((current) => ({
      ...current,
      [String(id)]: { ...(current[String(id)] || {}), ...patch },
    }))
  }

  async function saveChanges() {
    if (!canManage || dirtyLocations.length === 0) return
    setIsSaving(true)
    setMessage('')
    setError('')
    try {
      for (const item of dirtyLocations) {
        const draft = drafts[String(item.id)] || {}
        const naam = String(draft.naam || '').trim()
        if (!naam) throw new Error('Een locatienaam mag niet leeg zijn.')
        const response = await fetchJsonWithAuth(`/api/spaces/${encodeURIComponent(item.id)}`, {
          method: 'PUT',
          body: JSON.stringify({ naam, active: Boolean(draft.active) }),
        })
        const payload = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(payload?.detail || `Locatie '${naam}' kon niet worden opgeslagen.`)
      }
      await loadLocations()
      setMessage('Locaties opgeslagen.')
    } catch (saveError) {
      setError(saveError?.message || 'Locaties opslaan mislukt.')
    } finally {
      setIsSaving(false)
    }
  }

  async function addLocation() {
    const naam = String(newName || '').trim()
    if (!naam || !canManage) return
    setIsSaving(true)
    setMessage('')
    setError('')
    try {
      const response = await fetchJsonWithAuth('/api/spaces', {
        method: 'POST',
        body: JSON.stringify({ naam, active: true }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload?.detail || 'Locatie toevoegen mislukt.')
      setNewName('')
      await loadLocations()
      setMessage('Locatie toegevoegd.')
    } catch (saveError) {
      setError(saveError?.message || 'Locatie toevoegen mislukt.')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <AppShell title="Locaties" showExit={false}>
      <Card>
        <div style={{ display: 'grid', gap: 20 }} data-testid="settings-global-locations-page">
          <div>
            <h2 style={{ margin: '0 0 8px 0', fontSize: 20 }}>Hoofdlocaties</h2>
            <p style={{ margin: 0, color: '#667085' }}>
              Dit huishouden gebruikt globale locaties. Je beheert daarom alleen hoofdlocaties; sublocaties zijn niet actief.
            </p>
          </div>

          {!canManage ? (
            <div className="rz-inline-feedback rz-inline-feedback--warning">
              Je hebt geen toestemming om locaties te beheren.
            </div>
          ) : null}
          {error ? <div className="rz-inline-feedback rz-inline-feedback--error">{error}</div> : null}
          {message ? <div className="rz-inline-feedback rz-inline-feedback--success">{message}</div> : null}

          {canManage ? (
            <>
              <Table
                wrapperClassName="rz-stock-table-wrapper"
                tableClassName="rz-stock-table"
                dataTestId="settings-global-locations-table"
                tableStyle={{
                  tableLayout: 'fixed',
                  width: buildTableWidth(globalLocationColumnWidths),
                  minWidth: buildTableWidth(globalLocationColumnWidths),
                }}
              >
                <colgroup>
                  <col style={{ width: '420px' }} />
                  <col style={{ width: '140px' }} />
                </colgroup>
                <thead>
                  <tr className="rz-table-header">
                    <th>Locatie</th>
                    <th className="rz-num">Actief</th>
                  </tr>
                </thead>
                <tbody>
                  {isLoading ? (
                    <tr><td colSpan={2}>Locaties laden…</td></tr>
                  ) : sortedLocations.length === 0 ? (
                    <tr><td colSpan={2}>Nog geen hoofdlocaties beschikbaar.</td></tr>
                  ) : sortedLocations.map((item) => {
                    const draft = drafts[String(item.id)] || { naam: item.naam, active: item.active }
                    return (
                      <tr key={item.id}>
                        <td>
                          <input
                            className="rz-input rz-inline-input"
                            value={draft.naam}
                            onChange={(event) => updateDraft(item.id, { naam: event.target.value })}
                            aria-label={`Locatienaam ${item.naam}`}
                          />
                        </td>
                        <td className="rz-num">
                          <input
                            type="checkbox"
                            checked={Boolean(draft.active)}
                            onChange={(event) => updateDraft(item.id, { active: event.target.checked })}
                            aria-label={`Actief ${item.naam}`}
                          />
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </Table>

              <div style={{ display: 'flex', gap: 10, alignItems: 'end', flexWrap: 'wrap' }}>
                <label className="rz-input-field" style={{ flex: '1 1 280px' }}>
                  <div className="rz-label">Nieuwe hoofdlocatie</div>
                  <input
                    className="rz-input"
                    value={newName}
                    onChange={(event) => setNewName(event.target.value)}
                    placeholder="Bijvoorbeeld: Woning"
                    data-testid="global-location-name-input"
                  />
                </label>
                <Button
                  type="button"
                  variant="secondary"
                  onClick={addLocation}
                  disabled={isSaving || !String(newName || '').trim()}
                  data-testid="global-location-add"
                >
                  Toevoegen
                </Button>
                <Button
                  type="button"
                  onClick={saveChanges}
                  disabled={isSaving || dirtyLocations.length === 0}
                  data-testid="global-locations-save"
                >
                  {isSaving ? 'Opslaan…' : 'Wijzigingen opslaan'}
                </Button>
              </div>
            </>
          ) : null}
        </div>
      </Card>
    </AppShell>
  )
}
