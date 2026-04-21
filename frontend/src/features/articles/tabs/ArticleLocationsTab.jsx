import { useEffect, useMemo, useState } from 'react'
import Button from '../../../ui/Button'
import Input from '../../../ui/Input'

function normalizeLocationName(value) {
  return value || 'Onbekende locatie'
}

function normalizeSubLocationName(value) {
  return value || 'Algemeen'
}

function formatQuantity(value) {
  const number = Number(value)
  if (Number.isNaN(number)) return '0'
  return String(number)
}

function getPrimaryLocation(locations) {
  if (!locations.length) return null
  return [...locations].sort((a, b) => (Number(b?.aantal ?? b?.quantity) || 0) - (Number(a?.aantal ?? a?.quantity) || 0))[0]
}

function getAuthHeaders() {
  const token = window.localStorage.getItem('rezzerv_token') || ''
  return token ? { Authorization: `Bearer ${token}` } : {}
}

function buildTransferForm() {
  return {
    inventoryId: '',
    sourceSpaceId: '',
    sourceSublocationId: '',
    targetSpaceId: '',
    targetSublocationId: '',
    quantity: '',
    note: '',
  }
}

function groupSpacesWithSublocations(spaces = [], sublocations = []) {
  return spaces.map((space) => ({
    ...space,
    sublocations: sublocations.filter((entry) => String(entry?.space_id || '') === String(space?.id || '')),
  }))
}

