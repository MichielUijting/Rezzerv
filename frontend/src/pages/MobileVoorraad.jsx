import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import Header from '../ui/Header'
import Button from '../ui/Button'
import { fetchJsonWithAuth } from '../lib/authSession.js'
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

  return (
    <div
      className="rz-screen rz-mobile-inventory-screen"
      data-testid="mobile-inventory-page"
      data-location-tracking={locationTrackingEnabled ? 'enabled' : 'disabled'}
    >
      <Header title="Voorraad" />
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

          <div className={`rz-mobile-inventory-filter-grid${locationTrackingEnabled ? '' : ' rz-mobile-inventory-filter-grid--single'}`}>
            {locationTrackingEnabled ? (
              <label className="rz-mobile-inventory-field" data-testid="mobile-inventory-location-filter">
                <span className="rz-mobile-inventory-label">Locatie</span>
                <select className="rz-input" value={locationFilter} onChange={(event) => setLocationFilter(event.target.value)}>
                  <option value="">Alle locaties</option>
                  {locationOptions.map((option) => <option key={option} value={option}>{option}</option>)}
                </select>
              </label>
            ) : null}
            <label className="rz-mobile-inventory-field">
              <span className="rz-mobile-inventory-label">Artikelgroep</span>
              <select className="rz-input" value={groupFilter} onChange={(event) => setGroupFilter(event.target.value)}>
                <option value="">Alle groepen</option>
                {articleGroupOptions.map((option) => <option key={option} value={option}>{option}</option>)}
              </select>
            </label>
          </div>

          <div className="rz-mobile-inventory-toolbar-row">
            <label className="rz-mobile-inventory-sort">
              <span className="rz-mobile-inventory-label">Sorteren</span>
              <select className="rz-input" value={sortKey} onChange={(event) => setSortKey(event.target.value)}>
                <option value="name">Naam A–Z</option>
                <option value="quantity">Aantal hoog–laag</option>
                {locationTrackingEnabled ? <option value="location">Locatie A–Z</option> : null}
              </select>
            </label>
            {hasActiveFilters ? (
              <Button type="button" variant="secondary" className="rz-mobile-inventory-clear" onClick={clearFilters}>Filters wissen</Button>
            ) : null}
          </div>
        </section>

        <div className="rz-mobile-inventory-summary" aria-live="polite">
          {isLoading ? 'Voorraad laden…' : `${filteredRows.length} van ${rows.length} artikelen`}
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
                    <span className="rz-mobile-inventory-quantity" aria-label={`Aantal ${formatQuantity(row.quantity)}`}>{formatQuantity(row.quantity)}</span>
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

        <div
          className="rz-mobile-inventory-actions"
          style={{ bottom: 'calc(var(--size-app-bar-mobile) + 10px + env(safe-area-inset-bottom))' }}
        >
          <Button
            type="button"
            variant="primary"
            onClick={() => navigate('/voorraad/incidentele-aankoop')}
            data-testid="mobile-inventory-add-incidental-purchase"
          >
            Incidentele aankoop toevoegen
          </Button>
        </div>
      </main>
    </div>
  )
}

export { buildMobileInventoryRows }
