import { useEffect, useMemo, useRef, useState } from 'react'
import { Navigate } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import Card from '../../ui/Card'
import Button from '../../ui/Button'
import { buildTableWidth } from '../../ui/resizableTable'
import Table from '../../ui/Table'
import { fetchJsonWithAuth, isHouseholdAdminFromContext, readStoredAuthContext } from '../../lib/authSession'

const initialLocationForm = { naam: '', active: true }
const initialSublocationForm = { naam: '', active: true, space_id: '' }
const initialLocationFilters = { naam: '', actiefJa: false, actiefNee: false, sublocaties: '' }
const initialSublocationFilters = { naam: '', actiefJa: false, actiefNee: false }
const locationTableColumns = [
  { key: 'select', width: 48 },
  { key: 'naam', width: 420 },
  { key: 'actief', width: 140 },
  { key: 'sublocaties', width: 180 },
]
const locationColumnWidths = Object.fromEntries(locationTableColumns.map(({ key, width }) => [key, width]))
const sublocationTableColumns = [
  { key: 'select', width: 48 },
  { key: 'naam', width: 420 },
  { key: 'actief', width: 140 },
]
const sublocationColumnWidths = Object.fromEntries(sublocationTableColumns.map(({ key, width }) => [key, width]))
const greenCheckboxStyle = { accentColor: '#1A3E2B', width: 16, height: 16 }

function Feedback({ type = 'info', children }) {
  if (!children) return null
  const isError = type === 'error'
  const background = isError ? '#fef2f2' : '#ecfdf3'
  const border = isError ? '#fecaca' : '#bbf7d0'
  const color = isError ? '#991b1b' : '#166534'
  return <div style={{ padding: '12px 14px', borderRadius: 12, border: `1px solid ${border}`, background, color }}>{children}</div>
}


function LocationModal({ open, form, onChange, onClose, onSubmit, busy }) {
  if (!open) return null
  return (
    <div className="rz-modal-backdrop" role="presentation">
      <div className="rz-modal-card" role="dialog" aria-modal="true" aria-labelledby="location-modal-title">
        <h3 id="location-modal-title" className="rz-modal-title">Nieuwe locatie</h3>
        <div style={{ display: 'grid', gap: 16 }}>
          <label className="rz-input-field">
            <div className="rz-label">Locatie naam</div>
            <input className="rz-input" autoFocus value={form.naam} onChange={(event) => onChange({ ...form, naam: event.target.value })} placeholder="Bijvoorbeeld: Garage" />
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 10, color: '#0f172a', fontWeight: 600 }}>
            <input type="checkbox" style={greenCheckboxStyle} checked={Boolean(form.active)} onChange={(event) => onChange({ ...form, active: event.target.checked })} />
            Actief
          </label>
        </div>
        <div className="rz-modal-actions">
          <Button type="button" variant="secondary" onClick={onClose} disabled={busy}>Annuleren</Button>
          <Button type="button" onClick={onSubmit} disabled={busy}>{busy ? 'Opslaan…' : 'Opslaan'}</Button>
        </div>
      </div>
    </div>
  )
}

function SublocationModal({ mode, form, onChange, onClose, onSubmit, busy, locationOptions }) {
  if (!mode) return null
  return (
    <div className="rz-modal-backdrop" role="presentation">
      <div className="rz-modal-card" role="dialog" aria-modal="true" aria-labelledby="sublocation-modal-title">
        <h3 id="sublocation-modal-title" className="rz-modal-title">Nieuwe sublocatie</h3>
        <div style={{ display: 'grid', gap: 16 }}>
          <label className="rz-input-field">
            <div className="rz-label">Locatie</div>
            <select className="rz-input" value={form.space_id} onChange={(event) => onChange({ ...form, space_id: event.target.value })}>
              <option value="">Kies een locatie</option>
              {locationOptions.map((option) => <option key={option.id} value={String(option.id)}>{option.naam}</option>)}
            </select>
          </label>
          <label className="rz-input-field">
            <div className="rz-label">Sublocatie naam</div>
            <input className="rz-input" autoFocus value={form.naam} onChange={(event) => onChange({ ...form, naam: event.target.value })} placeholder="Bijvoorbeeld: Kast 1" />
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 10, color: '#0f172a', fontWeight: 600 }}>
            <input type="checkbox" style={greenCheckboxStyle} checked={Boolean(form.active)} onChange={(event) => onChange({ ...form, active: event.target.checked })} />
            Actief
          </label>
        </div>
        <div className="rz-modal-actions">
          <Button type="button" variant="secondary" onClick={onClose} disabled={busy}>Annuleren</Button>
          <Button type="button" onClick={onSubmit} disabled={busy}>{busy ? 'Opslaan…' : 'Opslaan'}</Button>
        </div>
      </div>
    </div>
  )
}

