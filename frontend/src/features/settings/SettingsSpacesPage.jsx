import { useEffect, useMemo, useState } from 'react'
import { Navigate } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import Card from '../../ui/Card'
import Button from '../../ui/Button'
import { buildTableWidth } from '../../ui/resizableTable'
import Table from '../../ui/Table'
import { fetchJsonWithAuth, isHouseholdAdminFromContext, readStoredAuthContext } from '../../lib/authSession'

const initialForm = { naam: '', active: true }
const initialFilters = { naam: '', actiefJa: false, actiefNee: false, sublocaties: '' }
const spacesTableColumns = [
  { key: 'select', width: 48 },
  { key: 'ruimte', width: 380 },
  { key: 'actief', width: 140 },
  { key: 'sublocaties', width: 180 },
]
const spaceColumnWidths = Object.fromEntries(spacesTableColumns.map(({ key, width }) => [key, width]))

function Feedback({ type = 'info', children }) {
  if (!children) return null
  const isError = type === 'error'
  const background = isError ? '#fef2f2' : '#ecfdf3'
  const border = isError ? '#fecaca' : '#bbf7d0'
  const color = isError ? '#991b1b' : '#166534'
  return <div style={{ padding: '12px 14px', borderRadius: 12, border: `1px solid ${border}`, background, color }}>{children}</div>
}

function SpaceModal({ mode, form, onChange, onClose, onSubmit, busy }) {
  if (!mode) return null
  const title = mode === 'create' ? 'Nieuwe ruimte' : 'Ruimte bewerken'
  return (
    <div className="rz-modal-backdrop" role="presentation">
      <div className="rz-modal-card" role="dialog" aria-modal="true" aria-labelledby="spaces-modal-title">
        <h3 id="spaces-modal-title" className="rz-modal-title">{title}</h3>
        <div style={{ display: 'grid', gap: 16 }}>
          <label className="rz-input-field">
            <div className="rz-label">Ruimte naam</div>
            <input
              className="rz-input"
              autoFocus
              value={form.naam}
              onChange={(event) => onChange({ ...form, naam: event.target.value })}
              placeholder="Bijvoorbeeld: Garage"
            />
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 10, color: '#0f172a', fontWeight: 600 }}>
            <input
              type="checkbox"
              style={{ accentColor: '#1A3E2B', width: 16, height: 16 }}
              checked={Boolean(form.active)}
              onChange={(event) => onChange({ ...form, active: event.target.checked })}
            />
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
      <div className="rz-modal-card" role="dialog" aria-modal="true" aria-labelledby="spaces-delete-title">
        <h3 id="spaces-delete-title" className="rz-modal-title">Geselecteerde ruimtes verwerken</h3>
        <p className="rz-modal-text">Je hebt {selectedCount} ruimte{selectedCount === 1 ? '' : 's'} geselecteerd. Kies wat je wilt doen.</p>
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

