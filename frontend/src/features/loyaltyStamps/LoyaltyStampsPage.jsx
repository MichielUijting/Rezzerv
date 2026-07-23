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

function formatDate(value) {
  const text = String(value || '').trim()
  if (!text) return '—'
  const date = new Date(text)
  if (Number.isNaN(date.getTime())) return text
  return new Intl.DateTimeFormat('nl-NL', { dateStyle: 'medium' }).format(date)
}

function programLabel(code) {
  const text = String(code || '').trim()
  if (!text) return 'Onbekend spaarprogramma'
  return text
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase())
}

export default function LoyaltyStampsPage() {
  const [programs, setPrograms] = useState([])
  const [transactions, setTransactions] = useState([])
  const [selectedProgram, setSelectedProgram] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isLoadingTransactions, setIsLoadingTransactions] = useState(false)
  const [error, setError] = useState('')
  const [transactionError, setTransactionError] = useState('')
  const [filter, setFilter] = useState('')
  const [sort, setSort] = useState({ key: 'lastTransactionAt', direction: 'desc' })

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
    transactionCount: Number(item?.transaction_count || 0),
    lastTransactionAt: item?.last_transaction_at || '',
  })), [programs])

  const visibleRows = useMemo(() => {
    const needle = normalizeText(filter)
    const filtered = needle
      ? rows.filter((row) => normalizeText(`${row.storeName} ${row.programName}`).includes(needle))
      : rows
    return sortItems(filtered, sort, {
      storeName: (row) => row.storeName,
      programName: (row) => row.programName,
      purchasedQuantity: (row) => row.purchasedQuantity,
      paidAmount: (row) => row.paidAmount,
      transactionCount: (row) => row.transactionCount,
      lastTransactionAt: (row) => row.lastTransactionAt,
    })
  }, [filter, rows, sort])

  async function openProgram(row) {
    setSelectedProgram(row)
    setTransactions([])
    setTransactionError('')
    setIsLoadingTransactions(true)
    try {
      const query = new URLSearchParams({ stamp_program_code: row.programCode, limit: '500' })
      const response = await fetchJsonWithAuth(`/api/loyalty-stamps/transactions?${query.toString()}`, { method: 'GET' })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data?.detail || 'Transacties konden niet worden geladen')
      setTransactions(Array.isArray(data?.transactions) ? data.transactions : [])
    } catch (err) {
      setTransactionError(String(err?.message || 'Transacties konden niet worden geladen'))
    } finally {
      setIsLoadingTransactions(false)
    }
  }

  return (
    <AppShell title="Spaartegoeden" showExit={false}>
      <div style={{ display: 'grid', gap: '16px' }} data-testid="loyalty-stamps-page">
        <ScreenCard>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', alignItems: 'center', flexWrap: 'wrap', marginBottom: '12px' }}>
            <div>
              <h2 style={{ margin: 0 }}>Spaar- en koopzegels</h2>
              <p style={{ margin: '4px 0 0' }}>Read-only overzicht van aantoonbaar aangekochte spaartegoeden.</p>
            </div>
            <input
              aria-label="Zoek in spaartegoeden"
              placeholder="Zoek"
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
              style={{ minWidth: '220px' }}
            />
          </div>

          {error ? <div className="rz-inline-feedback rz-inline-feedback--error" style={{ marginBottom: '12px' }}>{error}</div> : null}
          {isLoading ? <div className="rz-inline-feedback">Spaartegoeden laden…</div> : null}
          {!isLoading && !error && visibleRows.length === 0 ? (
            <div className="rz-empty-state" data-testid="loyalty-stamps-empty">Er zijn nog geen aangekochte spaar- of koopzegels gevonden.</div>
          ) : null}

          {!isLoading && visibleRows.length > 0 ? (
            <Table dataTestId="loyalty-stamps-table" tableClassName="rz-stock-table">
              <thead>
                <tr className="rz-table-header">
                  <th onClick={() => setSort((current) => nextSortState(current, 'storeName', { storeName: 'asc' }))}>Winkelketen</th>
                  <th onClick={() => setSort((current) => nextSortState(current, 'programName', { programName: 'asc' }))}>Spaarprogramma</th>
                  <th className="rz-num" onClick={() => setSort((current) => nextSortState(current, 'purchasedQuantity', { purchasedQuantity: 'desc' }))}>Aantal zegels</th>
                  <th className="rz-num" onClick={() => setSort((current) => nextSortState(current, 'paidAmount', { paidAmount: 'desc' }))}>Betaald bedrag</th>
                  <th className="rz-num" onClick={() => setSort((current) => nextSortState(current, 'transactionCount', { transactionCount: 'desc' }))}>Transacties</th>
                  <th onClick={() => setSort((current) => nextSortState(current, 'lastTransactionAt', { lastTransactionAt: 'desc' }))}>Laatste mutatie</th>
                  <th>Actie</th>
                </tr>
              </thead>
              <tbody>
                {visibleRows.map((row) => (
                  <tr key={row.id}>
                    <td>{row.storeName}</td>
                    <td>{row.programName}</td>
                    <td className="rz-num">{formatNumber(row.purchasedQuantity)}</td>
                    <td className="rz-num">{formatMoney(row.paidAmount)}</td>
                    <td className="rz-num">{row.transactionCount}</td>
                    <td>{formatDate(row.lastTransactionAt)}</td>
                    <td><button type="button" className="rz-button" onClick={() => openProgram(row)}>Details</button></td>
                  </tr>
                ))}
              </tbody>
            </Table>
          ) : null}
        </ScreenCard>

        {selectedProgram ? (
          <ScreenCard>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', alignItems: 'center', marginBottom: '12px' }}>
              <div>
                <h2 style={{ margin: 0 }}>{selectedProgram.storeName} — {selectedProgram.programName}</h2>
                <p style={{ margin: '4px 0 0' }}>Onderliggende transacties binnen het actieve huishouden.</p>
              </div>
              <button type="button" className="rz-button" onClick={() => setSelectedProgram(null)}>Sluiten</button>
            </div>

            {transactionError ? <div className="rz-inline-feedback rz-inline-feedback--error">{transactionError}</div> : null}
            {isLoadingTransactions ? <div className="rz-inline-feedback">Transacties laden…</div> : null}
            {!isLoadingTransactions && !transactionError && transactions.length === 0 ? <div className="rz-empty-state">Geen transacties gevonden.</div> : null}

            {!isLoadingTransactions && transactions.length > 0 ? (
              <Table dataTestId="loyalty-stamp-transactions-table" tableClassName="rz-stock-table">
                <thead>
                  <tr className="rz-table-header">
                    <th>Datum</th>
                    <th>Winkelketen</th>
                    <th>Type</th>
                    <th className="rz-num">Aantal</th>
                    <th className="rz-num">Prijs per zegel</th>
                    <th className="rz-num">Totaal</th>
                    <th>Bron</th>
                  </tr>
                </thead>
                <tbody>
                  {transactions.map((transaction) => (
                    <tr key={transaction.id}>
                      <td>{formatDate(transaction.purchase_at || transaction.created_at)}</td>
                      <td>{transaction.store_name || selectedProgram.storeName}</td>
                      <td>{transaction.transaction_type || '—'}</td>
                      <td className="rz-num">{formatNumber(transaction.quantity)}</td>
                      <td className="rz-num">{formatMoney(transaction.unit_price)}</td>
                      <td className="rz-num">{formatMoney(transaction.line_total)}</td>
                      <td>{transaction.source || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            ) : null}
          </ScreenCard>
        ) : null}
      </div>
    </AppShell>
  )
}
