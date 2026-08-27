import { useEffect, useMemo, useRef, useState } from 'react'
import { Navigate, useBlocker } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import Button from '../../ui/Button'
import Card from '../../ui/Card'
import DataTable from '../../ui/DataTable.jsx'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'
import { fetchJsonWithAuth, isHouseholdAdminFromContext, readStoredAuthContext } from '../../lib/authSession'

const checkboxStyle = { accentColor: 'var(--color-brand-primary)', width: 16, height: 16 }

function draftMap(items) {
  return Object.fromEntries(items.map((item) => [String(item.id), {
    naam: String(item.naam || ''),
    active: Boolean(item.active),
    space_id: item.space_id != null ? String(item.space_id) : '',
  }]))
}

function csvEscape(value) {
  const text = String(value ?? '')
  if (!text.includes(',') && !text.includes('"') && !text.includes('\n')) return text
  return `"${text.replace(/"/g, '""')}"`
}

function downloadCsv(filename, rows) {
  const blob = new Blob([rows.join('\n')], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

function normalizeName(value) {
  return String(value || '').trim().replace(/\s+/g, ' ')
}

export default function SettingsLocationsManagementPage({ sublocationsEnabled = true }) {
  const isAdmin = isHouseholdAdminFromContext(readStoredAuthContext())
  const { showFeedback } = useAppFeedback()
  const [locations, setLocations] = useState([])
  const [sublocations, setSublocations] = useState([])
  const [locationDrafts, setLocationDrafts] = useState({})
  const [sublocationDrafts, setSublocationDrafts] = useState({})
  const [selectedLocationIds, setSelectedLocationIds] = useState([])
  const [selectedSublocationIds, setSelectedSublocationIds] = useState([])
  const [selectedLocationId, setSelectedLocationId] = useState('')
  const [newLocationName, setNewLocationName] = useState('')
  const [newSublocationName, setNewSublocationName] = useState('')
  const [newSublocationParentId, setNewSublocationParentId] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)

  async function loadData({ preserveDrafts = false } = {}) {
    setIsLoading(true)
    try {
      const requests = [fetchJsonWithAuth('/api/spaces')]
      if (sublocationsEnabled) requests.push(fetchJsonWithAuth('/api/sublocations'))
      const responses = await Promise.all(requests)
      const spacesResponse = responses[0]
      const spacesData = await spacesResponse.json().catch(() => ({}))
      if (!spacesResponse.ok) throw new Error(spacesData?.detail || 'Locaties konden niet worden geladen.')

      let nextSublocations = []
      if (sublocationsEnabled) {
        const sublocationsResponse = responses[1]
        const sublocationsData = await sublocationsResponse.json().catch(() => ({}))
        if (!sublocationsResponse.ok) throw new Error(sublocationsData?.detail || 'Sublocaties konden niet worden geladen.')
        nextSublocations = Array.isArray(sublocationsData?.items) ? sublocationsData.items : []
      }

      const nextLocations = Array.isArray(spacesData?.items) ? spacesData.items : []
      setLocations(nextLocations)
      setSublocations(nextSublocations)
      setLocationDrafts((current) => {
        const fresh = draftMap(nextLocations)
        if (!preserveDrafts) return fresh
        return Object.fromEntries(Object.entries(fresh).map(([id, value]) => [id, current[id] || value]))
      })
      setSublocationDrafts((current) => {
        const fresh = draftMap(nextSublocations)
        if (!preserveDrafts) return fresh
        return Object.fromEntries(Object.entries(fresh).map(([id, value]) => [id, current[id] || value]))
      })
      setSelectedLocationId((current) => {
        if (current && nextLocations.some((item) => String(item.id) === String(current))) return current
        const first = [...nextLocations].sort((a, b) => String(a.naam || '').localeCompare(String(b.naam || ''), 'nl'))[0]
        return first ? String(first.id) : ''
      })
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    if (!isAdmin) return
    loadData().catch((error) => showFeedback({
      variant: 'error',
      message: error?.message || 'Locaties konden niet worden geladen.',
    }))
  }, [isAdmin, sublocationsEnabled])

  const isCanonicalDirect = (item) => !sublocationsEnabled && normalizeName(item?.naam).toLowerCase() === 'direct'

  const locationDirtyCount = useMemo(() => locations.reduce((count, item) => {
    if (isCanonicalDirect(item)) return count
    const draft = locationDrafts[String(item.id)]
    if (!draft) return count
    return count + (
      normalizeName(draft.naam) !== normalizeName(item.naam)
      || Boolean(draft.active) !== Boolean(item.active)
        ? 1
        : 0
    )
  }, 0), [locations, locationDrafts, sublocationsEnabled])

  const sublocationDirtyCount = useMemo(() => sublocations.reduce((count, item) => {
    const draft = sublocationDrafts[String(item.id)]
    if (!draft) return count
    return count + (
      normalizeName(draft.naam) !== normalizeName(item.naam)
      || Boolean(draft.active) !== Boolean(item.active)
        ? 1
        : 0
    )
  }, 0), [sublocations, sublocationDrafts])

  const hasPendingChanges = locationDirtyCount > 0 || sublocationDirtyCount > 0
  const blocker = useBlocker(hasPendingChanges)
  const blockerPromptVisible = useRef(false)

  useEffect(() => {
    if (blocker.state !== 'blocked') {
      blockerPromptVisible.current = false
      return
    }
    if (blockerPromptVisible.current) return
    blockerPromptVisible.current = true

    showFeedback({
      variant: 'warning',
      title: 'Wijzigingen bewaren?',
      message: 'Er zijn nog niet-opgeslagen wijzigingen in Locaties. Wil je deze opslaan of de wijzigingen annuleren?',
      dismissMode: 'blocked',
      testId: 'locations-pending-changes-overlay',
      primaryActionLabel: 'Wijzigingen opslaan',
      secondaryActionLabel: 'Wijzigingen annuleren',
      onPrimaryAction: async () => {
        await savePendingChanges()
        blockerPromptVisible.current = false
        blocker.proceed()
      },
      onSecondaryAction: async () => {
        discardPendingChanges()
        blockerPromptVisible.current = false
        blocker.proceed()
      },
    })
  }, [blocker.state])

  useEffect(() => {
    const handleBeforeUnload = (event) => {
      if (!hasPendingChanges) return
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', handleBeforeUnload)
    return () => window.removeEventListener('beforeunload', handleBeforeUnload)
  }, [hasPendingChanges])

  function updateLocationDraft(id, patch) {
    const key = String(id)
    setLocationDrafts((current) => ({ ...current, [key]: { ...(current[key] || {}), ...patch } }))
  }

  function updateSublocationDraft(id, patch) {
    const key = String(id)
    setSublocationDrafts((current) => ({ ...current, [key]: { ...(current[key] || {}), ...patch } }))
  }

  function discardPendingChanges() {
    setLocationDrafts(draftMap(locations))
    setSublocationDrafts(draftMap(sublocations))
  }

  async function savePendingChanges() {
    const changedLocations = locations.filter((item) => {
      if (isCanonicalDirect(item)) return false
      const draft = locationDrafts[String(item.id)]
      return draft && (
        normalizeName(draft.naam) !== normalizeName(item.naam)
        || Boolean(draft.active) !== Boolean(item.active)
      )
    })
    const changedSublocations = sublocations.filter((item) => {
      const draft = sublocationDrafts[String(item.id)]
      return draft && (
        normalizeName(draft.naam) !== normalizeName(item.naam)
        || Boolean(draft.active) !== Boolean(item.active)
      )
    })

    for (const item of changedLocations) {
      if (!normalizeName(locationDrafts[String(item.id)]?.naam)) throw new Error('Elke hoofdlocatie moet een naam hebben.')
    }
    for (const item of changedSublocations) {
      if (!normalizeName(sublocationDrafts[String(item.id)]?.naam)) throw new Error('Elke sublocatie moet een naam hebben.')
    }

    setIsSaving(true)
    try {
      for (const item of changedLocations) {
        const draft = locationDrafts[String(item.id)]
        const response = await fetchJsonWithAuth(`/api/spaces/${encodeURIComponent(item.id)}`, {
          method: 'PUT',
          body: JSON.stringify({ naam: normalizeName(draft.naam), active: Boolean(draft.active) }),
        })
        const data = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(data?.detail || `Locatie ${item.naam} opslaan mislukt.`)
      }
      for (const item of changedSublocations) {
        const draft = sublocationDrafts[String(item.id)]
        const response = await fetchJsonWithAuth(`/api/sublocations/${encodeURIComponent(item.id)}`, {
          method: 'PUT',
          body: JSON.stringify({ naam: normalizeName(draft.naam), space_id: String(item.space_id || ''), active: Boolean(draft.active) }),
        })
        const data = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(data?.detail || `Sublocatie ${item.naam} opslaan mislukt.`)
      }
      await loadData()
    } finally {
      setIsSaving(false)
    }
  }

  async function addLocation() {
    const naam = normalizeName(newLocationName)
    if (!naam) {
      showFeedback({ variant: 'warning', message: 'Vul een naam voor de nieuwe hoofdlocatie in.' })
      return
    }
    if (!sublocationsEnabled && naam.toLowerCase() === 'direct') {
      showFeedback({ variant: 'warning', message: 'Direct is een vaste locatie en bestaat al.' })
      return
    }
    setIsSaving(true)
    try {
      const response = await fetchJsonWithAuth('/api/spaces', {
        method: 'POST',
        body: JSON.stringify({ naam, active: true }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data?.detail || 'Hoofdlocatie toevoegen mislukt.')
      setNewLocationName('')
      await loadData({ preserveDrafts: true })
      showFeedback({ variant: 'success', message: 'Hoofdlocatie toegevoegd.' })
    } catch (error) {
      showFeedback({ variant: 'error', message: error?.message || 'Hoofdlocatie toevoegen mislukt.' })
    } finally {
      setIsSaving(false)
    }
  }

  async function addSublocation() {
    const naam = normalizeName(newSublocationName)
    const spaceId = String(newSublocationParentId || selectedLocationId || '').trim()
    if (!spaceId || !naam) {
      showFeedback({ variant: 'warning', message: 'Kies een hoofdlocatie en vul een naam voor de sublocatie in.' })
      return
    }
    setIsSaving(true)
    try {
      const response = await fetchJsonWithAuth('/api/sublocations', {
        method: 'POST',
        body: JSON.stringify({ naam, space_id: spaceId, active: true }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data?.detail || 'Sublocatie toevoegen mislukt.')
      setNewSublocationName('')
      setNewSublocationParentId(spaceId)
      setSelectedLocationId(spaceId)
      await loadData({ preserveDrafts: true })
      showFeedback({ variant: 'success', message: 'Sublocatie toegevoegd.' })
    } catch (error) {
      showFeedback({ variant: 'error', message: error?.message || 'Sublocatie toevoegen mislukt.' })
    } finally {
      setIsSaving(false)
    }
  }

  function toggleSelectedLocation(id) {
    const key = String(id)
    setSelectedLocationIds((current) => current.includes(key) ? current.filter((item) => item !== key) : [...current, key])
  }

  function toggleSelectedSublocation(id) {
    const key = String(id)
    setSelectedSublocationIds((current) => current.includes(key) ? current.filter((item) => item !== key) : [...current, key])
  }

  async function deleteLocations() {
    const items = locations.filter((item) => selectedLocationIds.includes(String(item.id)) && !isCanonicalDirect(item))
    if (!items.length) return
    showFeedback({
      variant: 'warning',
      title: 'Geselecteerde locaties verwijderen?',
      message: `Je verwijdert ${items.length} hoofdlocatie${items.length === 1 ? '' : 's'}.`,
      dismissMode: 'blocked',
      primaryActionLabel: 'Verwijderen',
      secondaryActionLabel: 'Annuleren',
      onPrimaryAction: async () => {
        for (const item of items) {
          const response = await fetchJsonWithAuth(`/api/spaces/${encodeURIComponent(item.id)}`, { method: 'DELETE' })
          const data = await response.json().catch(() => ({}))
          if (!response.ok) throw new Error(data?.detail || `Locatie ${item.naam} verwijderen mislukt.`)
        }
        setSelectedLocationIds([])
        await loadData({ preserveDrafts: true })
        showFeedback({ variant: 'success', message: 'Geselecteerde locaties verwijderd.' })
      },
      onSecondaryAction: async () => {},
    })
  }

  async function deleteSublocations() {
    const items = sublocations.filter((item) => selectedSublocationIds.includes(String(item.id)))
    if (!items.length) return
    showFeedback({
      variant: 'warning',
      title: 'Geselecteerde sublocaties verwijderen?',
      message: `Je verwijdert ${items.length} sublocatie${items.length === 1 ? '' : 's'}.`,
      dismissMode: 'blocked',
      primaryActionLabel: 'Verwijderen',
      secondaryActionLabel: 'Annuleren',
      onPrimaryAction: async () => {
        for (const item of items) {
          const response = await fetchJsonWithAuth(`/api/sublocations/${encodeURIComponent(item.id)}`, { method: 'DELETE' })
          const data = await response.json().catch(() => ({}))
          if (!response.ok) throw new Error(data?.detail || `Sublocatie ${item.naam} verwijderen mislukt.`)
        }
        setSelectedSublocationIds([])
        await loadData({ preserveDrafts: true })
        showFeedback({ variant: 'success', message: 'Geselecteerde sublocaties verwijderd.' })
      },
      onSecondaryAction: async () => {},
    })
  }

  const selectableLocations = locations.filter((item) => !isCanonicalDirect(item))
  const allLocationsSelected = selectableLocations.length > 0 && selectableLocations.every((item) => selectedLocationIds.includes(String(item.id)))
  const allSublocationsSelected = sublocations.length > 0 && sublocations.every((item) => selectedSublocationIds.includes(String(item.id)))

  const locationColumns = useMemo(() => [
    {
      key: 'select',
      width: 48,
      renderFilter: ({ placement }) => placement === 'header' ? (
        <input
          type="checkbox"
          style={checkboxStyle}
          aria-label="Selecteer alle locaties"
          checked={allLocationsSelected}
          onChange={() => setSelectedLocationIds(allLocationsSelected ? [] : selectableLocations.map((item) => String(item.id)))}
        />
      ) : null,
    },
    { key: 'naam', header: 'Locatie', width: 420, filterable: true, filterLabel: 'Filter op locatie', getFilterValue: (row) => locationDrafts[String(row.id)]?.naam ?? row.naam },
    {
      key: 'active',
      header: 'Actief',
      width: 140,
      renderFilter: ({ value, onChange, placement }) => placement === 'filter' ? (
        <select className="rz-input rz-inline-input" aria-label="Filter op actief" value={value || ''} onChange={(event) => onChange(event.target.value)}>
          <option value="">Alle</option>
          <option value="ja">Actief</option>
          <option value="nee">Inactief</option>
        </select>
      ) : null,
      filterable: true,
      filterPredicate: (row, value) => !value || (value === 'ja' ? Boolean(locationDrafts[String(row.id)]?.active ?? row.active) : !Boolean(locationDrafts[String(row.id)]?.active ?? row.active)),
    },
    sublocationsEnabled ? { key: 'sublocation_count', header: 'Aantal sublocaties', width: 180, filterable: true, filterLabel: 'Filter op aantal sublocaties' } : null,
  ].filter(Boolean), [allLocationsSelected, locations, selectedLocationIds, locationDrafts, sublocationsEnabled])

  const visibleSublocations = useMemo(() => sublocations.filter((item) => String(item.space_id || '') === String(selectedLocationId || '')), [sublocations, selectedLocationId])
  const allVisibleSublocationsSelected = visibleSublocations.length > 0 && visibleSublocations.every((item) => selectedSublocationIds.includes(String(item.id)))

  const sublocationColumns = useMemo(() => [
    {
      key: 'select',
      width: 48,
      renderFilter: ({ placement }) => placement === 'header' ? (
        <input
          type="checkbox"
          style={checkboxStyle}
          aria-label="Selecteer alle zichtbare sublocaties"
          checked={allVisibleSublocationsSelected}
          onChange={() => setSelectedSublocationIds((current) => {
            const visibleIds = visibleSublocations.map((item) => String(item.id))
            if (allVisibleSublocationsSelected) return current.filter((id) => !visibleIds.includes(id))
            return Array.from(new Set([...current, ...visibleIds]))
          })}
        />
      ) : null,
    },
    { key: 'naam', header: 'Sublocatie', width: 420, filterable: true, filterLabel: 'Filter op sublocatie', getFilterValue: (row) => sublocationDrafts[String(row.id)]?.naam ?? row.naam },
    {
      key: 'active',
      header: 'Actief',
      width: 140,
      renderFilter: ({ value, onChange, placement }) => placement === 'filter' ? (
        <select className="rz-input rz-inline-input" aria-label="Filter sublocaties op actief" value={value || ''} onChange={(event) => onChange(event.target.value)}>
          <option value="">Alle</option>
          <option value="ja">Actief</option>
          <option value="nee">Inactief</option>
        </select>
      ) : null,
      filterable: true,
      filterPredicate: (row, value) => !value || (value === 'ja' ? Boolean(sublocationDrafts[String(row.id)]?.active ?? row.active) : !Boolean(sublocationDrafts[String(row.id)]?.active ?? row.active)),
    },
  ], [allVisibleSublocationsSelected, visibleSublocations, selectedSublocationIds, sublocationDrafts])

  if (!isAdmin) return <Navigate to="/instellingen" replace />

  return (
    <AppShell title="Locaties" showExit={false}>
      <Card className="rz-settings-spaces-card">
        <div style={{ display: 'grid', gap: 24, width: '100%' }} data-testid="settings-locations-page" data-sublocations-enabled={sublocationsEnabled ? 'true' : 'false'}>
          <div>
            <h2 style={{ margin: 0, fontSize: 20 }}>Beheer Locaties</h2>
            {!sublocationsEnabled ? (
              <p style={{ margin: '8px 0 0', color: '#667085' }}>Dit huishouden gebruikt globale locaties. Sublocaties zijn daarom niet actief.</p>
            ) : null}
          </div>

          <section style={{ display: 'grid', gap: 14 }} data-testid="main-locations-section">
            <DataTable
              dataTestId="settings-locations-table"
              columns={locationColumns}
              data={locations}
              emptyMessage={isLoading ? 'Locaties laden…' : 'Nog geen locaties beschikbaar.'}
              wrapperClassName="rz-stock-table-wrapper"
              tableClassName="rz-stock-table"
              renderRow={(item) => {
                const direct = isCanonicalDirect(item)
                const draft = locationDrafts[String(item.id)] || { naam: item.naam, active: item.active }
                const selected = selectedLocationIds.includes(String(item.id))
                const detailSelected = String(selectedLocationId) === String(item.id)
                return (
                  <tr key={item.id} className={selected || detailSelected ? 'rz-row-selected' : ''} onDoubleClick={() => sublocationsEnabled && setSelectedLocationId(String(item.id))} title={sublocationsEnabled ? 'Dubbelklik om sublocaties van deze locatie te tonen' : undefined}>
                    <td>
                      <input type="checkbox" style={checkboxStyle} aria-label={`Selecteer ${item.naam}`} checked={selected} disabled={direct} onChange={() => toggleSelectedLocation(item.id)} />
                    </td>
                    <td>
                      {direct ? (
                        <span data-testid="canonical-direct-location" aria-label="Locatienaam Direct">Direct</span>
                      ) : (
                        <input className="rz-input rz-inline-input" value={draft.naam} onChange={(event) => updateLocationDraft(item.id, { naam: event.target.value })} aria-label={`Locatienaam ${item.naam}`} />
                      )}
                    </td>
                    <td className="rz-num">
                      <input type="checkbox" style={checkboxStyle} checked={direct ? true : Boolean(draft.active)} disabled={direct} onChange={(event) => updateLocationDraft(item.id, { active: event.target.checked })} aria-label={`Actief ${item.naam}`} />
                    </td>
                    {sublocationsEnabled ? <td className="rz-num">{Number(item.sublocation_count || 0)}</td> : null}
                  </tr>
                )
              }}
            />

            <div className="rz-stock-table-actions" style={{ justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
              <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                <Button type="button" variant="secondary" disabled={selectedLocationIds.length === 0} onClick={() => downloadCsv('rezzerv-locaties.csv', ['Locatie,Actief', ...locations.filter((item) => selectedLocationIds.includes(String(item.id))).map((item) => { const draft = locationDrafts[String(item.id)] || item; return [draft.naam, draft.active ? 'Ja' : 'Nee'].map(csvEscape).join(',') })])}>Exporteren</Button>
                <Button type="button" variant="secondary" disabled={selectedLocationIds.length === 0 || isSaving} onClick={deleteLocations}>Verwijderen</Button>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }} data-testid="new-main-location-row">
                <label htmlFor="new-main-location" style={{ fontWeight: 600, whiteSpace: 'nowrap' }}>Nieuwe hoofdlocatie</label>
                <input id="new-main-location" className="rz-input" style={{ width: 300 }} value={newLocationName} onChange={(event) => setNewLocationName(event.target.value)} placeholder="Bijvoorbeeld: Woning" />
                <Button type="button" disabled={isSaving} onClick={addLocation}>Toevoegen</Button>
              </div>
            </div>
          </section>

          {sublocationsEnabled ? (
            <section style={{ display: 'grid', gap: 14 }} data-testid="sublocations-section">
              <div style={{ fontWeight: 700, color: '#0f172a' }} data-testid="sublocations-heading">
                Sublocaties{selectedLocationId ? ` van ${locations.find((item) => String(item.id) === String(selectedLocationId))?.naam || ''}` : ''}
              </div>
              <DataTable
                dataTestId="settings-sublocations-table"
                columns={sublocationColumns}
                data={visibleSublocations}
                emptyMessage={selectedLocationId ? 'Nog geen sublocaties beschikbaar voor deze locatie.' : 'Kies een hoofdlocatie.'}
                wrapperClassName="rz-stock-table-wrapper"
                tableClassName="rz-stock-table"
                renderRow={(item) => {
                  const draft = sublocationDrafts[String(item.id)] || { naam: item.naam, active: item.active }
                  const selected = selectedSublocationIds.includes(String(item.id))
                  return (
                    <tr key={item.id} className={selected ? 'rz-row-selected' : ''}>
                      <td><input type="checkbox" style={checkboxStyle} aria-label={`Selecteer ${item.naam}`} checked={selected} onChange={() => toggleSelectedSublocation(item.id)} /></td>
                      <td><input className="rz-input rz-inline-input" value={draft.naam} onChange={(event) => updateSublocationDraft(item.id, { naam: event.target.value })} aria-label={`Sublocatienaam ${item.naam}`} /></td>
                      <td className="rz-num"><input type="checkbox" style={checkboxStyle} checked={Boolean(draft.active)} onChange={(event) => updateSublocationDraft(item.id, { active: event.target.checked })} aria-label={`Actief ${item.naam}`} /></td>
                    </tr>
                  )
                }}
              />
              <div className="rz-stock-table-actions" style={{ justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
                <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                  <Button type="button" variant="secondary" disabled={selectedSublocationIds.length === 0} onClick={() => downloadCsv('rezzerv-sublocaties.csv', ['Sublocatie,Locatie,Actief', ...sublocations.filter((item) => selectedSublocationIds.includes(String(item.id))).map((item) => { const draft = sublocationDrafts[String(item.id)] || item; return [draft.naam, item.space_name || '', draft.active ? 'Ja' : 'Nee'].map(csvEscape).join(',') })])}>Exporteren</Button>
                  <Button type="button" variant="secondary" disabled={selectedSublocationIds.length === 0 || isSaving} onClick={deleteSublocations}>Verwijderen</Button>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }} data-testid="new-sublocation-row">
                  <label htmlFor="new-sublocation-parent" style={{ fontWeight: 600, whiteSpace: 'nowrap' }}>Nieuwe sublocatie</label>
                  <select id="new-sublocation-parent" className="rz-input" aria-label="Hoofdlocatie voor nieuwe sublocatie" value={newSublocationParentId || selectedLocationId} onChange={(event) => { setNewSublocationParentId(event.target.value); setSelectedLocationId(event.target.value) }}>
                    <option value="">Kies hoofdlocatie</option>
                    {[...locations].sort((a, b) => String(a.naam || '').localeCompare(String(b.naam || ''), 'nl')).map((item) => <option key={item.id} value={String(item.id)}>{item.naam}</option>)}
                  </select>
                  <input className="rz-input" style={{ width: 240 }} aria-label="Naam nieuwe sublocatie" value={newSublocationName} onChange={(event) => setNewSublocationName(event.target.value)} placeholder="Bijvoorbeeld: Kast 1" />
                  <Button type="button" disabled={isSaving || locations.length === 0} onClick={addSublocation}>Toevoegen</Button>
                </div>
              </div>
            </section>
          ) : null}
        </div>
      </Card>
    </AppShell>
  )
}
