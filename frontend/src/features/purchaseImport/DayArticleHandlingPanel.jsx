import { useEffect, useMemo, useState } from 'react'
import ScreenCard from '../../ui/ScreenCard'
import Table from '../../ui/Table'
import { fetchJson } from '../stores/storeImportShared'
import {
  fetchInventoryHandlingByArticleIds,
  inventoryHandlingPresentation,
  STOCK,
} from '../receipts/dayArticleHandling.js'

function lineArticleId(line) {
  return String(line?.matched_household_article_id || '').trim()
}

function lineArticleLabel(line) {
  return String(
    line?.matched_household_article_name
      || line?.household_article_name
      || line?.article_name_raw
      || line?.article_name
      || 'Onbekend artikel'
  ).trim()
}

export default function DayArticleHandlingPanel({ batchId = '' }) {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false

    async function load() {
      const normalizedBatchId = String(batchId || '').trim()
      if (!normalizedBatchId) {
        setRows([])
        return
      }

      setLoading(true)
      setError('')
      try {
        const [household, batch] = await Promise.all([
          fetchJson('/api/household'),
          fetchJson(`/api/purchase-import-batches/${encodeURIComponent(normalizedBatchId)}?_ts=${Date.now()}`),
        ])
        if (cancelled) return

        const householdId = String(household?.active_household_id ?? household?.id ?? batch?.household_id ?? '').trim()
        const lines = Array.isArray(batch?.lines) ? batch.lines : []
        const articleIds = lines.map(lineArticleId).filter(Boolean)
        const defaults = await fetchInventoryHandlingByArticleIds(householdId, articleIds)
        if (cancelled) return

        setRows(lines.map((line, index) => {
          const articleId = lineArticleId(line)
          const presentation = articleId
            ? (defaults[articleId] || inventoryHandlingPresentation(STOCK))
            : inventoryHandlingPresentation(STOCK)
          return {
            id: String(line?.id || `${normalizedBatchId}-line-${index + 1}`),
            article: lineArticleLabel(line),
            linked: Boolean(articleId),
            ...presentation,
          }
        }))
      } catch (loadError) {
        if (!cancelled) {
          setRows([])
          setError(loadError?.message || 'Standaardverwerking kon niet worden geladen.')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    return () => { cancelled = true }
  }, [batchId])

  const visibleRows = useMemo(() => rows.filter((row) => row.linked), [rows])

  return (
    <ScreenCard fullWidth>
      <div style={{ display: 'grid', gap: 12 }} data-testid="uitpakken-day-article-handling-panel">
        <div>
          <h3 style={{ margin: 0, fontSize: 18 }}>Standaardverwerking</h3>
          <p style={{ margin: '4px 0 0', color: '#667085' }}>
            Deze waarden komen uit Beheer Artikelgroepen. Wijzigen per bonregel volgt in B3.
          </p>
        </div>

        {error ? <div className="rz-inline-feedback rz-inline-feedback--error">{error}</div> : null}

        <Table dataTestId="uitpakken-day-article-handling-table" tableStyle={{ tableLayout: 'fixed', width: '100%' }}>
          <colgroup>
            <col style={{ width: '40%' }} />
            <col style={{ width: '28%' }} />
            <col style={{ width: '16%' }} />
            <col style={{ width: '16%' }} />
          </colgroup>
          <thead>
            <tr className="rz-table-header">
              <th>Artikel</th>
              <th>Standaardverwerking</th>
              <th>Locatie</th>
              <th>Sublocatie</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={4}>Standaardverwerking laden…</td></tr>
            ) : visibleRows.length === 0 ? (
              <tr><td colSpan={4}>Nog geen gekoppelde huishoudartikelen beschikbaar.</td></tr>
            ) : visibleRows.map((row) => (
              <tr key={row.id}>
                <td>{row.article}</td>
                <td>{row.label}</td>
                <td>{row.location || 'Bestaande keuze'}</td>
                <td>{row.sublocation || 'Bestaande keuze'}</td>
              </tr>
            ))}
          </tbody>
        </Table>
      </div>
    </ScreenCard>
  )
}