function ActionModal({ open, title, noun, selectedCount, onClose, onDelete, onArchive, busy }) {
  if (!open) return null
  return (
    <div className="rz-modal-backdrop" role="presentation">
      <div className="rz-modal-card" role="dialog" aria-modal="true" aria-labelledby="action-modal-title">
        <h3 id="action-modal-title" className="rz-modal-title">{title}</h3>
        <p className="rz-modal-text">Je hebt {selectedCount} {noun}{selectedCount === 1 ? '' : 's'} geselecteerd. Kies wat je wilt doen.</p>
        <div className="rz-modal-actions">
          <Button type="button" variant="secondary" onClick={onClose} disabled={busy}>Annuleren</Button>
          <Button type="button" variant="secondary" onClick={onArchive} disabled={busy}>{busy ? 'Bezig…' : 'Archiveren'}</Button>
          <Button type="button" onClick={onDelete} disabled={busy}>{busy ? 'Bezig…' : 'Verwijderen'}</Button>
        </div>
      </div>
    </div>
  )
}

function PendingChangesModal({ open, onSave, onDiscard, onCancel, busy }) {
  if (!open) return null
  return (
    <div className="rz-modal-backdrop" role="presentation">
      <div className="rz-modal-card" role="dialog" aria-modal="true" aria-labelledby="pending-modal-title">
        <h3 id="pending-modal-title" className="rz-modal-title">Wijzigingen bewaren?</h3>
        <p className="rz-modal-text">Er zijn nog niet-opgeslagen wijzigingen in Locaties en/of Sublocaties. Kies of je deze wilt opslaan of annuleren.</p>
        <div className="rz-modal-actions">
          <Button type="button" variant="secondary" onClick={onCancel} disabled={busy}>Terug naar scherm</Button>
          <Button type="button" variant="secondary" onClick={onDiscard} disabled={busy}>Wijzigingen annuleren</Button>
          <Button type="button" onClick={onSave} disabled={busy}>{busy ? 'Opslaan…' : 'Wijzigingen opslaan'}</Button>
        </div>
      </div>
    </div>
  )
}

function csvEscape(value) {
  const text = String(value ?? '')
  if (!text.includes(",") && !text.includes("\"") && !text.includes("\n")) return text
  return `"${text.replace(/"/g, '""')}"`
}

function draftMapFromItems(items) {
  return Object.fromEntries(items.map((item) => [String(item.id), { naam: String(item.naam || ''), active: Boolean(item.active), space_id: item.space_id != null ? String(item.space_id) : '' }]))
}

