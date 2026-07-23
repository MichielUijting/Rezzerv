import { useEffect, useMemo, useState } from 'react'
import AppShell from '../../app/AppShell'
import ScreenCard from '../../ui/ScreenCard'
import Table from '../../ui/Table'
import { fetchJsonWithAuth } from '../../lib/authSession'
import { nextSortState, sortItems } from '../../ui/sorting'

function normalizeText(value) {
  return String(value || '').trim().toLowerCase()
}

function formatNumber(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return '0,00'
  return number.toLocaleString('nl-NL', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatMoney(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return '€ 0,00'
  return number.toLocaleString('nl-NL', { style: 'currency', currency: 'EUR' })
}

function programLabel(code) {
  const text = String(code || '').trim()
  if (!text) return 'Onbekend spaarprogramma'
  return text
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function csvCell(value) {
  const text = String(value ?? '')
  return `"${text.replace(/"/g, '""')}"`
}

export default function LoyaltyStampsPage() {
  const [programs, setPrograms] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')
  const [filters, setFilters] = useState({
    storeName: '',
    programName: '',
    purchasedQuantity: '',
    paidAmount: '',
  })
  const [selectedIds, setSelectedIds] = useState([])
  const [sort, setSort] = useState({ key: 'storeName', direction: 'asc' })

  useEffect(() => {
    let cancelled = false

    async function loadPrograms() {
      setIsLoading(true)
      setError('')
      try {
        const response = await fetchJsonWithAuth('/api/loyalty-stamps/programs', { method: 'GET' })
        const data = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(data?.detail || 'Spaartegoeden konden niet worden geladen')
        if (!cancelled) setPrograms(Array.isArray(data?.programs) ? data.programs : [])
      } catch (err) {
        if (!cancelled) {
          setPrograms([])
          setError(String(err?.message || 'Spaartegoeden konden niet worden geladen'))
        }
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }

    loadPrograms()
    return () => { cancelled = true }
  }, [])

  const rows = useMemo(() => programs.map((item) => ({
    id: `${item?.store_name || ''}:${item?.stamp_program_code || ''}`,
    storeName: String(item?.store_name || '').trim() || 'Onbekende winkelketen',
    programCode: String(item?.stamp_program_code || '').trim(),
    programName: programLabel(item?.stamp_program_code),
    purchasedQuantity: Number(item?.purchased_quantity || 0),
    paidAmount: Number(item?.paid_amount || 0),
  })), [programs])

  const programOptions = useMemo(() => (
    [...new Set(rows.map((row) => row.programName))].sort((left, right) => left.localeCompare(right, 'nl-NL'))
  ), [rows])

  const visibleRows = useMemo(() => {
    const storeNeedle = normalizeText(filters.storeName)
    const quantityNeedle = normalizeText(filters.purchasedQuantity)
    const amountNeedle = normalizeText(filters.paidAmount)

    const filtered = rows.filter((row) => {
      if (storeNeedle && !normalizeText(row.storeName).includes(storeNeedle)) return false
      if (filters.programName && row.programName !== filters.programName) return false
      if (quantityNeedle && !normalizeText(formatNumber(row.purchasedQuantity)).includes(quantityNeedle)) return false
      if (amountNeedle && !normalizeText(formatMoney(row.paidAmount)).includes(amountNeedle)) return false
      return true
    })

    return sortItems(filtered, sort, {
      storeName: (row) => row.storeName,
      programName: (row) => row.programName,
      purchasedQuantity: (row) => row.purchasedQuantity,
      paidAmount: (row) => row.paidAmount,
    })
  }, [filters, rows, sort])

  const selectedRows = useMemo(() => {
    const selectedSet = new Set(selectedIds)
    return rows.filter((row) => selectedSet.has(row.id))
  }, [rows, selectedIds])

  const allVisibleSelected = visibleRows.length > 0 && visibleRows.every((row) => selectedIds.includes(row.id))

  function updateFilter(key, value) {
    setFilters((current) => ({ ...current, [key]: value }))
  }

  function toggleRow(rowId) {
    setSelectedIds((current) => (
      current.includes(rowId)
        ? current.filter((id) => id !== rowId)
        : [...current, rowId]
    ))
  }

  function toggleAllVisible() {
    const visibleIds = visibleRows.map((row) => row.id)
    setSelectedIds((current) => {
      if (allVisibleSelected) return current.filter((id) => !visibleIds.includes(id))
      return [...new Set([...current, ...visibleIds])]
    })
  }

  function exportSelected() {
    if (selectedRows.length === 0) return

    const lines = [
      ['Winkelketen', 'Spaarprogramma', 'Aantal zegels', 'Betaald bedrag'],
      ...selectedRows.map((row) => [
        row.storeName,
        row.programName,
        formatNumber(row.purchasedQuantity),
        formatMoney(row.paidAmount),
      ]),
    ]
    const csv = `\uFEFF${lines.map((line) => line.map(csvCell).join(';')).join('\r\n')}`
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = 'rezzerv-spaartegoeden.csv'
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    URL.revokeObjectURL(url)
  }

  return (
    <AppShell title="Spaartegoeden" showExit={false}>
      <div data-testid="loyalty-stamps-page">
        <ScreenCard>
          <div style={{ marginBottom: '12px' }}>
            <h2 style={{ margin: 0 }}>Spaar- en koopzegels</h2>
            <p style={{ margin: '4px 0 0' }}>Read-only overzicht van aantoonbaar aangekochte spaartegoeden.</p>
          </div>

          <div style={{ display: 'flex', gap: '8px', marginBottom: '12px' }}>
            <button
              type="button"
              className="rz-button"
              disabled={selectedRows.length === 0}
              onClick={exportSelected}
            >
              Exporteren
            </button>
          </div>

          {error ? <div className="rz-inline-feedback rz-inline-feedback--error" style={{ marginBottom: '12px' }}>{error}</div> : null}
          {isLoading ? <div className="rz-inline-feedback">Spaartegoeden laden…</div> : null}

          {!isLoading && !error && rows.length === 0 ? (
            <div className="rz-empty-state" data-testid="loyalty-stamps-empty">Er zijn nog geen aangekochte spaar- of koopzegels gevonden.</div>
          ) : null}

          {!isLoading && !error && rows.length > 0 ? (
            <Table dataTestId="loyalty-stamps-table" tableClassName="rz-stock-table">
              <thead>
                <tr className="rz-table-filter-row">
                  <th aria-label="Selectiefilter" />
                  <th>
                    <input
                      aria-label="Zoek winkelketen"
                      placeholder="Zoek"
                      value={filters.storeName}
                      onChange={(event) => updateFilter('storeName', event.target.value)}
                    />
                  </th>
                  <th>
                    <select
                      aria-label="Filter spaarprogramma"
                      value={filters.programName}
                      onChange={(event) => updateFilter('programName', event.target.value)}
                    >
                      <option value="">Filter</option>
                      {programOptions.map((option) => <option key={option} value={option}>{option}</option>)}
                    </select>
                  </th>
                  <th>
                    <input
                      aria-label="Filter aantal zegels"
                      placeholder="Filter"
                      inputMode="decimal"
                      value={filters.purchasedQuantity}
                      onChange={(event) => updateFilter('purchasedQuantity', event.target.value)}
                    />
                  </th>
                  <th>
                    <input
                      aria-label="Filter betaald bedrag"
                      placeholder="Filter"
                      inputMode="decimal"
                      value={filters.paidAmount}
                      onChange={(event) => updateFilter('paidAmount', event.target.value)}
                    />
                  </th>
                </tr>
                <tr className="rz-table-header">
                  <th className="rz-checkbox-cell">
                    <input
                      type="checkbox"
                      aria-label="Selecteer alle zichtbare spaartegoeden"
                      checked={allVisibleSelected}
                      onChange={toggleAllVisible}
                    />
                  </th>
                  <th onClick={() => setSort((current) => nextSortState(current, 'storeName', { storeName: 'asc' }))}>Winkelketen</th>
                  <th onClick={() => setSort((current) => nextSortState(current, 'programName', { programName: 'asc' }))}>Spaarprogramma</th>
                  <th className="rz-num" onClick={() => setSort((current) => nextSortState(current, 'purchasedQuantity', { purchasedQuantity: 'desc' }))}>Aantal zegels</th>
                  <th className="rz-num" onClick={() => setSort((current) => nextSortState(current, 'paidAmount', { paidAmount: 'desc' }))}>Betaald bedrag</th>
                </tr>
              </thead>
              <tbody>
                {visibleRows.map((row) => (
                  <tr key={row.id}>
                    <td className="rz-checkbox-cell">
                      <input
                        type="checkbox"
                        aria-label={`Selecteer ${row.storeName} ${row.programName}`}
                        checked={selectedIds.includes(row.id)}
                        onChange={() => toggleRow(row.id)}
                      />
                    </td>
                    <td>{row.storeName}</td>
                    <td>{row.programName}</td>
                    <td className="rz-num">{formatNumber(row.purchasedQuantity)}</td>
                    <td className="rz-num">{formatMoney(row.paidAmount)}</td>
                  </tr>
                ))}
                {visibleRows.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="rz-empty-cell">Geen regels gevonden met deze filters.</td>
                  </tr>
                ) : null}
              </tbody>
            </Table>
          ) : null}
        </ScreenCard>
      </div>
    </AppShell>
  )
}
