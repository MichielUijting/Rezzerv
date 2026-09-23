import { useEffect, useMemo, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import Header from '../../ui/Header.jsx'
import Select from '../../ui/Select.jsx'
import QuantityStepper from '../../ui/QuantityStepper.jsx'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'
import {
  fetchJsonWithAuth,
  isHouseholdAdminFromContext,
  isHouseholdViewerFromContext,
  readStoredAuthContext,
} from '../../lib/authSession.js'
import {
  buildHouseholdSettingsPayload,
  buildMobileArticleInventoryRows,
  buildShoppingListPayload,
  chooseMobileInventoryRow,
  filterPurchaseHistory,
  formatMobileLocation,
  isMobileArticleAlmostOut,
  isStableHouseholdArticleId,
} from './mobileArticleDetailModel.js'
import './mobileArticleDetail.css'

async function requestJson(url, options = {}) {
  const response = await fetchJsonWithAuth(url, options)
  if (response.status === 204) return null
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = typeof payload?.detail === 'string'
      ? payload.detail
      : (payload?.detail?.reason || payload?.message || 'Verzoek mislukt')
    throw new Error(detail)
  }
  return payload
}

async function fetchMobileArticleDetails(articleId) {
  const normalizedId = String(articleId || '').trim()
  if (!normalizedId) throw new Error('Artikel ontbreekt.')
  const endpoint = isStableHouseholdArticleId(normalizedId)
    ? `/api/household-articles/${encodeURIComponent(normalizedId)}`
    : `/api/inventory/${encodeURIComponent(normalizedId)}/article-detail`
  return requestJson(endpoint, { method: 'GET', cache: 'no-store' })
}

async function fetchMobileInventoryRows() {
  const payload = await requestJson(`/api/dev/inventory-preview?_ts=${Date.now()}`, { method: 'GET', cache: 'no-store' })
  return Array.isArray(payload?.rows) ? payload.rows : []
}

async function fetchMobileLocationTracking() {
  try {
    const payload = await requestJson('/api/onboarding', { method: 'GET', cache: 'no-store' })
    return String(payload?.product_configuration?.location_tracking_level || 'none').trim().toLowerCase() !== 'none'
  } catch {
    return false
  }
}

async function fetchMobilePurchaseHistory(articleId, articleName) {
  try {
    const normalizedId = String(articleId || '').trim()
    if (isStableHouseholdArticleId(normalizedId)) {
      const payload = await requestJson(`/api/household-articles/${encodeURIComponent(normalizedId)}/events`, { method: 'GET', cache: 'no-store' })
      return Array.isArray(payload?.items) ? payload.items : []
    }
    const payload = await requestJson(`/api/dev/article-history?article_name=${encodeURIComponent(String(articleName || '').trim())}`, { method: 'GET', cache: 'no-store' })
    return Array.isArray(payload?.rows) ? payload.rows : []
  } catch {
    return []
  }
}

function formatQuantity(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return '0'
  return Number.isInteger(number) ? String(number) : String(Number(number.toFixed(2)))
}

function formatPurchaseDate(value) {
  if (!value) return 'Datum onbekend'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return new Intl.DateTimeFormat('nl-NL', { dateStyle: 'medium' }).format(date)
}

