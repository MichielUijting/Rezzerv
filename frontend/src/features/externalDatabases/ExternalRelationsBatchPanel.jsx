import { useEffect, useMemo, useState } from 'react'
import Button from '../../ui/Button'
import Table from '../../ui/Table'
import { fetchJsonWithAuth } from '../../lib/authSession'

function itemKey(item) {
  return String(item.id || item.candidate_id || '')
}

function formatScore(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return '-'
  return number.toLocaleString('nl-NL', { minimumFractionDigits: 3, maximumFractionDigits: 3 })
}

function catalogStatus(item) {
  if (item.global_product_id) return 'Verwerkt in catalogus'
  return 'Nog niet in catalogus'
}

function receiptLineLabel(item) {
  return String(item?.receipt_line_text || item?.raw_text || item?.parsed_name || '-').trim() || '-'
}

export default function ExternalRelationsBatchPanel({ onError }) {
  const [items, setItems] = useState([])
  const [selectedKey, setSelectedKey] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [isProcessing, setIsProcessing] = useState(false)
  const [message, setMessage] = useState('')

  async function loadItems() {
    setIsLoading(true)
    setMessage('')
    try {
      const response = await fetchJsonWithAuth('/api/external-databases/candidates?limit=100', { method: 'GET' })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data?.detail || 'Externe kandidaten konden niet worden geladen')
      const nextItems = Array.isArray(data?.items) ? data.items : []
      setItems(nextItems)
      setSelectedKey('')
    } catch (err) {
      onError?.(err?.message || 'Externe kandidaten konden niet worden geladen')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadItems()
  }, [])

  const selectedItem = useMemo(() => items.find((item) => itemKey(item) === selectedKey) || null, [items, selectedKey])
  const activeReceiptLine = receiptLineLabel(selectedItem || items[0])

  async function processSelected() {
    if (!selectedKey) {
      onError?.('Selecteer eerst één kandidaat om in de catalogus te verwerken')
      return
    }
    setIsProcessing(true)
    setMessage('')
    try {
      const response = await fetchJsonWithAuth('/api/external-databases/catalog/process-candidates', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ candidate_ids: [selectedKey], allow_create: true }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok || data?.ok === false) throw new Error(data?.detail || data?.reason || 'Catalogusverwerking is mislukt')
      setMessage(`Catalogus verwerkt: ${data.promoted_count ?? 0} kandidaat.`)
      await loadItems()
    } catch (err) {
      onError?.(err?.message || 'Catalogusverwerking is mislukt')
    } finally {
      setIsProcessing(false)
    }
  }

  return (
    <div className="rz-external-databases-batch">
      <div className="rz-external-databases-context-card">
        <div className="rz-external-databases-context-label">Bonartikel in behandeling</div>
        <div className="rz-external-databases-context-value">{activeReceiptLine}</div>
        <div className="rz-external-databases-context-helper">Kies hieronder precies één externe kandidaat voor dit bonartikel.</div>
      </div>

      <div className="rz-external-databases-batch-toolbar">
        <Button type="button" disabled={isProcessing || !selectedKey} onClick={processSelected}>{isProcessing ? 'Verwerken...' : 'Verwerk gekozen kandidaat in catalogus'}</Button>
        <Button type="button" variant="secondary" disabled={isLoading || isProcessing} onClick={loadItems}>Vernieuwen</Button>
        <span className="rz-external-databases-muted">Gekozen: {selectedKey ? 1 : 0}. Dit maakt geen huishoudartikel en geen voorraadmutatie.</span>
      </div>
      {message ? <div className="rz-inline-feedback rz-inline-feedback--success">{message}</div> : null}
      {isLoading ? <div>Externe kandidaten worden geladen...</div> : null}
      <Table dataTestId="external-catalog-candidates-table" tableClassName="rz-external-databases-batch-table">
        <colgroup>
          <col className="rz-external-databases-col-select" />
          <col className="rz-external-databases-col-receipt-line" />
          <col className="rz-external-databases-col-candidate" />
          <col className="rz-external-databases-col-brand" />
          <col className="rz-external-databases-col-code" />
          <col className="rz-external-databases-col-score" />
          <col className="rz-external-databases-col-status" />
        </colgroup>
        <thead>
          <tr className="rz-table-header">
            <th className="rz-check">Keuze</th>
            <th>Bonartikel</th>
            <th>Kandidaat</th>
            <th>Merk</th>
            <th>Artikelnummer</th>
            <th className="rz-num">Score</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {items.length ? items.map((item) => {
            const key = itemKey(item)
            return (
              <tr key={key}>
                <td className="rz-check"><input type="radio" name="catalog-candidate" checked={selectedKey === key} onChange={() => setSelectedKey(key)} /></td>
                <td>{receiptLineLabel(item)}</td>
                <td>{item.candidate_name || '-'}</td>
                <td>{item.candidate_brand || '-'}</td>
                <td>{item.candidate_source_product_code || item.source_product_code || item.retailer_article_number || '-'}</td>
                <td className="rz-num">{formatScore(item.score)}</td>
                <td><span className="rz-inline-feedback rz-external-databases-status">{catalogStatus(item)}</span></td>
              </tr>
            )
          }) : <tr><td colSpan="7">Geen externe kandidaten beschikbaar om in de catalogus te verwerken.</td></tr>}
        </tbody>
      </Table>
    </div>
  )
}
