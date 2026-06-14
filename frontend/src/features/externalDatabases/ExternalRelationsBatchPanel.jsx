import { useEffect, useState } from 'react'
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

export default function ExternalRelationsBatchPanel({ onError }) {
  const [items, setItems] = useState([])
  const [selectedKeys, setSelectedKeys] = useState([])
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
      setSelectedKeys([])
    } catch (err) {
      onError?.(err?.message || 'Externe kandidaten konden niet worden geladen')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadItems()
  }, [])

  function toggleItem(item) {
    const key = itemKey(item)
    setSelectedKeys((current) => (current.includes(key) ? current.filter((value) => value !== key) : [...current, key]))
  }

  function toggleAll() {
    const selectableKeys = items.map(itemKey).filter(Boolean)
    setSelectedKeys((current) => (current.length === selectableKeys.length ? [] : selectableKeys))
  }

  async function processSelected() {
    const candidateIds = selectedKeys.filter(Boolean)
    if (!candidateIds.length) {
      onError?.('Selecteer eerst één of meer kandidaten om in de catalogus te verwerken')
      return
    }
    setIsProcessing(true)
    setMessage('')
    try {
      const response = await fetchJsonWithAuth('/api/external-databases/catalog/process-candidates', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ candidate_ids: candidateIds, allow_create: true }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok || data?.ok === false) throw new Error(data?.detail || data?.reason || 'Catalogusverwerking is mislukt')
      setMessage(`Catalogus verwerkt: ${data.promoted_count ?? 0} van ${data.processed_count ?? candidateIds.length} geselecteerd.`)
      await loadItems()
    } catch (err) {
      onError?.(err?.message || 'Catalogusverwerking is mislukt')
    } finally {
      setIsProcessing(false)
    }
  }

  const allSelected = items.length > 0 && selectedKeys.length === items.length

  return (
    <div className="rz-external-databases-batch">
      <div className="rz-external-databases-batch-toolbar">
        <Button type="button" disabled={isProcessing || !selectedKeys.length} onClick={processSelected}>{isProcessing ? 'Verwerken...' : 'Verwerken in catalogus'}</Button>
        <Button type="button" variant="secondary" disabled={isLoading || isProcessing} onClick={loadItems}>Vernieuwen</Button>
        <span className="rz-external-databases-muted">Geselecteerd: {selectedKeys.length}. Dit maakt geen huishoudartikel en geen voorraadmutatie.</span>
      </div>
      {message ? <div className="rz-inline-feedback rz-inline-feedback--success">{message}</div> : null}
      {isLoading ? <div>Externe kandidaten worden geladen...</div> : null}
      <Table dataTestId="external-catalog-candidates-table" tableClassName="rz-external-databases-batch-table">
        <colgroup>
          <col className="rz-external-databases-col-select" />
          <col className="rz-external-databases-col-candidate" />
          <col className="rz-external-databases-col-brand" />
          <col className="rz-external-databases-col-code" />
          <col className="rz-external-databases-col-score" />
          <col className="rz-external-databases-col-status" />
        </colgroup>
        <thead>
          <tr className="rz-table-header">
            <th className="rz-check"><input type="checkbox" checked={allSelected} disabled={!items.length} onChange={toggleAll} /></th>
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
                <td className="rz-check"><input type="checkbox" checked={selectedKeys.includes(key)} onChange={() => toggleItem(item)} /></td>
                <td>{item.candidate_name || '-'}</td>
                <td>{item.candidate_brand || '-'}</td>
                <td>{item.candidate_source_product_code || item.source_product_code || item.retailer_article_number || '-'}</td>
                <td className="rz-num">{formatScore(item.score)}</td>
                <td><span className="rz-inline-feedback rz-external-databases-status">{catalogStatus(item)}</span></td>
              </tr>
            )
          }) : <tr><td colSpan="6">Geen externe kandidaten beschikbaar om in de catalogus te verwerken.</td></tr>}
        </tbody>
      </Table>
    </div>
  )
}
