import { useEffect, useMemo, useState } from 'react'
import { Navigate } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import Card from '../../ui/Card'
import Button from '../../ui/Button'
import { buildTableWidth } from '../../ui/resizableTable'
import Table from '../../ui/Table'
import { fetchJsonWithAuth, isHouseholdAdminFromContext, readStoredAuthContext } from '../../lib/authSession'

const initialForm = { naam: '', space_id: '', active: true }
const initialFilters = { naam: '', ruimte: '', actiefJa: false, actiefNee: false }
const columnWidths = { select: 48, sublocatie: 320, ruimte: 260, actief: 140 }

function Feedback({ type = 'info', children }) {
  if (!children) return null
  const isError = type === 'error'
  const background = isError ? '#fef2f2' : '#ecfdf3'
  const border = isError ? '#fecaca' : '#bbf7d0'
  const color = isError ? '#991b1b' : '#166534'
  return <div style={{ padding: '12px 14px', borderRadius: 12, border: `1px solid ${border}`, background, color }}>{children}</div>
}

function SublocationModal({ mode, form, onChange, onClose, onSubmit, busy, spaces }) {
  if (!mode) return null
  const title = mode === 'create' ? 'Nieuwe sublocatie' : 'Sublocatie bewerken'
  return (
    <div className="rz-modal-backdrop" role="presentation">
      <div className="rz-modal-card" role="dialog" aria-modal="true" aria-labelledby="sublocations-modal-title">
        <h3 id="sublocations-modal-title" className="rz-modal-title">{title}</h3>
        <div style={{ display: 'grid', gap: 16 }}>
          <label className="rz-input-field">
            <div className="rz-label">Ruimte</div>
            <select className="rz-input" value={form.space_id} onChange={(event) => onChange({ ...form, space_id: event.target.value })}>
              <option value="">Kies een ruimte</option>
              {spaces.map((space) => <option key={space.id} value={space.id}>{space.naam}</option>)}
            </select>
          </label>
          <label className="rz-input-field">
            <div className="rz-label">Sublocatie naam</div>
            <input className="rz-input" autoFocus value={form.naam} onChange={(event) => onChange({ ...form, naam: event.target.value })} placeholder="Bijvoorbeeld: Kast 1" />
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 10, color: '#0f172a', fontWeight: 600 }}>
            <input type="checkbox" style={{ accentColor: '#1A3E2B', width: 16, height: 16 }} checked={Boolean(form.active)} onChange={(event) => onChange({ ...form, active: event.target.checked })} />
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

function DeleteActionModal({ open, selectedCount, onClose, onDelete, onArchive, busy }) {
  if (!open) return null
  return (
    <div className="rz-modal-backdrop" role="presentation">
      <div className="rz-modal-card" role="dialog" aria-modal="true" aria-labelledby="sublocations-delete-title">
        <h3 id="sublocations-delete-title" className="rz-modal-title">Geselecteerde sublocaties verwerken</h3>
        <p className="rz-modal-text">Je hebt {selectedCount} sublocatie{selectedCount === 1 ? '' : 's'} geselecteerd. Kies wat je wilt doen.</p>
        <div className="rz-modal-actions">
          <Button type="button" variant="secondary" onClick={onClose} disabled={busy}>Annuleren</Button>
          <Button type="button" variant="secondary" onClick={onArchive} disabled={busy}>{busy ? 'Bezig…' : 'Archiveren'}</Button>
          <Button type="button" onClick={onDelete} disabled={busy}>{busy ? 'Bezig…' : 'Verwijderen'}</Button>
        </div>
      </div>
    </div>
  )
}

function csvEscape(value) {
  const text = String(value ?? '')
  if (!text.includes(',') && !text.includes('"') && !text.includes('\n')) return text
  return `"${text.replace(/"/g, '""')}"`
}

