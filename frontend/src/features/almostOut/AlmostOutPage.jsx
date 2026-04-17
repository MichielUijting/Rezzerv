import { useEffect, useMemo, useState } from 'react'
import AppShell from '../../app/AppShell'
import ScreenCard from '../../ui/ScreenCard'
import Table from '../../ui/Table'
import { fetchJsonWithAuth, readStoredAuthContext } from '../../lib/authSession'
import { buildTableWidth, ResizableHeaderCell, useResizableColumnWidths } from '../../ui/resizableTable.jsx'
import { nextSortState, sortItems } from '../../ui/sorting'

function normalizeNumber(value) {
  const number = Number(value)
  return Number.isFinite(number) ? number : 0
}

function formatQuantity(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return '0'
  return Number.isInteger(number) ? String(number) : String(Number(number.toFixed(2)))
}

function buildPackagingLabel(item) {
  const unit = String(item?.packaging_unit || item?.verpakkingseenheid || '').trim()
  const quantity = item?.packaging_quantity ?? item?.verpakkingshoeveelheid
  const normalizedQuantity = Number(quantity)
  if (unit && Number.isFinite(normalizedQuantity) && normalizedQuantity > 0) {
    return `${formatQuantity(normalizedQuantity)} ${unit}`
  }
  if (unit) return unit
  if (Number.isFinite(normalizedQuantity) && normalizedQuantity > 0) return formatQuantity(normalizedQuantity)
  return '—'
}

function buildArticleNames(item) {
  const householdName = String(item?.household_article_name || '').trim()
  const productName = String(item?.product_name || item?.article_name || '').trim()
  const primaryName = householdName || productName || 'Onbekend artikel'
  return {
    primaryName,
    householdName,
    productName,
  }
}

function buildLocationLabel(item) {
  const primary = item?.primary_location && typeof item.primary_location === 'object' ? item.primary_location : null
  const fallback = item?.default_location && typeof item.default_location === 'object' ? item.default_location : null
  const source = primary || fallback
  if (!source) return '—'
  const spaceName = String(source.space_name || source.locatie || '').trim()
  const sublocationName = String(source.sublocation_name || source.sublocatie || '').trim()
  if (spaceName && sublocationName) return `${spaceName} / ${sublocationName}`
  if (spaceName) return spaceName
  if (sublocationName) return sublocationName
  return '—'
}

function normalizeText(value) {
  return String(value || '').trim().toLowerCase()
}

