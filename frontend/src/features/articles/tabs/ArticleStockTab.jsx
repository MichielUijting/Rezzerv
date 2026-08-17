import { useMemo, useState } from 'react'
import Button from '../../../ui/Button'
import Input from '../../../ui/Input'
import { canCurrentUserPerform, fetchJsonWithAuth, isHouseholdAdminFromContext, readStoredAuthContext } from '../../../lib/authSession'

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

function emptyMutationForm() {
  return {
    inventoryId: '',
    action: '',
    quantity: '',
    note: '',
  }
}

export default function ArticleStockTab({ article = {}, articleData, onInventoryChanged = async () => {} }) {
  const sourceArticle = articleData ?? article
  const locations = Array.isArray(sourceArticle.locations) ? sourceArticle.locations : []
  const authContext = readStoredAuthContext() || {}
  const canEditInventory = isHouseholdAdminFromContext(authContext) || canCurrentUserPerform('inventory.update', authContext)
  const [mutationForm, setMutationForm] = useState(() => emptyMutationForm())
  const [mutationBusy, setMutationBusy] = useState(false)
  const [mutationError, setMutationError] = useState('')
  const [mutationSuccess, setMutationSuccess] = useState('')

  const totalQuantity = useMemo(() => {
    return locations.reduce((sum, entry) => sum + (Number(entry?.aantal ?? entry?.quantity) || 0), 0)
  }, [locations])

  const inventoryRows = useMemo(() => {
    return locations.map((entry, index) => ({
      rowKey: `${entry?.locatie || 'locatie'}-${entry?.sublocatie || 'algemeen'}-${index}`,
      inventoryId: String(entry?.id || ''),
      locationName: normalizeLocationName(entry?.locatie ?? entry?.space_name),
      sublocationName: normalizeSubLocationName(entry?.sublocatie ?? entry?.sublocation_name),
      quantity: Number(entry?.aantal ?? entry?.quantity) || 0,
    }))
  }, [locations])

  const selectedRow = useMemo(
    () => inventoryRows.find((row) => row.inventoryId === mutationForm.inventoryId) || null,
    [inventoryRows, mutationForm.inventoryId],
  )

  function resetFeedback() {
    setMutationError('')
    setMutationSuccess('')
  }

  function openMutation(row, action) {
    if (!canEditInventory || !row?.inventoryId) return
    resetFeedback()
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

  async function handleMutationSubmit(event) {
    event.preventDefault()
    if (!canEditInventory || !selectedRow) return

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
      const response = await fetchJsonWithAuth('/api/inventory-events', {
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
                  <span>{row.locationName}</span>
                  <span>{row.sublocationName}</span>
                  <span className="rz-stock-summary-table-quantity">{formatQuantity(row.quantity)}</span>
                  <span className="rz-stock-action-buttons">
                    <Button type="button" variant="secondary" disabled={!canEditInventory || !row.inventoryId} onClick={() => openMutation(row, 'adjustment')} data-testid={`article-stock-adjust-${row.inventoryId || row.rowKey}`}>Corrigeren</Button>
                    <Button type="button" variant="secondary" disabled={!canEditInventory || !row.inventoryId || row.quantity <= 0} onClick={() => openMutation(row, 'consume')} data-testid={`article-stock-consume-${row.inventoryId || row.rowKey}`}>Afboeken</Button>
                  </span>
                </div>
              ))}
            </div>

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
