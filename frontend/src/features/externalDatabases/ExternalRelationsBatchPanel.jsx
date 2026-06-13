import { useEffect, useState } from 'react'
import Button from '../../ui/Button'
import Table from '../../ui/Table'
import { fetchJsonWithAuth } from '../../lib/authSession'

function itemKey(item) {
  return `${item.candidate_id || ''}:${item.household_article_id || ''}`
}

function formatScore(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return '-'
  return number.toLocaleString('nl-NL', { minimumFractionDigits: 3, maximumFractionDigits: 3 })
}

export default function ExternalRelationsBatchPanel({ onError }) {
  const [items, setItems] = useState([])
  const [selectedKeys, setSelectedKeys] = useState([])
  const [isLoading, setIsLoading] = useState(false)
  const [isLinking, setIsLinking] = useState(false)
  const [message, setMessage] = useState('')

  async function loadItems() {
    setIsLoading(true)
    setMessage('')
    try {
      const response = await fetchJsonWithAuth('/api/admin/external-relations/batch?limit=50', { method: 'GET' })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data?.detail || 'Externe relaties konden niet worden geladen')
      const nextItems = Array.isArray(data?.items) ? data.items : []
      setItems(nextItems)
      setSelectedKeys([])
    } catch (err) {
      onError?.(err?.message || 'Externe relaties konden niet worden geladen')
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
    setSelectedKeys((current) => (current.length === items.length ? [] : items.map(itemKey)))
  }

  async function linkSelected() {
    const selectedItems = items.filter((item) => selectedKeys.includes(itemKey(item)))
    if (!selectedItems.length) {
      onError?.('Selecteer eerst één of meer relaties om te koppelen')
      return
    }
    setIsLinking(true)
    setMessage('')
    try {
      let linked = 0
      for (const item of selectedItems) {
        const response = await fetchJsonWithAuth('/api/admin/external-relations/batch/decision', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ candidate_id: item.candidate_id, household_article_id: item.household_article_id, decision: 'apply', decision_reason: 'M2C2g UI Koppelen' }),
        })
        const data = await response.json().catch(() => ({}))
        if (!response.ok || data?.ok === false) throw new Error(data?.detail || data?.reason || 'Koppelen is mislukt')
        if (data?.applied) linked += 1
      }
      setMessage(`Relaties gekoppeld: ${linked} van ${selectedItems.length} geselecteerd.`)
      await loadItems()
    } catch (err) {
      onError?.(err?.message || 'Koppelen is mislukt')
    } finally {
      setIsLinking(false)
    }
  }

  const allSelected = items.length > 0 && selectedKeys.length === items.length

  return (
    <div className="rz-external-databases-batch">
      <div className="rz-external-databases-batch-toolbar">
        <Button type="button" disabled={isLinking || !selectedKeys.length} onClick={linkSelected}>{isLinking ? 'Koppelen...' : 'Koppelen'}</Button>
        <Button type="button" variant="secondary" disabled={isLoading || isLinking} onClick={loadItems}>Vernieuwen</Button>
        <span className="rz-external-databases-muted">Geselecteerd: {selectedKeys.length}. Geen nieuw huishoudartikel en geen voorraadmutatie.</span>
      </div>
      {message ? <div className="rz-inline-feedback rz-inline-feedback--success">{message}</div> : null}
      {isLoading ? <div>Externe relaties worden geladen...</div> : null}
      <Table dataTestId="external-relation-batch-table" tableClassName="rz-external-databases-batch-table">
        <colgroup>
          <col className="rz-external-databases-col-select" />
          <col className="rz-external-databases-col-candidate" />
          <col className="rz-external-databases-col-brand" />
          <col className="rz-external-databases-col-household" />
          <col className="rz-external-databases-col-score" />
          <col className="rz-external-databases-col-status" />
        </colgroup>
        <thead>
          <tr className="rz-table-header">
            <th className="rz-check"><input type="checkbox" checked={allSelected} disabled={!items.length} onChange={toggleAll} /></th>
            <th>Kandidaat</th>
            <th>Merk</th>
            <th>Huishoudartikel</th>
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
                <td>{item.candidate_name || item.global_product_name || '-'}</td>
                <td>{item.candidate_brand || item.global_product_brand || '-'}</td>
                <td>{item.household_article_name || '-'}</td>
                <td className="rz-num">{formatScore(item.score)}</td>
                <td><span className="rz-inline-feedback rz-external-databases-status">klaar voor koppelen</span></td>
              </tr>
            )
          }) : <tr><td colSpan="6">Geen externe relaties beschikbaar om te koppelen.</td></tr>}
        </tbody>
      </Table>
    </div>
  )
}
