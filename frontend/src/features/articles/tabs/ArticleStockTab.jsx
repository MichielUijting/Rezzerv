import { useMemo, useState } from 'react'
import Button from '../../../ui/Button'
import Input from '../../../ui/Input'
import { fetchJsonWithAuth, isHouseholdAdminFromContext, readStoredAuthContext } from '../../../lib/authSession'

function normalizeLocationName(value, isUnassigned = false) {
  if (isUnassigned) return 'Nog geen locatie'
  return value || 'Onbekende locatie'
}

function normalizeSubLocationName(value, isUnassigned = false) {
  if (isUnassigned) return '—'
  return value || 'Algemeen'
}

function formatQuantity(value) {
  const number = Number(value)
  if (Number.isNaN(number)) return '0'
  return String(number)
}

function emptyMutationForm() {
  return {
    inventoryId: '',
    action: '',
    quantity: '',
    note: '',
  }
}

function emptyAssignmentForm() {
  return {
    inventoryId: '',
    quantity: '',
    spaceId: '',
    sublocationId: '',
  }
}

export default function ArticleStockTab({ article = {}, articleData, onInventoryChanged = async () => {} }) {
  const sourceArticle = articleData ?? article
  const locations = Array.isArray(sourceArticle.locations) ? sourceArticle.locations : []
  const authContext = readStoredAuthContext() || {}
  const canEditInventory = isHouseholdAdminFromContext(authContext)
  const householdArticleId = String(sourceArticle?.household_article_id || sourceArticle?.article_id || sourceArticle?.id || '').trim()
  const [mutationForm, setMutationForm] = useState(() => emptyMutationForm())
  const [mutationBusy, setMutationBusy] = useState(false)
  const [mutationError, setMutationError] = useState('')
  const [mutationSuccess, setMutationSuccess] = useState('')
  const [assignmentForm, setAssignmentForm] = useState(() => emptyAssignmentForm())
  const [assignmentBusy, setAssignmentBusy] = useState(false)
  const [assignmentOptionsBusy, setAssignmentOptionsBusy] = useState(false)
  const [locationOptions, setLocationOptions] = useState({ spaces: [], sublocations: [] })

  const totalQuantity = useMemo(() => {
    return locations.reduce((sum, entry) => sum + (Number(entry?.aantal ?? entry?.quantity) || 0), 0)
  }, [locations])

  const inventoryRows = useMemo(() => {
    return locations.map((entry, index) => {
      const rawSpaceId = String(entry?.space_id || '').trim()
      const rawSublocationId = String(entry?.sublocation_id || '').trim()
      const rawLocationName = String(entry?.locatie ?? entry?.space_name ?? '').trim()
      const rawSublocationName = String(entry?.sublocatie ?? entry?.sublocation_name ?? '').trim()
      const isUnassigned = !rawSpaceId && !rawSublocationId && !rawLocationName && !rawSublocationName
      return {
        rowKey: `${entry?.id || 'inventory'}-${index}`,
        inventoryId: String(entry?.id || ''),
        spaceId: rawSpaceId,
        sublocationId: rawSublocationId,
        isUnassigned,
        locationName: normalizeLocationName(rawLocationName, isUnassigned),
        sublocationName: normalizeSubLocationName(rawSublocationName, isUnassigned),
        quantity: Number(entry?.aantal ?? entry?.quantity) || 0,
      }
    })
  }, [locations])

  const selectedRow = useMemo(
    () => inventoryRows.find((row) => row.inventoryId === mutationForm.inventoryId) || null,
    [inventoryRows, mutationForm.inventoryId],
  )

  const selectedAssignmentRow = useMemo(
    () => inventoryRows.find((row) => row.inventoryId === assignmentForm.inventoryId) || null,
    [inventoryRows, assignmentForm.inventoryId],
  )

  const selectedAssignmentSpace = useMemo(
    () => locationOptions.spaces.find((space) => String(space.id) === String(assignmentForm.spaceId)) || null,
    [locationOptions.spaces, assignmentForm.spaceId],
  )

  const assignmentSublocations = useMemo(() => {
    if (!selectedAssignmentSpace) return []
    return locationOptions.sublocations.filter(
      (item) => String(item.space_id) === String(selectedAssignmentSpace.id),
    )
  }, [locationOptions.sublocations, selectedAssignmentSpace])

  function resetFeedback() {
    setMutationError('')
    setMutationSuccess('')
  }

  function openMutation(row, action) {
    if (!canEditInventory || !householdArticleId || !row?.inventoryId) return
    resetFeedback()
    setAssignmentForm(emptyAssignmentForm())
    setMutationForm({
      inventoryId: row.inventoryId,
      action,
      quantity: action === 'adjustment' ? String(row.quantity) : '1',
      note: '',
    })
  }

  function closeMutation() {
    resetFeedback()
    setMutationForm(emptyMutationForm())
  }

  async function loadLocationOptions() {
    const [spacesResponse, sublocationsResponse] = await Promise.all([
      fetchJsonWithAuth(`/api/spaces?_ts=${Date.now()}`, { cache: 'no-store' }),
      fetchJsonWithAuth(`/api/sublocations?_ts=${Date.now()}`, { cache: 'no-store' }),
    ])
    const spacesData = await spacesResponse.json().catch(() => ({}))
    const sublocationsData = await sublocationsResponse.json().catch(() => ({}))
    if (!spacesResponse.ok || !sublocationsResponse.ok) {
      throw new Error(spacesData?.detail || sublocationsData?.detail || 'Locaties konden niet worden geladen.')
    }
    return {
      spaces: (Array.isArray(spacesData?.items) ? spacesData.items : []).filter((item) => Boolean(item?.active)),
      sublocations: (Array.isArray(sublocationsData?.items) ? sublocationsData.items : []).filter((item) => Boolean(item?.active)),
    }
  }

  async function openAssignment(row) {
    if (!canEditInventory || !householdArticleId || !row?.inventoryId || !row?.isUnassigned) return
    resetFeedback()
    setMutationForm(emptyMutationForm())
    setAssignmentOptionsBusy(true)
    try {
      const options = await loadLocationOptions()
      setLocationOptions(options)
      setAssignmentForm({
        inventoryId: row.inventoryId,
        quantity: String(row.quantity),
        spaceId: options.spaces.length === 1 ? String(options.spaces[0].id) : '',
        sublocationId: '',
      })
    } catch (error) {
      setMutationError(error?.message || 'Locaties konden niet worden geladen.')
    } finally {
      setAssignmentOptionsBusy(false)
    }
  }

  function closeAssignment() {
    resetFeedback()
    setAssignmentForm(emptyAssignmentForm())
  }

  async function handleMutationSubmit(event) {
    event.preventDefault()
    if (!canEditInventory || !householdArticleId || !selectedRow) return

    const quantity = Number(mutationForm.quantity)
    if (!Number.isInteger(quantity) || quantity < 0) {
      setMutationError('Voer een geldig geheel aantal in.')
      return
    }
    if (mutationForm.action === 'consume' && quantity <= 0) {
      setMutationError('Het af te boeken aantal moet groter zijn dan 0.')
      return
    }
    if (mutationForm.action === 'consume' && quantity > selectedRow.quantity) {
      setMutationError('Je kunt niet meer afboeken dan op deze locatie aanwezig is.')
      return
    }

    setMutationBusy(true)
    resetFeedback()
    try {
      const response = await fetchJsonWithAuth(`/api/household-articles/${encodeURIComponent(householdArticleId)}/inventory-events`, {
        method: 'POST',
        body: JSON.stringify({
          inventory_id: selectedRow.inventoryId,
          article_name: String(sourceArticle?.article_name || sourceArticle?.name || '').trim(),
          quantity,
          event_type: mutationForm.action,
          note: String(mutationForm.note || '').trim() || undefined,
        }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(data?.detail || 'Voorraadmutatie kon niet worden opgeslagen.')
      }
      await onInventoryChanged()
      setMutationSuccess(mutationForm.action === 'consume' ? 'Voorraad is afgeboekt.' : 'Voorraadcorrectie is opgeslagen.')
      setMutationForm(emptyMutationForm())
    } catch (error) {
      setMutationError(error?.message || 'Voorraadmutatie kon niet worden opgeslagen.')
    } finally {
      setMutationBusy(false)
    }
  }

  async function handleAssignmentSubmit(event) {
    event.preventDefault()
    if (!canEditInventory || !householdArticleId || !selectedAssignmentRow) return

    const quantity = Number(assignmentForm.quantity)
    if (!Number.isInteger(quantity) || quantity <= 0) {
      setMutationError('Het toe te wijzen aantal moet een positief geheel getal zijn.')
      return
    }
    if (quantity > selectedAssignmentRow.quantity) {
      setMutationError('Je kunt niet meer toewijzen dan de voorraad zonder locatie.')
      return
    }
    if (!selectedAssignmentSpace) {
      setMutationError('Kies eerst een locatie.')
      return
    }
    if (assignmentSublocations.length > 0 && !assignmentForm.sublocationId) {
      setMutationError('Kies een sublocatie binnen deze locatie.')
      return
    }

    setAssignmentBusy(true)
    resetFeedback()
    try {
      const response = await fetchJsonWithAuth(`/api/household-articles/${encodeURIComponent(householdArticleId)}/inventory-transfers`, {
        method: 'POST',
        body: JSON.stringify({
          inventory_id: selectedAssignmentRow.inventoryId,
          quantity,
          to_space_id: String(selectedAssignmentSpace.id),
          to_sublocation_id: assignmentForm.sublocationId || null,
          note: 'Locatie toegewezen aan bestaande voorraad na activeren van Waar Inhuis',
        }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(data?.detail || 'Locatie kon niet aan de voorraad worden toegewezen.')
      }
      const targetSublocation = assignmentSublocations.find(
        (item) => String(item.id) === String(assignmentForm.sublocationId),
      )
      const targetLabel = targetSublocation
        ? `${selectedAssignmentSpace.naam} / ${targetSublocation.naam}`
        : String(selectedAssignmentSpace.naam || 'gekozen locatie')
      await onInventoryChanged()
      setMutationSuccess(`${quantity} toegewezen aan ${targetLabel}.`)
      setAssignmentForm(emptyAssignmentForm())
    } catch (error) {
      setMutationError(error?.message || 'Locatie kon niet aan de voorraad worden toegewezen.')
    } finally {
      setAssignmentBusy(false)
    }
  }

  return (
    <div className="rz-stock-tab">
      <section className="rz-stock-summary-card rz-article-detail-section rz-article-detail-section--summary">
        <div className="rz-stock-summary-label">Totale voorraad</div>
        <div className="rz-stock-summary-value">{totalQuantity}</div>
      </section>

      {mutationError ? <div className="rz-article-detail-alert" data-testid="article-stock-mutation-error">{mutationError}</div> : null}
      {mutationSuccess ? <div className="rz-inline-feedback rz-inline-feedback--success" data-testid="article-stock-mutation-success">{mutationSuccess}</div> : null}

      {inventoryRows.length === 0 ? (
        <div className="rz-empty-state">Er zijn nog geen voorraadlocaties bekend voor dit artikel.</div>
      ) : (
        <section className="rz-stock-block rz-article-detail-section">
          <h3 className="rz-stock-block-title rz-article-detail-section-title">Voorraad per sublocatie</h3>
          <div className="rz-stock-block-body rz-article-detail-section-body">
            <div className="rz-stock-summary-table" role="table" aria-label="Voorraad per sublocatie">
              <div className="rz-stock-summary-table-header" role="row">
                <div role="columnheader">Locatie</div>
                <div role="columnheader">Sublocatie</div>
                <div role="columnheader" className="rz-stock-summary-table-header-quantity">Aantal</div>
                <div role="columnheader">Acties</div>
              </div>
              {inventoryRows.map((row) => (
                <div key={row.rowKey} className="rz-stock-summary-table-row" role="row" data-testid={`article-stock-row-${row.rowKey}`}>
                  <span data-testid={row.isUnassigned ? `article-stock-unassigned-${row.inventoryId}` : undefined}>{row.locationName}</span>
                  <span>{row.sublocationName}</span>
                  <span className="rz-stock-summary-table-quantity">{formatQuantity(row.quantity)}</span>
                  <span className="rz-stock-action-buttons">
                    {row.isUnassigned ? (
                      <Button
                        type="button"
                        variant="secondary"
                        disabled={!canEditInventory || !householdArticleId || !row.inventoryId || row.quantity <= 0 || assignmentOptionsBusy}
                        onClick={() => openAssignment(row)}
                        data-testid={`article-stock-assign-location-${row.inventoryId || row.rowKey}`}
                      >
                        {assignmentOptionsBusy ? 'Locaties laden…' : 'Locatie toewijzen'}
                      </Button>
                    ) : null}
                    <Button type="button" variant="secondary" disabled={!canEditInventory || !householdArticleId || !row.inventoryId} onClick={() => openMutation(row, 'adjustment')} data-testid={`article-stock-adjust-${row.inventoryId || row.rowKey}`}>Corrigeren</Button>
                    <Button type="button" variant="secondary" disabled={!canEditInventory || !householdArticleId || !row.inventoryId || row.quantity <= 0} onClick={() => openMutation(row, 'consume')} data-testid={`article-stock-consume-${row.inventoryId || row.rowKey}`}>Afboeken</Button>
                  </span>
                </div>
              ))}
            </div>

            {assignmentForm.inventoryId && selectedAssignmentRow ? (
              <form className="rz-stock-mutation-form" onSubmit={handleAssignmentSubmit} data-testid="article-stock-location-assignment-form">
                <div className="rz-stock-mutation-title">Locatie toewijzen</div>
                <div className="rz-stock-selected-row-summary">
                  Nog geen locatie — beschikbaar {formatQuantity(selectedAssignmentRow.quantity)}
                </div>
                <Input
                  label="Aantal toewijzen"
                  type="number"
                  min="1"
                  max={String(selectedAssignmentRow.quantity)}
                  step="1"
                  value={assignmentForm.quantity}
                  onChange={(formEvent) => setAssignmentForm((current) => ({ ...current, quantity: formEvent.target.value }))}
                  disabled={assignmentBusy}
                />
                <label className="rz-field">
                  <span className="rz-label">Locatie</span>
                  <select
                    className="rz-input"
                    value={assignmentForm.spaceId}
                    disabled={assignmentBusy}
                    onChange={(event) => setAssignmentForm((current) => ({ ...current, spaceId: event.target.value, sublocationId: '' }))}
                    data-testid="article-stock-assignment-space"
                  >
                    <option value="">Kies locatie</option>
                    {locationOptions.spaces.map((space) => (
                      <option key={space.id} value={space.id}>{space.naam}</option>
                    ))}
                  </select>
                </label>
                {selectedAssignmentSpace && assignmentSublocations.length > 0 ? (
                  <label className="rz-field">
                    <span className="rz-label">Sublocatie</span>
                    <select
                      className="rz-input"
                      value={assignmentForm.sublocationId}
                      disabled={assignmentBusy}
                      onChange={(event) => setAssignmentForm((current) => ({ ...current, sublocationId: event.target.value }))}
                      data-testid="article-stock-assignment-sublocation"
                    >
                      <option value="">Kies sublocatie</option>
                      {assignmentSublocations.map((sublocation) => (
                        <option key={sublocation.id} value={sublocation.id}>{sublocation.naam}</option>
                      ))}
                    </select>
                  </label>
                ) : null}
                {locationOptions.spaces.length === 0 ? (
                  <div className="rz-article-detail-alert">
                    Er zijn nog geen locaties ingericht. Voeg die eerst toe via Instellingen → Locaties.
                  </div>
                ) : null}
                <div className="rz-stock-mutation-actions">
                  <Button type="button" variant="secondary" onClick={closeAssignment} disabled={assignmentBusy}>Annuleren</Button>
                  <Button type="submit" disabled={assignmentBusy || locationOptions.spaces.length === 0}>{assignmentBusy ? 'Toewijzen…' : 'Toewijzen'}</Button>
                </div>
              </form>
            ) : null}

            {mutationForm.inventoryId && selectedRow ? (
              <form className="rz-stock-mutation-form" onSubmit={handleMutationSubmit} data-testid="article-stock-mutation-form">
                <div className="rz-stock-mutation-title">
                  {mutationForm.action === 'consume' ? 'Voorraad afboeken' : 'Voorraad corrigeren'}
                </div>
                <div className="rz-stock-selected-row-summary">
                  {selectedRow.locationName} / {selectedRow.sublocationName} — huidige voorraad {formatQuantity(selectedRow.quantity)}
                </div>
                <Input
                  label={mutationForm.action === 'consume' ? 'Aantal afboeken' : 'Nieuwe hoeveelheid'}
                  type="number"
                  min="0"
                  step="1"
                  value={mutationForm.quantity}
                  onChange={(formEvent) => setMutationForm((current) => ({ ...current, quantity: formEvent.target.value }))}
                  disabled={mutationBusy}
                />
                <Input
                  label="Reden / notitie"
                  type="text"
                  value={mutationForm.note}
                  onChange={(formEvent) => setMutationForm((current) => ({ ...current, note: formEvent.target.value }))}
                  disabled={mutationBusy}
                />
                <div className="rz-stock-mutation-actions">
                  <Button type="button" variant="secondary" onClick={closeMutation} disabled={mutationBusy}>Annuleren</Button>
                  <Button type="submit" disabled={mutationBusy}>{mutationBusy ? 'Opslaan...' : 'Opslaan'}</Button>
                </div>
              </form>
            ) : null}
          </div>
        </section>
      )}
    </div>
  )
}
