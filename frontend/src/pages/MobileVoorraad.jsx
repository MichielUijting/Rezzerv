import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Button from '../ui/Button'
import Select from '../ui/Select.jsx'
import MobileArticleRow from '../ui/MobileArticleRow.jsx'
import MobileModuleHeader from '../ui/MobileModuleHeader.jsx'
import QuantityStepper from '../ui/QuantityStepper.jsx'
import { MobilePaginationControls } from '../ui/MobilePagination.jsx'
import { useAppFeedback } from '../ui/AppFeedbackProvider.jsx'
import {
  fetchJsonWithAuth,
  isHouseholdAdminFromContext,
  readStoredAuthContext,
} from '../lib/authSession.js'
import {
  applyInventoryRowQuantity,
  buildExactInventoryMutation,
  buildQuickInventoryMutation,
  selectExactInventoryTarget,
  selectQuickInventoryTarget,
} from './mobileInventoryQuickActions.js'
import './mobileVoorraad.css'

function normalizeText(value) {
  return String(value || '').trim().toLowerCase()
}

function formatQuantity(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return '0'
  return Number.isInteger(number) ? String(number) : String(Number(number.toFixed(2)))
}

function buildArticleGroupMap(items = []) {
  const byHouseholdArticleId = new Map()
  items.forEach((item) => {
    const householdArticleId = String(item?.id || item?.household_article_id || '').trim()
    if (!householdArticleId) return
    byHouseholdArticleId.set(householdArticleId, String(item?.article_group_name || 'Niet ingedeeld').trim() || 'Niet ingedeeld')
  })
  return byHouseholdArticleId
}

function buildMobileInventoryRows(liveRows = [], articleGroupItems = []) {
  const articleGroups = buildArticleGroupMap(articleGroupItems)
  const grouped = new Map()

  liveRows.forEach((item, index) => {
    const quantity = Number(item?.aantal ?? item?.quantity ?? 0)
    if (!Number.isFinite(quantity) || quantity <= 0) return

    const householdArticleId = String(item?.household_article_id || '').trim()
    const inventoryId = String(item?.id || '').trim()
    const key = householdArticleId ? `household:${householdArticleId}` : `inventory:${inventoryId || index}`
    const householdName = String(item?.household_article_name || item?.artikel || '').trim()
    const productName = String(item?.product_name || item?.artikel || '').trim()
    const location = String(item?.locatie || item?.space_name || '').trim()
    const sublocation = String(item?.sublocatie || item?.sublocation_name || '').trim()
    const articleGroup = articleGroups.get(householdArticleId)
      || String(item?.article_group_name || '').trim()
      || 'Niet ingedeeld'

    const existing = grouped.get(key)
    if (!existing) {
      grouped.set(key, {
        id: key,
        householdArticleId,
        detailId: householdArticleId || inventoryId,
        articleName: String(item?.artikel || householdName || productName).trim(),
        householdName: householdName || productName || 'Onbekend artikel',
        productName,
        imageUrl: String(item?.image_url || '').trim(),
        gpcBrickName: String(item?.gpc_brick_name || '').trim(),
        gpcClassName: String(item?.gpc_class_name || '').trim(),
        gpcFamilyName: String(item?.gpc_family_name || '').trim(),
        articleGroup,
        quantity,
        inventoryEntries: inventoryId ? [{ inventoryId, quantity, sourceIndex: index }] : [],
        locations: new Set(location ? [location] : []),
        sublocations: new Set(sublocation ? [`${location}__${sublocation}`] : []),
        firstSeenIndex: index,
      })
      return
    }

    existing.quantity += quantity
    if (inventoryId) existing.inventoryEntries.push({ inventoryId, quantity, sourceIndex: index })
    if (location) existing.locations.add(location)
    if (sublocation) existing.sublocations.add(`${location}__${sublocation}`)
    if (!existing.detailId && inventoryId) existing.detailId = inventoryId
    if (!existing.imageUrl && item?.image_url) existing.imageUrl = String(item.image_url).trim()
  })

  return [...grouped.values()]
    .map((row) => {
      const locations = [...row.locations]
      const sublocations = [...row.sublocations]
      return {
        ...row,
        location: locations.length > 1 ? 'Meerdere locaties' : (locations[0] || 'Geen locatie'),
        sublocation: sublocations.length > 1
          ? 'Meerdere sublocaties'
          : ((sublocations[0] || '').split('__')[1] || ''),
      }
    })
    .sort((a, b) => a.firstSeenIndex - b.firstSeenIndex)
}

