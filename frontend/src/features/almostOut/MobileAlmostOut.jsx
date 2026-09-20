import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import Header from '../../ui/Header'
import Button from '../../ui/Button'
import Select from '../../ui/Select.jsx'
import CatalogArticleThumbnail from '../../ui/CatalogArticleThumbnail.jsx'
import { fetchJsonWithAuth, readStoredAuthContext } from '../../lib/authSession.js'
import {
  buildMobileAlmostOutRows,
  formatAlmostOutQuantity,
  normalizeAlmostOutText,
} from './mobileAlmostOutModel.js'
import '../../pages/mobileVoorraad.css'

async function resolveHouseholdId() {
  const storedContext = readStoredAuthContext()
  const storedHouseholdId = String(storedContext?.active_household_id ?? '').trim()
  if (storedHouseholdId) return storedHouseholdId

  const response = await fetchJsonWithAuth('/api/household', { method: 'GET' })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(data?.detail || 'Huishouden kon niet worden geladen')
  }
  const resolvedHouseholdId = String(data?.id || '').trim()
  if (!resolvedHouseholdId) throw new Error('Huishouden kon niet worden geladen')
  return resolvedHouseholdId
}

async function loadMobileAlmostOut() {
  const householdId = await resolveHouseholdId()
  const response = await fetchJsonWithAuth(
    `/api/households/${encodeURIComponent(householdId)}/almost-out`,
    { method: 'GET', cache: 'no-store' },
  )
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(data?.detail || 'Bijna-op-artikelen konden niet worden geladen')
  }
  return buildMobileAlmostOutRows(Array.isArray(data?.items) ? data.items : [])
}

