import { useEffect, useMemo, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import CatalogArticleThumbnail from '../../ui/CatalogArticleThumbnail.jsx'
import MobileModuleHeader from '../../ui/MobileModuleHeader.jsx'
import QuantityStepper from '../../ui/QuantityStepper.jsx'
import Tabs from '../../ui/Tabs.jsx'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'
import {
  fetchJsonWithAuth,
  isHouseholdAdminFromContext,
  readStoredAuthContext,
} from '../../lib/authSession.js'
import { useArticleFieldVisibility } from './hooks/useArticleFieldVisibility.js'
import ArticleOverviewSubtabs from './tabs/ArticleOverviewSubtabs.jsx'
import ArticleStockTab from './tabs/ArticleStockTab.jsx'
import ArticleLocationsTab from './tabs/ArticleLocationsTab.jsx'
import {
  buildMobileArticleInventoryRows,
  buildShoppingListPayload,
  chooseMobileInventoryRow,
  formatMobileLocation,
  isMobileArticleAlmostOut,
  isMobileArticleLocationTrackingEnabled,
  isStableHouseholdArticleId,
} from './mobileArticleDetailModel.js'
import './articleDetailMutationPolicy.css'
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

async function fetchMobileLocationTracking(authContext = {}) {
  if (isMobileArticleLocationTrackingEnabled(authContext)) return true
  try {
    const payload = await requestJson('/api/onboarding', { method: 'GET', cache: 'no-store' })
    return isMobileArticleLocationTrackingEnabled(authContext, payload)
  } catch {
    return false
  }
}

function formatQuantity(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return '0'
  return Number.isInteger(number) ? String(number) : String(Number(number.toFixed(2)))
}

export default function MobileArticlePage() {
  const { articleId = '' } = useParams()
  const [searchParams] = useSearchParams()
  const requestedArticleName = String(searchParams.get('artikel') || '').trim()
  const authContext = readStoredAuthContext() || {}
  const canEditInventory = isHouseholdAdminFromContext(authContext)
  const {
    visibilityMap,
    isLoading: visibilityLoading,
    error: visibilityError,
  } = useArticleFieldVisibility()

  const [articleData, setArticleData] = useState(null)
  const [liveRows, setLiveRows] = useState([])
  const [locationTrackingEnabled, setLocationTrackingEnabled] = useState(() => (
    isMobileArticleLocationTrackingEnabled(authContext)
  ))
  const [selectedInventoryId, setSelectedInventoryId] = useState('')
  const [activeDetailTab, setActiveDetailTab] = useState('Artikel')
  const [loading, setLoading] = useState(true)
  const [inventoryBusy, setInventoryBusy] = useState(false)
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
  const canDirectEditQuantity = canEditInventory
    && Boolean(selectedRow?.id)
    && (inventoryRows.length === 1 || locationTrackingEnabled)
  const articleImageUrl = String(selectedRow?.imageUrl || articleData?.image_url || '').trim()
  const almostOut = isMobileArticleAlmostOut(totalQuantity, settings?.min_stock)

  const detailTabs = useMemo(
    () => locationTrackingEnabled
      ? ['Artikel', 'Huishouden', 'Identiteit', 'Productdata', 'Voorraad', 'Locaties']
      : ['Artikel', 'Huishouden', 'Identiteit', 'Productdata', 'Voorraad'],
    [locationTrackingEnabled],
  )

  const fullArticleData = useMemo(() => {
    if (!articleData) return null
    const locations = inventoryRows.map((row) => ({
      id: row.id,
      space_id: row.spaceId,
      sublocation_id: row.sublocationId,
      locatie: row.location,
      sublocatie: row.sublocation,
      aantal: row.quantity,
    }))
    const primaryLocation = locations[0] || {}
    return {
      ...articleData,
      id: articleData?.id || householdArticleId || articleId,
      household_article_id: articleData?.household_article_id || householdArticleId,
      article_id: articleData?.article_id || householdArticleId,
      name: articleName,
      article_name: articleName,
      locations,
      total_quantity: totalQuantity,
      main_location: primaryLocation.locatie || '',
      sub_location: primaryLocation.sublocatie || '',
    }
  }, [articleData, articleId, articleName, householdArticleId, inventoryRows, totalQuantity])

  async function loadAll({ showLoading = true } = {}) {
    if (showLoading) setLoading(true)
    setError('')
    try {
      const [details, inventory, locationTracking] = await Promise.all([
        fetchMobileArticleDetails(articleId),
        fetchMobileInventoryRows(),
        fetchMobileLocationTracking(authContext),
      ])
      setArticleData(details)
      setLiveRows(inventory)
      setLocationTrackingEnabled(locationTracking)
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
    if (!detailTabs.includes(activeDetailTab)) {
      setActiveDetailTab('Artikel')
    }
  }, [activeDetailTab, detailTabs])

  function showSuccess(message) {
    showFeedback({ variant: 'success', message, testId: 'mobile-article-feedback' })
  }

  function showError(message) {
    showFeedback({ variant: 'error', message, testId: 'mobile-article-feedback' })
  }

  async function refreshInventory() {
    const inventory = await fetchMobileInventoryRows()
    setLiveRows(inventory)
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
      await refreshInventory()
      showSuccess(direction > 0 ? 'Voorraad met 1 verhoogd.' : 'Voorraad met 1 verlaagd.')
    } catch (mutationError) {
      showError(mutationError?.message || 'Voorraad kon niet worden aangepast.')
    } finally {
      setInventoryBusy(false)
    }
  }

  async function setExactInventoryQuantity(nextQuantity) {
    if (!canDirectEditQuantity || inventoryBusy || !householdArticleId || !selectedRow?.id) return
    const normalizedQuantity = Number(String(nextQuantity ?? '').replace(',', '.'))
    if (!Number.isFinite(normalizedQuantity) || normalizedQuantity < 0) return
    if (normalizedQuantity === Number(displayedQuantity)) return

    setInventoryBusy(true)
    try {
      await requestJson(`/api/household-articles/${encodeURIComponent(householdArticleId)}/inventory-events`, {
        method: 'POST',
        body: JSON.stringify({
          inventory_id: selectedRow.id,
          article_name: articleName,
          quantity: normalizedQuantity,
          event_type: 'adjustment',
          note: 'Exact aantal aangepast via mobiel artikeldetail.',
        }),
      })
      await refreshInventory()
      showSuccess('Voorraad aangepast naar ' + formatQuantity(normalizedQuantity) + '.')
    } catch (mutationError) {
      showError(mutationError?.message || 'Voorraad kon niet worden aangepast.')
    } finally {
      setInventoryBusy(false)
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
      showSuccess(`${articleName} staat op de boodschappenlijst.`)
    } catch (shoppingError) {
      showError(shoppingError?.message || 'Artikel kon niet op de boodschappenlijst worden geplaatst.')
    } finally {
      setShoppingBusy(false)
    }
  }

  if (loading) {
    return (
      <div className="rz-screen rz-mobile-article-screen" data-testid="mobile-article-detail-page">
        <MobileModuleHeader title="Artikel in Voorraad" testId="mobile-article-header" />
        <main className="rz-mobile-article-content">
          <section className="rz-mobile-article-card rz-mobile-article-state">Artikeldetails laden…</section>
        </main>
      </div>
    )
  }

  if (error || !articleData) {
    return (
      <div className="rz-screen rz-mobile-article-screen" data-testid="mobile-article-detail-page">
        <MobileModuleHeader title="Artikel in Voorraad" testId="mobile-article-header" />
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

  return (
    <div
      className="rz-screen rz-mobile-article-screen"
      data-testid="mobile-article-detail-page"
      data-location-tracking={locationTrackingEnabled ? 'enabled' : 'disabled'}
    >
      <MobileModuleHeader title="Artikel in Voorraad" testId="mobile-article-header" />
      <main className="rz-mobile-article-content">
        <section className="rz-mobile-article-card rz-mobile-article-hero" aria-label="Actuele voorraad">
          <div className="rz-mobile-article-identity">
            <CatalogArticleThumbnail
              imageUrl={articleImageUrl}
              productName={articleName}
              className="rz-mobile-article-product-thumbnail"
            />
            <div className="rz-mobile-article-identity-copy">
              <div className="rz-mobile-article-name">{articleName}</div>
              <div className="rz-mobile-article-chips">
                <span className="rz-mobile-article-chip">{articleGroup || 'Niet ingedeeld'}</span>
                {almostOut ? <span className="rz-mobile-article-chip rz-mobile-article-chip--warning">Bijna op</span> : null}
              </div>
            </div>
          </div>

          <div className="rz-mobile-article-stock-row">
            <div className="rz-mobile-article-stock-copy">
              <span className="rz-mobile-article-stock-label">Actuele voorraad</span>
              {locationTrackingEnabled && selectedRow ? (
                <span className="rz-mobile-article-stock-location">{formatMobileLocation(selectedRow)}</span>
              ) : null}
            </div>
            <div className="rz-mobile-article-stock-control">
              <QuantityStepper
                value={formatQuantity(displayedQuantity)}
                decreaseDisabled={!canEditInventory || inventoryBusy || !selectedRow || selectedRow.quantity <= 0}
                increaseDisabled={!canEditInventory || inventoryBusy || !selectedRow}
                valueEditable={canDirectEditQuantity}
                valueDisabled={inventoryBusy}
                decreaseLabel="Voorraad met 1 verlagen"
                increaseLabel="Voorraad met 1 verhogen"
                valueLabel={canDirectEditQuantity
                  ? 'Aantal ' + formatQuantity(displayedQuantity) + '. Tik om aan te passen'
                  : 'Aantal ' + formatQuantity(displayedQuantity)}
                decreaseTestId="mobile-article-stock-minus"
                increaseTestId="mobile-article-stock-plus"
                valueTestId="mobile-article-stock-value"
                onValueCommit={setExactInventoryQuantity}
                onDecrease={() => changeInventory(-1)}
                onIncrease={() => changeInventory(1)}
              />
            </div>
          </div>
          {!canEditInventory ? <div className="rz-mobile-article-helper">Alleen een beheerder of eigenaar kan de voorraad aanpassen.</div> : null}
        </section>

        <section
          className="rz-mobile-article-card rz-mobile-article-functional-card"
          aria-label="Artikeldetails"
          data-testid="mobile-article-full-details"
        >
          <Tabs
            tabs={detailTabs}
            activeTab={activeDetailTab}
            onTabChange={setActiveDetailTab}
            className="rz-mobile-article-functional-tabs"
            ariaLabel="Artikeldetails"
            rootTestId="mobile-article-detail-tabs"
            tablistTestId="mobile-article-detail-tablist"
            tabTestIdMap={{
              Artikel: 'mobile-article-tab-article',
              Huishouden: 'mobile-article-tab-household',
              Identiteit: 'mobile-article-tab-identity',
              Productdata: 'mobile-article-tab-productdata',
              Voorraad: 'mobile-article-tab-stock',
              Locaties: 'mobile-article-tab-locations',
            }}
          >
            {(currentTab) => {
              if (!fullArticleData) return null
              if (['Artikel', 'Huishouden', 'Identiteit', 'Productdata'].includes(currentTab)) {
                return (
                  <div className="rz-mobile-article-tab-stack">
                    <ArticleOverviewSubtabs
                      articleData={fullArticleData}
                      activeSubtab={currentTab}
                      showTabs={false}
                      visibilityMap={visibilityMap}
                      visibilityLoading={visibilityLoading}
                      visibilityError={visibilityError}
                      onDetailsSaved={(details) => {
                        setArticleData((current) => ({ ...(current || {}), ...(details || {}) }))
                      }}
                    />
                    {currentTab === 'Artikel' ? (
                      <button
                        type="button"
                        className="rz-mobile-article-action-row rz-mobile-article-action-row--primary"
                        onClick={addToShoppingList}
                        disabled={shoppingBusy || !householdArticleId}
                        data-testid="mobile-article-add-to-shopping-list"
                      >
                        <span>Op boodschappenlijst</span>
                        {shoppingBusy ? <span className="rz-mobile-article-action-value">Bezig…</span> : null}
                      </button>
                    ) : null}
                  </div>
                )
              }
              if (currentTab === 'Voorraad') {
                return <ArticleStockTab articleData={fullArticleData} onInventoryChanged={refreshInventory} />
              }
              if (currentTab === 'Locaties') {
                return <ArticleLocationsTab articleData={fullArticleData} onInventoryChanged={refreshInventory} />
              }
              return null
            }}
          </Tabs>
        </section>
      </main>
    </div>
  )
}
