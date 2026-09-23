import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import Button from '../ui/Button'
import Select from '../ui/Select.jsx'
import CatalogArticleThumbnail from '../ui/CatalogArticleThumbnail.jsx'
import {
  canCurrentUserPerform,
  fetchJsonWithAuth,
  isFrontteamMemberFromContext,
  isHouseholdAdminFromContext,
  isPlatformSuperuserFromContext,
  readStoredAuthContext,
} from '../lib/authSession.js'
import { readHouseholdOnboarding } from '../features/onboarding/onboardingState.js'
import { buildHomeNavigation } from '../features/home/homeNavigation.js'
import useFeatureAvailability from '../features/platform/useFeatureAvailability.js'
import { useActionButtonAvailability } from '../features/platform/actionButtonAvailability.js'
import { buildQuickInventoryMutation, selectQuickInventoryTarget } from './mobileInventoryQuickActions.js'
import {
  ACTION_ROUTE_BY_KEY,
  readRecentActionKeys,
  recordRecentAction,
  selectRecentActionTiles,
} from '../features/home/recentActionUsage.js'
import './mobileVoorraad.css'

const MORE_NAV_ITEM = { key: 'meer', label: 'Meer', route: '/home', icon: 'menu' }

function mobileNavIconType(key) {
  if (key === 'meldingen') return 'bell'
  if (key === 'voorraad') return 'inventory'
  if (key === 'bijna-op') return 'clock'
  if (key === 'winkelen') return 'cart'
  if (key === 'kassabonnen' || key === 'kassa') return 'receipt'
  return 'menu'
}

function MobileNavIcon({ type }) {
  if (type === 'bell') {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M7 10a5 5 0 0 1 10 0v4l1.5 2H5.5L7 14v-4Z" />
        <path d="M10 19h4" />
      </svg>
    )
  }
  if (type === 'inventory') {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M4 7.5 12 4l8 3.5v9L12 20l-8-3.5v-9Z" />
        <path d="m4.5 7.7 7.5 3.4 7.5-3.4M12 11.1V20" />
      </svg>
    )
  }
  if (type === 'clock') {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="12" cy="12" r="8" />
        <path d="M12 8v4l2.8 1.8" />
      </svg>
    )
  }
  if (type === 'cart') {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M3 5h2l1.5 9h10.8l2-6H6" />
        <circle cx="9" cy="18.5" r="1.2" />
        <circle cx="17" cy="18.5" r="1.2" />
      </svg>
    )
  }
  if (type === 'receipt') {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M7 3h10v18l-2-1.4-2 1.4-2-1.4L9 21l-2-1.4V3Z" />
        <path d="M9.5 8h5M9.5 11h5M9.5 14h3.5" />
      </svg>
    )
  }
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M5 7h14M5 12h14M5 17h14" />
    </svg>
  )
}

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

async function loadMobileInventory() {
  const [inventoryResponse, articleGroupsResponse] = await Promise.all([
    fetchJsonWithAuth(`/api/dev/inventory-preview?_ts=${Date.now()}`, { method: 'GET', cache: 'no-store' }),
    fetchJsonWithAuth(`/api/article-groups/household-articles?_ts=${Date.now()}`, { method: 'GET', cache: 'no-store' }),
  ])

  const inventoryData = await inventoryResponse.json().catch(() => ({}))
  if (!inventoryResponse.ok) {
    throw new Error(inventoryData?.detail || 'Voorraad kon niet worden geladen')
  }

  const articleGroupsData = articleGroupsResponse.ok
    ? await articleGroupsResponse.json().catch(() => ({}))
    : {}

  return buildMobileInventoryRows(
    Array.isArray(inventoryData?.rows) ? inventoryData.rows : [],
    Array.isArray(articleGroupsData?.items) ? articleGroupsData.items : [],
  )
}

