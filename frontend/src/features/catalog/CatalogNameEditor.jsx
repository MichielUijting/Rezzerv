import { useEffect, useState } from 'react'
import { fetchJsonWithAuth } from '../../lib/authSession'

/** One central name editor for both Catalogus detail layouts. */
export default function CatalogNameEditor({ globalProductId, name, canEdit, onSaved }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(name || '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    setDraft(name || '')
    setEditing(false)
    setError('')
  }, [globalProductId, name])

  function cancel() {
    setEditing(false)
    setDraft(name || '')
    setError('')
  }

  async function save(event) {
    event.preventDefault()
    if (saving) return
    const normalized = String(draft || '').trim().replace(/\s+/g, ' ')
    const previous = String(name || '').trim()
    if (!normalized || normalized.length > 200) {
      setError('Vul een artikelnaam in van maximaal 200 tekens.')
      return
    }
    if (normalized === previous) {
      cancel()
      return
    }
    setSaving(true)
    setError('')
    try {
      const response = await fetchJsonWithAuth(
        `/api/catalog/${encodeURIComponent(globalProductId)}/name`,
        {
          method: 'PUT',
          body: JSON.stringify({ name: normalized, expected_name: previous }),
        },
      )
      const result = await response.json().catch(() => ({}))
      if (!response.ok) {
        const detail = result?.detail
        throw new Error(typeof detail === 'string' ? detail : 'De artikelnaam kon niet worden opgeslagen.')
      }
      onSaved(String(result.name || normalized))
      setEditing(false)
    } catch (saveError) {
      setError(saveError?.message || 'De artikelnaam kon niet worden opgeslagen.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="rz-catalog-name-editor" data-testid="catalog-shared-name-editor">
      <div className="rz-catalog-name-editor-heading">
        <h2 data-testid="catalog-shared-product-name">{String(name || '').trim() || 'Universeel artikel'}</h2>
        {canEdit && !editing ? (
          <button type="button" className="rz-button-secondary" onClick={() => setEditing(true)} data-testid="catalog-shared-name-edit">
            Naam wijzigen
          </button>
        ) : null}
      </div>
      {editing && canEdit ? (
        <form className="rz-catalog-name-editor-form" onSubmit={save} data-testid="catalog-shared-name-form">
          <label htmlFor="catalog-shared-name-input">Nieuwe universele artikelnaam</label>
          <input
            id="catalog-shared-name-input"
            className="rz-input"
            type="text"
            value={draft}
            maxLength={200}
            autoFocus
            disabled={saving}
            onChange={(event) => { setDraft(event.target.value); setError('') }}
            data-testid="catalog-shared-name-input"
          />
          <p>De naam wordt in de Catalogus voor alle huishoudens aangepast. Barcode en voorraad blijven behouden.</p>
          <div className="rz-catalog-name-editor-actions">
            <button type="button" className="rz-button-secondary" onClick={cancel} disabled={saving}>
              Annuleren
            </button>
            <button type="submit" className="rz-button-primary" disabled={saving || !String(draft).trim()} data-testid="catalog-shared-name-save">
              {saving ? 'Opslaan…' : 'Opslaan'}
            </button>
          </div>
        </form>
      ) : null}
      {error ? <p className="rz-inline-feedback rz-inline-feedback--error" role="alert">{error}</p> : null}
    </div>
  )
}
