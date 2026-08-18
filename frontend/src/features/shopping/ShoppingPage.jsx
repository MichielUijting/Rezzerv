import { useEffect, useMemo, useRef, useState } from 'react'
import AppShell from '../../app/AppShell.jsx'
import Card from '../../ui/Card.jsx'
import Button from '../../ui/Button.jsx'
import DataTable from '../../ui/DataTable.jsx'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'
import { fetchJsonWithAuth } from '../../lib/authSession.js'

const SOURCE_LABELS = {
  household_article: 'Huishoudartikel',
  product_type: 'Producttype',
  article_group: 'Artikelgroep',
}

const SOURCE_GROUPS = [
  ['household_article', 'Huishoudartikelen'],
  ['product_type', 'Producttypen'],
  ['article_group', 'Artikelgroepen'],
]

const CHECKBOX_STYLE = {
  accentColor: '#1A3E2B',
  width: 18,
  height: 18,
  margin: 0,
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

function filterOptions(items, field) {
  return [...new Set((items || []).map((item) => String(item?.[field] || '').trim()).filter(Boolean))]
    .sort((a, b) => a.localeCompare(b, 'nl'))
}

function csvValue(value) {
  return `"${String(value ?? '').replaceAll('"', '""')}"`
}

export default function ShoppingPage() {
  const { showFeedback } = useAppFeedback()
  const [list, setList] = useState({ items: [], item_count: 0 })
  const [catalogQuery, setCatalogQuery] = useState('')
  const [catalogResults, setCatalogResults] = useState([])
  const [selectedResultId, setSelectedResultId] = useState('')
  const [selectedItemIds, setSelectedItemIds] = useState([])
  const [filters, setFilters] = useState({ checked: 'all', article: '', productType: '' })
  const [sort, setSort] = useState({ key: 'article', direction: 'asc' })
  const [loading, setLoading] = useState(true)
  const [searching, setSearching] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
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

  const groupedResults = useMemo(
    () => SOURCE_GROUPS
      .map(([sourceType, label]) => ({
        sourceType,
        label,
        items: catalogResults.filter((item) => item.source_type === sourceType),
      }))
      .filter((group) => group.items.length > 0),
    [catalogResults],
  )

  const productTypeOptions = useMemo(() => filterOptions(list.items, 'product_type_name'), [list.items])

  const visibleItems = useMemo(() => (list.items || []).filter((item) => {
    if (filters.checked === 'checked' && !item.checked) return false
    if (filters.article && !String(item.article_name || '').toLowerCase().includes(filters.article.toLowerCase())) return false
    if (filters.productType && String(item.product_type_name || '') !== filters.productType) return false
    return true
  }), [list.items, filters])

  const selectedItems = useMemo(
    () => (list.items || []).filter((item) => selectedItemIds.includes(item.id)),
    [list.items, selectedItemIds],
  )

  const allVisibleSelected = visibleItems.length > 0
    && visibleItems.every((item) => selectedItemIds.includes(item.id))

  function toggleSelectedItem(itemId, selected) {
    setSelectedItemIds((current) => selected
      ? [...new Set([...current, itemId])]
      : current.filter((id) => id !== itemId))
  }

  function toggleAllVisible(selected) {
    const visibleIds = new Set(visibleItems.map((item) => item.id))
    setSelectedItemIds((current) => selected
      ? [...new Set([...current, ...visibleIds])]
      : current.filter((id) => !visibleIds.has(id)))
  }

  function patchListItem(itemId, patch) {
    setList((current) => ({
      ...current,
      items: (current.items || []).map((currentItem) => (
        currentItem.id === itemId ? { ...currentItem, ...patch } : currentItem
      )),
    }))
  }

  async function addSelectedResult() {
    if (!selectedResult) {
      setError('Selecteer eerst een zoekresultaat.')
      return
    }

    setSaving(true)
    setError('')
    setMessage('')
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
      setMessage(`${selectedResult.label} toegevoegd aan de winkellijst.`)
      setCatalogQuery('')
      setCatalogResults([])
      setSelectedResultId('')
      await loadList()
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
      await requestJson(`/api/shopping-list/items/${encodeURIComponent(item.id)}`, {
        method: 'PUT',
        body: JSON.stringify(patch),
      })
      await loadList()
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

    setError('')
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
          const latestVersion = checkedMutationVersionsRef.current.get(itemId)
          if (latestVersion === nextVersion) {
            setList((current) => ({
              ...current,
              items: (current.items || []).map((currentItem) => (
                currentItem.id === itemId && Boolean(currentItem.checked) === checked
                  ? { ...currentItem, checked: previousChecked }
                  : currentItem
              )),
            }))
            setError(saveError?.message || 'De koopstatus kon niet worden opgeslagen.')
          }
          throw saveError
        } finally {
          const latestVersion = checkedMutationVersionsRef.current.get(itemId)
          if (latestVersion === nextVersion) {
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
        setError('')
        setMessage('')
        try {
          await Promise.all(selectedItems.map((item) => requestJson(`/api/shopping-list/items/${encodeURIComponent(item.id)}`, { method: 'DELETE' })))
          setSelectedItemIds([])
          setMessage(count === 1 ? '1 rij verwijderd.' : `${count} rijen verwijderd.`)
          await loadList()
        } catch (deleteError) {
          await loadList()
          throw new Error(deleteError?.message || 'De geselecteerde rijen konden niet worden verwijderd.')
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
      ...selectedItems.map((item) => [item.article_name, item.product_type_name, item.size, item.note, item.checked ? 'Ja' : 'Nee']),
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
        setError('')
        setMessage('')
        try {
          await requestJson('/api/shopping-list/complete', { method: 'POST' })
          setSelectedItemIds([])
          setMessage('Winkelen is afgerond. De winkellijst is leeggemaakt.')
          await loadList()
        } catch (completeError) {
          throw new Error(completeError?.message || 'Winkelen kon niet worden afgerond.')
        } finally {
          setSaving(false)
        }
      },
    })
  }

  const inlineInputStyle = { width: '100%', minWidth: 0, boxSizing: 'border-box' }
  const dataTableFilters = {
    article: filters.article,
    productType: filters.productType,
    checked: filters.checked === 'checked' ? 'checked' : '',
  }
  const shoppingColumns = useMemo(() => [
    {
      key: 'select',
      header: <span aria-label="Bulkselectie">&nbsp;</span>,
      width: 60,
      headerStyle: { textAlign: 'center' },
      renderFilter: () => (
        <input
          type="checkbox"
          checked={allVisibleSelected}
          onChange={(event) => toggleAllVisible(event.target.checked)}
          aria-label="Selecteer alle zichtbare rijen"
          style={CHECKBOX_STYLE}
        />
      ),
      renderCell: (item) => (
        <div style={{ textAlign: 'center' }}>
          <input
            type="checkbox"
            checked={selectedItemIds.includes(item.id)}
            onChange={(event) => toggleSelectedItem(item.id, event.target.checked)}
            aria-label={`Selecteer ${item.article_name}`}
            style={CHECKBOX_STYLE}
          />
        </div>
      ),
    },
    {
      key: 'article',
      label: 'Artikel',
      width: 330,
      sortable: true,
      filterable: true,
      filterPlaceholder: 'Zoeken',
      filterLabel: 'Zoeken in winkellijst',
      getFilterValue: (item) => item.article_name || '',
      getSortValue: (item) => item.article_name || '',
      renderCell: (item) => <span title={item.article_name}>{item.article_name}</span>,
    },
    {
      key: 'productType',
      label: 'Producttype',
      width: 300,
      sortable: true,
      filterable: true,
      getFilterValue: (item) => item.product_type_name || '',
      filterPredicate: (item, value) => !value || String(item.product_type_name || '') === String(value),
      getSortValue: (item) => item.product_type_name || '',
      renderFilter: ({ value, onChange }) => (
        <select
          className="rz-input rz-inline-input"
          value={value || ''}
          onChange={(event) => onChange(event.target.value)}
          aria-label="Filter producttype"
        >
          <option value="">Filter</option>
          {productTypeOptions.map((option) => <option key={option} value={option}>{option}</option>)}
        </select>
      ),
      renderCell: (item) => <span title={item.product_type_name}>{item.product_type_name}</span>,
    },
    {
      key: 'size',
      label: 'Omvang',
      width: 120,
      sortable: true,
      getSortValue: (item) => item.size || '',
      renderCell: (item) => (
        <input
          className="rz-input"
          style={inlineInputStyle}
          defaultValue={item.size || ''}
          aria-label={`Omvang ${item.article_name}`}
          onBlur={(event) => updateItem(item, { size: event.target.value })}
        />
      ),
    },
    {
      key: 'note',
      label: 'Opmerking',
      width: 220,
      sortable: true,
      getSortValue: (item) => item.note || '',
      renderCell: (item) => (
        <input
          className="rz-input"
          style={inlineInputStyle}
          defaultValue={item.note || ''}
          aria-label={`Opmerking ${item.article_name}`}
          onBlur={(event) => updateItem(item, { note: event.target.value })}
        />
      ),
    },
    {
      key: 'checked',
      label: 'Gekocht',
      width: 90,
      sortable: true,
      filterable: true,
      headerStyle: { textAlign: 'center' },
      getFilterValue: (item) => item.checked ? 'checked' : 'unchecked',
      filterPredicate: (item, value) => !value || (value === 'checked' ? Boolean(item.checked) : !item.checked),
      getSortValue: (item) => Boolean(item.checked),
      renderFilter: ({ value, onChange }) => (
        <input
          type="checkbox"
          checked={value === 'checked'}
          onChange={(event) => onChange(event.target.checked ? 'checked' : '')}
          aria-label="Filter gekocht"
          style={CHECKBOX_STYLE}
        />
      ),
      renderCell: (item) => (
        <div style={{ textAlign: 'center' }}>
          <input
            type="checkbox"
            checked={Boolean(item.checked)}
            onChange={(event) => updateChecked(item, event.target.checked)}
            aria-label={`Gekocht ${item.article_name}`}
            style={CHECKBOX_STYLE}
          />
        </div>
      ),
    },
  ], [allVisibleSelected, productTypeOptions, selectedItemIds])

  function handleDataTableFilterChange(key, value) {
    if (key === 'article') {
      setFilters((current) => ({ ...current, article: value }))
      return
    }
    if (key === 'productType') {
      setFilters((current) => ({ ...current, productType: value }))
      return
    }
    if (key === 'checked') {
      setFilters((current) => ({ ...current, checked: value === 'checked' ? 'checked' : 'all' }))
    }
  }

  return (
    <AppShell title="Winkelen" showExit={false}>
      <div style={{ display: 'grid', gap: 18, width: '100%' }}>
        <Card>
          <div style={{ display: 'grid', gap: 18, width: '100%' }} data-testid="shopping-page">
            <h2 style={{ margin: 0 }}>Winkelen — {Number(list.item_count || 0)} artikelen</h2>

            <div style={{ display: 'grid', gridTemplateColumns: 'minmax(280px, 1fr) minmax(280px, 1fr) auto', gap: 12, alignItems: 'stretch' }}>
              <label className="rz-input-field">
                <span className="rz-label">Artikel toevoegen</span>
                <input
                  className="rz-input"
                  value={catalogQuery}
                  onChange={(event) => setCatalogQuery(event.target.value)}
                  placeholder="Zoek artikel, producttype of artikelgroep"
                  aria-label="Artikel toevoegen"
                />
              </label>

              <label className="rz-input-field">
                <span className="rz-label">Zoekresultaat</span>
                <select
                  className="rz-input"
                  value={selectedResultId}
                  onChange={(event) => setSelectedResultId(event.target.value)}
                  aria-label="Zoekresultaat"
                  disabled={searching || catalogResults.length === 0}
                >
                  <option value="">
                    {searching ? 'Zoeken‥' : catalogResults.length ? 'Selecteer resultaat' : 'Geen resultaten'}
                  </option>
                  {groupedResults.map((group) => (
                    <optgroup key={group.sourceType} label={group.label}>
                      {group.items.map((item) => (
                        <option
                          key={`${item.source_type}:${item.source_id}`}
                          value={`${item.source_type}:${item.source_id}`}
                        >
                          {item.label} — {SOURCE_LABELS[item.source_type] || item.source_type}
                        </option>
                      ))}
                    </optgroup>
                  ))}
                </select>
              </label>

              <Button
                type="button"
                onClick={addSelectedResult}
                disabled={saving || !selectedResult}
                style={{ alignSelf: 'end' }}
              >
                Toevoegen
              </Button>
            </div>

            {error ? <div role="alert" style={{ color: '#9b1c1c' }}>{error}</div> : null}
            {message ? <div role="status" style={{ color: '#1A3E2B' }}>{message}</div> : null}

            <DataTable
              columns={shoppingColumns}
              data={list.items || []}
              dataTestId="shopping-list-table"
              getRowKey={(item) => item.id}
              emptyMessage={loading ? 'Winkellijst laden…' : 'Nog geen artikelen op de winkellijst.'}
              filterState={dataTableFilters}
              onFilterChange={handleDataTableFilterChange}
              sortState={sort}
              onSortChange={setSort}
              stickyHeader
              stickyFilters
            />

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12 }}>
              <Button
                type="button"
                onClick={deleteSelectedItems}
                disabled={saving || selectedItems.length === 0}
              >
                Verwijderen
              </Button>
              <Button
                type="button"
                onClick={exportSelectedItems}
                disabled={selectedItems.length === 0}
              >
                Exporteren
              </Button>
            </div>
          </div>
        </Card>

        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <Button
            type="button"
            onClick={completeShopping}
            disabled={saving || Number(list.item_count || 0) === 0}
          >
            Winkelen afgerond
          </Button>
        </div>
      </div>
    </AppShell>
  )
}
