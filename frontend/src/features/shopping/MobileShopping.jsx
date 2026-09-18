import { useEffect, useMemo, useRef, useState } from 'react'
import Header from '../../ui/Header.jsx'
import Button from '../../ui/Button.jsx'
import Select from '../../ui/Select.jsx'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'
import { fetchJsonWithAuth } from '../../lib/authSession.js'
import '../../pages/mobileVoorraad.css'
import './mobileShopping.css'

const SOURCE_LABELS = {
  household_article: 'Huishoudartikel',
  product_type: 'Producttype',
  article_group: 'Artikelgroep',
}

async function requestJson(url, options = {}) {
  const response = await fetchJsonWithAuth(url, options)
  if (response.status === 204) return null
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = typeof payload?.detail === 'string' ? payload.detail : 'Verzoek mislukt'
    throw new Error(detail)
  }
  return payload
}

function normalizeText(value) {
  return String(value || '').trim().toLowerCase()
}

function csvValue(value) {
  return `"${String(value ?? '').replaceAll('"', '""')}"`
}

function articleGroupLabel(item) {
  return String(item?.article_group_name || '').trim() || 'Niet ingedeeld'
}

function productTypeLabel(item) {
  return String(item?.product_type_name || '').trim()
}

export default function MobileShopping() {
  const { showFeedback } = useAppFeedback()
  const [list, setList] = useState({ items: [], item_count: 0 })
  const [catalogQuery, setCatalogQuery] = useState('')
  const [catalogResults, setCatalogResults] = useState([])
  const [selectedResultId, setSelectedResultId] = useState('')
  const [listQuery, setListQuery] = useState('')
  const [productTypeFilter, setProductTypeFilter] = useState('')
  const [sortKey, setSortKey] = useState('articleGroup')
  const [selectedItemIds, setSelectedItemIds] = useState([])
  const [editingItemId, setEditingItemId] = useState('')
  const [loading, setLoading] = useState(true)
  const [searching, setSearching] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const checkedSaveChainsRef = useRef(new Map())
  const checkedMutationVersionsRef = useRef(new Map())

  async function loadList() {
    setLoading(true)
    setError('')
    try {
      const payload = await requestJson('/api/shopping-list')
      setList(payload)
      const existingIds = new Set((payload.items || []).map((item) => item.id))
      setSelectedItemIds((current) => current.filter((id) => existingIds.has(id)))
      setEditingItemId((current) => existingIds.has(current) ? current : '')
    } catch (loadError) {
      setError(loadError?.message || 'Winkellijst kon niet worden geladen.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadList() }, [])

  useEffect(() => {
    const query = catalogQuery.trim()
    setSelectedResultId('')
    if (query.length < 2) {
      setCatalogResults([])
      return undefined
    }

    const timer = window.setTimeout(async () => {
      setSearching(true)
      setError('')
      try {
        const payload = await requestJson(`/api/shopping-list/catalog-search?scope=all&query=${encodeURIComponent(query)}`)
        setCatalogResults(Array.isArray(payload?.items) ? payload.items : [])
      } catch (searchError) {
        setCatalogResults([])
        setError(searchError?.message || 'Artikelen konden niet worden doorzocht.')
      } finally {
        setSearching(false)
      }
    }, 250)

    return () => window.clearTimeout(timer)
  }, [catalogQuery])

  const selectedResult = useMemo(
    () => catalogResults.find((item) => `${item.source_type}:${item.source_id}` === selectedResultId) || null,
    [catalogResults, selectedResultId],
  )

  const resultOptions = useMemo(() => [
    {
      value: '',
      label: searching
        ? 'Zoeken…'
        : catalogResults.length > 0
          ? 'Selecteer resultaat'
          : 'Geen resultaten',
      disabled: true,
    },
    ...catalogResults.map((item) => ({
      value: `${item.source_type}:${item.source_id}`,
      label: `${item.label} — ${SOURCE_LABELS[item.source_type] || item.source_type}`,
    })),
  ], [catalogResults, searching])

  const productTypeOptions = useMemo(
    () => [...new Set((list.items || []).map(productTypeLabel).filter(Boolean))]
      .sort((a, b) => a.localeCompare(b, 'nl')),
    [list.items],
  )

  const filteredItems = useMemo(() => {
    const needle = normalizeText(listQuery)
    const rows = (list.items || []).filter((item) => {
      if (productTypeFilter && productTypeLabel(item) !== productTypeFilter) return false
      if (!needle) return true
      return [
        item.article_name,
        item.article_group_name,
        item.product_type_name,
        item.size,
        item.note,
      ].some((value) => normalizeText(value).includes(needle))
    })

    return rows.sort((a, b) => {
      if (sortKey === 'productType') {
        return productTypeLabel(a).localeCompare(productTypeLabel(b), 'nl')
          || String(a.article_name || '').localeCompare(String(b.article_name || ''), 'nl')
      }
      if (sortKey === 'status') {
        return Number(Boolean(a.checked)) - Number(Boolean(b.checked))
          || String(a.article_name || '').localeCompare(String(b.article_name || ''), 'nl')
      }
      if (sortKey === 'articleGroup') {
        return articleGroupLabel(a).localeCompare(articleGroupLabel(b), 'nl')
          || String(a.article_name || '').localeCompare(String(b.article_name || ''), 'nl')
      }
      return String(a.article_name || '').localeCompare(String(b.article_name || ''), 'nl')
    })
  }, [list.items, listQuery, productTypeFilter, sortKey])

  const groupedItems = useMemo(() => {
    if (sortKey !== 'articleGroup') return [{ label: 'Winkellijst', items: filteredItems }]
    const groups = new Map()
    filteredItems.forEach((item) => {
      const label = articleGroupLabel(item)
      if (!groups.has(label)) groups.set(label, [])
      groups.get(label).push(item)
    })
    return [...groups.entries()].map(([label, items]) => ({ label, items }))
  }, [filteredItems, sortKey])

  const selectedItems = useMemo(
    () => (list.items || []).filter((item) => selectedItemIds.includes(item.id)),
    [list.items, selectedItemIds],
  )
  const remainingCount = useMemo(
    () => (list.items || []).filter((item) => !item.checked).length,
    [list.items],
  )
  const hasActiveFilters = Boolean(listQuery || productTypeFilter || sortKey !== 'articleGroup')

  function patchListItem(itemId, patch) {
    setList((current) => ({
      ...current,
      items: (current.items || []).map((item) => item.id === itemId ? { ...item, ...patch } : item),
    }))
  }

  function clearFilters() {
    setListQuery('')
    setProductTypeFilter('')
    setSortKey('articleGroup')
  }

  function toggleSelectedItem(itemId, selected) {
    setSelectedItemIds((current) => selected
      ? [...new Set([...current, itemId])]
      : current.filter((id) => id !== itemId))
  }

  async function addSelectedResult() {
    if (!selectedResult) return
    setSaving(true)
    setError('')
    try {
      await requestJson('/api/shopping-list/items', {
        method: 'POST',
        body: JSON.stringify({
          article_name: selectedResult.article_name || selectedResult.label,
          article_group_name: selectedResult.article_group_name || '',
          product_type_name: selectedResult.product_type_name || '',
          source_type: selectedResult.source_type,
          source_id: selectedResult.source_id,
        }),
      })
      const addedLabel = selectedResult.label
      setCatalogQuery('')
      setCatalogResults([])
      setSelectedResultId('')
      await loadList()
      showFeedback({
        variant: 'success',
        title: 'Toegevoegd',
        message: `${addedLabel} staat op de winkellijst.`,
      })
    } catch (saveError) {
      setError(saveError?.message || 'Het geselecteerde resultaat kon niet worden toegevoegd.')
    } finally {
      setSaving(false)
    }
  }

  async function updateItem(item, patch) {
    setSaving(true)
    setError('')
    try {
      const updated = await requestJson(`/api/shopping-list/items/${encodeURIComponent(item.id)}`, {
        method: 'PUT',
        body: JSON.stringify(patch),
      })
      if (updated) patchListItem(item.id, updated)
    } catch (saveError) {
      setError(saveError?.message || 'Winkellijstregel kon niet worden bijgewerkt.')
      await loadList()
    } finally {
      setSaving(false)
    }
  }

  function updateChecked(item, checked) {
    const itemId = item.id
    const previousChecked = Boolean(item.checked)
    const nextVersion = (checkedMutationVersionsRef.current.get(itemId) || 0) + 1
    checkedMutationVersionsRef.current.set(itemId, nextVersion)
    patchListItem(itemId, { checked })

    const previousChain = checkedSaveChainsRef.current.get(itemId) || Promise.resolve()
    const nextChain = previousChain
      .catch(() => undefined)
      .then(async () => {
        try {
          await requestJson(`/api/shopping-list/items/${encodeURIComponent(itemId)}`, {
            method: 'PUT',
            body: JSON.stringify({ checked }),
          })
        } catch (saveError) {
          if (checkedMutationVersionsRef.current.get(itemId) === nextVersion) {
            patchListItem(itemId, { checked: previousChecked })
            setError(saveError?.message || 'De koopstatus kon niet worden opgeslagen.')
          }
          throw saveError
        } finally {
          if (checkedMutationVersionsRef.current.get(itemId) === nextVersion) {
            checkedSaveChainsRef.current.delete(itemId)
          }
        }
      })

    checkedSaveChainsRef.current.set(itemId, nextChain)
    void nextChain.catch(() => undefined)
  }

  function deleteSelectedItems() {
    if (selectedItems.length === 0) return
    const count = selectedItems.length
    showFeedback({
      variant: 'warning',
      title: count === 1 ? 'Rij verwijderen' : 'Rijen verwijderen',
      message: count === 1 ? '1 geselecteerde rij verwijderen?' : `${count} geselecteerde rijen verwijderen?`,
      detail: 'De geselecteerde regels verdwijnen uit de actuele winkellijst.',
      testId: 'shopping-delete-confirmation',
      primaryActionLabel: 'Verwijderen',
      secondaryActionLabel: 'Annuleren',
      onPrimaryAction: async () => {
        setSaving(true)
        try {
          await Promise.all(selectedItems.map((item) => requestJson(
            `/api/shopping-list/items/${encodeURIComponent(item.id)}`,
            { method: 'DELETE' },
          )))
          setSelectedItemIds([])
          await loadList()
          showFeedback({
            variant: 'success',
            title: 'Verwijderd',
            message: count === 1 ? '1 rij verwijderd.' : `${count} rijen verwijderd.`,
          })
        } finally {
          setSaving(false)
        }
      },
    })
  }

  function exportSelectedItems() {
    if (selectedItems.length === 0) return
    const rows = [
      ['Artikel', 'Producttype', 'Omvang', 'Opmerking', 'Gekocht'],
      ...selectedItems.map((item) => [
        item.article_name,
        item.product_type_name,
        item.size,
        item.note,
        item.checked ? 'Ja' : 'Nee',
      ]),
    ]
    const csv = `\uFEFF${rows.map((row) => row.map(csvValue).join(';')).join('\r\n')}`
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'winkelen-geselecteerde-rijen.csv'
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  }

  function completeShopping() {
    showFeedback({
      variant: 'warning',
      title: 'Winkelen afronden',
      message: 'De actuele winkellijst wordt leeggemaakt.',
      detail: 'Voorraad en bronlijsten blijven ongewijzigd.',
      testId: 'shopping-complete-confirmation',
      primaryActionLabel: 'Afronden',
      secondaryActionLabel: 'Annuleren',
      onPrimaryAction: async () => {
        setSaving(true)
        try {
          await requestJson('/api/shopping-list/complete', { method: 'POST' })
          setSelectedItemIds([])
          setEditingItemId('')
          await loadList()
          showFeedback({
            variant: 'success',
            title: 'Winkelen afgerond',
            message: 'De winkellijst is leeggemaakt.',
          })
        } finally {
          setSaving(false)
        }
      },
    })
  }

  return (
    <div className="rz-screen rz-mobile-inventory-screen rz-mobile-shopping-screen" data-testid="mobile-shopping-page">
      <Header title="Winkelen" />
      <main className="rz-mobile-inventory-content rz-mobile-shopping-content">
        <section className="rz-mobile-shopping-summary-card" aria-label="Mijn winkellijst">
          <div>
            <div className="rz-mobile-shopping-summary-title">Mijn lijst</div>
            <div className="rz-mobile-shopping-summary-meta">
              {loading ? 'Winkellijst laden…' : `${Number(list.item_count || 0)} artikelen • ${remainingCount} nog te kopen`}
            </div>
          </div>
          <span className="rz-mobile-shopping-count" aria-label={`${remainingCount} nog te kopen`}>
            {remainingCount}
          </span>
        </section>

        <section className="rz-mobile-inventory-toolbar rz-mobile-shopping-toolbar" aria-label="Winkelen zoeken en filteren">
          <div className="rz-mobile-shopping-toolbar-title">Artikel toevoegen</div>
          <label className="rz-mobile-inventory-field rz-mobile-inventory-search">
            <span className="rz-mobile-inventory-label">Catalogus zoeken</span>
            <input
              className="rz-input"
              type="search"
              value={catalogQuery}
              onChange={(event) => setCatalogQuery(event.target.value)}
              placeholder="Zoek artikel, producttype of artikelgroep"
              aria-label="Artikel toevoegen"
              autoComplete="off"
            />
          </label>

          <div className="rz-mobile-shopping-add-row">
            <div className="rz-mobile-inventory-field">
              <span id="mobile-shopping-result-label" className="rz-mobile-inventory-label">Zoekresultaat</span>
              <Select
                ariaLabelledby="mobile-shopping-result-label"
                value={selectedResultId}
                onChange={setSelectedResultId}
                options={resultOptions}
                disabled={searching || catalogResults.length === 0}
                dataTestId="mobile-shopping-result"
              />
            </div>
            <Button
              type="button"
              variant="primary"
              onClick={addSelectedResult}
              disabled={saving || !selectedResult}
              data-testid="mobile-shopping-add"
            >
              Toevoegen
            </Button>
          </div>

          <div className="rz-mobile-shopping-divider" />

          <label className="rz-mobile-inventory-field rz-mobile-inventory-search">
            <span className="rz-mobile-inventory-label">Zoek in lijst</span>
            <input
              className="rz-input"
              type="search"
              value={listQuery}
              onChange={(event) => setListQuery(event.target.value)}
              placeholder="Zoek in je winkellijst"
              aria-label="Zoek in winkellijst"
              autoComplete="off"
            />
          </label>

          <div className="rz-mobile-shopping-filter-grid">
            <div className="rz-mobile-inventory-field">
              <span id="mobile-shopping-producttype-label" className="rz-mobile-inventory-label">Producttype</span>
              <Select
                ariaLabelledby="mobile-shopping-producttype-label"
                value={productTypeFilter}
                onChange={setProductTypeFilter}
                options={[
                  { value: '', label: 'Alle producttypen' },
                  ...productTypeOptions.map((option) => ({ value: option, label: option })),
                ]}
                dataTestId="mobile-shopping-producttype"
              />
            </div>
            <div className="rz-mobile-inventory-field">
              <span id="mobile-shopping-sort-label" className="rz-mobile-inventory-label">Sorteren</span>
              <Select
                ariaLabelledby="mobile-shopping-sort-label"
                value={sortKey}
                onChange={setSortKey}
                options={[
                  { value: 'articleGroup', label: 'Artikelgroep' },
                  { value: 'name', label: 'Naam A–Z' },
                  { value: 'productType', label: 'Producttype A–Z' },
                  { value: 'status', label: 'Nog te kopen eerst' },
                ]}
                dataTestId="mobile-shopping-sort"
              />
            </div>
          </div>

          {hasActiveFilters ? (
            <Button type="button" variant="secondary" className="rz-mobile-shopping-clear" onClick={clearFilters}>
              Filters wissen
            </Button>
          ) : null}
        </section>

        {error ? (
          <section className="rz-mobile-inventory-state rz-mobile-inventory-state--error" role="alert">
            <div>{error}</div>
            <Button type="button" variant="secondary" onClick={loadList}>Opnieuw proberen</Button>
          </section>
        ) : null}

        {!error && !loading && filteredItems.length === 0 ? (
          <section className="rz-mobile-inventory-state">
            <strong>{(list.items || []).length === 0 ? 'Nog geen artikelen op de winkellijst.' : 'Geen artikelen gevonden.'}</strong>
            {hasActiveFilters ? <span>Pas je zoekopdracht of filters aan.</span> : null}
          </section>
        ) : null}

        {!error && filteredItems.length > 0 ? (
          <div className="rz-mobile-shopping-groups" aria-label="Winkellijst">
            {groupedItems.map((group) => (
              <section className="rz-mobile-shopping-group" key={group.label}>
                <div className="rz-mobile-shopping-group-header">
                  <div className="rz-mobile-shopping-group-title">{group.label}</div>
                  <span>{group.items.length} {group.items.length === 1 ? 'artikel' : 'artikelen'}</span>
                </div>

                <div className="rz-mobile-shopping-list">
                  {group.items.map((item) => {
                    const editing = editingItemId === item.id
                    return (
                      <article
                        key={item.id}
                        className={`rz-mobile-shopping-card${item.checked ? ' rz-mobile-shopping-card--checked' : ''}`}
                        data-testid={`mobile-shopping-item-${item.id}`}
                      >
                        <label className="rz-mobile-shopping-buy-check">
                          <input
                            type="checkbox"
                            checked={Boolean(item.checked)}
                            onChange={(event) => updateChecked(item, event.target.checked)}
                            aria-label={`Gekocht ${item.article_name}`}
                          />
                          <span>{item.checked ? 'Gekocht' : 'Nog te kopen'}</span>
                        </label>

                        <div className="rz-mobile-shopping-card-main">
                          <div className="rz-mobile-shopping-card-title">{item.article_name}</div>
                          {productTypeLabel(item) ? (
                            <div className="rz-mobile-shopping-card-product">{productTypeLabel(item)}</div>
                          ) : null}
                          <div className="rz-mobile-shopping-card-meta">
                            <span>{articleGroupLabel(item)}</span>
                            {item.size ? <span>{item.size}</span> : null}
                            {item.note ? <span>{item.note}</span> : null}
                          </div>
                        </div>

                        <div className="rz-mobile-shopping-card-actions">
                          <button
                            type="button"
                            className="rz-mobile-shopping-edit"
                            onClick={() => setEditingItemId(editing ? '' : item.id)}
                            aria-expanded={editing}
                            aria-controls={`mobile-shopping-editor-${item.id}`}
                          >
                            {editing ? 'Sluiten' : 'Bewerken'}
                          </button>
                          <label className="rz-mobile-shopping-select">
                            <input
                              type="checkbox"
                              checked={selectedItemIds.includes(item.id)}
                              onChange={(event) => toggleSelectedItem(item.id, event.target.checked)}
                              aria-label={`Selecteer ${item.article_name}`}
                            />
                            <span>Selecteer</span>
                          </label>
                        </div>

                        {editing ? (
                          <div className="rz-mobile-shopping-editor" id={`mobile-shopping-editor-${item.id}`}>
                            <label className="rz-mobile-inventory-field">
                              <span className="rz-mobile-inventory-label">Omvang</span>
                              <input
                                className="rz-input"
                                defaultValue={item.size || ''}
                                aria-label={`Omvang ${item.article_name}`}
                                onBlur={(event) => updateItem(item, { size: event.target.value })}
                              />
                            </label>
                            <label className="rz-mobile-inventory-field">
                              <span className="rz-mobile-inventory-label">Opmerking</span>
                              <input
                                className="rz-input"
                                defaultValue={item.note || ''}
                                aria-label={`Opmerking ${item.article_name}`}
                                onBlur={(event) => updateItem(item, { note: event.target.value })}
                              />
                            </label>
                          </div>
                        ) : null}
                      </article>
                    )
                  })}
                </div>
              </section>
            ))}
          </div>
        ) : null}

        {selectedItems.length > 0 ? (
          <section className="rz-mobile-shopping-selection-actions" aria-label="Geselecteerde regels">
            <span>{selectedItems.length} geselecteerd</span>
            <div>
              <Button type="button" variant="secondary" onClick={exportSelectedItems}>Exporteren</Button>
              <Button type="button" variant="secondary" onClick={deleteSelectedItems} disabled={saving}>Verwijderen</Button>
            </div>
          </section>
        ) : null}

        <div className="rz-mobile-shopping-complete">
          <Button
            type="button"
            variant="primary"
            onClick={completeShopping}
            disabled={saving || Number(list.item_count || 0) === 0}
            data-testid="mobile-shopping-complete"
          >
            Winkelen afgerond
          </Button>
        </div>
      </main>
    </div>
  )
}