export default function SettingsSublocationsPage() {
  const isAdmin = isHouseholdAdminFromContext(readStoredAuthContext())
  const [items, setItems] = useState([])
  const [spaces, setSpaces] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [modalMode, setModalMode] = useState('')
  const [editingId, setEditingId] = useState('')
  const [form, setForm] = useState(initialForm)
  const [filters, setFilters] = useState(initialFilters)
  const [selectedIds, setSelectedIds] = useState([])
  const [showActionModal, setShowActionModal] = useState(false)

  async function loadData() {
    setIsLoading(true)
    setError('')
    try {
      const [sublocationsResponse, spacesResponse] = await Promise.all([
        fetchJsonWithAuth('/api/sublocations'),
        fetchJsonWithAuth('/api/spaces'),
      ])
      const sublocationsData = await sublocationsResponse.json().catch(() => ({}))
      const spacesData = await spacesResponse.json().catch(() => ({}))
      if (!sublocationsResponse.ok) throw new Error(sublocationsData?.detail || 'Sublocaties konden niet worden geladen.')
      if (!spacesResponse.ok) throw new Error(spacesData?.detail || 'Ruimtes konden niet worden geladen.')
      setItems(Array.isArray(sublocationsData?.items) ? sublocationsData.items : [])
      setSpaces(Array.isArray(spacesData?.items) ? spacesData.items.filter((item) => item?.active) : [])
    } catch (loadError) {
      setError(loadError?.message || 'Sublocaties konden niet worden geladen.')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    if (isAdmin) loadData()
  }, [isAdmin])

  const sortedItems = useMemo(() => [...items].sort((a, b) => `${a?.space_name || ''} ${a?.naam || ''}`.localeCompare(`${b?.space_name || ''} ${b?.naam || ''}`, 'nl')), [items])
  const filteredItems = useMemo(() => sortedItems.filter((item) => {
    const naamOk = !filters.naam || String(item?.naam || '').toLowerCase().includes(filters.naam.toLowerCase())
    const ruimteOk = !filters.ruimte || String(item?.space_name || '').toLowerCase().includes(filters.ruimte.toLowerCase())
    const actief = Boolean(item?.active)
    const actiefFilterAan = Boolean(filters.actiefJa) !== Boolean(filters.actiefNee)
    const actiefOk = !actiefFilterAan || (filters.actiefJa ? actief : !actief)
    return naamOk && ruimteOk && actiefOk
  }), [sortedItems, filters])

  const allFilteredSelected = filteredItems.length > 0 && filteredItems.every((item) => selectedIds.includes(String(item.id)))

  function openCreate() {
    setMessage('')
    setError('')
    setEditingId('')
    setForm({ ...initialForm, space_id: spaces.length === 1 ? String(spaces[0].id) : '' })
    setModalMode('create')
  }

  function openEdit(item) {
    setMessage('')
    setError('')
    setEditingId(String(item?.id || ''))
    setForm({ naam: String(item?.naam || ''), space_id: String(item?.space_id || ''), active: Boolean(item?.active) })
    setModalMode('edit')
  }

  function closeModal() {
    if (isSaving) return
    setModalMode('')
    setEditingId('')
    setForm(initialForm)
  }

  function toggleSelected(id) {
    const key = String(id)
    setSelectedIds((current) => current.includes(key) ? current.filter((value) => value !== key) : [...current, key])
  }

  function toggleAllFiltered() {
    if (allFilteredSelected) {
      const filteredSet = new Set(filteredItems.map((item) => String(item.id)))
      setSelectedIds((current) => current.filter((id) => !filteredSet.has(id)))
      return
    }
    const merged = new Set(selectedIds)
    filteredItems.forEach((item) => merged.add(String(item.id)))
    setSelectedIds(Array.from(merged))
  }

  async function handleSave() {
    const naam = String(form.naam || '').trim()
    const spaceId = String(form.space_id || '').trim()
    if (!spaceId) {
      setError('Ruimte is verplicht.')
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
      const url = modalMode === 'edit' ? `/api/sublocations/${encodeURIComponent(editingId)}` : '/api/sublocations'
      const method = modalMode === 'edit' ? 'PUT' : 'POST'
      const response = await fetchJsonWithAuth(url, { method, body: JSON.stringify({ naam, space_id: spaceId, active: Boolean(form.active) }) })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data?.detail || 'Sublocatie opslaan mislukt.')
      setMessage(data?.message || 'Sublocatie opgeslagen.')
      closeModal()
      await loadData()
    } catch (saveError) {
      setError(saveError?.message || 'Sublocatie opslaan mislukt.')
    } finally {
      setIsSaving(false)
    }
  }

  async function deleteSelectedSublocations() {
    const selectedItems = items.filter((item) => selectedIds.includes(String(item.id)))
    if (!selectedItems.length) return
    setIsSaving(true)
    setError('')
    setMessage('')
    const blocked = []
    let deletedCount = 0
    try {
      for (const item of selectedItems) {
        if (Number(item?.inventory_count || 0) > 0) {
          blocked.push(item.naam)
          continue
        }
        const response = await fetchJsonWithAuth(`/api/sublocations/${encodeURIComponent(item.id)}`, { method: 'DELETE' })
        if (!response.ok) {
          blocked.push(item.naam)
          continue
        }
        deletedCount += 1
      }
      await loadData()
      setSelectedIds([])
      if (blocked.length && deletedCount) {
        setMessage(`${deletedCount} sublocatie${deletedCount === 1 ? '' : 's'} verwijderd. ${blocked.length} sublocatie${blocked.length === 1 ? ' kon' : 's konden'} niet worden verwijderd.`)
      } else if (deletedCount) {
        setMessage(`${deletedCount} sublocatie${deletedCount === 1 ? '' : 's'} verwijderd.`)
      } else {
        setError(blocked.length ? 'De geselecteerde sublocaties konden niet worden verwijderd zolang er voorraad aan gekoppeld is.' : 'Geen sublocaties verwijderd.')
      }
    } finally {
      setIsSaving(false)
      setShowActionModal(false)
    }
  }

  async function archiveSelectedSublocations() {
    const selectedItems = items.filter((item) => selectedIds.includes(String(item.id)))
    if (!selectedItems.length) return
    setIsSaving(true)
    setError('')
    setMessage('')
    let archivedCount = 0
    try {
      for (const item of selectedItems) {
        const response = await fetchJsonWithAuth(`/api/sublocations/${encodeURIComponent(item.id)}`, {
          method: 'PUT',
          body: JSON.stringify({ naam: String(item.naam || '').trim(), space_id: String(item.space_id || ''), active: false }),
        })
        if (response.ok) archivedCount += 1
      }
      await loadData()
      setSelectedIds([])
      setMessage(`${archivedCount} sublocatie${archivedCount === 1 ? '' : 's'} gearchiveerd.`)
    } catch (archiveError) {
      setError(archiveError?.message || 'Sublocaties archiveren mislukt.')
    } finally {
      setIsSaving(false)
      setShowActionModal(false)
    }
  }

  function exportCsv() {
    const rows = items.filter((item) => selectedIds.includes(String(item.id))).map((item) => [item.naam, item.space_name, Boolean(item.active) ? 'Ja' : 'Nee'])
    const csv = [['Sublocatie naam', 'Ruimte', 'Actief'].join(','), ...rows.map((row) => row.map(csvEscape).join(','))].join('\n')
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

  if (!isAdmin) return <Navigate to="/instellingen" replace />

  return (
    <AppShell title="Sublocaties" showExit={false}>
      <Card className="rz-settings-spaces-card">
        <div style={{ display: 'grid', gap: 18, width: '100%' }} data-testid="settings-sublocations-page">
          <div><h2 style={{ margin: '0 0 8px 0', fontSize: 20 }}>Beheer Sublocaties</h2></div>
          <Feedback type="error">{error}</Feedback>
          <Feedback type="success">{message}</Feedback>
          <Table wrapperClassName="rz-stock-table-wrapper" tableClassName="rz-stock-table" dataTestId="settings-sublocations-table" tableStyle={{ tableLayout: 'fixed', width: buildTableWidth(columnWidths), minWidth: buildTableWidth(columnWidths) }}>
              <colgroup>
                <col style={{ width: '48px' }} />
                <col style={{ width: '320px' }} />
                <col style={{ width: '260px' }} />
                <col style={{ width: '140px' }} />
              </colgroup>
              <thead>
                <tr className="rz-table-header">
                  <th><input type="checkbox" style={{ accentColor: '#1A3E2B', width: 16, height: 16 }} checked={allFilteredSelected} onChange={toggleAllFiltered} aria-label="Selecteer alle zichtbare sublocaties" /></th>
                  <th>Sublocatie</th>
                  <th>Ruimte</th>
                  <th className="rz-num">Actief</th>
                </tr>
                <tr className="rz-table-filters">
                  <th />
                  <th><input className="rz-input rz-inline-input" value={filters.naam} onChange={(event) => setFilters((current) => ({ ...current, naam: event.target.value }))} placeholder="Filter" aria-label="Filter op sublocatie" /></th>
                  <th><input className="rz-input rz-inline-input" value={filters.ruimte} onChange={(event) => setFilters((current) => ({ ...current, ruimte: event.target.value }))} placeholder="Filter" aria-label="Filter op ruimte" /></th>
                  <th className="rz-num">
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, justifyContent: 'center', minHeight: 20, width: '100%' }}>
                      <label style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 12 }}>
                        <input type="checkbox" style={{ accentColor: '#1A3E2B', width: 16, height: 16 }} checked={filters.actiefJa} onChange={(event) => setFilters((current) => ({ ...current, actiefJa: event.target.checked }))} />Ja
                      </label>
                      <label style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 12 }}>
                        <input type="checkbox" style={{ accentColor: '#1A3E2B', width: 16, height: 16 }} checked={filters.actiefNee} onChange={(event) => setFilters((current) => ({ ...current, actiefNee: event.target.checked }))} />Nee
                      </label>
                    </div>
                  </th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr><td colSpan={4}>Sublocaties laden…</td></tr>
                ) : filteredItems.length === 0 ? (
                  <tr><td colSpan={4}>Nog geen sublocaties beschikbaar.</td></tr>
                ) : filteredItems.map((item) => {
                  const selected = selectedIds.includes(String(item.id))
                  return (
                    <tr key={item.id} className={selected ? 'rz-row-selected' : ''}>
                      <td><input type="checkbox" style={{ accentColor: '#1A3E2B', width: 16, height: 16 }} checked={selected} onChange={() => toggleSelected(item.id)} aria-label={`Selecteer ${item.naam}`} /></td>
                      <td>
                        <button type="button" className="rz-inline-cell rz-inline-cell-button" onClick={() => openEdit(item)} title="Klik om te bewerken">{item.naam}</button>
                      </td>
                      <td>{item.space_name}</td>
                      <td className="rz-num"><input type="checkbox" style={{ accentColor: '#1A3E2B', width: 16, height: 16 }} checked={Boolean(item.active)} readOnly aria-label={`Actief ${item.naam}`} /></td>
                    </tr>
                  )
                })}
              </tbody>
            </Table>
          <div className="rz-stock-table-actions" style={{ justifyContent: 'flex-end', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              <Button type="button" variant="secondary" onClick={exportCsv} disabled={isLoading || selectedIds.length === 0 || isSaving}>Exporteren</Button>
              <Button type="button" variant="secondary" onClick={() => setShowActionModal(true)} disabled={isSaving || selectedIds.length === 0}>Verwijderen</Button>
              <Button type="button" onClick={openCreate} disabled={isSaving}>Toevoegen</Button>
            </div>
          </div>
        </div>
      </Card>
      <SublocationModal mode={modalMode} form={form} onChange={setForm} onClose={closeModal} onSubmit={handleSave} busy={isSaving} spaces={spaces} />
      <DeleteActionModal open={showActionModal} selectedCount={selectedIds.length} onClose={() => setShowActionModal(false)} onDelete={deleteSelectedSublocations} onArchive={archiveSelectedSublocations} busy={isSaving} />
    </AppShell>
  )
}