export default function ArticleLocationsTab({ articleData = {}, onInventoryChanged = async () => {} }) {
  const articleName = String(articleData?.name || '').trim()
  const locations = Array.isArray(articleData.locations) ? articleData.locations : []
  const [spaces, setSpaces] = useState([])
  const [sublocations, setSublocations] = useState([])
  const [locationsLoading, setLocationsLoading] = useState(false)
  const [locationsError, setLocationsError] = useState('')
  const [transferBusy, setTransferBusy] = useState(false)
  const [transferError, setTransferError] = useState('')
  const [transferSuccess, setTransferSuccess] = useState('')
  const [transferForm, setTransferForm] = useState(() => buildTransferForm())

  useEffect(() => {
    let cancelled = false
    setLocationsLoading(true)
    setLocationsError('')

    Promise.all([
      fetch(`/api/spaces?_ts=${Date.now()}`, { cache: 'no-store', headers: getAuthHeaders() }).then((response) => response.json().then((data) => ({ ok: response.ok, data }))),
      fetch(`/api/sublocations?_ts=${Date.now()}`, { cache: 'no-store', headers: getAuthHeaders() }).then((response) => response.json().then((data) => ({ ok: response.ok, data }))),
    ])
      .then(([spacesResponse, sublocationsResponse]) => {
        if (cancelled) return
        if (!spacesResponse.ok) throw new Error(spacesResponse.data?.detail || 'Ruimtes konden niet worden geladen.')
        if (!sublocationsResponse.ok) throw new Error(sublocationsResponse.data?.detail || 'Sublocaties konden niet worden geladen.')
        setSpaces(Array.isArray(spacesResponse.data?.items) ? spacesResponse.data.items.filter((item) => item?.active !== false) : [])
        setSublocations(Array.isArray(sublocationsResponse.data?.items) ? sublocationsResponse.data.items.filter((item) => item?.active !== false) : [])
      })
      .catch((error) => {
        if (cancelled) return
        setSpaces([])
        setSublocations([])
        setLocationsError(error?.message || 'Ruimtes en sublocaties konden niet worden geladen.')
      })
      .finally(() => {
        if (!cancelled) setLocationsLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [])

  const primaryLocation = useMemo(() => getPrimaryLocation(locations), [locations])

  const locationRows = useMemo(() => {
    return locations.map((entry, index) => ({
      key: `${entry?.locatie || 'locatie'}-${entry?.sublocatie || 'algemeen'}-${index}`,
      inventoryId: String(entry?.id || ''),
      sourceSpaceId: String(entry?.space_id || ''),
      sourceSublocationId: String(entry?.sublocation_id || ''),
      locatie: normalizeLocationName(entry?.locatie ?? entry?.space_name),
      sublocatie: normalizeSubLocationName(entry?.sublocatie ?? entry?.sublocation_name),
      aantal: formatQuantity(entry?.aantal ?? entry?.quantity),
    }))
  }, [locations])

  const spaceOptions = useMemo(() => groupSpacesWithSublocations(spaces, sublocations), [spaces, sublocations])
  const targetSublocationOptions = useMemo(() => {
    if (!transferForm.targetSpaceId) return []
    return sublocations.filter((entry) => String(entry?.space_id || '') === String(transferForm.targetSpaceId))
  }, [transferForm.targetSpaceId, sublocations])

  const selectedRow = useMemo(() => locationRows.find((row) => row.inventoryId === transferForm.inventoryId) || null, [locationRows, transferForm.inventoryId])

  function resetFeedback() {
    setTransferError('')
    setTransferSuccess('')
  }

  function openTransferForm(row) {
    resetFeedback()
    setTransferForm({
      inventoryId: String(row?.inventoryId || ''),
      sourceSpaceId: String(row?.sourceSpaceId || ''),
      sourceSublocationId: String(row?.sourceSublocationId || ''),
      targetSpaceId: '',
      targetSublocationId: '',
      quantity: '',
      note: '',
    })
  }

  function closeTransferForm() {
    resetFeedback()
    setTransferForm(buildTransferForm())
  }

  function handleFormChange(field, value) {
    setTransferForm((current) => {
      if (field === 'targetSpaceId') {
        return { ...current, targetSpaceId: value, targetSublocationId: '' }
      }
      return { ...current, [field]: value }
    })
  }

  async function handleTransferSubmit(event) {
    event.preventDefault()
    resetFeedback()
    setTransferBusy(true)

    try {
      const response = await fetch('/api/inventory-transfers', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeaders(),
        },
        body: JSON.stringify({
          inventory_id: transferForm.inventoryId || undefined,
          article_name: articleName,
          quantity: Number(transferForm.quantity),
          note: String(transferForm.note || '').trim() || undefined,
          from_space_id: transferForm.sourceSpaceId || undefined,
          from_sublocation_id: transferForm.sourceSublocationId || undefined,
          to_space_id: transferForm.targetSpaceId || undefined,
          to_sublocation_id: transferForm.targetSublocationId || undefined,
        }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(data?.detail || 'Voorraadverplaatsing kon niet worden opgeslagen.')
      }
      await onInventoryChanged()
      setTransferSuccess('Voorraad is verplaatst. Locaties, Voorraad en Historie zijn ververst.')
      setTransferForm(buildTransferForm())
    } catch (error) {
      setTransferError(error?.message || 'Voorraadverplaatsing kon niet worden opgeslagen.')
    } finally {
      setTransferBusy(false)
    }
  }

  if (!locationRows.length) {
    return <div className="rz-empty-state">Er zijn nog geen locatiegegevens bekend voor dit artikel.</div>
  }

  return (
    <div className="rz-locations-tab">
      <section className="rz-locations-summary-card rz-article-detail-section rz-article-detail-section--summary">
        <div className="rz-locations-summary-label">Primaire locatie</div>
        <div className="rz-locations-summary-value">{normalizeLocationName(primaryLocation?.locatie)}</div>
        <div className="rz-locations-summary-subvalue">{normalizeSubLocationName(primaryLocation?.sublocatie)}</div>
      </section>

      <section className="rz-locations-group rz-article-detail-section">
        <div className="rz-stock-actions-header">
          <div>
            <h3 className="rz-locations-group-title rz-article-detail-section-title">Alle locaties</h3>
            <div className="rz-stock-actions-help">Gebruik Verplaatsen om voorraad van de ene sublocatie naar een andere sublocatie te verplaatsen.</div>
          </div>
          <div className="rz-stock-action-buttons" data-testid="article-location-actions">
            <Button type="button" variant="secondary" disabled={!locationRows.length} onClick={() => openTransferForm(locationRows[0])} data-testid="article-location-action-transfer">Verplaatsen</Button>
          </div>
        </div>
        <div className="rz-locations-group-body rz-article-detail-section-body">
          {locationsLoading ? <div className="rz-empty-state">Ruimtes en sublocaties worden geladen.</div> : null}
          {locationsError ? <div className="rz-article-detail-alert">{locationsError}</div> : null}
          {transferError ? <div className="rz-article-detail-alert" data-testid="article-location-transfer-error">{transferError}</div> : null}
          {transferSuccess ? <div className="rz-inline-feedback rz-inline-feedback--success" data-testid="article-location-transfer-success">{transferSuccess}</div> : null}

          {transferForm.inventoryId ? (
            <form className="rz-stock-mutation-form" onSubmit={handleTransferSubmit} data-testid="article-location-transfer-form">
              <div className="rz-stock-mutation-title">Actie: Verplaatsen</div>
              {selectedRow ? <div className="rz-stock-selected-row-summary" data-testid="article-location-selected-row">Geselecteerd: {selectedRow.locatie} / {selectedRow.sublocatie} — huidige voorraad {selectedRow.aantal}</div> : null}
              <label className="rz-input-field">
                <div className="rz-label">Doelruimte</div>
                <select className="rz-input" value={transferForm.targetSpaceId} onChange={(formEvent) => handleFormChange('targetSpaceId', formEvent.target.value)} disabled={transferBusy || locationsLoading}>
                  <option value="">Kies een doelruimte</option>
                  {spaceOptions.map((space) => (
                    <option key={space.id} value={space.id}>{space.naam}</option>
                  ))}
                </select>
              </label>
              <label className="rz-input-field">
                <div className="rz-label">Doelsublocatie</div>
                <select className="rz-input" value={transferForm.targetSublocationId} onChange={(formEvent) => handleFormChange('targetSublocationId', formEvent.target.value)} disabled={transferBusy || !transferForm.targetSpaceId}>
                  <option value="">Kies een doelsublocatie</option>
                  {targetSublocationOptions.map((entry) => (
                    <option key={entry.id} value={entry.id}>{entry.naam}</option>
                  ))}
                </select>
              </label>
              <Input label="Aantal" type="number" min="0" value={transferForm.quantity} onChange={(formEvent) => handleFormChange('quantity', formEvent.target.value)} disabled={transferBusy} />
              <Input label="Notitie (optioneel)" type="text" value={transferForm.note} onChange={(formEvent) => handleFormChange('note', formEvent.target.value)} disabled={transferBusy} />
              <div className="rz-stock-mutation-actions">
                <Button type="button" variant="secondary" onClick={closeTransferForm} disabled={transferBusy}>Annuleren</Button>
                <Button type="submit" disabled={transferBusy}>{transferBusy ? 'Opslaan...' : 'Opslaan'}</Button>
              </div>
            </form>
          ) : null}

          {locationRows.map((row) => {
            const isSelected = row.inventoryId === transferForm.inventoryId
            return (
              <button
                key={row.key}
                type="button"
                className={`rz-location-row${isSelected ? ' is-selected' : ''}`}
                onClick={() => openTransferForm(row)}
                data-testid={`article-location-row-${row.inventoryId || row.key}`}
              >
                <div className="rz-location-row-main">
                  <div className="rz-location-row-title">{row.locatie}</div>
                  <div className="rz-location-row-subtitle">{row.sublocatie}</div>
                </div>
                <div className="rz-location-row-meta">
                  <div className="rz-location-row-label">Aantal</div>
                  <div className="rz-location-row-value">{row.aantal}</div>
                </div>
              </button>
            )
          })}
        </div>
      </section>
    </div>
  )
}
