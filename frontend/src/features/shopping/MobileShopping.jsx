import { useEffect, useMemo, useRef, useState } from 'react'
import Button from '../../ui/Button.jsx'
import SearchCandidateList from '../../ui/SearchCandidateList.jsx'
import MobileArticleRow from '../../ui/MobileArticleRow.jsx'
import MobileModuleHeader from '../../ui/MobileModuleHeader.jsx'
import QuantityStepper from '../../ui/QuantityStepper.jsx'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'
import { fetchJsonWithAuth } from '../../lib/authSession.js'
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
  const [checkedFilter, setCheckedFilter] = useState('all')
  const [loading, setLoading] = useState(true)
  const [searching, setSearching] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const filterCheckboxRef = useRef(null)
  const checkedSaveChainsRef = useRef(new Map())
  const checkedMutationVersionsRef = useRef(new Map())

  async function loadList() {
    setLoading(true)
    setError('')
    try {
      setList(await requestJson('/api/shopping-list'))
    } catch (loadError) {
      setError(loadError?.message || 'Boodschappen konden niet worden geladen.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadList() }, [])

  useEffect(() => {
    if (filterCheckboxRef.current) {
      filterCheckboxRef.current.indeterminate = checkedFilter === 'all'
    }
  }, [checkedFilter])

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
        const payload = await requestJson(`/api/shopping-list/catalog-search?scope=all&query=${encodeURIComponent(query)}&limit=5`)
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
  const remainingCount = useMemo(
    () => (list.items || []).filter((item) => !item.checked).length,
    [list.items],
  )
  const visibleItems = useMemo(() => {
    if (checkedFilter === 'checked') return (list.items || []).filter((item) => item.checked)
    if (checkedFilter === 'unchecked') return (list.items || []).filter((item) => !item.checked)
    return list.items || []
  }, [checkedFilter, list.items])

  function patchListItem(itemId, patch) {
    setList((current) => ({
      ...current,
      items: (current.items || []).map((item) => item.id === itemId ? { ...item, ...patch } : item),
    }))
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
      setCatalogQuery('')
      setCatalogResults([])
      setSelectedResultId('')
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

  function updateChecked(item, checked) {
    const itemId = item.id
    const previousChecked = Boolean(item.checked)
    const nextVersion = (checkedMutationVersionsRef.current.get(itemId) || 0) + 1
    checkedMutationVersionsRef.current.set(itemId, nextVersion)
    patchListItem(itemId, { checked })
    const previousChain = checkedSaveChainsRef.current.get(itemId) || Promise.resolve()
    const nextChain = previousChain.catch(() => undefined).then(async () => {
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
        if (checkedMutationVersionsRef.current.get(itemId) === nextVersion) checkedSaveChainsRef.current.delete(itemId)
      }
    })
    checkedSaveChainsRef.current.set(itemId, nextChain)
    void nextChain.catch(() => undefined)
  }

  function cycleCheckedFilter() {
    setCheckedFilter((current) => current === 'all' ? 'unchecked' : current === 'unchecked' ? 'checked' : 'all')
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
          await loadList()
          showFeedback({ variant: 'success', title: 'Boodschappen afgerond', message: 'Boodschappen zijn leeggemaakt.' })
        } finally {
          setSaving(false)
        }
      },
    })
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
              onChange={(event) => setCatalogQuery(event.target.value)}
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
          <Button type="button" variant="primary" onClick={addArticle} disabled={saving || (!selectedResult && !catalogQuery.trim())} data-testid="mobile-shopping-add">
            Toevoegen
          </Button>
        </section>

        <section className="rz-mobile-shopping-summary-card" aria-label="Mijn boodschappen">
          <div>
            <div className="rz-mobile-shopping-summary-title">Mijn boodschappen</div>
            <div className="rz-mobile-shopping-summary-meta">
              {loading ? 'Boodschappen laden…' : `${Number(list.item_count || 0)} artikelen • ${remainingCount} nog te vinden`}
            </div>
          </div>
          <span className="rz-mobile-shopping-count" aria-label={`${remainingCount} nog te vinden`}>{remainingCount}</span>
        </section>

        {error ? <section className="rz-mobile-inventory-state rz-mobile-inventory-state--error" role="alert"><div>{error}</div><Button type="button" variant="secondary" onClick={loadList}>Opnieuw proberen</Button></section> : null}
        {!error && !loading && (list.items || []).length === 0 ? <section className="rz-mobile-inventory-state"><strong>Nog geen artikelen bij Boodschappen.</strong></section> : null}

        {!error && (list.items || []).length > 0 ? (
          <section className="rz-mobile-shopping-group" aria-label="Boodschappen">
            <div className="rz-mobile-shopping-group-header rz-mobile-shopping-filter-header">
              <label className="rz-mobile-shopping-status-filter" title="Filter: in kar, nog te vinden of beide">
                <input
                  ref={filterCheckboxRef}
                  type="checkbox"
                  checked={checkedFilter === 'checked'}
                  onChange={cycleCheckedFilter}
                  aria-label={`Filter koopstatus: ${checkedFilter === 'all' ? 'beide' : checkedFilter === 'checked' ? 'in kar' : 'nog te vinden'}`}
                />
              </label>
              <div className="rz-mobile-shopping-group-title">Boodschappen</div>
              <span>{visibleItems.length} van {(list.items || []).length}</span>
            </div>
            <div className="rz-mobile-shopping-list">
              {visibleItems.map((item) => (
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
                      checked={Boolean(item.checked)}
                      onChange={(event) => updateChecked(item, event.target.checked)}
                      aria-label={`${item.article_name} ${item.checked ? 'uit kar halen' : 'in kar leggen'}`}
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
              ))}
            </div>
          </section>
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