async function loadMobileInventory(options = {}) {
  // Server groups by household article before selecting the ten visible
  // articles. All underlying inventory targets of each article are retained.
  const params = new URLSearchParams({
    page: String(options.page || 1),
    page_size: '10',
    query: String(options.query || ''),
    location_filter: String(options.locationFilter || ''),
    group_filter: String(options.groupFilter || ''),
    sort_key: String(options.sortKey || 'name-asc'),
    location_tracking_enabled: String(options.locationTrackingEnabled !== false),
  })
  const response = await fetchJsonWithAuth(
    `/api/voorraad/mobile-page?${params.toString()}`,
    { method: 'GET', cache: 'no-store' },
  )
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(data?.detail || 'Voorraad kon niet worden geladen')
  }
  if (!Array.isArray(data?.rows) || !Number.isFinite(Number(data?.total))) {
    throw new Error('Voorraad heeft een onverwacht paginaantwoord ontvangen.')
  }
  return {
    initialRows: buildMobileInventoryRows(data.rows),
    total: Number(data.total),
    inventoryTotal: Number(data.inventory_total || 0),
    locations: Array.isArray(data.location_options) ? data.location_options : [],
    groups: Array.isArray(data.article_group_options) ? data.article_group_options : [],
  }
}

export default function MobileVoorraad({ locationTrackingEnabled = true }) {
  const navigate = useNavigate()
  const [rows, setRows] = useState([])
  const [inventoryPage, setInventoryPage] = useState(1)
  const [inventoryTotal, setInventoryTotal] = useState(0)
  const [inventoryOverallTotal, setInventoryOverallTotal] = useState(0)
  const [allLocationOptions, setAllLocationOptions] = useState([])
  const [allGroupOptions, setAllGroupOptions] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [locationFilter, setLocationFilter] = useState('')
  const [groupFilter, setGroupFilter] = useState('')
  const [sortKey, setSortKey] = useState('name-asc')
  const [mutatingRowId, setMutatingRowId] = useState('')
  const mutationLockRef = useRef(false)
  const loadGenerationRef = useRef(0)
  const { showFeedback } = useAppFeedback()
  useEffect(() => { if (error) showFeedback({ variant: 'error', message: error }) }, [error, showFeedback])
  const context = readStoredAuthContext()
  const canEditInventory = isHouseholdAdminFromContext(context)
  async function reload() {
    setIsLoading(true)
    setError('')
    const generation = ++loadGenerationRef.current
    try {
      const { initialRows, total, inventoryTotal: overallTotal, locations, groups } = await loadMobileInventory({
        page: inventoryPage, query, locationFilter, groupFilter, sortKey, locationTrackingEnabled,
      })
      if (generation !== loadGenerationRef.current) return
      setRows(initialRows)
      setInventoryTotal(total)
      setInventoryOverallTotal(overallTotal)
      setAllLocationOptions(locations)
      setAllGroupOptions(groups)
    } catch (err) {
      if (generation !== loadGenerationRef.current) return
      setRows([])
      setError(String(err?.message || 'Voorraad kon niet worden geladen'))
    } finally {
      if (generation === loadGenerationRef.current) setIsLoading(false)
    }
  }

  useEffect(() => {
    // Keep old rows visible without allowing actions until the requested page
    // and filters are consistent; debounce only free-text input.
    setIsLoading(true)
    const timer = window.setTimeout(() => { reload().catch(() => {}) }, query ? 250 : 0)
    return () => {
      window.clearTimeout(timer)
      ++loadGenerationRef.current
    }
  }, [inventoryPage, query, locationFilter, groupFilter, sortKey, locationTrackingEnabled])

  useEffect(() => {
    if (locationTrackingEnabled) return
    setLocationFilter('')
    setSortKey((current) => current === 'location' ? 'name-asc' : current)
  }, [locationTrackingEnabled])

  async function submitInventoryMutation(row, mutation, nextRowQuantity) {
    if (!canEditInventory || isLoading || mutationLockRef.current || !row?.householdArticleId) return
    const inventoryId = String(mutation.inventory_id || '')
    const previousRows = rows
    // Optimistic feedback: change the number immediately, not after two full GETs.
    mutationLockRef.current = true
    setMutatingRowId(row.id)
    setRows((current) => applyInventoryRowQuantity(current, row.id, inventoryId, nextRowQuantity))
    try {
      const response = await fetchJsonWithAuth(
        `/api/household-articles/${encodeURIComponent(row.householdArticleId)}/inventory-events`,
        {
          method: 'POST',
          body: JSON.stringify({
            ...mutation,
            article_name: String(row.articleName || row.householdName || '').trim(),
          }),
        },
      )
      const data = await response.json().catch(() => ({}))
      if (!response.ok) {
        const message = response.status >= 500
          ? 'Voorraadmutatie kon niet worden opgeslagen.'
          : (data?.detail || 'Voorraadmutatie kon niet worden opgeslagen.')
        throw new Error(message)
      }
      // Reconcile the changed identity from the authoritative POST response.
      // No reload of all inventory rows, GPC projections or article groups.
      const serverQuantity = Number(data?.row_new_quantity)
      if (data?.row_new_quantity != null && Number.isFinite(serverQuantity)) {
        setRows((current) => applyInventoryRowQuantity(current, row.id, inventoryId, serverQuantity))
        if (serverQuantity <= 0 && row.inventoryEntries.length === 1) {
          // Preserve accurate pagination totals when the last stock unit is consumed.
          setInventoryTotal((current) => Math.max(0, current - 1))
          setInventoryOverallTotal((current) => Math.max(0, current - 1))
        }
      }
    } catch (err) {
      setRows(previousRows)
      showFeedback({
        variant: 'error',
        message: String(err?.message || 'Voorraadmutatie kon niet worden opgeslagen.'),
        testId: 'mobile-inventory-quick-feedback',
      })
    } finally {
      mutationLockRef.current = false
      setMutatingRowId('')
    }
  }

  async function mutateQuickInventory(row, direction) {
    const mutation = buildQuickInventoryMutation(row, direction)
    if (!mutation) return
    const target = selectQuickInventoryTarget(row, direction)
    if (!target) return
    const nextRowQuantity = direction === 'decrease' ? target.quantity - 1 : Number(mutation.quantity)
    await submitInventoryMutation(row, mutation, nextRowQuantity)
  }

  async function setExactInventoryQuantity(row, nextQuantity) {
    const mutation = buildExactInventoryMutation(row, nextQuantity)
    if (!mutation || Number(nextQuantity) === Number(row.quantity)) return
    await submitInventoryMutation(row, mutation, Number(mutation.quantity))
  }

  // Server-side filters, name/location sorting and household article grouping
  // apply to the full household, not merely the visible page.
  const locationOptions = allLocationOptions
  const articleGroupOptions = allGroupOptions
  const filteredRows = rows
  const inventoryPageCount = Math.max(1, Math.ceil(inventoryTotal / 10))
  const inventoryPagination = {
    page: inventoryPage,
    pageCount: inventoryPageCount,
    pageItems: filteredRows,
    setPage: setInventoryPage,
  }
  useEffect(() => {
    if (!isLoading && inventoryPage > inventoryPageCount) setInventoryPage(inventoryPageCount)
  }, [isLoading, inventoryPage, inventoryPageCount])

  const hasActiveFilters = Boolean(query || groupFilter || (locationTrackingEnabled && locationFilter))

  function clearFilters() {
    setInventoryPage(1)
    setQuery('')
    setLocationFilter('')
    setGroupFilter('')
  }

  const resultSummary = isLoading
    ? 'Voorraad laden…'
    : (inventoryTotal === inventoryOverallTotal
      ? `${inventoryOverallTotal} artikelen`
      : `${inventoryTotal} van ${inventoryOverallTotal} artikelen`)

  return (
    <div
      className="rz-screen rz-mobile-inventory-screen"
      data-testid="mobile-inventory-page"
      data-location-tracking={locationTrackingEnabled ? 'enabled' : 'disabled'}
    >
      <MobileModuleHeader title="Voorraad" testId="mobile-inventory-header" />

      <main className="rz-mobile-inventory-content">
        <section className="rz-mobile-inventory-toolbar" aria-label="Voorraad zoeken en filteren">
          <label className="rz-mobile-inventory-field rz-mobile-inventory-search">
            <span className="rz-mobile-inventory-label">Zoek</span>
            <input
              className="rz-input"
              type="search"
              value={query}
              onChange={(event) => { setInventoryPage(1); setQuery(event.target.value) }}
              placeholder={locationTrackingEnabled ? 'Zoek artikel, groep of locatie' : 'Zoek artikel of groep'}
              autoComplete="off"
            />
          </label>

          <div className="rz-mobile-inventory-filter-strip">
            {locationTrackingEnabled ? (
              <div className="rz-mobile-inventory-field" data-testid="mobile-inventory-location-filter">
                <span id="mobile-inventory-location-label" className="rz-mobile-inventory-label">Locatie</span>
                <Select
                  ariaLabelledby="mobile-inventory-location-label"
                  value={locationFilter}
                  onChange={(value) => { setInventoryPage(1); setLocationFilter(value) }}
                  triggerClassName="rz-mobile-inventory-select-trigger"
                  options={[
                    { value: '', label: 'Alle locaties' },
                    ...locationOptions.map((option) => ({ value: option, label: option })),
                  ]}
                />
              </div>
            ) : null}

            <div className="rz-mobile-inventory-field">
              <span id="mobile-inventory-group-label" className="rz-mobile-inventory-label">Artikelgroep</span>
              <Select
                ariaLabelledby="mobile-inventory-group-label"
                value={groupFilter}
                onChange={(value) => { setInventoryPage(1); setGroupFilter(value) }}
                triggerClassName="rz-mobile-inventory-select-trigger"
                options={[
                  { value: '', label: 'Alle groepen' },
                  ...articleGroupOptions.map((option) => ({ value: option, label: option })),
                ]}
              />
            </div>

            <div className="rz-mobile-inventory-field rz-mobile-inventory-sort">
              <span id="mobile-inventory-sort-label" className="rz-mobile-inventory-label">Sorteren</span>
              <Select
                ariaLabelledby="mobile-inventory-sort-label"
                value={sortKey}
                onChange={(value) => { setInventoryPage(1); setSortKey(value) }}
                triggerClassName="rz-mobile-inventory-select-trigger"
                options={[
                  { value: 'name-asc', label: 'Naam A–Z' },
                  { value: 'name-desc', label: 'Naam Z–A' },
                  ...(locationTrackingEnabled ? [{ value: 'location', label: 'Locatie A–Z' }] : []),
                ]}
              />
            </div>
          </div>

          {hasActiveFilters ? (
            <Button
              type="button"
              variant="secondary"
              className="rz-mobile-inventory-clear"
              onClick={clearFilters}
            >
              Filters wissen
            </Button>
          ) : null}
        </section>

        <div className="rz-mobile-inventory-summary-row">
          <div className="rz-mobile-inventory-summary" aria-live="polite">{resultSummary}</div>
          <Button
            type="button"
            variant="primary"
            className="rz-mobile-inventory-add"
            onClick={() => navigate('/voorraad/incidentele-aankoop')}
            data-testid="mobile-inventory-add-incidental-purchase"
          >
            + Incidentele aankoop
          </Button>
        </div>



        {!error && !isLoading && filteredRows.length === 0 ? (
          <section className="rz-mobile-inventory-state">
            <strong>{inventoryOverallTotal === 0 ? 'Nog geen voorraad beschikbaar.' : 'Geen artikelen gevonden.'}</strong>
            {hasActiveFilters ? <span>Pas je zoekopdracht of filters aan.</span> : null}
          </section>
        ) : null}

        {!error && filteredRows.length > 0 ? (
          <section className="rz-mobile-inventory-list" aria-label="Voorraadartikelen" aria-busy={isLoading} style={{ pointerEvents: isLoading ? 'none' : undefined }}>
            {inventoryPagination.pageItems.map((row) => {
              const detailTarget = row.detailId
                ? `/voorraad/${encodeURIComponent(row.detailId)}?artikel=${encodeURIComponent(row.articleName || row.householdName)}`
                : ''
              const decreaseTarget = selectQuickInventoryTarget(row, 'decrease')
              const increaseTarget = selectQuickInventoryTarget(row, 'increase')
              const exactQuantityTarget = selectExactInventoryTarget(row)
              const rowBusy = mutatingRowId === row.id

              return (
                <MobileArticleRow
                  key={row.id}
                  title={row.householdName}
                  subtitle=""
                  meta={[
                    locationTrackingEnabled && row.location && row.location !== 'Geen locatie' ? `Locatie: ${row.location}` : '',
                    locationTrackingEnabled && row.sublocation ? `Sublocatie: ${row.sublocation}` : '',
                  ].filter(Boolean)}
                  imageUrl={row.imageUrl}
                  imageProductName={row.productName || row.householdName}
                  onActivate={detailTarget && !rowBusy && !isLoading ? () => navigate(detailTarget) : null}
                  testId={detailTarget ? `mobile-inventory-open-detail-${row.detailId}` : undefined}
                  side={(
                    <>
                      {canEditInventory ? (
                        <QuantityStepper
                          value={formatQuantity(row.quantity)}
                          decreaseDisabled={!decreaseTarget || rowBusy || isLoading}
                          increaseDisabled={!increaseTarget || rowBusy || isLoading}
                          decreaseLabel={`Boek 1 af van ${row.householdName}`}
                          increaseLabel={`Boek 1 op bij ${row.householdName}`}
                          valueLabel={exactQuantityTarget
                            ? `Aantal ${formatQuantity(row.quantity)}. Tik om aan te passen`
                            : `Aantal ${formatQuantity(row.quantity)}`}
                          valueEditable={Boolean(exactQuantityTarget)}
                          valueDisabled={rowBusy || isLoading}
                          testIdPrefix={`mobile-inventory-${row.detailId || row.id}`}
                          onValueCommit={(nextQuantity) => setExactInventoryQuantity(row, nextQuantity)}
                          onDecrease={(event) => {
                            event.stopPropagation()
                            mutateQuickInventory(row, 'decrease')
                          }}
                          onIncrease={(event) => {
                            event.stopPropagation()
                            mutateQuickInventory(row, 'increase')
                          }}
                        />
                      ) : (
                        <span className="rz-mobile-inventory-readonly-quantity" aria-label={`Aantal ${formatQuantity(row.quantity)}`}>
                          {formatQuantity(row.quantity)}
                        </span>
                      )}

                    </>
                  )}
                />
              )
            })}
          </section>
        ) : null}
        <div style={{ pointerEvents: isLoading ? 'none' : undefined }}><MobilePaginationControls {...inventoryPagination} ariaLabel="Paginering Voorraad" /></div>
      </main>

    </div>
  )
}

export { buildMobileInventoryRows }