export default function MobileAlmostOut({ locationTrackingEnabled = true }) {
  const [rows, setRows] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [locationFilter, setLocationFilter] = useState('')
  const [sortKey, setSortKey] = useState('amountToBuy')

  async function reload() {
    setIsLoading(true)
    setError('')
    try {
      setRows(await loadMobileAlmostOut())
    } catch (err) {
      setRows([])
      setError(String(err?.message || 'Bijna-op-artikelen konden niet worden geladen'))
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
    setSortKey((current) => current === 'location' ? 'amountToBuy' : current)
  }, [locationTrackingEnabled])

  const locationOptions = useMemo(() => {
    if (!locationTrackingEnabled) return []
    return [...new Set(rows.map((row) => row.location).filter((value) => value && value !== '—'))]
      .sort((a, b) => a.localeCompare(b, 'nl'))
  }, [locationTrackingEnabled, rows])

  const filteredRows = useMemo(() => {
    const needle = normalizeAlmostOutText(query)
    const nextRows = rows.filter((row) => {
      if (locationTrackingEnabled && locationFilter && row.location !== locationFilter) return false
      if (!needle) return true
      const searchableValues = [row.householdName, row.primaryName, row.productName, row.packaging]
      if (locationTrackingEnabled) searchableValues.push(row.location)
      return searchableValues.some((value) => normalizeAlmostOutText(value).includes(needle))
    })

    return nextRows.sort((a, b) => {
      if (sortKey === 'amountToBuy') {
        return b.amountToBuy - a.amountToBuy || a.primaryName.localeCompare(b.primaryName, 'nl')
      }
      if (sortKey === 'currentQuantity') {
        return a.currentQuantity - b.currentQuantity || a.primaryName.localeCompare(b.primaryName, 'nl')
      }
      if (locationTrackingEnabled && sortKey === 'location') {
        return a.location.localeCompare(b.location, 'nl') || a.primaryName.localeCompare(b.primaryName, 'nl')
      }
      return a.primaryName.localeCompare(b.primaryName, 'nl')
    })
  }, [locationFilter, locationTrackingEnabled, query, rows, sortKey])

  const hasActiveFilters = Boolean(query || (locationTrackingEnabled && locationFilter))

  function clearFilters() {
    setQuery('')
    setLocationFilter('')
  }

  return (
    <div
      className="rz-screen rz-mobile-inventory-screen"
      data-testid="mobile-almost-out-page"
      data-almost-out-location-tracking={locationTrackingEnabled ? 'enabled' : 'disabled'}
    >
      <Header title="Bijna op" />
      <main className="rz-mobile-inventory-content">
        <section className="rz-mobile-inventory-toolbar" aria-label="Bijna op zoeken en filteren">
          <label className="rz-mobile-inventory-field rz-mobile-inventory-search">
            <span className="rz-mobile-inventory-label">Zoek</span>
            <input
              className="rz-input"
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={locationTrackingEnabled ? 'Zoek artikel, product of locatie' : 'Zoek artikel of product'}
              autoComplete="off"
            />
          </label>

          {locationTrackingEnabled ? (
            <div className="rz-mobile-inventory-filter-grid rz-mobile-inventory-filter-grid--single">
              <div className="rz-mobile-inventory-field" data-testid="mobile-almost-out-location-filter">
                <span id="mobile-almost-out-location-label" className="rz-mobile-inventory-label">Locatie</span>
                <Select
                  ariaLabelledby="mobile-almost-out-location-label"
                  value={locationFilter}
                  onChange={setLocationFilter}
                  options={[
                    { value: '', label: 'Alle locaties' },
                    ...locationOptions.map((option) => ({ value: option, label: option })),
                  ]}
                />
              </div>
            </div>
          ) : null}

          <div className="rz-mobile-inventory-toolbar-row">
            <div className="rz-mobile-inventory-sort">
              <span id="mobile-almost-out-sort-label" className="rz-mobile-inventory-label">Sorteren</span>
              <Select
                ariaLabelledby="mobile-almost-out-sort-label"
                value={sortKey}
                onChange={setSortKey}
                options={[
                  { value: 'amountToBuy', label: 'Te kopen hoog–laag' },
                  { value: 'name', label: 'Naam A–Z' },
                  { value: 'currentQuantity', label: 'Huidig laag–hoog' },
                  ...(locationTrackingEnabled ? [{ value: 'location', label: 'Locatie A–Z' }] : []),
                ]}
              />
            </div>
            {hasActiveFilters ? (
              <Button type="button" variant="secondary" className="rz-mobile-inventory-clear" onClick={clearFilters}>
                Filters wissen
              </Button>
            ) : null}
          </div>
        </section>

        <div className="rz-mobile-inventory-summary" aria-live="polite">
          {isLoading ? 'Bijna-op-artikelen laden…' : `${filteredRows.length} van ${rows.length} artikelen`}
        </div>

        {error ? (
          <section className="rz-mobile-inventory-state rz-mobile-inventory-state--error" role="alert">
            <div>{error}</div>
            <Button type="button" variant="secondary" onClick={reload}>Opnieuw proberen</Button>
          </section>
        ) : null}

        {!error && !isLoading && filteredRows.length === 0 ? (
          <section className="rz-mobile-inventory-state">
            <strong>
              {rows.length === 0
                ? 'Er zijn op dit moment geen artikelen die aangevuld moeten worden.'
                : 'Geen artikelen gevonden.'}
            </strong>
            {hasActiveFilters ? <span>Pas je zoekopdracht of filters aan.</span> : null}
          </section>
        ) : null}

        {!error && filteredRows.length > 0 ? (
          <section className="rz-mobile-inventory-list" aria-label="Bijna-op-artikelen">
            {filteredRows.map((row) => {
              const title = row.householdName || row.primaryName
              const contextParts = []
              if (row.productName && row.productName !== title) contextParts.push(row.productName)
              if (row.packaging && row.packaging !== '—') contextParts.push(row.packaging)

              const content = (
                <>
                  <CatalogArticleThumbnail
                    imageUrl={row.imageUrl}
                    productName={row.productName || title}
                    className="rz-mobile-inventory-product-thumbnail"
                  />
                  <div className="rz-mobile-inventory-card-main">
                    <div className="rz-mobile-inventory-card-title">{title}</div>
                    {contextParts.length > 0 ? (
                      <div className="rz-mobile-inventory-card-product">{contextParts.join(' • ')}</div>
                    ) : null}
                    <div className="rz-mobile-inventory-card-meta">
                      <span>Huidig {formatAlmostOutQuantity(row.currentQuantity)}</span>
                      <span>Minimum {formatAlmostOutQuantity(row.minStock)}</span>
                      <span>Streef {formatAlmostOutQuantity(row.idealStock)}</span>
                      {locationTrackingEnabled && row.location !== '—' ? <span>{row.location}</span> : null}
                    </div>
                  </div>
                  <div className="rz-mobile-inventory-card-side">
                    <span
                      className="rz-mobile-inventory-quantity"
                      aria-label={`Te kopen ${formatAlmostOutQuantity(row.amountToBuy)}`}
                    >
                      Te kopen {formatAlmostOutQuantity(row.amountToBuy)}
                    </span>
                    <span className="rz-mobile-inventory-chevron" aria-hidden="true">›</span>
                  </div>
                </>
              )

              const detailTarget = row.detailId
                ? `/voorraad/${encodeURIComponent(row.detailId)}?artikel=${encodeURIComponent(title)}`
                : ''

              return detailTarget ? (
                <Link
                  key={row.id}
                  to={detailTarget}
                  className="rz-mobile-inventory-card"
                  data-testid={`mobile-almost-out-open-detail-${row.detailId}`}
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
    </div>
  )
}