export default function MobileArticlePage() {
  const { articleId = '' } = useParams()
  const [searchParams] = useSearchParams()
  const requestedArticleName = String(searchParams.get('artikel') || '').trim()
  const authContext = readStoredAuthContext() || {}
  const canEditInventory = isHouseholdAdminFromContext(authContext)
  const canEditHouseholdSettings = !isHouseholdViewerFromContext(authContext)

  const [articleData, setArticleData] = useState(null)
  const [liveRows, setLiveRows] = useState([])
  const [historyRows, setHistoryRows] = useState([])
  const [locationTrackingEnabled, setLocationTrackingEnabled] = useState(false)
  const [selectedInventoryId, setSelectedInventoryId] = useState('')
  const [favoriteStoreDraft, setFavoriteStoreDraft] = useState('')
  const [activeQuickPanel, setActiveQuickPanel] = useState('')
  const [loading, setLoading] = useState(true)
  const [inventoryBusy, setInventoryBusy] = useState(false)
  const [settingsBusy, setSettingsBusy] = useState(false)
  const [shoppingBusy, setShoppingBusy] = useState(false)
  const { showFeedback } = useAppFeedback()
  const [error, setError] = useState('')

  const articleName = String(articleData?.article_name || articleData?.name || requestedArticleName || 'Voorraadartikel').trim()
  const householdArticleId = String(
    articleData?.household_article_id
      || articleData?.article_id
      || (isStableHouseholdArticleId(articleId) ? articleId : ''),
  ).trim()
  const settings = articleData?.settings && typeof articleData.settings === 'object' ? articleData.settings : {}

  const inventoryRows = useMemo(
    () => buildMobileArticleInventoryRows(liveRows, householdArticleId || articleId, articleName),
    [liveRows, householdArticleId, articleId, articleName],
  )

  const totalQuantity = useMemo(
    () => inventoryRows.reduce((sum, row) => sum + (Number(row.quantity) || 0), 0),
    [inventoryRows],
  )

  const selectedRow = useMemo(
    () => inventoryRows.find((row) => row.id === selectedInventoryId) || chooseMobileInventoryRow(inventoryRows, settings),
    [inventoryRows, selectedInventoryId, settings],
  )

  const displayedQuantity = locationTrackingEnabled && inventoryRows.length > 1
    ? (selectedRow?.quantity ?? 0)
    : totalQuantity
  const almostOut = isMobileArticleAlmostOut(totalQuantity, settings?.min_stock)
  const purchaseHistory = useMemo(() => filterPurchaseHistory(historyRows), [historyRows])

  async function loadAll({ showLoading = true } = {}) {
    if (showLoading) setLoading(true)
    setError('')
    try {
      const [details, inventory, locationTracking] = await Promise.all([
        fetchMobileArticleDetails(articleId),
        fetchMobileInventoryRows(),
        fetchMobileLocationTracking(),
      ])
      const resolvedName = String(details?.article_name || details?.name || requestedArticleName || '').trim()
      const resolvedId = String(details?.household_article_id || details?.article_id || (isStableHouseholdArticleId(articleId) ? articleId : '')).trim()
      const history = await fetchMobilePurchaseHistory(resolvedId || articleId, resolvedName)
      setArticleData(details)
      setLiveRows(inventory)
      setHistoryRows(history)
      setLocationTrackingEnabled(locationTracking)
      setFavoriteStoreDraft(String(details?.settings?.favorite_store || ''))
    } catch (loadError) {
      setError(loadError?.message || 'Artikeldetails konden niet worden geladen.')
    } finally {
      if (showLoading) setLoading(false)
    }
  }

  useEffect(() => {
    loadAll()
  }, [articleId, requestedArticleName])

  useEffect(() => {
    if (inventoryRows.some((row) => row.id === selectedInventoryId)) return
    const preferred = chooseMobileInventoryRow(inventoryRows, settings)
    setSelectedInventoryId(preferred?.id || '')
  }, [inventoryRows, selectedInventoryId, settings?.default_location_id, settings?.default_sublocation_id])

  useEffect(() => {
    setFavoriteStoreDraft(String(settings?.favorite_store || ''))
  }, [settings?.favorite_store])

  function showSuccess(message) {
    showFeedback({ variant: 'success', message, testId: 'mobile-article-feedback' })
  }

  function showError(message) {
    showFeedback({ variant: 'error', message, testId: 'mobile-article-feedback' })
  }

  async function refreshInventoryAndHistory() {
    const [inventory, history] = await Promise.all([
      fetchMobileInventoryRows(),
      fetchMobilePurchaseHistory(householdArticleId || articleId, articleName),
    ])
    setLiveRows(inventory)
    setHistoryRows(history)
  }

  async function changeInventory(direction) {
    if (!canEditInventory || inventoryBusy || !householdArticleId || !selectedRow?.id) return
    if (direction < 0 && selectedRow.quantity <= 0) return

    setInventoryBusy(true)
    try {
      await requestJson(`/api/household-articles/${encodeURIComponent(householdArticleId)}/inventory-events`, {
        method: 'POST',
        body: JSON.stringify({
          inventory_id: selectedRow.id,
          article_name: articleName,
          quantity: direction > 0 ? selectedRow.quantity + 1 : 1,
          event_type: direction > 0 ? 'adjustment' : 'consume',
          note: direction > 0
            ? 'Voorraad verhoogd via mobiel artikeldetail.'
            : 'Voorraad verlaagd via mobiel artikeldetail.',
        }),
      })
      await refreshInventoryAndHistory()
      showSuccess(direction > 0 ? 'Voorraad met 1 verhoogd.' : 'Voorraad met 1 verlaagd.')
    } catch (mutationError) {
      showError(mutationError?.message || 'Voorraad kon niet worden aangepast.')
    } finally {
      setInventoryBusy(false)
    }
  }

  async function saveFavoriteStore() {
    const currentValue = String(settings?.favorite_store || '').trim()
    const nextValue = String(favoriteStoreDraft || '').trim()
    if (!canEditHouseholdSettings || settingsBusy || !householdArticleId || nextValue === currentValue) return

    setSettingsBusy(true)
    try {
      const payload = buildHouseholdSettingsPayload(settings, nextValue)
      const result = await requestJson(`/api/household-articles/${encodeURIComponent(householdArticleId)}/settings`, {
        method: 'PUT',
        body: JSON.stringify(payload),
      })
      const nextSettings = result?.settings && typeof result.settings === 'object' ? result.settings : payload
      setArticleData((current) => ({ ...(current || {}), settings: nextSettings }))
      setFavoriteStoreDraft(String(nextSettings.favorite_store || ''))
      showSuccess(nextValue ? `Voorkeurswinkel ingesteld op ${nextValue}.` : 'Voorkeurswinkel verwijderd.')
    } catch (settingsError) {
      setFavoriteStoreDraft(currentValue)
      showError(settingsError?.message || 'Voorkeurswinkel kon niet worden opgeslagen.')
    } finally {
      setSettingsBusy(false)
    }
  }

  async function addToShoppingList() {
    if (shoppingBusy || !householdArticleId) return
    setShoppingBusy(true)
    try {
      const payload = buildShoppingListPayload(articleData || { article_name: articleName }, householdArticleId)
      await requestJson('/api/shopping-list/items', {
        method: 'POST',
        body: JSON.stringify(payload),
      })
      showSuccess(`${articleName} toegevoegd aan Winkelen.`)
    } catch (shoppingError) {
      showError(shoppingError?.message || 'Artikel kon niet aan Winkelen worden toegevoegd.')
    } finally {
      setShoppingBusy(false)
    }
  }

  function togglePanel(panel) {
    setActiveQuickPanel((current) => current === panel ? '' : panel)
  }

  if (loading) {
    return (
      <div className="rz-screen rz-mobile-article-screen" data-testid="mobile-article-detail-page">
        <Header title={requestedArticleName || 'Voorraadartikel'} />
        <main className="rz-mobile-article-content">
          <section className="rz-mobile-article-card rz-mobile-article-state">Artikeldetails laden…</section>
        </main>
      </div>
    )
  }

  if (error || !articleData) {
    return (
      <div className="rz-screen rz-mobile-article-screen" data-testid="mobile-article-detail-page">
        <Header title={requestedArticleName || 'Voorraadartikel'} />
        <main className="rz-mobile-article-content">
          <section className="rz-mobile-article-card rz-mobile-article-state rz-mobile-article-state--error" role="alert">
            <strong>Artikel niet beschikbaar</strong>
            <span>{error || 'Voor dit artikel zijn geen gegevens beschikbaar.'}</span>
            <button type="button" className="rz-mobile-article-text-action" onClick={() => loadAll()}>Opnieuw proberen</button>
          </section>
        </main>
      </div>
    )
  }

  const articleGroup = String(articleData?.article_group_name || articleData?.article_group || articleData?.category || 'Niet ingedeeld').trim()
  const notes = String(settings?.notes || articleData?.notes || '').trim()

  return (
    <div
      className="rz-screen rz-mobile-article-screen"
      data-testid="mobile-article-detail-page"
      data-location-tracking={locationTrackingEnabled ? 'enabled' : 'disabled'}
    >
      <Header title={articleName} />
      <main className="rz-mobile-article-content">
        <section className="rz-mobile-article-card rz-mobile-article-hero" aria-label="Actuele voorraad">
          <div className="rz-mobile-article-heading">
            <div>
              <div className="rz-mobile-article-name">{articleName}</div>
              <div className="rz-mobile-article-chips">
                <span className="rz-mobile-article-chip">{articleGroup || 'Niet ingedeeld'}</span>
                {almostOut ? <span className="rz-mobile-article-chip rz-mobile-article-chip--warning">Bijna op</span> : null}
              </div>
            </div>
            <div className="rz-mobile-article-stock-control">
              <QuantityStepper
                value={formatQuantity(displayedQuantity)}
                decreaseDisabled={!canEditInventory || inventoryBusy || !selectedRow || selectedRow.quantity <= 0}
                increaseDisabled={!canEditInventory || inventoryBusy || !selectedRow}
                decreaseLabel="Voorraad met 1 verlagen"
                increaseLabel="Voorraad met 1 verhogen"
                valueLabel={`Aantal ${formatQuantity(displayedQuantity)}`}
                decreaseTestId="mobile-article-stock-minus"
                increaseTestId="mobile-article-stock-plus"
                valueTestId="mobile-article-stock-value"
                onDecrease={() => changeInventory(-1)}
                onIncrease={() => changeInventory(1)}
              />
            </div>
          </div>
          {!canEditInventory ? <div className="rz-mobile-article-helper">Alleen een beheerder of eigenaar kan de voorraad aanpassen.</div> : null}
        </section>

        <section className="rz-mobile-article-card rz-mobile-article-details" aria-label="Artikelgegevens">
          <div className="rz-mobile-article-section-title">Artikelgegevens</div>
          <div className="rz-mobile-article-detail-row">
            <span>Minimumvoorraad</span>
            <strong>{settings?.min_stock == null || settings?.min_stock === '' ? 'Niet ingesteld' : formatQuantity(settings.min_stock)}</strong>
          </div>
          {locationTrackingEnabled ? (
            <div className="rz-mobile-article-detail-row rz-mobile-article-detail-row--location" data-testid="mobile-article-location-row">
              <span>Locatie</span>
              {inventoryRows.length > 1 ? (
                <Select
                  value={selectedRow?.id || ''}
                  onChange={setSelectedInventoryId}
                  options={inventoryRows.map((row) => ({
                    value: row.id,
                    label: `${formatMobileLocation(row)} — ${formatQuantity(row.quantity)}`,
                  }))}
                  ariaLabel="Voorraadlocatie"
                  triggerClassName="rz-mobile-article-select"
                  dataTestId="mobile-article-location-select"
                />
              ) : (
                <strong>{formatMobileLocation(selectedRow)}</strong>
              )}
            </div>
          ) : null}
          <div className="rz-mobile-article-detail-row">
            <span>Notities</span>
            <strong>{notes || 'Geen notities'}</strong>
          </div>
        </section>

        <section className="rz-mobile-article-card rz-mobile-article-quick-actions" aria-label="Snelle acties">
          <div className="rz-mobile-article-section-title">Snelle acties</div>

          <button
            type="button"
            className="rz-mobile-article-action-row"
            onClick={() => togglePanel('favorite-store')}
            aria-expanded={activeQuickPanel === 'favorite-store'}
            data-testid="mobile-article-favorite-store-action"
          >
            <span>Voorkeurswinkel</span>
            <span className="rz-mobile-article-action-value">{String(settings?.favorite_store || '').trim() || 'Niet ingesteld'}</span>
          </button>
          {activeQuickPanel === 'favorite-store' ? (
            <div className="rz-mobile-article-inline-panel" data-testid="mobile-article-favorite-store-panel">
              <label className="rz-mobile-article-field">
                <span>Voorkeurswinkel</span>
                <input
                  className="rz-mobile-article-input"
                  value={favoriteStoreDraft}
                  onChange={(event) => setFavoriteStoreDraft(event.target.value)}
                  onBlur={saveFavoriteStore}
                  disabled={!canEditHouseholdSettings || settingsBusy}
                  placeholder="Bijvoorbeeld: AH"
                />
              </label>
              <div className="rz-mobile-article-helper">Wijzigingen worden opgeslagen zodra je het veld verlaat.</div>
            </div>
          ) : null}

          <button
            type="button"
            className="rz-mobile-article-action-row"
            onClick={() => togglePanel('purchase-history')}
            aria-expanded={activeQuickPanel === 'purchase-history'}
            data-testid="mobile-article-purchase-history-action"
          >
            <span>Aankoophistorie</span>
            <span className="rz-mobile-article-action-value">{purchaseHistory.length}</span>
          </button>
          {activeQuickPanel === 'purchase-history' ? (
            <div className="rz-mobile-article-inline-panel" data-testid="mobile-article-purchase-history-panel">
              {purchaseHistory.length === 0 ? (
                <div className="rz-mobile-article-helper">Nog geen aankopen geregistreerd.</div>
              ) : (
                <div className="rz-mobile-article-history-list">
                  {purchaseHistory.map((event, index) => (
                    <div key={event?.id || `${event?.created_at || event?.datetime || 'purchase'}-${index}`} className="rz-mobile-article-history-row">
                      <span>{formatPurchaseDate(event?.created_at || event?.datetime)}</span>
                      <strong>{event?.quantity == null ? 'Aankoop' : `+${formatQuantity(event.quantity)}`}</strong>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : null}

          <button
            type="button"
            className="rz-mobile-article-action-row rz-mobile-article-action-row--primary"
            onClick={addToShoppingList}
            disabled={shoppingBusy || !householdArticleId}
            data-testid="mobile-article-add-to-shopping-list"
          >
            <span>Naar inkooplijstje</span>
            <span className="rz-mobile-article-action-value">{shoppingBusy ? 'Bezig…' : 'Winkelen'}</span>
          </button>
        </section>
      </main>
    </div>
  )
}
