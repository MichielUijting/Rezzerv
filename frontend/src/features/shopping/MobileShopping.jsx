import { useEffect, useMemo, useRef, useState } from 'react'
import Button from '../../ui/Button.jsx'
import SearchCandidateList from '../../ui/SearchCandidateList.jsx'
import MobileArticleRow from '../../ui/MobileArticleRow.jsx'
import MobileModuleHeader from '../../ui/MobileModuleHeader.jsx'
import QuantityStepper from '../../ui/QuantityStepper.jsx'
import Select from '../../ui/Select.jsx'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'
import { fetchJsonWithAuth, readStoredAuthContext } from '../../lib/authSession.js'
import {
  SHOPPING_SEARCH_MODE_OPTIONS,
  combineShoppingSearchResults,
  readShoppingSearchModePreference,
  shoppingSearchScopes,
  writeShoppingSearchModePreference,
} from './shoppingSearchMode.js'
import '../../pages/mobileVoorraad.css'
import './mobileShopping.css'

const SOURCE_LABELS = {
  household_article: 'Huishoudartikel',
  global_product: 'Exact Catalogusproduct',
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

function quantityValue(item) {
  const value = Number(item?.quantity ?? 1)
  return Number.isFinite(value) && value > 0 ? value : 1
}

export default function MobileShopping() {
  const { showFeedback } = useAppFeedback()
  const [list, setList] = useState({ items: [], item_count: 0 })
  const [catalogQuery, setCatalogQuery] = useState('')
  const [catalogResults, setCatalogResults] = useState([])
  const [selectedResultId, setSelectedResultId] = useState('')
  const [searchMode, setSearchMode] = useState(() => readShoppingSearchModePreference(readStoredAuthContext()))
  const [selectedItemIds, setSelectedItemIds] = useState([])
  const [loading, setLoading] = useState(true)
  const [searching, setSearching] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const catalogSearchRequestRef = useRef(0)

  async function loadList() {
    setLoading(true)
    setError('')
    try {
      const payload = await requestJson('/api/shopping-list')
      setList(payload)
      const existingIds = new Set((payload.items || []).map((item) => item.id))
      setSelectedItemIds((current) => current.filter((id) => existingIds.has(id)))
    } catch (loadError) {
      setError(loadError?.message || 'Boodschappen konden niet worden geladen.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadList() }, [])

  function updateCatalogQuery(value) {
    catalogSearchRequestRef.current += 1
    setCatalogQuery(value)
    setCatalogResults([])
    setSelectedResultId('')
    setSearching(false)
  }

  useEffect(() => {
    const query = catalogQuery.trim()
    const requestId = catalogSearchRequestRef.current
    let cancelled = false
    setSelectedResultId('')

    if (query.length < 2) {
      setCatalogResults([])
      return () => { cancelled = true }
    }

    const timer = window.setTimeout(async () => {
      if (cancelled || catalogSearchRequestRef.current !== requestId) return
      setSearching(true)
      setError('')
      try {
        const payloads = await Promise.all(shoppingSearchScopes(searchMode).map((scope) => requestJson(
          `/api/shopping-list/catalog-search?scope=${scope}&query=${encodeURIComponent(query)}&limit=5`,
        )))
        if (cancelled || catalogSearchRequestRef.current !== requestId) return
        setCatalogResults(combineShoppingSearchResults(payloads, 5))
      } catch (searchError) {
        if (cancelled || catalogSearchRequestRef.current !== requestId) return
        setCatalogResults([])
        setError(searchError?.message || 'Artikelen konden niet worden doorzocht.')
      } finally {
        if (!cancelled && catalogSearchRequestRef.current === requestId) setSearching(false)
      }
    }, 250)

    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [catalogQuery, searchMode])

  function updateSearchMode(value) {
    const nextMode = writeShoppingSearchModePreference(value, readStoredAuthContext())
    catalogSearchRequestRef.current += 1
    setSearchMode(nextMode)
    setCatalogResults([])
    setSelectedResultId('')
    setSearching(false)
  }

  const selectedResult = useMemo(
    () => catalogResults.find((item) => `${item.source_type}:${item.source_id}` === selectedResultId) || null,
    [catalogResults, selectedResultId],
  )

  const toBuyItems = useMemo(
    () => (list.items || []).filter((item) => !item.checked),
    [list.items],
  )
  const cartItems = useMemo(
    () => (list.items || []).filter((item) => item.checked),
    [list.items],
  )
  const selectedToBuyItems = useMemo(
    () => toBuyItems.filter((item) => selectedItemIds.includes(item.id)),
    [selectedItemIds, toBuyItems],
  )
  const selectedCartItems = useMemo(
    () => cartItems.filter((item) => selectedItemIds.includes(item.id)),
    [cartItems, selectedItemIds],
  )

  function patchListItem(itemId, patch) {
    setList((current) => ({
      ...current,
      items: (current.items || []).map((item) => item.id === itemId ? { ...item, ...patch } : item),
    }))
  }

  function toggleSelectedItem(itemId, selected) {
    setSelectedItemIds((current) => selected
      ? [...new Set([...current, itemId])]
      : current.filter((id) => id !== itemId))
  }

  function clearSectionSelection(items) {
    const ids = new Set(items.map((item) => item.id))
    setSelectedItemIds((current) => current.filter((id) => !ids.has(id)))
  }

  async function addArticle() {
    const manualName = catalogQuery.trim()
    if (!selectedResult && !manualName) return
    const payload = selectedResult ? {
      article_name: selectedResult.article_name || selectedResult.label,
      article_group_name: selectedResult.article_group_name || '',
      product_type_name: selectedResult.product_type_name || '',
      source_type: selectedResult.source_type,
      source_id: selectedResult.source_id,
    } : {
      article_name: manualName,
      source_type: 'manual',
      source_id: '',
      quantity: 1,
    }
    const addedLabel = selectedResult?.label || manualName
    setSaving(true)
    setError('')
    try {
      await requestJson('/api/shopping-list/items', { method: 'POST', body: JSON.stringify(payload) })
      updateCatalogQuery('')
      await loadList()
      showFeedback({ variant: 'success', title: 'Toegevoegd', message: `${addedLabel} staat bij Boodschappen.` })
    } catch (saveError) {
      setError(saveError?.message || 'Het artikel kon niet worden toegevoegd.')
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
      setError(saveError?.message || 'Boodschappenregel kon niet worden bijgewerkt.')
      await loadList()
    } finally {
      setSaving(false)
    }
  }

  async function setPurchasedForItems(items, checked) {
    if (!items.length) return
    setSaving(true)
    setError('')
    try {
      await Promise.all(items.map((item) => requestJson(
        `/api/shopping-list/items/${encodeURIComponent(item.id)}`,
        { method: 'PUT', body: JSON.stringify({ checked }) },
      )))
      clearSectionSelection(items)
      await loadList()
    } catch (saveError) {
      setError(saveError?.message || 'De winkelwagenstatus kon niet worden opgeslagen.')
      await loadList()
    } finally {
      setSaving(false)
    }
  }

  function deleteSelectedItems(items) {
    if (!items.length) return
    const count = items.length
    showFeedback({
      variant: 'warning',
      title: count === 1 ? 'Artikel verwijderen' : 'Artikelen verwijderen',
      message: count === 1 ? '1 geselecteerd artikel verwijderen?' : `${count} geselecteerde artikelen verwijderen?`,
      detail: 'De geselecteerde artikelen verdwijnen uit de actuele boodschappen.',
      testId: 'shopping-delete-confirmation',
      primaryActionLabel: 'Verwijderen',
      secondaryActionLabel: 'Annuleren',
      onPrimaryAction: async () => {
        setSaving(true)
        try {
          await Promise.all(items.map((item) => requestJson(
            `/api/shopping-list/items/${encodeURIComponent(item.id)}`,
            { method: 'DELETE' },
          )))
          clearSectionSelection(items)
          await loadList()
          showFeedback({
            variant: 'success',
            title: 'Verwijderd',
            message: count === 1 ? '1 artikel verwijderd.' : `${count} artikelen verwijderd.`,
          })
        } finally {
          setSaving(false)
        }
      },
    })
  }

  function completeShopping() {
    showFeedback({
      variant: 'warning',
      title: 'Boodschappen afronden',
      message: 'De actuele boodschappen worden leeggemaakt.',
      detail: 'Voorraad en bronlijsten blijven ongewijzigd.',
      testId: 'shopping-complete-confirmation',
      primaryActionLabel: 'Afronden',
      secondaryActionLabel: 'Annuleren',
      onPrimaryAction: async () => {
        setSaving(true)
        try {
          await requestJson('/api/shopping-list/complete', { method: 'POST' })
          setSelectedItemIds([])
          await loadList()
          showFeedback({ variant: 'success', title: 'Boodschappen afgerond', message: 'Boodschappen zijn leeggemaakt.' })
        } finally {
          setSaving(false)
        }
      },
    })
  }

  function renderShoppingRow(item) {
    return (
      <MobileArticleRow
        key={item.id}
        title={item.article_name}
        subtitle=""
        meta={[]}
        imageUrl={item.image_url}
        imageProductName={item.article_name}
        checked={Boolean(item.checked)}
        testId={`mobile-shopping-item-${item.id}`}
        leading={(
          <input
            type="checkbox"
            checked={selectedItemIds.includes(item.id)}
            onChange={(event) => toggleSelectedItem(item.id, event.target.checked)}
            aria-label={`Selecteer ${item.article_name}`}
          />
        )}
        side={(
          <QuantityStepper
            value={String(quantityValue(item))}
            decreaseDisabled={saving || quantityValue(item) <= 1}
            increaseDisabled={saving}
            decreaseLabel={`Verlaag aantal van ${item.article_name}`}
            increaseLabel={`Verhoog aantal van ${item.article_name}`}
            valueLabel={`Aantal ${quantityValue(item)}`}
            valueEditable={false}
            testIdPrefix={`mobile-shopping-quantity-${item.id}`}
            onDecrease={(event) => { event.stopPropagation(); updateItem(item, { quantity: quantityValue(item) - 1 }) }}
            onIncrease={(event) => { event.stopPropagation(); updateItem(item, { quantity: quantityValue(item) + 1 }) }}
          />
        )}
      />
    )
  }

  return (
    <div className="rz-screen rz-mobile-inventory-screen rz-mobile-shopping-screen" data-testid="mobile-shopping-page">
      <MobileModuleHeader title="Boodschappen" testId="mobile-shopping-header" />
      <main className="rz-mobile-inventory-content rz-mobile-shopping-content">
        <section className="rz-mobile-inventory-toolbar rz-mobile-shopping-toolbar" aria-label="Artikel toevoegen">
          <div className="rz-mobile-shopping-toolbar-title">Artikel toevoegen</div>

          <label className="rz-mobile-inventory-field rz-mobile-inventory-search">
            <span className="rz-mobile-inventory-label">Zoek of typ een artikel</span>
            <input
              className="rz-input"
              type="search"
              value={catalogQuery}
              disabled={saving}
              onChange={(event) => updateCatalogQuery(event.target.value)}
              placeholder="Zoek in de catalogus of voer zelf een naam in"
              aria-label="Artikel toevoegen"
              aria-controls="mobile-shopping-candidate-list"
              aria-expanded={catalogResults.length > 0}
              autoComplete="off"
            />
          </label>
          <SearchCandidateList
            items={catalogResults}
            selectedKey={selectedResultId}
            getKey={(item) => `${item.source_type}:${item.source_id}`}
            getLabel={(item) => `${item.label} — ${SOURCE_LABELS[item.source_type] || item.source_type}`}
            onSelect={setSelectedResultId}
            loading={searching}
            ariaLabel="Kandidaten voor artikel toevoegen"
            dataTestId="mobile-shopping-candidate-list"
          />

          <div className="rz-mobile-inventory-field">
            <span className="rz-mobile-inventory-label" id="mobile-shopping-search-mode-label">Zoekwijze</span>
            <Select
              value={searchMode}
              options={SHOPPING_SEARCH_MODE_OPTIONS}
              disabled={saving}
              onChange={updateSearchMode}
              ariaLabelledby="mobile-shopping-search-mode-label"
              ariaLabel="Zoekwijze specifiek of generiek"
              dataTestId="mobile-shopping-search-mode"
            />
          </div>

          <Button type="button" variant="primary" onClick={addArticle} disabled={saving || (!selectedResult && !catalogQuery.trim())} data-testid="mobile-shopping-add">
            Toevoegen
          </Button>
        </section>

        <section className="rz-mobile-shopping-summary-card" aria-label="Mijn boodschappen">
          <div>
            <div className="rz-mobile-shopping-summary-title">Mijn boodschappen</div>
            <div className="rz-mobile-shopping-summary-meta">
              {loading ? 'Boodschappen laden…' : `${Number(list.item_count || 0)} artikelen • ${toBuyItems.length} nog te kopen • ${cartItems.length} in winkelwagen`}
            </div>
          </div>
          <span className="rz-mobile-shopping-count" aria-label={`${toBuyItems.length} nog te kopen`}>{toBuyItems.length}</span>
        </section>

        {error ? <section className="rz-mobile-inventory-state rz-mobile-inventory-state--error" role="alert"><div>{error}</div><Button type="button" variant="secondary" onClick={loadList}>Opnieuw proberen</Button></section> : null}
        {!error && !loading && (list.items || []).length === 0 ? <section className="rz-mobile-inventory-state"><strong>Nog geen artikelen bij Boodschappen.</strong></section> : null}

        {!error && !loading && (list.items || []).length > 0 ? (
          <div className="rz-mobile-shopping-groups">
            <section className="rz-mobile-shopping-group" aria-label="Nog te kopen" data-testid="mobile-shopping-to-buy">
              <div className="rz-mobile-shopping-group-header">
                <div className="rz-mobile-shopping-group-title">Nog te kopen</div>
                <span>{toBuyItems.length}</span>
              </div>
              {toBuyItems.length ? (
                <div className="rz-mobile-shopping-list">
                  {toBuyItems.map(renderShoppingRow)}
                </div>
              ) : (
                <div className="rz-mobile-shopping-empty-section">Alles uit deze lijst zit in je winkelwagen.</div>
              )}
              <div className="rz-mobile-shopping-selection-actions" data-testid="mobile-shopping-to-buy-actions">
                <span>{selectedToBuyItems.length} geselecteerd</span>
                <div>
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => deleteSelectedItems(selectedToBuyItems)}
                    disabled={saving || selectedToBuyItems.length === 0}
                    data-testid="mobile-shopping-delete-selected"
                  >
                    Verwijderen
                  </Button>
                  <Button
                    type="button"
                    variant="primary"
                    onClick={() => setPurchasedForItems(selectedToBuyItems, true)}
                    disabled={saving || selectedToBuyItems.length === 0}
                    data-testid="mobile-shopping-move-to-cart"
                  >
                    In winkelwagen
                  </Button>
                </div>
              </div>
            </section>

            <section className="rz-mobile-shopping-group" aria-label="In winkelwagen" data-testid="mobile-shopping-cart">
              <div className="rz-mobile-shopping-group-header">
                <div className="rz-mobile-shopping-group-title">In winkelwagen</div>
                <span>{cartItems.length}</span>
              </div>
              {cartItems.length ? (
                <div className="rz-mobile-shopping-list">
                  {cartItems.map(renderShoppingRow)}
                </div>
              ) : (
                <div className="rz-mobile-shopping-empty-section">Nog geen artikelen in je winkelwagen.</div>
              )}
              <div className="rz-mobile-shopping-selection-actions" data-testid="mobile-shopping-cart-actions">
                <span>{selectedCartItems.length} geselecteerd</span>
                <div>
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => deleteSelectedItems(selectedCartItems)}
                    disabled={saving || selectedCartItems.length === 0}
                    data-testid="mobile-shopping-cart-delete-selected"
                  >
                    Verwijderen
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => setPurchasedForItems(selectedCartItems, false)}
                    disabled={saving || selectedCartItems.length === 0}
                    data-testid="mobile-shopping-return-to-buy"
                  >
                    Terug naar nog te kopen
                  </Button>
                </div>
              </div>
            </section>
          </div>
        ) : null}

        <div className="rz-mobile-shopping-complete">
          <Button type="button" variant="primary" onClick={completeShopping} disabled={saving || Number(list.item_count || 0) === 0} data-testid="mobile-shopping-complete">
            Boodschappen afgerond
          </Button>
        </div>
      </main>
    </div>
  )
}