export default function MobileVoorraad({ locationTrackingEnabled = true }) {
  const navigate = useNavigate()
  const [rows, setRows] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [locationFilter, setLocationFilter] = useState('')
  const [groupFilter, setGroupFilter] = useState('')
  const [sortKey, setSortKey] = useState('name-asc')
  const [mutatingRowId, setMutatingRowId] = useState('')
  const [mutationFeedback, setMutationFeedback] = useState({ type: '', message: '' })
  const context = readStoredAuthContext()
  const canEditInventory = isHouseholdAdminFromContext(context)
  const onboarding = readHouseholdOnboarding(context)
  const features = useFeatureAvailability()
  const actionAvailability = useActionButtonAvailability({
    enabled: Boolean(context && context.context_type !== 'none'),
  })

  const visibility = {
    canOpenAdmin: canEditInventory,
    canOpenExternalDatabases: isFrontteamMemberFromContext(context),
    isPlatformSuperuser: isPlatformSuperuserFromContext(context),
    canManageLocations: canCurrentUserPerform('locations.manage', context),
  }

  const homeNavigation = buildHomeNavigation({
    onboarding,
    visibility,
    features,
    actionButtons: actionAvailability.items,
    actionOrder: actionAvailability.order,
  })

  const availableActionTiles = useMemo(() => {
    const seen = new Set()
    return [...homeNavigation.primaryTiles, ...homeNavigation.moreTiles]
      .filter((tile) => {
        const route = ACTION_ROUTE_BY_KEY[tile.key]
        if (!tile?.clickable || !route || seen.has(tile.key)) return false
        seen.add(tile.key)
        return true
      })
  }, [homeNavigation])

  const recentNavItems = useMemo(() => {
    return selectRecentActionTiles({
      recentKeys: readRecentActionKeys(context),
      availableTiles: availableActionTiles,
      excludeKeys: ['voorraad'],
      limit: 4,
    }).map((tile) => ({
      key: tile.key,
      label: tile.label,
      route: ACTION_ROUTE_BY_KEY[tile.key],
      icon: mobileNavIconType(tile.key),
    }))
  }, [availableActionTiles, context?.user_id])

  const bottomNavItems = [...recentNavItems, MORE_NAV_ITEM]

  async function reload() {
    setIsLoading(true)
    setError('')
    try {
      setRows(await loadMobileInventory())
    } catch (err) {
      setRows([])
      setError(String(err?.message || 'Voorraad kon niet worden geladen'))
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    reload()
  }, [])

  useEffect(() => {
    if (locationTrackingEnabled) return
    setLocationFilter('')
    setSortKey((current) => current === 'location' ? 'name-asc' : current)
  }, [locationTrackingEnabled])

  async function mutateQuickInventory(row, direction) {
    if (!canEditInventory || mutatingRowId) return
    const mutation = buildQuickInventoryMutation(row, direction)
    if (!mutation || !row?.householdArticleId) return

    setMutatingRowId(row.id)
    setMutationFeedback({ type: '', message: '' })
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
      setRows(await loadMobileInventory())
      setMutationFeedback({
        type: 'success',
        message: direction === 'decrease'
          ? `${row.householdName}: 1 afgeboekt.`
          : `${row.householdName}: 1 opgeboekt.`,
      })
    } catch (err) {
      setMutationFeedback({
        type: 'error',
        message: String(err?.message || 'Voorraadmutatie kon niet worden opgeslagen.'),
      })
    } finally {
      setMutatingRowId('')
    }
  }

  const locationOptions = useMemo(() => {
    if (!locationTrackingEnabled) return []
    return [...new Set(rows.map((row) => row.location).filter((value) => value && value !== 'Geen locatie'))]
      .sort((a, b) => a.localeCompare(b, 'nl'))
  }, [locationTrackingEnabled, rows])

  const articleGroupOptions = useMemo(() => {
    return [...new Set(rows.map((row) => row.articleGroup).filter(Boolean))]
      .sort((a, b) => a.localeCompare(b, 'nl'))
  }, [rows])

  const filteredRows = useMemo(() => {
    const needle = normalizeText(query)
    const nextRows = rows.filter((row) => {
      if (locationTrackingEnabled && locationFilter && row.location !== locationFilter) return false
      if (groupFilter && row.articleGroup !== groupFilter) return false
      if (!needle) return true
      const searchableValues = [row.householdName, row.productName, row.articleGroup]
      if (locationTrackingEnabled) searchableValues.push(row.location, row.sublocation)
      return searchableValues.some((value) => normalizeText(value).includes(needle))
    })

    return nextRows.sort((a, b) => {
      if (sortKey === 'name-desc') return b.householdName.localeCompare(a.householdName, 'nl')
      if (locationTrackingEnabled && sortKey === 'location') return a.location.localeCompare(b.location, 'nl') || a.householdName.localeCompare(b.householdName, 'nl')
      return a.householdName.localeCompare(b.householdName, 'nl')
    })
  }, [groupFilter, locationFilter, locationTrackingEnabled, query, rows, sortKey])

  const hasActiveFilters = Boolean(query || groupFilter || (locationTrackingEnabled && locationFilter))

  function clearFilters() {
    setQuery('')
    setLocationFilter('')
    setGroupFilter('')
  }

  const resultSummary = isLoading
    ? 'Voorraad laden…'
    : (filteredRows.length === rows.length
      ? `${rows.length} artikelen`
      : `${filteredRows.length} van ${rows.length} artikelen`)

  return (
    <div
      className="rz-screen rz-mobile-inventory-screen"
      data-testid="mobile-inventory-page"
      data-location-tracking={locationTrackingEnabled ? 'enabled' : 'disabled'}
    >
      <header className="rz-mobile-inventory-topbar" data-testid="mobile-inventory-header">
        <h1>Voorraad</h1>
        <img
          className="rz-mobile-inventory-header-logo"
          src="/inhuis-logo-white.png"
          alt="Inhuis"
          draggable="false"
        />
      </header>

      <main className="rz-mobile-inventory-content">
        <section className="rz-mobile-inventory-toolbar" aria-label="Voorraad zoeken en filteren">
          <label className="rz-mobile-inventory-field rz-mobile-inventory-search">
            <span className="rz-mobile-inventory-label">Zoek</span>
            <input
              className="rz-input"
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
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
                  onChange={setLocationFilter}
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
                onChange={setGroupFilter}
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
                onChange={setSortKey}
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

        {mutationFeedback.message ? (
          <div
            className={`rz-mobile-inventory-quick-feedback rz-mobile-inventory-quick-feedback--${mutationFeedback.type}`}
            role={mutationFeedback.type === 'error' ? 'alert' : 'status'}
            data-testid="mobile-inventory-quick-feedback"
          >
            {mutationFeedback.message}
          </div>
        ) : null}

        {error ? (
          <section className="rz-mobile-inventory-state rz-mobile-inventory-state--error" role="alert">
            <div>{error}</div>
            <Button type="button" variant="secondary" onClick={reload}>Opnieuw proberen</Button>
          </section>
        ) : null}

        {!error && !isLoading && filteredRows.length === 0 ? (
          <section className="rz-mobile-inventory-state">
            <strong>{rows.length === 0 ? 'Nog geen voorraad beschikbaar.' : 'Geen artikelen gevonden.'}</strong>
            {hasActiveFilters ? <span>Pas je zoekopdracht of filters aan.</span> : null}
          </section>
        ) : null}

        {!error && filteredRows.length > 0 ? (
          <section className="rz-mobile-inventory-list" aria-label="Voorraadartikelen">
            {filteredRows.map((row) => {
              const detailTarget = row.detailId
                ? `/voorraad/${encodeURIComponent(row.detailId)}?artikel=${encodeURIComponent(row.articleName || row.householdName)}`
                : ''
              const decreaseTarget = selectQuickInventoryTarget(row, 'decrease')
              const increaseTarget = selectQuickInventoryTarget(row, 'increase')
              const rowBusy = mutatingRowId === row.id

              return (
                <div
                  key={row.id}
                  className={`rz-mobile-inventory-card${detailTarget ? '' : ' rz-mobile-inventory-card--disabled'}`}
                  role={detailTarget ? 'link' : undefined}
                  tabIndex={detailTarget ? 0 : undefined}
                  onClick={() => {
                    if (detailTarget && !rowBusy) navigate(detailTarget)
                  }}
                  onKeyDown={(event) => {
                    if (detailTarget && !rowBusy && (event.key === 'Enter' || event.key === ' ')) {
                      event.preventDefault()
                      navigate(detailTarget)
                    }
                  }}
                  data-testid={detailTarget ? `mobile-inventory-open-detail-${row.detailId}` : undefined}
                >
                  <CatalogArticleThumbnail
                    imageUrl={row.imageUrl}
                    productName={row.productName || row.householdName}
                    className="rz-mobile-inventory-product-thumbnail"
                  />
                  <div className="rz-mobile-inventory-card-main">
                    <div className="rz-mobile-inventory-card-title">{row.householdName}</div>
                    {row.productName && row.productName !== row.householdName ? (
                      <div className="rz-mobile-inventory-card-product">{row.productName}</div>
                    ) : null}
                    <div className="rz-mobile-inventory-card-meta">
                      <span>{row.articleGroup || 'Niet ingedeeld'}</span>
                      {locationTrackingEnabled ? (
                        <span data-testid={`mobile-inventory-location-${row.detailId || row.id}`}>
                          {row.sublocation ? `${row.location} / ${row.sublocation}` : row.location}
                        </span>
                      ) : null}
                    </div>
                  </div>
                  <div className="rz-mobile-inventory-card-side">
                    <div className="rz-mobile-inventory-quantity-control">
                      {canEditInventory ? (
                        <button
                          type="button"
                          className="rz-mobile-inventory-quantity-button"
                          disabled={!decreaseTarget || rowBusy}
                          aria-label={`Boek 1 af van ${row.householdName}`}
                          data-testid={`mobile-inventory-decrease-${row.detailId || row.id}`}
                          onClick={(event) => {
                            event.stopPropagation()
                            mutateQuickInventory(row, 'decrease')
                          }}
                        >
                          −
                        </button>
                      ) : null}
                      <span className="rz-mobile-inventory-quantity" aria-label={`Aantal ${formatQuantity(row.quantity)}`}>
                        {formatQuantity(row.quantity)}
                      </span>
                      {canEditInventory ? (
                        <button
                          type="button"
                          className="rz-mobile-inventory-quantity-button"
                          disabled={!increaseTarget || rowBusy}
                          aria-label={`Boek 1 op bij ${row.householdName}`}
                          data-testid={`mobile-inventory-increase-${row.detailId || row.id}`}
                          onClick={(event) => {
                            event.stopPropagation()
                            mutateQuickInventory(row, 'increase')
                          }}
                        >
                          +
                        </button>
                      ) : null}
                    </div>
                    <span className="rz-mobile-inventory-chevron" aria-hidden="true">›</span>
                  </div>
                </div>
              )
            })}
          </section>
        ) : null}
      </main>

      <nav
        className="rz-mobile-inventory-bottom-nav"
        aria-label="Recent gebruikte acties"
        data-testid="mobile-inventory-bottom-nav"
        style={{ '--rz-mobile-nav-count': bottomNavItems.length }}
      >
        {bottomNavItems.map((item) => {
          return (
            <Link
              key={item.key}
              to={item.route}
              className="rz-mobile-inventory-nav-item"
              data-testid={`mobile-inventory-nav-${item.key}`}
              onClick={() => {
                if (item.key !== 'meer') recordRecentAction(item.key, context)
              }}
            >
              <span className="rz-mobile-inventory-nav-icon"><MobileNavIcon type={item.icon} /></span>
              <span>{item.label}</span>
            </Link>
          )
        })}
      </nav>
    </div>
  )
}

export { buildMobileInventoryRows }