export default function SettingsSpacesPage() {
  const isAdmin = isHouseholdAdminFromContext(readStoredAuthContext())
  const [items, setItems] = useState([])
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

  async function loadSpaces() {
    setIsLoading(true)
    setError('')
    try {
      const response = await fetchJsonWithAuth('/api/spaces')
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data?.detail || 'Ruimtes konden niet worden geladen.')
      setItems(Array.isArray(data?.items) ? data.items : [])
    } catch (loadError) {
      setError(loadError?.message || 'Ruimtes konden niet worden geladen.')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    if (isAdmin) loadSpaces()
  }, [isAdmin])

  const sortedItems = useMemo(
    () => [...items].sort((left, right) => String(left?.naam || '').localeCompare(String(right?.naam || ''), 'nl')),
    [items],
  )

  const filteredItems = useMemo(() => {
    return sortedItems.filter((item) => {
      const naamOk = !filters.naam || String(item?.naam || '').toLowerCase().includes(filters.naam.toLowerCase())
      const actief = Boolean(item?.active)
      const actiefFilterAan = Boolean(filters.actiefJa) !== Boolean(filters.actiefNee)
      const actiefOk = !actiefFilterAan || (filters.actiefJa ? actief : !actief)
      const sublocatiesOk = !filters.sublocaties || String(Number(item?.sublocation_count || 0)).includes(filters.sublocaties)
      return naamOk && actiefOk && sublocatiesOk
    })
  }, [sortedItems, filters])

  const allFilteredSelected = filteredItems.length > 0 && filteredItems.every((item) => selectedIds.includes(String(item.id)))

  function openCreate() {
    setMessage('')
    setError('')
    setEditingId('')
    setForm(initialForm)
    setModalMode('create')
  }

  function openEdit(item) {
    setMessage('')
    setError('')
    setEditingId(String(item?.id || ''))
    setForm({ naam: String(item?.naam || ''), active: Boolean(item?.active) })
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
    if (!naam) {
      setError('Ruimtenaam is verplicht.')
      return
    }
    setIsSaving(true)
    setError('')
    setMessage('')
    try {
      const url = modalMode === 'edit' ? `/api/spaces/${encodeURIComponent(editingId)}` : '/api/spaces'
      const method = modalMode === 'edit' ? 'PUT' : 'POST'
      const response = await fetchJsonWithAuth(url, {
        method,
        body: JSON.stringify({ naam, active: Boolean(form.active) }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data?.detail || 'Ruimte opslaan mislukt.')
      setMessage(data?.message || 'Ruimte opgeslagen.')
      closeModal()
      await loadSpaces()
    } catch (saveError) {
      setError(saveError?.message || 'Ruimte opslaan mislukt.')
    } finally {
      setIsSaving(false)
    }
  }

  async function deleteSelectedSpaces() {
    const selectedItems = items.filter((item) => selectedIds.includes(String(item.id)))
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
        const data = await response.json().catch(() => ({}))
        if (!response.ok) {
          blocked.push(item.naam)
          continue
        }
        deletedCount += 1
      }
      await loadSpaces()
      setSelectedIds([])
      if (blocked.length && deletedCount) {
        setMessage(`${deletedCount} ruimte${deletedCount === 1 ? '' : 's'} verwijderd. ${blocked.length} ruimte${blocked.length === 1 ? ' kon' : 's konden'} niet worden verwijderd.`)
      } else if (deletedCount) {
        setMessage(`${deletedCount} ruimte${deletedCount === 1 ? '' : 's'} verwijderd.`)
      } else {
        setError(blocked.length ? 'De geselecteerde ruimtes konden niet worden verwijderd zolang er sublocaties of voorraad aan gekoppeld zijn.' : 'Geen ruimtes verwijderd.')
      }
    } finally {
      setIsSaving(false)
      setShowActionModal(false)
    }
  }

  async function archiveSelectedSpaces() {
    const selectedItems = items.filter((item) => selectedIds.includes(String(item.id)))
    if (!selectedItems.length) return
    setIsSaving(true)
    setError('')
    setMessage('')
    let archivedCount = 0
    try {
      for (const item of selectedItems) {
        const response = await fetchJsonWithAuth(`/api/spaces/${encodeURIComponent(item.id)}`, {
          method: 'PUT',
          body: JSON.stringify({ naam: String(item.naam || '').trim(), active: false }),
        })
        const data = await response.json().catch(() => ({}))
        if (response.ok) archivedCount += 1
      }
      await loadSpaces()
      setSelectedIds([])
      setMessage(`${archivedCount} ruimte${archivedCount === 1 ? '' : 's'} gearchiveerd.`)
    } catch (archiveError) {
      setError(archiveError?.message || 'Ruimtes archiveren mislukt.')
    } finally {
      setIsSaving(false)
      setShowActionModal(false)
    }
  }

  function exportCsv() {
    const rows = items.filter((item) => selectedIds.includes(String(item.id))).map((item) => [
      item.naam,
      Boolean(item.active) ? 'Ja' : 'Nee',
      Number(item.sublocation_count || 0),
      Number(item.inventory_count || 0),
    ])
    const csv = [
      ['Ruimte naam', 'Actief', 'Aantal sublocaties', 'Aantal voorraadregels'].join(','),
      ...rows.map((row) => row.map(csvEscape).join(',')),
    ].join('\n')
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'rezzerv-ruimtes.csv'
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  }

  if (!isAdmin) {
    return <Navigate to="/instellingen" replace />
  }

  return (
    <AppShell title="Ruimtes" showExit={false}>
      <Card className="rz-settings-spaces-card">
        <div style={{ display: 'grid', gap: 18, width: '100%' }} data-testid="settings-spaces-page">
          <div>
            <h2 style={{ margin: '0 0 8px 0', fontSize: 20 }}>Beheer Ruimtes</h2>
          </div>

          <Feedback type="error">{error}</Feedback>
          <Feedback type="success">{message}</Feedback>

          <Table wrapperClassName="rz-stock-table-wrapper" tableClassName="rz-stock-table" dataTestId="settings-spaces-table" tableStyle={{ tableLayout: 'fixed', width: buildTableWidth(spaceColumnWidths), minWidth: buildTableWidth(spaceColumnWidths) }}>
              <colgroup>
                <col style={{ width: '48px' }} />
                <col style={{ width: 'auto' }} />
                <col style={{ width: '140px' }} />
                <col style={{ width: '180px' }} />
              </colgroup>
              <thead>
                <tr className="rz-table-header">
                  <th>
<input
                      type="checkbox"
                      style={{ accentColor: '#1A3E2B', width: 16, height: 16 }}
                      checked={allFilteredSelected}
                      onChange={toggleAllFiltered}
                      aria-label="Selecteer alle zichtbare ruimtes"
                    />
                  </th>
                  <th>Ruimte</th>
                  <th className="rz-num">Actief</th>
                  <th className="rz-num">Aantal sublocaties</th>
                </tr>
                <tr className="rz-table-filters">
                  <th />
                  <th>
                    <input
                      className="rz-input rz-inline-input"
                      value={filters.naam}
                      onChange={(event) => setFilters((current) => ({ ...current, naam: event.target.value }))}
                      placeholder="Filter"
                      aria-label="Filter op ruimte"
                    />
                  </th>
                  <th className="rz-num">
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, justifyContent: 'center', minHeight: 20, width: '100%' }}>
                      <label style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 12 }}>
                        <input
                          type="checkbox"
                          style={{ accentColor: '#1A3E2B', width: 16, height: 16 }}
                          checked={filters.actiefJa}
                          onChange={(event) => setFilters((current) => ({ ...current, actiefJa: event.target.checked }))}
                          aria-label="Filter actief"
                        />
                        Ja
                      </label>
                      <label style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 12 }}>
                        <input
                          type="checkbox"
                          style={{ accentColor: '#1A3E2B', width: 16, height: 16 }}
                          checked={filters.actiefNee}
                          onChange={(event) => setFilters((current) => ({ ...current, actiefNee: event.target.checked }))}
                          aria-label="Filter inactief"
                        />
                        Nee
                      </label>
                    </div>
                  </th>
                  <th>
                    <input
                      className="rz-input rz-inline-input"
                      value={filters.sublocaties}
                      onChange={(event) => setFilters((current) => ({ ...current, sublocaties: event.target.value }))}
                      placeholder="Filter"
                      aria-label="Filter op aantal sublocaties"
                    />
                  </th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr><td colSpan={4}>Ruimtes laden…</td></tr>
                ) : filteredItems.length === 0 ? (
                  <tr><td colSpan={4}>Nog geen ruimtes beschikbaar.</td></tr>
                ) : filteredItems.map((item) => {
                  const selected = selectedIds.includes(String(item.id))
                  return (
                    <tr key={item.id} className={selected ? 'rz-row-selected' : ''}>
                      <td>
<input
                          type="checkbox"
                          style={{ accentColor: '#1A3E2B', width: 16, height: 16 }}
                          checked={selected}
                          onChange={() => toggleSelected(item.id)}
                          aria-label={`Selecteer ${item.naam}`}
                        />
                      </td>
                      <td>
                        <button
                          type="button"
                          className="rz-inline-cell rz-inline-cell-button"
                          onClick={() => openEdit(item)}
                          title="Klik om te bewerken"
                          data-testid={`settings-space-edit-${item.id}`}
                        >
                          {item.naam}
                        </button>
                      </td>
                      <td className="rz-num">
                        <input type="checkbox" style={{ accentColor: '#1A3E2B', width: 16, height: 16 }} checked={Boolean(item.active)} readOnly aria-label={`Actief ${item.naam}`} />
                      </td>
                      <td className="rz-num">{Number(item.sublocation_count || 0)}</td>
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

      <SpaceModal
        mode={modalMode}
        form={form}
        onChange={setForm}
        onClose={closeModal}
        onSubmit={handleSave}
        busy={isSaving}
      />

      <DeleteActionModal
        open={showActionModal}
        selectedCount={selectedIds.length}
        onClose={() => setShowActionModal(false)}
        onDelete={deleteSelectedSpaces}
        onArchive={archiveSelectedSpaces}
        busy={isSaving}
      />
    </AppShell>
  )
}