export default function SettingsLocationsPage() {
  const isAdmin = isHouseholdAdminFromContext(readStoredAuthContext())
  const [locations, setLocations] = useState([])
  const [sublocations, setSublocations] = useState([])
  const [locationDrafts, setLocationDrafts] = useState({})
  const [sublocationDrafts, setSublocationDrafts] = useState({})
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [locationModalOpen, setLocationModalOpen] = useState(false)
  const [locationForm, setLocationForm] = useState(initialLocationForm)
  const [sublocationModalMode, setSublocationModalMode] = useState('')
  const [sublocationForm, setSublocationForm] = useState(initialSublocationForm)
  const [locationFilters, setLocationFilters] = useState(initialLocationFilters)
  const [sublocationFilters, setSublocationFilters] = useState(initialSublocationFilters)
  const [selectedLocationIds, setSelectedLocationIds] = useState([])
  const [selectedSublocationIds, setSelectedSublocationIds] = useState([])
  const [selectedLocationId, setSelectedLocationId] = useState('')
  const [showLocationActionModal, setShowLocationActionModal] = useState(false)
  const [showSublocationActionModal, setShowSublocationActionModal] = useState(false)
  const [showPendingModal, setShowPendingModal] = useState(false)
  const pendingNavigationRef = useRef(null)

  async function loadData() {
    setIsLoading(true)
    setError('')
    try {
      const [spacesResponse, sublocationsResponse] = await Promise.all([
        fetchJsonWithAuth('/api/spaces'),
        fetchJsonWithAuth('/api/sublocations'),
      ])
      const spacesData = await spacesResponse.json().catch(() => ({}))
      const sublocationsData = await sublocationsResponse.json().catch(() => ({}))
      if (!spacesResponse.ok) throw new Error(spacesData?.detail || 'Locaties konden niet worden geladen.')
      if (!sublocationsResponse.ok) throw new Error(sublocationsData?.detail || 'Sublocaties konden niet worden geladen.')
      const nextLocations = Array.isArray(spacesData?.items) ? spacesData.items : []
      const nextSublocations = Array.isArray(sublocationsData?.items) ? sublocationsData.items : []
      setLocations(nextLocations)
      setSublocations(nextSublocations)
      setLocationDrafts(draftMapFromItems(nextLocations))
      setSublocationDrafts(draftMapFromItems(nextSublocations))
      setSelectedLocationId((current) => {
        if (current && nextLocations.some((item) => String(item.id) === String(current))) return current
        const first = [...nextLocations].sort((a, b) => String(a?.naam || '').localeCompare(String(b?.naam || ''), 'nl'))[0]
        return first ? String(first.id) : ''
      })
    } catch (loadError) {
      setError(loadError?.message || 'Locaties konden niet worden geladen.')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    if (isAdmin) loadData()
  }, [isAdmin])

  const sortedLocations = useMemo(() => [...locations].sort((a, b) => String(a?.naam || '').localeCompare(String(b?.naam || ''), 'nl')), [locations])
  const selectedLocation = useMemo(() => sortedLocations.find((item) => String(item.id) === String(selectedLocationId)) || null, [sortedLocations, selectedLocationId])

  const locationDirtyCount = useMemo(() => {
    return locations.reduce((count, item) => {
      const draft = locationDrafts[String(item.id)]
      if (!draft) return count
      if (String(draft.naam || '').trim() !== String(item.naam || '').trim()) return count + 1
      if (Boolean(draft.active) !== Boolean(item.active)) return count + 1
      return count
    }, 0)
  }, [locations, locationDrafts])

  const sublocationDirtyCount = useMemo(() => {
    return sublocations.reduce((count, item) => {
      const draft = sublocationDrafts[String(item.id)]
      if (!draft) return count
      if (String(draft.naam || '').trim() !== String(item.naam || '').trim()) return count + 1
      if (Boolean(draft.active) !== Boolean(item.active)) return count + 1
      return count
    }, 0)
  }, [sublocations, sublocationDrafts])

  const hasPendingChanges = locationDirtyCount > 0 || sublocationDirtyCount > 0

  useEffect(() => {
    const handleBeforeUnload = (event) => {
      if (!hasPendingChanges) return undefined
      event.preventDefault()
      event.returnValue = ''
      return ''
    }
    window.addEventListener('beforeunload', handleBeforeUnload)
    return () => window.removeEventListener('beforeunload', handleBeforeUnload)
  }, [hasPendingChanges])

  useEffect(() => {
    const handleDocumentClick = (event) => {
      if (!hasPendingChanges) return
      const anchor = event.target instanceof Element ? event.target.closest('a[href]') : null
      if (!anchor) return
      const href = anchor.getAttribute('href')
      if (!href || href.startsWith('#') || href.startsWith('javascript:')) return
      if (anchor.target === '_blank' || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
      const next = new URL(anchor.href, window.location.origin)
      const current = new URL(window.location.href)
      if (next.pathname === current.pathname && next.search === current.search && next.hash === current.hash) return
      event.preventDefault()
      pendingNavigationRef.current = () => { window.location.assign(next.toString()) }
      setShowPendingModal(true)
    }
    document.addEventListener('click', handleDocumentClick, true)
    return () => document.removeEventListener('click', handleDocumentClick, true)
  }, [hasPendingChanges])

  const filteredLocations = useMemo(() => {
    return sortedLocations.filter((item) => {
      const draft = locationDrafts[String(item.id)] || { naam: item.naam, active: item.active }
      const naamOk = !locationFilters.naam || String(draft?.naam || '').toLowerCase().includes(locationFilters.naam.toLowerCase())
      const actief = Boolean(draft?.active)
      const actiefFilterAan = Boolean(locationFilters.actiefJa) !== Boolean(locationFilters.actiefNee)
      const actiefOk = !actiefFilterAan || (locationFilters.actiefJa ? actief : !actief)
      const sublocatiesOk = !locationFilters.sublocaties || String(Number(item?.sublocation_count || 0)).includes(locationFilters.sublocaties)
      return naamOk && actiefOk && sublocatiesOk
    })
  }, [sortedLocations, locationFilters, locationDrafts])

  const visibleSublocations = useMemo(() => sublocations.filter((item) => String(item?.space_id || '') === String(selectedLocationId || '')), [sublocations, selectedLocationId])

  const filteredSublocations = useMemo(() => {
    return [...visibleSublocations]
      .sort((a, b) => String(a?.naam || '').localeCompare(String(b?.naam || ''), 'nl'))
      .filter((item) => {
        const draft = sublocationDrafts[String(item.id)] || { naam: item.naam, active: item.active }
        const naamOk = !sublocationFilters.naam || String(draft?.naam || '').toLowerCase().includes(sublocationFilters.naam.toLowerCase())
        const actief = Boolean(draft?.active)
        const actiefFilterAan = Boolean(sublocationFilters.actiefJa) !== Boolean(sublocationFilters.actiefNee)
        const actiefOk = !actiefFilterAan || (sublocationFilters.actiefJa ? actief : !actief)
        return naamOk && actiefOk
      })
  }, [visibleSublocations, sublocationFilters, sublocationDrafts])

  const allFilteredLocationsSelected = filteredLocations.length > 0 && filteredLocations.every((item) => selectedLocationIds.includes(String(item.id)))
  const allFilteredSublocationsSelected = filteredSublocations.length > 0 && filteredSublocations.every((item) => selectedSublocationIds.includes(String(item.id)))

  function toggleSelectedLocation(id) {
    const key = String(id)
    setSelectedLocationIds((current) => current.includes(key) ? current.filter((value) => value !== key) : [...current, key])
  }

  function toggleSelectedSublocation(id) {
    const key = String(id)
    setSelectedSublocationIds((current) => current.includes(key) ? current.filter((value) => value !== key) : [...current, key])
  }

  function toggleAllFilteredLocations() {
    if (allFilteredLocationsSelected) {
      const filteredSet = new Set(filteredLocations.map((item) => String(item.id)))
      setSelectedLocationIds((current) => current.filter((id) => !filteredSet.has(id)))
      return
    }
    const merged = new Set(selectedLocationIds)
    filteredLocations.forEach((item) => merged.add(String(item.id)))
    setSelectedLocationIds(Array.from(merged))
  }

  function toggleAllFilteredSublocations() {
    if (allFilteredSublocationsSelected) {
      const filteredSet = new Set(filteredSublocations.map((item) => String(item.id)))
      setSelectedSublocationIds((current) => current.filter((id) => !filteredSet.has(id)))
      return
    }
    const merged = new Set(selectedSublocationIds)
    filteredSublocations.forEach((item) => merged.add(String(item.id)))
    setSelectedSublocationIds(Array.from(merged))
  }

  function openCreateLocation() {
    setMessage('')
    setError('')
    setLocationForm(initialLocationForm)
    setLocationModalOpen(true)
  }

  function openCreateSublocation() {
    setMessage('')
    setError('')
    setSublocationForm({ ...initialSublocationForm, space_id: String(selectedLocationId || '') })
    setSublocationModalMode('create')
  }

  function updateLocationDraft(id, patch) {
    const key = String(id)
    setLocationDrafts((current) => ({ ...current, [key]: { ...(current[key] || {}), ...patch } }))
  }

  function updateSublocationDraft(id, patch) {
    const key = String(id)
    setSublocationDrafts((current) => ({ ...current, [key]: { ...(current[key] || {}), ...patch } }))
  }

  function discardPendingChanges() {
    setLocationDrafts(draftMapFromItems(locations))
    setSublocationDrafts(draftMapFromItems(sublocations))
    setMessage('Wijzigingen geannuleerd.')
    setError('')
  }

  async function savePendingChanges() {
    const changedLocations = locations.filter((item) => {
      const draft = locationDrafts[String(item.id)]
      return draft && (String(draft.naam || '').trim() !== String(item.naam || '').trim() || Boolean(draft.active) !== Boolean(item.active))
    })
    const changedSublocations = sublocations.filter((item) => {
      const draft = sublocationDrafts[String(item.id)]
      return draft && (String(draft.naam || '').trim() !== String(item.naam || '').trim() || Boolean(draft.active) !== Boolean(item.active))
    })

    for (const item of changedLocations) {
      const draft = locationDrafts[String(item.id)]
      if (!String(draft?.naam || '').trim()) {
        setError('Elke locatie moet een naam hebben voordat je opslaat.')
        return false
      }
    }
    for (const item of changedSublocations) {
      const draft = sublocationDrafts[String(item.id)]
      if (!String(draft?.naam || '').trim()) {
        setError('Elke sublocatie moet een naam hebben voordat je opslaat.')
        return false
      }
    }

    if (!changedLocations.length && !changedSublocations.length) {
      setShowPendingModal(false)
      return true
    }

    setIsSaving(true)
    setError('')
    setMessage('')
    try {
      for (const item of changedLocations) {
        const draft = locationDrafts[String(item.id)]
        const response = await fetchJsonWithAuth(`/api/spaces/${encodeURIComponent(item.id)}`, {
          method: 'PUT',
          body: JSON.stringify({ naam: String(draft.naam || '').trim(), active: Boolean(draft.active) }),
        })
        const data = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(data?.detail || `Locatie ${item.naam} opslaan mislukt.`)
      }
      for (const item of changedSublocations) {
        const draft = sublocationDrafts[String(item.id)]
        const response = await fetchJsonWithAuth(`/api/sublocations/${encodeURIComponent(item.id)}`, {
          method: 'PUT',
          body: JSON.stringify({ naam: String(draft.naam || '').trim(), space_id: String(item.space_id || ''), active: Boolean(draft.active) }),
        })
        const data = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(data?.detail || `Sublocatie ${item.naam} opslaan mislukt.`)
      }
      await loadData()
      setMessage(`${changedLocations.length + changedSublocations.length} wijziging${changedLocations.length + changedSublocations.length === 1 ? '' : 'en'} opgeslagen.`)
      setShowPendingModal(false)
      return true
    } catch (saveError) {
      setError(saveError?.message || 'Wijzigingen opslaan mislukt.')
      return false
    } finally {
      setIsSaving(false)
    }
  }

  async function handleSaveLocation() {
    const naam = String(locationForm.naam || '').trim()
    if (!naam) {
      setError('Locatienaam is verplicht.')
      return
    }
    setIsSaving(true)
    setError('')
    setMessage('')
    try {
      const response = await fetchJsonWithAuth('/api/spaces', { method: 'POST', body: JSON.stringify({ naam, active: Boolean(locationForm.active) }) })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data?.detail || 'Locatie opslaan mislukt.')
      setMessage(data?.message || 'Locatie opgeslagen.')
      setLocationModalOpen(false)
      await loadData()
    } catch (saveError) {
      setError(saveError?.message || 'Locatie opslaan mislukt.')
    } finally {
      setIsSaving(false)
    }
  }

  async function handleSaveSublocation() {
    const naam = String(sublocationForm.naam || '').trim()
    const space_id = String(sublocationForm.space_id || '').trim()
    if (!space_id) {
      setError('Locatie is verplicht.')
      return
    }
    if (!naam) {
      setError('Sublocatienaam is verplicht.')
      return
    }
    setIsSaving(true)
    setError('')
    setMessage('')
    try {
      const response = await fetchJsonWithAuth('/api/sublocations', { method: 'POST', body: JSON.stringify({ naam, space_id, active: Boolean(sublocationForm.active) }) })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data?.detail || 'Sublocatie opslaan mislukt.')
      setMessage(data?.message || 'Sublocatie opgeslagen.')
      setSublocationModalMode('')
      await loadData()
    } catch (saveError) {
      setError(saveError?.message || 'Sublocatie opslaan mislukt.')
    } finally {
      setIsSaving(false)
    }
  }

  async function deleteSelectedLocations() {
    const selectedItems = locations.filter((item) => selectedLocationIds.includes(String(item.id)))
    if (!selectedItems.length) return
    setIsSaving(true)
    setError('')
    setMessage('')
    const blocked = []
    let deletedCount = 0
    try {
      for (const item of selectedItems) {
        const lockedDelete = Number(item?.inventory_count || 0) > 0 || Number(item?.sublocation_count || 0) > 0
        if (lockedDelete) {
          blocked.push(item.naam)
          continue
        }
        const response = await fetchJsonWithAuth(`/api/spaces/${encodeURIComponent(item.id)}`, { method: 'DELETE' })
        if (response.ok) deletedCount += 1
        else blocked.push(item.naam)
      }
      await loadData()
      setSelectedLocationIds([])
      if (blocked.length && deletedCount) setMessage(`${deletedCount} locatie${deletedCount === 1 ? '' : 's'} verwijderd. ${blocked.length} locatie${blocked.length === 1 ? ' kon' : 's konden'} niet worden verwijderd.`)
      else if (deletedCount) setMessage(`${deletedCount} locatie${deletedCount === 1 ? '' : 's'} verwijderd.`)
      else setError(blocked.length ? 'De geselecteerde locaties konden niet worden verwijderd omdat er nog artikelen aan gekoppeld zijn.' : 'Geen locaties verwijderd.')
    } finally {
      setIsSaving(false)
      setShowLocationActionModal(false)
    }
  }

  async function archiveSelectedLocations() {
    const selectedItems = locations.filter((item) => selectedLocationIds.includes(String(item.id)))
    if (!selectedItems.length) return
    setIsSaving(true)
    setError('')
    setMessage('')
    let archivedCount = 0
    try {
      for (const item of selectedItems) {
        const draft = locationDrafts[String(item.id)] || item
        const response = await fetchJsonWithAuth(`/api/spaces/${encodeURIComponent(item.id)}`, { method: 'PUT', body: JSON.stringify({ naam: String(draft.naam || item.naam || '').trim(), active: false }) })
        if (response.ok) archivedCount += 1
      }
      await loadData()
      setSelectedLocationIds([])
      setMessage(`${archivedCount} locatie${archivedCount === 1 ? '' : 's'} gearchiveerd.`)
    } catch (archiveError) {
      setError(archiveError?.message || 'Locaties archiveren mislukt.')
    } finally {
      setIsSaving(false)
      setShowLocationActionModal(false)
    }
  }

  async function deleteSelectedSublocations() {
    const selectedItems = sublocations.filter((item) => selectedSublocationIds.includes(String(item.id)))
    if (!selectedItems.length) return
    setIsSaving(true)
    setError('')
    setMessage('')
    const blocked = []
    let deletedCount = 0
    try {
      for (const item of selectedItems) {
        const lockedDelete = Number(item?.inventory_count || 0) > 0
        if (lockedDelete) {
          blocked.push(item.naam)
          continue
        }
        const response = await fetchJsonWithAuth(`/api/sublocations/${encodeURIComponent(item.id)}`, { method: 'DELETE' })
        if (response.ok) deletedCount += 1
        else blocked.push(item.naam)
      }
      await loadData()
      setSelectedSublocationIds([])
      if (blocked.length && deletedCount) setMessage(`${deletedCount} sublocatie${deletedCount === 1 ? '' : 's'} verwijderd. ${blocked.length} sublocatie${blocked.length === 1 ? ' kon' : 's konden'} niet worden verwijderd.`)
      else if (deletedCount) setMessage(`${deletedCount} sublocatie${deletedCount === 1 ? '' : 's'} verwijderd.`)
      else setError(blocked.length ? 'De geselecteerde sublocaties konden niet worden verwijderd omdat er nog artikelen aan gekoppeld zijn.' : 'Geen sublocaties verwijderd.')
    } finally {
      setIsSaving(false)
      setShowSublocationActionModal(false)
    }
  }

  async function archiveSelectedSublocations() {
    const selectedItems = sublocations.filter((item) => selectedSublocationIds.includes(String(item.id)))
    if (!selectedItems.length) return
    setIsSaving(true)
    setError('')
    setMessage('')
    let archivedCount = 0
    try {
      for (const item of selectedItems) {
        const draft = sublocationDrafts[String(item.id)] || item
        const response = await fetchJsonWithAuth(`/api/sublocations/${encodeURIComponent(item.id)}`, { method: 'PUT', body: JSON.stringify({ naam: String(draft.naam || item.naam || '').trim(), space_id: String(item.space_id || ''), active: false }) })
        if (response.ok) archivedCount += 1
      }
      await loadData()
      setSelectedSublocationIds([])
      setMessage(`${archivedCount} sublocatie${archivedCount === 1 ? '' : 's'} gearchiveerd.`)
    } catch (archiveError) {
      setError(archiveError?.message || 'Sublocaties archiveren mislukt.')
    } finally {
      setIsSaving(false)
      setShowSublocationActionModal(false)
    }
  }

  function exportLocationsCsv() {
    const rows = locations.filter((item) => selectedLocationIds.includes(String(item.id))).map((item) => {
      const draft = locationDrafts[String(item.id)] || item
      return [draft.naam, Boolean(draft.active) ? 'Ja' : 'Nee', Number(item.sublocation_count || 0), Number(item.inventory_count || 0)]
    })
    const csv = [['Locatie naam', 'Actief', 'Aantal sublocaties', 'Aantal voorraadregels'].join(','), ...rows.map((row) => row.map(csvEscape).join(','))].join('\n')
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'rezzerv-locaties.csv'
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  }

  function exportSublocationsCsv() {
    const rows = sublocations.filter((item) => selectedSublocationIds.includes(String(item.id))).map((item) => {
      const draft = sublocationDrafts[String(item.id)] || item
      return [draft.naam, item.space_name, Boolean(draft.active) ? 'Ja' : 'Nee']
    })
    const csv = [['Sublocatie naam', 'Locatie', 'Actief'].join(','), ...rows.map((row) => row.map(csvEscape).join(','))].join('\n')
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'rezzerv-sublocaties.csv'
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  }

  function handleAttemptLeave() {
    if (!hasPendingChanges) return false
    setShowPendingModal(true)
    return true
  }

  async function confirmSaveAndContinue() {
    const ok = await savePendingChanges()
    if (ok && pendingNavigationRef.current) {
      const navigate = pendingNavigationRef.current
      pendingNavigationRef.current = null
      navigate()
    }
  }

  function confirmDiscardAndContinue() {
    discardPendingChanges()
    setShowPendingModal(false)
    if (pendingNavigationRef.current) {
      const navigate = pendingNavigationRef.current
      pendingNavigationRef.current = null
      navigate()
    }
  }

  function cancelPendingDialog() {
    pendingNavigationRef.current = null
    setShowPendingModal(false)
  }

  if (!isAdmin) return <Navigate to="/instellingen" replace />

  return (
    <AppShell title="Locaties" showExit={false}>
      <Card className="rz-settings-spaces-card">
        <div style={{ display: 'grid', gap: 24, width: '100%' }} data-testid="settings-locations-page">
          <div>
            <h2 style={{ margin: 0, fontSize: 20 }}>Beheer Locaties</h2>
          </div>

          <Feedback type="error">{error}</Feedback>
          <Feedback type="success">{message}</Feedback>

          <section style={{ display: 'grid', gap: 18 }}>
            <div style={{ fontWeight: 700, color: '#0f172a' }}>Locaties</div>
            <Table wrapperClassName="rz-stock-table-wrapper" tableClassName="rz-stock-table" tableStyle={{ tableLayout: 'fixed', width: buildTableWidth(locationColumnWidths), minWidth: buildTableWidth(locationColumnWidths) }}>
                <colgroup>
                  <col style={{ width: '48px' }} />
                  <col style={{ width: 'auto' }} />
                  <col style={{ width: '140px' }} />
                  <col style={{ width: '180px' }} />
                </colgroup>
                <thead>
                  <tr className="rz-table-header">
                    <th><input type="checkbox" style={greenCheckboxStyle} checked={allFilteredLocationsSelected} onChange={toggleAllFilteredLocations} aria-label="Selecteer alle zichtbare locaties" /></th>
                    <th>Locatie</th>
                    <th className="rz-num">Actief</th>
                    <th className="rz-num">Aantal sublocaties</th>
                  </tr>
                  <tr className="rz-table-filters">
                    <th />
                    <th><input className="rz-input rz-inline-input" value={locationFilters.naam} onChange={(event) => setLocationFilters((current) => ({ ...current, naam: event.target.value }))} placeholder="Filter" aria-label="Filter op locatie" /></th>
                    <th className="rz-num">
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10, justifyContent: 'center', minHeight: 20, width: '100%' }}>
                        <label style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 12 }}><input type="checkbox" style={greenCheckboxStyle} checked={locationFilters.actiefJa} onChange={(event) => setLocationFilters((current) => ({ ...current, actiefJa: event.target.checked }))} />Ja</label>
                        <label style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 12 }}><input type="checkbox" style={greenCheckboxStyle} checked={locationFilters.actiefNee} onChange={(event) => setLocationFilters((current) => ({ ...current, actiefNee: event.target.checked }))} />Nee</label>
                      </div>
                    </th>
                    <th><input className="rz-input rz-inline-input" value={locationFilters.sublocaties} onChange={(event) => setLocationFilters((current) => ({ ...current, sublocaties: event.target.value }))} placeholder="Filter" aria-label="Filter op aantal sublocaties" /></th>
                  </tr>
                </thead>
                <tbody>
                  {isLoading ? (
                    <tr><td colSpan={4}>Locaties laden…</td></tr>
                  ) : filteredLocations.length === 0 ? (
                    <tr><td colSpan={4}>Nog geen locaties beschikbaar.</td></tr>
                  ) : filteredLocations.map((item) => {
                    const selected = selectedLocationIds.includes(String(item.id))
                    const detailSelected = String(selectedLocationId) === String(item.id)
                    const draft = locationDrafts[String(item.id)] || { naam: item.naam, active: item.active }
                    return (
                      <tr key={item.id} className={selected || detailSelected ? 'rz-row-selected' : ''} onDoubleClick={() => setSelectedLocationId(String(item.id))} title="Dubbelklik om sublocaties van deze locatie te tonen">
                        <td><input type="checkbox" style={greenCheckboxStyle} checked={selected} onChange={() => toggleSelectedLocation(item.id)} aria-label={`Selecteer ${item.naam}`} /></td>
                        <td>
                          <input className="rz-input rz-inline-input" value={draft.naam} onChange={(event) => updateLocationDraft(item.id, { naam: event.target.value })} aria-label={`Locatienaam ${item.naam}`} />
                        </td>
                        <td className="rz-num"><input type="checkbox" style={greenCheckboxStyle} checked={Boolean(draft.active)} onChange={(event) => updateLocationDraft(item.id, { active: event.target.checked })} aria-label={`Actief ${item.naam}`} /></td>
                        <td className="rz-num">{Number(item.sublocation_count || 0)}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </Table>
            <div className="rz-stock-table-actions" style={{ justifyContent: 'flex-end', gap: 12, flexWrap: 'wrap' }}>
              <Button type="button" variant="secondary" onClick={exportLocationsCsv} disabled={isLoading || selectedLocationIds.length === 0 || isSaving}>Exporteren</Button>
              <Button type="button" variant="secondary" onClick={() => setShowLocationActionModal(true)} disabled={isSaving || selectedLocationIds.length === 0}>Verwijderen</Button>
              <Button type="button" onClick={openCreateLocation} disabled={isSaving}>Toevoegen locatie</Button>
            </div>
          </section>

          <section style={{ display: 'grid', gap: 18 }}>
            <div style={{ fontWeight: 700, color: '#0f172a' }}>Sublocaties{selectedLocation ? ` van ${selectedLocation.naam}` : ''}</div>
            <Table wrapperClassName="rz-stock-table-wrapper" tableClassName="rz-stock-table" tableStyle={{ tableLayout: 'fixed', width: buildTableWidth(sublocationColumnWidths), minWidth: buildTableWidth(sublocationColumnWidths) }}>
                <colgroup>
                  <col style={{ width: '48px' }} />
                  <col style={{ width: 'auto' }} />
                  <col style={{ width: '140px' }} />
                </colgroup>
                <thead>
                  <tr className="rz-table-header">
                    <th><input type="checkbox" style={greenCheckboxStyle} checked={allFilteredSublocationsSelected} onChange={toggleAllFilteredSublocations} aria-label="Selecteer alle zichtbare sublocaties" /></th>
                    <th>Sublocatie</th>
                    <th className="rz-num">Actief</th>
                  </tr>
                  <tr className="rz-table-filters">
                    <th />
                    <th><input className="rz-input rz-inline-input" value={sublocationFilters.naam} onChange={(event) => setSublocationFilters((current) => ({ ...current, naam: event.target.value }))} placeholder="Filter" aria-label="Filter op sublocatie" /></th>
                    <th className="rz-num">
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10, justifyContent: 'center', minHeight: 20, width: '100%' }}>
                        <label style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 12 }}><input type="checkbox" style={greenCheckboxStyle} checked={sublocationFilters.actiefJa} onChange={(event) => setSublocationFilters((current) => ({ ...current, actiefJa: event.target.checked }))} />Ja</label>
                        <label style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 12 }}><input type="checkbox" style={greenCheckboxStyle} checked={sublocationFilters.actiefNee} onChange={(event) => setSublocationFilters((current) => ({ ...current, actiefNee: event.target.checked }))} />Nee</label>
                      </div>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {isLoading ? (
                    <tr><td colSpan={3}>Sublocaties laden…</td></tr>
                  ) : !selectedLocationId ? (
                    <tr><td colSpan={3}>Nog geen locatie beschikbaar.</td></tr>
                  ) : filteredSublocations.length === 0 ? (
                    <tr><td colSpan={3}>Nog geen sublocaties beschikbaar voor deze locatie.</td></tr>
                  ) : filteredSublocations.map((item) => {
                    const selected = selectedSublocationIds.includes(String(item.id))
                    const draft = sublocationDrafts[String(item.id)] || { naam: item.naam, active: item.active }
                    return (
                      <tr key={item.id} className={selected ? 'rz-row-selected' : ''}>
                        <td><input type="checkbox" style={greenCheckboxStyle} checked={selected} onChange={() => toggleSelectedSublocation(item.id)} aria-label={`Selecteer ${item.naam}`} /></td>
                        <td><input className="rz-input rz-inline-input" value={draft.naam} onChange={(event) => updateSublocationDraft(item.id, { naam: event.target.value })} aria-label={`Sublocatienaam ${item.naam}`} /></td>
                        <td className="rz-num"><input type="checkbox" style={greenCheckboxStyle} checked={Boolean(draft.active)} onChange={(event) => updateSublocationDraft(item.id, { active: event.target.checked })} aria-label={`Actief ${item.naam}`} /></td>
                      </tr>
                    )
                  })}
                </tbody>
              </Table>
            <div className="rz-stock-table-actions" style={{ justifyContent: 'flex-end', gap: 12, flexWrap: 'wrap' }}>
              <Button type="button" variant="secondary" onClick={exportSublocationsCsv} disabled={isLoading || selectedSublocationIds.length === 0 || isSaving}>Exporteren</Button>
              <Button type="button" variant="secondary" onClick={() => setShowSublocationActionModal(true)} disabled={isSaving || selectedSublocationIds.length === 0}>Verwijderen</Button>
              <Button type="button" onClick={openCreateSublocation} disabled={isSaving || !selectedLocationId}>Toevoegen sublocatie</Button>
            </div>
          </section>

          <div className="rz-stock-table-actions" style={{ justifyContent: 'flex-end', gap: 12, flexWrap: 'wrap' }}>
            <Button type="button" variant="secondary" onClick={() => { discardPendingChanges(); setShowPendingModal(false) }} disabled={isSaving || !hasPendingChanges}>Wijzigingen annuleren</Button>
            <Button type="button" onClick={savePendingChanges} disabled={isSaving || !hasPendingChanges}>{isSaving ? 'Opslaan…' : 'Wijzigingen opslaan'}</Button>
          </div>
        </div>
      </Card>

      <LocationModal open={locationModalOpen} form={locationForm} onChange={setLocationForm} onClose={() => setLocationModalOpen(false)} onSubmit={handleSaveLocation} busy={isSaving} />
      <SublocationModal mode={sublocationModalMode} form={sublocationForm} onChange={setSublocationForm} onClose={() => setSublocationModalMode('')} onSubmit={handleSaveSublocation} busy={isSaving} locationOptions={sortedLocations} />
      <ActionModal open={showLocationActionModal} title="Geselecteerde locaties verwerken" noun="locatie" selectedCount={selectedLocationIds.length} onClose={() => setShowLocationActionModal(false)} onDelete={deleteSelectedLocations} onArchive={archiveSelectedLocations} busy={isSaving} />
      <ActionModal open={showSublocationActionModal} title="Geselecteerde sublocaties verwerken" noun="sublocatie" selectedCount={selectedSublocationIds.length} onClose={() => setShowSublocationActionModal(false)} onDelete={deleteSelectedSublocations} onArchive={archiveSelectedSublocations} busy={isSaving} />
      <PendingChangesModal open={showPendingModal} onSave={confirmSaveAndContinue} onDiscard={confirmDiscardAndContinue} onCancel={cancelPendingDialog} busy={isSaving} />
    </AppShell>
  )
}
