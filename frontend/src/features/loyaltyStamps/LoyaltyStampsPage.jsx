import { useEffect, useMemo, useState } from 'react'
import AppShell from '../../app/AppShell'
import ScreenCard from '../../ui/ScreenCard'
import DataTable from '../../ui/DataTable'
import Button from '../../ui/Button'
import { fetchJsonWithAuth } from '../../lib/authSession'

function normalizeText(value) {
  return String(value ?? '').trim().toLowerCase()
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

  const visibleRows = useMemo(() => rows.filter((row) => {
    if (filters.storeName && !normalizeText(row.storeName).includes(normalizeText(filters.storeName))) return false
    if (filters.programName && !normalizeText(row.programName).includes(normalizeText(filters.programName))) return false
    if (filters.purchasedQuantity && !normalizeText(formatNumber(row.purchasedQuantity)).includes(normalizeText(filters.purchasedQuantity))) return false
    if (filters.paidAmount && !normalizeText(formatMoney(row.paidAmount)).includes(normalizeText(filters.paidAmount))) return false
    return true
  }), [filters, rows])

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

  function requestDeleteSelected() {
    if (selectedRows.length === 0) return
    window.alert('Verwijderen wordt beschikbaar zodra de veilige permanente verwijderactie in de backend is gerealiseerd.')
  }

  const columns = useMemo(() => ([
    {
      key: 'select',
      width: 44,
      header: (
        <input
          type="checkbox"
          aria-label="Selecteer alle zichtbare spaartegoeden"
          checked={allVisibleSelected}
          onChange={toggleAllVisible}
        />
      ),
      renderCell: (row) => (
        <input
          type="checkbox"
          aria-label={`Selecteer ${row.storeName} ${row.programName}`}
          checked={selectedIds.includes(row.id)}
          onChange={() => toggleRow(row.id)}
        />
      ),
    },
    {
      key: 'storeName',
      label: 'Winkelketen',
      width: 260,
      sortable: true,
      filterable: true,
      filterPlaceholder: 'Zoek',
    },
    {
      key: 'programName',
      label: 'Spaarprogramma',
      width: 220,
      sortable: true,
      filterable: true,
      filterPlaceholder: 'Filter',
    },
    {
      key: 'purchasedQuantity',
      label: 'Aantal zegels',
      width: 140,
      align: 'right',
      sortable: true,
      filterable: true,
      filterPlaceholder: 'Filter',
      getFilterValue: (row) => formatNumber(row.purchasedQuantity),
      getSortValue: (row) => row.purchasedQuantity,
      renderCell: (row) => formatNumber(row.purchasedQuantity),
    },
    {
      key: 'paidAmount',
      label: 'Betaald bedrag',
      width: 160,
      align: 'right',
      sortable: true,
      filterable: true,
      filterPlaceholder: 'Filter',
      getFilterValue: (row) => formatMoney(row.paidAmount),
      getSortValue: (row) => row.paidAmount,
      renderCell: (row) => formatMoney(row.paidAmount),
    },
  ]), [allVisibleSelected, selectedIds, visibleRows])

  const emptyMessage = isLoading
    ? 'Spaartegoeden laden…'
    : error || 'Er zijn nog geen aangekochte spaar- of koopzegels gevonden.'

  return (
    <AppShell title="Spaartegoeden" showExit={false}>
      <div data-testid="loyalty-stamps-page">
        <ScreenCard>
          <DataTable
            columns={columns}
            data={rows}
            getRowKey={(row) => row.id}
            defaultSort={{ key: 'storeName', direction: 'asc' }}
            emptyMessage={emptyMessage}
            dataTestId="loyalty-stamps-table"
            tableClassName="rz-stock-table"
            filterState={filters}
            onFilterChange={updateFilter}
            renderRow={(row) => (
              <tr key={row.id} className={selectedIds.includes(row.id) ? 'rz-row-selected' : ''}>
                {columns.map((column) => (
                  <td key={column.key} className={column.align === 'right' ? 'rz-num' : column.cellClassName || ''}>
                    {typeof column.renderCell === 'function' ? column.renderCell(row) : row[column.key]}
                  </td>
                ))}
              </tr>
            )}
          />

          <div className="rz-stock-table-actions">
            <Button
              type="button"
              variant="secondary"
              disabled={selectedRows.length === 0}
              onClick={exportSelected}
            >
              Exporteren
            </Button>
            <Button
              type="button"
              variant="secondary"
              disabled={selectedRows.length === 0}
              onClick={requestDeleteSelected}
            >
              Verwijderen
            </Button>
          </div>
        </ScreenCard>
      </div>
    </AppShell>
  )
}
