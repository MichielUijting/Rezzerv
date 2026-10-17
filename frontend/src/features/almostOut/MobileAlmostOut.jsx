import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import MobileModuleHeader from '../../ui/MobileModuleHeader.jsx'
import Button from '../../ui/Button'
import Select from '../../ui/Select.jsx'
import CatalogArticleThumbnail from '../../ui/CatalogArticleThumbnail.jsx'
import { MobilePaginationControls, useMobilePagination } from '../../ui/MobilePagination.jsx'
import { fetchJsonWithAuth, readStoredAuthContext } from '../../lib/authSession.js'
import {
  buildMobileAlmostOutRows,
  formatAlmostOutQuantity,
  normalizeAlmostOutText,
} from './mobileAlmostOutModel.js'
import '../../pages/mobileVoorraad.css'
import { exportAlmostOutRows, moveAlmostOutToShopping, hideAlmostOutRows, restoreAlmostOutRows } from './almostOutBulk.js'

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
  const [selectedIds, setSelectedIds] = useState([])
  const [bulkBusy, setBulkBusy] = useState(false)
  const [bulkMessage, setBulkMessage] = useState('')
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
    if (readStoredAuthContext()?.context_type !== 'regular') {
      setIsLoading(false)
      return
    }
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
      const searchableValues = [row.householdName, row.primaryName, row.productName, row.packaging, row.gpcBrickName, row.gpcClassName, row.gpcFamilyName]
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

  const almostOutPagination = useMobilePagination(
    filteredRows,
    [query, locationFilter, sortKey, locationTrackingEnabled].join('|'),
  )
  const hasActiveFilters = Boolean(query || (locationTrackingEnabled && locationFilter))

  const currentPageIds = almostOutPagination.pageItems.map((row) => row.id)
  const pageSelected = currentPageIds.length > 0 && currentPageIds.every((id) => selectedIds.includes(id))
  const selectedRows = rows.filter((row) => selectedIds.includes(row.id))
  function toggleSelected(id) {
    setSelectedIds((current) => current.includes(id) ? current.filter((value) => value !== id) : [...current, id])
  }
  function togglePageSelection() {
    setSelectedIds((current) => pageSelected
      ? current.filter((id) => !currentPageIds.includes(id))
      : [...new Set([...current, ...currentPageIds])])
  }

  async function handleBulkAction(action) {
    if (bulkBusy || (action !== 'restore' && !selectedRows.length)) return
    if (action === 'export') return exportAlmostOutRows(selectedRows)
    if (action === 'hide' && !window.confirm(`Verwijder ${selectedRows.length} melding(en) uit Bijna op? De voorraad blijft bewaard. Verborgen meldingen zijn herstelbaar.`)) return
    setBulkBusy(true)
    setError('')
    setBulkMessage('')
    try {
      if (action === 'shopping') {
        const total = await moveAlmostOutToShopping(selectedRows)
        setBulkMessage(`${total} artikel(en) naar Boodschappen overgezet en uit Bijna op verwijderd.`)
      } else {
        if (action === 'hide') await hideAlmostOutRows(selectedRows)
        else await restoreAlmostOutRows()
        setRows(await loadMobileAlmostOut())
        setSelectedIds([])
        setBulkMessage(action === 'hide' ? 'Meldingen verborgen, voorraad behouden.' : 'Verwijderingen ongedaan gemaakt.')
      }
    } catch (err) {
      setError(String(err?.message || 'Bulkverwerking mislukt'))
    } finally {
      // Reconcile the view also when part of a batch transfer succeeded.
      if (action === 'shopping') {
        try {
          setRows(await loadMobileAlmostOut())
          setSelectedIds([])
        } catch {
          // Preserve the actionable transfer error.
        }
      }
      setBulkBusy(false)
    }
  }

  function clearFilters() {
    setQuery('')
    setLocationFilter('')
  }

  // Platform/Superuser sessions have no household inventory scope.
  if (readStoredAuthContext()?.context_type !== 'regular') {
    return (
      <div className="rz-screen rz-mobile-inventory-screen" data-testid="mobile-almost-out-page">
        <MobileModuleHeader title="Bijna op" testId="mobile-almost-out-header" />
        <main className="rz-mobile-inventory-content">
          <section className="rz-mobile-inventory-state" role="status">
            Bijna op is alleen beschikbaar binnen een geselecteerd huishouden.
          </section>
        </main>
      </div>
    )
  }

  return (
    <div
      className="rz-screen rz-mobile-inventory-screen"
      data-testid="mobile-almost-out-page"
      data-almost-out-location-tracking={locationTrackingEnabled ? 'enabled' : 'disabled'}
    >
      <MobileModuleHeader title="Bijna op" testId="mobile-almost-out-header" />
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
          {isLoading && rows.length === 0 ? 'Bijna-op-artikelen laden…' : `${filteredRows.length} van ${rows.length} artikelen`}
        </div>

        {bulkMessage ? <div role="status" className="rz-mobile-inventory-state">{bulkMessage}</div> : null}
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

        <section className="rz-mobile-inventory-toolbar rz-mobile-almost-out-bulk-top" aria-label="Bijna op selectie en verwijderen" style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <label style={{ display: 'inline-flex', gap: 7, alignItems: 'center' }}><input type="checkbox" checked={pageSelected} onChange={togglePageSelection} disabled={bulkBusy || !currentPageIds.length} /> Alles op pagina</label>
          <Button type="button" variant="secondary" disabled={!selectedRows.length || bulkBusy} onClick={() => handleBulkAction('hide')}>Verwijderen</Button>
        </section>
        {!error && filteredRows.length > 0 ? (
          <section className="rz-mobile-inventory-list" aria-label="Bijna-op-artikelen" aria-busy={isLoading} style={{ pointerEvents: isLoading ? 'none' : undefined }}>
            {almostOutPagination.pageItems.map((row) => {
              const title = row.householdName || row.primaryName
              const contextParts = []
              if (row.productName && row.productName !== title) contextParts.push(row.productName)
              if (row.packaging && row.packaging !== '—') contextParts.push(row.packaging)
              if (row.gpcBrickName) contextParts.push(`Brick: ${row.gpcBrickName}`)
              if (row.gpcClassName) contextParts.push(`GPC-groep: ${row.gpcClassName}`)
              if (row.gpcFamilyName) contextParts.push(`GPC-familie: ${row.gpcFamilyName}`)

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

                  </div>
                </>
              )

              const detailTarget = row.detailId
                ? `/voorraad/${encodeURIComponent(row.detailId)}?artikel=${encodeURIComponent(title)}`
                : ''

              return <div key={row.id} style={{ display: 'grid', gap: 6 }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 8px' }}>
                  <input type="checkbox" aria-label={`Selecteer ${title}`} checked={selectedIds.includes(row.id)} disabled={bulkBusy} onChange={() => toggleSelected(row.id)} />
                  Selecteren
                </label>
                {detailTarget ? (
                <Link
                  to={detailTarget}
                  className="rz-mobile-inventory-card"
                  data-testid={`mobile-almost-out-open-detail-${row.detailId}`}
                >
                  {content}
                </Link>
              ) : (
                <div className="rz-mobile-inventory-card rz-mobile-inventory-card--disabled">
                  {content}
                </div>
              )}
              </div>
            })}
          </section>
        ) : null}
        <MobilePaginationControls {...almostOutPagination} ariaLabel="Paginering Bijna op" />
        <section className="rz-mobile-inventory-state" aria-label="Overige Bijna op bulkacties" style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <Button type="button" variant="secondary" disabled={!selectedRows.length || bulkBusy} onClick={() => handleBulkAction('export')}>Exporteren</Button>
          <Button type="button" disabled={!selectedRows.length || bulkBusy} onClick={() => handleBulkAction('shopping')}>Naar Boodschappenlijst</Button>
        </section>
      </main>
      <div className="rz-mobile-almost-out-undo" style={{ padding: '8px 12px 16px', display: 'flex', justifyContent: 'flex-end' }}>
        <Button type="button" variant="secondary" disabled={bulkBusy} onClick={() => handleBulkAction('restore')}>Verwijderingen ongedaan maken</Button>
      </div>
    </div>
  )
}
