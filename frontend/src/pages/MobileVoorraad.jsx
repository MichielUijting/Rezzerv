import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import Button from '../ui/Button'
import Select from '../ui/Select.jsx'
import CatalogArticleThumbnail from '../ui/CatalogArticleThumbnail.jsx'
import { fetchJsonWithAuth } from '../lib/authSession.js'
import './mobileVoorraad.css'

const MOBILE_NAV_ITEMS = [
  { key: 'meldingen', label: 'Meldingen', route: '/meldingen', icon: 'bell' },
  { key: 'voorraad', label: 'Voorraad', route: '/voorraad', icon: 'inventory' },
  { key: 'bijna-op', label: 'Bijna op', route: '/bijna-op', icon: 'clock' },
  { key: 'winkelen', label: 'Winkelen', route: '/winkelen', icon: 'cart' },
  { key: 'meer', label: 'Meer', route: '/home', icon: 'menu' },
]

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
        locations: new Set(location ? [location] : []),
        sublocations: new Set(sublocation ? [`${location}__${sublocation}`] : []),
        firstSeenIndex: index,
      })
      return
    }

    existing.quantity += quantity
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
  const [sortKey, setSortKey] = useState('name')

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
    setSortKey((current) => current === 'location' ? 'name' : current)
  }, [locationTrackingEnabled])

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
      if (sortKey === 'quantity') return b.quantity - a.quantity || a.householdName.localeCompare(b.householdName, 'nl')
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
                  { value: 'name', label: 'Naam A–Z' },
                  { value: 'quantity', label: 'Aantal hoog–laag' },
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
              const content = (
                <>
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
                    <span className="rz-mobile-inventory-quantity" aria-label={`Aantal ${formatQuantity(row.quantity)}`}>
                      {formatQuantity(row.quantity)}
                    </span>
                    <span className="rz-mobile-inventory-chevron" aria-hidden="true">›</span>
                  </div>
                </>
              )

              return detailTarget ? (
                <Link
                  key={row.id}
                  to={detailTarget}
                  className="rz-mobile-inventory-card"
                  data-testid={`mobile-inventory-open-detail-${row.detailId}`}
                >
                  {content}
                </Link>
              ) : (
                <div key={row.id} className="rz-mobile-inventory-card rz-mobile-inventory-card--disabled">
                  {content}
                </div>
              )
            })}
          </section>
        ) : null}
      </main>

      <nav className="rz-mobile-inventory-bottom-nav" aria-label="Hoofdnavigatie" data-testid="mobile-inventory-bottom-nav">
        {MOBILE_NAV_ITEMS.map((item) => {
          const active = item.key === 'voorraad'
          return (
            <Link
              key={item.key}
              to={item.route}
              className={`rz-mobile-inventory-nav-item${active ? ' is-active' : ''}`}
              aria-current={active ? 'page' : undefined}
              data-testid={`mobile-inventory-nav-${item.key}`}
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
