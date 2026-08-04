import { useEffect, useState } from 'react'
import { fetchJsonWithAuth } from '../../../lib/authSession'

export const STOCK = 'STOCK'
export const DIRECT_CONSUMPTION = 'DIRECT_CONSUMPTION'

export const INVENTORY_HANDLING_OPTIONS = [
  { value: STOCK, label: 'Opslaan in voorraad' },
  { value: DIRECT_CONSUMPTION, label: 'Direct consumeren' },
]

function normalizeHandling(value) {
  return String(value || '').trim().toUpperCase() === DIRECT_CONSUMPTION
    ? DIRECT_CONSUMPTION
    : STOCK
}

export default function InventoryHandlingField({
  householdId,
  householdArticleId,
  canManage = false,
  onSaved = null,
}) {
  const [value, setValue] = useState(STOCK)
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [statusMessage, setStatusMessage] = useState('')
  const [errorMessage, setErrorMessage] = useState('')

  useEffect(() => {
    let cancelled = false
    const resolvedHouseholdId = String(householdId || '').trim()
    const resolvedArticleId = String(householdArticleId || '').trim()

    if (!resolvedHouseholdId || !resolvedArticleId) {
      setValue(STOCK)
      setIsLoading(false)
      return () => {
        cancelled = true
      }
    }

    setIsLoading(true)
    setStatusMessage('')
    setErrorMessage('')

    fetchJsonWithAuth(
      `/api/households/${encodeURIComponent(resolvedHouseholdId)}/articles/${encodeURIComponent(resolvedArticleId)}/inventory-handling`,
      { method: 'GET' },
    )
      .then(async (response) => {
        const data = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(data?.detail || 'Voorraadverwerking kon niet worden geladen.')
        if (!cancelled) setValue(normalizeHandling(data?.default_inventory_handling))
      })
      .catch((error) => {
        if (!cancelled) {
          setValue(STOCK)
          setErrorMessage(error?.message || 'Voorraadverwerking kon niet worden geladen.')
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [householdId, householdArticleId])

  async function handleChange(event) {
    const previousValue = value
    const nextValue = normalizeHandling(event.target.value)
    const resolvedHouseholdId = String(householdId || '').trim()
    const resolvedArticleId = String(householdArticleId || '').trim()

    if (!canManage || !resolvedHouseholdId || !resolvedArticleId || nextValue === previousValue) return

    setValue(nextValue)
    setIsSaving(true)
    setStatusMessage('')
    setErrorMessage('')

    try {
      const response = await fetchJsonWithAuth(
        `/api/households/${encodeURIComponent(resolvedHouseholdId)}/articles/${encodeURIComponent(resolvedArticleId)}/inventory-handling`,
        {
          method: 'PUT',
          body: JSON.stringify({ default_inventory_handling: nextValue }),
        },
      )
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data?.detail || 'Voorraadverwerking kon niet worden opgeslagen.')
      const savedValue = normalizeHandling(data?.default_inventory_handling)
      setValue(savedValue)
      setStatusMessage('Wijziging verwerkt.')
      if (typeof onSaved === 'function') onSaved(savedValue)
    } catch (error) {
      setValue(previousValue)
      setErrorMessage(error?.message || 'Voorraadverwerking kon niet worden opgeslagen.')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div data-testid="article-inventory-handling-field">
      <div className="rz-field-row rz-field-row--editable">
        <label className="rz-field-row-label" htmlFor="article-inventory-handling">
          Standaard voorraadverwerking:
        </label>
        <div className="rz-field-row-value rz-field-row-value--editable">
          <select
            id="article-inventory-handling"
            className="rz-input rz-article-inline-input"
            value={value}
            onChange={handleChange}
            disabled={!canManage || isLoading || isSaving || !householdId || !householdArticleId}
            data-testid="article-inventory-handling-select"
          >
            {INVENTORY_HANDLING_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
          {!canManage ? (
            <div className="rz-article-overview-instruction" data-testid="article-inventory-handling-readonly">
              Alleen de beheerder kan de standaardvoorraadverwerking wijzigen.
            </div>
          ) : null}
          {statusMessage ? (
            <div className="rz-inline-feedback rz-inline-feedback--success" data-testid="article-inventory-handling-success">
              {statusMessage}
            </div>
          ) : null}
          {errorMessage ? (
            <div className="rz-article-detail-alert" data-testid="article-inventory-handling-error">
              {errorMessage}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  )
}