async function resolveHouseholdId() {
  const storedContext = readStoredAuthContext()
  const storedHouseholdId = String(storedContext?.active_household_id || '').trim()
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

export default function AlmostOutPage() {
  const [items, setItems] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')
  const [filters, setFilters] = useState({
    householdName: '',
    productName: '',
    currentQuantity: '',
    minStock: '',
    idealStock: '',
    amountToBuy: '',
    packaging: '',
    location: '',
  })
  const [tableSort, setTableSort] = useState({ key: 'householdName', direction: 'asc' })
  const almostOutTableColumns = useMemo(() => ([
    { key: 'huishoudnaam', width: 220 },
    { key: 'productnaam', width: 260 },
    { key: 'huidig', width: 110 },
    { key: 'minimum', width: 120 },
    { key: 'streef', width: 120 },
    { key: 'kopen', width: 130 },
    { key: 'verpakking', width: 160 },
    { key: 'locatie', width: 220 },
  ]), [])
  const columnDefaults = useMemo(() => Object.fromEntries(almostOutTableColumns.map(({ key, width }) => [key, width])), [almostOutTableColumns])
  const { widths: tableWidths, startResize: startTableResize } = useResizableColumnWidths(columnDefaults)

  useEffect(() => {
    let cancelled = false

    async function loadAlmostOut() {
      setIsLoading(true)
      setError('')
      try {
        const householdId = await resolveHouseholdId()
        if (cancelled) return
        const response = await fetchJsonWithAuth(`/api/households/${encodeURIComponent(householdId)}/almost-out`, { method: 'GET' })
        const data = await response.json().catch(() => ({}))
        if (!response.ok) {
          throw new Error(data?.detail || 'Bijna-op-artikelen konden niet worden geladen')
        }
        const nextItems = Array.isArray(data?.items) ? data.items : []
        if (!cancelled) setItems(nextItems)
      } catch (err) {
        if (!cancelled) {
          setError(String(err?.message || 'Bijna-op-artikelen konden niet worden geladen'))
          setItems([])
        }
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }

    loadAlmostOut()
    return () => { cancelled = true }
  }, [])

  const rows = useMemo(() => {
    return (items || []).map((item) => ({
      id: String(item?.household_article_id || item?.article_id || item?.article_name || Math.random()),
      ...buildArticleNames(item),
      currentQuantity: normalizeNumber(item?.current_quantity ?? item?.huidige_voorraad),
      minStock: normalizeNumber(item?.min_stock ?? item?.minimumvoorraad),
      idealStock: normalizeNumber(item?.ideal_stock ?? item?.streefvoorraad),
      amountToBuy: normalizeNumber(item?.amount_to_buy ?? item?.aantal_te_kopen),
      packaging: buildPackagingLabel(item),
      location: buildLocationLabel(item),
    }))
  }, [items])

  const filteredRows = useMemo(() => {
    const filtered = rows.filter((row) => {
      if (filters.householdName && !normalizeText(row.householdName).includes(normalizeText(filters.householdName))) return false
      if (filters.productName && !normalizeText(row.productName).includes(normalizeText(filters.productName))) return false
      if (filters.currentQuantity && !normalizeText(formatQuantity(row.currentQuantity)).includes(normalizeText(filters.currentQuantity))) return false
      if (filters.minStock && !normalizeText(formatQuantity(row.minStock)).includes(normalizeText(filters.minStock))) return false
      if (filters.idealStock && !normalizeText(formatQuantity(row.idealStock)).includes(normalizeText(filters.idealStock))) return false
      if (filters.amountToBuy && !normalizeText(formatQuantity(row.amountToBuy)).includes(normalizeText(filters.amountToBuy))) return false
      if (filters.packaging && !normalizeText(row.packaging).includes(normalizeText(filters.packaging))) return false
      if (filters.location && !normalizeText(row.location).includes(normalizeText(filters.location))) return false
      return true
    })

    return sortItems(filtered, tableSort, {
      householdName: (row) => row.householdName || row.primaryName || '',
      productName: (row) => row.productName || '',
      currentQuantity: (row) => Number(row.currentQuantity ?? 0),
      minStock: (row) => Number(row.minStock ?? 0),
      idealStock: (row) => Number(row.idealStock ?? 0),
      amountToBuy: (row) => Number(row.amountToBuy ?? 0),
      packaging: (row) => row.packaging || '',
      location: (row) => row.location || '',
    })
  }, [filters, rows, tableSort])

  function handleFilterChange(key, value) {
    setFilters((current) => ({ ...current, [key]: value }))
  }

  return (
    <AppShell title="Bijna op" showExit={false}>
      <div style={{ display: 'grid', gap: '16px' }} data-testid="almost-out-page">
        <ScreenCard>
          {error ? <div className="rz-inline-feedback rz-inline-feedback--error" style={{ marginBottom: '12px' }}>{error}</div> : null}
          <Table tableClassName="rz-stock-table" dataTestId="almost-out-table" tableStyle={{ tableLayout: 'fixed', width: buildTableWidth(tableWidths), minWidth: buildTableWidth(tableWidths) }}>
              <colgroup>
                <col style={{ width: `${tableWidths.huishoudnaam}px` }} />
                <col style={{ width: `${tableWidths.productnaam}px` }} />
                <col style={{ width: `${tableWidths.huidig}px` }} />
                <col style={{ width: `${tableWidths.minimum}px` }} />
                <col style={{ width: `${tableWidths.streef}px` }} />
                <col style={{ width: `${tableWidths.kopen}px` }} />
                <col style={{ width: `${tableWidths.verpakking}px` }} />
                <col style={{ width: `${tableWidths.locatie}px` }} />
              </colgroup>
              <thead>
                <tr className="rz-table-header">
                  <ResizableHeaderCell columnKey="huishoudnaam" widths={tableWidths} onStartResize={startTableResize} sortable isSorted={tableSort.key === 'householdName'} sortDirection={tableSort.direction} onSort={() => setTableSort((current) => nextSortState(current, 'householdName', { householdName: 'asc', productName: 'asc', currentQuantity: 'desc', minStock: 'asc', idealStock: 'asc', amountToBuy: 'desc', packaging: 'asc', location: 'asc' }))}>Huishoudnaam</ResizableHeaderCell>
                  <ResizableHeaderCell columnKey="productnaam" widths={tableWidths} onStartResize={startTableResize} sortable isSorted={tableSort.key === 'productName'} sortDirection={tableSort.direction} onSort={() => setTableSort((current) => nextSortState(current, 'productName', { householdName: 'asc', productName: 'asc', currentQuantity: 'desc', minStock: 'asc', idealStock: 'asc', amountToBuy: 'desc', packaging: 'asc', location: 'asc' }))}>Productnaam</ResizableHeaderCell>
                  <ResizableHeaderCell columnKey="huidig" widths={tableWidths} onStartResize={startTableResize} className="rz-num" sortable isSorted={tableSort.key === 'currentQuantity'} sortDirection={tableSort.direction} onSort={() => setTableSort((current) => nextSortState(current, 'currentQuantity', { householdName: 'asc', productName: 'asc', currentQuantity: 'desc', minStock: 'asc', idealStock: 'asc', amountToBuy: 'desc', packaging: 'asc', location: 'asc' }))}>Huidig</ResizableHeaderCell>
                  <ResizableHeaderCell columnKey="minimum" widths={tableWidths} onStartResize={startTableResize} className="rz-num" sortable isSorted={tableSort.key === 'minStock'} sortDirection={tableSort.direction} onSort={() => setTableSort((current) => nextSortState(current, 'minStock', { householdName: 'asc', productName: 'asc', currentQuantity: 'desc', minStock: 'asc', idealStock: 'asc', amountToBuy: 'desc', packaging: 'asc', location: 'asc' }))}>Minimum</ResizableHeaderCell>
                  <ResizableHeaderCell columnKey="streef" widths={tableWidths} onStartResize={startTableResize} className="rz-num" sortable isSorted={tableSort.key === 'idealStock'} sortDirection={tableSort.direction} onSort={() => setTableSort((current) => nextSortState(current, 'idealStock', { householdName: 'asc', productName: 'asc', currentQuantity: 'desc', minStock: 'asc', idealStock: 'asc', amountToBuy: 'desc', packaging: 'asc', location: 'asc' }))}>Streef</ResizableHeaderCell>
                  <ResizableHeaderCell columnKey="kopen" widths={tableWidths} onStartResize={startTableResize} className="rz-num" sortable isSorted={tableSort.key === 'amountToBuy'} sortDirection={tableSort.direction} onSort={() => setTableSort((current) => nextSortState(current, 'amountToBuy', { householdName: 'asc', productName: 'asc', currentQuantity: 'desc', minStock: 'asc', idealStock: 'asc', amountToBuy: 'desc', packaging: 'asc', location: 'asc' }))}>Te kopen</ResizableHeaderCell>
                  <ResizableHeaderCell columnKey="verpakking" widths={tableWidths} onStartResize={startTableResize} sortable isSorted={tableSort.key === 'packaging'} sortDirection={tableSort.direction} onSort={() => setTableSort((current) => nextSortState(current, 'packaging', { householdName: 'asc', productName: 'asc', currentQuantity: 'desc', minStock: 'asc', idealStock: 'asc', amountToBuy: 'desc', packaging: 'asc', location: 'asc' }))}>Verpakking</ResizableHeaderCell>
                  <ResizableHeaderCell columnKey="locatie" widths={tableWidths} onStartResize={startTableResize} sortable isSorted={tableSort.key === 'location'} sortDirection={tableSort.direction} onSort={() => setTableSort((current) => nextSortState(current, 'location', { householdName: 'asc', productName: 'asc', currentQuantity: 'desc', minStock: 'asc', idealStock: 'asc', amountToBuy: 'desc', packaging: 'asc', location: 'asc' }))}>Locatie</ResizableHeaderCell>
                </tr>
                <tr className="rz-table-filters">
                  <th><input value={filters.householdName} onChange={(event) => handleFilterChange('householdName', event.target.value)} placeholder="Filter" /></th>
                  <th><input value={filters.productName} onChange={(event) => handleFilterChange('productName', event.target.value)} placeholder="Filter" /></th>
                  <th className="rz-num"><input value={filters.currentQuantity} onChange={(event) => handleFilterChange('currentQuantity', event.target.value)} placeholder="Filter" /></th>
                  <th className="rz-num"><input value={filters.minStock} onChange={(event) => handleFilterChange('minStock', event.target.value)} placeholder="Filter" /></th>
                  <th className="rz-num"><input value={filters.idealStock} onChange={(event) => handleFilterChange('idealStock', event.target.value)} placeholder="Filter" /></th>
                  <th className="rz-num"><input value={filters.amountToBuy} onChange={(event) => handleFilterChange('amountToBuy', event.target.value)} placeholder="Filter" /></th>
                  <th><input value={filters.packaging} onChange={(event) => handleFilterChange('packaging', event.target.value)} placeholder="Filter" /></th>
                  <th><input value={filters.location} onChange={(event) => handleFilterChange('location', event.target.value)} placeholder="Filter" /></th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr><td colSpan={8}>Bijna-op-artikelen laden…</td></tr>
                ) : filteredRows.length === 0 ? (
                  <tr><td colSpan={8}>Er zijn op dit moment geen artikelen die aangevuld moeten worden.</td></tr>
                ) : filteredRows.map((row) => (
                  <tr key={row.id}>
                    <td title={row.householdName || '—'}>{row.householdName || '—'}</td>
                    <td title={row.productName || row.primaryName}>{row.productName || row.primaryName}</td>
                    <td className="rz-num">{formatQuantity(row.currentQuantity)}</td>
                    <td className="rz-num">{formatQuantity(row.minStock)}</td>
                    <td className="rz-num">{formatQuantity(row.idealStock)}</td>
                    <td className="rz-num">{formatQuantity(row.amountToBuy)}</td>
                    <td title={row.packaging}>{row.packaging}</td>
                    <td title={row.location}>{row.location}</td>
                  </tr>
                ))}
              </tbody>
            </Table>
        </ScreenCard>
      </div>
    </AppShell>
  )
}
